"""Build-time fetch of pinned public local AI assets; never invoked by the app.

Usage: python fetch_local_ai.py --model hy_mt_local [--runtime-from PATH]
Interrupted downloads retain a resumable .part file; only verified assets become live.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.request
import uuid
import zipfile

ASSETS = {
    'hy_mt_local': {'file': 'Hy-MT2-1.8B-Q4_K_M.gguf', 'repo': 'tencent/Hy-MT2-1.8B-GGUF',
        'revision': 'a0c709d9fac510f2c807aa3af52872340dc37a4a', 'bytes': 1133080448,
        'sha256': 'dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699'},
    'gemma_local': {'file': 'gemma-4-E2B_q4_0-it.gguf', 'repo': 'google/gemma-4-E2B-it-qat-q4_0-gguf',
        'revision': '675cff42a74c774d6cb76f76d8eacb49b48c9b93', 'bytes': 3349516256,
        'sha256': 'fa401b55b07ee70a54c6dae3903c783a6e65064312529ea57175cb5f8dec6634'},
    'index_local': {'file': 'Index-Translate-2B.Q4_K_M.gguf', 'repo': 'IndexTeam/Index-Translate-2B-GGUF',
        'revision': '449c9e6457b3632d328c6cbb78ae8e8e0c8059a5', 'bytes': 1312164352,
        'sha256': '044b313d29342bd3b2c77cbb64023ca0d209bd9b3247763f9d162767ef2d746a'},
}
RUNTIME = {'file': 'llama-b11541-bin-win-cpu-x64.zip', 'bytes': 19518702,
    'sha256': 'cdc0535d11038bb337dfba3c15682050eaa9c07aedd0f915b4c09e8a8e8c0a5c',
    'url': 'https://github.com/ggml-org/llama.cpp/releases/download/b11541/llama-b11541-bin-win-cpu-x64.zip'}
VC_RUNTIME = {
    'msvcp140.dll': {'bytes':549176,'sha256':'fd4a8c046fa3fea9ca6132f50cf8a56cf1e783b2d3093ba5c85fa063bc6b3845'},
    'vcruntime140.dll': {'bytes':116024,'sha256':'de617641d82eac15595d2e39394163ac33e49bb032cf2c2ea0044ed39d3675e9'},
    'vcruntime140_1.dll': {'bytes':41272,'sha256':'fa577d54bd10a91e52472da784a619da6cf241af45f0a0c48b27e91fa0fe6104'},
}

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def verify(path: Path, asset: dict) -> bool:
    return path.is_file() and path.stat().st_size == asset['bytes'] and digest(path) == asset['sha256']

def download(asset: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / asset['file']
    if verify(final, asset):
        print(f"Verified existing {final.name}", flush=True)
        return final
    partial = final.with_suffix(final.suffix + '.part')
    url = asset.get('url') or f"https://huggingface.co/{asset['repo']}/resolve/{asset['revision']}/{asset['file']}?download=true"
    for attempt in range(4):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > asset['bytes']:
            partial.unlink()
            offset = 0
        if offset == asset['bytes']:
            break
        headers = {'User-Agent': 'GrayFeather-build/1.3', 'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                if offset and response.status != 206:
                    offset = 0
                if offset and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise ValueError('Server returned an unexpected download range')
                done, last = offset, time.monotonic()
                with partial.open('ab' if offset else 'wb') as stream:
                    while block := response.read(4 * 1024 * 1024):
                        done += len(block)
                        if done > asset['bytes']:
                            raise ValueError('Download exceeds pinned asset size')
                        stream.write(block)
                        if time.monotonic() - last > 3:
                            print(f"{final.name}: {done}/{asset['bytes']} bytes", flush=True)
                            last = time.monotonic()
                    stream.flush()
                    os.fsync(stream.fileno())
            if done == asset['bytes']:
                break
        except Exception as exc:
            print(f"Attempt {attempt + 1}: {type(exc).__name__}: {exc}", flush=True)
            if attempt == 3:
                raise
            time.sleep(2)
    if not verify(partial, asset):
        raise ValueError(f'Asset size/hash mismatch: {partial}')
    os.replace(partial, final)
    print(f"Verified {final.name} SHA256 {asset['sha256']}", flush=True)
    return final

def install_runtime(archive: Path, destination: Path) -> dict:
    if not verify(archive, RUNTIME):
        raise ValueError('Runtime archive does not match its pinned hash')
    destination.mkdir(parents=True, exist_ok=True)
    selected = {'llama-completion.exe', 'llama-completion-impl.dll',
                'llama-common.dll', 'llama.dll', 'ggml.dll', 'ggml-base.dll', 'libomp.dll', 'LICENSE-LLVM-OpenMP'}
    hashes = {}
    with zipfile.ZipFile(archive) as zipped:
        for item in zipped.infolist():
            name = Path(item.filename).name
            if name in selected or (name.startswith('ggml-cpu-') and name.endswith('.dll')):
                target = destination / name
                # Archive is pinned; read one bounded runtime component at a time.
                if item.file_size > 12 * 1024 * 1024:
                    raise ValueError('Unexpectedly large runtime component')
                with zipped.open(item) as source:
                    content = source.read()
                expected = hashlib.sha256(content).hexdigest()
                if target.is_file() and target.stat().st_size == len(content) and digest(target) == expected:
                    hashes[name] = expected
                    continue  # In-use DLLs are valid; do not truncate or replace them.
                pending = target.with_name(target.name + '.' + uuid.uuid4().hex + '.pending')
                try:
                    pending.write_bytes(content)
                    os.replace(pending, target)
                finally:
                    pending.unlink(missing_ok=True)
                hashes[name] = expected
    missing = selected - hashes.keys()
    if missing:
        raise ValueError(f'Runtime archive lacks {sorted(missing)}')
    return hashes

def install_vc_runtime(source: Path | None, destination: Path) -> dict:
    hashes={}
    for name,asset in VC_RUNTIME.items():
        target=destination/name
        if not verify(target,asset):
            original=source/name if source else None
            if original is None or not verify(original,asset):
                raise ValueError(f'Provide --vc-runtime-from pointing to pinned shiboken6 6.11.2 DLLs: {name}')
            pending=target.with_name(name+'.'+uuid.uuid4().hex+'.pending')
            try:
                shutil.copyfile(original,pending)
                if not verify(pending,asset): raise ValueError('VC runtime changed while copying')
                os.replace(pending,target)
            finally: pending.unlink(missing_ok=True)
        hashes[name]=asset['sha256']
    # Previous helper copied a dispatcher for tools that are not bundled or used.
    (destination/'llama.exe').unlink(missing_ok=True)
    return hashes

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=ASSETS, default='index_local')
    parser.add_argument('--destination', type=Path, default=Path(__file__).resolve().parent / 'resources' / 'local-ai')
    parser.add_argument('--runtime-from', type=Path)
    parser.add_argument('--vc-runtime-from', type=Path)
    args = parser.parse_args()
    download(ASSETS[args.model], args.destination)
    archive = args.runtime_from
    if archive and archive.is_dir():
        archive = archive / RUNTIME['file']
    if archive is None:
        archive = download(RUNTIME, args.destination / 'build-assets')
    hashes = install_runtime(archive, args.destination / 'runtime')
    hashes.update(install_vc_runtime(args.vc_runtime_from,args.destination/'runtime'))
    installed={name:asset for name,asset in ASSETS.items() if verify(args.destination/asset['file'],asset)}
    manifest = {'runtime': RUNTIME, 'runtime_files': hashes, 'models': installed,
                'vc_runtime': {'version':'14.44.35211.0','source':'shiboken6 6.11.2 Windows x64 wheel','files':VC_RUNTIME},
                'network': 'Build-time download only; inference uses no network.'}
    pending = args.destination / ('ASSETS.' + uuid.uuid4().hex + '.pending')
    try:
        pending.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        os.replace(pending, args.destination / 'ASSETS.json')
    finally:
        pending.unlink(missing_ok=True)

if __name__ == '__main__':
    main()
