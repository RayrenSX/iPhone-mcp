"""Official MCP SDK stdio server; stdout is reserved for the protocol."""

import argparse
import asyncio
import io
import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from mcp.server.fastmcp import Context, FastMCP, Image
from mcp.types import ImageContent, TextContent, ToolAnnotations
from PIL import Image as PillowImage, ImageChops, ImageStat
from pydantic import BaseModel, ConfigDict, Field

from .client import AutomationClient
from .runtime import RuntimeClient
from .schema import LeanFastMCP
from .vision import Frame, capture, image_transform, ocr_view, recognize, render, scroll_points, visible_elements

Coordinate = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Duration = Annotated[float, Field(ge=0.05, le=10, allow_inf_nan=False)]
LeaseDuration = Annotated[int, Field(ge=5, le=300)]
GeometryVersion = Annotated[str, Field(min_length=1)]
ImageWidth = Annotated[int, Field(ge=0, le=4096)]
Region = Annotated[list[int], Field(min_length=4, max_length=4)]
Shortcut = Literal["home", "app_switcher", "control_center", "notification_center",
                   "dock", "siri", "volume_up", "volume_down", "lock_screen"]


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: Coordinate
    y: Coordinate


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[RuntimeClient]:
    client = RuntimeClient()
    try:
        yield client
    finally:
        await client.close()


mcp = LeanFastMCP("iPhoneMirror", lifespan=lifespan, log_level="WARNING", instructions="""
start_iphonemirror starts the hidden app/API and prepares direct control plus observation.
Choose capture_mode=on_demand for individual screenshots without continuous video, or
capture_mode=continuous for a live video frame cache. on_demand is the default.
Follow the user's mode preference. Otherwise choose on_demand for occasional
before/after observations, continuous for frequent observations or animation tracking.
On-demand avoids video streaming work but adds a device request per screenshot;
continuous keeps frames available but consumes resources between observations.
Explain the tradeoff if the user asks for help choosing. Release leases before
switching modes, close any preview before on_demand, then verify a fresh snapshot.
enable_control defaults to true.
Use its device_id; list_devices only to select a device. Open a preview only when
requested, using open_independent_window after releasing control.
snapshot includes fresh status, capabilities and geometry; reuse them instead of
another status query for the same observation. Installation acceptance still needs
its explicit checks. Respect capabilities. Coordinates are native screenshot pixels
(top-left origin), not iOS points; use imageTransform for cropped/resized images.
Provide current geometry.version for touch. On GEOMETRY_CHANGED refresh observation
and release/reacquire control; never guess coordinates after rotation.
Acquire control before input, renew before expiresAt and release when done.
Dispatched means transport only: act once, inspect a fresh image to verify effects.
Never retry input automatically after timeout/disconnection or unknown effects.
Text uses the phone clipboard; resolve any iOS Allow Paste prompt before more keys
or clipboard changes. BLE may support keys only.
OCR IDs describe text, not accessibility/button semantics; click_element requires
a current snapshot ID (30s, replaced by the next snapshot). Crops return overlapping
lines with original IDs/native bounds; partial lines can include text outside the crop.
Default snapshots: compact OCR and 720px width. compact=false restores full fields;
max_width=0 keeps native detail. include_image=false is for text extraction, not input
verification. Prefer wait_for(return_snapshot=true) to polling then another snapshot;
a match does not guarantee animation has stopped. Scroll down moves the finger up.
prepare_iphone_environment performs headless runtime/driver setup. Wait for progress
using get_setup_status(job_id, after_revision=revision, timeout=20); keep MCP connected
until terminal. Present actionRequired: connect_usb/replug_usb need a USB data cable,
unlocked phone and Trust if offered; confirm_uac needs human Windows elevation;
restart_windows needs saved work and a restart; select_device needs explicit selection.
Do not claim unseen prompts. Never uninstall healthy drivers or repeat uncertain
transactions. DRIVER_INSTALL_FAILED/DRIVER_OUTCOME_UNKNOWN require diagnosis, not a
retry loop. After setup verify startup, snapshot and controlReady; installation alone
does not prove phone readiness. Phone trust/unlock/UAC remain human actions.
""")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                        idempotentHint=False, openWorldHint=False)
MANAGE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def client(ctx: Context) -> RuntimeClient:
    return ctx.request_context.lifespan_context


