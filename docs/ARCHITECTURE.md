# Architecture

## Find the part you need

| File | Responsibility |
| --- | --- |
| `app.py` | Service API, application lifecycle, diagnostics and executable commands |
| `ui.py` | Native two-speaker Qt workspace, settings, manual and review pane |
| `engine.py` | Provider adapters, language mappings, history and transport controls |
| `reinforced_engine.py` / `reinforcement.py` | Complete-candidate consultation, protected-detail checks and bounded repair |
| `index_engine.py` / `local_ai.py` | Online Index adapter and isolated local-model inference |
| `speech.py` | Recording, interim/final recognition, prepared voice reserves and playback |
| `offline_omni.py` / `offline_voice.py` | Bundled native recognition and Persian voice adapters |
| `settings.py` / `docx_export.py` | Validated settings and Unicode document export |

## Source stays authoritative

Each speaker's source and translated result remain together. Original text, revisions and provider provenance are retained. A new request clears stale output; cancellation and request ownership stop late responses from overwriting edited text or a newer turn. Speech previews are provisional. Only complete final recognition becomes the saved source.

## Reinforcement is a bounded repair pipeline

Automatic mode consults eligible free routes within a shared deadline. Ranking is direction-specific: Persian, Dari, Sorani and Kurmanji are separate identities. Provider-family information prevents a proxy or mixed-provenance response from being presented as another independent engine.

The selector considers complete candidate translations. Protected-content checks examine amounts, signs, units, references, contact details and supported calendar expressions. Narrow source-bound repairs can replace uniquely aligned corrupt details or select a better complete candidate. Detected unresolved discrepancies can trigger an Index repair candidate within the current source-length limit. Glossary/context constraints prevent an unconstrained alternative from replacing a conditioned result.

This is intentionally not a universal semantic proof. Matching numbers, engine agreement and a plausible backtranslation can coexist with a wrong actor, obligation or negation. Additional model-based repair currently accepts at most 1,200 source characters. Longer input still receives available complete-candidate comparison and deterministic checks. See [verification and known limits](VERIFICATION.md).

## Speech has two different jobs

While recording, one worker processes snapshots and a replaceable pending snapshot prevents an expanding queue. Stop cancels preview work and requests full recognition. Result ownership protects changed languages, edited drafts and abandoned recordings.

Voice output prepares eligible reserves in bounded parallel slots. Only one completed route plays; the preferred route has a short grace period if a reserve finishes first. Stop cancels work and prevents delayed fallback playback. Exact-language eligibility is checked independently of whether a voice service is currently reachable. Offline recognition and voice are enabled only for the measured mappings, not merely every language mentioned by a model card.

## Local by design, online when selected

SQLite stores local history, revisions and drafts. Writes and exports use explicit durability/replacement behavior; backups are verified. Optional credentials use Windows DPAPI, which is account-bound. History is not encrypted by this application. Automatic translation, online recognition and online voice send their respective text or audio to their providers; there is no claim that the default workflow is wholly offline.

The explicit Index 2B offline option uses a pinned local model and a cancellable CPU helper. It has bounded threads, memory checks and integrity verification. Native helpers use private transient files/pipes rather than a resident server. The bundled model is a translation option, not an always-running semantic authority.

## Small dependency surface at runtime

Qt supplies the native interface. Python's standard library handles SQLite, structured exports and DOCX ZIP/XML assembly. Word and a database server are unnecessary. The portable directory carries the required shared libraries, native helpers and model weights. Large upstream source archives are release assets, so the Git repository stays practical to clone.

Implementation and product direction: [Parham (Leon) Faraji](https://github.com/leon-executes).
