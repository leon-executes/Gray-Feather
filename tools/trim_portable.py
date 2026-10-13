"""Remove redundant copies of private helper libraries after packaging."""
import argparse
import hashlib
import json
from pathlib import Path

PRIVATE = {
    'espeak-ng.dll': 'offline-voice/piper/espeak-ng.dll',
    'onnxruntime.dll': 'offline-voice/piper/onnxruntime.dll',
    'piper_phonemize.dll': 'offline-voice/piper/piper_phonemize.dll',
}

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def trim(portable):
    root = portable.resolve() / '_internal'
    removed = []
    for name, private in PRIVATE.items():
        duplicate, retained = root / name, root / 'resources' / private
        if not duplicate.exists():
            continue
        if duplicate.is_symlink() or not duplicate.resolve().is_relative_to(root):
            raise ValueError('Unsafe library path: ' + name)
        if not retained.is_file() or digest(duplicate) != digest(retained):
            raise ValueError('Private library differs: ' + name)
        removed.append({'file': name, 'bytes': duplicate.stat().st_size, 'retained': private})
        duplicate.unlink()
    return {'removed': removed, 'bytes_saved': sum(row['bytes'] for row in removed)}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('portable', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = trim(args.portable)
    args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
