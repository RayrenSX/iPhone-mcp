# Background device runtime source

## On-demand screenshots and direct control

The current MCP defaults to `capture_mode=on_demand`, while `enable_control=true`
continues to prepare phone input. `iphonemirror-ondemand.patch` applies to the complete
runtime-v0.2.1 corresponding source (including management, shortcuts and driver setup).
The published runtime-v0.2.1 does not include this supplemental patch. An unpatched app
returns `RUNTIME_UPGRADE_REQUIRED`; the MCP does not silently start video capture.
`capture_mode=continuous` explicitly selects the continuous mode.

This patch stops the selected device's video session, prepares its existing USB control
transport, and requests each PNG through the device's Instruments screenshot service.
It does not briefly start video to take screenshots. It requires a trusted/unlocked USB
phone, Developer Mode and matching DDI. It reports `capturing=false` alongside screenshot
and control capabilities. A screenshot-capable bridge is required even when
`enable_control=false`; no phone input is sent by startup or screenshots.

Screenshot dimensions define the native pixel coordinates. Before a touch operation,
the runtime takes a still image to check geometry again; changed geometry rejects input.
It retains the control lease, cancellation and session-generation guards. Screenshot RPC
responses are excluded from diagnostic logs. A visible preview explicitly switches back
to continuous capture; close it and release the lease before requesting still-image mode.
Wireless/AirPlay still uses the explicit legacy mode.

To build, extract the complete runtime-v0.2.1 source and select a complete working
app installation as the base runtime (including the native Core/USB DLLs and bridge payload).
The build rejects an incomplete payload before changing the source. Use Windows x64,
.NET SDK 10.0.301 and a dedicated Python 3.13 build
environment. The script applies the patch (or checks that it is already applied), copies
`ondemand_screenshot.py`, installs the pinned bridge build dependencies in the supplied
Python environment, builds both the bridge and app, regenerates the bridge integrity
manifest, and runs the native API tests. It keeps the base runtime intact.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-ondemand-runtime.ps1 `
  -SourcePath C:/build/runtime-source `
  -BaseRuntimePath C:/build/runtime/app `
  -Python C:/build/python/Scripts/python.exe `
  -OutputPath C:/build/ondemand-runtime
```

Close the previous app normally, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 `
  -MirrorPath C:/build/ondemand-runtime/app/iPhoneMirror.exe -CaptureMode on_demand
