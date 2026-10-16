"""Invoke the actual MCP background-start tool without sending phone input."""
import asyncio
import argparse
import json
import sys
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(capture_mode="on_demand", device_id=None):
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "iphonemirror_mcp", "--local-key-store"])
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=120)) as session:
            await session.initialize()
            arguments = {"capture_mode": capture_mode}
            if device_id is not None:
                arguments["device_id"] = device_id
            result = await session.call_tool("start_iphonemirror", arguments)
            if result.isError:
                print("Background startup failed. Check the installed runtime and port.")
                return 2
            output = json.loads(next(c.text for c in result.content if c.type == "text"))
            if output.get("actionRequired") == "wait_for_setup":
                print(json.dumps({"actionRequired": "wait_for_setup", "setup": output["setup"]}))
                return 2
            output.pop("device_id", None)
            print(json.dumps(output, indent=2))
            return 0 if output.get("devicePrepared") else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("on_demand", "continuous"), default="on_demand",
                        help="Screen observation mode (default: on_demand)")
    parser.add_argument("--continuous-capture", action="store_true",
                        help="Compatibility alias for --mode continuous")
    parser.add_argument("--device-id", help="Select the device_id returned by list_devices when several are online")
    arguments = parser.parse_args()
    mode = "continuous" if arguments.continuous_capture else arguments.mode
    sys.exit(asyncio.run(run(mode, arguments.device_id)))
