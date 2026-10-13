"""Bounded process adapter for optional neural and bundled basic voices.
Copyright 2026 Parham (Leon) Faraji / leon-executes.
SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
import hashlib,io,json,os,re,subprocess,tempfile,threading,time,wave
from pathlib import Path

class ReserveError(Exception):pass
# Variants are explicit. Dari is an approximate Persian pronunciation reserve.
BASIC={'en-US':'en-us','ar-SA':'ar','fr-FR':'fr','fa-IR':'fa','fa-AF':'fa',
 'am-ET':'am',
 'tr-TR':'tr','ur-PK':'ur','hi-IN':'hi','bn-BD':'bn','pa-IN':'pa','sd-PK':'sd',
 'om-ET':'om','ku-TR':'ku','sw-KE':'sw','es-ES':'es','de-DE':'de','it-IT':'it',
 'pt-PT':'pt','ru-RU':'ru','zh-CN':'cmn','ja-JP':'ja','ko-KR':'ko','nl-NL':'nl',
 'pl-PL':'pl','ro-RO':'ro','uk-UA':'uk','el-GR':'el','he-IL':'he','id-ID':'id'}
_SLOT=threading.BoundedSemaphore(1)
_VALIDATED={};_LOCK=threading.Lock()
APPROXIMATE={'fa-AF':'Persian pronunciation for Dari'}

def resources(config=None):
    return Path((config or {}).get('_reserve_resources') or Path(__file__).resolve().parent/'resources'/'voice-reserve').resolve()
def piper(config=None):
    return Path((config or {}).get('_offline_voice_resources') or Path(__file__).resolve().parent/'resources'/'offline-voice').resolve()/'piper'
def helper(config=None):
    return resources(config)/'helper'/'GrayFeatherVoice.exe'
def catalog(config=None):
    try:
        path=resources(config)/'catalog.json'
        if path.stat().st_size>65536:return {}
        result=json.loads(path.read_text(encoding='utf-8'))
        return result if isinstance(result,dict) else {}
    except (OSError,ValueError,UnicodeError):return {}

def _entry(locale,config=None):
    entry=catalog(config).get(locale)
    if not isinstance(entry,dict) or entry.get('enabled') is not True or entry.get('kind') not in ('mms','vekol'):return None
    files=entry.get('files')
    if not isinstance(files,dict) or not 2<=len(files)<=10:return None
    required={'model.onnx','config.json'} | ({'vocab.json','tokenizer_config.json'} if entry['kind']=='mms' else set())
    if not required.issubset(files):return None
    for name,spec in files.items():
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',name) or name in ('.','..'):return None
        if not isinstance(spec,dict) or type(spec.get('bytes')) is not int or not 0<spec['bytes']<=512*1024*1024:return None
        if not isinstance(spec.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',spec['sha256']):return None
    return entry

def available(locale,kind='basic',config=None):
    try:
        if not helper(config).is_file() and not (config or {}).get('_reserve_python'):return False
        if kind=='basic':
            code=BASIC.get(locale)
            return bool(code and (piper(config)/'espeak-ng.dll').is_file() and (piper(config)/'espeak-ng-data'/(code.split('-')[0]+'_dict')).is_file())
        if kind!='neural' or not re.fullmatch('[a-z]{2,3}-[A-Z]{2}',str(locale)):return False
        entry=_entry(locale,config)
        if entry is None:return False
        return all((resources(config)/'models'/locale/name).is_file() and (resources(config)/'models'/locale/name).stat().st_size==spec['bytes'] for name,spec in entry['files'].items())
    except OSError:return False
def identity(locale,kind,config=None):
    try: stamp=(str(helper(config)),helper(config).stat().st_size,helper(config).stat().st_mtime_ns)
    except OSError: stamp=None
    return ('reserve-2',kind,locale,BASIC.get(locale),stamp) if kind=='basic' else ('reserve-2',kind,locale,json.dumps(catalog(config).get(locale),sort_keys=True),stamp)
def _validate(folder,entry,stop):
    signature=tuple((str(folder/name),(folder/name).stat().st_size,(folder/name).stat().st_mtime_ns,entry['files'][name]['sha256']) for name in entry['files'])
    with _LOCK:
        if signature in _VALIDATED:return
        for name,spec in entry['files'].items():
            path=folder/name
            if path.resolve().parent!=folder.resolve():raise ReserveError('Invalid voice model path.')
            h=hashlib.sha256()
            with path.open('rb') as f:
                while b:=f.read(1024*1024):
                    if stop.is_set():raise ReserveError('Voice cancelled.')
                    h.update(b)
            if h.hexdigest()!=spec['sha256']:raise ReserveError('Voice pack failed its integrity check. Restore the voice pack.')
        if len(_VALIDATED)>8:_VALIDATED.clear()
        _VALIDATED[signature]=True

def prepare(text,locale,kind,config=None,stop=None,timeout=60):
    config=dict(config or {});stop=stop or threading.Event()
    if kind not in ('basic','neural') or not isinstance(text,str) or not text.strip() or len(text)>6000:raise ReserveError('Invalid local voice request.')
    if any(ord(c)<32 and c not in '\t\r\n' for c in text):raise ReserveError('Voice text contains an unsupported control character.')
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not .1<=timeout<=60:raise ReserveError('Invalid voice deadline.')
    if stop.is_set():raise ReserveError('Voice cancelled.')
    if not available(locale,kind,config):raise ReserveError('The local voice pack is unavailable for this language.')
    deadline=time.monotonic()+timeout;acquired=False
    try:
        while not acquired:
            if stop.is_set():raise ReserveError('Voice cancelled.')
            if time.monotonic()>=deadline:raise ReserveError('Local voice is busy.')
            acquired=_SLOT.acquire(timeout=.025)
        entry=_entry(locale,config) if kind=='neural' else {}
        folder=resources(config)/'models'/locale
        if kind=='neural':_validate(folder,entry,stop)
        temp=Path(config.get('_audio_dir') or tempfile.gettempdir());temp.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='voice-reserve-',dir=temp) as scratch:
            source=Path(scratch)/'request.json';output=Path(scratch)/'complete.wav';error=Path(scratch)/'error.txt'
            source.write_text(json.dumps({'text':text,'kind':entry.get('kind','espeak'),'code':BASIC.get(locale),'model':str(folder)},ensure_ascii=False),encoding='utf-8')
            command=[str(helper(config))]
            if config.get('_reserve_python'):command=[config['_reserve_python'],str(Path(__file__).with_name('voice_helper.py'))]
            if stop.is_set():raise ReserveError('Voice cancelled.')
            if time.monotonic()>=deadline:raise ReserveError('Local voice exceeded its deadline.')
            with error.open('wb') as err:
                process=subprocess.Popen(command+[str(source),str(output)],cwd=piper(config),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                try:
                    while process.poll() is None:
                        if stop.wait(.025):raise ReserveError('Voice cancelled.')
                        if time.monotonic()>=deadline:raise ReserveError('Local voice exceeded its deadline.')
                        if error.stat().st_size>65536 or (output.exists() and output.stat().st_size>240*48000*2+100):raise ReserveError('Local voice exceeded its output limit.')
                    if process.returncode:raise ReserveError(error.read_text(encoding='utf-8',errors='replace')[:500] or 'Local voice could not render the complete passage.')
                finally:
                    if process.poll() is None:process.kill()
                    process.wait(timeout=5)
            if stop.is_set():raise ReserveError('Voice cancelled.')
            if not output.exists() or output.stat().st_size>240*48000*2+100:raise ReserveError('Invalid local voice output.')
            with wave.open(str(output),'rb') as w:
                if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getcomptype()!='NONE' or not 0<w.getnframes()<=240*w.getframerate():raise ReserveError('Invalid local voice audio.')
                rate=w.getframerate();n=w.getnframes();pcm=w.readframes(n)
                if len(pcm)!=n*2 or not any(pcm):raise ReserveError('Incomplete or silent local voice audio.')
            from offline_voice import _resample
            audio=_resample(pcm,rate)
            if stop.is_set():raise ReserveError('Voice cancelled.')
            if time.monotonic()>=deadline:raise ReserveError('Local voice exceeded its deadline.')
        approximate=locale in APPROXIMATE and kind=='basic'
        return {'audio':audio,'provider':'offline_'+kind,'locale':locale,'voice':entry.get('name') or ('Approximate '+APPROXIMATE[locale] if approximate else 'Basic '+BASIC[locale]+' · eSpeak NG'),
                'offline':True,'approximate':approximate,'complete_preparation':True,'sample_rate':16000,
                'warnings':['Approximate voice: '+APPROXIMATE[locale]+'.'] if approximate else (['Robotic fallback voice; pronunciation can be weak.'] if kind=='basic' else [])}
    except (OSError,ValueError,wave.Error) as e:raise ReserveError('Local voice files could not be used: '+str(e)) from e
    finally:
        if acquired:_SLOT.release()
