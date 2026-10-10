"""Check the publishable tree, links, licence and unchanged runtime identity.
Parham (Leon) Faraji / leon-executes.
SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
import hashlib,json,re,sys
from pathlib import Path
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    problems=[]
    inventory=json.loads((ROOT/'packaging'/'repository-files.json').read_text(encoding='utf8'))['files']
    for name in inventory:
        path=ROOT/name
        if not path.is_file():problems.append('Missing: '+name);continue
        if path.stat().st_size>=25*1024**2:problems.append('Too large for browser upload: '+name)
        if path.suffix.lower() in ('.exe','.dll','.gguf','.onnx','.zip','.sqlite3'):problems.append('Binary or user data in source inventory: '+name)
        if path.suffix=='.md':
            for target in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)',path.read_text(encoding='utf8')):
                target=target.strip('<>')
                if target.startswith(('http:','https:','mailto:','#')):continue
                local=unquote(target.split('#',1)[0])
                if local and not (path.parent/local).exists():problems.append(f'Broken link: {name} -> {target}')
    identity=json.loads((ROOT/'verification'/'final-build-identity.json').read_text(encoding='utf8'))
    for name,expected in identity['runtime_source_sha256'].items():
        if sha(ROOT/name)!=expected:problems.append('Runtime source differs from released executable: '+name)
    license_meta=json.loads((ROOT/'packaging'/'license-provenance.json').read_text(encoding='utf8'))
    if sha(ROOT/'LICENSE')!=license_meta['sha256']:problems.append('Official PolyForm text differs')
    if 'Required Notice: Copyright 2026 Parham (Leon) Faraji' not in (ROOT/'NOTICE').read_text(encoding='utf8'):problems.append('Missing author notice')
    report={'successful':not problems,'repository_files':len(inventory),'runtime_sources_unchanged':not any('Runtime source' in p for p in problems),'problems':problems}
    print(json.dumps(report,indent=2));return 0 if not problems else 1
if __name__=='__main__':sys.exit(main())
