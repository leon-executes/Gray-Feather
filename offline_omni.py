"""Bundled Windows CPU Omnilingual CTC, guarded by measured exact locales.

The release native console helper must contain activeCodePage UTF-8 and is
relocation-tested during the build. Model paths are ASCII relative names;
the private WAV uses the helper's verified UTF-8 argv path support.
"""
from __future__ import annotations
import array
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import wave

class OmniError(Exception): pass

# Published support does not automatically add an operational route. These
# two exact locales have actual native-speaker recording proofs in verification.
LOCALES={'om-ET':'orm_Latn','ckb-IQ':'ckb_Arab'}
ENGINE='Omnilingual CTC 300M int8 · sherpa-onnx 1.13.8'
MODEL_FILES={
    'sherpa-onnx-offline.exe':(18751488,'3a0177956d7ffc3c4d4eda8cd2b5386984861574783b89afb50379c7822bd24a'),
    'model.int8.onnx':(365352120,'e7c4e54ee4c4c47829cc6667d5d00ed8ea7bef1dcfeef0fce766f77752a2726c'),
    'tokens.txt':(86423,'a7a044c52cb29cbe8b0dc1953e92cefd4ca16b0ed968177b6beab21f9a7d0b31'),
}
_SLOT=threading.BoundedSemaphore(1)
_VALIDATED={}
_LOCK=threading.Lock()

def resources(config=None):
    return Path((config or {}).get('_omni_resources') or Path(__file__).resolve().parent/'resources'/'omni-asr').resolve()

def available(locale=None,config=None):
    if locale is not None and locale not in LOCALES: return False
    folder=resources(config)
    try:
        return (folder/'sherpa-onnx-offline.exe').is_file() and all((folder/name).is_file() and (folder/name).stat().st_size==size for name,(size,_) in MODEL_FILES.items())
    except OSError: return False

def _validate(folder,cancel):
    try:
        signature=tuple((str((folder/name).resolve()),(folder/name).stat().st_size,(folder/name).stat().st_mtime_ns) for name in MODEL_FILES)
        with _LOCK:
            if signature in _VALIDATED: return
            for name,(size,expected) in MODEL_FILES.items():
                if (folder/name).stat().st_size!=size: raise OmniError('The bundled multilingual speech files are incomplete.')
                digest=hashlib.sha256()
                with (folder/name).open('rb') as source:
                    while block:=source.read(1024*1024):
                        if cancel.is_set(): raise OmniError('Speech cancelled.')
                        digest.update(block)
                if digest.hexdigest()!=expected: raise OmniError('The bundled multilingual speech model failed its integrity check.')
            _VALIDATED.clear(); _VALIDATED[signature]=True
    except OSError as error: raise OmniError('Restore the complete portable app to use bundled multilingual dictation.') from error

def _pcm(audio):
    if not isinstance(audio,bytes) or len(audio)>1700000: raise OmniError('Dictation needs bounded PCM WAV audio.')
    try:
        with wave.open(io.BytesIO(audio),'rb') as file:
            count=file.getnframes()
            if (file.getnchannels(),file.getsampwidth(),file.getframerate(),file.getcomptype())!=(1,2,16000,'NONE') or not 0<count<=800000:
                raise OmniError('Dictation needs 16 kHz mono PCM, up to 50 seconds.')
            pcm=file.readframes(count)
            if len(pcm)!=count*2: raise OmniError('The recording is incomplete.')
    except (wave.Error,EOFError) as error: raise OmniError('The recording is not valid WAV audio.') from error
    samples=array.array('h',pcm)
    if sys.byteorder!='little': samples.byteswap()
    if min(samples)==max(samples): raise OmniError('The recording contains no changing speech signal.')
    return pcm

def _wav(pcm):
    value=io.BytesIO()
    with wave.open(value,'wb') as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(16000); file.writeframes(pcm)
    return value.getvalue()

def segments(pcm):
    """Complete contiguous PCM slices <40s, favouring quiet 20ms boundaries.

    No overlap, text deduplication or dropped tail. A boundary within ongoing
    speech can still split a word; the completed result explicitly says review.
    """
    values=array.array('h',pcm)
    if sys.byteorder!='little': values.byteswap()
    result=[]; start=0; total=len(values)
    while total-start>35*16000:
        low=start+25*16000; high=min(start+32*16000,total)
        # Prefer the lowest mean-square window; ties choose the later point.
        cut=min(range(low,high+1,320),key=lambda index:(sum(value*value for value in values[index-160:index+160]),-index))
        result.append(pcm[start*2:cut*2]); start=cut
    result.append(pcm[start*2:])
    return result