@mcp.tool(annotations=MANAGE)
async def start_iphonemirror(ctx: Context, device_id: str | None = None, enable_control: bool = True,
                           capture_mode: Literal["on_demand", "continuous"] = "on_demand") -> dict:
    """Prepare direct control and choose how the phone screen is observed.

    Defaults to the sole online device; multiple devices require an explicit device_id.
    Does not send phone input or open a preview. Missing trust, driver, pairing or
    Developer Mode requires human action. A missing runtime starts a setup job;
    poll get_setup_status, then call this tool again. Drivers use prepare_iphone_environment.
    capture_mode=on_demand requests individual screenshots over the USB control
    transport and keeps capturing=false: avoids ongoing video work, but each shot
    adds a device round trip. Requires the patched runtime, USB and Developer Mode/DDI.
    capture_mode=continuous maintains a video frame cache: useful for frequent
    observations or animation tracking, but consumes resources between observations.
    Both modes keep control enabled and windows hidden by default. Continuous
    observation alone does not require input setup; input may need Developer Mode/DDI.
    Follow the user's choice; otherwise prefer on_demand for occasional screenshots.
    Release leases before switching and close any preview before on_demand.
    """
    return await client(ctx).start(device_id, enable_control, capture_mode)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                    idempotentHint=False, openWorldHint=True))
async def prepare_iphone_environment(ctx: Context, install_drivers: bool = True,
                                     device_id: str | None = None, proxy: str | None = None) -> dict:
    """Install missing runtime and selected-device drivers without a driver-manager GUI.

    Returns immediately with jobId; poll get_setup_status. device_id is a setup:
    ID returned in setup.devices, not the app device ID. Multiple phones require
    selection. Existing healthy drivers are preserved by native inspection.
    Direct downloads first; optional proxy is a fallback, with no system change.
    UAC remains visible. Report actionRequired to the user and verify capture after
    setup. Do not repeat failed/unknown installations without fresh diagnosis.
    """
    api = client(ctx)
    if install_drivers and api.api is not None and api.api.sessions:
        raise RuntimeError("CONTROL_LOCKED: release control before driver setup")
    return api.setup.begin(install_drivers, device_id, proxy)


@mcp.tool(annotations=READ)
async def get_setup_status(job_id: str, ctx: Context,
                           after_revision: Annotated[int, Field(ge=0)] | None = None,
                           timeout: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)] = 0) -> dict:
    """Read setup progress; pass after_revision and timeout to wait for a change (max 30s).

    Returns immediately for terminal/action_required states. Setup completion is not phone readiness.
    """
    return await asyncio.to_thread(client(ctx).setup.status, job_id, after_revision, timeout)


@mcp.tool(annotations=READ)
async def get_app_status(ctx: Context) -> dict:
    """Check management support, API, background mode and main/independent window visibility."""
    return await client(ctx).app_status()


@mcp.tool(annotations=MANAGE)
async def open_independent_window(device_id: str, ctx: Context) -> dict:
    """Open/activate this device's standalone preview while the main app stays hidden.

    Release control leases before changing window/capture setup. No device input is sent.
    """
    return await client(ctx).request("POST", client(ctx).path(device_id, "/window/open"))


@mcp.tool(annotations=READ)
async def list_devices(ctx: Context) -> dict:
    """List existing sources with opaque IDs, connection, capabilities and geometry."""
    return await client(ctx).request("GET", "devices")


@mcp.tool(annotations=READ)
async def get_device_status(device_id: str, ctx: Context) -> dict:
    """Read online/capture/control state and geometry.version before operating."""
    api = client(ctx)
    return await api.request("GET", api.path(device_id, "/status"))


@mcp.tool(annotations=READ)
async def screenshot(device_id: str, ctx: Context) -> Image:
    """Return the native capture PNG as an MCP image, without resizing. No lease needed."""
    api = client(ctx)
    data = await api.request("GET", api.path(device_id, "/screenshot"), binary=True)
    return Image(data=data, format="png")


