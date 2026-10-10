# AI setup and troubleshooting

Read AGENTS.md, then execute installation and real MCP verification. Requires Windows 10/11 x64 and Python 3.11+.

```powershell
git clone https://github.com/RayrenSX/iPhone-mcp.git
cd iPhone-mcp
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

Bootstrap installs missing Python using winget, downloads this repository's runtime-v0.2.0,
verifies SHA256SUMS.txt, and installs it under %LOCALAPPDATA%/iPhone-mcp/runtime/v0.2.0/app.
It installs the MCP package, registers Codex, starts the background runtime and diagnoses real screenshots/OCR.
The main window stays hidden. Older official runtimes lack background management: close them normally and rerun.
Complete corresponding native source and patch are provided with the release; see runtime-patches/README.md.

Without Git, download the repository ZIP. Without winget, install Python and pass -Python <actual-executable>.
Without Codex CLI, pass -SkipCodex and import artifacts/mcp-config.json into another MCP client.
For download failures use -Proxy <HTTP-proxy-URL>. This does not change system proxy settings.
-SkipDoctor configures only; it does not prove device readiness. -MirrorPath <actual-iPhoneMirror.exe>
selects an existing compatible runtime. scripts/setup.ps1 can reuse that runtime without UI automation.

## First device preparation

1. Connect by USB data cable, unlock the phone and confirm Trust This Computer.
2. explicitly opens the driver UI. Install missing Apple USB support and capture filters
   using its one-click installer, confirming UAC if requested. Do not reinstall working drivers.
3. Input requires pairing/binding, iPhone Developer Mode and possible restart confirmation.
   The first DDI download needs network access. Finish reported prerequisites and retry.
4. In a new Codex session call start_iphonemirror. A sole online device is prepared automatically;
   with multiple devices select device_id from list_devices. For observation only pass enable_control=false.
5. Check devicePrepared/actionRequired, then snapshot. To show a phone preview, release any control lease
   and call open_independent_window(device_id).

MCP initialization and tool discovery work before the app starts or a key exists. start_iphonemirror
starts the hidden app, enables local API, capture and reverse control without opening a preview.
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
ready=true proves a screenshot; controlReady reports input availability, not verified input effects.
Exit code 2 means the API or device is not ready.

| Symptom | Action |
|---|---|
| RUNTIME_NOT_INSTALLED / RUNTIME_UPGRADE_REQUIRED | Close old app normally and run bootstrap |
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

## Phone system shortcuts

`press_shortcut` requires a native runtime with the shortcut API; the original downloadable
runtime-v0.2.0 does not include it. Apply/build the supplemental patch following
runtime-patches/README.md, then select that compatible app with setup.ps1 -MirrorPath.
Close the previous app normally before starting the replacement. Start a new MCP session
to reload the 28-tool catalog, inspect get_device_status.capabilities.shortcuts, and acquire
control before invoking one supported action. A missing shortcuts capability returns
RUNTIME_UPGRADE_REQUIRED without sending input; an empty list means that transport has
no supported actions. Doctor only observes the phone and does not verify shortcut UI effects.
