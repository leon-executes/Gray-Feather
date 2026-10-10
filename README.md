![Gray Feather — interpret forward](https://github.com/user-attachments/assets/088d7f6f-97ae-4e9b-b584-715e4299b8b6)
# Gray Feather

**Multi-Engine Reinforced Translation with Voice and Dictation in a Portable Windows App.**

[Download](https://github.com/leon-executes/Gray-Feather/releases/latest) · [Dependencies](DEPENDENCIES.md) · [Manual](docs/MANUAL.md) · [Build](BUILD.md) · [Licence](LICENSE)

<!-- Banner slot: replace assets/banner.svg with your final wide artwork. See assets/README.md. -->
![Gray Feather — interpret ahead](https://github.com/user-attachments/assets/cc9c591f-48bc-4b73-b226-9782cd770bf3)


## Run

1. Download **GrayFeather-1.3.0-GitHub-Windows-x64.zip** from Releases. GitHub's automatic **Source code** download is for developers.
2. Extract it to a writable folder. Keep `_internal`, `licenses` and the other supplied folders beside `GrayFeather.exe`.
3. Open **GrayFeather.exe**. Choose both languages. Press **Record Speech**, speak, then **Stop recording**.
4. The app finishes transcription, translates and reads the result when **Voice Enabled** is selected. Or type and press **Translate →**.

Windows 10 version 1903+ or Windows 11, x64. No Python, browser, WebView2, Docker or model installer required. The release is unsigned. Automatic translation uses the internet; **Index 2B · offline AI** is an explicit local option. See [dependencies and language coverage](DEPENDENCIES.md).

## Use

| Control | What it does |
| --- | --- |
| **Record Speech** | Live previews while speaking; one final result when recording stops. |
| **Review** | Inspect alternatives and backtranslation. Add another available opinion. |
| **Listen / Halt Voice** | Read the result again or stop playback. |
| **Voice Enabled / Disabled** | Control automatic reading. |
| **Clear Session** | Start fresh; the previous session remains in Saved sessions. |
| **Export** | Save DOCX, TXT, CSV or JSON. Word is not required. |
| **Settings / Manual** | Change settings immediately or read short usage tips. |

**Ctrl+Enter:** translate · **Esc:** cancel/stop voice · **Ctrl+Shift+E:** export · **Ctrl+,** settings.

History lives in `GrayFeather-data` beside the executable. **Close the app and keep that folder when upgrading.** See [data, backup and privacy](docs/PRIVACY.md). Free services can throttle or fail. Language support differs between text, dictation and voice; [coverage table](APP-CAPABILITIES.csv).

## Build

Use **CPython 3.12 x64**. Restore the pinned resource packs, then run `build.ps1`. The exact commands, asset downloads and verification steps are in [BUILD.md](BUILD.md). Dependencies are pinned in [requirements-build.txt](requirements-build.txt).

## Engineering behind Gray Feather

Gray Feather brings translation, speech recognition, automatic reinforcement, voice playback and local history into a native Windows application. The default workflow uses free online services without requiring a personal API key. Bundled models provide additional offline capabilities without separate runtime installation.

### Reinforcement improves the main result

Automatic mode requests the preferred eligible translation alongside additional consultations within a shared time budget. The reinforcement pipeline evaluates complete translations against the original source, then can select a stronger candidate or apply a narrowly supported correction **before displaying the main result**. Users do not need to inspect the Review pane to receive these improvements.

Checks cover supported patterns involving quantities, explicit positive and negative signs, currencies, units, addresses, identifiers, contact details and calendar terminology. A uniquely identifiable corrupted email address, for example, can be restored from the source when the surrounding protected details remain consistent. Ambiguous mappings are rejected.

Supported Gregorian month corrections use Unicode CLDR terminology without silently converting calendars. Where consequential discrepancies remain, eligible inputs can receive an additional source-based Index AI repair attempt. That candidate must pass the same selection checks before replacing the result. Custom glossary and context conditions also constrain replacement.

The system preserves original wording and alternative results for inspection. It evaluates complete candidates rather than assembling sentences from unrelated engine fragments.

### Routing by language, direction and task

Translation, recognition and playback maintain separate eligibility and preference policies. Support for translating a language does not automatically imply support for recognizing or speaking it.

Translation routes distinguish direction and language identities such as Persian, Dari, Sorani and Kurmanji. Provider provenance matters: Google, Microsoft and Index represent distinct engine families, while mixed-provenance services are not counted as independent confirmation.

Failed routes can fall back to other eligible providers. Quota responses trigger cooldowns; unavailable optional consultations do not discard an otherwise completed primary result. Requests have bounded deadlines, and incomplete responses are rejected rather than presented as finished translations.

### Live speech without a growing processing queue

Recording produces provisional transcription and translation previews. Preview processing uses a replaceable pending snapshot, keeping recent speech useful without accumulating an ever-growing queue.

Stopping recording cancels preview work and requests final recognition. Request ownership checks prevent an obsolete response from overwriting a newer recording, edited text or changed language selection.

Voice playback prepares eligible reserve routes through bounded parallel work. A completed reserve can reduce fallback delay, while a short preference window gives the preferred voice an opportunity to finish. Only one selected result plays. Cancellation prevents abandoned work from producing delayed playback.

### Local intelligence, bundled and controlled

The portable release includes **Index-Translate-2B in Q4_K_M format**, executed through **llama.cpp** as an explicit offline translation option. Quantization reduces the model's storage and memory requirements. CPU threads are bounded, model integrity is checked, and inference supports cancellation and memory checks.

The model runs when requested rather than remaining loaded as a background service. Explicit offline translation does not silently fall back to an online provider.

Other bundled components include Whisper-based dictation, Omnilingual recognition through sherpa-onnx for validated routes, and a Piper Persian voice reserve. Offline coverage follows the application's supported mappings; a model's advertised language count is not treated as proof that every language works reliably.

The local translation model is an optional engine, not an always-running judge of semantic correctness.

### Native Windows architecture

The interface uses **Qt through PySide6**. Translation, audio, persistence and interface responsibilities are separated so each can handle its own failures and cancellation boundaries.

**SQLite** stores conversation history, revisions and drafts locally. DOCX export uses ZIP/XML assembly without requiring Microsoft Word. TXT, CSV and JSON exports provide additional ways to retain or reuse conversations, with Unicode and right-to-left text handling.

The portable folder carries its Python runtime, shared libraries, native helpers and model weights. No browser shell, WebView2 installation, database server or resident model server is required. There is no background updater or automatic model download.

### Local records and explicit online boundaries

Conversation history stays in the application's local data folder. Backup verification and recoverable storage behavior support moving or upgrading the portable installation. Optional provider credentials use Windows account-bound protection; conversation history and exported documents are not encrypted by the app.

Online translation sends relevant text to its providers. Online recognition sends audio, and online playback sends the text to be spoken. Translation, recognition and voice settings are independent, so choosing offline translation alone does not make every stage offline.

### Verification with defined limits

Source tests, packaged application checks, native model execution, asset hashes and release identity records cover different parts of the system. Packaging verification checks that the distributed executable and resources match the prepared release.

These safeguards target concrete failure modes. They do not establish universal translation accuracy: fluent wording, matching numbers and agreement between engines can still conceal a meaning error.

Additional AI repair currently accepts up to **1,200 source characters**. Longer inputs retain available candidate comparison and deterministic checks. Language coverage and translation quality also differ between providers and directions.

Read the [architecture](docs/ARCHITECTURE.md), [dependency inventory](DEPENDENCIES.md), [privacy details](docs/PRIVACY.md) and [verification findings](docs/VERIFICATION.md) for implementation details and measured limitations.

## Licence and author

Created by **[Parham (Leon) Faraji](https://github.com/leon-executes)**, from [Forumark's creators](https://forumark.com).

Gray Feather's original code and documentation are **source-available under [PolyForm Noncommercial 1.0.0](LICENSE)**. The full licence defines permitted purposes, including its provisions for noncommercial organizations. For uses outside those permissions, contact the author through the GitHub profile. Third-party code, runtimes, models and datasets retain their [own licences](THIRD-PARTY-NOTICES.md).
