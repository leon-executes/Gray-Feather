# All-language evidence and deferred work · 1.3.1

**No blanket quality guarantee.** Every app language now has native-recording recognition evidence and an actual voice availability/outage check. Translation has historical human-reference evidence in both English directions. Voice naturalness/intelligibility and consequential semantic accuracy still need independent native review.

The current release preserves the translation algorithms. Uncertain new engines and unverified Tigrinya/Sorani cross-language pronunciation substitutes are deferred. Persian-for-Dari is explicitly approximate.

## Dictation evidence

CER is character error rate, lower is better. It is not “100 minus accuracy.” Values include letters, numbers and combining marks; punctuation/spaces are excluded. Dates/numbers are not normalized into equivalent meaning. Each cell reports CER and completed/attempted clips. Different languages/corpora are not a fair league table. The new reserve screens use only five recordings for most previously untested languages; those are screening evidence, not robust quality assurance.

| Language | Current routes: measured CER and completion | Qualification |
| --- | --- | --- |
| English | Whisper 3.47%; 20/20 → Google: quality not measured here | Read-speech sample; accents and spontaneous conversation are not certified. |
| Arabic | Google 11.66%; 20/20 → Whisper: quality not measured here | FLEURS ar_eg is Egyptian, not a Saudi-accent certification. |
| French | Whisper 4.76%; 20/20 → Google: quality not measured here | Read-speech sample; accents and spontaneous conversation are not certified. |
| Turkish | Google 6.28%; 20/20 → Whisper: quality not measured here | Read-speech sample; accents and spontaneous conversation are not certified. |
| Persian / Farsi | Google 3.16%; 50/50 → Omnilingual 6.22%; 50/50 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Dari | Google 2.97%; 30/30 → Omnilingual 6.19%; 30/30 | Dari-labelled corpus; accent authenticity not independently established. |
| Pashto | Omnilingual 17.31%; 20/20 → Whisper 51.0%; 20/20 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Urdu | Google 9.51%; 20/20 → Whisper: quality not measured here | Read-speech sample; accents and spontaneous conversation are not certified. |
| Hindi | Google 7.08%; 10/10 → Whisper 22.24%; 10/10 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Bengali / Bangla | Google 5.19%; 10/10 | FLEURS bn_in, not Bangladesh-specific certification. |
| Punjabi (Gurmukhi) | Google 9.65%; 10/10 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Sindhi | Omnilingual 14.36%; 50/50 | FLEURS sd_in, not Pakistan-specific certification. |
| Amharic | Omnilingual 9.57%; 20/20 → Google 16.26%; 20/20 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Tigrinya | Google 26.17%; 50/50 → Omnilingual 25.34%; 50/50 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Oromo | Omnilingual 22.85%; 41/41 → Google 23.51%; 10/10 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Somali | Omnilingual 15.91%; 20/20 → Google 17.5%; 10/10 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Swahili | Google 11.67%; 10/10 → Whisper 17.99%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Kurdish Sorani / Central Kurdish | Omnilingual 10.21%; 50/50 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Kurdish Kurmanji / Northern Kurdish | Omnilingual 9.01%; 50/50 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Spanish | Google 0.94%; 10/10 → Whisper 2.19%; 5/5 | FLEURS es_419, not Spain-specific certification. |
| German | Google 2.22%; 20/20 → Whisper: quality not measured here | Read-speech sample; accents and spontaneous conversation are not certified. |
| Italian | Google 0.85%; 10/10 → Whisper 1.01%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Portuguese (Portugal) | Google 5.28%; 10/10 → Whisper 4.69%; 5/5 | FLEURS pt_br, not Portugal-specific certification. |
| Russian | Google 4.98%; 10/10 → Whisper 1.7%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Chinese (Simplified) | Google 16.08%; 10/10 → Whisper 18.97%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Japanese | Google 9.26%; 10/10 → Whisper 16.4%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Korean | Google 11.63%; 10/10 → Whisper 5.24%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Dutch | Google 4.09%; 20/20 → Whisper: quality not measured here | Read-speech sample; accents and spontaneous conversation are not certified. |
| Polish | Google 2.39%; 10/10 → Whisper 7.81%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Romanian | Google 14.59%; 10/10 → Whisper 9.08%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Ukrainian | Google 9.99%; 20/20 → Whisper: quality not measured here | Read-speech sample; accents and spontaneous conversation are not certified. |
| Greek | Google 8.64%; 6/10 → Whisper 8.83%; 4/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Hebrew | Google 14.86%; 9/10 → Whisper 11.34%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |
| Indonesian | Google 2.3%; 10/10 → Whisper 2.09%; 5/5 | Read-speech sample; accents and spontaneous conversation are not certified. |

