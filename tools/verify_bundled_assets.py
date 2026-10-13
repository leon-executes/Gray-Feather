"""Release gate: the selected native model packs must be present and pinned."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import offline_omni
import offline_voice
import offline_reserve
import threading

def main():
    if (Path(__file__).resolve().parents[1] / 'resources/local-ai').exists():
        raise RuntimeError('Retired offline translation assets must not be bundled.')
    if not all(offline_omni.available(locale) for locale in ('om-ET','ckb-IQ')):
        raise RuntimeError('Bundled Omnilingual assets are missing or altered.')
    if not offline_voice.available('fa-IR'):
        raise RuntimeError('Bundled Persian voice assets are missing or altered.')
    for locale in ('ti-ET','om-ET','ckb-IQ','so-SO'):
        if not offline_reserve.available(locale,'neural'):
            raise RuntimeError('Restore the complete neural voice pack: '+locale)
        offline_reserve._validate(offline_reserve.resources()/'models'/locale,offline_reserve._entry(locale),threading.Event())
    if not offline_reserve.available('sd-PK','basic'):
        raise RuntimeError('Restore the bundled basic voice worker.')
    print(json.dumps({'offline_text_translation':False,'offline_speech':['om-ET','ckb-IQ'],'offline_voice':['fa-IR']},ensure_ascii=True))

if __name__=='__main__':main()