@mcp.tool(annotations=WRITE)
async def acquire_control(device_id: str, ctx: Context, duration_seconds: LeaseDuration = 30) -> dict:
    """Acquire/renew exclusive control for 5..300 seconds. Returns expiry, never the token.

    After expiry/revocation, release the old session before acquiring a new one.
    """
    return await client(ctx).acquire(device_id, duration_seconds)


@mcp.tool(annotations=WRITE)
async def release_control(device_id: str, ctx: Context) -> dict:
    """Release this server's lease and cancel its held touch or in-flight gesture."""
    return await client(ctx).release(device_id)


@mcp.tool(annotations=WRITE)
async def tap(device_id: str, x: Coordinate, y: Coordinate, geometry_version: GeometryVersion, ctx: Context) -> dict:
    """Tap a screenshot pixel. Requires acquired control and the current geometry version."""
    return await client(ctx).input(device_id, "tap", x=x, y=y, geometryVersion=geometry_version)


@mcp.tool(annotations=WRITE)
async def long_press(device_id: str, x: Coordinate, y: Coordinate, duration: Duration,
                     geometry_version: GeometryVersion, ctx: Context) -> dict:
    """Hold a screenshot pixel for duration seconds (0.05..10). Requires control."""
    return await client(ctx).input(device_id, "long-press", x=x, y=y, duration=duration,
                                  geometryVersion=geometry_version)


@mcp.tool(annotations=WRITE)
async def swipe(device_id: str, x1: Coordinate, y1: Coordinate, x2: Coordinate, y2: Coordinate,
                duration: Duration, geometry_version: GeometryVersion, ctx: Context) -> dict:
    """Swipe between distinct screenshot pixels over duration seconds. Requires control."""
    return await client(ctx).input(device_id, "swipe", x1=x1, y1=y1, x2=x2, y2=y2,
                                  duration=duration, geometryVersion=geometry_version)


@mcp.tool(annotations=WRITE)
async def touch_path(device_id: str, points: Annotated[list[Point], Field(min_length=2, max_length=256)],
                     duration: Duration, geometry_version: GeometryVersion, ctx: Context) -> dict:
    """Trace 2..256 screenshot pixel points evenly over duration seconds. Requires control."""
    return await client(ctx).input(device_id, "touch-path", points=[p.model_dump() for p in points],
                                  duration=duration, geometryVersion=geometry_version)


@mcp.tool(annotations=WRITE)
async def touch_down(device_id: str, x: Coordinate, y: Coordinate,
                     geometry_version: GeometryVersion, ctx: Context) -> dict:
    """Hold a touch and return touchId; call touch_up to end it. Expires after at most 10s."""
    return await client(ctx).input(device_id, "touch-down", x=x, y=y, geometryVersion=geometry_version)


@mcp.tool(annotations=WRITE)
async def touch_up(device_id: str, touch_id: str, ctx: Context) -> dict:
    """End the held touch using its touchId. release_control also cleans up held touches."""
    return await client(ctx).input(device_id, "touch-up", touchId=touch_id)


@mcp.tool(annotations=WRITE)
async def press_key(device_id: str, key: str, ctx: Context) -> dict:
    """Send a supported key: A-Z, 0-9, ENTER, ESCAPE, TAB, SPACE, BACKSPACE,
    DELETE, INSERT, LEFT/RIGHT/UP/DOWN, HOME, END, PAGEUP/PAGEDOWN,
    SHIFT, CTRL, ALT, F3-F12. HOME means keyboard Home, not the iOS Home button.
    Requires control and keyboard.input. Does not accept arbitrary shortcuts.
    """
    return await client(ctx).input(device_id, "key", key=key)


@mcp.tool(annotations=WRITE)
async def press_shortcut(device_id: str, shortcut: Shortcut, ctx: Context) -> dict:
    """Run an iPhoneMirror phone system action on the explicitly selected device.

    Requires acquired control, keyboard.input and capabilities.shortcuts support.
    home is the iOS Home action; press_key(HOME) is the keyboard navigation key.
    Uses the native device route without changing Windows hotkey settings or focus.
    Observe first, invoke once, verify a fresh snapshot, then release control.
    Locking the phone may stop capture. dispatched does not confirm a UI effect.
    """
    api = client(ctx)
    status = await api.request("GET", api.path(device_id, "/status"))
    shortcuts = status.get("capabilities", {}).get("shortcuts")
    if shortcuts is None:
        raise RuntimeError("RUNTIME_UPGRADE_REQUIRED: install a runtime with the shortcut API; no input was sent")
    if shortcut not in shortcuts:
        raise RuntimeError("CAPABILITY_NOT_SUPPORTED: this connection does not support the requested shortcut; no input was sent")
    return await api.input(device_id, "shortcut", shortcut=shortcut)


