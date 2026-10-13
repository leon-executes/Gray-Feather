# 1.3.2 · Speech usability repair

## 1.4.1

- Removed offline Index text AI, its weights, runtime and selectable engine. Existing offline preferences migrate with a notice.
- Kept online reinforcement, dictation, voices, Safe Speech, history and exports.
- Index failures skip redundant repair requests; brief service cooldowns preserve working translation routes.
- Standard DEFLATE ZIP, one complete Windows download. No separate voice pack.


## 1.4.0

- Group regression tests and probes under `tests/`; build and maintenance commands under `tools/`.
- Use stronger standard ZIP compression and remove verified duplicate private DLL copies. Models and voice weights are unchanged.
- Move developer-only corresponding sources to their own release archive. All voices remain in the app download.
- Preserve published README artwork; refresh upgrade, privacy and publishing instructions.
- Add hash-checked GitHub download assembly for the complete ZIP when it exceeds the per-asset limit.

## 1.3.4

Saved sessions have checkboxes and atomic multi-session deletion. Shred History purges sessions, revisions, drafts and managed automatic backups after confirmation. Settings and separate exports/backups are retained; forensic erasure on SSDs or system backups cannot be guaranteed.

## 1.3.3

Voice and Safe Speech controls now use taller ash housings with six-pixel padding on every side, inset button segments and clear selected states. Voice routing, speech playback and translation behavior are unchanged.

Female Persian preference restored. Reference webapp voice substitutes restored ahead of robotic Kurmanji and as reserves for other gaps; Sindhi gains labelled Urdu approximation. Safe Speech masks visible translations/playback reversibly. Completion-based Windows playback avoids timer truncation. One complete portable ZIP includes every voice.

# Changelog

## 1.3.0 — GitHub distribution preparation

- Added PolyForm Noncommercial 1.0.0, author attribution and explicit third-party scope.
- Added concise run/build/dependency guides, a replaceable README banner and contribution guidance.
- Added a clean source package, verified asset restoration and release-package checks.
- Separated a large optional upstream source archive so each release asset fits GitHub's size limit.
- Kept application behavior, runtime sources, executable and model weights unchanged.

## 1.3.0 — application

Automatic free-engine consultation and bounded repair; source-preserving two-speaker workflow; live speech previews; prepared voice reserves; DOCX export; bundled offline Index translation, selected Omnilingual recognition and Persian voice.

## 1.3.1 · speech coverage and fallback validation

Measured language routing expands the existing Omnilingual recognizer without another ASR model. New isolated neural/basic voice reserves fill the reported playback gaps, with explicit approximation labels, bounded complete-audio preparation, local-only modes, number guards and source/licence provenance. Translation algorithms and the main layout are preserved. See [the measured report](verification/gap-validation-20261012.md); weak languages are not described as universally reliable.

### Final conservative coverage check

- Added native-recording and voice-outage evidence for all 34 languages.
- Sidelined unreliable Bengali/Punjabi small-Whisper automatic reserves; deferred replacement engines.
- Deferred unverified Tigrinya/Sorani cross-language voice substitutes. Retained explicitly labelled Persian-for-Dari.
- Clarified when Automatic has no verified offline dictation reserve.
