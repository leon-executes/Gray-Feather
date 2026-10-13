# Speech gap validation · 12 October 2026

**Verdict:** material dictation improvements and working voice routes for the six reported gaps. This is a tested engineering improvement, not a claim of uniformly reliable interpretation. Sindhi and Kurmanji voices remain basic; Dari uses labelled Persian pronunciation. Tigrinya needs further native-listener validation.

## What changed

- Preserve the interface, translation/reinforcement algorithms, saved sessions, export and existing good routes.
- Route Amharic, Pashto, Somali and Sindhi to the already bundled Omnilingual model first. Add Kurmanji. Keep Google first for Persian, Dari and Tigrinya with an offline Omnilingual reserve. Add measured Google reserves for Amharic, Oromo and Somali.
- Add dedicated local neural voices for Tigrinya, Oromo and Sorani, plus a limited Somali reserve. Reuse bundled eSpeak NG for basic voices. Restore Dari playback through explicitly approximate Persian Edge/Piper voices.
- Do not enable cloud recognition candidates merely because they return HTTP success. Sorani, Kurmanji, Sindhi and Pashto Google probes returned poor/wrong-language transcripts. Do not automatically retry the poor small-Whisper routes for Amharic, Somali or Sindhi.
- Prepare complete audio before playback. Bound native jobs, CPU threads, output size and deadlines. Reject a partial render, damaged model, unsupported neural symbol or cancellation. Keep original text unchanged. Show actual degraded voice status before playback.

## Paired recognition evidence

545 distinct public recordings; 1,136 recognition attempts, including 150 clean/quiet/noisy workflow trials. Fifty blocked Persian-Whisper probes were excluded. **CER is character error rate: lower is better, not a reliability score.** Insertions can produce values above 100%. Failed requests are counted separately and excluded from CER. Orthographic variation and numbers written as words affect these scores.

| Language | Previous automatic route: CER / completion | Candidate evidence and decision |
| --- | --- | --- |
| Amharic | 154.1%; 19/20 | Omnilingual 9.6%; 20/20. Google reserve 16.3%; 20/20. |
| Pashto | 51.0%; 20/20 | Omnilingual 17.3%; 20/20. Whisper remains a weaker emergency reserve. |
| Somali | 100.0%; 20/20 | Omnilingual 15.9%; 20/20. Google reserve 17.5%; 10/10. |
| Sindhi | 114.2%; 37/50 | Omnilingual 13.9%; 50/50. Poor alternatives sidelined. |
| Persian | Google 3.2%; 50/50 | Keep Google. Add Omnilingual reserve: 6.2%; 50/50. |
| Dari | Disabled | Google 2.7%; Omnilingual 6.2%; 30/30 each on a Dari-labelled corpus. Accent authenticity not independently established. |
| Tigrinya | Disabled | Google 26.2%; Omnilingual 25.3%; 50/50 each on Phonetico. Four short Common Voice clips favoured Google but both were weak. |
| Kurmanji | Disabled | Omnilingual 9.0%; 50/50 Common Voice clips. |
| Oromo | Omnilingual 22.9%; 41/41 | Keep it; add Google reserve (23.5%; 10/10). |
| Sorani | Omnilingual 10.2%; 50/50 | Keep it. Google did not qualify as a reserve. |

Unchanged automatic checks also covered English, Arabic, French, German, Dutch, Turkish, Ukrainian and Urdu. See [all measured groups](gap-validation-summary.json). These corpora are not guaranteed absent from model training. They are mostly recorded/read speech, not representative of every regional accent, spontaneous conversation, medical encounter or microphone.

The 150 workflow trials use five recordings per language in clean, 0.1 amplitude and deterministic 20 dB additive-noise conditions. All completed. Numbers, names and short utterances remain failure areas. Tigrinya quiet-audio CER reached 40.5% in this small subset. This is not an acoustic hardware or real-room noise certification.

## Voice decisions

| Language | Automatic path | Remaining limitation |
| --- | --- | --- |
| Tigrinya | MMS neural → exact installed Windows | Native listening still needed. Unverified Amharic-pronunciation fallback is deferred. |
| Dari | Persian Piper → Persian Edge reserve → exact Windows → basic Persian | Explicit pronunciation approximation, not a dedicated Dari voice. |
| Oromo | MMS neural → exact Windows → basic Oromo | Numbers/unsupported neural symbols fall through as a whole passage. |
| Sorani | Vekol neural → exact Windows | Strict symbol coverage; unverified Persian-pronunciation fallback is deferred. |
| Kurmanji | exact Windows → basic Kurmanji | Tested MMS model was worse and is not shipped. Basic voice is robotic. |
| Sindhi | exact Windows → basic Sindhi | Weak round-trip intelligibility. No claim of a high-quality Sindhi voice. |
| Somali | Edge → MMS reserve → exact Windows | Local voice covers ordinary text/plain integers. Complex numeric notation may require online Edge. |