```

Refresh MCP or open a new session to load the new startup argument/default. Verify
`start_iphonemirror`, `get_device_status` and a fresh `snapshot`; the expected state is
`capturing=false`, screenshot capability true and control available. The screenshot
and lease checks alone do not verify the phone's response to input.

The MCP management tools require the runtime distributed in this repository's
`runtime-v0.2.0` Release. The earlier upstream v1.8.5-pre2 app does not have these
management endpoints or background startup behavior.

This runtime is based on GPL-3.0-only iPhoneMirror at the exact public commit
`829c5919f25718efc91f3fae4ee1e808f193964d`:
https://github.com/RayrenSX/iPhoneMirror/tree/829c5919f25718efc91f3fae4ee1e808f193964d

`iphonemirror-management.patch` contains all native source changes. The Release
also provides the complete corresponding patched source archive, including upstream
build scripts, license and third-party notices. Native library/bridge binaries in
the Windows runtime are retained from the upstream v1.8.5-pre2 official ZIP.
The modified application executable is rebuilt from the patched source.

To build from source, use Windows x64, .NET SDK 10.0.301, Python 3.13 and the
Visual Studio C++/Windows SDK toolchain described in upstream docs/DEVELOPMENT.md.
Extract the source archive, then execute `./build.ps1 -Configuration Release`.
Optional media dependencies and their exact build recipes are in that source tree.
Alternatively clone the exact commit and apply the patch with `git apply` before building.

Changes: `--automation-background` creates the controller HWND without showing
the main window, starts device services and the authenticated loopback API, and
forwards same-user background-start requests to an existing supported app instance.
API routes provide app state, preparation of one explicitly selected device and
opening its independent preview. Preparation reuses capture/control sessions,
suppresses automatic setup dialogs and reports missing prerequisites to the client.
Active MCP control leases block preparation/window changes. Existing input APIs
and their permission/lease checks remain in use.

## Phone system shortcuts

`iphonemirror-shortcuts.patch` is a supplemental patch for the complete runtime-v0.2.0
corresponding source (or the exact upstream commit with the management patch applied).
Apply it after `iphonemirror-management.patch`, never to an arbitrary upstream HEAD:

```powershell
git apply --ignore-space-change C:/path/to/iPhone-mcp/runtime-patches/iphonemirror-shortcuts.patch
./build.ps1 -Configuration Release
```

The patch adds `POST /api/v1/devices/{id}/input/shortcut` with a JSON `shortcut` field,
the nine names in `DeviceSystemShortcuts.cs`, OpenAPI enums, and per-device
`capabilities.shortcuts`. It requires `device.control`, `keyboard.input`, and the
existing control session. The native service uses both the lease operation lock and
the keyboard session gate; transport cleanup ignores lease cancellation but stays on
the original captured session. BLE reuses its guarded consumer/navigation helpers.
No Windows hotkeys are synthesized and no shortcut settings are changed.
`--ignore-space-change` permits applying to the release archive's CRLF source files.

Keep the rebuilt executable with the runtime's existing native libraries, bridge tools
and `mcp-runtime.json`; close the previous app normally and use
`scripts/setup.ps1 -MirrorPath <rebuilt-runtime/iPhoneMirror.exe>` to select it.
The original runtime-v0.2.0 download does not include this supplemental patch.

Validation from this MCP checkout:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m pip check
dotnet run --project tests/native-shortcuts/ShortcutTests.csproj -c Release
```

The isolated native tests compile `DeviceSystemShortcuts.cs` against minimal transport
contracts and cover all nine mappings, button/chord release, cancellation, uncertain
dispatch failure, session replacement and BLE delegation. Build the complete patched
native app as well to verify its real contracts. Automated dispatch tests do not prove
the phone UI changed; verify a fresh screenshot after an explicitly authorized action.

## Headless driver setup

Add `FirstRunDriverHost.cs` to the corresponding native source alongside the
management/shortcut changes. It adds `--first-run-pipe <nonce> diagnose|prepare
<serial>` to the driver executable; no driver-manager window is opened. Communication
uses a private current-user pipe. Apple MSI uses `/quiet /norestart`; existing
signature checks, elevation, snapshot and rollback remain in force. Healthy
components are preserved, missing components installed, and unhealthy filters repaired.

Publish the driver and retain the full runtime payload:

```powershell
dotnet publish src/DriverInstaller/iPhoneMirror.DriverInstaller.csproj -c Release -o out/driver
```

Place the rebuilt iPhoneMirror.Driver.exe beside the rebuilt app, then add
`"driverSetupVersion": 1` to mcp-runtime.json only for this rebuilt package.
The original runtime-v0.2.0 lacks this entry point. runtime-v0.2.1 includes the
rebuilt driver with this marker and complete corresponding source. Actual missing
driver installation and healthy reinspection are recorded in docs/HEADLESS_DRIVER_VALIDATION.md.

MCP `prepare_iphone_environment` starts a background job; `get_setup_status`
returns progress, sanitized error codes, and human actions. The calling AI must
present those actions: connect/replug USB, select a device, confirm UAC or restart.
`driversReady` only reports installation/inspection success. `phoneReady` remains
false until the caller verifies startup and a fresh snapshot separately.
Multiple clients are serialized by an OS file lock; driver mutations also have a
native operation gate. Keep MCP connected during installation. If disconnected or
timed out, do not retry an uncertain MSI transaction; diagnose its outcome first.
Jobs are session-local, and automatic repair is limited to diagnosed components.
