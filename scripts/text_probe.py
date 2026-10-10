"""Verify paste/key/clipboard on an already focused Safari address field, without submitting."""

import asyncio
import argparse
import base64
import json
import sys
from pathlib import Path

import win32crypt

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(resume=False):
    folder = Path(__file__).resolve().parents[1] / "artifacts/text-probe"
    folder.mkdir(parents=True, exist_ok=True)
    params = StdioServerParameters(command=sys.executable, args=["-m", "iphonemirror_mcp", "--local-key-store"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            devices = await session.call_tool("list_devices", {})
            device = json.loads(devices.content[0].text)["devices"][0]["id"]

            async def call(tool, **args):
                result = await session.call_tool(tool, {"device_id": device, **args})
                if result.isError:
                    raise RuntimeError(f"{tool}: {result.content[0].text}")
                return result

            async def shot(name):
                result = await call("snapshot", language="en-US", max_width=800)
                metadata = json.loads(result.content[0].text)
                for c in result.content:
                    if c.type == "image":
                        (folder / f"{name}.png").write_bytes(base64.b64decode(c.data))
                return metadata

            backup = folder / "clipboard-original.dpapi"
            purpose = b"iPhone-mcp.TextProbe.v1"
            if resume and backup.exists():
                original = win32crypt.CryptUnprotectData(backup.read_bytes(), purpose, None, None, 0)[1].decode("utf-8")
            else:
                original = json.loads((await call("read_clipboard")).content[0].text)["text"]
                if not resume:
                    backup.write_bytes(win32crypt.CryptProtectData(original.encode("utf-8"), None, purpose, None, None, 0))
            marker, clip_marker = "iphone-mcp-20261010", "iphone-mcp-clipboard-20261010"
            paste_confirmed = False
            report = {}
            await call("acquire_control", duration_seconds=90)
            try:
                # Focus was explicitly established and inspected by focus-address.json.
                if not resume:
                    await call("type_text", text=marker)
                    await asyncio.sleep(1)
                after = await shot("01-paste")
                recognized = after["ocr"].get("text", "")
                paste_confirmed = marker in recognized
                report["pasteVisibleInOcr"] = paste_confirmed
                report["pastePromptVisible"] = "allow paste" in recognized.casefold()
                if not paste_confirmed:
                    raise RuntimeError("Paste not visually confirmed; leaving clipboard untouched while a prompt may be pending")
                await call("press_key", key="BACKSPACE")
                await asyncio.sleep(0.5)
                after_key = await shot("02-backspace")
                report["backspaceVisibleInOcr"] = marker[:-1] in after_key["ocr"].get("text", "")
                await call("press_key", key="ESCAPE")
                await asyncio.sleep(0.5)
                await shot("03-escape")
                await call("write_clipboard", text=clip_marker)
                copied = json.loads((await call("read_clipboard")).content[0].text)["text"]
                report["clipboardRoundtrip"] = copied == clip_marker
            finally:
                try:
                    if paste_confirmed:
                        current = json.loads((await call("read_clipboard")).content[0].text)["text"]
                        if current in {marker, clip_marker}:
                            await call("write_clipboard", text=original)
                            report["clipboardRestored"] = True
                            backup.unlink(missing_ok=True)
                        else:
                            report["clipboardRestored"] = False
                finally:
                    await call("release_control")
                    (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-after-permission", action="store_true")
    asyncio.run(run(parser.parse_args().resume_after_permission))
