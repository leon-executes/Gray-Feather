# Rebuild the separate voice renderer

The helper is GPL-3.0-or-later; `voice_text.py` is MIT. Main Gray Feather code retains PolyForm Noncommercial. End users install nothing.

1. Use CPython 3.12 x64. From the repository root run `build_voice_helper.ps1 -Python <python.exe>`.
2. Keep the generated helper folder in `resources/voice-reserve/helper`. It uses the existing Piper eSpeak DLL/data via its working directory.
3. Run `app.py --self-test` and `verify_bundled_assets.py`, then build the portable app.

`requirements-voice-build.txt` pins the worker build. The full eSpeak corresponding source is in the parent runtime-source folder. Component licence texts are in `licenses/voice-reserve`.

For MMS conversion, create `mms-tir`, `mms-orm` and `mms-som` beside `export_mms.py`, restore the original files from the pinned repositories in `MODEL-SOURCES.json`, and install `requirements-export.txt` in a separate developer environment (CPU PyTorch is sufficient). Run `export_mms.py`. It exports dynamic-length ONNX graphs and checks multiple lengths for finite output. Copy the model/config/vocabulary/tokenizer files into their locale folders. Record the resulting hashes in `resources/voice-reserve/catalog.json`; retain original model cards and licences. Conversion checks alone do not establish speech quality.

Vekol's ONNX/config are unmodified upstream artifacts at revision `64037ebd9dedeacb7b946752d474a3a265b3f853`. Its model and original notice retain their own noncommercial terms. Runtime normalization differs intentionally: unsupported content is rejected rather than silently dropped; numeric spelling does not truncate decimals, round values or reinterpret calendars. No startup downloader runs.
