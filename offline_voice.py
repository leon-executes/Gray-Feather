"""Silent bundled native Piper voice preparation, with no installed runtime.

The native helper is a separate process. UTF-8 text and raw PCM use private
file handles; native model/data arguments are ASCII relative paths so Unicode
portable folders do not depend on the Windows narrow command-line code page.
"""
from __future__ import annotations
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import wave


class OfflineVoiceError(Exception):
    pass


# This is a voice-specific registry, not a language alias table. A Persian
# model is deliberately not advertised as Dari or either Kurdish variant.
VOICE_MODELS = {
    'fa-IR': {'id': 'fa_IR-gyro-medium', 'name': 'Persian · Gyro (bundled)',
              'filename': 'fa_IR-gyro-medium.onnx', 'sample_rate': 22050,
              'model_bytes': 63122309,
              'model_sha256': '37dfae43c82ee38ca9e6aac4ffef76a74d6b282ccbc397b27761f35d355c99ba',
              'espeak_voice': 'fa', 'model_license': 'MIT',
              'creator_revision': 'e409c5a8fb164ff6e710bfbd07b7b02c1e13949a',
              'source': 'https://huggingface.co/gyroing/Persian-Piper-Model-gyro/tree/e409c5a8fb164ff6e710bfbd07b7b02c1e13949a'},
}
PIPER_RELEASE = '2023.11.14-2'
_MAX_AUDIO_SECONDS = 240
_RENDER_SLOT = threading.BoundedSemaphore(1)
_VALIDATED = {}
_VALIDATION_LOCK = threading.Lock()
_RUNTIME_FILES = ('piper.exe', 'espeak-ng.dll', 'piper_phonemize.dll',
                  'onnxruntime.dll', 'onnxruntime_providers_shared.dll')


def resources(config=None):
    return Path((config or {}).get('_offline_voice_resources') or Path(__file__).resolve().parent/'resources'/'offline-voice').resolve()


def available_locales(config=None):
    return frozenset(locale for locale in VOICE_MODELS if available(locale, config))


def available(locale, config=None):
    if locale not in VOICE_MODELS: return False
    base=resources(config); model=VOICE_MODELS[locale]; folder=base/'models'/locale
    try:
        return (all((base/'piper'/name).is_file() for name in _RUNTIME_FILES)
                and (base/'piper'/'espeak-ng-data'/'phondata').is_file()
                and (folder/model['filename']).is_file() and (folder/model['filename']).stat().st_size==model['model_bytes']
                and (folder/(model['filename']+'.json')).is_file())
    except OSError: return False


def cache_identity(locale):
    model=VOICE_MODELS.get(locale)
    return (PIPER_RELEASE,model['id'],model['model_sha256']) if model else None


def _validate_model(locale, base):
    model=VOICE_MODELS[locale]; folder=base/'models'/locale
    path=folder/model['filename']; config=folder/(model['filename']+'.json')
    try:
        signature=(str(path.resolve()),path.stat().st_size,path.stat().st_mtime_ns,
                   config.stat().st_size,config.stat().st_mtime_ns)
        with _VALIDATION_LOCK:
            if signature in _VALIDATED: return folder,model
            if path.stat().st_size!=model['model_bytes'] or not 0<config.stat().st_size<=65536:
                raise OfflineVoiceError('The bundled offline voice files are incomplete. Restore the full portable app folder.')
            metadata=json.loads(config.read_text(encoding='utf-8'))
            if (not isinstance(metadata,dict) or metadata.get('audio',{}).get('sample_rate')!=model['sample_rate']
                or metadata.get('num_speakers')!=1 or metadata.get('phoneme_type')!='espeak'
                or metadata.get('espeak',{}).get('voice')!=model['espeak_voice']):
                raise OfflineVoiceError('The bundled offline voice configuration does not match this exact voice.')
            digest=hashlib.sha256()
            with path.open('rb') as file:
                while block:=file.read(1024*1024): digest.update(block)
            if digest.hexdigest()!=model['model_sha256']:
                raise OfflineVoiceError('The bundled offline voice model failed its integrity check.')
            _VALIDATED.clear(); _VALIDATED[signature]=True
        return folder,model
    except (OSError,ValueError,UnicodeError,AttributeError,TypeError) as error:
        raise OfflineVoiceError('The bundled offline voice files could not be read. Restore the full portable app folder.') from error


def _wav(pcm,rate=16000):
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate); wav.writeframes(pcm)
    return buffer.getvalue()


