[CmdletBinding()]
param(
    [string]$Python,
    [string]$MirrorPath,
    [string]$Proxy,
    [switch]$SkipCodex,
    [switch]$SkipDoctor,
    [switch]$OpenDriverManager,
    [switch]$SkipDrivers
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Bootstrap requires Windows 10/11 x64.' }
$repoRoot = Split-Path $PSScriptRoot -Parent
$setupArgs = @{ EnableAutomationApi = $true }
if ($SkipCodex) { $setupArgs.SkipCodex = $true }
$setupArgs.SkipDoctor = $true
if ($OpenDriverManager) { throw 'GUI driver setup was removed. Run bootstrap without -OpenDriverManager for headless setup.' }
if (-not $SkipCodex -and -not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw 'Codex CLI not found. Use -SkipCodex for another MCP client, or install Codex CLI first; see docs/SETUP.md.'
}
if (-not $Python -and -not (Test-Path -LiteralPath (Join-Path $repoRoot '.venv/Scripts/python.exe'))) {
    foreach ($candidate in @('py', 'python', 'python3')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $resolved = & $command.Source -c 'import sys; print(sys.executable) if sys.version_info >= (3,11) else sys.exit(1)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path -LiteralPath "$resolved")) { $Python = "$resolved"; break }
    }
    if (-not $Python) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) { throw 'Python 3.11+ and winget are unavailable. Install Python 3.13 and rerun with -Python <python.exe>.' }
        & $winget.Source install --exact --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Python installation failed; install Python 3.13 manually or specify -Python.' }
        $Python = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python313/python.exe'
        if (-not (Test-Path -LiteralPath $Python)) { throw 'Python installed at an unexpected path. Rerun with -Python <actual-path>.' }
    }
}
if ($Python) { $setupArgs.Python = $Python }
$running = @(Get-Process iPhoneMirror -ErrorAction SilentlyContinue)
if ($MirrorPath) {
    $setupArgs.MirrorPath = $MirrorPath
} elseif ($running.Count -gt 0) {
    $MirrorPath = $running[0].Path
    if (-not (Test-Path -LiteralPath (Join-Path (Split-Path $MirrorPath -Parent) 'mcp-runtime.json'))) {
        throw 'An older iPhoneMirror is running. Close it normally and rerun bootstrap to install the background runtime.'
    }
    Write-Host 'Using the running MCP-compatible iPhoneMirror.'
    $setupArgs.MirrorPath = $MirrorPath
} else {
    $runtimeArgs = @{}
    if ($Proxy) { $runtimeArgs.Proxy = $Proxy }
    $MirrorPath = & "$PSScriptRoot/install-runtime.ps1" @runtimeArgs
    $setupArgs.MirrorPath = $MirrorPath
}
& "$PSScriptRoot/setup.ps1" @setupArgs
if (-not $SkipDrivers) {
    $driverArgs = @("$PSScriptRoot/setup-drivers.py")
    if ($Proxy) { $driverArgs += @('--proxy', $Proxy) }
    & (Join-Path $repoRoot '.venv/Scripts/python.exe') @driverArgs
    if ($LASTEXITCODE -ne 0) { throw 'Driver setup requires action. Read the JSON actionRequired above, complete it and rerun; never retry an unknown transaction.' }
}
if (-not $SkipDoctor) {
    & (Join-Path $repoRoot '.venv/Scripts/python.exe') "$PSScriptRoot/start-runtime.py"
    if ($LASTEXITCODE -ne 0) { throw 'Background preparation requires action; see the MCP response.' }
    & (Join-Path $repoRoot '.venv/Scripts/python.exe') "$PSScriptRoot/doctor.py"
    if ($LASTEXITCODE -ne 0) { throw 'Device verification failed; see docs/SETUP.md.' }
}
