# Build

## Prepare

1. Install [CPython 3.12 x64](https://www.python.org/downloads/windows/).
2. Clone or extract this repository. Work in its root directory.
3. Download and extract the [Windows portable release](https://github.com/leon-executes/Gray-Feather/releases/latest). Also download `GrayFeather-1.3.0-ThirdParty-Sources.zip` from that release.
4. Restore the pinned assets. Replace the example paths below with your actual locations:

```powershell
py -3.12 tools/prepare_assets.py --portable "C:\Downloads\GrayFeather" --sources "C:\Downloads\GrayFeather-1.3.0-ThirdParty-Sources.zip"
```

The helper copies resources from the portable release and restores the corresponding-source collection. It checks every file against the repository's [asset manifest](packaging/assets-manifest.json). It refuses changed existing files rather than overwriting them. It makes no network requests and does not read your conversation data. Model downloads are deliberately outside Git; Git LFS is not required.

## Build the portable app

```powershell
.\build.ps1 -Python (py -3.12 -c "import sys; print(sys.executable)")
```

Use a writable folder with room for the resource packs, build environment and a second packaged copy. The script installs pinned build dependencies, checks assets, runs source tests, builds the app and checks the packaged executable and native window. Output: `Portable\GrayFeather.exe`. Reports: `verification\`.

An existing `Portable` folder is preserved. Choose a new output name when rebuilding:

```powershell
.\build.ps1 -Python (py -3.12 -c "import sys; print(sys.executable)") -PortableName Portable-New
```

PowerShell may require you to unblock downloaded scripts according to your machine's policy. The finished release needs no Python installation. Rebuilding does not promise a byte-identical executable across toolchains or hosts.

## Run source / checks

After the build environment and assets are ready:

```powershell
.\.build-env\Scripts\python.exe app.py --data-dir .\development-data
.\.build-env\Scripts\python.exe app.py --self-test --data-dir .\test-data --report .\verification\source-tests.json
.\.build-env\Scripts\python.exe tools\check_repository.py
```

`--self-test` uses synthetic data and mocked services. It measures software behavior, not translation accuracy. `--native-self-test` additionally exercises the actual bundled local engines. Live speech/language checks contact external services; see [verification](docs/VERIFICATION.md).

## Prepare GitHub release assets

After the executable has passed its checks and its release identity is current:

```powershell
.\.build-env\Scripts\python.exe tools\package_release.py --portable .\Portable --output .\dist
```

This validates source/executable identity and all pinned resources, then writes the portable ZIP, clean source ZIP, third-party source ZIP and checksums. Existing output files are preserved. Each release asset must be below 2 GiB. The repository-file allowlist is in `packaging/repository-files.json`; update it when intentionally adding source files. See [publishing](docs/PUBLISH.md).

## How the build stays portable

PyInstaller places the native Qt application and its Python dependencies in one folder. Native translation, recognition and voice helpers run as bounded child processes. Model files and DLLs are app-local. No local HTTP service, browser shell, scheduled updater or system-wide model installation is required.

`release_identity.py` records runtime-source hashes and binds them to the built executable. Existing user data is never an input to packaging. Keep the third-party licence texts, replacement-library rights and required source materials with redistributions; see [notices](THIRD-PARTY-NOTICES.md).

Maintained by [Parham (Leon) Faraji](https://github.com/leon-executes).
