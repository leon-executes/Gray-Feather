# Gray Feather build packaging — Parham (Leon) Faraji / leon-executes
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
param([string]$Python = '', [switch]$SkipInstall, [string]$BuildPython = '', [string]$PortableName = 'Portable')
$ErrorActionPreference = 'Stop'
$Project = $PSScriptRoot
if ($PortableName -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') { throw 'Choose a simple portable folder name.' }
$EnvironmentPython = if ($BuildPython) { (Resolve-Path -LiteralPath $BuildPython).Path } else { Join-Path $Project '.build-env/Scripts/python.exe' }
$TaskTemp = Join-Path $Project '.build-temp'
New-Item -ItemType Directory -Force -Path $TaskTemp | Out-Null
$env:TEMP = $TaskTemp
$env:TMP = $TaskTemp
if (-not (Test-Path -LiteralPath $EnvironmentPython)) {
    if (-not $Python) { throw 'Pass -Python with a CPython 3.12 x64 executable for the development build.' }
    & $Python -m venv (Join-Path $Project '.build-env')
    if ($LASTEXITCODE -ne 0) { throw 'Build environment creation failed.' }
}
# Prevent unrelated development tools (for example Poppler's private ICU) from
# shadowing the Windows ICU libraries used by Qt during dependency collection.
$BasePython = & $EnvironmentPython -c 'import sys; print(sys.base_prefix)'
$env:PATH = (Split-Path -Parent $EnvironmentPython) + ';' + $BasePython + ';' + (Join-Path $env:WINDIR 'System32') + ';' + $env:WINDIR
if (-not $SkipInstall) {
    & $EnvironmentPython -m pip install --disable-pip-version-check -r (Join-Path $Project 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$Reports = Join-Path $Project 'verification'
& $EnvironmentPython (Join-Path $Project 'tools/fetch_speech_resources.py')
if ($LASTEXITCODE -ne 0) { throw 'Bundled speech resources could not be verified.' }
& $EnvironmentPython (Join-Path $Project 'tools/verify_bundled_assets.py')
if ($LASTEXITCODE -ne 0) { throw 'Bundled native assets could not be verified.' }
New-Item -ItemType Directory -Force -Path $Reports | Out-Null
& $EnvironmentPython (Join-Path $Project 'app.py') --self-test --data-dir (Join-Path $TaskTemp 'source-test-data') --report (Join-Path $Reports 'source-tests.json')
if ($LASTEXITCODE -ne 0) { throw 'Source tests failed.' }
& $EnvironmentPython (Join-Path $Project 'tools/make_icon.py')
if ($LASTEXITCODE -ne 0) { throw 'Icon build failed.' }
& $EnvironmentPython (Join-Path $Project 'tools/release_identity.py')
if ($LASTEXITCODE -ne 0) { throw 'Source snapshot failed.' }
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Stage = Join-Path $Project ('.build-stage-' + $Stamp)
& $EnvironmentPython -m PyInstaller --noconfirm --clean --onedir --windowed --name GrayFeather --icon (Join-Path $Project 'grayfeather.ico') --add-data ((Join-Path $Project 'grayfeather.png') + ';.') --add-data ((Join-Path $Project 'resources') + ';resources') --add-data ((Join-Path $Project 'language_routes.json') + ';.') --add-data ((Join-Path $Project 'verification/historical-critical-regressions.json') + ';verification') --hidden-import tests.test_reinforcement --hidden-import tests.test_reinforced_engine --hidden-import tests.test_translation_removal --hidden-import tests.test_offline_voice --hidden-import tests.test_index_engine --hidden-import tests.test_speech_hotfix --hidden-import tests.test_voice_reserve --hidden-import tests.test_offline_omni --hidden-import tests.test_engine --hidden-import tests.test_app --hidden-import tests.test_app_extra --hidden-import tests.test_ui --hidden-import tests.test_ui_ux --hidden-import tests.test_ui_storage --hidden-import tests.test_ui_speech_integration --hidden-import tests.test_speech_model_policy --hidden-import tests.test_workflow_service --hidden-import tests.test_live_speech --hidden-import tests.test_free_speech --hidden-import tests.live_benchmark --hidden-import tests.language_corpus_check --hidden-import win32com.client --hidden-import pythoncom --hidden-import _cffi_backend --collect-data certifi --exclude-module numpy --exclude-module tkinter --exclude-module PySide6.QtNetwork --distpath $Stage --workpath (Join-Path $TaskTemp ('pyinstaller-' + $Stamp)) --specpath $TaskTemp (Join-Path $Project 'app.py')
if ($LASTEXITCODE -ne 0) { throw 'Portable packaging failed.' }
$StagedApp = Join-Path $Stage 'GrayFeather'
& $EnvironmentPython (Join-Path $Project 'tools/trim_portable.py') $StagedApp --report (Join-Path $Reports 'portable-trim.json')
if ($LASTEXITCODE -ne 0) { throw 'Portable trim verification failed.' }
$Exe = Join-Path $StagedApp 'GrayFeather.exe'
& $EnvironmentPython (Join-Path $Project 'tools/release_identity.py') --executable $Exe
if ($LASTEXITCODE -ne 0) { throw 'Build source identity failed.' }
$PackagedReport = Join-Path $Reports 'packaged-tests.json'
$Process = Start-Process -FilePath $Exe -ArgumentList @('--self-test','--data-dir',('"' + (Join-Path $TaskTemp 'packaged-test-data') + '"'),'--report',('"' + $PackagedReport + '"')) -WindowStyle Hidden -Wait -PassThru
if ($Process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $PackagedReport)) { throw 'Packaged executable tests failed.' }
if (-not (Get-Content -LiteralPath $PackagedReport -Raw | ConvertFrom-Json).successful) { throw 'Packaged executable reported failed tests.' }
$PackagedUiReport = Join-Path $Reports 'packaged-ui.json'
$UiProcess = Start-Process -FilePath $Exe -ArgumentList @('--ui-smoke','--data-dir',('"' + (Join-Path $TaskTemp 'packaged-ui-data') + '"'),'--report',('"' + $PackagedUiReport + '"')) -WindowStyle Hidden -Wait -PassThru
if ($UiProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $PackagedUiReport)) { throw 'Packaged native interface check failed.' }
if (-not (Get-Content -LiteralPath $PackagedUiReport -Raw | ConvertFrom-Json).successful) { throw 'Packaged native interface reported a failed check.' }
foreach ($Name in @('README.md','LICENSE','NOTICE','AUTHORS.md','DEPENDENCIES.md','BUILD.md','CHANGELOG.md','THIRD-PARTY-NOTICES.md','APP-CAPABILITIES.csv')) {
    Copy-Item -LiteralPath (Join-Path $Project $Name) -Destination $StagedApp
}
foreach ($DocFolder in @('docs','assets','packaging')) {
    Copy-Item -LiteralPath (Join-Path $Project $DocFolder) -Destination (Join-Path $StagedApp $DocFolder) -Recurse
}
Copy-Item -LiteralPath (Join-Path $Project 'licenses') -Destination (Join-Path $StagedApp 'licenses') -Recurse
# Corresponding sources ship in the same release as a separate developer archive.
$SourceRoot = Join-Path $Project 'runtime-source'
foreach ($SourceFile in (Get-ChildItem -LiteralPath $SourceRoot -File -Recurse)) {
    if ($SourceFile.Name -match '\.tar\.(gz|xz)$') { continue }
    $RelativeSource = $SourceFile.FullName.Substring($SourceRoot.Length).TrimStart('\','/')
    $SourceTarget = Join-Path (Join-Path $StagedApp 'runtime-source') $RelativeSource
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $SourceTarget) | Out-Null
    Copy-Item -LiteralPath $SourceFile.FullName -Destination $SourceTarget
}
$PortableReports = Join-Path $StagedApp 'verification'
New-Item -ItemType Directory -Path $PortableReports -Force | Out-Null
foreach ($Name in @('source-tests.json','packaged-tests.json','packaged-ui.json','gap-validation-20261012.md','gap-validation-summary.json','dari-voice-comparison.json','portable-voice-checks.json')) {
    Copy-Item -LiteralPath (Join-Path $Reports $Name) -Destination $PortableReports
}
$Portable = Join-Path $Project $PortableName
if (Test-Path -LiteralPath $Portable) { throw ('Existing Portable folder is preserved. Verified new build is at ' + $StagedApp) }
$ResolvedProject = [System.IO.Path]::GetFullPath($Project).TrimEnd('\') + '\'
$ResolvedStage = (Resolve-Path -LiteralPath $StagedApp).Path
$ResolvedPortable = [System.IO.Path]::GetFullPath($Portable)
if (-not $ResolvedStage.StartsWith($ResolvedProject, [System.StringComparison]::OrdinalIgnoreCase) -or -not $ResolvedPortable.StartsWith($ResolvedProject, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Build target paths escaped the project folder.' }
Move-Item -LiteralPath $StagedApp -Destination $Portable
Write-Output ('Verified portable application: ' + (Join-Path $Portable 'GrayFeather.exe'))

