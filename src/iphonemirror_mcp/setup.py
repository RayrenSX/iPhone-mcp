"""Bounded, presentation-free setup jobs. Never return native log text or secrets."""
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path

import httpx

TAG = "runtime-v0.2.1"
ASSET = "iPhoneMirror-mcp-runtime-v0.2.1-win-x64.zip"
RELEASE = f"https://github.com/RayrenSX/iPhone-mcp/releases/download/{TAG}"


class SetupFailure(Exception):
    pass


class SetupGate:
    """OS releases the file lock even if a client terminates unexpectedly."""
    def __enter__(self):
        import msvcrt
        root = Path(os.environ["LOCALAPPDATA"]) / "iPhone-mcp"
        root.mkdir(parents=True, exist_ok=True)
        self.file = (root / "setup.lock").open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.file.close()
            raise SetupFailure("SETUP_BUSY") from None
        return self

    def __exit__(self, *args):
        self.file.close()


def checksum(manifest):
    matches = re.findall(r"^([a-fA-F0-9]{64})\s+\*?" + re.escape(ASSET) + r"\s*$", manifest, re.M)
    if len(matches) != 1:
        raise SetupFailure("INVALID_RELEASE_MANIFEST")
    return matches[0].lower()


def install_runtime(progress, proxy=None):
    """Direct first; an explicitly supplied proxy is used only after network failure."""
    root = Path(os.environ["LOCALAPPDATA"]) / "iPhone-mcp" / "runtime" / TAG
    root.mkdir(parents=True, exist_ok=True)
    archive = root / (uuid.uuid4().hex + ".zip")
    expected = None
    for route in ([None, proxy] if proxy else [None]):
        try:
            progress(stage="downloading_runtime", route="proxy" if route else "direct")
            with httpx.Client(proxy=route, trust_env=False, follow_redirects=True,
                              timeout=httpx.Timeout(30, connect=15)) as http:
                response = http.get(RELEASE + "/SHA256SUMS.txt")
                response.raise_for_status()
                expected = checksum(response.text)
                digest = hashlib.sha256()
                count = 0
                started = time.monotonic()
                with http.stream("GET", RELEASE + "/" + ASSET) as response:
                    response.raise_for_status()
                    with archive.open("wb") as output:
                        for block in response.iter_bytes(1024 * 1024):
                            if time.monotonic() - started > 900 or count + len(block) > 1024**3:
                                raise SetupFailure("DOWNLOAD_LIMIT_EXCEEDED")
                            output.write(block)
                            digest.update(block)
                            count += len(block)
                            progress(downloadedBytes=count)
                if digest.hexdigest() != expected:
                    raise SetupFailure("RUNTIME_CHECKSUM_MISMATCH")
            break
        except httpx.HTTPError:
            if route is not None or not proxy:
                raise SetupFailure("RUNTIME_DOWNLOAD_FAILED") from None
    progress(stage="extracting_runtime")
    extract = root / ("install-" + uuid.uuid4().hex)
    extract.mkdir()
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if sum(x.file_size for x in members) > 2 * 1024**3:
            raise SetupFailure("UNSAFE_RUNTIME_ARCHIVE")
        for member in members:
            target = (extract / member.filename).resolve()
            if not target.is_relative_to(extract.resolve()) or "\\" in member.filename or ":" in member.filename or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise SetupFailure("UNSAFE_RUNTIME_ARCHIVE")
        package.extractall(extract)
    apps = list(extract.rglob("iPhoneMirror.exe"))
    if len(apps) != 1 or not (apps[0].parent / "iPhoneMirror.Driver.exe").is_file():
        raise SetupFailure("INVALID_RUNTIME_ARCHIVE")
    marker = json.loads((apps[0].parent / "mcp-runtime.json").read_text(encoding="utf-8-sig"))
    if marker.get("managementVersion") != 1:
        raise SetupFailure("RUNTIME_UPGRADE_REQUIRED")
    # A new directory preserves existing installs and running executables.
    config = root.parents[1] / "runtime.json"
    temporary = config.with_name("runtime-" + uuid.uuid4().hex + ".json")
    temporary.write_text(json.dumps({"executable": str(apps[0]), "sha256": expected}), encoding="utf-8")
    os.replace(temporary, config)
    archive.unlink()
    return apps[0]


