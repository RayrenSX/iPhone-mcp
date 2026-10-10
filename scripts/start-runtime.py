"""Invoke the actual MCP background-start tool without sending phone input."""
import asyncio
import json
import sys
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run():
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "iphonemirror_mcp", "--local-key-store"])
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=120)) as session:
            await session.initialize()
            result = await session.call_tool("start_iphonemirror", {})
            if result.isError:
                print("Background startup failed. Check the installed runtime and port.")
                return 2
            output = json.loads(next(c.text for c in result.content if c.type == "text"))
            if output.get("actionRequired") == "wait_for_setup":
                print(json.dumps({"actionRequired": "wait_for_setup", "setup": output["setup"]}))
                return 2
            output.pop("device_id", None)
            print(json.dumps(output, indent=2))
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
