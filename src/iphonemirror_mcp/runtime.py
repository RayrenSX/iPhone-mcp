"""Lazy API credentials and explicit background device-runtime management."""
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

from .client import AutomationClient
from .credentials import configuration
from .setup import SetupJobs


class RuntimeClient:
    def __init__(self):
        self.api = None
        self.observations = {}
        self.management_lock = asyncio.Lock()
        self.setup = SetupJobs(self.executable)

    def connect(self):
        if self.api is None:
            self.api = AutomationClient(*configuration())
            self.api.observations = self.observations
        return self.api

    path = staticmethod(AutomationClient.path)

    async def request(self, *args, **kwargs):
        return await self.connect().request(*args, **kwargs)

    async def acquire(self, *args, **kwargs):
        return await self.connect().acquire(*args, **kwargs)

    async def release(self, *args, **kwargs):
        return await self.connect().release(*args, **kwargs)

    async def input(self, *args, **kwargs):
        return await self.connect().input(*args, **kwargs)

    async def close(self):
        if self.api is not None:
            await self.api.close()

    @staticmethod
    def executable():
        if os.name != "nt":
            raise RuntimeError("BACKGROUND_START_UNAVAILABLE: Windows is required")
        configured = os.environ.get("IPHONEMIRROR_EXE")
        folder = Path(os.environ["LOCALAPPDATA"]) / "iPhone-mcp"
        if not configured:
            try:
                configured = json.loads((folder / "runtime.json").read_text(encoding="utf-8-sig"))["executable"]
            except (OSError, ValueError, KeyError):
                configured = str(folder / "runtime" / "v0.2.0" / "app" / "iPhoneMirror.exe")
        exe = Path(configured).resolve()
        if exe.name.casefold() != "iphonemirror.exe" or not exe.is_file():
            raise RuntimeError("RUNTIME_NOT_INSTALLED: run scripts/bootstrap.ps1 first")
        try:
            marker = json.loads((exe.parent / "mcp-runtime.json").read_text(encoding="utf-8"))
            if marker["managementVersion"] != 1:
                raise ValueError()
        except (OSError, ValueError, KeyError):
            raise RuntimeError("RUNTIME_UPGRADE_REQUIRED: install the MCP background runtime with scripts/bootstrap.ps1") from None
        return exe

    async def app_status(self):
        try:
            return await self.request("GET", "app/status")
        except RuntimeError as error:
            if str(error).startswith("INVALID_REQUEST"):
                raise RuntimeError("RUNTIME_UPGRADE_REQUIRED: this app lacks background/window management") from None
            raise

    @staticmethod
    def launch(exe, environment):
        # MCP clients often put the server in a kill-on-close Windows Job. Use
        # the local, current-user WMI provider so closing MCP doesn't kill the
        # independent preview or interrupt USB capture teardown.
        import pythoncom
        import win32com.client
        import win32api
        import win32process
        pythoncom.CoInitialize()
        services = startup = parameters = result = None
        try:
            services = win32com.client.Dispatch("WbemScripting.SWbemLocator").ConnectServer(".", "root/cimv2")
            startup = services.Get("Win32_ProcessStartup").SpawnInstance_()
            startup.ShowWindow = 0
            startup.EnvironmentVariables = [f"{key}={value}" for key, value in environment.items()]
            parameters = services.Get("Win32_Process").Methods_("Create").InParameters.SpawnInstance_()
            parameters.CommandLine = subprocess.list2cmdline([str(exe), "--automation-background"])
            parameters.CurrentDirectory = str(exe.parent)
            parameters.ProcessStartupInformation = startup
            result = services.ExecMethod("Win32_Process", "Create", parameters)
            if int(result.Properties_("ReturnValue").Value) != 0:
                raise RuntimeError("BACKGROUND_LAUNCH_DENIED: local WMI could not start the user runtime")
            handle = win32api.OpenProcess(0x1000, False, int(result.Properties_("ProcessId").Value))
        finally:
            result = parameters = startup = services = None
            pythoncom.CoUninitialize()

        class Process:
            returncode = None

            def poll(self):
                code = win32process.GetExitCodeProcess(handle)
                self.returncode = None if code == 259 else code
                return self.returncode

            def __del__(self):
                win32api.CloseHandle(handle)

        return Process()

    async def start(self, device_id=None, enable_control=True):
        async with self.management_lock:
            # Validate support before launching: old apps ignore unknown CLI flags and show the main UI.
            try:
                exe = self.executable()
            except RuntimeError as error:
                if not str(error).startswith("RUNTIME_NOT_INSTALLED"):
                    raise
                job = self.setup.begin(install_drivers=False)
                return {"devicePrepared": False, "actionRequired": "wait_for_setup",
                        "setup": job, "nextTool": "get_setup_status"}
            try:
                await self.app_status()
            except RuntimeError as error:
                if str(error).startswith("RUNTIME_UPGRADE_REQUIRED"):
                    raise
            except ValueError:
                pass
            environment = os.environ.copy()
            # MCP clients filter inherited environment variables. WPF resolves its
            # font directory through WINDIR even when SYSTEMROOT is already present.
            if "WINDIR" not in environment and environment.get("SYSTEMROOT"):
                environment["WINDIR"] = environment["SYSTEMROOT"]
            process = await asyncio.to_thread(self.launch, exe, environment)
            deadline = time.monotonic() + 20
            status = None
            while time.monotonic() < deadline:
                if process.poll() not in (None, 0):
                    raise RuntimeError(f"BACKGROUND_PROCESS_FAILED: native process exited with code {process.returncode}")
                try:
                    status = await self.app_status()
                    if status.get("background") and status.get("apiRunning"):
                        break
                except (RuntimeError, ValueError):
                    # Only startup connection polling is retried, never device input.
                    pass
                await asyncio.sleep(.3)
            else:
                raise RuntimeError("BACKGROUND_START_FAILED: check the runtime version, same-user session and API port")
            devices = []
            for _ in range(20):
                devices = (await self.request("GET", "devices"))["devices"]
                if devices:
                    break
                await asyncio.sleep(.25)
            if device_id is None:
                online = [d for d in devices if d.get("online")]
                if len(online) != 1:
                    return {"app": status, "devicePrepared": False,
                            "actionRequired": "Connect/unlock/trust a device" if not online else "Select device_id from list_devices; multiple devices are online"}
                device_id = online[0]["id"]
            elif not any(d["id"] == device_id for d in devices):
                raise RuntimeError("DEVICE_NOT_FOUND: select device_id from list_devices")
            prepared = await self.request("POST", self.path(device_id, "/prepare"), {"enableControl": enable_control}, timeout=65)
            ready = prepared.get("capturing", False) and (not enable_control or prepared.get("controlAvailable", False))
            return {"app": await self.app_status(), "devicePrepared": ready, "device_id": device_id, "device": prepared}