**Deferred dictation reserves:** Bengali small-Whisper produced 103.04% CER on six completed clips and timed out on four more; Punjabi produced 103.68% CER on ten clips. Both are removed from Automatic. Google remains available; replacement offline reserves are deferred. These rejected-candidate measurements are screening evidence, not a claim about larger Whisper models.

## Voice availability and practical next step

One native/reference or simple synthetic phrase per language, actual synthesis with playback intercepted. Primary-provider outages were injected. No exact Windows voices are assumed to be installed on another PC. Timing under concurrent test/build load is not a clean latency benchmark.

| Language | Automatic | Survives primary voice outage on this PC | Decision / deferred work |
| --- | --- | --- | --- |
| English | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Arabic | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| French | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Turkish | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Persian / Farsi | Audio produced | Yes: offline_piper | Keep Google recognition with Omnilingual reserve and bundled Persian voice; Whisper stays sidelined. |
| Dari | Audio produced | Yes: edge_persian_approx | Use labelled Persian Piper/Edge. Native Dari voice adoption deferred until clear licence and listener evidence. |
| Pashto | Audio produced | **No verified reserve** | Keep Edge; independent local voice deferred. Pashto Ghag/YourTTS is a later-pass candidate, not integrated. |
| Urdu | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Hindi | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Bengali / Bangla | Audio produced | Yes: google_web | Keep Google dictation. Poor small-Whisper automatic reserve is sidelined; test bundled Omnilingual as a later-pass replacement. |
| Punjabi (Gurmukhi) | Audio produced | Yes: google_web | Keep Google dictation. Poor small-Whisper automatic reserve is sidelined; test Gurmukhi-specific Omnilingual recognition in a later pass. |
| Sindhi | Audio produced | **No verified reserve** | Basic Sindhi voice is weak; Indic Parler is a later-pass candidate requiring Arabic-script, CPU and packaging tests. |
| Amharic | Audio produced | Yes: google_web | Keep improved Omnilingual recognition with Google reserve; validate spontaneous speech and consequential terminology. |
| Tigrinya | Audio produced | **No verified reserve** | Dedicated local voice; no unverified Amharic substitute. Recognition variability and second voice deferred. |
| Oromo | Audio produced | Yes: offline_basic | Keep neural/basic voice and measured ASR reserve. Calendar/semantic issues require native reference work; no inferred date repair. |
| Somali | Audio produced | Yes: offline_neural | Local voice reserve handles ordinary text/plain integers; complex numeric notation remains an online-voice dependency. |
| Swahili | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Kurdish Sorani / Central Kurdish | Audio produced | **No verified reserve** | Dedicated local voice; no unverified Persian substitute. Unsupported-symbol handling and second exact voice deferred. |
| Kurdish Kurmanji / Northern Kurdish | Audio produced | **No verified reserve** | Keep basic Kurmanji. The tested MMS model was worse and remains sidelined; native-listener work needed. |
| Spanish | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| German | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Italian | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Portuguese (Portugal) | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Russian | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Chinese (Simplified) | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Japanese | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Korean | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Dutch | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Polish | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Romanian | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Ukrainian | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Greek | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Hebrew | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |
| Indonesian | Audio produced | Yes: google_web | Preserve current routes. Native-listener/domain validation and any offline voice upgrades remain a later pass. |

