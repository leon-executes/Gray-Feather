# Gray Feather Desktop · 1.3.0

A portable Windows workspace for two speakers. Free translation, reinforcement, dictation and voice are the main experience. No account or personal API key is required. Originals, drafts and history stay on this PC.

## Start speaking

1. Choose each speaker's language.
2. Press **Record Speech**, speak, then press **Stop recording**. Transcription and translation previews appear while speaking. Provisional previews are never saved as final results.
3. Stop recognizes the complete recording, translates once and reads the result when **Voice Enabled** is selected. Each speaker's source and translation stay together in the same column. The other speaker's language is the destination.
4. You can also type and press **Translate →**. Source words stay visible. A new recording replaces an unchanged last translated source; if you edited it, your words are preserved and the new transcript is appended.
5. **Review** opens complete alternatives and back translation. **Add opinion** requests another unused available route, up to four total results. Each identifies its provider and provenance. Mirrors and MyMemory's mixed sources are not presented as independent engines.

Copy symbols copy the exact visible source or translation. **Listen** reads again. **Halt Voice** stops playback; **Voice Disabled** prevents automatic reading. Incomplete dictation and changed consequential details block automatic reading and show review guidance. Manual playback can require confirmation. Previews are never spoken.

**Clear Session** starts fresh and preserves the previous session in **Saved sessions**. Drafts save automatically; the latest session reopens. Originals, revisions and undo remain recoverable. Retranslation clears stale output immediately so a failed request cannot present old wording as new.

Shortcuts: **Ctrl+Enter** translate the focused speaker; **Alt+1 / Alt+2** focus a speaker; **Ctrl+S** save; **Ctrl+N** clear session; **Ctrl+Shift+E** export; **Ctrl+,** settings; **Esc** cancel a task and stop voice. Stop recording commits capture; Cancel/Esc discards capture or cancels recognition already underway.

## Settings apply immediately

The **Settings / Manual** panel provides concise facts alongside controls. Appearance comes first: Dark/Day and reading size apply immediately. Default reading size is 12 points. Translation, dictation and voice have separate provider choices. Reset keeps history, optional credentials and approved context. DeepL context is collapsed because the free main workflow does not use it.

**Check Windows voices** shows a busy state followed by the discovered count and names, or a clear failure message. An installed voice must match the requested language. Optional account settings do not enable paid calls in Automatic mode.

## Free translation and reinforcement

Automatic translation compares complete free engine outputs before returning the final result. Google, Bing and the official no-key Index Translate AI API provide independent families; MyMemory supplies a further fallback with mixed provenance. Bing remains preferred for English↔Persian and exact Dari. Direction-specific eligibility preserves Dari, Persian, Sorani and Kurmanji identities. No broad engine superiority is inferred from response speed or a few fluent examples. Fragments from different engines are never assembled into a purported complete translation.

Source-based checks automatically repair supported conflicts in the main output: uniquely aligned corrupted contact/reference details, aligned Gregorian months, explicit signed quantities, currency/amount bindings, and narrowly verified Amharic dose and Dutch prohibition contrasts. Index receives source-derived calendar terminology and exact temperature symbols. When a critical discrepancy remains, its source-bound repair candidate is checked before selection. Original wording stays in Review. User glossary/context conditions prevent replacement by unconstrained alternatives. Mere agreement, fluency and back translation cannot establish correctness; arbitrary semantic rewrites remain disabled after trials found regressions. Index online Oromo→English is excluded after eight reference tests returned untranslated Oromo; English→Oromo remains eligible.

The extended corpus contains 204 inputs: six styles across all 34 text languages, plus explicit sense contrasts and a provider evidence registry. These are test inputs and meaning criteria, not invented target-language gold answers. Reports distinguish request completion, provider provenance, fact warnings and semantic review. No completion count is an accuracy percentage.

Automatic translation needs internet. Select **Index 2B · offline AI** to translate locally without uploading text. Its 1.31 GB model and CPU runtime are bundled; no download or installer runs at startup. Native tests used about 2 GB working memory, with bounded CPU threads, a memory guard and cancellable process. The model has known terminology and weaker-language errors, so it is an explicit option rather than an automatic semantic judge. Published coverage is 33 app languages, excluding exact Dari. Free online services can throttle or fail; complete results survive failed optional consultation.

## Dictation and voice

Recording uses native Windows 16 kHz mono PCM with a 50-second limit. Automatic recognition uses bundled **Whisper small-q5_1** first for English and French and bundled **Omnilingual 300M int8** for measured Oromo and Sorani routes. Other supported languages use Google first and an enabled local fallback. Persian uses Google because the tested offline models produced poor wording. Offline choices keep audio on this PC. Online dictation sends audio to its service. Long Omni recordings preserve every PCM sample across bounded segments; a failed segment rejects the entire transcript.

Snapshots use one recognition worker and one replaceable pending snapshot. Stale results cannot overwrite newer text, edited drafts, changed languages or the final turn. Stop cancels preview work and begins complete recognition without waiting for old previews. Full recognition alone decides the saved source. Cadence depends on service and device speed. Private working audio is removed after use; recordings are not stored in history.