@mcp.tool(annotations=WRITE)
async def type_text(device_id: str, text: str, ctx: Context) -> dict:
    """Paste UTF-8 text (max 64 KiB) via the phone clipboard. Requires control,
    keyboard.input and clipboard.write. May show iOS Allow Paste; wait for it
    before further input or clipboard changes. Verify insertion with screenshot.
    """
    return await client(ctx).input(device_id, "text", text=text)


@mcp.tool(annotations=READ)
async def read_clipboard(device_id: str, ctx: Context) -> dict:
    """Read phone clipboard text; requires clipboard.read, no control lease needed."""
    api = client(ctx)
    return await api.request("GET", api.path(device_id, "/clipboard"))


@mcp.tool(annotations=WRITE)
async def write_clipboard(device_id: str, text: str, ctx: Context) -> dict:
    """Replace phone clipboard (max 64 KiB UTF-8) without pasting. Requires control
    and clipboard.write. Do not overwrite it while an Allow Paste prompt is pending.
    """
    api = client(ctx)
    return await api.request("PUT", api.path(device_id, "/clipboard"), {"text": text},
                             device_id=device_id, control=True)


def snapshot_contents(api, device_id: str, frame: Frame, ocr: dict, *,
                      annotate: bool = True, region: list[int] | None = None,
                      max_width: int = 720, grid: int = 0, compact: bool = True,
                      include_image: bool = True, extra: dict | None = None) -> list[TextContent | ImageContent]:
    transform = image_transform(frame, region, max_width)
    elements = visible_elements(ocr, region)
    contents = []
    if include_image:
        image, transform = render(frame, region=region, max_width=max_width, grid=grid,
                                  elements=elements if annotate else [])
        contents.append(Image(data=image, format="png").to_image_content())
    snapshot_id = uuid.uuid4().hex
    if device_id not in api.observations and len(api.observations) >= 16:
        api.observations.pop(next(iter(api.observations)))
    api.observations[device_id] = {"id": snapshot_id, "created": time.monotonic(),
        "geometry": frame.status["geometry"], "ocr": ocr, "png": frame.png,
        "element_ids": {e["id"] for e in elements}}
    if compact:
        transform = {k: v for k, v in transform.items() if k != "formula"}
    metadata = {"snapshotId": snapshot_id, "deviceId": device_id,
                "status": frame.status, "imageTransform": transform,
                "ocr": ocr_view(ocr, elements, compact=compact, cropped=region is not None)}
    if not compact:
        metadata["note"] = "OCR boxes do not prove clickability; inspect the image and verify input effects."
    if extra:
        metadata.update(extra)
    return [TextContent(type="text", text=json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))),
            *contents]


@mcp.tool(annotations=READ, structured_output=False)
async def snapshot(device_id: str, ctx: Context, use_ocr: bool = True,
                   language: str | None = None, annotate: bool = True,
                   region: Region | None = None, max_width: ImageWidth = 720,
                   grid: Annotated[int, Field(ge=0, le=20)] = 0,
                   compact: bool = True, include_image: bool = True) -> list[TextContent | ImageContent]:
    """Observe fresh status/geometry, image and OCR. No separate status query is needed.

    Default: 720px image, compact id/text/bounds OCR. compact=false restores full
    fields; max_width=0 preserves width; include_image=false extracts text only.
    Region=[left,top,right,bottom] filters overlapping full-frame OCR lines, keeping
    original IDs/native coordinates. Boxes do not prove clickability. Observe images
    before/after input. IDs expire after 30s or the next snapshot of this device.
    """
    api = client(ctx)
    frame = await capture(api, device_id)
    image_transform(frame, region, max_width)  # Reject invalid crops before doing OCR.
    ocr = await recognize(frame.png, language) if use_ocr else {"elements": [], "semanticTreeAvailable": False}
    return snapshot_contents(api, device_id, frame, ocr, annotate=annotate, region=region,
                             max_width=max_width, grid=grid, compact=compact, include_image=include_image)


