# Headless driver installation validation

Validated on 2026-10-10 in the Windows 11 evaluation VirtualBox guest used by
CLEAN_FIRST_USE_VALIDATION.md. The restored baseline had zero Apple/libusb driver
packages, no iPhoneMirror and no MCP installation. No host drivers were reinstalled.

The candidate native package contained managementVersion=1 and driverSetupVersion=1.
The current scripts/setup-drivers.py called the same SetupJobs implementation exposed
by prepare_iphone_environment. No driver-manager GUI was opened. Windows UAC was
confirmed by the human.

Observed results:

- Apple MSI returned exit code 0; native install_completed reported success=True.
  Apple Mobile Device Service was running.
- USB kind=Install returned success=True and requires_replug=True. The Python script
  reported state=action_required, stage=Replug, actionRequired=replug_usb.
- After the human unplugged/reconnected USB, the same script reported completed,
  stage=drivers_healthy, driversReady=true, healthy=true, filterInstalled=true.
  libusb0 was running. Healthy drivers were then skipped.
- A concurrent call returned SETUP_BUSY, without starting a second installation.

Limits and problems encountered:

- Windows Update and a temporary Windows profile delayed preparation considerably.
  Python/MCP dependencies were installed from locally downloaded matching wheels
  after guest network installation stalled. This was not a first-download network test.
- A short-lived guest-control test channel closed after the Apple transaction,
  producing a broken pipe. The Apple transaction completed; USB was not started.
  Native logs and service state were checked before resuming with a long-lived
  channel. No uncertain MSI transaction was repeated. Keep MCP connected during setup.
- This verifies driver installation and inspection. It does not prove a guest phone
  screenshot or input. phoneReady remains false until startup/snapshot verification.
- Actual stdio MCP client loaded 28 tools and completed prepare/status with
  driversReady=true on the restored host. This uncovered a filtered-environment
  WPF font initialization failure: the child driver now receives windir from
  the Windows API. A regression test covers this missing variable.
- Python tests: 37 passed; pip check passed. Driver native build/publish passed.
  Native shortcut tests passed separately; their results do not prove UI effects.

Raw guest logs and identities are kept only in ignored artifacts, not in this report.
