"""Still screenshots must reject stale sessions and never retry or expose errors."""
import asyncio
import base64
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

spec = importlib.util.spec_from_file_location("ondemand_screenshot",
    Path(__file__).parents[1] / "runtime-patches/ondemand_screenshot.py")
module = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"pymobiledevice3.dtx_service_provider": SimpleNamespace(DtxServiceProvider=object)}):
    spec.loader.exec_module(module)


class OnDemandScreenshotTests(unittest.IsolatedAsyncioTestCase):
    async def capture(self, *, data=b"\x89PNG\r\n\x1a\nimage", error=None, current=None):
        channel = SimpleNamespace(invoke=AsyncMock(return_value=data, side_effect=error))
        hub = SimpleNamespace(dtx=SimpleNamespace(open_channel=AsyncMock(return_value=channel)))
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=hub)
        context.__aexit__ = AsyncMock(return_value=False)
        emit = AsyncMock()
        with patch.object(module, "ScreenshotHub", return_value=context):
            try:
                await module.screenshot_result(object(), {"requestId": "request"}, 4,
                                                current or (lambda: True), emit)
            except asyncio.CancelledError:
                self.assertEqual(emit.call_args.args[0]["code"], "SCREENSHOT_CANCELLED")
                raise
        return emit.call_args.args[0], channel

    async def test_png_uses_one_request(self):
        result, channel = await self.capture()
        self.assertTrue(result["success"])
        self.assertEqual(base64.b64decode(result["text"]), b"\x89PNG\r\n\x1a\nimage")
        channel.invoke.assert_awaited_once_with("takeScreenshot")

    async def test_non_png_and_device_errors_are_sanitized_without_retry(self):
        for options in ({"data": b"not an image"}, {"error": RuntimeError("private-device-data")}):
            result, channel = await self.capture(**options)
            self.assertFalse(result["success"])
            self.assertEqual(result["code"], "SCREENSHOT_UNAVAILABLE")
            self.assertNotIn("text", result)
            self.assertNotIn("private-device-data", str(result))
            self.assertEqual(channel.invoke.await_count, 1)

    async def test_session_replacement_discards_received_pixels(self):
        checks = iter([True, False])
        result, _ = await self.capture(current=lambda: next(checks))
        self.assertFalse(result["success"])
        self.assertNotIn("text", result)

    async def test_cancellation_is_acknowledged_and_propagated(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.capture(error=asyncio.CancelledError())