def observation(api: AutomationClient, device_id: str, snapshot_id: str) -> dict:
    observed = api.observations.get(device_id)
    if (observed is None or observed["id"] != snapshot_id
            or time.monotonic() - observed["created"] > 30):
        raise RuntimeError("STALE_SNAPSHOT: take a new snapshot before using an OCR element ID")
    return observed


@mcp.tool(annotations=WRITE)
async def click_element(device_id: str, snapshot_id: str, element_id: int, ctx: Context) -> dict:
    """Tap the native center of a text line from a snapshot less than 30s old.

    Requires control. Text may not be clickable; inspect the image first. Does
    not search by guessed text or reuse IDs after a new snapshot/geometry change.
    """
    api = client(ctx)
    observed = observation(api, device_id, snapshot_id)
    if "element_ids" in observed and element_id not in observed["element_ids"]:
        raise ValueError("Unknown OCR element ID for this snapshot region")
    element = next((e for e in observed["ocr"]["elements"] if e["id"] == element_id), None)
    if element is None:
        raise ValueError("Unknown OCR element ID for this snapshot")
    frame = await capture(api, device_id)
    if frame.status["geometry"]["version"] != observed["geometry"]["version"]:
        raise RuntimeError("GEOMETRY_CHANGED: take a new snapshot and reacquire control")
    x, y = element["center"]
    fresh = await recognize(frame.png, observed["ocr"].get("language"))
    if not any(e["text"] == element["text"]
               and e["bounds"][0] <= x <= e["bounds"][2]
               and e["bounds"][1] <= y <= e["bounds"][3]
               for e in fresh["elements"]):
        raise RuntimeError("STALE_ELEMENT: text moved or disappeared; take a new snapshot")
    # OCR awaits allow another observation to replace this ID, or its TTL to expire.
    observation(api, device_id, snapshot_id)
    return await api.input(device_id, "tap", x=x, y=y,
                           geometryVersion=observed["geometry"]["version"])


@mcp.tool(annotations=WRITE)
async def scroll(device_id: str, direction: Literal["up", "down", "left", "right"],
                 geometry_version: GeometryVersion, ctx: Context,
                 distance: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 400,
                 x: Coordinate | None = None, y: Coordinate | None = None,
                 duration: Duration = 0.5) -> dict:
    """Scroll content with one swipe. Down moves the finger up; right moves it left.

    Distance is native capture pixels. Start defaults to capture center. Rejects
    out-of-bounds endpoints instead of clamping. Requires control/current geometry.
    """
    api = client(ctx)
    status = await api.request("GET", api.path(device_id, "/status"))
    geometry = status["geometry"]
    if geometry["version"] != geometry_version:
        raise RuntimeError("GEOMETRY_CHANGED: refresh status and reacquire control")
    x = geometry["width"] / 2 if x is None else x
    y = geometry["height"] / 2 if y is None else y
    x2, y2 = scroll_points(geometry["width"], geometry["height"], x, y, direction, distance)
    return await api.input(device_id, "swipe", x1=x, y1=y, x2=x2, y2=y2,
                           duration=duration, geometryVersion=geometry_version)


@mcp.tool(annotations=WRITE)
async def drag(device_id: str, x1: Coordinate, y1: Coordinate, x2: Coordinate, y2: Coordinate,
               geometry_version: GeometryVersion, ctx: Context, duration: Duration = 0.8) -> dict:
    """Drag by holding one contact while moving from an explicit start to end.

    This is a continuous touch gesture, with no mouse hover or native iOS drag
    session guarantee. Use long_press separately if the target UI needs it.
    """
    return await client(ctx).input(device_id, "touch-path", points=[{"x": x1, "y": y1}, {"x": x2, "y": y2}],
                                  duration=duration, geometryVersion=geometry_version)


