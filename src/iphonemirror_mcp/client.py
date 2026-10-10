"""HTTP adapter. Credentials and leases stay inside this process."""

import asyncio
from urllib.parse import quote, urlsplit

import httpx


class AutomationClient:
    def __init__(self, key: str, address: str = "http://127.0.0.1:17890", *, transport=None):
        url = urlsplit(address)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost"}
                or url.username is not None or url.password is not None
                or url.path not in {"", "/"} or url.query or url.fragment):
            raise ValueError("IPHONEMIRROR_API_URL must be a local HTTP origin, e.g. http://127.0.0.1:17890")
        if not key.strip() or any(c in key for c in "\r\n"):
            raise ValueError("Set IPHONEMIRROR_API_KEY to the key copied from Developer tools")
        self.http = httpx.AsyncClient(
            base_url=address.rstrip("/") + "/api/v1/", headers={"X-API-Key": key},
            timeout=httpx.Timeout(30, connect=3), follow_redirects=False, trust_env=False,
            transport=transport or httpx.AsyncHTTPTransport(retries=0),
        )
        self.sessions: dict[str, str] = {}
        self._lease_locks: dict[str, asyncio.Lock] = {}
        self.observations: dict[str, dict] = {}

    @staticmethod
    def path(device_id: str, suffix: str = "") -> str:
        if not device_id or device_id in {".", ".."}:
            raise ValueError("Use the opaque device_id returned by list_devices")
        return "devices/" + quote(device_id, safe="") + suffix

    async def request(self, method: str, path: str, body=None, *, device_id=None,
                      control=False, binary=False, timeout=None):
        headers = {}
        if control:
            token = self.sessions.get(device_id)
            if token is None:
                raise RuntimeError("CONTROL_REQUIRED: call acquire_control for this device first")
            headers["X-Control-Session"] = token
        try:
            options = {"timeout": timeout} if timeout is not None else {}
            response = await self.http.request(method, path, json=body, headers=headers, **options)
        except httpx.TimeoutException:
            raise RuntimeError("API_TIMEOUT: the action may already have happened. Do not retry input automatically; inspect device status and screenshot first.") from None
        except httpx.RequestError:
            raise RuntimeError("API_CONNECTION_FAILED: check iPhoneMirror and its local Automation API. Input effects may be unknown; do not retry input automatically.") from None
        if not response.is_success:
            # Do not expose headers, request bodies, or redirects containing credentials.
            try:
                detail = response.json()["error"]
                code, message = detail["code"], detail["message"]
                if not isinstance(code, str) or not isinstance(message, str):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                code, message = "API_HTTP_ERROR", f"HTTP {response.status_code}"
            retry = response.headers.get("Retry-After")
            hint = f"; Retry-After: {retry}" if response.status_code == 429 and retry else ""
            raise RuntimeError(f"{code}: {message}{hint}")
        if binary:
            if response.headers.get("content-type", "").split(";")[0] != "image/png" or not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("INVALID_API_RESPONSE: expected a PNG screenshot")
            return response.content
        if response.status_code == 204:
            return {"status": "completed"}
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except ValueError:
            raise RuntimeError("INVALID_API_RESPONSE: expected a JSON object") from None

    async def acquire(self, device_id: str, duration_seconds: int):
        async with self._lease_locks.setdefault(device_id, asyncio.Lock()):
            result = await self.request(
                "POST", self.path(device_id, "/control/acquire"),
                {"durationSeconds": duration_seconds}, device_id=device_id,
                control=device_id in self.sessions,
            )
            token = result.get("sessionToken")
            if not isinstance(token, str) or not token:
                raise RuntimeError("INVALID_API_RESPONSE: missing control session")
            self.sessions[device_id] = token
            return {"status": "acquired", "expiresAt": result.get("expiresAt")}

    async def release(self, device_id: str):
        async with self._lease_locks.setdefault(device_id, asyncio.Lock()):
            if device_id not in self.sessions:
                return {"status": "not_acquired"}
            # Retain the token on failure so an explicit release can be attempted again.
            await self.request("POST", self.path(device_id, "/control/release"),
                               device_id=device_id, control=True)
            self.sessions.pop(device_id, None)
            return {"status": "released"}

    async def input(self, device_id: str, action: str, **body):
        return await self.request("POST", self.path(device_id, "/input/" + action),
                                  body, device_id=device_id, control=True)

    async def close(self):
        async def release_one(device_id):
            try:
                await asyncio.wait_for(self.release(device_id), timeout=3)
            except (Exception, asyncio.CancelledError):
                pass  # App-side TTL also revokes leases after abrupt process termination.
        try:
            await asyncio.gather(*(release_one(d) for d in list(self.sessions)))
        finally:
            await self.http.aclose()
