import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from iphonemirror_mcp import runtime


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialization_does_not_read_credentials(self):
        with patch.object(runtime, "configuration", side_effect=RuntimeError("no key")):
            instance = runtime.RuntimeClient()
            await instance.close()
            self.assertIsNone(instance.api)

    async def start(self, devices, prepared=None, device_id=None):
        instance = runtime.RuntimeClient()
        instance.app_status = AsyncMock(return_value={"background": True, "apiRunning": True, "mainWindowVisible": False})
        instance.request = AsyncMock(side_effect=[{"devices": devices}, prepared])
        with patch.object(instance, "executable", return_value=Path("iPhoneMirror.exe")), \
             patch.object(instance, "launch") as launch:
            launch.return_value.poll.return_value = None
            result = await instance.start(device_id)
        self.assertEqual(launch.call_args.args[0], Path("iPhoneMirror.exe"))
        if runtime.os.environ.get("SYSTEMROOT"):
            self.assertIn("WINDIR", launch.call_args.args[1])
        return result, instance

    async def test_multiple_devices_require_selection_without_preparing(self):
        result, instance = await self.start([{"id": "a", "online": True}, {"id": "b", "online": True}])
        self.assertFalse(result["devicePrepared"])
        self.assertEqual(instance.request.await_count, 1)

    async def test_prepare_uses_exact_online_device_and_reports_readiness(self):
        result, instance = await self.start([{"id": "usb:selected", "online": True}],
                                          {"capturing": True, "controlAvailable": True})
        self.assertTrue(result["devicePrepared"])
        self.assertEqual(instance.request.call_args.args[:2], ("POST", "devices/usb%3Aselected/prepare"))
        self.assertTrue(instance.request.call_args.args[2]["enableControl"])

    async def test_failed_control_is_not_reported_ready(self):
        result, _ = await self.start([{"id": "a", "online": True}], {"capturing": True, "controlAvailable": False})
        self.assertFalse(result["devicePrepared"])

    async def test_old_running_app_is_rejected_before_launch(self):
        instance = runtime.RuntimeClient()
        instance.app_status = AsyncMock(side_effect=RuntimeError("RUNTIME_UPGRADE_REQUIRED"))
        with patch.object(instance, "executable", return_value=Path("iPhoneMirror.exe")), patch.object(instance, "launch") as launch:
            with self.assertRaisesRegex(RuntimeError, "UPGRADE_REQUIRED"):
                await instance.start()
            launch.assert_not_called()