@mcp.tool(annotations=WRITE)
async def type_at(device_id: str, x: Coordinate, y: Coordinate, text: str,
                  geometry_version: GeometryVersion, ctx: Context) -> dict:
    """Tap a text field, then paste text. Requires control/keyboard/clipboard scopes.

    Does not clear existing content or press Enter. If paste fails after the tap,
    reports partial dispatch; never retry this composite operation automatically.
    Handle any iOS Allow Paste prompt and inspect a screenshot before continuing.
    """
    api = client(ctx)
    await api.input(device_id, "tap", x=x, y=y, geometryVersion=geometry_version)
    await asyncio.sleep(0.3)
    try:
        result = await api.input(device_id, "text", text=text, geometryVersion=geometry_version)
    except Exception as error:
        raise RuntimeError(f"TYPE_AT_PARTIAL: tap dispatched; paste not confirmed. {error}") from None
    return {"status": "dispatched", "tap": "dispatched", "paste": result}


@mcp.tool(annotations=READ)
async def wait(duration: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)]) -> dict:
    """Wait at most 30 seconds for animation/paste. Does not renew control."""
    await asyncio.sleep(duration)
    return {"waitedSeconds": duration}


@mcp.tool(annotations=READ, structured_output=False)
async def wait_for(device_id: str, condition: Literal["text_exists", "text_absent", "screen_changed", "online", "capturing", "control_available"],
                   ctx: Context, text: str | None = None, language: str | None = None,
                   timeout: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)] = 10,
                   interval: Annotated[float, Field(ge=0.25, le=5, allow_inf_nan=False)] = 0.5,
                   return_snapshot: bool = False, max_width: ImageWidth = 720,
                   region: Region | None = None) -> dict | list[TextContent | ImageContent]:
    """Poll read-only status, Windows OCR text, or meaningful pixel change.

    Text matching is a case-insensitive substring. screen_changed compares with
    the first frame in this call, using mean absolute grayscale difference >3.
    A timeout returns matched=false; API errors propagate without automatic retry.
    No semantic enabled/focused element detection, no automatic control renewal.
    return_snapshot=true adds the matched frame/status as a compact snapshot;
    text waits reuse their OCR. Other conditions omit OCR. Region filters output,
    not the full-frame matching condition. Timeouts return no image or snapshot ID.
    """
    if condition in {"text_exists", "text_absent"} and not text:
        raise ValueError("text is required for this wait condition")
    api = client(ctx)
    deadline = time.monotonic() + timeout
    baseline = None
    polls = 0
    while True:
        polls += 1
        frame = None
        ocr = {"elements": [], "semanticTreeAvailable": False}
        if condition in {"online", "capturing", "control_available"}:
            status = await api.request("GET", api.path(device_id, "/status"))
            matched = bool(status["control"]["available"] if condition == "control_available" else status[condition])
        else:
            frame = await capture(api, device_id)
            if return_snapshot:
                image_transform(frame, region, max_width)
            if condition == "screen_changed":
                with PillowImage.open(io.BytesIO(frame.png)) as raw:
                    current = raw.convert("L")
                matched = baseline is not None and (baseline.size != current.size or
                    ImageStat.Stat(ImageChops.difference(baseline, current)).mean[0] > 3)
                if baseline is None:
                    baseline = current
            else:
                ocr = await recognize(frame.png, language)
                found = text.casefold() in ocr["text"].casefold()
                matched = found if condition == "text_exists" else not found
        if matched and return_snapshot and frame is None:
            frame = await capture(api, device_id)
            status = frame.status
            matched = bool(status["control"]["available"] if condition == "control_available" else status[condition])
        if matched or time.monotonic() >= deadline:
            result = {"matched": matched, "condition": condition, "polls": polls}
            if matched and return_snapshot:
                return snapshot_contents(api, device_id, frame, ocr, region=region,
                                         max_width=max_width, extra=result)
            return result
        await asyncio.sleep(min(interval, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description="iPhone MCP over the iPhoneMirror Automation API")
    parser.add_argument("--local-key-store", action="store_true",
                        help="Read this Windows user's iPhoneMirror DPAPI key and API port")
    args = parser.parse_args()
    if args.local_key_store:
        os.environ["IPHONEMIRROR_LOCAL_KEY_STORE"] = "1"
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
