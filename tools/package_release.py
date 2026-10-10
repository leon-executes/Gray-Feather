"""Package the tested release for GitHub, preserving its executable and models.
Parham (Leon) Faraji / leon-executes.
SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VERSION='1.3.0'
PREFIX='GrayFeather-'+VERSION
# This MIT upstream source archive is not used at runtime. The complete source
# collection is provided in a companion release asset. GPL source stays bundled.
SEPARATE='runtime-source/offline-voice/onnxruntime-1.14.1.tar.gz'
LIMIT=2*1024**3
DOCS=('README.md','LICENSE','NOTICE','AUTHORS.md','DEPENDENCIES.md','BUILD.md','CHANGELOG.md','THIRD-PARTY-NOTICES.md','REINFORCEMENT.md','FREE_SPEECH_RESEARCH.md','APP-CAPABILITIES.csv')

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--upstream-sources',type=Path,default=ROOT,help='Directory containing runtime-source/')
    args=parser.parse_args()
    source=args.portable.resolve();output=args.output.resolve()
    if source==output or output.is_relative_to(source):raise ValueError('Output must be outside the portable folder')
    identity=json.loads((ROOT/'verification/final-build-identity.json').read_text(encoding='utf8'))
    if sha(source/'GrayFeather.exe')!=identity['executable_sha256']:raise ValueError('Executable does not match release identity')
    for name,expected in identity['runtime_source_sha256'].items():
        if sha(ROOT/name)!=expected:raise ValueError('Runtime source changed: '+name)
    resources=json.loads((ROOT/'packaging/assets-manifest.json').read_text(encoding='utf8'))['files']
    for name,expected in resources.items():
        p=source/'_internal'/name if name.startswith('resources/') else args.upstream_sources/name
        if not p.is_file() or p.stat().st_size!=expected['bytes'] or sha(p)!=expected['sha256']:raise ValueError('Asset does not match: '+name)
    output.mkdir(parents=True,exist_ok=True)
    names=[PREFIX+'-GitHub-Windows-x64.zip',PREFIX+'-GitHub-Source.zip',PREFIX+'-ThirdParty-Sources.zip',PREFIX+'-GitHub-SHA256SUMS.txt',PREFIX+'-GitHub-packaging.json']
    for name in names:
        if (output/name).exists():raise FileExistsError('Existing artifact preserved: '+name)
    files={}
    for p in source.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(source).as_posix()
        if rel==SEPARATE or rel=='RELEASE-SHA256.json' or rel.startswith(('verification/','GrayFeather-data/','docs/','assets/','packaging/')):continue
        if p.suffix.lower() in ('.sqlite','.sqlite3','.db') or p.name=='settings.json':raise ValueError('User data found in portable input: '+rel)
        files[rel]=p
    for name in DOCS:files[name]=ROOT/name
    inventory=json.loads((ROOT/'packaging/repository-files.json').read_text(encoding='utf8'))['files']
    for name in inventory:
        if name.startswith(('docs/','assets/','packaging/','verification/')):files[name]=ROOT/name
    # Existing exploratory reports contain host paths and are not required to run
    # the app. Publish curated verification notes and exact source identity.
    file_hashes={name:sha(p) for name,p in sorted(files.items())}
    portable_path=output/names[0]
    print('Writing portable ZIP...',flush=True)
    with zipfile.ZipFile(portable_path,'x',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for name,p in sorted(files.items()):z.write(p,'GrayFeather/'+name)
        z.writestr('GrayFeather/RELEASE-SHA256.json',json.dumps({'version':VERSION,'packaging':'github.1','files':file_hashes},indent=2))
    if portable_path.stat().st_size>=LIMIT:raise RuntimeError('Portable archive exceeds GitHub limit')
    print('Writing clean source ZIP...',flush=True)
    with zipfile.ZipFile(output/names[1],'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in inventory:z.write(ROOT/name,'Gray-Feather/'+name)
    print('Writing third-party source ZIP...',flush=True)
    with zipfile.ZipFile(output/names[2],'x',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
        for name in resources:
            if name.startswith('runtime-source/'):z.write(args.upstream_sources/name,name)
        z.write(ROOT/'THIRD-PARTY-NOTICES.md','THIRD-PARTY-NOTICES.md')
        z.write(ROOT/'LICENSE','LICENSE')
        z.write(ROOT/'NOTICE','NOTICE')
        for p in (ROOT/'licenses').rglob('*'):
            if p.is_file():z.write(p,p.relative_to(ROOT).as_posix())
    artifacts={}
    for name in names[:3]:
        p=output/name
        if p.stat().st_size>=LIMIT:raise RuntimeError('Release asset exceeds GitHub limit: '+name)
        artifacts[name]={'bytes':p.stat().st_size,'sha256':sha(p)}
    (output/names[3]).write_text(''.join(v['sha256']+'  '+k+'\n' for k,v in artifacts.items()),encoding='ascii')
    record={'version':VERSION,'packaging_revision':'github.1','runtime_behavior_changed':False,'executable_sha256':identity['executable_sha256'],'portable_files':len(files)+1,'source_files':len(inventory),'excluded_optional_source_archive':SEPARATE,'all_release_assets_under_2_GiB':True,'artifacts':artifacts}
    (output/names[4]).write_text(json.dumps(record,indent=2)+'\n',encoding='utf8')
    print(json.dumps(record),flush=True)

if __name__=='__main__':main()
