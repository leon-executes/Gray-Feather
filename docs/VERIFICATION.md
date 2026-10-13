# Verification

## Release 1.4.1

- **498 source tests passed.** Frozen app: **492 passed**, six source-only packaging tests skipped; those passed from source.
- **9 native checks and 15 speech checks passed**, with a minimal Windows search path. Every retained speech/voice asset matches the preceding release hash.
- **20/20 fresh default translations completed.** Eight more requests with Index deliberately unavailable completed through live fallback services. No second Index repair request was issued after a failed consultation.
- Tests cover Index timeout, service failure, malformed response, throttling/cooldown recovery, failed repair, cancellation, old settings and historical opinions.
- Actual Windows playback completed the full buffer and cancelled promptly. The UI smoke check passed.
- Offline text AI, its weights and inference runtime are absent. Online reinforcement, dictation, voices, history, Safe Speech and exports remain.
- The repository update helper passed dry-run, legacy-file removal, README replacement and dirty-clone protection in a disposable local clone.

These are operational and regression results, not a translation-accuracy percentage or a claim of flawless service availability. Free services, approximate voices and semantic errors remain limitations. The app is unsigned.

[Release evidence](../verification/release-checks-1.4.1.json) · [Live translations](../verification/live-translation-1.4.1.json) · [Index outage evidence](../verification/index-contingency-1.4.1.json) · [Native checks](../verification/native-1.4.1.json) · [Speech checks](../verification/speech-1.4.1.json).

The following versioned results are historical. Offline text translation was removed after 1.4.0.

## Release 1.4.0

- **514 source checks passed.** Packaged executable: **503 passed**, 11 source-only checks skipped.
- **10 actual offline checks passed:** local translation, recognition and neural/basic voice helpers. Native checks ran with a minimal Windows search path after removal of verified redundant DLL copies.
- **15 speech checks passed:** offline and free online recognition, voice preparation, real fallback workers and cancellation. These use synthetic or attributed public audio; no personal microphone recording.
- **20/20 fresh default automatic reinforced free translation requests completed**, including priority languages and three reverse-direction cases. Completion is not a semantic-accuracy score. Outputs and warnings remain in the [live report](../verification/live-translation-1.4.0.json).
- Actual silent Windows playback finished a 0.4-second buffer and cancelled a 2-second buffer promptly. Earlier audio cutoff regressions remain covered.
- Legacy database migration preserves originals and drafts. History deletion, backup races, interrupted backup staging files and purge failures are tested using synthetic data.
- Download assembly is checked byte-for-byte; missing/corrupt parts and conflicting existing ZIPs are rejected. Repository update tooling was checked in a disposable local Git clone.

The app's model weights and language-routing code are unchanged from 1.3.4. The main download is smaller through stronger standard ZIP compression, duplicate private-DLL removal and separate developer source archives. ONNX Runtime source tar contents are identical after XZ recompression. No runtime installer, executable packer or lower-quality model was introduced.

This is release verification on the available Windows x64 PC, not clean-VM certification for every supported Windows/CPU combination. Free-service reliability, approximate voices and language-dependent semantic errors remain. Online dictation can mishear wording even when the request succeeds. The release remains unsigned. Historical findings below stay applicable where not explicitly superseded.

See [release checks](../verification/release-checks-1.4.0.json), [native checks](../verification/native-1.4.0.json), [speech checks](../verification/speech-1.4.0.json) and [compression measurements](../verification/compression-1.4.0.json).

## Check your copy

Compare a download with the release's `GrayFeather-1.4.1-SHA256SUMS.txt`:

```powershell
Get-FileHash .\GrayFeather-1.4.1-Windows-x64.zip -Algorithm SHA256
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


## Speech update · 1.3.1

See [speech coverage](SPEECH-COVERAGE.md) and the [measured gap-validation report](../verification/gap-validation-20261012.md) for current routes, native-reference tests, approximation labels and remaining weaknesses. Earlier version results above remain historical evidence.
