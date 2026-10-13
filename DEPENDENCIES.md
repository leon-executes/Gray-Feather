# Dependencies

## Running the release

**Install nothing extra.** Extract the Windows x64 portable ZIP and keep the complete folder together. It includes Python, Qt, native helpers, runtime DLLs, model weights and licence texts. Word is not needed for DOCX export.

- Windows 10 version 1903+ or Windows 11, x64.
- Internet for automatic free translation and supported online speech routes.
- Microphone permission for recording; a working output device for playback.

No personal API key is needed for the default workflow. Optional paid-provider accounts are separate and are not silently enabled by Automatic mode. Service availability and terms belong to each provider.

## Bundled engines and models

| Component | Role | Official source |
| --- | --- | --- |
| Whisper small-q5_1 / whisper.cpp | Supported offline dictation | [whisper.cpp](https://github.com/ggml-org/whisper.cpp/tree/b5454) · [Whisper](https://github.com/openai/whisper) |
| Omnilingual CTC 300M int8 / sherpa-onnx | Ten measured local recognition routes; see the current coverage report | [Model project](https://github.com/facebookresearch/omnilingual-asr) · [Runtime](https://github.com/k2-fsa/sherpa-onnx/tree/v1.13.8) |
| Persian Gyro / Piper | Local Persian voice reserve | [Voice and model terms](https://huggingface.co/gyroing/Persian-Piper-Model-gyro/tree/e409c5a8fb164ff6e710bfbd07b7b02c1e13949a) · [Piper](https://github.com/rhasspy/piper/tree/2023.11.14-2) |
| eSpeak NG / ONNX Runtime | Voice phonemization and model execution | [eSpeak NG](https://github.com/espeak-ng/espeak-ng) · [ONNX Runtime](https://github.com/microsoft/onnxruntime) |
| Unicode CLDR | Calendar terminology checks | [CLDR](https://github.com/unicode-org/cldr) |

Exact files, byte sizes and SHA-256 values: [asset manifest](packaging/assets-manifest.json). Full version/licence mapping: [third-party notices](THIRD-PARTY-NOTICES.md). In particular, eSpeak NG has GPL terms; Qt/PySide and edge-tts have LGPL terms. They are not relicensed under PolyForm.

## Online routes

| Purpose | Integrations |
| --- | --- |
| Free automatic translation | [Google Translate](https://translate.google.com/), [Bing Translator](https://www.bing.com/translator), [Index Translate](https://github.com/bilibili/Index-Translate), [MyMemory](https://mymemory.translated.net/doc/spec.php) |
| Free speech | Google recognition, [edge-tts](https://github.com/rany2/edge-tts), supported Google speech playback |
| Optional configured services | [Azure Translator](https://learn.microsoft.com/azure/ai-services/translator/), [Google Cloud Translation](https://cloud.google.com/translate/docs), [DeepL](https://developers.deepl.com/docs), [LibreTranslate](https://github.com/LibreTranslate/LibreTranslate), [Lingva](https://github.com/thedaviddelta/lingva-translate) |

Public web routes have no availability guarantee. A service name does not imply endorsement or a production API agreement. Language eligibility and provenance are separate from whether a request happens to succeed.

## Development only

Install [CPython 3.12 x64](https://www.python.org/downloads/windows/). Follow [BUILD.md](BUILD.md); `build.ps1` creates a virtual environment and installs the exact [pinned requirements](requirements-build.txt).

| Package family | Purpose | Source |
| --- | --- | --- |
| PySide6 Essentials / Shiboken6 | Native Qt interface | [Qt for Python](https://doc.qt.io/qtforpython-6/) |
| PyInstaller / hooks | Portable executable packaging | [PyInstaller](https://pyinstaller.org/) |
| pywin32 | Windows integration | [pywin32](https://github.com/mhammond/pywin32) |
| miniaudio / CFFI / pycparser | Audio decoding and native bindings | [miniaudio](https://github.com/irmen/pyminiaudio) · [CFFI](https://cffi.readthedocs.io/) |
| edge-tts / aiohttp and dependencies | Free neural voice transport | [edge-tts](https://github.com/rany2/edge-tts) · [aiohttp](https://docs.aiohttp.org/) |
| certifi / tabulate | TLS certificates and command-line formatting | [certifi](https://github.com/certifi/python-certifi) · [tabulate](https://github.com/astanin/python-tabulate) |

All direct and transitive versions are pinned. Python's standard library provides SQLite, HTTP utilities and DOCX/ZIP writing; there is no database server or Office automation dependency.

## Voice reserves added in 1.3.1

End users install nothing. The portable worker contains NumPy 2.2.6, ONNX Runtime 1.23.2 and uroman 1.3.1.1. It runs only while rendering speech, with two inference threads and cancellation/deadline guards. PyTorch/Transformers are conversion tools and are **not bundled**.

[MMS models](https://huggingface.co/facebook/mms-tts) cover the selected Tigrinya, Oromo and Somali voices. [Vekol](https://huggingface.co/RevgeAI/vekol-tts-ckb-edge) supplies Sorani. [eSpeak NG](https://github.com/espeak-ng/espeak-ng) supplies basic voices using the data already distributed with Piper. Exact weights and hashes are in `resources/voice-reserve/catalog.json`. [Licence texts and component versions](licenses/voice-reserve/manifest.json) and [helper source/build inputs](runtime-source/voice-reserve/README.md) are supplied.

The complete 1.4.1 Windows ZIP includes every voice model. No companion voice pack or archive joiner is required. Developer-only third-party sources are supplied separately in the same release. [Coverage and limitations](docs/SPEECH-COVERAGE.md).
