$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../scripts/runtime-common.ps1"
$hash = 'a' * 64
$manifest = "$hash  iPhoneMirror-v1.8.5-pre2-win-x64.zip`n$('b' * 64)  unrelated.zip"
$actual = Get-ReleaseChecksum $manifest 'iPhoneMirror-v1.8.5-pre2-win-x64.zip'
if ($actual -ne $hash) { throw 'Wrong release checksum selected.' }
foreach ($bad in @('', ($manifest + "`n$hash  iPhoneMirror-v1.8.5-pre2-win-x64.zip"), "$hash  iPhoneMirror-v1X8X5-pre2-win-x64Xzip")) {
    $rejected = $false
    try { Get-ReleaseChecksum $bad 'iPhoneMirror-v1.8.5-pre2-win-x64.zip' | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw 'Malformed, missing or duplicate manifest entry was accepted.' }
}
$fixture = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText($fixture, 'fixture')
    $expected = (Get-FileHash -LiteralPath $fixture -Algorithm SHA256).Hash
    Test-ReleaseChecksum $fixture $expected | Out-Null
    [IO.File]::WriteAllText($fixture, 'corrupted')
    $rejected = $false
    try { Test-ReleaseChecksum $fixture $expected | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw 'Corrupt runtime passed checksum verification.' }
} finally { Remove-Item -LiteralPath $fixture }
Write-Host 'Release selection and corrupt-download rejection tests passed.'
