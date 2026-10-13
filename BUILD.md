# Build

Use [CPython 3.12 x64](https://www.python.org/downloads/windows/). End users do not install Python.

## Restore and build

Extract the complete Windows release and download its matching third-party source ZIP. From the repository root:

```powershell
py -3.12 tools/prepare_assets.py --portable "C:/Path/GrayFeather-1.4.1" --sources "C:/Path/GrayFeather-1.4.1-ThirdParty-Sources.zip"
./build.ps1 -Python "C:/Path/Python312/python.exe" -PortableName Portable-1.4.1
```

The restore tool verifies pinned hashes and preserves changed files. The build installs [pinned packages](requirements-build.txt), runs source tests, builds the app, removes verified redundant private DLL copies, then runs packaged tests and a UI check. Existing portable folders are preserved. Keep `GrayFeather-data` out of build inputs.

## Verify

```powershell
./Portable-1.4.1/GrayFeather.exe --self-test --data-dir ./build-check-data --report ./verification/packaged-tests.json
./Portable-1.4.1/GrayFeather.exe --native-self-test --data-dir ./native-check-data --report ./verification/packaged-native.json
```

Regression tests use synthetic fixtures. Native checks execute the actual local models. Live benchmark and speech switches contact free services; see [verification](docs/VERIFICATION.md). `tests/` contains these checks; [tests/README.md](tests/README.md) explains their role.

## Package

```powershell
./.build-env/Scripts/python.exe tools/check_repository.py
./.build-env/Scripts/python.exe tools/package_release.py --portable ./Portable-1.4.1 --output ./dist
```

The default is standard ZIP DEFLATE level 6. Windows Extract All can open it; no extra decompressor, nested archive or model conversion is needed.

Packaging verifies source identity, every model hash and every ZIP entry. It produces the complete app ZIP, repository source ZIP, corresponding third-party source ZIP and checksums. The Windows release fits in one GitHub asset; all voice resources remain included. See [publishing](docs/PUBLISH.md).

## Architecture and helper builds

PyInstaller carries Python, Qt and app-local native helpers. No resident server or automatic model download is used. `tools/release_identity.py` binds runtime, tests and build tools to the executable. Third-party sources remain available in the same release; preserve their [notices](THIRD-PARTY-NOTICES.md).

To rebuild the isolated voice worker, run `tools/build_voice_helper.ps1 -Python "C:/Path/Python312/python.exe"`. Its dependencies are in [requirements-voice-build.txt](requirements-voice-build.txt). Model conversion inputs remain in [runtime-source/voice-reserve](runtime-source/voice-reserve/README.md).

Parham (Leon) Faraji · [leon-executes](https://github.com/leon-executes).
