# Publish 1.4.1

## Update the repository

Use the prepared **Repository** folder or extract `GrayFeather-1.4.1-Source.zip`. Upload its contents, not the enclosing folder. Do not upload the development app folder, portable binaries or `GrayFeather-data`.

The cleanest update is through GitHub Desktop:

1. Clone `leon-executes/Gray-Feather` into a **new empty folder**. This leaves your working app and data alone.
2. In that fresh clone, keep the hidden `.git` folder. Replace the other repository files with the prepared Repository contents. This removes old root test files as well as adding `tests/` and `tools/`.
3. Review the changes in GitHub Desktop. Commit **Prepare Gray Feather 1.4.1**, then **Push origin**.

Developers can instead run `python tools/stage_github_update.py "C:/Path/FreshClone"`, review its dry-run summary, then repeat with `--apply`. It requires a clean Git clone, removes only the listed old paths, and never commits or pushes.

**README only:** on GitHub, use **Add file → Upload files**, choose the prepared root `README.md`, and commit directly to `main`. The same filename at the same path replaces the existing README. Both published artwork links are already retained. Uploading files alone does not remove old root test files; use Desktop for the complete cleanup.

## Publish the release

1. Create a **new release**, tag **v1.4.1**, target **main**. Keep v1.3.0 available for rollback.
2. Paste [RELEASE-NOTES.md](RELEASE-NOTES.md).
3. Upload **GrayFeather-1.4.1-Windows-x64.zip**. This one file includes every speech resource.
4. Also upload `GrayFeather-1.4.1-Source.zip`, `GrayFeather-1.4.1-ThirdParty-Sources.zip` and `GrayFeather-1.4.1-SHA256SUMS.txt`.
5. Set it as the latest release. Publish after reviewing the [verification report](VERIFICATION.md).

The Windows ZIP fits in one GitHub release asset. Users extract it with Windows **Extract All**.

The third-party source archive is for developers and redistribution compliance; it is not required to run the app. Publish it beside the app ZIP. No remote upload is performed by the packaging tools.
