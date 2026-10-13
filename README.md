![Gray Feather — interpret forward](https://github.com/user-attachments/assets/088d7f6f-97ae-4e9b-b584-715e4299b8b6)
# Gray Feather

**Reinforced translation, voice and dictation. One portable Windows app.**

[Download](https://github.com/leon-executes/Gray-Feather/releases/latest) · [Dependencies](DEPENDENCIES.md) · [Manual](docs/MANUAL.md) · [Build](BUILD.md) · [Licence](LICENSE)

![Gray Feather — interpret ahead](https://github.com/user-attachments/assets/cc9c591f-48bc-4b73-b226-9782cd770bf3)

## Run

1. Download **GrayFeather-1.4.1-Windows-x64.zip** from [Releases](https://github.com/leon-executes/Gray-Feather/releases/latest).
2. Extract the ZIP to a writable folder. Keep `_internal`, `licenses` and the supplied folders beside `GrayFeather.exe`.
3. Open **GrayFeather.exe**. Choose both languages. Press **Record Speech**, speak, then **Stop recording**. Or type and press **Translate →**.
4. The app completes the translation and reads it when **Voice Enabled** is selected.

Windows 10 version 1903+ or Windows 11, x64. No Python, browser, WebView2, Docker or model installation. All bundled voices and dictation models are included. The app is unsigned. Text translation needs internet; offline text AI has been removed. Free providers can throttle or change availability.

**Upgrading:** close the old app and copy its `GrayFeather-data` folder beside the new executable. Do not overwrite or delete that folder. Source archives are for developers; they are not needed to run the app.

## Use

| Control | Action |
| --- | --- |
| **Record Speech** | See live previews; stop for the final result. |
| **Review** | Inspect alternative translations and backtranslation. |
| **Voice / Listen / Halt Voice** | Control automatic reading, replay or stop. |
| **Safe Speech** | Mask supported profanity/slurs in displayed translations and speech; originals are retained. |
| **Clear Session** | Start fresh and keep the previous session saved. |
| **Saved sessions** | Reopen a session. Tick boxes and choose **Delete selected** to remove several. |
| **Shred History** | Confirm a purge of sessions, drafts, revisions and automatic backups. No in-app Undo. |
| **Export** | Save DOCX, TXT, CSV or JSON. Word is not required. |
| **Settings / Manual** | Apply preferences immediately or read short usage tips. |

**Ctrl+Enter:** translate · **Esc:** cancel/stop voice · **Ctrl+Shift+E:** export · **Ctrl+,** settings.

History stays in `GrayFeather-data`. Separate exports, backups and system snapshots are outside Shred History; SSD forensic erasure cannot be guaranteed. See [privacy](docs/PRIVACY.md) and [language coverage](APP-CAPABILITIES.csv).

## Build and source

Use **CPython 3.12 x64** and the pinned [build dependencies](requirements-build.txt). Restore the release resources, then run `build.ps1`; [BUILD.md](BUILD.md) gives the commands.

Runtime modules sit at the root. `tests/` contains regression tests and explicit live checks; `tools/` contains build, packaging and maintenance commands. Tests do not run during normal app use. They remain available through `GrayFeather.exe --self-test` for support and release verification.

## Engineering

**Reinforcement improves the displayed result.** Automatic mode consults eligible engines within a shared deadline, compares complete translations against the source, and can select a stronger candidate or apply a narrowly supported repair before displaying it. Supported checks cover numbers, signs, currencies, units, identifiers, contact details and calendar terms. A uniquely corrupted email address can be restored from the source; ambiguous repairs are rejected. CLDR month terminology preserves calendar identity rather than silently converting dates. Eligible conflicts can receive an Index AI repair attempt; that candidate must pass the same checks. This repair stage accepts up to 1,200 source characters. Longer passages retain candidate comparison and deterministic checks.

**Routing follows the language and task.** Translation, recognition and voice have separate policies. Dari, Persian, Sorani and Kurmanji keep distinct identities. Independent engine families are distinguished from shared-provider alternatives. Quota responses trigger cooldowns; failed consultations do not discard a completed primary translation. Free-service availability is not guaranteed. Practical substitute voices are identified as approximations, not native-language speech.

**Speech work stays bounded.** Live previews replace stale pending work instead of building a queue. Stopping commits final recognition and translation. Request ownership prevents late results from overwriting new text or another recording. Voice preparation uses bounded reserves and a preference window; one complete result plays. Windows audio completion controls playback so a duration estimate does not cut off the ending.

**Speech resources stay bundled.** The complete download includes Whisper dictation, measured sherpa-onnx recognition routes, a Persian Piper reserve and additional language voice resources. Helpers run on demand with bounded work and checked model hashes. The offline text model and its inference runtime have been removed; online reinforcement and all speech resources remain. Advertised language counts are not proof of reliable coverage.

**Index outages degrade gracefully.** Eligible Google/Bing results still receive complete-candidate comparison and deterministic source-detail repairs. A failed Index consultation is not retried for repair in the same turn. Service failures briefly pause new Index requests, and HTTP 429 honours a bounded cooldown. Cached complete results remain usable. AI rewriting is unavailable while Index is down; no unverified proxy is silently substituted. If all eligible translation routes fail, the original remains available for retry.

**Native interface, local records.** PySide6/Qt provides the desktop UI. SQLite stores sessions, drafts and revisions. Exports preserve Unicode and right-to-left text; DOCX uses ZIP/XML without Microsoft Word. Optional credentials use Windows account-bound protection. History and exports are not encrypted. No local web server, resident model server or background updater is required.

Tests cover software behavior, native execution, cancellation, storage and packaging integrity. They do not certify every translation or accent. Agreement between engines and preserved numbers can still conceal meaning errors. Read the [architecture](docs/ARCHITECTURE.md), [verification](docs/VERIFICATION.md) and [dependency inventory](DEPENDENCIES.md).

## Licence and author

Created by **[Parham (Leon) Faraji](https://github.com/leon-executes)**, from [Forumark's creators](https://forumark.com).

Original code and documentation are source-available under [PolyForm Noncommercial 1.0.0](LICENSE). Third-party code and models retain their [own licences](THIRD-PARTY-NOTICES.md). Corresponding third-party source is supplied as a separate developer archive in the same release; no separate voice download is needed.
