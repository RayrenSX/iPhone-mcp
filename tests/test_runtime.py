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

    async def start(self, devices, prepared=None, device_id=None, *, capture_mode="on_demand", enable_control=True, on_demand_version=1):
        instance = runtime.RuntimeClient()
        instance.app_status = AsyncMock(return_value={"background": True, "apiRunning": True, "mainWindowVisible": False,
                                                    "onDemandCaptureVersion": on_demand_version})
        instance.request = AsyncMock(side_effect=[{"devices": devices}, prepared])
        with patch.object(instance, "executable", return_value=Path("iPhoneMirror.exe")), \
             patch.object(instance, "launch") as launch:
            launch.return_value.poll.return_value = None
            result = await instance.start(device_id, enable_control, capture_mode)
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
                                          {"capturing": False, "screenshotAvailable": True, "controlAvailable": True})
        self.assertTrue(result["devicePrepared"])
        self.assertEqual(instance.request.call_args.args[:2], ("POST", "devices/usb%3Aselected/prepare"))
        self.assertTrue(instance.request.call_args.args[2]["enableControl"])
        self.assertFalse(instance.request.call_args.args[2]["continuousCapture"])
        self.assertEqual(result["capture_mode"], "on_demand")

    async def test_legacy_capture_is_explicit_and_keeps_old_request_format(self):
        result, instance = await self.start([{"id": "a", "online": True}],
            {"capturing": True, "controlAvailable": True}, capture_mode="continuous", on_demand_version=0)
        self.assertTrue(result["devicePrepared"])
        self.assertEqual(instance.request.call_args.args[2], {"enableControl": True})

    async def test_missing_screenshot_is_not_ready_even_with_control(self):
        result, _ = await self.start([{"id": "a", "online": True}],
            {"capturing": False, "controlAvailable": True, "screenshotAvailable": False})
        self.assertFalse(result["devicePrepared"])

    async def test_legacy_capture_is_explicitly_enabled_on_new_runtime(self):
        result, instance = await self.start([{"id": "a", "online": True}],
            {"capturing": True, "controlAvailable": True}, capture_mode="continuous")
        self.assertTrue(result["devicePrepared"])
        self.assertTrue(instance.request.call_args.args[2]["continuousCapture"])
        self.assertEqual(result["capture_mode"], "continuous")

    async def test_invalid_mode_does_not_start_app_or_prepare_device(self):
        instance = runtime.RuntimeClient()
        with patch.object(instance, "executable") as executable:
            with self.assertRaisesRegex(ValueError, "capture_mode"):
                await instance.start(capture_mode="automatic")
            executable.assert_not_called()

    async def test_observation_readiness_does_not_require_control(self):
        result, _ = await self.start([{"id": "a", "online": True}],
            {"capturing": False, "screenshotAvailable": True, "controlAvailable": False}, enable_control=False)
        self.assertTrue(result["devicePrepared"])

    async def test_on_demand_rejects_old_runtime_before_device_preparation(self):
        instance = runtime.RuntimeClient()
        instance.app_status = AsyncMock(return_value={"background": True, "apiRunning": True})
        instance.request = AsyncMock()
        with patch.object(instance, "executable", return_value=Path("iPhoneMirror.exe")), patch.object(instance, "launch") as launch:
            launch.return_value.poll.return_value = None
            with self.assertRaisesRegex(RuntimeError, "RUNTIME_UPGRADE_REQUIRED"):
                await instance.start()
        instance.request.assert_not_called()

    async def test_failed_control_is_not_reported_ready(self):
        result, _ = await self.start([{"id": "a", "online": True}], {"screenshotAvailable": True, "controlAvailable": False})
        self.assertFalse(result["devicePrepared"])

    async def test_old_running_app_is_rejected_before_launch(self):
        instance = runtime.RuntimeClient()
        instance.app_status = AsyncMock(side_effect=RuntimeError("RUNTIME_UPGRADE_REQUIRED"))
        with patch.object(instance, "executable", return_value=Path("iPhoneMirror.exe")), patch.object(instance, "launch") as launch:
            with self.assertRaisesRegex(RuntimeError, "UPGRADE_REQUIRED"):
                await instance.start()
            launch.assert_not_called()
