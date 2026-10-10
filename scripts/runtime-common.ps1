function Get-ReleaseChecksum([string]$Manifest, [string]$FileName) {
    $pattern = '^(?<hash>[a-fA-F0-9]{64})\s+\*?' + [regex]::Escape($FileName) + '$'
    $matchesFound = @($Manifest -split '\r?\n' | ForEach-Object {
        if ($_ -match $pattern) { $Matches['hash'].ToLowerInvariant() }
    })
    if ($matchesFound.Count -ne 1) { throw "Expected exactly one SHA256 entry for $FileName" }
    return $matchesFound[0]
}

function Test-ReleaseChecksum([string]$Path, [string]$Expected) {
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.ToLowerInvariant()) { throw 'Runtime checksum mismatch; file will not be extracted or executed.' }
    return $actual
}
