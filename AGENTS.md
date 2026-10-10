# Instructions for AI agents

This repository is an installable MCP server for real iPhone/iPad observation and control
through the **iPhoneMirror Windows app**. Read README.md and docs/SETUP.md first.
When asked to install/configure this project, execute the steps; do not just describe them.

## Configure this machine

1. Use Windows 10/11 x64 and Python 3.11+ (3.13 recommended). Work from this checkout;
   never substitute paths from historical validation reports. Install missing Python with
   `winget install --exact --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements`
   when installation is authorized; rediscover the executable after installation.
2. For a fresh machine run
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap.ps1 -OpenDriverManager`.
   Bootstrap installs missing Python using winget and downloads/checksums this repository's
   runtime-v0.2.0 background runtime if no app is running. Official older runtimes lack
   the management endpoints; don't use them for background startup.
   Bootstrap uses an existing compatible app; if that app lacks the runtime marker,
   close it normally and rerun. A `-MirrorPath <actual-exe>` overrides runtime discovery.
3. Follow docs/SETUP.md to prepare USB drivers, Trust This Computer, capture and wired control.
   The driver manager's one-click installer handles missing Apple USB support and filters.
   Human UAC and on-phone prompts cannot be completed by a headless agent. Don't reinstall
   drivers when an existing device already works. Setup creates .venv, installs this package,
   registers `iphone-mcp` in Codex, exports a credential-free client JSON, and runs diagnosis.
   Without Codex use bootstrap `-SkipCodex` and import artifacts/mcp-config.json in the chosen MCP client.
   For an already configured app, `scripts/setup.ps1 -EnableAutomationApi` avoids downloading.
4. Resolve failed checks, then rerun `.venv/Scripts/python.exe scripts/doctor.py`.
   Exit 0 means a real screenshot succeeded through stdio MCP and API. Check `controlReady`
   and each device's `ocr` separately; observation readiness does not imply input readiness.
5. Open a new Codex session (running tool catalogs may not reload). Call start_iphonemirror,
   then list_devices,
   get_device_status and snapshot through the client's actual MCP tools. Report whether the
   client invocation was verified or only the stdio diagnostic was verified.

USB connection, unlocking, Trust This Computer, pairing and on-phone permission prompts
may require the human. Continue all independent configuration before asking for these.
Use start_iphonemirror for hidden capture/control preparation; specify device_id when multiple
devices are online. Read devicePrepared/actionRequired rather than assuming readiness.
Call open_independent_window only when a visible preview is requested; release the lease first.
Never weaken Codex permission settings just to make a diagnostic pass.

## Input and verification

Installation/doctor are observation-only on the phone. Input needs a user task authorizing
the intended device operation. Observe first; use current native screenshot coordinates and
geometry version; acquire a lease, act once, verify a fresh snapshot, release in finally.
Do not blindly execute scripts/plans/*.json: these are historical 1082x2340 device plans.
Never retry input after uncertain timeout. Do not paste into or submit unrelated apps.
OCR provides text boxes, not an iOS accessibility tree or application debug logs.

## Development

Run `.venv/Scripts/python.exe -m unittest discover -s tests -v` and pip check for code changes.
Keep stdout reserved for MCP protocol. Never commit artifacts, screenshots, clipboard data,
device identifiers, .venv, settings files or API credentials. Keys stay in current-user DPAPI;
do not copy them to Codex config. Docs must distinguish dispatch from verified UI effects.