def time_budget(seconds):
    if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not 0<seconds<=50:
        raise OmniError('Dictation duration must be between zero and 50 seconds.')
    return min(60.,max(15.,8.+.65*seconds))

def _native(folder,audio_path,output,cancel,deadline):
    if cancel.is_set(): raise OmniError('Speech cancelled.')
    if time.monotonic()>=deadline: raise OmniError('Multilingual dictation exceeded its bounded time budget.')
    args=[str(folder/'sherpa-onnx-offline.exe'),'--omnilingual-asr-model=model.int8.onnx','--tokens=tokens.txt',
          '--num-threads=2','--provider=cpu','--debug=false','--print-args=false',str(audio_path)]
    with output.open('wb') as destination:
        try:
            process=subprocess.Popen(args,cwd=folder,stdin=subprocess.DEVNULL,stdout=destination,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError as error: raise OmniError('The bundled multilingual recognizer could not start.') from error
        try:
            while process.poll() is None:
                if cancel.wait(.025): raise OmniError('Speech cancelled.')
                if time.monotonic()>=deadline: raise OmniError('Multilingual dictation exceeded its bounded time budget.')
                if output.stat().st_size>1024*1024: raise OmniError('Multilingual dictation returned an oversized response.')
            if cancel.is_set(): raise OmniError('Speech cancelled.')
            if time.monotonic()>=deadline: raise OmniError('Multilingual dictation exceeded its bounded time budget.')
            if process.returncode: raise OmniError('Multilingual dictation could not process the complete recording.')
        finally:
            if process.poll() is None: process.kill()
            process.wait(timeout=5)
    if output.stat().st_size>1024*1024: raise OmniError('Multilingual dictation returned an oversized response.')
    try:
        lines=output.read_text(encoding='utf-8').splitlines()
        if len(lines)!=1: raise ValueError('Expected one complete result.')
        value=json.loads(lines[0]); text=value.get('text')
        if not isinstance(text,str) or not 0<len(text.strip())<=50000 or any(ord(char)<32 and char not in '\t\r\n' for char in text):
            raise ValueError('Invalid text.')
        return text.strip()
    except (OSError,UnicodeError,ValueError,AttributeError) as error: raise OmniError('Multilingual dictation returned no valid complete transcript.') from error

def recognize(audio,locale,config=None,cancel=None):
    if locale not in LOCALES: raise OmniError('This exact language has no measured bundled multilingual route. No other language was substituted.')
    config=dict(config or {}); cancel=cancel or threading.Event()
    if cancel.is_set(): raise OmniError('Speech cancelled.')
    pcm=_pcm(audio); folder=resources(config)
    if not available(locale,config): raise OmniError('The bundled multilingual speech files are missing. Restore the complete portable app folder.')
    deadline=time.monotonic()+time_budget(len(pcm)/32000)
    acquired=False
    try:
        while not acquired:
            if cancel.is_set(): raise OmniError('Speech cancelled.')
            if time.monotonic()>=deadline: raise OmniError('Multilingual dictation is busy. Try a shorter turn.')
            acquired=_SLOT.acquire(timeout=.025)
        _validate(folder,cancel)
        if cancel.is_set(): raise OmniError('Speech cancelled.')
        if time.monotonic()>=deadline: raise OmniError('Multilingual dictation exceeded its bounded time budget.')
        directory=Path(config.get('_audio_dir') or tempfile.gettempdir()); directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='multilingual-',dir=directory) as scratch:
            base=Path(scratch); parts=segments(pcm); texts=[]
            for index,part in enumerate(parts):
                if cancel.is_set(): raise OmniError('Speech cancelled.')
                values=array.array('h',part)
                if min(values)==max(values): continue  # Exact silence/DC has no transcript; keep every nonconstant slice.
                path=base/(str(index)+'.wav'); path.write_bytes(_wav(part))
                texts.append(_native(folder,path,base/(str(index)+'.json'),cancel,deadline))
            if cancel.is_set(): raise OmniError('Speech cancelled.')
            text=' '.join(texts)
            letters=[unicodedata.name(char,'') for char in text if char.isalpha()]
            script='ARABIC' if locale=='ckb-IQ' else 'LATIN'
            if not text or not any(script in name for name in letters):
                raise OmniError('Multilingual dictation returned a different or unclear script. Review or type this turn.')
            return {'text':text,'provider':'omnilingual','locale':locale,'engine':ENGINE,'offline':True,
                    'chunks':len(parts),'language_conditioned':False,'complete':True,
                    'warnings':['Review names, numbers and negation. This small CTC model does not accept a language constraint and may misidentify short speech.']}
    except OSError as error: raise OmniError('Multilingual dictation could not read its complete local recording.') from error
    finally:
        if acquired: _SLOT.release()
