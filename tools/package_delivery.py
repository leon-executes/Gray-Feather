"""Build verified Windows, source and GitHub download archives."""
import argparse, hashlib, json, shutil, subprocess, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.4.1'
PREFIX = 'GrayFeather-' + VERSION

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def zip_files(destination, files):
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted(files.items()):
            archive.write(path, name)

def github_parts(archive, output, part_size=1900 * 1024**2):
    folder = output / 'GitHub-Release'
    folder.mkdir(exist_ok=False)
    parts = []
    with archive.open('rb') as source:
        while True:
            block = source.read(min(4 * 1024**2, part_size))
            if not block: break
            target = folder / (archive.name + '.part' + str(len(parts) + 1))
            with target.open('xb') as stream:
                remaining = part_size
                while block:
                    stream.write(block)
                    remaining -= len(block)
                    if remaining == 0: break
                    block = source.read(min(4 * 1024**2, remaining))
            parts.append({'name': target.name, 'bytes': target.stat().st_size, 'sha256': sha(target)})
    manifest = {'archive': archive.name, 'sha256': sha(archive), 'parts': parts}
    script = (ROOT / 'tools/join_download.ps1').read_text(encoding='utf-8').replace('DOWNLOAD_MANIFEST', json.dumps(manifest, indent=2))
    (folder / 'Join-GrayFeather.ps1').write_text(script, encoding='utf-8')
    (folder / 'Join-GrayFeather.cmd').write_text('@echo off\r\n"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0Join-GrayFeather.ps1"\r\nif errorlevel 1 (echo Assembly failed. Read the message above. & pause & exit /b 1)\r\npause\r\n', encoding='ascii')
    return manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sevenzip', type=Path, help='Official 7za.exe for stronger standard ZIP compression')
    args = parser.parse_args()
    source, output = args.portable.resolve(), args.output.resolve()
    if output.is_relative_to(source): raise ValueError('Output must be outside the portable folder.')
    output.mkdir(parents=True, exist_ok=True)
    identity = json.loads((ROOT / 'verification/final-build-identity.json').read_text(encoding='utf-8'))
    if sha(source / 'GrayFeather.exe') != identity['executable_sha256']: raise ValueError('Executable differs from the verified build.')
    for name, expected in identity['runtime_source_sha256'].items():
        if sha(ROOT / name) != expected: raise ValueError('Source changed after the build: ' + name)
    assets = json.loads((ROOT / 'packaging/assets-manifest.json').read_text(encoding='utf-8'))['files']
    for name, expected in assets.items():
        path = source / '_internal' / name if name.startswith('resources/') else ROOT / name
        if sha(path) != expected['sha256']: raise ValueError('Asset verification failed: ' + name)
    files = {p.relative_to(source).as_posix(): p for p in source.rglob('*') if p.is_file()}
    if any('/local-ai/' in n or n.lower().endswith(('.gguf', '/llama.dll', '/llama-cli.exe')) for n in files):
        raise ValueError('Retired offline text AI found in portable folder.')
    if any('GrayFeather-data' in n or n.endswith(('.db', '.sqlite', '.sqlite3', '/settings.json')) for n in files):
        raise ValueError('Private data in release folder.')
    hashes = {name: sha(path) for name, path in sorted(files.items())}
    archive = output / (PREFIX + '-Windows-x64.zip')
    if archive.exists(): raise FileExistsError(archive)
    print('Compressing complete Windows app...', flush=True)
    with tempfile.TemporaryDirectory(prefix='.gray-package-', dir=output) as scratch:
        staged = Path(scratch) / PREFIX
        shutil.copytree(source, staged)
        (staged / 'RELEASE-SHA256.json').write_text(json.dumps({'version': VERSION, 'files': hashes}, indent=2), encoding='utf-8')
        if args.sevenzip:
            subprocess.run([str(args.sevenzip.resolve()), 'a', '-tzip', str(archive), PREFIX, '-mx=5', '-mm=Deflate', '-mmt=4', '-bso0'], cwd=scratch, check=True)
        else:
            zip_files(archive, {p.relative_to(Path(scratch)).as_posix(): p for p in staged.rglob('*') if p.is_file()})
    print('Checking every archive entry...', flush=True)
    with zipfile.ZipFile(archive) as zipped:
        actual = set()
        for item in zipped.infolist():
            if item.is_dir(): continue
            if not item.filename.startswith(PREFIX + '/'): raise ValueError('Invalid archive root.')
            name = item.filename[len(PREFIX) + 1:]
            if name == 'RELEASE-SHA256.json': continue
            if name not in hashes or name in actual: raise ValueError('Unexpected or duplicate entry: ' + name)
            actual.add(name)
            with zipped.open(item) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != hashes[name]: raise ValueError('Archive content differs: ' + name)
        if actual != set(hashes): raise ValueError('Archive is incomplete.')
    inventory = json.loads((ROOT / 'packaging/repository-files.json').read_text(encoding='utf-8'))['files']
    source_zip = output / (PREFIX + '-Source.zip')
    zip_files(source_zip, {'Gray-Feather/' + n: ROOT / n for n in inventory})
    third_party = output / (PREFIX + '-ThirdParty-Sources.zip')
    zip_files(third_party, {p.relative_to(ROOT).as_posix(): p for p in (ROOT / 'runtime-source').rglob('*') if p.is_file()})
    checks = {p.name: sha(p) for p in (archive, source_zip, third_party)}
    (output / (PREFIX + '-SHA256SUMS.txt')).write_text(''.join(h + '  ' + n + '\n' for n, h in checks.items()), encoding='ascii')
    parts = github_parts(archive, output) if archive.stat().st_size >= 2 * 1024**3 else None
    result = {'version': VERSION, 'archive': archive.name, 'bytes': archive.stat().st_size, 'sha256': checks[archive.name], 'all_speech_and_voice_models_included': True, 'offline_text_ai_included': False, 'compression': 'standard ZIP DEFLATE', 'archive_entries_verified': len(hashes), 'github_parts': parts, 'checksums': checks}
    (output / (PREFIX + '-packaging.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)

if __name__ == '__main__': main()
