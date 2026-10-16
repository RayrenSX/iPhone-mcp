# On-demand screenshots with direct USB control

Validated on Windows x64 with a USB iPhone running iOS 18.7.8 on 2026-10-16.
This uses the supplemental on-demand native patch and screenshot-capable control
bridge, not the unmodified runtime-v0.2.1 executable.

The updated stdio `start_iphonemirror` returns `devicePrepared=true`,
`captureMode=on_demand`, `capturing=false`, `screenshotAvailable=true` and
`controlAvailable=true`. App status confirms both main and independent preview
windows are hidden. The installed runtime preserves the v0.2.1 driver setup entry.

Through the current chat's actual MCP tools, device status and a fresh `snapshot`
confirmed a 1125×2436 PNG, working Chinese OCR and touch/keyboard/shortcut
capabilities while `capturing=false`. Acquiring a control lease set acquired=true;
release succeeded and restored acquired=false. No phone input was sent, so these
checks verify observation and control availability, not actual touch/UI effects.
Doctor exited 0 with screenshot=true, ocr=true and controlReady=true.

The existing chat retains its loaded older MCP startup implementation, which
incorrectly returns devicePrepared=false because it requires continuous capture.
Its native preparation result and snapshot/status already show the correct state.
A fresh stdio session loads the new readiness logic and returns true. Refresh MCP
or open a new chat before relying on the updated startup arguments/default.

Automated checks cover screenshot cancellation, stale-session rejection, sanitized
errors, single-request behavior, screenshot readiness without video, explicit
legacy mode and native geometry changes that block stale touch coordinates.
Native API integration tests pass. Real phone rotation and input effects were not
tested; wireless on-demand screenshots are unsupported.

Review verification also rebuilt the app and screenshot bridge end to end using
scripts/build-ondemand-runtime.ps1 under Windows PowerShell 5.1. The native API
suite includes an in-flight snapshot regression: a later touch must request a
new still image and reject geometry changed by that image before dispatch.
Mode switching retires the standalone USB control claim before video startup;
still-image responses cannot publish geometry after their capture mode or bridge
instance changes. The Python suite contains 70 passing tests; pip check,
PowerShell syntax/checksum checks and Python package builds pass.

Bootstrap/setup explicitly default to continuous mode for the published runtime,
while -CaptureMode on_demand selects patched-runtime installation. This preserves
fresh installation compatibility without changing the MCP tool's on_demand default
or silently falling back when a user requests still images.

Rebuild instructions are in [the runtime source guide](../runtime-patches/README.md#on-demand-screenshots-and-direct-control).
