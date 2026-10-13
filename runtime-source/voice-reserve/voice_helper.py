"""Isolated local speech renderer. Copyright 2026 Parham (Leon) Faraji.

SPDX-License-Identifier: GPL-3.0-or-later
Separate executable communicating through bounded JSON and WAV files.
No network, microphone, playback, model installation or persistent process.
"""
import array,ctypes as C,json,os,re,sys,unicodedata,wave
from pathlib import Path
MAX_SECONDS=240

def espeak(text,code,base):
    cookie=os.add_dll_directory(str(base))
    dll=C.CDLL(str(base/'espeak-ng.dll'))
    dll.espeak_Initialize.argtypes=[C.c_int,C.c_int,C.c_char_p,C.c_int]
    # Relative data path avoids the native library's narrow Windows argv handling.
    rate=dll.espeak_Initialize(2,0,b'.',0x8000)
    if rate<=0:raise ValueError('Basic voice data could not load.')
    dll.espeak_SetVoiceByName.argtypes=[C.c_char_p]
    if dll.espeak_SetVoiceByName(code.encode('ascii')):raise ValueError('Basic voice unavailable.')
    dll.espeak_Synth.argtypes=[C.c_char_p,C.c_size_t,C.c_uint,C.c_int,C.c_uint,C.c_uint,C.c_void_p,C.c_void_p]
    chunks=[];size=0;overflow=False
    CB=C.CFUNCTYPE(C.c_int,C.POINTER(C.c_short),C.c_int,C.c_void_p)
    @CB
    def callback(ptr,n,event):
        nonlocal size,overflow
        if ptr and n>0:
            size+=n
            if size>MAX_SECONDS*rate:overflow=True;return 1
            chunks.append(C.string_at(ptr,n*2))
        return 0
    dll.espeak_SetSynthCallback.argtypes=[CB];dll.espeak_SetSynthCallback(callback)
    try:
        raw=text.encode('utf-8')
        if dll.espeak_Synth(raw,len(raw)+1,0,1,0,1,None,None) or overflow:raise ValueError('Basic voice could not render the complete passage.')
        pcm=b''.join(chunks)
        if not pcm or not any(pcm):raise ValueError('Basic voice returned silence.')
        return pcm,rate
    finally:dll.espeak_Terminate();cookie.close()

def segments(text,limit=180):
    """Whitespace boundaries only: never silently truncate or split decimals."""
    parts=[]
    while len(text)>limit:
        cut=text.rfind(' ',0,limit+1)
        if cut<1:raise ValueError('A voice token is too long; no text was omitted.')
        parts.append(text[:cut]);text=text[cut+1:]
    if text.strip():parts.append(text)
    return parts

def neural(text,kind,folder):
    import numpy as np
    import onnxruntime as ort
    opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
    session=ort.InferenceSession(str(folder/'model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
    config=json.loads((folder/'config.json').read_text(encoding='utf-8'))
    pcm=[];total=0
    if kind=='vekol':
        from voice_text import spell_numbers
        text=spell_numbers(text,'ckb')
        mapping=config['phoneme_id_map'];rate=config['audio']['sample_rate']
        substitutions=str.maketrans({'ك':'ک','ھ':'ه','ہ':'ه','ى':'ی','ۀ':'ە','ة':'ە','ـ':'','\u200c':'','\u200d':'','“':'"','”':'"','—':'-','–':'-'})
        text=unicodedata.normalize('NFD',text.translate(substitutions))
        text=''.join(' ' if c.isspace() or c in '()[]{}«»' else c for c in text)
        # Do not copy the upstream silent-drop or integer-only digit conversion.
        bad={c for c in text if c not in mapping and not c.isspace()}
        if bad:raise ValueError('This Sorani neural voice cannot read all symbols; use the complete basic reserve.')
        def inputs(part):
            ids=[1,0]
            for c in part:ids.extend([mapping[c][0],0])
            ids.append(2)
            return {'input':np.array([ids],dtype=np.int64),'input_lengths':np.array([len(ids)],dtype=np.int64),'scales':np.array([0.0,1.0,0.0],dtype=np.float32),'sid':np.array([0],dtype=np.int64)}
    else:
        mapping=json.loads((folder/'vocab.json').read_text(encoding='utf-8'));rate=config['sampling_rate']
        text=unicodedata.normalize('NFC',text).lower()
        tc=json.loads((folder/'tokenizer_config.json').read_text(encoding='utf-8'))
        if tc.get('language')=='som':
            from voice_text import spell_numbers
            text=spell_numbers(text,'som')
        if tc.get('is_uroman'):
            from voice_text import spell_numbers
            text=spell_numbers(text,tc.get('language'))
            import uroman
            text=uroman.Uroman().romanize_string(text)
        # Unsupported numeric/symbol content must fall through as a WHOLE
        # passage; never produce seemingly complete audio missing quantities.
        bad={c for c in text if c not in mapping and (c.isalnum() or unicodedata.category(c).startswith('S') or c in '%/−')}
        if bad:raise ValueError('This local voice cannot read every letter, number or symbol in this passage.')
        text=''.join(c if c in mapping else ' ' for c in text)
        text=' '.join(text.split())
        def inputs(part):
            ids=[0]*(len(part)*2+1);ids[1::2]=[mapping[c] for c in part]
            return {'input_ids':np.array([ids],dtype=np.int64)}
    if not text.strip():raise ValueError('No speakable text.')
    for part in segments(text):
        values=session.run(None,inputs(part))[0].reshape(-1)
        if not values.size or not np.isfinite(values).all():raise ValueError('Invalid neural audio.')
        total+=values.size
        if total>MAX_SECONDS*rate:raise ValueError('Voice passage exceeded its complete-audio limit.')
        pcm.append((np.clip(values,-1,1)*32767).astype('<i2').tobytes())
        pcm.append(b'\0\0'*int(.12*rate))
    return b''.join(pcm),rate

def main():
    if len(sys.argv)!=3:return 2
    source,destination=map(Path,sys.argv[1:])
    if source.stat().st_size>100000 or destination.exists():return 2
    request=json.loads(source.read_text(encoding='utf-8'));text=request['text']
    if not isinstance(text,str) or not text.strip() or len(text)>6000:return 2
    if any(ord(c)<32 and c not in '\t\r\n' for c in text):return 2
    text.encode('utf-8')
    if request['kind']=='espeak':pcm,rate=espeak(text,request['code'],Path.cwd())
    elif request['kind'] in ('mms','vekol'):pcm,rate=neural(text,request['kind'],Path(request['model']))
    else:return 2
    if not pcm or len(pcm)>MAX_SECONDS*rate*2:return 2
    with destination.open('xb') as f:
        with wave.open(f,'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(pcm)
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(str(error)[:500],file=sys.stderr);raise SystemExit(1)
