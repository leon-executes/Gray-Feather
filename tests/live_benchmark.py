"""Reproducible synthetic no-key live checks. Never reads user conversations."""
from __future__ import annotations
import dataclasses, json, time
from pathlib import Path

TEXT = 'Please bring 2 copies. The booking reference is GF-4821. Do not pay £50.'
CASES = [
    ('negation-fr', 'Do not send the file. It has not been approved.', 'en', 'fr'),
    ('negation-ar', 'I did not agree. Do not cancel the appointment.', 'en', 'ar'),
    ('negation-es', 'She has already sent 2 files. You must not send a third file.', 'en', 'es'),
    ('numbers-tr', 'The total is £38.50. Bring 2 copies, not 3. Reference GF-4821.', 'en', 'tr'),
    ('numbers-fa', 'There are 2 boxes. Do not open box 3. Reference GF-4821.', 'en', 'fa'),
    ('dari-distinct', 'Please bring 2 copies. Do not pay £50.', 'en', 'prs'),
    ('portugal', 'The bus arrives at the train station. Please bring your mobile phone.', 'en', 'pt'),
    ('sorani', 'Please bring 2 copies. Do not open the door.', 'en', 'ckb'),
    ('kurmanji', 'Please bring 2 copies. Do not open the door.', 'en', 'kmr'),
    ('punjabi-script', 'Please bring 2 copies. Do not open the door.', 'en', 'pa'),
    ('unicode-links', 'Contact test@example.com. Reference GF-4821. Bring 2 copies.', 'en', 'ar'),
    ('line-breaks', 'First line: bring 2 copies.\n\nSecond line: do not send file 3.', 'en', 'fr'),
    ('reverse-fr', 'Je n’ai pas accepté. N’annulez pas le rendez-vous.', 'fr', 'en'),
    ('reverse-ar', 'لم أوافق. لا تلغ الموعد.', 'ar', 'en'),
    ('reverse-es', 'No envíe el archivo. Todavía no ha sido aprobado.', 'es', 'en'),
    ('reverse-tr', 'Dosyayı göndermeyin. Henüz onaylanmadı.', 'tr', 'en'),
    ('reverse-zh', '请带两份副本。不要付款。', 'zh', 'en'),
]

def run(service, progress=None, include_languages=True):
    from app import VERSION
    from engine import LANGUAGES, LANG_BY_CODE
    cases = [(f'language-{item.code}', TEXT, 'en', item.code) for item in LANGUAGES if item.code != 'en'] if include_languages else []
    cases += CASES
    started = time.perf_counter()
    rows = []
    for identifier, source, source_code, target_code in cases:
        begin = time.perf_counter()
        row = {'id': identifier, 'source': source, 'source_code': source_code, 'target_code': target_code}
        try:
            value = service.translate(source, source_code, target_code, reinforce=True)
            row.update(success=True, text=value['text'], provider=value['provider'],
                       second_opinion=value.get('review_text',''), second_provider=value.get('review_provider',''),
                       backtranslation=value.get('backtranslation',''),backtranslation_provider=value.get('backtranslation_provider',''),
                       checks=value.get('checks',[]), trace=value.get('trace',[]), cached=value.get('cached',False))
        except Exception as error:
            row.update(success=False, error=str(error))
        row['seconds'] = round(time.perf_counter()-begin,3)
        rows.append(row)
        if progress: progress(row)
    return {'version': VERSION, 'scope':'Live no-key service and reinforcement checks on synthetic inputs. Availability and fact flags are measured; no universal semantic-accuracy percentage or native-speaker certification is claimed.',
            'configured_user_keys': False, 'cases':len(rows), 'successful_cases':sum(r['success'] for r in rows),
            'failed_cases':sum(not r['success'] for r in rows),
            'independent_comparisons':sum(bool(r.get('second_opinion')) for r in rows),
            'elapsed_seconds':round(time.perf_counter()-started,3), 'results': rows,
            'semantic_review':{'status':'Pending inspection of outputs; machine fact flags are not a semantic accuracy score.'}}
