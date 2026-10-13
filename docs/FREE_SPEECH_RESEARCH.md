# Free speech repair: implemented routes and evidence

Updated 10 October 2026 for version 1.3. This supplements the original reinforcement research. The
Windows app keeps native WinMM recording and ships its speech runtime. Users do
not install Python, PyAudio, a browser, a codec pack or a machine-learning toolkit.

## Version 1.3: measured local reserves and remaining gaps

The added native Omnilingual CTC 300M int8 route is enabled only for exact Oromo
`om-ET` and Sorani `ckb-IQ`, after actual public native-speaker trials. It is a
usable experimental gap route with spelling and name errors, not a semantic
certification. Two FLEURS recordings per language completed in approximately
1.84–2.18 seconds for Oromo and 2.43–3.11 seconds for Sorani. The second Oromo
recording's three/two relationships were recognizable; Sorani's explicit
negative wording remained present. The exact raw references and outputs are in
`verification/omnilingual-native.json`. The source native-bundle check also
shows its imperfect Oromo transcript alongside the public reference.
[Meta's primary model](https://github.com/facebookresearch/omnilingual-asr),
[sherpa-onnx native model documentation](https://k2-fsa.github.io/sherpa/onnx/omnilingual-asr/models.html),
[FLEURS publisher and attribution](https://huggingface.co/datasets/google/fleurs).

This CTC model does not accept a language constraint. Published coverage of
more than 1,600 languages does not enable every app locale. Broader local trials
made Persian, Somali and Urdu wording or script errors; they do not change the
existing automatic routes. Distinct Dari is not replaced with Persian, and no
untested Tigrinya or Kurmanji route is enabled. The recognizer uses one native
CPU process at a time, a duration-based 15–60 second request budget, contiguous
segments of at most 35 seconds, and rejection of the entire transcript if any
non-silent segment fails. A real 50-second two-segment trial retained every PCM
byte, including its final speech tail. A native cancellation trial stopped in
201 ms, and actual Unicode-resource and scratch-folder trials passed. See
`verification/omnilingual-wrapper-native.json`; these are execution and boundary
proofs, not dictation accuracy rates.

Persian voice now has one bundled Piper Gyro medium reserve. Eight synthetic
fixtures compared Amir and Gyro using actual Google recognition and independent
Omnilingual transcripts. Gyro preserved tested quantities, prohibitions,
calendar and conditional wording more clearly in Google's round-trip than Amir.
Both recognizers corrupted the name Maryam, so name fidelity is a known remaining
limitation. A returned WAV alone is never counted as a correct spoken passage.
The chosen exact weight hash matches the creator's immutable revision
`e409c5a8fb164ff6e710bfbd07b7b02c1e13949a`, which declares MIT; the original model
and dataset attribution are retained. Piper and its phonemizer are MIT components,
but the eSpeak NG helper/data retain GPL notices and source. This stack is not
relabelled entirely MIT. [Pinned Gyro creator evidence](https://huggingface.co/gyroing/Persian-Piper-Model-gyro/tree/e409c5a8fb164ff6e710bfbd07b7b02c1e13949a),
[Piper release](https://github.com/rhasspy/piper/releases/tag/2023.11.14-2).

Gyro completed an actual Unicode relocation in 1.438 seconds and native
cancellation in 93 ms, with private scratch cleanup. Automatic Persian synthesis
prepares Edge and this exact local reserve concurrently; a failed or slow free
network route need not prevent the complete local passage from playing.
Explicit Offline uses only bundled Persian or an exact installed Windows token,
and uploads no text. No Persian voice is substituted for Dari. See
`verification/offline-voice-unicode-native.json` and
`verification/speech-semantic-assessment-1.3.json`.

Current registry coverage is 31 exact default dictation locales and 28 mapped
free/bundled voice locales. Dictation gaps remain Dari, Tigrinya and Kurmanji;
voice gaps remain those three plus Sindhi, Oromo and Sorani. An exact installed
Windows voice is optional and never assumed. The current complete route inventory
is `APP-CAPABILITIES.csv` and `verification/speech-capabilities-34.json`.

## Recognition

**Free online Google recognition works in the live test.** The legacy Chromium
speech endpoint accepted FLAC made by the new standard-library encoder, using the
public personal/testing client key distributed by SpeechRecognition. On the
11-second public-domain JFK clip it preserved “not” but made minor word errors
(“And so” became “answer”, and the second “ask” became “asked”). The observed request
took 2.812 seconds. The key can be revoked; the app uses an independent local
route where its quality checks support that language. [SpeechRecognition's implementation and caveat](https://github.com/Uberi/speech_recognition/blob/master/speech_recognition/recognizers/google.py)

**The production model is Whisper small-q5_1 multilingual.** An earlier base
probe transcribed the JFK clip in 1.187–1.250 seconds with expected wording, but
later paired multilingual conditions justified replacing base with one quantized
small model. English and French now use local recognition first, with Google
fallback: local fixtures retained “two copies” / “deux copies” where Google
returned different words. Other covered languages use Google first and the
supported local route as fallback. Persian is online-only after poor offline
wording with both tested models. These are scoped routing decisions, not overall
accuracy estimates. The native engine remains whisper.cpp v1.9.5, official build
b5454. [Official release](https://github.com/ggml-org/whisper.cpp/releases/tag/v1.9.5)

The single bundled `ggml-small-q5_1.bin` file is 190,085,487 bytes with SHA-256
`ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb`.
It adds about 40 MiB to the previous base model; both models are not bundled.
Its native runtime, required app-local Microsoft runtime DLLs and model are
packaged under `resources/speech`. This gives local speech a measurable benefit
without requiring Torch or a user-installed runtime. The model and native engine
are MIT licensed. [Model download instructions](https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md),
[whisper.cpp license](https://github.com/ggml-org/whisper.cpp/blob/master/LICENSE),
[Whisper license](https://github.com/openai/whisper/blob/main/LICENSE)

Thirty-one project language mappings have an automatic dictation route: 25
through Google, 28 through the enabled Whisper registry and two measured
Omnilingual routes, with overlap. Offline
Persian is deliberately disabled after quality checks even though Whisper has a
Persian token. Whisper declines Tigrinya, Oromo, Kurdish Sorani, Kurdish Kurmanji
and distinct Dari; the separate measured Omnilingual route covers only Oromo and
Sorani. Other unsupported languages are not substituted.
Enabled tokens describe model availability, not measured accuracy for every language.
The app saves recognized words as an editable draft and preserves that text as
the original when translated. It does not retain microphone audio. The tokens
identify languages, not guaranteed recognition quality for every regional accent.
[Primary language registry](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py)

The production choice is supported by `verification/speech-model-comparison.json`
and `verification/speech-model-conditions.json`. On the nine-word Arabic fixture,
small-q5_1 retained all nine expected words in clean and 20 dB quieter audio, and
eight of nine with additive 15 dB SNR noise; base retained four. The small model
took roughly 2.8 seconds and about 482 MiB working memory on those short fixtures.
Those improvements are useful, but not universal: both models struggled with the
Persian fixture, the small model made a Chinese character error, and repeated
long speech was omitted in another stress case. Written numbers versus digits
and Traditional versus Simplified characters can also inflate literal edit
metrics without changing meaning. Selected synthetic voices and conditions are
not population accuracy. Review names, quantities, negation and longer turns.

The FLAC encoder uses bounded 16 kHz mono PCM, STREAMINFO, verbatim frames, MD5,
header CRC-8 and frame CRC-16. A separately implemented native decoder reproduced
the original signed PCM bit for bit for randomized lengths 1, 511, 4095, 4096,
4097, 7499 and 800000 samples. This covers full frames, the last short frame and
the 50-second recording limit. [FLAC format specification](https://xiph.org/flac/format.html)

Recognition is bounded and cancellable. Cancelling a cloud attempt does not send
the audio to another provider. The offline process is terminated on cancellation
and removes its private recording and transcript files. Silent recordings are
rejected before local inference to reduce known hallucination behavior.

## Playback

**Free Google Translate TTS returned real MP3 audio.** Windows MCI could not
decode it on the test PC despite an available input and output device, so MCI is
removed from the playback path. The bundled miniaudio decoder converts MP3 to
validated 16 kHz mono PCM WAV, which the existing WinMM playback path can play.
The decoder's wheel and small supporting wheels cost substantially less than a
Qt multimedia stack or a separately installed codec pack.
[miniaudio Python implementation](https://github.com/irmen/pyminiaudio),
[Google TTS client implementation](https://github.com/pndurette/gTTS)

**Free Edge TTS is the primary voice route.** Live requests with edge-tts 7.2.8
worked for `en-US-JennyNeural`, `fa-IR-DilaraNeural` and `ps-AF-LatifaNeural`, each
returning MP3 that the bundled decoder successfully decoded. Observed synthesis
was about 0.62 seconds per short request. This restores exact Persian and Pashto
voices that the Google fallback does not establish. No paid resource key is used.
[Primary edge-tts project](https://github.com/rany2/edge-tts)

The voice router covers 28 project language mappings and selects an exact
language voice from the existing 28-voice
registry, then the free Google voice when supported, then an installed matching
Windows voice. Each route synthesizes and validates the complete requested
passage before any fragment plays. A failed later synthesis chunk therefore does
not play an incomplete passage. It never substitutes Dari, Oromo, Tigrinya or a
Kurdish voice with another language; Sindhi also has no free voice route. Free synthesis has a total 60-second budget,
short network timeouts and prompt cancellation. Decoded temporary WAV files are
removed when playback starts unsuccessfully or is cancelled.

Edge synthesis runs in a private child process using the same bundled executable.
The parent enforces cancellation and the deadline even if DNS resolution or
asyncio teardown stalls. Voice text travels in a disposable private request file,
not the command line, and the worker never opens the conversation database.

## What the tests establish

The staged tests check malformed, truncated and incorrectly formatted recording
rejection; silent input; exact-locale boundaries; cancellation; process cleanup;
lossless FLAC round trips; real MP3 decoding; full-text chunk preservation; and
late synthesis failure before playback. The audio fixture inside the test module
is a generated sentence, so packaged self-tests do not depend on a development
directory or network access. They establish audio and cancellation contracts,
not the accuracy of a live recognizer on unseen speech.

## Version 1.2: provisional intake and ready voice reserves

Recording now submits an immutable snapshot of completed native PCM buffers at
a default three-second cadence. It never reads a buffer while the microphone
driver still owns it. One recognition worker processes at most one snapshot,
with one replaceable pending snapshot: slower recognition discards intermediate
queued snapshots instead of accumulating jobs. Repeated whitespace/case-only
transcripts do not emit another preview. Capture continues while recognition
runs. [Microsoft's completed-buffer contract](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/ns-mmeapi-wavehdr)

These are progressively updated full-prefix recognitions, not a promise of
word-by-word server streaming. Each preview carries `provisional: true` and
`complete: false`; the UI must never save it as a finished turn or speak it.
Stop cancels the provisional worker and immediately returns the complete
recording, including the final partial buffer. Final recognition and translation
use that full audio. Preview errors do not discard it. Abort suppresses pending
and late preview results and prevents fallback to another recognition route.
[Microsoft's reset contract](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-waveinreset)

Native provisional inference uses two CPU threads; the final pass uses up to four.
Actual cached synthetic-fixture measurements on this development PC are:

| Locale | Recorded fixture duration | Two-thread native recognition | Meaning in this fixture |
| --- | ---: | ---: | --- |
| English | 5.328 s | 4.297 s | Do not cancel; two copies, not three retained |
| French | 5.232 s | 4.906 s | Do not pay fifty pounds; two copies, not three retained |
| Arabic | 6.744 s | 4.844 s | Payment prohibition, fifty pounds, two copies, not three retained |

Evidence is `verification/live-preview-native-proof.json`. These timings start
when an already recorded snapshot enters native inference; they exclude live
microphone capture, UI painting and translation. A three-second snapshot start
plus inference therefore can make the first local preview take several more
seconds. English/French retain the measured local-first policy; previews do not
switch those working local routes to cloud just for speed. Other supported
automatic locales retain the established Google-first policy. Persian remains
online-only. Hardware, length, language and competing work affect latency.

Cloud previews run in a short-lived child of the same portable executable,
using `--speech-preview-worker` and a ten-second parent-enforced budget. The
child reads disposable private request/audio files and does not open the
conversation database. Native inference runs directly under the preview
coordinator's supervision, avoiding a child worker that could leave a Whisper
grandchild behind when killed. Closing provisional work does not join it or
delay final recognition. This is explicit process control rather than reliance
on a socket timeout while DNS or executor teardown remains stuck.

Voice selection is independent of recognition selection. Automatic mode
prepares the preferred exact-locale Edge neural voice and a supported Google
reserve almost simultaneously, with at most two online preparation slots.
Preferred Edge wins if ready first or within a 350 ms grace after the reserve
becomes ready. Otherwise, a fully prepared reserve is selected and the slower
route is cancelled. This bounds the quality preference without making someone
wait for an entire failing preferred-service timeout. The 350 ms is a chosen
responsiveness policy, not a measured perceptual-quality threshold. Tests with
a deliberately stalled preferred route establish the grace/cancellation
behavior; live service latency remains a separate measurement.

The voice dropdown can prefer Automatic, free Edge, free Google, installed
Windows, or optional Azure. Explicit Windows attempts silent local rendering
first and only falls back online after a real native failure. Languages absent
from the free voice maps try only an installed exact-locale Windows token.
There is no dialect substitution. Azure is eligible only on explicit selection,
with a supplied speech resource key and a mapped voice; a configured paid
recognizer alone never enables paid voice. The current optional credentials
field is shared: independent Google paid-recognition and Azure paid-voice keys
cannot be configured together. Free/default paths need neither account.

A final live frozen probe exposed an intermittent missing Persian Edge result.
The same run later synthesized Persian through Edge successfully, while its
Google reserve returned HTTP 400. Google's current TTS language registry in the
primary gTTS client omits Persian; that reserve has now been removed. Google
Persian recognition is a separate route and remains enabled. Version 1.3 adds
the measured local Gyro reserve to the exact Edge and installed Windows choices.
[Current gTTS language registry](https://github.com/pndurette/gTTS/blob/main/gtts/langs.py),
[gTTS registry construction](https://github.com/pndurette/gTTS/blob/main/gtts/lang.py)

For an actually missing/failed Edge worker result, production synthesis now makes
one fresh attempt at the complete passage within the original 60-second budget.
Any successful earlier chunks are discarded before that retry. Invalid text,
unsupported locale, invalid/oversized/incomplete audio, PCM decode failure,
cancellation, or a consumed deadline are not retry reasons. There are at most
two whole-passage attempts, one selected playback, no cache of failed fragments,
and no permanent availability assumption after a successful retry.

All routes produce a complete validated mono 16-bit 16 kHz WAV before selection
and playback. Whole-text chunks preserve every character. A failed later chunk
cannot play a successful earlier fragment, and reserves never start speakers.
One serialized player owns the chosen passage. Google, Azure and native Windows
rendering use the same bounded private child protocol; Edge retains its separate
bounded child. No voice preparation begins just from typing or recording: these
paths run only when the app explicitly requests Listen or enabled final voice.

Windows rendering uses `SpFileStream`, plain-text speech flags and an exact
installed token. SAPI can otherwise change an assigned output stream's format,
so `AllowAudioOutputFormatChangesOnNextSet` is explicitly false before assigning
the 16 kHz stream. This route is optional: a usable installed SAPI voice was
unavailable on the development host; protocol and format behavior have mocked
boundary tests, not a claim of live native synthesis on every PC.
[Microsoft's stream and format behavior](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ee125635(v=vs.85))

Validated online voice audio has a memory-only cache bounded to four entries,
20 MiB and 120 seconds. Keys include provider, language, voice identity, text
digest and Azure credential/region identity when applicable. Temporary files
are deleted, and text is absent from child command lines. Installed Windows
voice audio is not cached because installed token identities can change outside
app settings. A per-Service session records actual route failures for a short
30-second ordering adjustment; cancelled losing reserves do not mark a service
unavailable. No availability assumption comes from a HEAD request, and no
failure disables a route permanently.

The new `test_live_speech` regressions cover native buffer ownership/order and
cadence, latest-only scheduling, duplicate suppression, prompt Stop, late-result
suppression, private worker protocol, kill/cleanup, exact-locale PCM validation,
parallel reserve selection, one playback, explicit-provider behavior, silent
native rendering, cache scope/expiry/memory bounds and cancellation. The local
run passed 38 new tests; the combined speech suite passed 91 tests in 1.687 s.
That local combined run excluded one legacy
in-process asyncio test because this agent's sandbox blocks asyncio socket-pair
creation; the granted full application runner is the definitive source/frozen
suite. No mock race test is counted as service availability or speech accuracy.

## Translation benchmark that remains honest

The definitive `verification/live-free-translation.json` run completed 50/50
keyless translation cases, with independent engine comparisons for 49/50,
including English into the other 33 text languages. Same-language preservation
is tested separately. This is operational evidence on those inputs, not a
semantic accuracy percentage. Google and Microsoft Bing supply free independent
reinforcement; MyMemory supplies an operational fallback with mixed provenance
and is not counted as an independent opinion.

Use a fixed corpus for all 34 text languages and preserve every raw provider
response. Separate two measurements: operational availability and bilingual
meaning. Availability cases can use translated short greetings with exact source
and target tags. For meaning, use paired gold examples of negation, names,
numbers, quantities, dates, references and pronoun context. Suggested English
anchors include “Do not pay 38.50 pounds until Friday”, “The room is not cold”,
“I gave her two tablets, not three”, and “Keep reference GF-0012 unchanged”.

For each gold pair, add a corrupted candidate that reverses negation or changes
one fact. Deterministic checks must flag the applicable number/reference changes;
they must not claim semantic certification when a negation reverses undetected.
Use independent bilingual review for the 34-language gold set, especially Dari,
Kurdish and the lower-resource African languages. Collect explicit failed and
unsupported calls rather than treating returned text or engine agreement as a
passing quality score. Repeated outputs, backtranslation similarity and fluent
wording are useful review aids, not evidence of perfect translation accuracy.
