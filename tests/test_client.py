import asyncio
import unittest

import httpx

from iphonemirror_mcp.client import AutomationClient


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.handler = lambda r: httpx.Response(200, json={"status": "dispatched"})

        async def dispatch(request):
            self.requests.append(request)
            self.assertEqual(request.headers["X-API-Key"], "test-key")
            return self.handler(request)

        self.api = AutomationClient("test-key", transport=httpx.MockTransport(dispatch))

    async def asyncTearDown(self):
        await self.api.close()

    def lease_response(self, request):
        if request.url.path.endswith("/control/acquire"):
            return httpx.Response(200, json={"sessionToken": "secret-session", "expiresAt": "later"})
        return httpx.Response(204)

    async def test_control_is_explicit_and_token_is_private(self):
        with self.assertRaisesRegex(RuntimeError, "CONTROL_REQUIRED"):
            await self.api.input("a", "tap", x=1, y=2)
        self.assertEqual(self.requests, [])
        self.handler = self.lease_response
        result = await self.api.acquire("a", 30)
        self.assertNotIn("secret-session", str(result))
        self.assertNotIn("X-Control-Session", self.requests[0].headers)
        await self.api.acquire("a", 60)
        self.assertEqual(self.requests[1].headers["X-Control-Session"], "secret-session")
        await self.api.input("a", "tap", x=1, y=2, geometryVersion="frame-1")
        self.assertIn(b'"geometryVersion":"frame-1"', self.requests[-1].content)
        await self.api.release("a")
        self.assertEqual(self.api.sessions, {})
        self.assertEqual(await self.api.release("a"), {"status": "not_acquired"})

    async def test_tokens_are_not_shared_between_devices(self):
        self.handler = self.lease_response
        await self.api.acquire("a", 30)
        with self.assertRaisesRegex(RuntimeError, "CONTROL_REQUIRED"):
            await self.api.input("b", "text", text="hello")
        await self.api.request("GET", self.api.path("a", "/status"))
        self.assertNotIn("X-Control-Session", self.requests[-1].headers)

    async def test_release_failure_retains_token_for_cleanup(self):
        self.handler = self.lease_response
        await self.api.acquire("a", 30)
        self.handler = lambda r: httpx.Response(503, json={"error": {"code": "UNAVAILABLE", "message": "offline"}})
        with self.assertRaisesRegex(RuntimeError, "UNAVAILABLE"):
            await self.api.release("a")
        self.assertEqual(self.api.sessions["a"], "secret-session")
        self.handler = self.lease_response
        await self.api.close()
        self.assertEqual(self.api.sessions, {})

    async def test_input_timeout_is_not_retried(self):
        self.api.sessions["a"] = "secret-session"

        def timeout(request):
            raise httpx.ReadTimeout("secret-session test-key", request=request)

        self.handler = timeout
        with self.assertRaisesRegex(RuntimeError, "may already have happened") as caught:
            await self.api.input("a", "tap", x=1, y=2)
        self.assertEqual(len(self.requests), 1)
        self.assertNotIn("secret-session", str(caught.exception))
        self.assertNotIn("test-key", str(caught.exception))
        self.api.sessions.clear()

    async def test_errors_and_rate_limit_are_reported_without_retry(self):
        for status, code in [(401, "UNAUTHORIZED"), (403, "FORBIDDEN"), (409, "GEOMETRY_CHANGED"),
                             (422, "INVALID_COORDINATE"), (429, "RATE_LIMITED"), (503, "SCREENSHOT_UNAVAILABLE")]:
            with self.subTest(status=status):
                self.handler = lambda r: httpx.Response(status, json={"error": {"code": code, "message": "detail"}}, headers={"Retry-After": "2"})
                before = len(self.requests)
                with self.assertRaisesRegex(RuntimeError, code) as caught:
                    await self.api.request("GET", "devices")
                self.assertEqual(len(self.requests), before + 1)
                if status == 429:
                    self.assertIn("Retry-After: 2", str(caught.exception))

    async def test_redirect_is_not_followed(self):
        self.handler = lambda r: httpx.Response(302, headers={"Location": "https://example.com/"})
        with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
            await self.api.request("GET", "devices")
        self.assertEqual(len(self.requests), 1)

    async def test_screenshot_and_invalid_response(self):
        png = b"\x89PNG\r\n\x1a\nfixture"
        self.handler = lambda r: httpx.Response(200, content=png, headers={"Content-Type": "image/png"})
        self.assertEqual(await self.api.request("GET", "devices/a/screenshot", binary=True), png)
        self.handler = lambda r: httpx.Response(200, text="not png")
        with self.assertRaisesRegex(RuntimeError, "expected a PNG"):
            await self.api.request("GET", "devices/a/screenshot", binary=True)
        with self.assertRaisesRegex(RuntimeError, "expected a JSON object"):
            await self.api.request("GET", "devices")

    async def test_concurrent_acquire_renews_same_session(self):
        self.handler = self.lease_response
        await asyncio.gather(self.api.acquire("a", 30), self.api.acquire("a", 30))
        self.assertNotIn("X-Control-Session", self.requests[0].headers)
        self.assertEqual(self.requests[1].headers["X-Control-Session"], "secret-session")


class ConfigurationTests(unittest.TestCase):
    def test_reject_remote_origins_and_credentials(self):
        for address in ["https://127.0.0.1", "http://example.com", "http://127.0.0.1.evil",
                        "http://user:password@localhost", "http://localhost/api", "http://localhost?key=secret"]:
            with self.subTest(address=address), self.assertRaises(ValueError):
                AutomationClient("test-key", address)
        with self.assertRaises(ValueError):
            AutomationClient("")

    def test_device_id_cannot_inject_an_endpoint(self):
        self.assertEqual(AutomationClient.path("usb:abc/def?x=1", "/status"),
                         "devices/usb%3Aabc%2Fdef%3Fx%3D1/status")
        for device in ["", ".", ".."]:
            with self.assertRaises(ValueError):
                AutomationClient.path(device)
