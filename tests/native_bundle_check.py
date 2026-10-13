"""Bounded offline release check of the bundled native model adapters.

Uses only synthetic text and the attributed public Oromo fixture. It neither
plays audio nor sends network requests, and does not claim translation fidelity.
"""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import wave

def run():
    root = Path(__file__).resolve().parents[1]
    result = {'scope': 'Actual bundled CPU helper execution, synthetic voice text and public Oromo native speech. No network, playback, user data or aggregate accuracy claim.',
              'successful': False, 'checks': []}
    with tempfile.TemporaryDirectory(prefix='gray-native-check-') as scratch:
        for kind in ('persian_voice', 'oromo_dictation',
                     'voice_tigrinya','voice_oromo','voice_sorani','voice_somali',
                     'basic_kurmanji','basic_sindhi','basic_french'):
            start = time.monotonic()
            entry = {'kind': kind, 'successful': False}
            try:
                if kind == 'persian_voice':
                    import offline_voice
                    phrase = 'دو نسخه بیاورید. در را باز نکنید.'
                    output = offline_voice.prepare(phrase, 'fa-IR', {'_audio_dir': scratch}, timeout=20)
                    with wave.open(io.BytesIO(output['audio']), 'rb') as audio:
                        if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getframerate() != 16000 or audio.getnframes() <= 0:
                            raise ValueError('Native voice returned invalid complete PCM.')
                        seconds = audio.getnframes() / audio.getframerate()
                    entry.update({'source': phrase, 'locale': 'fa-IR', 'provider': output['provider'],
                                  'model': output['model'], 'audio_seconds': round(seconds, 4),
                                  'wav_bytes': len(output['audio']), 'wav_sha256': hashlib.sha256(output['audio']).hexdigest(),
                                  'complete_preparation': output['complete_preparation'], 'played': False})
                elif kind == 'oromo_dictation':
                    import offline_omni
                    fixture = root / 'resources' / 'test' / 'om-native.wav'
                    attribution = json.loads(fixture.with_name('om-native-attribution.json').read_text(encoding='utf-8'))
                    audio = fixture.read_bytes()
                    if hashlib.sha256(audio).hexdigest() != attribution['audio_sha256']:
                        raise ValueError('The bundled public Oromo fixture changed.')
                    output = offline_omni.recognize(audio, 'om-ET', {'_audio_dir': scratch})
                    if not output.get('complete') or not output.get('text'):
                        raise ValueError('Incomplete native Oromo response.')
                    entry.update({'locale': 'om-ET', 'text': output['text'], 'reference': attribution['reference'],
                                  'provider': output['provider'], 'engine': output['engine'], 'complete': True,
                                  'fixture_sha256': attribution['audio_sha256'], 'fixture_licence': attribution['licence'],
                                  'language_conditioned': output['language_conditioned']})
                else:
                    import offline_reserve
                    phrases={
                        'voice_tigrinya':('ti-ET','እቲ ስነ-ጥበበኛ ሓደ ክልተ 09፡30'),
                        'voice_oromo':('om-ET','Koppii lama fidaa.'),
                        'voice_sorani':('ckb-IQ','تکایە دوو کۆپی بهێنە. 12.5'),
                        'voice_somali':('so-SO','Laba nuqul keen. 12'),
                        'basic_kurmanji':('ku-TR','Ji kerema xwe du kopiyan bîne.'),
                        'basic_sindhi':('sd-PK','مهرباني ڪري ٻه ڪاپيون آڻيو.'),
                        'basic_french':('fr-FR','Apportez deux copies.')}
                    locale,phrase=phrases[kind]
                    output=offline_reserve.prepare(phrase,locale,'basic' if kind.startswith('basic_') else 'neural',{'_audio_dir':scratch},timeout=30)
                    entry.update({k:v for k,v in output.items() if k!='audio'})
                    entry.update({'played':False,'wav_bytes':len(output['audio']),
                                  'wav_sha256':hashlib.sha256(output['audio']).hexdigest()})
                entry['successful'] = True
            except Exception as error:
                entry['error'] = str(error)
                entry['error_type'] = type(error).__name__
            entry['elapsed_ms'] = round((time.monotonic() - start) * 1000)
            result['checks'].append(entry)
    result['successful'] = all(row['successful'] for row in result['checks'])
    result['private_scratch_removed'] = not Path(scratch).exists()
    return result

if __name__ == '__main__':
    print(json.dumps(run(), ensure_ascii=False, indent=2))
