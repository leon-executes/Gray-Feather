"""Bounded offline release check of the three added native model adapters.

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
    root = Path(__file__).resolve().parent
    result = {'scope': 'Actual bundled CPU helper execution, synthetic translation/voice text and public Oromo native speech. No network, playback, user data or aggregate accuracy claim.',
              'successful': False, 'checks': []}
    with tempfile.TemporaryDirectory(prefix='gray-native-check-') as scratch:
        for kind in ('index_translation', 'persian_voice', 'oromo_dictation'):
            start = time.monotonic()
            entry = {'kind': kind, 'successful': False}
            try:
                if kind == 'index_translation':
                    from local_ai import LocalAI
                    model = LocalAI('index_local', threads=2, max_output_tokens=128, working_directory=scratch)
                    output = model.translate('Please bring two copies.', 'en', 'fr', deadline_seconds=45)
                    if not output.get('complete') or not output.get('text'):
                        raise ValueError('Incomplete local translation response.')
                    entry.update({'source': 'Please bring two copies.', 'source_code': 'en', 'target_code': 'fr',
                                  'text': output['text'], 'provider': output['provider'], 'model': output['model'],
                                  'peak_working_set_bytes': output.get('peak_working_set_bytes'), 'complete': True})
                elif kind == 'persian_voice':
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
                else:
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