## Translation evidence

The previous public-reference run covered all 34 identities in 66 English translation directions: 2,112 engine-attempt records, 1,350 completed outputs. It used eight reference sentences per direction. Quota-limited and unsupported attempts were recorded separately. This is historical lexical/comparison evidence across raw engines, not a fresh semantic rating of this release’s final repaired output. English is the common counterpart; counts for it are therefore not comparable to a single target language.

| Language | Reference directions | Historical completed engine outputs |
| --- | --- | --- |
| English | 66 | 1350 |
| Arabic | 2 | 64 |
| French | 2 | 64 |
| Turkish | 2 | 64 |
| Persian / Farsi | 2 | 64 |
| Dari | 2 | 48 |
| Pashto | 2 | 58 |
| Urdu | 2 | 48 |
| Hindi | 2 | 48 |
| Bengali / Bangla | 2 | 48 |
| Punjabi (Gurmukhi) | 2 | 48 |
| Sindhi | 2 | 48 |
| Amharic | 2 | 48 |
| Tigrinya | 2 | 48 |
| Oromo | 2 | 32 |
| Somali | 2 | 44 |
| Swahili | 2 | 32 |
| Kurdish Sorani / Central Kurdish | 2 | 32 |
| Kurdish Kurmanji / Northern Kurdish | 2 | 32 |
| Spanish | 2 | 32 |
| German | 2 | 32 |
| Italian | 2 | 32 |
| Portuguese (Portugal) | 2 | 32 |
| Russian | 2 | 32 |
| Chinese (Simplified) | 2 | 32 |
| Japanese | 2 | 32 |
| Korean | 2 | 32 |
| Dutch | 2 | 32 |
| Polish | 2 | 32 |
| Romanian | 2 | 32 |
| Ukrainian | 2 | 32 |
| Greek | 2 | 32 |
| Hebrew | 2 | 32 |
| Indonesian | 2 | 32 |

Earlier model-assisted reviews also found substantive and critical errors. Do not promote those reviews into native-speaker certification or use an isolated lexical score to replace a working engine. The new 24-scenario default-pipeline smoke test completed but retained meaning ambiguities. Broader semantic repair changes are deferred.

## Verified leads for a later pass

- [Pashto Ghag / YourTTS](https://huggingface.co/Nasimbahar/pashto-ghag-yourtts): public Apache-2.0 model card with inference artifacts. Needs isolated CPU/ONNX portability, whole-passage and native-listener testing before adoption. No free hosted service is assumed.
- [Indic Parler](https://huggingface.co/ai4bharat/indic-parler-tts): publisher lists Sindhi under Apache-2.0. Arabic-script coverage, access terms, resource use and portable conversion require validation; it is not bundled.
- [Piper voice catalogue](https://huggingface.co/rhasspy/piper-voices/tree/main): practical optional local upgrades where an exact locale exists. Check each model licence and evaluate against the existing voice; do not bulk-add models merely for coverage.
- [Omnilingual](https://github.com/facebookresearch/omnilingual-asr): existing bundled recognition model is a candidate for weak reserves, but broader declared coverage does not justify automatic enablement without paired native tests.
- Tigrinya/Sorani/Kurmanji: retain the current tested route; prioritize native listening, numbers, names and a second exact-language model over unverified cross-language substitution.

[Detailed machine-readable evidence](language-evidence-34.json) · [Speech changes and initial measurements](gap-validation-20261012.md)

Public-recording sources: [FLEURS](https://huggingface.co/datasets/google/fleurs), [Common Voice mirror](https://huggingface.co/datasets/fsicoli/common_voice_17_0), [Phonetico](https://huggingface.co/datasets/phoneticoai/phonetico-speech), and the [Dari-labelled corpus](https://huggingface.co/datasets/latif98/whisper-dari-16k). The lab preserves hashes/raw results. No user recordings or session data were used.
