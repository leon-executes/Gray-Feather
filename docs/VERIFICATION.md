# Verification

## Check your copy

Compare a download with the release's `GrayFeather-1.3.0-GitHub-SHA256SUMS.txt`:

```powershell
Get-FileHash .\GrayFeather-1.3.0-GitHub-Windows-x64.zip -Algorithm SHA256
```

Run deterministic checks without contacting translation services:

```powershell
.\GrayFeather.exe --self-test --report .\self-test.json
.\GrayFeather.exe --diagnose --report .\diagnostics.json
```

`--native-self-test` runs actual bundled local engines. `--ui-smoke` opens the window briefly. `--speech-check`, `--ui-live-check` and `--all-language-check` perform live requests; they are explicit developer/user actions, not startup work. The manual lists complete commands.

## What is verified

The 1.3.0 application has source and packaged software tests, native-helper checks, speech workflow tests and Unicode relocation evidence. [Release identity](../verification/final-build-identity.json) binds the tested executable to its runtime source hashes. [Historical critical fixtures](../verification/historical-critical-regressions.json) are regression inputs, not proof of general language accuracy.

The GitHub preparation adds licence, documentation, an asset-restoration helper and packaging checks. It preserves the runtime sources, executable, models and native libraries. New archive hashes describe this packaging; they do not reuse the older ZIP's checksum.

## Translation-quality limits

A later scenario audit used the unchanged 1.3.0 default automatic reinforced free pipeline: 215 requests, 114 completed, 101 quota-related failures. The connection had already seen heavy testing. That completion rate is not a normal-user uptime estimate.

Structured model review assessed 113 outputs and left one unscored: 23 contained major errors and four contained critical emergency-information errors. This was not native-speaker certification or a matched comparison against raw engines. It does not establish an industry accuracy percentage or an engine superiority ranking.

Observed issues include kinship/actor changes, technical terminology, some emergency terms and sentence fragments at chunk boundaries. The current splitter can choose a late word-space instead of an earlier sentence boundary. The additional AI-repair step has a 1,200-character source limit. These findings are preserved as limitations; GitHub preparation does not silently change application behavior.

Use the original source and verify consequential content. A correct number, fluent sentence, second opinion or backtranslation is not a meaning guarantee. Speech recognition and playback coverage are separate from text translation coverage.
