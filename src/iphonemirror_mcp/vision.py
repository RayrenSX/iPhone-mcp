"""Native screenshot inspection. OCR boxes are observations, not accessibility nodes."""

import io
import os
from dataclasses import dataclass

from PIL import Image, ImageDraw


@dataclass
class Frame:
    png: bytes
    status: dict
    width: int
    height: int


async def capture(api, device_id: str) -> Frame:
    # Guard against a geometry change while the screenshot request is in flight.
    before = await api.request("GET", api.path(device_id, "/status"))
    png = await api.request("GET", api.path(device_id, "/screenshot"), binary=True)
    after = await api.request("GET", api.path(device_id, "/status"))
    with Image.open(io.BytesIO(png)) as image:
        width, height = image.size
    geometry = after["geometry"]
    if (before["geometry"]["version"] != geometry["version"]
            or (width, height) != (geometry["width"], geometry["height"])):
        raise RuntimeError("GEOMETRY_CHANGED: capture again before operating")
    return Frame(png, after, width, height)


async def recognize(png: bytes, language: str | None = None) -> dict:
    if os.name != "nt":
        raise RuntimeError("OCR_UNAVAILABLE: Windows OCR is required; snapshot with use_ocr=false still works")
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder, BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    engine = (OcrEngine.try_create_from_language(Language(language)) if language
              else OcrEngine.try_create_from_user_profile_languages())
    if engine is None:
        available = ", ".join(x.language_tag for x in OcrEngine.available_recognizer_languages)
        raise RuntimeError(f"OCR_UNAVAILABLE: install a Windows OCR language pack; available: {available}")
    # Boxes are mapped back to the native capture; OCR is never a semantic UI tree.
    with Image.open(io.BytesIO(png)) as image:
        ratio = min(1.0, OcrEngine.max_image_dimension / max(image.size))
        if ratio < 1:
            image = image.resize((int(image.width * ratio), int(image.height * ratio)))
        output = io.BytesIO()
        image.save(output, format="PNG")
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    bitmap = converted = None
    try:
        writer.write_bytes(output.getvalue())
        await writer.store_async()
        writer.detach_stream()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        converted = SoftwareBitmap.convert(bitmap, BitmapPixelFormat.BGRA8)
        result = await engine.recognize_async(converted)
        angle = result.text_angle
        # Windows OCR bounding boxes refer to the source bitmap pixels.
        elements = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            left = min(w.bounding_rect.x for w in words) / ratio
            top = min(w.bounding_rect.y for w in words) / ratio
            right = max(w.bounding_rect.x + w.bounding_rect.width for w in words) / ratio
            bottom = max(w.bounding_rect.y + w.bounding_rect.height for w in words) / ratio
            elements.append({"id": len(elements), "text": line.text, "source": "ocr",
                             "bounds": [left, top, right, bottom],
                             "center": [(left + right) / 2, (top + bottom) / 2]})
        return {"language": engine.recognizer_language.language_tag,
                "text": result.text, "textAngle": angle, "elements": elements,
                "semanticTreeAvailable": False}
    finally:
        if converted is not None:
            converted.close()
        if bitmap is not None:
            bitmap.close()
        writer.close()
        stream.close()


def image_transform(frame: Frame, region: list[int] | None, max_width: int) -> dict:
    """Validate the native crop and calculate display geometry without encoding an image."""
    width, height = frame.width, frame.height
    left, top, right, bottom = 0, 0, width, height
    if region is not None:
        if len(region) != 4:
            raise ValueError("region needs [left, top, right, bottom] in native capture pixels")
        left, top, right, bottom = region
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("region must lie inside the native capture frame")
    image_width, image_height = right - left, bottom - top
    if max_width and image_width > max_width:
        image_height = max(1, round(image_height * max_width / image_width))
        image_width = max_width
    return {"imageWidth": image_width, "imageHeight": image_height,
            "nativeWidth": width, "nativeHeight": height,
            "offsetX": left, "offsetY": top,
            "scaleX": (right - left) / image_width,
            "scaleY": (bottom - top) / image_height,
            "formula": "nativeX=offsetX+imageX*scaleX; nativeY=offsetY+imageY*scaleY"}


def visible_elements(ocr: dict, region: list[int] | None) -> list[dict]:
    """Keep original IDs/native bounds, including lines that partially overlap the crop."""
    if region is None:
        return list(ocr["elements"])
    left, top, right, bottom = region
    return [e for e in ocr["elements"] if e["bounds"][0] < right
            and e["bounds"][2] > left and e["bounds"][1] < bottom
            and e["bounds"][3] > top]


def ocr_view(ocr: dict, elements: list[dict], *, compact: bool, cropped: bool) -> dict:
    """Project OCR for the client while retaining original precision inside the server."""
    if not compact:
        result = dict(ocr, elements=elements)
        if cropped:
            result["text"] = "\n".join(e["text"] for e in elements)
        return result
    result = {k: ocr[k] for k in ("language", "semanticTreeAvailable") if k in ocr}
    if ocr.get("textAngle") is not None:
        result["textAngle"] = ocr["textAngle"]
    result["elements"] = [{"id": e["id"], "text": e["text"],
                           "bounds": [round(v, 1) for v in e["bounds"]]} for e in elements]
    return result


def render(frame: Frame, *, region: list[int] | None, max_width: int,
           grid: int, elements: list[dict]) -> tuple[bytes, dict]:
    transform = image_transform(frame, region, max_width)
    left, top = transform["offsetX"], transform["offsetY"]
    right, bottom = region[2:] if region else (frame.width, frame.height)
    with Image.open(io.BytesIO(frame.png)) as raw:
        image = raw.convert("RGB")
    draw = ImageDraw.Draw(image)
    for element in elements:
        bounds = element["bounds"]
        draw.rectangle(bounds, outline="#ffad33", width=3)
        draw.text((bounds[0], max(0, bounds[1] - 18)), str(element["id"]), fill="#ffad33")
    if grid:
        for i in range(1, grid):
            x, y = left + (right - left) * i / grid, top + (bottom - top) * i / grid
            draw.line((x, top, x, bottom), fill="#00c8ff", width=2)
            draw.line((left, y, right, y), fill="#00c8ff", width=2)
    image = image.crop((left, top, right, bottom))
    if image.size != (transform["imageWidth"], transform["imageHeight"]):
        image = image.resize((transform["imageWidth"], transform["imageHeight"]), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue(), transform


def scroll_points(width: int, height: int, x: float, y: float,
                  direction: str, distance: float) -> tuple[float, float]:
    # Direction describes content movement, matching a scroll wheel, not finger movement.
    dx, dy = {"down": (0, -distance), "up": (0, distance),
              "right": (-distance, 0), "left": (distance, 0)}[direction]
    end = x + dx, y + dy
    if not (0 <= x < width and 0 <= y < height and 0 <= end[0] < width and 0 <= end[1] < height):
        raise ValueError("Scroll endpoints exceed the capture frame; reduce distance or move the start point")
    return end
