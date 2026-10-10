import io
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from iphonemirror_mcp.server import click_element, observation, scroll, type_at
from iphonemirror_mcp.vision import Frame, capture, render, scroll_points


def fixture(width=120, height=240):
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


class CoordinateTests(unittest.TestCase):
    def test_crop_resize_transform_maps_back_to_native_pixels(self):
        frame = Frame(fixture(), {}, 120, 240)
        png, transform = render(frame, region=[20, 40, 100, 200], max_width=40, grid=0, elements=[])
        self.assertEqual(Image.open(io.BytesIO(png)).size, (40, 80))
        self.assertEqual(transform["offsetX"] + 10 * transform["scaleX"], 40)
        self.assertEqual(transform["offsetY"] + 10 * transform["scaleY"], 60)
        with self.assertRaises(ValueError):
            render(frame, region=[0, 0, 121, 240], max_width=0, grid=0, elements=[])

    def test_scroll_direction_is_content_direction_and_bounds_are_strict(self):
        self.assertEqual(scroll_points(120, 240, 60, 120, "down", 80), (60, 40))
        self.assertEqual(scroll_points(120, 240, 60, 120, "right", 40), (20, 120))
        with self.assertRaises(ValueError):
            scroll_points(120, 240, 60, 120, "down", 121)

    def test_expired_or_replaced_snapshot_is_rejected(self):
        api = SimpleNamespace(observations={"phone": {"id": "fresh", "created": time.monotonic() - 31}})
        with self.assertRaisesRegex(RuntimeError, "STALE_SNAPSHOT"):
            observation(api, "phone", "fresh")
        api.observations["phone"]["created"] = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "STALE_SNAPSHOT"):
            observation(api, "phone", "previous")


class StateTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture_rejects_geometry_change_and_wrong_size(self):
        for after in [{"width": 120, "height": 240, "version": "new"},
                      {"width": 130, "height": 240, "version": "old"}]:
            api = SimpleNamespace(path=lambda d,s:s, request=AsyncMock(side_effect=[
                {"geometry": {"version": "old"}}, fixture(), {"geometry": after}]))
            with self.assertRaisesRegex(RuntimeError, "GEOMETRY_CHANGED"):
                await capture(api, "phone")

    async def test_click_rechecks_text_location_before_dispatch(self):
        element = {"id": 0, "text": "Button", "center": [40, 50], "bounds": [20, 30, 60, 70]}
        observed = {"id": "snap", "created": time.monotonic(), "geometry": {"version": "v1"},
                    "ocr": {"elements": [element], "language": "en-US"}}
        api = SimpleNamespace(observations={"phone": observed}, input=AsyncMock())
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=api))
        frame = Frame(fixture(), {"geometry": {"version": "v1"}}, 120, 240)
        with patch("iphonemirror_mcp.server.capture", AsyncMock(return_value=frame)), \
             patch("iphonemirror_mcp.server.recognize", AsyncMock(return_value={"elements": []})):
            with self.assertRaisesRegex(RuntimeError, "STALE_ELEMENT"):
                await click_element("phone", "snap", 0, ctx)
            api.input.assert_not_awaited()
        with patch("iphonemirror_mcp.server.capture", AsyncMock(return_value=frame)), \
             patch("iphonemirror_mcp.server.recognize", AsyncMock(return_value={"elements": [element]})):
            await click_element("phone", "snap", 0, ctx)
            api.input.assert_awaited_once_with("phone", "tap", x=40, y=50, geometryVersion="v1")

    async def test_type_at_reports_partial_input_without_retry(self):
        api = SimpleNamespace(input=AsyncMock(side_effect=[{"status": "dispatched"}, RuntimeError("API_TIMEOUT")]))
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=api))
        with self.assertRaisesRegex(RuntimeError, "TYPE_AT_PARTIAL"):
            await type_at("phone", 10, 20, "text", "v1", ctx)
        self.assertEqual(api.input.await_count, 2)
