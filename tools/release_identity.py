"""Bind the final executable to unchanged application sources during packaging."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
FILES=('app.py','engine.py','ui.py','speech.py','offline_voice.py','offline_omni.py',
       'offline_reserve.py','voice_helper.py','voice_text.py','safe_speech.py',
       'reinforcement.py','reinforced_engine.py','index_engine.py',
       'settings.py','docx_export.py','tests/native_bundle_check.py','language_routes.json')
FILES = tuple(sorted(set(FILES) | {p.relative_to(ROOT).as_posix() for folder in ('tests', 'tools') for p in (ROOT/folder).glob('*.py')} | {'build.ps1'}))

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--executable',type=Path);args=parser.parse_args()
    snapshot=ROOT/'verification/build-source-snapshot.json'
    hashes={name:sha(ROOT/name) for name in FILES}
    if args.executable:
        if hashes!=json.loads(snapshot.read_text(encoding='utf8')):
            raise RuntimeError('Application sources changed during the build.')
        result={'version':'1.4.1','executable_sha256':sha(args.executable),
                'runtime_source_sha256':hashes,'sources_unchanged_during_build':True}
        (ROOT/'verification/final-build-identity.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    else:snapshot.write_text(json.dumps(hashes,indent=2),encoding='utf8')
if __name__=='__main__':main()
