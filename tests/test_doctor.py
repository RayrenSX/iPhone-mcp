"""Diagnostic readiness must reflect evidence and not expose screen/device data."""
import importlib.util
import json
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("doctor", Path(__file__).parents[1] / "scripts/doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def result(data, *, error=False, image=False):
    content = [SimpleNamespace(type="text", text=json.dumps(data))]
    if image:
        content.append(SimpleNamespace(type="image"))
    return SimpleNamespace(isError=error, content=content)


class DoctorTests(unittest.IsolatedAsyncioTestCase):
    async def diagnose(self, devices, *, screenshot=True, ocr=False, fail=False):
        calls = []

        class Session:
            async def initialize(self):
                if fail:
                    raise RuntimeError("private-api-key")

            async def list_tools(self):
                return SimpleNamespace(tools=[None] * 22)

            async def call_tool(self, name, args):
                calls.append(name)
                if name == "list_devices":
                    return result({"devices": devices})
                if args["use_ocr"]:
                    if args.get("include_image") is not False:
                        raise AssertionError("OCR diagnosis must not resend the image")
                    return result({"ocr": {"language": "en-US", "text": "private-screen-text"}}, error=not ocr)
                return result({"status": {"geometry": {"width": 100, "height": 200},
                                          "control": {"available": True}}},
                              error=not screenshot, image=screenshot)

        @asynccontextmanager
        async def stdio(*args, **kwargs):
            yield None, None

        @asynccontextmanager
        async def session(*args, **kwargs):
            yield Session()

        with patch.object(doctor, "stdio_client", stdio), patch.object(doctor, "ClientSession", session):
            report = await doctor.diagnose()
        self.assertTrue(set(calls) <= {"list_devices", "snapshot"})
        if devices:
            self.assertEqual(calls, ["list_devices", "snapshot"] + (["snapshot"] if screenshot else []))
        self.assertNotIn("private-", json.dumps(report))
        return report

    async def test_no_devices_is_not_ready(self):
        self.assertFalse((await self.diagnose([]))["ready"])

    async def test_capture_failure_is_not_control_ready(self):
        report = await self.diagnose([{"id": "private-id"}], screenshot=False)
        self.assertFalse(report["ready"])
        self.assertFalse(report["controlReady"])

    async def test_missing_ocr_preserves_screenshot_readiness(self):
        report = await self.diagnose([{"id": "private-id"}])
        self.assertTrue(report["ready"])
        self.assertFalse(report["devices"][0]["ocr"])

    async def test_success_redacts_screen_and_id(self):
        report = await self.diagnose([{"id": "private-id"}], ocr=True)
        self.assertTrue(report["ready"])
        self.assertTrue(report["devices"][0]["ocr"])
        self.assertTrue(report["controlReady"])

    async def test_start_failure_redacts_exception(self):
        report = await self.diagnose([], fail=True)
        self.assertFalse(report["ready"])
        self.assertEqual(report["failedStage"], "mcp_start")
