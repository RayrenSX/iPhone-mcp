[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourcePath,
    [Parameter(Mandatory)][string]$BaseRuntimePath,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$sourceRoot = (Resolve-Path -LiteralPath $SourcePath).Path
$baseRuntime = (Resolve-Path -LiteralPath $BaseRuntimePath).Path
$outputRoot = [IO.Path]::GetFullPath($OutputPath)
$patchRoot = Join-Path $repoRoot 'runtime-patches'
if (Test-Path -LiteralPath $outputRoot) { throw 'OutputPath must be a new directory.' }
if (-not (Test-Path -LiteralPath (Join-Path $baseRuntime 'mcp-runtime.json'))) { throw 'Select the complete runtime-v0.2.1 app folder.' }
foreach ($name in @('iPhoneMirror.Core.dll', 'iPhoneMirror.UsbConfigurationSwitch.exe', 'libusb-1.0.dll', 'libusb0.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $baseRuntime $name))) { throw "Base runtime is incomplete: missing $name. Select a complete working app installation." }
}
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot 'src/App/MainWindow.AutomationManagement.cs'))) { throw 'Select the complete runtime-v0.2.1 corresponding source.' }

function Run-Checked([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Command" }
}

$nativePatch = Join-Path $patchRoot 'iphonemirror-ondemand.patch'
function Test-Patch([switch]$Reverse) {
    $previousPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 treats redirected git stderr as errors even
        # for an expected nonzero --check; let the exit code decide the result.
        $ErrorActionPreference = 'Continue'
        $checkArgs = @('-C', $sourceRoot, 'apply', '--check', '--ignore-space-change')
        if ($Reverse) { $checkArgs += '--reverse' }
        & git @checkArgs $nativePatch 2>$null
        return $LASTEXITCODE -eq 0
    } finally { $ErrorActionPreference = $previousPreference }
}
if (Test-Patch) {
    Run-Checked git @('-C', $sourceRoot, 'apply', '--ignore-space-change', $nativePatch)
} else {
    if (-not (Test-Patch -Reverse)) { throw 'Source does not match the on-demand patch or already contains partial changes.' }
}
Copy-Item -LiteralPath (Join-Path $patchRoot 'ondemand_screenshot.py') -Destination (Join-Path $sourceRoot 'tools/ondemand_screenshot.py')
New-Item -ItemType Directory -Path $outputRoot | Out-Null
$appOutput = Join-Path $outputRoot 'app'
$toolOutput = Join-Path $appOutput 'tools'
New-Item -ItemType Directory -Path $toolOutput -Force | Out-Null
# Preserve the complete driver/native payload, without mixing old Python DLLs
# into the newly packaged bridge. No existing runtime is modified or removed.
foreach ($entry in Get-ChildItem -LiteralPath $baseRuntime) {
    if ($entry.Name -ne 'tools') { Copy-Item -LiteralPath $entry.FullName -Destination $appOutput -Recurse }
}
foreach ($entry in Get-ChildItem -LiteralPath (Join-Path $baseRuntime 'tools')) {
    if ($entry.Name -notin @('_internal', 'iUsbBridge.exe', 'iUsbBridge.runtime.json')) {
        Copy-Item -LiteralPath $entry.FullName -Destination $toolOutput -Recurse
    }
}
$nativeLibraries = Join-Path $sourceRoot 'third_party/airplay-server/bin/x64'
New-Item -ItemType Directory -Path $nativeLibraries -Force | Out-Null
foreach ($name in @('airplay2dll.dll', 'avcodec-58.dll', 'avutil-56.dll', 'swresample-3.dll', 'swscale-5.dll')) {
    Copy-Item -LiteralPath (Join-Path $baseRuntime "Wireless/$name") -Destination (Join-Path $nativeLibraries $name)
}
Run-Checked $Python @('-m', 'pip', 'install', '-r', (Join-Path $patchRoot 'requirements-ondemand.txt'))
$previousSourceRoot = $env:IPHONEMIRROR_SOURCE_ROOT
try {
    $env:IPHONEMIRROR_SOURCE_ROOT = $sourceRoot
    Run-Checked $Python @('-m', 'PyInstaller', '--noconfirm', '--distpath', (Join-Path $outputRoot 'bridge'),
        '--workpath', (Join-Path $outputRoot 'bridge-build'), (Join-Path $patchRoot 'iUsbBridge-ondemand.spec'))
} finally { $env:IPHONEMIRROR_SOURCE_ROOT = $previousSourceRoot }
$bridgeOutput = Join-Path $outputRoot 'bridge/iUsbBridge'
Copy-Item -LiteralPath (Join-Path $bridgeOutput 'iUsbBridge.exe') -Destination $toolOutput
Copy-Item -LiteralPath (Join-Path $bridgeOutput '_internal') -Destination $toolOutput -Recurse
$bridgeFiles = @(Get-ChildItem -LiteralPath $bridgeOutput -Recurse -File | Sort-Object FullName | ForEach-Object {
    @{ path = $_.FullName.Substring($bridgeOutput.Length + 1).Replace('\', '/'); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
})
$bridgeManifest = @{ schema = 1; files = $bridgeFiles } | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $toolOutput 'iUsbBridge.runtime.json'), $bridgeManifest, [Text.UTF8Encoding]::new($false))
$nativeOutput = Join-Path $outputRoot 'native'
Push-Location $sourceRoot
try {
    Run-Checked dotnet @('publish', 'src/App/iPhoneMirror.App.csproj', '-c', 'Release', '-o', $nativeOutput,
        "-p:UsbBridgeRoot=$toolOutput", '-p:IncludeBundledFfmpeg=false')
    Run-Checked dotnet @('run', '--project', 'src/App.Runtime.Tests/iPhoneMirror.App.Runtime.Tests.csproj',
        '-c', 'Release', "-p:UsbBridgeRoot=$toolOutput", '--', '--automation-api')
} finally { Pop-Location }
Copy-Item -LiteralPath (Join-Path $nativeOutput 'iPhoneMirror.exe') -Destination (Join-Path $appOutput 'iPhoneMirror.exe') -Force
$marker = Get-Content -LiteralPath (Join-Path $baseRuntime 'mcp-runtime.json') -Raw | ConvertFrom-Json
$marker | Add-Member -NotePropertyName onDemandCaptureVersion -NotePropertyValue 1 -Force
[IO.File]::WriteAllText((Join-Path $appOutput 'mcp-runtime.json'), ($marker | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
Write-Host "Built and tested on-demand runtime: $appOutput"
Write-Host 'Close the previous app normally, then select this app with scripts/setup.ps1 -MirrorPath <app/iPhoneMirror.exe> -CaptureMode on_demand.'
