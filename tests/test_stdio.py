"""Exercise the installed entry point with a real MCP client and fake local API."""

import base64
import json
import sys
import tempfile
import threading
import unittest
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5XcAAAAASUVORK5CYII=")


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_initializes_without_api_key_or_running_app(self):
        params = StdioServerParameters(command=sys.executable, args=["-m", "iphonemirror_mcp"],
            env={"IPHONEMIRROR_API_KEY": "", "IPHONEMIRROR_LOCAL_KEY_STORE": "0"})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                names = set(tools)
                self.assertTrue({"start_iphonemirror", "get_app_status", "open_independent_window"} <= names)
                properties = tools["start_iphonemirror"].inputSchema["properties"]
                self.assertEqual(properties["capture_mode"]["default"], "on_demand")
                self.assertEqual(properties["capture_mode"]["enum"], ["on_demand", "continuous"])
                self.assertIs(properties["enable_control"]["default"], True)

    async def asyncSetUp(self):
        self.requests = []
        requests = self.requests
        self.capabilities = {"shortcuts": ["home", "app_switcher", "control_center", "notification_center",
                                           "dock", "siri", "volume_up", "volume_down", "lock_screen"]}
        capabilities = self.capabilities

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                requests.append((self.command, self.path, dict(self.headers), json.loads(body) if body else None))
                status, payload, kind = 200, {}, "application/json"
                if self.headers.get("X-API-Key") != "fixture-key":
                    status, payload = 401, {"error": {"code": "UNAUTHORIZED", "message": "bad key"}}
                elif self.path == "/api/v1/devices":
                    payload = {"devices": [{"id": "usb:fixture", "online": True}]}
                elif self.path.endswith("/status"):
                    payload = {"online": True, "capabilities": capabilities,
                               "geometry": {"width": 1, "height": 1, "version": "frame-1"}}
                elif self.path.endswith("/screenshot"):
                    payload, kind = PNG, "image/png"
                elif self.path.endswith("/control/acquire"):
                    payload = {"sessionToken": "a" * 64, "expiresAt": "2099-01-01T00:00:00Z"}
                elif self.path.endswith("/control/release"):
                    status = 204
                elif "/input/" in self.path:
                    if self.headers.get("X-Control-Session") != "a" * 64:
                        status, payload = 409, {"error": {"code": "CONTROL_LOCKED", "message": "lease required"}}
                    elif body and json.loads(body).get("geometryVersion") == "stale":
                        status, payload = 409, {"error": {"code": "GEOMETRY_CHANGED", "message": "refresh geometry"}}
                    else:
                        payload = {"status": "dispatched"}
                elif self.command == "PUT":
                    status = 204
                else:
                    payload = {"text": "手机剪贴板"}
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                if status == 204:
                    data = b""
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = respond

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.params = StdioServerParameters(command=sys.executable, args=["-m", "iphonemirror_mcp"], env={
            "IPHONEMIRROR_API_KEY": "fixture-key",
            "IPHONEMIRROR_API_URL": f"http://127.0.0.1:{self.http.server_port}",
        })

    async def asyncTearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)

    async def test_snapshot_and_wait_images_are_not_duplicated_in_structured_content(self):
        async with stdio_client(self.params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                self.assertIsNone(tools["snapshot"].outputSchema)
                self.assertIsNone(tools["wait_for"].outputSchema)
                self.assertNotIn("title", tools["snapshot"].inputSchema)
                self.assertNotIn("title", tools["tap"].inputSchema["properties"]["x"])
                self.assertEqual(tools["tap"].inputSchema["properties"]["x"]["minimum"], 0)
                self.assertEqual(tools["snapshot"].inputSchema["properties"]["max_width"]["default"], 720)
                device = {"device_id": "usb:fixture"}
                before = len(self.requests)
                result = await session.call_tool("snapshot", {**device, "use_ocr": False})
                self.assertFalse(result.isError)
                self.assertEqual([item.type for item in result.content], ["text", "image"])
                self.assertIsNone(result.structuredContent)
                image = result.content[1]
                self.assertEqual(result.model_dump_json().count(image.data), 1)
                data = json.loads(result.content[0].text)
                self.assertEqual(data["status"]["geometry"]["version"], "frame-1")
                self.assertEqual([request[1].split("/")[-1] for request in self.requests[before:]],
                                 ["status", "screenshot", "status"])

                text_only = await session.call_tool("snapshot", {**device, "use_ocr": False,
                                                                  "include_image": False, "compact": False})
                self.assertFalse(text_only.isError)
                self.assertEqual([item.type for item in text_only.content], ["text"])
                self.assertIsNone(text_only.structuredContent)
                self.assertIn("formula", json.loads(text_only.content[0].text)["imageTransform"])

                matched = await session.call_tool("wait_for", {**device, "condition": "online",
                                                               "return_snapshot": True, "max_width": 0})
                self.assertFalse(matched.isError)
                self.assertIsNone(matched.structuredContent)
                self.assertEqual([item.type for item in matched.content], ["text", "image"])
                data = json.loads(matched.content[0].text)
                self.assertTrue(data["matched"])
                self.assertNotEqual(data["snapshotId"], json.loads(text_only.content[0].text)["snapshotId"])
                self.assertEqual(matched.model_dump_json().count(matched.content[1].data), 1)

                unchanged = await session.call_tool("wait_for", {**device, "condition": "screen_changed",
                                                                 "return_snapshot": True, "timeout": 0})
                self.assertFalse(unchanged.isError)
                self.assertEqual([item.type for item in unchanged.content], ["text"])
                data = json.loads(unchanged.content[0].text)
                self.assertFalse(data["matched"])
                self.assertNotIn("snapshotId", data)

                before = len(self.requests)
                for args in ({**device, "max_width": -1}, {**device, "region": [0, 0, 1]}):
                    invalid = await session.call_tool("snapshot", args)
                    self.assertTrue(invalid.isError)
                invalid_wait = await session.call_tool("get_setup_status", {"job_id": "unknown", "timeout": 31})
                self.assertTrue(invalid_wait.isError)
                self.assertEqual(len(self.requests), before)

    async def test_handshake_tools_images_input_and_errors(self):
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
            async with stdio_client(self.params, errlog=errors) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as session:
                    initialized = await session.initialize()
                    self.assertEqual(initialized.serverInfo.name, "iPhoneMirror")
                    tools = {t.name: t for t in (await session.list_tools()).tools}
                    self.assertEqual(len(tools), 28)
                    self.assertIn("prepare_iphone_environment", tools)
                    self.assertTrue(tools["get_setup_status"].annotations.readOnlyHint)
                    self.assertIn("geometry_version", tools["tap"].inputSchema["required"])
                    self.assertNotIn("ctx", tools["tap"].inputSchema["properties"])
                    self.assertTrue(tools["screenshot"].annotations.readOnlyHint)
                    self.assertFalse(tools["tap"].annotations.idempotentHint)
                    self.assertFalse(tools["press_shortcut"].annotations.idempotentHint)
                    self.assertTrue(tools["press_shortcut"].annotations.destructiveHint)
                    self.assertIn("lock_screen", tools["press_shortcut"].inputSchema["properties"]["shortcut"]["enum"])
                    devices = await session.call_tool("list_devices", {})
                    self.assertFalse(devices.isError)
                    self.assertIn("usb:fixture", str(devices.content))
                    device = {"device_id": "usb:fixture"}
                    status = await session.call_tool("get_device_status", device)
                    self.assertIn("frame-1", str(status.content))
                    shot = await session.call_tool("screenshot", device)
                    self.assertFalse(shot.isError)
                    self.assertEqual(shot.content[0].type, "image")
                    self.assertEqual(base64.b64decode(shot.content[0].data), PNG)
                    args = {**device, "x": 0, "y": 0, "geometry_version": "frame-1"}
                    before = len(self.requests)
                    no_lease = await session.call_tool("tap", args)
                    self.assertTrue(no_lease.isError)
                    self.assertEqual(len(self.requests), before)
                    no_shortcut_lease = await session.call_tool("press_shortcut", {**device, "shortcut": "home"})
                    self.assertTrue(no_shortcut_lease.isError)
                    self.assertEqual(self.requests[-1][1].split("/")[-1], "status")
                    lease = await session.call_tool("acquire_control", device)
                    self.assertFalse(lease.isError)
                    self.assertNotIn("a" * 64, str(lease))
                    before = len(self.requests)
                    shortcut = await session.call_tool("press_shortcut", {**device, "shortcut": "app_switcher"})
                    self.assertFalse(shortcut.isError)
                    self.assertEqual(len(self.requests), before + 2)
                    self.assertTrue(self.requests[-1][1].endswith("/input/shortcut"))
                    self.assertEqual(self.requests[-1][3], {"shortcut": "app_switcher"})
                    before = len(self.requests)
                    invalid = await session.call_tool("press_shortcut", {**device, "shortcut": "CTRL+H"})
                    self.assertTrue(invalid.isError)
                    self.assertEqual(len(self.requests), before)
                    self.capabilities["shortcuts"] = []
                    unsupported = await session.call_tool("press_shortcut", {**device, "shortcut": "home"})
                    self.assertTrue(unsupported.isError)
                    self.assertIn("CAPABILITY_NOT_SUPPORTED", str(unsupported.content))
                    self.assertTrue(self.requests[-1][1].endswith("/status"))
                    self.capabilities.clear()
                    legacy = await session.call_tool("press_shortcut", {**device, "shortcut": "home"})
                    self.assertTrue(legacy.isError)
                    self.assertIn("RUNTIME_UPGRADE_REQUIRED", str(legacy.content))
                    self.assertTrue(self.requests[-1][1].endswith("/status"))
                    tap = await session.call_tool("tap", args)
                    self.assertFalse(tap.isError)
                    self.assertEqual(self.requests[-1][3]["geometryVersion"], "frame-1")
                    changed = await session.call_tool("tap", {**args, "geometry_version": "stale"})
                    self.assertTrue(changed.isError)
                    self.assertIn("GEOMETRY_CHANGED", str(changed.content))
                    before = len(self.requests)
                    for bad in [{**args, "x": -1}, {**args, "geometry_version": ""}, device]:
                        result = await session.call_tool("tap", bad)
                        self.assertTrue(result.isError)
                    too_long = await session.call_tool("swipe", {**device, "x1": 0, "y1": 0,
                        "x2": 1, "y2": 1, "duration": 11, "geometry_version": "frame-1"})
                    self.assertTrue(too_long.isError)
                    self.assertEqual(len(self.requests), before)
                    pasted = await session.call_tool("type_text", {**device, "text": "你好 🌍"})
                    self.assertFalse(pasted.isError)
                    self.assertEqual(self.requests[-1][3]["text"], "你好 🌍")
                    clip = await session.call_tool("read_clipboard", device)
                    self.assertIn("手机剪贴板", str(clip.content))
                    written = await session.call_tool("write_clipboard", {**device, "text": ""})
                    self.assertFalse(written.isError)
                    released = await session.call_tool("release_control", device)
                    self.assertFalse(released.isError)
            errors.seek(0)
            logs = errors.read()
            self.assertNotIn("fixture-key", logs)
            self.assertNotIn("a" * 64, logs)
