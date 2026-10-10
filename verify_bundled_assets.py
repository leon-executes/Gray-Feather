"""Release gate: the selected native model packs must be present and pinned."""
import json
from pathlib import Path
from local_ai import LocalAI
import offline_omni
import offline_voice

def main():
    report = LocalAI(model='index_local').available(verify=True,deadline_seconds=60)
    if not report['available']:
        raise RuntimeError(report['reason'])
    if not all(offline_omni.available(locale) for locale in ('om-ET','ckb-IQ')):
        raise RuntimeError('Bundled Omnilingual assets are missing or altered.')
    if not offline_voice.available('fa-IR'):
        raise RuntimeError('Bundled Persian voice assets are missing or altered.')
    print(json.dumps({'local_translation':report,'offline_speech':['om-ET','ckb-IQ'],'offline_voice':['fa-IR']},ensure_ascii=True))

if __name__=='__main__':main()