Voice diagnostics used native reference text, synthetic number stress cases, generated-audio decoding and ASR round trips. **Round-trip scores are not listener intelligibility or naturalness ratings.** No physical playback was needed; final playback calls were intercepted during pipeline checks. One local-only Somali complex-number scenario correctly refused unsupported content rather than omit details.

Tigrinya and Sorani numeric tokens are spoken literally with leading zeros and separators retained; no calendar conversion or floating-point rounding occurs. Somali's additional spelling only handles plain unsigned integers. Other notation is rejected by the neural guard. Displayed translations are never changed by speech normalization.

A further ten Dari-labelled passages compared Persian voices: Piper rendered 10/10 (median 0.758 s); Edge rendered 9/10 (median 1.718 s). Google recognized 9/10 Piper outputs and all nine Edge outputs. Successful-output round-trip CER was 1.13% versus 1.49%, on different successful subsets; this is not a naturalness ranking. Bundled Persian Piper is the practical default, with Persian Edge as reserve. Dedicated [Farahnaz Dari](https://huggingface.co/kk221208/mms-tts-farahnaz-dari) and [Dari test](https://huggingface.co/kk221208/mms-tts-dari-test) model cards leave licence/evaluation fields unspecified, so they are not release-ready replacements.

## Translation and honest limits

24 default reinforced, no-key scenarios covered the six reported languages: appointments, safeguarding, reported medical facts and everyday travel. All completed. This is availability evidence, not 100% accuracy. Backtranslations showed ambiguities involving Tigrinya time/medical wording, Oromo relationship wording and Kurmanji travel wording; a backtranslation can itself be wrong. The translation algorithm was preserved rather than tuned to four handpicked sentences per language.

Sorani, Kurmanji and Sindhi currently have one acceptable bundled ASR engine; typing remains the last resort if it fails. Pashto still lacks an independently verified second free voice service. An unintelligible unrelated-language voice is not counted as a quality solution. Larger/gated models are not bundled without performance, licence and language-quality evidence.

## Readiness

Suitable for a controlled release with the stated limitations. Not certified for unattended medical, safeguarding or legal interpretation. Engineering checks and cleaner fallback behaviour do not establish semantic safety. A native-listener panel, authentic spontaneous speech, a clean Windows VM and lower-end hardware remain necessary before claiming broad commercial readiness. The new MMS/Vekol weights also retain their noncommercial terms; product engineering quality does not change licensing permissions.

## Sources and reproducibility

- [FLEURS](https://huggingface.co/datasets/google/fleurs): 20–50 test clips per language; all 41 available Oromo test clips. CC BY 4.0.
- [Common Voice 17 mirror](https://huggingface.co/datasets/fsicoli/common_voice_17_0): Kurmanji and four short Tigrinya clips; CC0.
- [Phonetico speech](https://huggingface.co/datasets/phoneticoai/phonetico-speech): 50 Tigrinya test clips; CC BY 4.0.
- [Dari-labelled corpus](https://huggingface.co/datasets/latif98/whisper-dari-16k): 30 test clips; licence unspecified, audio/transcripts not redistributed here.
- [MMS](https://huggingface.co/facebook/mms-tts), [Vekol Sorani](https://huggingface.co/RevgeAI/vekol-tts-ckb-edge), [eSpeak NG](https://github.com/espeak-ng/espeak-ng), [Omnilingual](https://github.com/facebookresearch/omnilingual-asr).

The separate local laboratory retains raw outputs, fixture hashes, original baselines and rejected candidates. Published aggregates contain no private user recordings or session history. Runtime/model source revisions, transformations, licences and hashes ship with the app.

## Release checks

487 source checks passed. The frozen executable passed 482 checks with five source-interpreter fixtures skipped; those five passed from source. All ten actual bundled native checks passed, including offline translation, dictation and new voice synthesis. Interface startup/rendering passed. Persian-character portable paths worked; a real cancelled helper exited in 0.703 seconds with scratch files removed. [Release evidence](release-checks-1.3.1.json).

## Expanded all-language check

The expanded laboratory now contains 705 distinct public recordings and 1,391 native recognition attempts, including failures. All 34 app languages have some native-recording evidence. These small read-speech samples do not establish equivalent dialect, conversational or domain quality. [All-language evidence and deferred work](language-evidence-34.md) separates each route and its limits.

Actual synthesis produced audio for 34/34 sampled languages; 29/34 survived an injected primary-voice failure. Pashto, Sindhi, Kurmanji, Tigrinya and Sorani have no independently verified voice reserve on this test PC. Installed exact-language Windows voices may help, but are not assumed.

Bengali and Punjabi small-Whisper produced poor, wrong-script results and are sidelined from Automatic. Google remains their automatic dictation route. Replacement reserves and uncertain new models are deferred; unsupported cases remain explicit failures or text rather than speculative output.
