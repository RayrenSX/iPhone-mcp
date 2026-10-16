# AI setup and troubleshooting

Read AGENTS.md, then execute installation and real MCP verification. Requires Windows 10/11 x64 and Python 3.11+.

```powershell
git clone https://github.com/RayrenSX/iPhone-mcp.git
cd iPhone-mcp
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

Bootstrap installs missing Python using winget, downloads this repository's runtime-v0.2.1,
verifies SHA256SUMS.txt, and installs it under %LOCALAPPDATA%/iPhone-mcp/runtime/v0.2.1/app.
It installs the MCP package, registers Codex, starts the background runtime and diagnoses real screenshots/OCR.
The main window stays hidden. Older official runtimes lack background management: close them normally and rerun.
Bootstrap/setup explicitly select continuous capture for compatibility with the published runtime;
pass -CaptureMode on_demand with -MirrorPath pointing to a patched app to install in still-image mode.
This installer choice does not change the MCP tool's on_demand default or a user's later selection.
Complete corresponding native source and patch are provided with the release; see runtime-patches/README.md.

Without Git, download the repository ZIP. Without winget, install Python and pass -Python <actual-executable>.
Without Codex CLI, pass -SkipCodex and import artifacts/mcp-config.json into another MCP client.
For download failures use -Proxy <HTTP-proxy-URL>. This does not change system proxy settings.
-SkipDoctor configures only; it does not prove device readiness. -MirrorPath <actual-iPhoneMirror.exe>
selects an existing compatible runtime. scripts/setup.ps1 can reuse that runtime without UI automation.

## First device preparation

1. Connect by USB data cable, unlock the phone and confirm Trust This Computer.
2. Bootstrap runs scripts/setup-drivers.py without the driver-manager GUI. MCP clients use
   prepare_iphone_environment and poll get_setup_status with the returned jobId,
   after_revision=revision and timeout=20 to wait for a change (maximum 30s).
   Omit the new parameters for an immediate read. Terminal/action_required states
   return immediately; present actionRequired to the user instead of repeatedly polling.
   Requires driverSetupVersion=1,
   included in runtime-v0.2.1. Present actionRequired to the user; confirm UAC if requested,
   replug USB when reported, and rerun diagnosis. Healthy drivers are skipped. -SkipDrivers
   configures MCP without driver installation. Keep the client connected until a terminal state.
3. Input requires pairing/binding, iPhone Developer Mode and possible restart confirmation.
   The first DDI download needs network access. Finish reported prerequisites and retry.
4. Install the [on-demand screenshot patch](../runtime-patches/README.md#on-demand-screenshots-and-direct-control)
   for the default direct-control/still-image mode. The published runtime-v0.2.1 needs this supplemental patch;
   bootstrap does not build it automatically. On an unpatched runtime explicitly use capture_mode=continuous
   (scripts/start-runtime.py --mode continuous) for continuous video capture.
5. In a new Codex session call start_iphonemirror. A sole online device is prepared automatically;
   with multiple devices select device_id from list_devices. It defaults to capture_mode=on_demand
   and enable_control=true: stop continuous capture, prepare direct control, and request individual screenshots.
   Use capture_mode=continuous for frequent observations, animation tracking or a visible preview.
   On-demand screenshots reuse the control transport and need Developer Mode/DDI even for observation.
   enable_control=false changes readiness requirements, not the input lease requirement or an existing control channel.
6. Check devicePrepared/actionRequired, then snapshot. To show a phone preview, release any control lease
   and call open_independent_window(device_id).

MCP initialization and tool discovery work before the app starts or a key exists. start_iphonemirror
starts the hidden app, enables local API and prepares direct control plus on-demand screenshots without video capture.
On-demand mode currently supports USB. capturing=false is expected when screenshot/control capabilities are true.
An explicit preview switches back to continuous capture. Close that preview and release leases before switching to still images.
get_app_status reports window/API state. The app and preview survive closing the MCP connection.
Background startup does not permanently change the saved API-enabled preference.
Physical connection, unlock/trust, Developer Mode restart and secure-desktop UAC may need the user.

## Diagnosis

```powershell
.venv/Scripts/python.exe scripts/start-runtime.py
.venv/Scripts/python.exe scripts/doctor.py
codex mcp get iphone-mcp
```

start-runtime performs actual stdio startup/device preparation. doctor enumerates 28 tools, devices,
status, real screenshots and OCR without sending phone input or printing identities, screen text or keys.
Status is reused from the verified snapshot; the separate OCR check omits its image payload.
ready=true proves a screenshot; controlReady reports input availability, not verified input effects.
Exit code 2 means the API or device is not ready.
start-runtime.py accepts --device-id for multiple devices, and exits 2 when selection/preparation is incomplete.

| Symptom | Action |
|---|---|
| RUNTIME_NOT_INSTALLED | Run bootstrap, then install the on-demand patch |
| RUNTIME_UPGRADE_REQUIRED | Apply the on-demand patch for the default mode; capture_mode=continuous selects continuous video |
| BACKGROUND_START_FAILED | Check current-user desktop, local WMI, API port and app logs |
| No online device | Connect, unlock and trust, then retry start_iphonemirror |
| Multiple devices | Select device_id explicitly using list_devices |
| controlReady=false | Finish drivers, pairing, Developer Mode and DDI prerequisites; retry startup |
| ocr=false | Install Windows OCR language packs or use snapshot(use_ocr=false) |
| Codex tools missing | Start a new session or refresh MCP; existing tool catalogs may not reload |
| Input denied | Use client permissions appropriate to the authorized task; setup does not change policies |

The key is current-user DPAPI at %LOCALAPPDATA%/iPhoneMirror/automation-key.bin.
The API port comes from settings.json (default 17890); only loopback HTTP origins are accepted.
IPHONEMIRROR_API_KEY / IPHONEMIRROR_API_URL override connection settings; IPHONEMIRROR_EXE overrides runtime discovery.
Never commit keys, identities or screenshots; do not edit running settings.json to bypass application flows.

## Compact observations

Refresh the MCP connection or start a new session after updating this checkout. All 28 tools remain.
snapshot defaults to compact OCR and a 720px maximum display width; native input coordinates
and geometry checks remain unchanged. Use compact=false and max_width=0 for full OCR fields
and native image detail. Crop output preserves OCR IDs and native bounds, including partial
lines that overlap the region. include_image=false is for read-only text extraction; inspect
images before input and to verify effects. Image blocks are returned only in content, without
a Base64 copy in structuredContent. Clients consuming the old structuredContent.result must migrate.

The status/capabilities/geometry in snapshot are fresh, so normal operation can reuse them
without an extra get_device_status call. Follow AGENTS.md's explicit checks for installation acceptance.
wait_for(return_snapshot=true) returns its matched frame as a compact snapshot, including
matched/condition/polls in the same metadata. Text waits reuse OCR; other conditions omit it.
max_width/region affect the returned view, not the full-frame text predicate. A timeout adds
no image or new snapshot ID, and a match alone does not mean animation has stopped.

## Phone system shortcuts

`press_shortcut` requires a native runtime with the shortcut API, included in runtime-v0.2.1;
the original runtime-v0.2.0 does not include it. Upgrade or apply/build the supplemental patch following
runtime-patches/README.md, then select that compatible app with setup.ps1 -MirrorPath.
Close the previous app normally before starting the replacement. Start a new MCP session
to reload the 28-tool catalog, inspect get_device_status.capabilities.shortcuts, and acquire
control before invoking one supported action. A missing shortcuts capability returns
RUNTIME_UPGRADE_REQUIRED without sending input; an empty list means that transport has
no supported actions. Doctor only observes the phone and does not verify shortcut UI effects.
