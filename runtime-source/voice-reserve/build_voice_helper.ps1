# Isolated GPL speech helper — Parham (Leon) Faraji.
# End users do not run this script or install Python.
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Build = Join-Path $Root '.voice-build'
New-Item -ItemType Directory -Force -Path $Build | Out-Null
$env:TEMP = $Build
$env:TMP = $Build
$EnvPython = Join-Path $Build 'env/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $EnvPython)) {
    & $Python -m venv (Join-Path $Build 'env')
    if ($LASTEXITCODE -ne 0) { throw 'Voice build environment failed.' }
}
& $EnvPython -m pip install -r (Join-Path $Root 'requirements-voice-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Voice dependencies failed.' }
& $EnvPython -m PyInstaller --noconfirm --clean --onedir --console --name GrayFeatherVoice --collect-data uroman --exclude-module torch --exclude-module transformers --exclude-module scipy --exclude-module onnx --exclude-module pyarrow --distpath (Join-Path $Build 'dist') --workpath (Join-Path $Build 'work') --specpath $Build (Join-Path $Root 'voice_helper.py')
if ($LASTEXITCODE -ne 0) { throw 'Voice worker build failed.' }
$Target = Join-Path $Root 'resources/voice-reserve/helper'
$Parent = Split-Path -Parent $Target
New-Item -ItemType Directory -Force -Path $Parent | Out-Null
if (Test-Path -LiteralPath $Target) {
    $Resolved = (Resolve-Path -LiteralPath $Target).Path
    $ExpectedParent = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $Resolved.StartsWith($ExpectedParent,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected helper path.' }
    $Backup = Join-Path $Build ('previous-helper-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    if (-not ([System.IO.Path]::GetFullPath($Backup)).StartsWith([System.IO.Path]::GetFullPath($Build).TrimEnd('\')+'\',[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected backup path.' }
    Move-Item -LiteralPath $Resolved -Destination $Backup
}
Copy-Item -LiteralPath (Join-Path $Build 'dist/GrayFeatherVoice') -Destination $Target -Recurse
Write-Output ('Built voice helper: ' + $Target)