Free voice prefers exact-language Microsoft Edge neural speech, then supported Google voice, then an installed exact-language Windows voice. On an actual voice request, supported reserves prepare concurrently within bounded slots. A preferred voice has a short quality grace if another complete route is ready. Actual failures adjust short-lived session ordering. Every chunk is prepared and validated before playback; only one route plays. Stop cancels workers and prevents later fallback playback. A bounded memory cache avoids repeating identical preparation. There are no speculative background text uploads. Azure is attempted only when explicitly selected with credentials.

Coverage: **34 text languages**, **31 automatic dictation mappings**, **30 enabled offline mappings**, **25 Google dictation mappings**, **28 free online voice mappings**. Dari, Tigrinya and Kurmanji still lack a verified dictation route. Free online playback is unavailable for Dari, Tigrinya, Oromo, both Kurdish variants and Sindhi; an exact installed Windows voice may work. Persian now has a bundled Gyro/Piper voice reserve alongside Edge, while recognition remains online. Mapping coverage is separate from measured accuracy. See APP-CAPABILITIES.csv and the current language evidence report.

## Portable launch, data and export

Open **Portable/GrayFeather.exe** in the project folder, or extract the versioned Windows x64 ZIP from dist and open **GrayFeather/GrayFeather.exe**. Move the whole folder including _internal and resources. No Python, browser, WebView2, Qt, Docker, database server, codec pack or model installation is required. This x64 build targets Windows 10 1903 or later and Windows 11. It is unsigned. Offline AI needs sufficient free memory; the default online workflow does not load it.

GrayFeather-data beside the executable holds conversations.sqlite3 and settings.json. Release ZIPs exclude personal data. When upgrading, close the app and retain that data folder. Use --data-dir with another writable local location. Keep the working database off network shares. Optional credentials use Windows account-bound DPAPI; re-enter them after changing accounts or computers. History is ordinary local data, not encrypted by this app.

**Export** supports Word **DOCX**, TXT, CSV and JSON. It snapshots the visible current revision and preserves full Unicode, sources, translations, warnings and attribution. DOCX includes second/additional opinions and back translation with right-to-left paragraphs where appropriate. Export needs no installed Word or additional library. CSV protects against spreadsheet formula execution. Atomic replacement preserves an existing export if writing fails.

**Back up history** creates a verified SQLite copy. Closing after changes keeps the latest two backups in GrayFeather-data/backups. Backups can retain removed conversations. A damaged or newer-schema database is preserved and refused rather than replaced. To restore, close the app, keep a copy of current data and replace conversations.sqlite3 with a verified backup. Leave settings.json intact. Database backups do not include separate credentials; copying the complete data folder while closed preserves both.

No telemetry, account, updater or background model download is included. Network requests follow translation, recording previews/final recognition, listening or enabled automatic voice.

## Verification and development

The publication package includes the release identity and critical regression fixtures in `verification`. The [verification guide](VERIFICATION.md) summarizes software checks, live-test scope and current limitations. The development archive retains the more extensive historical experiments; they are not all copied into this clean repository. Live checks use synthetic or public-domain inputs.

```text
GrayFeather.exe --self-test --report "C:\My Reports\self-test.json"
GrayFeather.exe --native-self-test --report "C:\My Reports\native-models.json"
GrayFeather.exe --diagnose --report "C:\My Reports\diagnostics.json"
GrayFeather.exe --ui-smoke --data-dir "C:\My Test Data" --report "C:\My Reports\ui.json"
GrayFeather.exe --speech-check --data-dir "C:\My Test Data" --report "C:\My Reports\speech.json"
GrayFeather.exe --ui-live-check --data-dir "C:\My Test Data" --report "C:\My Reports\workflow.json"
GrayFeather.exe --all-language-check --data-dir "C:\My Test Data" --report "C:\My Reports\languages.json"
```

The executable writes reports to files. Diagnostics omit keys and transcripts. Self-tests use mocked transports and synthetic data; they make no live calls and certify no accuracy. Native self-test runs the actual bundled translation model, Persian voice and a public Oromo audio fixture without network access or playback. UI smoke briefly opens the native window. Speech and language checks make live free requests. UI live checks inject known cumulative audio instead of microphone input while exercising actual preview/final recognition, translation and voice. Microphone capture is checked separately.

Production boundaries are app.py lifecycle/service, engine.py translation/history, ui.py native Qt workspace, speech.py audio, settings.py protected settings and docx_export.py Word export. Build with CPython 3.12 x64 and pinned requirements-build.txt. build.ps1 validates assets, runs source tests, packages and checks the executable. It preserves an existing Portable folder. Original Gray Feather Translation and Forumark files remain read-only references.

## Version 1.3.0 evidence

The [release identity](../verification/final-build-identity.json) identifies the tested executable and runtime sources. Development evidence includes reference comparisons, critical-domain inputs, targeted repair/control experiments, local-model failures, native recognition/voice tests, cancellation and Unicode relocation. Completion and literal-detail checks are never semantic accuracy percentages. See [verification](VERIFICATION.md) for the later scenario audit and its limits, and [publishing](PUBLISH.md) for the prepared release files.
