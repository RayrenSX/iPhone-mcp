# Background device runtime source

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
