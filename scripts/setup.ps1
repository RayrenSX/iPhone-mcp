[CmdletBinding()]
param(
    [string]$Python,
    [string]$MirrorPath,
    [switch]$EnableAutomationApi,
    [switch]$SkipCodex,
    [switch]$SkipDoctor
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
if ($env:OS -ne 'Windows_NT') { throw 'This setup requires Windows 10/11 x64.' }

function Run-Checked([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Command" }
}

if ($MirrorPath) {
    $mirrorExe = (Resolve-Path -LiteralPath $MirrorPath).Path
    if (-not (Get-Process iPhoneMirror -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $mirrorExe -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }
}
if ($EnableAutomationApi) { & "$PSScriptRoot/enable-api.ps1" }

$venvPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    if ($Python) {
        $pythonExe = (Get-Command $Python -ErrorAction Stop).Source
    } else {
        $pythonExe = $null
        foreach ($candidate in @('py', 'python', 'python3')) {
            $found = Get-Command $candidate -ErrorAction SilentlyContinue
            if (-not $found) { continue }
            $resolved = & $found.Source -c 'import sys; print(sys.executable) if sys.version_info >= (3, 11) else sys.exit(1)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path -LiteralPath "$resolved")) {
                $pythonExe = "$resolved"; break
            }
        }
        if (-not $pythonExe) { throw 'Install Python 3.11+ (recommended 3.13), then rerun. See docs/SETUP.md.' }
    }
    Run-Checked $pythonExe @('-c', 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"')
    Run-Checked $pythonExe @('-m', 'venv', (Join-Path $repoRoot '.venv'))
}
Run-Checked $venvPython @('-m', 'pip', 'install', '-e', $repoRoot)
Run-Checked $venvPython @('-m', 'pip', 'check')

$artifactDir = Join-Path $repoRoot 'artifacts'
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
$config = @{ mcpServers = @{ 'iphone-mcp' = @{ command = $venvPython; args = @('-m', 'iphonemirror_mcp', '--local-key-store') } } }
$config | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $artifactDir 'mcp-config.json') -Encoding UTF8
if (-not $SkipCodex) {
    $codexExe = (Get-Command codex -ErrorAction Stop).Source
    Run-Checked $codexExe @('mcp', 'add', 'iphone-mcp', '--', $venvPython, '-m', 'iphonemirror_mcp', '--local-key-store')
}
Write-Host 'MCP configured. Generated artifacts/mcp-config.json for other clients. Open a new Codex session.'
if (-not $SkipDoctor) {
    & $venvPython "$PSScriptRoot/doctor.py"
    if ($LASTEXITCODE -ne 0) { throw 'Configured, but device validation failed. Follow docs/SETUP.md and rerun doctor.py.' }
}
