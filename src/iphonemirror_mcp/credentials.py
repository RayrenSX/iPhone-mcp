"""Read iPhoneMirror's current-user DPAPI key without copying it into MCP config."""

import json
import os
from pathlib import Path


def configuration() -> tuple[str, str]:
    key = os.environ.get("IPHONEMIRROR_API_KEY", "")
    address = os.environ.get("IPHONEMIRROR_API_URL", "")
    if os.environ.get("IPHONEMIRROR_LOCAL_KEY_STORE") == "1":
        if os.name != "nt":
            raise RuntimeError("The local DPAPI key store requires Windows")
        import win32crypt

        folder = Path(os.environ["LOCALAPPDATA"]) / "iPhoneMirror"
        if not key:
            try:
                encrypted = (folder / "automation-key.bin").read_bytes()
                key = win32crypt.CryptUnprotectData(
                    encrypted, b"iPhoneMirror.Automation.v1", None, None, 0
                )[1].decode("utf-8")
            except Exception:
                raise RuntimeError("Cannot read the iPhoneMirror key store; enable Automation API in Developer tools under this Windows user") from None
        if not address:
            try:
                settings = json.loads((folder / "settings.json").read_text(encoding="utf-8-sig"))
                port = int(settings.get("AutomationApi", {}).get("Port", 17890))
                address = f"http://127.0.0.1:{port}"
            except (OSError, ValueError, TypeError):
                raise RuntimeError("Cannot read iPhoneMirror API settings; set IPHONEMIRROR_API_URL explicitly") from None
    return key, address or "http://127.0.0.1:17890"
