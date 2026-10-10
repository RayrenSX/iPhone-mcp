"""Run an explicit MCP test plan against a real device; always release control."""

import argparse
import asyncio
import base64
import json
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image


async def run(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8")) if args.plan else [{"tool": "snapshot", "args": {"language": "en-US", "max_width": 0}}]
    params = StdioServerParameters(command=sys.executable, args=["-m", "iphonemirror_mcp", "--local-key-store"])
    report = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=40)) as session:
            await session.initialize()
            schemas = {tool.name: tool.inputSchema for tool in (await session.list_tools()).tools}
            listed = await session.call_tool("list_devices", {})
            devices = json.loads(listed.content[0].text)["devices"]
            device = devices[args.device]["id"]
            print(json.dumps({"tools": len(schemas), "deviceIndex": args.device,
                              "capabilities": devices[args.device]["capabilities"]}), flush=True)
            latest = None
            touch_id = None
            try:
                for index, step in enumerate(plan):
                    tool = step["tool"]
                    supplied = step.get("args", {}).copy()
                    if supplied.get("touch_id") == "$last_touch_id":
                        supplied["touch_id"] = touch_id
                    properties = schemas[tool].get("properties", {})
                    if "device_id" in properties:
                        supplied.setdefault("device_id", device)
                    if "geometry_version" in properties and "geometry_version" not in supplied:
                        status = await session.call_tool("get_device_status", {"device_id": device})
                        supplied["geometry_version"] = json.loads(status.content[0].text)["geometry"]["version"]
                    if tool == "click_element" and "match" in step:
                        elements = [e for e in latest["ocr"]["elements"] if step["match"].casefold() in e["text"].casefold()]
                        if len(elements) != 1:
                            raise RuntimeError(f"OCR match must be unique: {len(elements)} results")
                        supplied.update(snapshot_id=latest["snapshotId"], element_id=elements[0]["id"])
                    result = await session.call_tool(tool, supplied)
                    record = {"step": index, "tool": tool, "isError": bool(result.isError)}
                    for content in result.content:
                        if content.type == "image":
                            path = output / f"{index:02d}-{tool}.png"
                            path.write_bytes(base64.b64decode(content.data))
                            with Image.open(path) as shot:
                                record["image"] = {"file": path.name, "width": shot.width, "height": shot.height}
                        elif content.type == "text":
                            try:
                                data = json.loads(content.text)
                            except ValueError:
                                data = {"message": content.text}
                            if tool == "snapshot" and not result.isError:
                                latest = data
                                (output / f"{index:02d}-snapshot.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                                record["observation"] = {"geometry": data["status"]["geometry"],
                                    "imageTransform": data["imageTransform"], "ocrText": data["ocr"].get("text", ""),
                                    "elements": len(data["ocr"]["elements"])}
                            else:
                                record["result"] = data
                                if tool == "touch_down":
                                    touch_id = data.get("touchId")
                    report.append(record)
                    print(json.dumps(record, ensure_ascii=True), flush=True)
                    if result.isError:
                        raise RuntimeError(f"{tool} failed; no further input dispatched")
            finally:
                result = await session.call_tool("release_control", {"device_id": device})
                report.append({"tool": "release_control", "isError": bool(result.isError)})
                final = await session.call_tool("get_device_status", {"device_id": device})
                if not final.isError:
                    state = json.loads(final.content[0].text)
                    report.append({"tool": "get_device_status", "controlAcquiredAfterRelease": state["control"]["acquired"]})
                (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--plan", help="Explicit JSON array of tool calls; may send real device input")
    parser.add_argument("--output", default="artifacts/probe")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
