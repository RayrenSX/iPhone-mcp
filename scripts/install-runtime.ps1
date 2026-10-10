[CmdletBinding()]
param(
    [string]$TargetDirectory = (Join-Path $env:LOCALAPPDATA 'iPhone-mcp/runtime/v0.2.1'),
    [string]$Proxy
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
. "$PSScriptRoot/runtime-common.ps1"
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
    throw 'The device runtime requires Windows 10/11 x64; ARM64 is not supported.'
}
$releaseTag = 'runtime-v0.2.1'
$assetName = 'iPhoneMirror-mcp-runtime-v0.2.1-win-x64.zip'
$releaseUrl = "https://github.com/RayrenSX/iPhone-mcp/releases/download/$releaseTag"
$destination = [IO.Path]::GetFullPath($TargetDirectory)
$receiptPath = Join-Path $destination 'install-receipt.json'
if (Test-Path -LiteralPath $receiptPath) {
    $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    $existingExe = Join-Path $destination 'app/iPhoneMirror.exe'
    if ($receipt.releaseTag -eq $releaseTag -and (Test-Path -LiteralPath $existingExe) -and (Test-Path -LiteralPath (Join-Path $destination 'app/iPhoneMirror.Driver.exe'))) {
        Write-Host "Using downloaded runtime $releaseTag."
        return $existingExe
    }
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
function Get-RuntimeFile([string]$Uri, [string]$OutputPath) {
    $curl = Get-Command curl.exe -ErrorAction Stop
    $common = @('--fail', '--location', '--silent', '--show-error', '--connect-timeout', '15', '--max-time', '900', '--speed-limit', '1024', '--speed-time', '60', '--output', $OutputPath)
    & $curl.Source @common --noproxy '*' $Uri
    if ($LASTEXITCODE -eq 0) { return }
    if (-not $Proxy) { throw 'Direct runtime download failed. Supply -Proxy for fallback if needed.' }
    Write-Host 'Direct download failed; retrying through the supplied proxy.'
    & $curl.Source @common --proxy $Proxy --noproxy '' $Uri
    if ($LASTEXITCODE -ne 0) { throw 'Runtime download failed through both direct and proxy routes.' }
}
Write-Host "Downloading iPhone-mcp background runtime $releaseTag; no drivers are changed."
$manifestPath = Join-Path $destination ('manifest-' + [guid]::NewGuid().ToString('N') + '.txt')
Get-RuntimeFile "$releaseUrl/SHA256SUMS.txt" $manifestPath
$manifest = Get-Content -LiteralPath $manifestPath -Raw
$expected = Get-ReleaseChecksum "$manifest" $assetName
$archivePath = Join-Path $destination $assetName
if (-not (Test-Path -LiteralPath $archivePath) -or (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $expected) {
    $temporaryPath = "$archivePath.download"
    Get-RuntimeFile "$releaseUrl/$assetName" $temporaryPath
    Test-ReleaseChecksum $temporaryPath $expected | Out-Null
    Move-Item -LiteralPath $temporaryPath -Destination $archivePath -Force
}
$actual = Test-ReleaseChecksum $archivePath $expected
Unblock-File -LiteralPath $archivePath
# Extract into a new directory on every attempt. Never delete an existing installation.
$extractPath = Join-Path $destination ('extract-' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $archivePath -DestinationPath $extractPath
$executables = @(Get-ChildItem -LiteralPath $extractPath -Recurse -Filter iPhoneMirror.exe)
if ($executables.Count -ne 1) { throw 'The official archive must contain exactly one iPhoneMirror.exe.' }
$appPath = Join-Path $destination 'app'
if (Test-Path -LiteralPath $appPath) { throw 'An incomplete/existing app directory is present. Choose another -TargetDirectory; existing files were preserved.' }
Move-Item -LiteralPath $executables[0].Directory.FullName -Destination $appPath
$exe = Join-Path $appPath 'iPhoneMirror.exe'
if (-not (Test-Path -LiteralPath (Join-Path $appPath 'iPhoneMirror.Driver.exe'))) { throw 'Driver manager missing from runtime.' }
@{ releaseTag = $releaseTag; sha256 = $actual; source = "$releaseUrl/$assetName" } |
    ConvertTo-Json | Set-Content -LiteralPath $receiptPath -Encoding UTF8
Write-Host 'Runtime downloaded and checksum verified. Run headless driver setup and follow its actionRequired results.'
return $exe
