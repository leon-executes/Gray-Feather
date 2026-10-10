# Publish on GitHub

## Repository

Prepared owner/name: **leon-executes/Gray-Feather**. If you choose another repository name, update the GitHub links before uploading. No repository or release has been published by this preparation.

1. Create an empty public repository named `Gray-Feather`. Do not generate another licence or README.
2. Upload the contents of the prepared `GitHub` folder, including hidden `.gitignore`, `.gitattributes` and `.github` files. Or use Git:

```powershell
git init -b main
git add .
git commit -m "Prepare Gray Feather 1.3.0 for GitHub"
git remote add origin https://github.com/leon-executes/Gray-Feather.git
git push -u origin main
```

3. About description: **Portable Windows translation for two speakers. Free online engines, optional offline AI, speech and local history.**
4. Suggested topics: `windows`, `translation`, `speech-recognition`, `text-to-speech`, `portable`, `pyside6`, `offline-translation`.

## Release

Create release tag **v1.3.0** from the uploaded source. Use [release notes](RELEASE-NOTES.md). Attach these files from the application's `dist` folder:

- `GrayFeather-1.3.0-GitHub-Windows-x64.zip` — users download this.
- `GrayFeather-1.3.0-GitHub-Source.zip` — clean application source.
- `GrayFeather-1.3.0-ThirdParty-Sources.zip` — corresponding upstream source collection.
- `GrayFeather-1.3.0-GitHub-SHA256SUMS.txt` — download checksums.

Upload the third-party source asset with the portable release. It contains the ONNX Runtime source archive moved out of the portable ZIP, plus the complete supplied native-source collection. It is not another user installation step.

The original 1.3.0 portable ZIP is over GitHub's documented 2 GiB per-asset limit. Use the newly prepared GitHub ZIP; do not upload the old archive or model weights into the Git tree. [GitHub release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas).

Before publishing: run `python tools/check_repository.py`, confirm the archive checksums and preview the README. The banner is replaceable at [assets/banner.svg](../assets/banner.svg); see [artwork instructions](../assets/README.md).

Application licence: **PolyForm Noncommercial 1.0.0**, source-available. Keep that wording; do not describe the application licence as OSI-approved open source. Third-party licences remain separate.
