"""Document exact app speech mappings; declared support is not an accuracy score."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import engine
import speech
import offline_voice
import offline_omni

QUALITY_NOTES={tag:'Paired public-reference ASR tests and voice diagnostics are reported in verification/gap-validation-20261012.md. These are not native-listener voice ratings or universal semantic accuracy scores.' for tag in speech.OMNILINGUAL_LOCALES}


def build_registry():
    rows=[]
    for language in engine.LANGUAGES:
        tag=language.bcp47
        routes=['offline_whisper' if p=='offline' else p for p in speech.recognition_routes(tag)]
        voice=speech.voice_route_plan(tag)
        online_voices=[p for p in voice['providers'] if not p.startswith('offline_') and p!='windows']
        bundled=offline_voice.VOICE_MODELS.get(tag)
        rows.append({'code':language.code,'name':language.name,'exact_locale':tag,
          'dictation':{'automatic_order':routes,'online_google_declared':tag in speech.GOOGLE_STT_LOCALES,
                      'bundled_whisper_declared':tag in speech.WHISPER_LOCALES,
                      'bundled_omnilingual_measured_route':tag in speech.OMNILINGUAL_LOCALES,
                      'bundled_omnilingual_assets_present':offline_omni.available(tag),
                      'omnilingual_language_conditioned':False,
                      'optional_azure_declared':tag in speech.AZURE_STT_LOCALES,
                      'policy':'Google first with Omnilingual reserve; Whisper stays sidelined.' if tag=='fa-IR' else 'Review names, quantities and negation.',
                      'gap':None if routes else 'No exact free/bundled dictation route; type the turn. No language is substituted.'},
          'voice':{'automatic_order':voice['providers'],'edge_voice_mapping':speech.AZURE_VOICES.get(tag),
                   'google_voice_mapping':speech.GOOGLE_TTS_LOCALES.get(tag),'bundled_voice':bundled,
                   'bundled_assets_present':offline_voice.available(tag) or any(p.startswith('offline_') for p in voice['providers']),'windows_requires_exact_installed_locale':True,
                   'offline_selection_order':speech.voice_route_plan(tag,{'voice_provider':'offline'})['providers'],
                   'gap':None if speech.voice_supported(tag) else 'Only an exact installed Windows voice could serve this locale; none is assumed.'},
          'quality_basis':QUALITY_NOTES.get(tag,'Exact provider/model mapping only; no representative semantic accuracy claim is made for this locale.'),
          'measurement_status':'Public reference recordings plus synthetic voice diagnostics; see gap-validation report.' if tag in QUALITY_NOTES else 'Declared mapping; completion and fidelity must be evaluated separately.'})
    return {'version':3,'app_version':'1.3.2','scope':'All 34 app locales, including explicitly labelled pronunciation approximations. Mapping, live completion, and meaning fidelity are different claims.',
      'free_defaults':True,'paid_voice_requires_explicit_azure_selection_and_key':True,
      'hierarchy_rules':['Language-specific ASR routing comes from paired public recordings; documented unsupported cloud candidates remain disabled.',
                         'Ten measured routes use Omnilingual, often as the default or as a reserve. Its published inventory does not enable every language.',
                         'Edge voice and the best mapped reserve prepare concurrently; a complete reserve may win after 350 ms preference grace.',
                         'Dari prefers female Persian Edge with local Piper reserve, explicitly approximate pronunciation. Working local gap voices stay first. Kurmanji and Sindhi prefer labelled Turkish/Urdu substitutes over robotic voices; recovered webapp routes reserve other gap languages. Offline and Basic never upload text.',
                         'Only validated whole audio can be played. Cancellation kills active worker/helper and never plays a partial passage.',
                         'Recent observed failures change the current session auto order; network services are never declared dependable from a mapping or HEAD request.'],
      'uncovered_free_dictation':[r['exact_locale'] for r in rows if not r['dictation']['automatic_order']],
      'uncovered_mapped_free_voice':[r['exact_locale'] for r in rows if r['voice']['gap']],
      'source_links':{
        'azure_speech_languages':'https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support',
        'google_cloud_languages_context_only':'https://cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages',
        'legacy_google_client':'https://github.com/Uberi/speech_recognition/blob/master/speech_recognition/recognizers/google.py',
        'edge_client':'https://github.com/rany2/edge-tts',
        'google_tts_language_registry':'https://github.com/pndurette/gTTS/blob/main/gtts/langs.py',
        'whisper_languages':'https://github.com/openai/whisper/blob/main/whisper/tokenizer.py',
        'whisper_native':'https://github.com/ggml-org/whisper.cpp',
        'piper_native_release':'https://github.com/rhasspy/piper/releases/tag/2023.11.14-2',
        'persian_model_card':'https://huggingface.co/rhasspy/piper-voices/blob/main/fa/fa_IR/gyro/medium/MODEL_CARD',
        'persian_creator_pinned_MIT':'https://huggingface.co/gyroing/Persian-Piper-Model-gyro/blob/e409c5a8fb164ff6e710bfbd07b7b02c1e13949a/README.md',
        'omnilingual_primary':'https://github.com/facebookresearch/omnilingual-asr',
        'omnilingual_native_models':'https://k2-fsa.github.io/sherpa/onnx/omnilingual-asr/models.html',
        'native_recording_publisher':'https://huggingface.co/datasets/google/fleurs'},
      'language_count':len(rows),'languages':rows}

if __name__=='__main__':
    directory=Path(__file__).resolve().parents[1]/'verification'; directory.mkdir(exist_ok=True)
    output=directory/'speech-capabilities-34.json'; output.write_text(json.dumps(build_registry(),ensure_ascii=False,indent=2),encoding='utf-8')
    print(str(output))