def _resample(raw,rate):
    if not isinstance(raw,bytes) or not raw or len(raw)%2 or len(raw)>_MAX_AUDIO_SECONDS*rate*2:
        raise OfflineVoiceError('Offline voice returned incomplete or oversized PCM. Nothing was played.')
    try:
        import miniaudio
        pcm=bytes(miniaudio.convert_frames(miniaudio.SampleFormat.SIGNED16,1,rate,raw,
            miniaudio.SampleFormat.SIGNED16,1,16000))
    except Exception as error:
        raise OfflineVoiceError('The bundled offline voice audio converter is unavailable.') from error
    if not pcm or len(pcm)%2 or len(pcm)>_MAX_AUDIO_SECONDS*32000:
        raise OfflineVoiceError('Offline voice returned incomplete or oversized PCM. Nothing was played.')
    return _wav(pcm)


def prepare(text,locale,config=None,stop=None,timeout=60):
    """Produce the entire passage or fail silently, bounded by the caller budget."""
    config=dict(config or {}); stop=stop or threading.Event()
    if stop.is_set(): raise OfflineVoiceError('Voice cancelled.')
    if not isinstance(text,str) or not text.strip() or len(text)>6000:
        raise OfflineVoiceError('Offline voice needs nonempty text of at most 6,000 characters.')
    try: text.encode('utf-8')
    except UnicodeError as error: raise OfflineVoiceError('The voice text contains invalid Unicode.') from error
    if locale not in VOICE_MODELS:
        raise OfflineVoiceError('No bundled offline voice exists for this exact language. No other language was substituted.')
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not .1<=timeout<=60:
        raise OfflineVoiceError('Offline voice needs a time budget between 0.1 and 60 seconds.')
    base=resources(config)
    if not available(locale,config):
        raise OfflineVoiceError('The bundled offline voice files are missing. Restore the complete portable app folder.')
    deadline=time.monotonic()+timeout; acquired=False; process=None
    try:
        while not stop.is_set():
            if _RENDER_SLOT.acquire(timeout=.025): acquired=True; break
            if time.monotonic()>=deadline: raise OfflineVoiceError('Offline voice preparation is busy.')
        if not acquired or stop.is_set(): raise OfflineVoiceError('Voice cancelled.')
        folder,model=_validate_model(locale,base)
        directory=Path(config.get('_audio_dir') or tempfile.gettempdir()); directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='offline-voice-',dir=directory) as scratch:
            source,output=Path(scratch)/'text.json',Path(scratch)/'voice.raw'
            source.write_text(json.dumps({'text':text},ensure_ascii=False)+'\n',encoding='utf-8')
            args=[str(base/'piper'/'piper.exe'),'--model',model['filename'],'--config',model['filename']+'.json',
                  '--output_raw','--json-input','--espeak_data',os.path.join('..','..','piper','espeak-ng-data'),'--quiet']
            if stop.is_set(): raise OfflineVoiceError('Voice cancelled.')
            if time.monotonic()>=deadline: raise OfflineVoiceError('Offline voice preparation exceeded its time budget.')
            with source.open('rb') as input_file,output.open('wb') as audio_file:
                try:
                    process=subprocess.Popen(args,cwd=folder,stdin=input_file,stdout=audio_file,stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                except OSError as error:
                    raise OfflineVoiceError('The bundled offline voice runtime could not start.') from error
                try:
                    while process.poll() is None:
                        if stop.wait(.025): raise OfflineVoiceError('Voice cancelled.')
                        if time.monotonic()>=deadline: raise OfflineVoiceError('Offline voice preparation exceeded its time budget.')
                        if output.stat().st_size>_MAX_AUDIO_SECONDS*model['sample_rate']*2:
                            raise OfflineVoiceError('The complete offline voice passage is too long. Choose a shorter passage.')
                    if stop.is_set(): raise OfflineVoiceError('Voice cancelled.')
                    if process.returncode: raise OfflineVoiceError('The bundled offline voice could not synthesize the complete passage.')
                finally:
                    if process.poll() is None: process.kill()
                    process.wait(timeout=5)
            if stop.is_set(): raise OfflineVoiceError('Voice cancelled.')
            audio=_resample(output.read_bytes(),model['sample_rate'])
            if stop.is_set(): raise OfflineVoiceError('Voice cancelled.')
            if time.monotonic()>deadline: raise OfflineVoiceError('Offline voice preparation exceeded its time budget.')
        return {'audio':audio,'provider':'offline_piper','voice':model['name'],'locale':locale,
                'characters':len(text),'decoded':True,'offline':True,'model':model['id'],
                'engine':'Piper '+PIPER_RELEASE,'privacy':'Text and synthesized audio stayed on this PC.',
                'sample_rate':16000,'complete_preparation':True}
    finally:
        if acquired: _RENDER_SLOT.release()