def driver_events(exe, operation, serial=""):
    """Same-user private pipe; the driver owns signature checks, UAC and rollback."""
    import win32api
    import win32file
    import win32pipe
    import win32security
    import pywintypes

    marker = json.loads((exe.parent / "mcp-runtime.json").read_text(encoding="utf-8-sig"))
    if marker.get("driverSetupVersion") != 1:
        raise SetupFailure("DRIVER_CLI_UPGRADE_REQUIRED")
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), 8)
    sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    token.Close()
    acl = win32security.ACL()
    acl.AddAccessAllowedAce(win32security.ACL_REVISION, 0x10000000, sid)
    descriptor = win32security.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorDacl(1, acl, 0)
    security = pywintypes.SECURITY_ATTRIBUTES()
    security.SECURITY_DESCRIPTOR = descriptor
    name = uuid.uuid4().hex
    pipe = win32pipe.CreateNamedPipe(r"\\.\pipe\iPhoneMirror.setup." + name,
        win32pipe.PIPE_ACCESS_DUPLEX | 0x00080000,
        win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_NOWAIT | 0x00000008,
        1, 65536, 65536, 0, security)
    process = None
    try:
        # MCP SDK clients deliberately pass a small environment. WPF's font
        # initialization requires windir even when SYSTEMROOT is present.
        environment = dict(os.environ)
        environment["windir"] = win32api.GetWindowsDirectory()
        process = subprocess.Popen([str(exe.parent / "iPhoneMirror.Driver.exe"),
            "--first-run-pipe", name, operation, serial], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, env=environment)
        deadline = time.monotonic() + 1800
        buffer = b""
        connected = False
        while time.monotonic() < deadline:
            try:
                if not connected:
                    try:
                        win32pipe.ConnectNamedPipe(pipe, None)
                    except pywintypes.error as error:
                        if error.winerror != 535:
                            raise
                    connected = True
                _, block = win32file.ReadFile(pipe, 65536)
                buffer += block
                if len(buffer) > 1024**2:
                    raise SetupFailure("INVALID_DRIVER_RESPONSE")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    yield json.loads(line.decode("utf-8-sig"))
            except pywintypes.error as error:
                if error.winerror not in (109, 231, 232, 233, 536):
                    raise SetupFailure("DRIVER_CHANNEL_FAILED") from None
                if process.poll() is not None:
                    if buffer.strip():
                        yield json.loads(buffer.decode("utf-8-sig"))
                    return
                time.sleep(.1)
        # Do not kill MSI or retry a transaction with uncertain outcome.
        raise SetupFailure("DRIVER_OUTCOME_UNKNOWN")
    finally:
        win32file.CloseHandle(pipe)


def driver_id(serial):
    return "setup:" + hashlib.sha256(serial.encode()).hexdigest()[:24]


