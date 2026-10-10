[CmdletBinding()]
param(
    [string]$Python,
    [string]$MirrorPath,
    [string]$Proxy,
    [switch]$SkipCodex,
    [switch]$SkipDoctor,
    [switch]$OpenDriverManager
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Bootstrap requires Windows 10/11 x64.' }
$repoRoot = Split-Path $PSScriptRoot -Parent
$setupArgs = @{ EnableAutomationApi = $true }
if ($SkipCodex) { $setupArgs.SkipCodex = $true }
if ($SkipDoctor) { $setupArgs.SkipDoctor = $true }
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
Write-Host 'First device setup: connect/unlock/trust the phone, install USB drivers in the Driver manager, start capture, and enable wired control for input.'
Write-Host 'Driver installation may require UAC. Wired control may require Developer Mode and an iOS restart. These prompts need human interaction.'
if ($OpenDriverManager) {
    $driverExe = Join-Path (Split-Path $MirrorPath -Parent) 'iPhoneMirror.Driver.exe'
    if (-not (Test-Path -LiteralPath $driverExe)) { throw 'Driver manager not found next to the main program.' }
    # The user explicitly requested an interactive driver window with this switch.
    Start-Process -FilePath $driverExe
}
& "$PSScriptRoot/setup.ps1" @setupArgs
