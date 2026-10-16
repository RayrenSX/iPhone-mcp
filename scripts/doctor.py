"""Read-only end-to-end MCP diagnosis. Never prints credentials or device IDs."""
import asyncio
import json
import sys
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def payload(result):
    if result.isError:
        raise RuntimeError("MCP_TOOL_FAILED")
    return json.loads(next(item.text for item in result.content if item.type == "text"))


async def diagnose():
    report = {"ready": False, "checks": {}, "devices": []}
    stage = "mcp_start"
    try:
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "iphonemirror_mcp", "--local-key-store"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=35)) as session:
                await session.initialize()
                report["checks"]["mcpInitialize"] = True
                tools = (await session.list_tools()).tools
                report["checks"]["toolCount"] = len(tools)
                stage = "api_devices"
                devices = payload(await session.call_tool("list_devices", {}))["devices"]
                report["checks"]["apiConnected"] = True
                for index, device in enumerate(devices):
                    item = {"index": index, "controlAvailable": False,
                            "screenshot": False, "ocr": False}
                    report["devices"].append(item)
                    # Screenshot readiness is determined by the actual response, not guessed status fields.
                    stage = "snapshot"
                    shot = await session.call_tool("snapshot", {"device_id": device["id"], "use_ocr": False})
                    if shot.isError:
                        continue
                    data = payload(shot)
                    status = data["status"]
                    item["controlAvailable"] = status.get("control", {}).get("available", False)
                    item["screenshot"] = any(c.type == "image" for c in shot.content)
                    geometry = status["geometry"]
                    item["dimensions"] = [geometry["width"], geometry["height"]]
                    stage = "ocr"
                    ocr = await session.call_tool("snapshot", {"device_id": device["id"],
                                                               "use_ocr": True, "include_image": False})
                    if not ocr.isError:
                        item["ocr"] = True
                        item["ocrLanguage"] = payload(ocr)["ocr"].get("language")
                report["ready"] = any(d["screenshot"] for d in report["devices"])
                report["controlReady"] = any(d["screenshot"] and d["controlAvailable"] for d in report["devices"])
                if not report["ready"]:
                    report["action"] = "Connect/unlock/trust a device and call start_iphonemirror for on-demand screenshots; rerun doctor."
    except Exception:
        # Server logs may show a local diagnostic, but JSON never includes arbitrary exceptions/secrets.
        report["failedStage"] = stage
        report["action"] = "Check iPhoneMirror is running with Automation API enabled under the same Windows user; see docs/SETUP.md."
    return report


def main():
    try:
        report = asyncio.run(asyncio.wait_for(diagnose(), timeout=180))
    except TimeoutError:
        report = {"ready": False, "failedStage": "timeout", "action": "Check the app/API and rerun doctor."}
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
