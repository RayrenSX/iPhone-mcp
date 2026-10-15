"""Compact observations must preserve native geometry, freshness and one-frame wait results."""
import base64
import copy
import io
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from iphonemirror_mcp.server import click_element, observation, snapshot, wait_for
from iphonemirror_mcp.vision import Frame, render


def frame(width=120, height=240, color="white", **status):
    output = io.BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    return Frame(output.getvalue(), {"online": True, "capturing": True,
        "geometry": {"width": width, "height": height, "version": "v1"},
        "control": {"available": True}, "capabilities": {"shortcuts": ["home"]},
        **status}, width, height)


def text_observation():
    elements = []
    for identifier, text, bounds in [
        (0, "Outside", [0, 0, 10, 10]),
        (7, "Inside", [20.123456, 40.123456, 90.987654, 120.987654]),
        (12, "Touching edge", [100, 40, 110, 60]),
        (19, "Partial", [10, 130, 30, 160]),
    ]:
        elements.append({"id": identifier, "text": text, "source": "ocr", "bounds": bounds,
                         "center": [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]})
    return {"language": "en-US", "text": "\n".join(e["text"] for e in elements),
            "textAngle": None, "elements": elements, "semanticTreeAvailable": False}


def metadata(contents):
    return json.loads(contents[0].text)


class ObservationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.api = SimpleNamespace(observations={}, request=AsyncMock(), input=AsyncMock())
        self.api.path = lambda device, suffix: suffix
        self.ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=self.api))
        self.frame = frame()
        self.ocr = text_observation()
        self.capture = AsyncMock(return_value=self.frame)
        self.recognize = AsyncMock(return_value=self.ocr)
        self.patches = [patch("iphonemirror_mcp.server.capture", self.capture),
                        patch("iphonemirror_mcp.server.recognize", self.recognize)]
        for mock_patch in self.patches:
            mock_patch.start()
            self.addCleanup(mock_patch.stop)

    async def test_crop_filters_text_without_renumbering_or_rounding_internal_coordinates(self):
        original = copy.deepcopy(self.ocr)
        result = await snapshot("phone", self.ctx, region=[20, 40, 100, 200], max_width=40)
        data = metadata(result)
        self.assertEqual([e["id"] for e in data["ocr"]["elements"]], [7, 19])
        self.assertEqual(data["ocr"]["elements"][0]["bounds"], [20.1, 40.1, 91.0, 121.0])
        self.assertNotIn("text", data["ocr"])
        self.assertNotIn("center", data["ocr"]["elements"][0])
        self.assertNotIn("source", data["ocr"]["elements"][0])
        self.assertNotIn("formula", data["imageTransform"])
        self.assertNotIn("note", data)
        self.assertEqual(self.ocr, original)
        self.assertEqual(self.api.observations["phone"]["ocr"], original)
        self.assertEqual(data["status"], self.frame.status)
        self.assertEqual(data["imageTransform"]["offsetX"] + 10 * data["imageTransform"]["scaleX"], 40)
        with Image.open(io.BytesIO(base64.b64decode(result[1].data))) as image:
            self.assertEqual(image.size, (40, 80))
        self.api.request.assert_not_awaited()  # No redundant status calls around capture().

        with self.assertRaisesRegex(ValueError, "snapshot region"):
            await click_element("phone", data["snapshotId"], 0, self.ctx)
        self.api.input.assert_not_awaited()
        await click_element("phone", data["snapshotId"], 7, self.ctx)
        x, y = original["elements"][1]["center"]
        self.api.input.assert_awaited_once_with("phone", "tap", x=x, y=y, geometryVersion="v1")

    async def test_full_view_restores_fields_and_crop_fulltext_contains_only_visible_lines(self):
        full = metadata(await snapshot("phone", self.ctx, compact=False, max_width=0))
        self.assertEqual(full["ocr"], self.ocr)
        self.assertIn("formula", full["imageTransform"])
        self.assertIn("note", full)
        cropped = metadata(await snapshot("phone", self.ctx, compact=False, region=[20, 40, 100, 200]))
        self.assertEqual(cropped["ocr"]["text"], "Inside\nPartial")
        self.assertEqual(cropped["ocr"]["elements"][0], self.ocr["elements"][1])
        empty = metadata(await snapshot("phone", self.ctx, compact=False, region=[110, 200, 120, 240]))
        self.assertEqual(empty["ocr"]["text"], "")
        self.assertEqual(empty["ocr"]["elements"], [])

    async def test_text_only_skips_image_encoding_but_still_replaces_snapshot(self):
        previous = metadata(await snapshot("phone", self.ctx))
        with patch("iphonemirror_mcp.server.render") as renderer:
            result = await snapshot("phone", self.ctx, include_image=False)
        renderer.assert_not_called()
        self.assertEqual([item.type for item in result], ["text"])
        self.assertEqual(metadata(result)["ocr"]["elements"][1]["id"], 7)
        with self.assertRaisesRegex(RuntimeError, "STALE_SNAPSHOT"):
            observation(self.api, "phone", previous["snapshotId"])

    async def test_invalid_region_fails_before_ocr_and_keeps_previous_observation(self):
        previous = metadata(await snapshot("phone", self.ctx))
        self.recognize.reset_mock()
        for region in ([0, 0, 121, 240], [-1, 0, 10, 10], [20, 20, 10, 10]):
            with self.assertRaises(ValueError):
                await snapshot("phone", self.ctx, region=region)
        self.recognize.assert_not_awaited()
        observation(self.api, "phone", previous["snapshotId"])

    async def test_default_width_and_native_override(self):
        self.capture.return_value = frame(1082, 2340)
        for options, expected in (({}, (720, 1557)), ({"max_width": 0}, (1082, 2340))):
            result = await snapshot("phone", self.ctx, use_ocr=False, **options)
            with Image.open(io.BytesIO(base64.b64decode(result[1].data))) as image:
                self.assertEqual(image.size, expected)
            data = metadata(result)
            self.assertEqual(data["status"]["geometry"]["width"], 1082)
            transform = data["imageTransform"]
            self.assertAlmostEqual(transform["imageHeight"] * transform["scaleY"], 2340)
        self.recognize.assert_not_awaited()

    async def test_rotated_frame_and_small_images_preserve_native_transform(self):
        for source, expected in ((frame(2340, 1082), (720, 333)), (frame(), (120, 240))):
            png, transform = render(source, region=None, max_width=720, grid=0, elements=[])
            with Image.open(io.BytesIO(png)) as image:
                self.assertEqual(image.size, expected)
            self.assertAlmostEqual(expected[0] * transform["scaleX"], source.width)
            self.assertAlmostEqual(expected[1] * transform["scaleY"], source.height)

    async def test_text_wait_returns_same_frame_and_ocr_with_fresh_snapshot_id(self):
        result = await wait_for("phone", "text_exists", self.ctx, text="inside", return_snapshot=True,
                                region=[20, 40, 100, 200], max_width=40)
        data = metadata(result)
        self.assertTrue(data["matched"])
        self.assertEqual(data["polls"], 1)
        self.assertEqual(data["condition"], "text_exists")
        self.assertEqual([e["id"] for e in data["ocr"]["elements"]], [7, 19])
        self.capture.assert_awaited_once()
        self.recognize.assert_awaited_once()
        self.assertEqual(observation(self.api, "phone", data["snapshotId"])["png"], self.frame.png)

    async def test_text_absent_wait_keeps_legacy_dict_result_by_default(self):
        result = await wait_for("phone", "text_absent", self.ctx, text="missing")
        self.assertEqual(result, {"matched": True, "condition": "text_absent", "polls": 1})
        self.assertEqual(self.api.observations, {})

    async def test_timeout_returns_no_image_or_new_observation(self):
        result = await wait_for("phone", "text_exists", self.ctx, text="missing", timeout=0, return_snapshot=True)
        self.assertEqual(result, {"matched": False, "condition": "text_exists", "polls": 1})
        self.assertEqual(self.api.observations, {})
        self.capture.assert_awaited_once()

    async def test_screen_change_reuses_final_frame_without_extra_ocr(self):
        last = frame(color="black")
        self.capture.side_effect = [self.frame, last]
        with patch("iphonemirror_mcp.server.asyncio.sleep", AsyncMock()):
            result = await wait_for("phone", "screen_changed", self.ctx, return_snapshot=True)
        data = metadata(result)
        self.assertTrue(data["matched"])
        self.assertEqual(data["polls"], 2)
        self.assertEqual(self.capture.await_count, 2)
        self.recognize.assert_not_awaited()
        self.assertEqual(observation(self.api, "phone", data["snapshotId"])["png"], last.png)

    async def test_status_wait_without_snapshot_does_not_capture(self):
        self.api.request.return_value = self.frame.status
        result = await wait_for("phone", "control_available", self.ctx)
        self.assertTrue(result["matched"])
        self.capture.assert_not_awaited()
        self.recognize.assert_not_awaited()

    async def test_status_wait_with_snapshot_captures_and_rechecks_fresh_status(self):
        self.api.request.return_value = self.frame.status
        result = await wait_for("phone", "control_available", self.ctx, return_snapshot=True)
        self.assertTrue(metadata(result)["matched"])
        self.assertEqual(metadata(result)["status"], self.frame.status)
        self.capture.assert_awaited_once()
        self.recognize.assert_not_awaited()

    async def test_status_race_cannot_return_a_stale_match(self):
        self.api.request.return_value = self.frame.status
        self.capture.return_value = frame(control={"available": False})
        result = await wait_for("phone", "control_available", self.ctx, timeout=0, return_snapshot=True)
        self.assertFalse(result["matched"])
        self.assertEqual(self.api.observations, {})

    async def test_wait_errors_propagate_without_retry(self):
        self.capture.side_effect = RuntimeError("API_TIMEOUT")
        with self.assertRaisesRegex(RuntimeError, "API_TIMEOUT"):
            await wait_for("phone", "text_exists", self.ctx, text="inside", return_snapshot=True)
        self.capture.assert_awaited_once()
        self.assertEqual(self.api.observations, {})

    async def test_missing_wait_text_is_rejected_before_reading(self):
        with self.assertRaisesRegex(ValueError, "text is required"):
            await wait_for("phone", "text_exists", self.ctx)
        self.capture.assert_not_awaited()

    async def test_click_rejects_snapshot_replaced_during_ocr_before_dispatch(self):
        data = metadata(await snapshot("phone", self.ctx))

        async def replace_snapshot(*args):
            self.api.observations["phone"] = dict(self.api.observations["phone"], id="newer-snapshot")
            return self.ocr

        self.recognize.side_effect = replace_snapshot
        with self.assertRaisesRegex(RuntimeError, "STALE_SNAPSHOT"):
            await click_element("phone", data["snapshotId"], 7, self.ctx)
        self.api.input.assert_not_awaited()

    async def test_click_rejects_snapshot_expired_during_ocr_before_dispatch(self):
        data = metadata(await snapshot("phone", self.ctx))

        async def expire_snapshot(*args):
            self.api.observations["phone"]["created"] = time.monotonic() - 31
            return self.ocr

        self.recognize.side_effect = expire_snapshot
        with self.assertRaisesRegex(RuntimeError, "STALE_SNAPSHOT"):
            await click_element("phone", data["snapshotId"], 7, self.ctx)
        self.api.input.assert_not_awaited()

    async def test_wait_rejects_invalid_crop_before_ocr_even_without_match(self):
        with self.assertRaisesRegex(ValueError, "region"):
            await wait_for("phone", "text_exists", self.ctx, text="missing", timeout=0,
                           return_snapshot=True, region=[0, 0, 121, 240])
        self.recognize.assert_not_awaited()
        self.assertEqual(self.api.observations, {})
