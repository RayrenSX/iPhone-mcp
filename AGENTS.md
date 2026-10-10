# Instructions for AI agents

This repository is an installable MCP server for real iPhone/iPad observation and control
through the **iPhoneMirror Windows app**. Read README.md and docs/SETUP.md first.
When asked to install/configure this project, execute the steps; do not just describe them.

## Configure this machine

1. Use Windows 10/11 x64 and Python 3.11+ (3.13 recommended). Work from this checkout;
   never substitute paths from historical validation reports. Install missing Python with
   `winget install --exact --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements`
   when installation is authorized; rediscover the executable after installation.
2. Detect the running iPhoneMirror process, its executable path, adjacent checkout/output,
   or installations under Program Files / LocalAppData Programs. If missing or lacking API,
   follow docs/SETUP.md. Do not assume an old release has Automation API.
3. Start iPhoneMirror if needed. Run
   `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -MirrorPath <actual-exe> -EnableAutomationApi`.
   If the app is already running, omit `-MirrorPath`. Setup creates .venv, installs this package,
   registers `iphone-mcp` in Codex, exports a credential-free client JSON, and runs diagnosis.
   Without Codex use `-SkipCodex` and import artifacts/mcp-config.json in the chosen MCP client.
4. Resolve failed checks, then rerun `.venv/Scripts/python.exe scripts/doctor.py`.
   Exit 0 means a real screenshot succeeded through stdio MCP and API. Check `controlReady`
   and each device's `ocr` separately; observation readiness does not imply input readiness.
5. Open a new Codex session (running tool catalogs may not reload). Call list_devices,
   get_device_status and snapshot through the client's actual MCP tools. Report whether the
   client invocation was verified or only the stdio diagnostic was verified.

USB connection, unlocking, Trust This Computer, pairing and on-phone permission prompts
may require the human. Continue all independent configuration before asking for these.
Use iPhoneMirror's own UI for capture/control setup; don't fabricate device readiness.
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
