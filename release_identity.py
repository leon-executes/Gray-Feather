"""Bind the final executable to unchanged application sources during packaging."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FILES=('app.py','engine.py','ui.py','speech.py','offline_voice.py','offline_omni.py',
       'reinforcement.py','reinforced_engine.py','index_engine.py','local_ai.py',
       'settings.py','docx_export.py','native_bundle_check.py','language_routes.json')
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--executable',type=Path);args=parser.parse_args()
    snapshot=ROOT/'verification/build-source-snapshot.json'
    hashes={name:sha(ROOT/name) for name in FILES}
    if args.executable:
        if hashes!=json.loads(snapshot.read_text(encoding='utf8')):
            raise RuntimeError('Application sources changed during the build.')
        result={'version':'1.3.0','executable_sha256':sha(args.executable),
                'runtime_source_sha256':hashes,'sources_unchanged_during_build':True}
        (ROOT/'verification/final-build-identity.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    else:snapshot.write_text(json.dumps(hashes,indent=2),encoding='utf8')
if __name__=='__main__':main()
