"""One device screenshot over the existing control session; never start video."""
import asyncio
import base64

from pymobiledevice3.dtx_service_provider import DtxServiceProvider


class ScreenshotHub(DtxServiceProvider):
    SERVICE_NAME = "com.apple.instruments.dtservicehub"
    RSD_SERVICE_NAME = SERVICE_NAME


async def screenshot_result(rsd, frame, generation, current, emit):
    result = {"event": "screenshot_result", "requestId": frame["requestId"],
              "generation": generation, "success": False}
    try:
        if not current():
            raise RuntimeError("session changed")
        async with asyncio.timeout(20):
            async with ScreenshotHub(rsd) as hub:
                channel = await hub.dtx.open_channel("com.apple.instruments.server.services.screenshot")
                data = bytes(await channel.invoke("takeScreenshot"))
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 32 * 1024 * 1024:
            raise ValueError("invalid screenshot")
        if not current():
            raise RuntimeError("session changed")
        result.update(success=True, text=base64.b64encode(data).decode("ascii"))
    except asyncio.CancelledError:
        result["code"] = "SCREENSHOT_CANCELLED"
        raise
    except Exception:
        result["code"] = "SCREENSHOT_UNAVAILABLE"
    finally:
        await emit(result)
