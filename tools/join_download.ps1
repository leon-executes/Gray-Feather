$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$manifest = @'
DOWNLOAD_MANIFEST
'@ | ConvertFrom-Json
$folder = $PSScriptRoot
$output = Join-Path $folder $manifest.archive
function Hash($path) {
    $reader = [IO.File]::OpenRead($path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { ([BitConverter]::ToString($sha.ComputeHash($reader))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $reader.Dispose() }
}
if (Test-Path -LiteralPath $output) {
    if ((Hash $output) -eq $manifest.sha256) { Write-Host 'Verified ZIP already exists. Extract it and open GrayFeather.exe.'; exit 0 }
    throw 'A different ZIP already exists here. Move it elsewhere first; nothing was overwritten.'
}
foreach ($part in $manifest.parts) {
    $path = Join-Path $folder $part.name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Download missing part: ' + $part.name) }
    if ((Get-Item -LiteralPath $path).Length -ne $part.bytes -or (Hash $path) -ne $part.sha256) { throw ('Damaged download; download again: ' + $part.name) }
}
$temporary = Join-Path $folder ('.grayfeather-join-' + [guid]::NewGuid().ToString('N') + '.tmp')
$created = $false
try {
    $writer = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    $created = $true
    try {
        foreach ($part in $manifest.parts) {
            $reader = [IO.File]::OpenRead((Join-Path $folder $part.name))
            try { $reader.CopyTo($writer, 4194304) } finally { $reader.Dispose() }
        }
        $writer.Flush($true)
    } finally { $writer.Dispose() }
    if ((Hash $temporary) -ne $manifest.sha256) { throw 'Combined ZIP failed verification. Download the parts again.' }
    [IO.File]::Move($temporary, $output)
    Write-Host 'Verified ZIP ready. Extract it and open GrayFeather.exe.'
} finally {
    if ($created -and [IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
}