class SetupJobs:
    def __init__(self, resolve):
        self.resolve = resolve
        self.lock = threading.Condition()
        self.jobs = {}
        self.active = None

    def status(self, job_id, after_revision=None, timeout=0):
        with self.lock:
            if job_id not in self.jobs:
                raise RuntimeError("SETUP_JOB_NOT_FOUND")
            if after_revision is not None and timeout > 0:
                self.lock.wait_for(lambda: self.jobs[job_id]["revision"] > after_revision
                                   or self.jobs[job_id]["state"] != "running",
                                   timeout=min(timeout, 30))
            return json.loads(json.dumps(self.jobs[job_id]))

    def begin(self, install_drivers=True, device_id=None, proxy=None):
        if os.name != "nt":
            raise RuntimeError("SETUP_UNAVAILABLE: Windows x64 is required")
        if proxy and (not proxy.startswith(("http://", "https://")) or "@" in proxy):
            raise ValueError("Proxy must be an HTTP(S) URL without credentials")
        with self.lock:
            if self.active:
                return dict(self.jobs[self.active], reused=True)
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {"jobId": job_id, "state": "running", "stage": "checking_runtime",
                                 "phoneReady": False, "driversReady": False,
                                 "installDrivers": install_drivers, "actionRequired": None,
                                 "revision": 0}
            self.active = job_id

        def update(**values):
            with self.lock:
                job = self.jobs[job_id]
                if any(job.get(k) != v for k, v in values.items()):
                    job.update(values)
                    job["revision"] += 1
                    self.lock.notify_all()

        def perform():
            try:
                try:
                    exe = self.resolve()
                except RuntimeError as error:
                    if not str(error).startswith("RUNTIME_NOT_INSTALLED"):
                        raise SetupFailure("RUNTIME_UPGRADE_REQUIRED") from None
                    exe = install_runtime(update, proxy)
                if not install_drivers:
                    update(state="completed", stage="runtime_installed", nextTool="start_iphonemirror")
                    return
                inventory = None
                for event in driver_events(exe, "diagnose"):
                    if event.get("Stage") == "Result":
                        inventory = event
                if inventory is None or not inventory.get("Success"):
                    raise SetupFailure("INVALID_DRIVER_RESPONSE")
                devices = inventory.get("Devices") or []
                choices = [{"id": driver_id(d["Serial"]), "healthy": bool(d.get("Healthy")),
                            "filterInstalled": bool(d.get("FilterInstalled"))} for d in devices]
                update(devices=choices)
                selected = [d for d in devices if device_id == driver_id(d["Serial"])] if device_id else devices
                if not selected:
                    update(state="action_required", actionRequired="connect_usb" if not device_id else "select_device")
                    return
                if len(selected) != 1:
                    update(state="action_required", actionRequired="select_device")
                    return
                environment = inventory.get("Environment") or {}
                if selected[0].get("Healthy") and selected[0].get("FilterInstalled") and all(
                    environment.get(k) for k in ("AppleReady", "UsbFilesMatch", "UsbRunning")
                ):
                    update(state="completed", stage="drivers_healthy", driversReady=True, nextTool="start_iphonemirror")
                    return
                terminal = False
                for event in driver_events(exe, "prepare", selected[0]["Serial"]):
                    stage = event.get("Stage", "")
                    update(stage=stage)
                    actions = {"Replug": "replug_usb", "Restart": "restart_windows",
                               "Disconnected": "connect_usb", "Busy": "wait_for_existing_installation"}
                    if stage in actions:
                        update(state="action_required", actionRequired=actions[stage])
                        terminal = True
                    elif stage == "Result" and event.get("Success"):
                        update(state="completed", driversReady=True, nextTool="start_iphonemirror")
                        terminal = True
                    elif stage in ("AppleFailed", "DriverFailed", "Cancelled"):
                        detail = event.get("Detail") or ""
                        if "cancel" in detail.lower() or "取消" in detail:
                            raise SetupFailure("UAC_CANCELLED")
                        raise SetupFailure("DRIVER_INSTALL_FAILED" if stage != "Cancelled" else "SETUP_CANCELLED")
                if not terminal:
                    raise SetupFailure("DRIVER_OUTCOME_UNKNOWN")
            except SetupFailure as error:
                code = str(error)
                update(state="failed", errorCode=code, retryAllowed=code == "RUNTIME_DOWNLOAD_FAILED",
                       actionRequired="wait_for_existing_installation" if code == "SETUP_BUSY" else
                       "confirm_uac" if code == "UAC_CANCELLED" else
                       "upgrade_runtime" if code in ("DRIVER_CLI_UPGRADE_REQUIRED", "RUNTIME_UPGRADE_REQUIRED") else
                       "diagnose_installation")
            except Exception:
                update(state="failed", errorCode="SETUP_FAILED", actionRequired="diagnose_installation")
        def work():
            try:
                with SetupGate():
                    perform()
            except SetupFailure as error:
                update(state="action_required", errorCode=str(error),
                       actionRequired="wait_for_existing_installation")
            except Exception:
                update(state="failed", errorCode="SETUP_FAILED", actionRequired="diagnose_installation")
            finally:
                with self.lock:
                    self.active = None

        threading.Thread(target=work, name="iphone-setup", daemon=True).start()
        return self.status(job_id)
