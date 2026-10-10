"""Build-time fetch of pinned speech assets; never runs at application startup."""
import hashlib,json,shutil,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SPEECH=ROOT/'resources'/'speech'
MODEL_SHA='ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb'
ZIP_SHA='6ba69e3482d7826214f90a6a9c84ca07782aec1e1d0c6a7c30c994fd5d816ccb'
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def fetch(url,path,expected=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and (not expected or sha(path)==expected):return
    staged=path.with_suffix(path.suffix+'.part')
    try:
        with urllib.request.urlopen(url,timeout=60) as source,staged.open('wb') as target:
            while block:=source.read(1024*1024):target.write(block)
        if expected and sha(staged)!=expected:raise RuntimeError('Upstream hash mismatch: '+path.name)
        staged.replace(path)
    finally:staged.unlink(missing_ok=True)
def main():
    SPEECH.mkdir(parents=True,exist_ok=True)
    if not (SPEECH/'whisper-cli.exe').exists():
        archive=ROOT/'.build-temp'/'downloads'/'whisper-b5454-x64.zip'
        fetch('https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-x64.zip',archive,ZIP_SHA)
        with zipfile.ZipFile(archive) as zipped:
            for item in zipped.infolist():
                name=Path(item.filename).name
                if name in ('whisper-cli.exe','whisper.dll','ggml.dll','ggml-base.dll') or (name.startswith('ggml-cpu-') and name.endswith('.dll')):
                    (SPEECH/name).write_bytes(zipped.read(item))
    fetch('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q5_1.bin',SPEECH/'ggml-small-q5_1.bin',MODEL_SHA)
    fetch('https://raw.githubusercontent.com/ggml-org/whisper.cpp/b5454/samples/jfk.wav',ROOT/'resources'/'test'/'jfk.wav','59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e')
    import PySide6
    redist=Path(PySide6.__file__).resolve().parent
    for name in ('msvcp140.dll','vcomp140.dll','vcruntime140.dll','vcruntime140_1.dll'):
        if not (SPEECH/name).exists():shutil.copyfile(redist/name,SPEECH/name)
    print('Pinned portable speech resources verified; no runtime installer is needed.')
if __name__=='__main__':main()
