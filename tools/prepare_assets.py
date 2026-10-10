"""Restore pinned release assets. Parham (Leon) Faraji / leon-executes.

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
No service calls, implicit downloads, deletion or changed-file overwrites.
"""
import argparse,hashlib,json,os,shutil,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def valid(path,expected):
    return path.is_file() and path.stat().st_size==expected['bytes'] and digest(path)==expected['sha256']

def safe_destination(name):
    rel=PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name or rel.parts[0] not in ('resources','runtime-source'):
        raise ValueError('Unsafe asset path: '+name)
    path=ROOT.joinpath(*rel.parts)
    if not path.resolve().is_relative_to(ROOT):raise ValueError('Asset destination escapes repository: '+name)
    return path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable',type=Path,required=True,help='Extracted folder containing GrayFeather.exe')
    parser.add_argument('--sources',type=Path,required=True,help='ThirdParty-Sources ZIP or directory containing runtime-source/')
    args=parser.parse_args()
    if not (args.portable/'GrayFeather.exe').is_file():parser.error('--portable must contain GrayFeather.exe')
    resources=args.portable/'_internal'/'resources'
    if not resources.is_dir():parser.error('The portable resource folder is missing')
    manifest=json.loads((ROOT/'packaging'/'assets-manifest.json').read_text(encoding='utf8'))['files']
    source_zip=zipfile.ZipFile(args.sources) if args.sources.is_file() else None
    restored=present=0
    try:
        # Validate every destination before beginning any copy.
        for name,expected in manifest.items():
            target=safe_destination(name)
            if target.exists() and not valid(target,expected):raise RuntimeError('Preserved changed existing asset: '+name)
        for name,expected in manifest.items():
            target=safe_destination(name)
            if valid(target,expected):present+=1;continue
            target.parent.mkdir(parents=True,exist_ok=True)
            temporary=target.with_name(target.name+'.part')
            if temporary.exists():raise RuntimeError('Preserved existing partial file: '+str(temporary))
            if name.startswith('resources/'):
                source=resources/Path(name).relative_to('resources')
                if not valid(source,expected):raise RuntimeError('Source asset missing or failed SHA-256: '+name)
                shutil.copyfile(source,temporary)
            elif source_zip:
                info=source_zip.getinfo(name)
                if info.file_size!=expected['bytes']:raise RuntimeError('Source archive size mismatch: '+name)
                with source_zip.open(info) as src,temporary.open('xb') as dst:shutil.copyfileobj(src,dst,4*1024*1024)
            else:
                source=args.sources/name
                if not valid(source,expected):raise RuntimeError('Source asset missing or failed SHA-256: '+name)
                shutil.copyfile(source,temporary)
            if not valid(temporary,expected):raise RuntimeError('Copied asset failed SHA-256; partial retained: '+name)
            os.replace(temporary,target);restored+=1
        report={'version':'1.3.0','verified':present+restored,'restored':restored,'already_present':present,'network_used':False}
        (ROOT/'.assets-ready.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report))
    finally:
        if source_zip:source_zip.close()

if __name__=='__main__':main()
