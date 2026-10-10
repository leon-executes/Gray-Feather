# Third-party notices

Gray Feather includes Python/Qt libraries, native CPU helpers and model weights. Their licences are separate from the application source. Preserve the full licence and copyright texts in `licenses`, the model notices in `resources`, and the supplied source archives in `runtime-source` when redistributing this release.

| Component | Version | Licence / source |
| --- | --- | --- |
| CPython | 3.12.14 | PSF and included component notices: `licenses/Python-LICENSE.txt`; https://github.com/python/cpython/tree/v3.12.14 |
| PySide6 Essentials and Shiboken6 | 6.11.2 | LGPL 3.0 option; https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=v6.11.2 |
| Qt Core, Gui, Widgets and platform plugins | 6.11.2 | LGPL 3.0 option and Qt component notices; https://code.qt.io/cgit/qt/qtbase.git/tree/?h=v6.11.2 |
| pywin32 | 312 | PSF-style licences in `licenses`; https://github.com/mhammond/pywin32 |
| PyInstaller bootloader | 6.22.3 | GPL with bootloader exception permitting application distribution; `licenses/PyInstaller-COPYING.txt`; https://github.com/pyinstaller/pyinstaller |
| SQLite | bundled with CPython | Public domain; https://sqlite.org/copyright.html |
| OpenSSL | 3.5.8 | Apache 2.0; `licenses/OpenSSL-3.5.8-LICENSE.txt`; https://github.com/openssl/openssl/tree/openssl-3.5.8 |
| Index-Translate-2B Q4_K_M weights | repository revision `449c9e6457b3632d328c6cbb78ae8e8e0c8059a5` | Apache 2.0; model card, licence and pinned repository metadata in `resources/local-ai/notices`; https://huggingface.co/IndexTeam/Index-Translate-2B-GGUF/tree/449c9e6457b3632d328c6cbb78ae8e8e0c8059a5 |
| llama.cpp / GGML CPU runtime | b11541, commit `f2918cabb` | MIT; `resources/local-ai/notices/llama.cpp-MIT-LICENSE.txt`; https://github.com/ggml-org/llama.cpp/tree/f2918cabb |
| LLVM OpenMP runtime | supplied with the pinned llama.cpp CPU archive | Apache 2.0 with LLVM exceptions and retained component notices; `resources/local-ai/runtime/LICENSE-LLVM-OpenMP` |
| Microsoft Visual C++ runtime DLLs | 14.44.35211.0 for the local translation runtime; other native copies retain their recorded file hashes | Microsoft redistributable terms, not an open-source licence; full text and original document in `licenses/Microsoft-VC-Runtime-2015-2022-LICENSE.txt` and `licenses/Microsoft-VC-Runtime-2015-2022-original.docx`. [Official runtime licence](https://visualstudio.microsoft.com/license-terms/vs2022-cruntime/) and [redistribution reference](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution). App-local copies originate in the pinned PySide6/Shiboken6 wheels. No installer runs. See `resources/local-ai/ASSETS.json` and the native asset manifests. |
| whisper.cpp and multilingual Whisper small-q5_1 weights | b5454 / v1.9.5 | MIT; notices in `licenses/free-speech`; https://github.com/ggml-org/whisper.cpp/tree/b5454 and https://github.com/openai/whisper |
| sherpa-onnx native CPU recognizer | 1.13.8, static MT Release without TTS | Apache 2.0; `licenses/omnilingual`; corresponding source archive in `runtime-source/omnilingual`; https://github.com/k2-fsa/sherpa-onnx/tree/v1.13.8 |
| Meta Omnilingual CTC 300M int8 weights | sherpa conversion dated 2025-11-12 | Apache 2.0; `resources/omni-asr/LICENSE` and `licenses/omnilingual/Meta-Omnilingual-LICENSE.txt`; https://github.com/facebookresearch/omnilingual-asr |
| ONNX Runtime in the native recognizer | 1.28.2 | MIT plus retained third-party notices in `licenses/omnilingual` |
| Piper / Piper phonemizer | Piper 2023.11.14-2 | MIT for these components; retained notices and helper-source provenance in `licenses/offline-voice`; https://github.com/rhasspy/piper/tree/2023.11.14-2 |
| eSpeak NG phonemizer and language data | supplied with the pinned Piper runtime | GPL 3.0; full licence and corresponding source are included in `licenses/offline-voice/eSpeak-NG-GPL.txt` and `runtime-source/offline-voice`. These components are not MIT. |
| ONNX Runtime in Piper | 1.14.1 | MIT plus retained third-party notices in `licenses/offline-voice` |
| Persian Gyro medium voice weights | creator revision `e409c5a8fb164ff6e710bfbd07b7b02c1e13949a` | Creator's MIT declaration for the exact bundled weight hash; pinned README and model/dataset attribution in `licenses/offline-voice`. See https://huggingface.co/gyroing/Persian-Piper-Model-gyro/tree/e409c5a8fb164ff6e710bfbd07b7b02c1e13949a |

The Qt/PySide shared libraries remain separate inside `_internal`, rather than statically incorporated into the application. Users may replace/rebuild those components and reverse engineer for debugging modifications to the LGPL components. Corresponding upstream source links and exact versions are above; build sources and instructions for the application are provided alongside the release. Preserve the licence texts when redistributing the runtime folder.

The bundled model weights are Index translation, Whisper dictation, Omnilingual dictation and the Persian Gyro voice. Paid provider credentials are not bundled. The free Google recognition adapter uses the public personal/testing client identifier distributed by SpeechRecognition; no user service account is required. Service names identify integrations, not endorsement. Gray Feather application code is offered by Parham (Leon) Faraji under PolyForm Noncommercial 1.0.0; see LICENSE and NOTICE. These third-party components retain their own terms.

Supplemental QtBase attribution records, their retrievable licence and copyright texts, and exact upstream source hashes are in `licenses/QtBase-6.11.2` and `licenses/manifest.json`. This upstream catalogue also describes optional modules; it does not assert that all are compiled into the Windows runtime. The application is based in part on the work of the FreeType Team. Preserve the unchanged component notices alongside the main Qt licences.

Free speech Python components include miniaudio 1.71 (MIT), CFFI 2.1.1 (MIT-0), pycparser 3.0 (BSD-3-Clause), and edge-tts 7.2.8 (LGPLv3; MIT for `srt_composer.py`). Exact async dependency versions and licence texts are in `licenses/free-speech/manifest.json`. The repository contains the unmodified edge_tts source and application build inputs so users can rebuild with a modified library; debugging modifications to LGPL components is permitted. Upstream sources: [miniaudio](https://github.com/irmen/pyminiaudio), [edge-tts](https://github.com/rany2/edge-tts/tree/7.2.8).

The Piper helper retains the licences for fmt 10.0.0, spdlog 1.12.0, nlohmann/json 3.11.2 and the embedded utf8cpp header in `licenses/offline-voice`. The original upstream Piper build fetched a floating phonemizer branch. The source collection records the nearest dated immutable helper source, exact redistributed binary hashes and build inputs; it does not claim a bit-reproducible upstream build. The complete eSpeak source archive is supplied. Gyro's original model card retains its Persian dataset link; the dataset is not relabelled CC0. Amir was evaluated but its model weights are not bundled.

Gray Feather adds only a Windows UTF-8 process manifest to the supplied sherpa recognizer executable so Unicode portable-folder and audio paths work on Windows 10 1903 or newer. This modification, original and installed hashes, and rebuild helper are recorded in `verification/omni-utf8-manifest.json`, `resources/omni-asr/SOURCES.json` and `patch_native_utf8.py`.

The retained `jfk.wav` test fixture is whisper.cpp's public-domain US presidential speech sample `samples/jfk.wav`. The current live UI workflow instead uses `long-en-speech.wav`, containing developer-authored synthetic instructions. Neither fixture is a personal microphone recording.

The bundled Oromo native-speech self-test fixture is an excerpt from FLEURS (Alexis Conneau et al., 2022), licensed CC BY 4.0. Its public source, reference, attribution, resampling change and SHA-256 are retained in `resources/test/om-native-attribution.json`. This small fixture proves native adapter execution; it is not an accuracy certification.

Unicode CLDR Gregorian month and weekday names are retained in the derived `resources/reinforcement/calendar_lexicon.json`, under the Unicode licence in `resources/reinforcement/UNICODE-LICENSE.txt`. The derived asset records exact upstream locale files and SHA-256 hashes. Source: [Unicode CLDR locale data](https://github.com/unicode-org/cldr/tree/main/common/main); [Unicode licence](https://www.unicode.org/license.txt). These source-derived calendar terms do not certify full translation quality.

## GitHub release packaging

The portable download retains the licence texts, edge_tts source, and the supplied native source archives except `runtime-source/offline-voice/onnxruntime-1.14.1.tar.gz`. That unmodified MIT upstream source archive is included in the separate [third-party sources release asset](https://github.com/leon-executes/Gray-Feather/releases/download/v1.3.0/GrayFeather-1.3.0-ThirdParty-Sources.zip), together with the full supplied source collection. It is not needed to run the app. This separation keeps the portable download below GitHub's per-asset size limit; no executable, model or runtime DLL is removed. Download links become live when the prepared release is published.
