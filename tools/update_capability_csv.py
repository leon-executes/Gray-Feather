"""Development-only export of current exact mappings; never an accuracy score."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import csv
import json
import index_engine
import speech
import offline_voice
import offline_reserve
from generate_speech_registry import build_registry

ROOT = Path(__file__).resolve().parents[1]

def main():
    target = ROOT / 'APP-CAPABILITIES.csv'
    with target.open(encoding='utf-8', newline='') as source:
        reader = csv.DictReader(source)
        fields = [n for n in reader.fieldnames if n != 'index_local_exact_mapping']
        rows = list(reader)
    added = ['index_web_exact_mapping',
             'whisper_dictation_available', 'omnilingual_dictation_available',
             'offline_voice_available', 'offline_voice_model', 'free_voice_route']
    fields.extend(name for name in added if name not in fields)
    registry = build_registry()
    lookup = {row['code']: row for row in registry['languages']}
    for row in rows:
        row.pop('index_local_exact_mapping', None)
        info = lookup[row['app_code']]
        locale = row['speech_locale']
        routes = info['dictation']['automatic_order']
        whisper = locale in speech.WHISPER_LOCALES
        omni = locale in speech.OMNILINGUAL_LOCALES
        voice = offline_voice.VOICE_MODELS.get(locale)
        row.update({
            'default_dictation_available': bool(routes),
            'default_dictation_route': ' -> '.join(routes) if routes else 'Unavailable',
            'google_dictation_available': locale in speech.GOOGLE_STT_LOCALES,
            'offline_dictation_available': whisper or omni,
            'offline_model': ('Omnilingual CTC 300M int8 (unconditioned language)' if omni else
                              'Whisper small-q5_1 multilingual model' if whisper else ''),
            'free_voice_locale': locale if speech.voice_supported(locale) else '',
            'index_web_exact_mapping': row['app_code'] in index_engine.LANGUAGES,
            'whisper_dictation_available': whisper,
            'omnilingual_dictation_available': omni,
            'offline_voice_available': any(p.startswith('offline_') for p in info['voice']['automatic_order']),
            'offline_voice_model': voice['id'] if voice else ' / '.join(p for p in info['voice']['automatic_order'] if p.startswith('offline_')),
            'free_voice_route': ' -> '.join(info['voice']['automatic_order']),
        })
        notes = 'MyMemory has mixed provenance and is not independent reinforcement. Registry coverage is not measured accuracy. '
        if row['app_code'] == 'prs':
            notes += 'Bing prs is distinct Dari; Persian translation is a flagged approximation. Index does not support exact Dari. '
        if locale == 'fa-IR':
            notes += 'Whisper stays sidelined; Omnilingual is now a measured offline dictation reserve. Gyro remains the preferred local voice. '
        if omni:
            notes += 'Public-reference ASR trials are in verification/gap-validation-20261012.md. CTC is not language-conditioned; short clips can be misidentified. '
        if locale in speech.AUTO_WHISPER_SIDELINED:
            notes += 'Whisper remains explicitly selectable but is sidelined from Automatic because of poor native-reference results. '
        if locale in offline_reserve.APPROXIMATE:
            notes += 'Basic reserve: approximate ' + offline_reserve.APPROXIMATE[locale] + '. '
        if locale == 'sd-PK':
            notes += 'Basic Sindhi voice has weak diagnostic intelligibility; no native-listener validation. '
        if not routes:
            notes += 'No exact free/bundled dictation route; typing remains available. No dialect is substituted. '
        if info['voice']['gap']:
            notes += 'No mapped free/bundled voice. Only a working exact-locale installed Windows voice can provide speech; none is assumed. '
        if locale == 'zh-CN':
            notes += 'A local synthetic dictation fixture substituted one copy-request character. '
        notes += 'Published model/provider language coverage does not establish semantic fidelity. See verification/speech-capabilities-34.json.'
        row['notes'] = notes
    with target.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fields)
        writer.writeheader()
        writer.writerows(rows)
    counts = {'languages': len(rows),
              'default_dictation': sum(row['default_dictation_available'] for row in rows),
              'whisper_dictation': sum(row['whisper_dictation_available'] for row in rows),
              'omnilingual_dictation': sum(row['omnilingual_dictation_available'] for row in rows),
              'free_or_bundled_voice': sum(bool(row['free_voice_locale']) for row in rows),
              'bundled_voice': sum(row['offline_voice_available'] for row in rows),
              'index_exact_mapping': sum(row['index_web_exact_mapping'] for row in rows),
              'dictation_gaps': registry['uncovered_free_dictation'],
              'voice_gaps': registry['uncovered_mapped_free_voice'],
              'scope': 'Configured routes include explicitly labelled pronunciation approximations; counts are not accuracy, native-voice certification or service availability measurements.'}
    assert counts['languages'] == 34 and counts['default_dictation'] == 34
    assert counts['omnilingual_dictation'] == 10 and counts['index_exact_mapping'] == 33
    (ROOT / 'verification' / 'app-capability-counts.json').write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(counts, ensure_ascii=False))

if __name__ == '__main__':
    main()
