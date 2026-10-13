"""Explicit live synthetic checks for the packaged free speech stack."""
import io,time,threading,wave,tempfile
from pathlib import Path
from unittest.mock import patch

def run():
    import speech
    from app import VERSION
    stop=threading.Event()
    audio=(Path(__file__).resolve().parents[1]/'resources'/'test'/'jfk.wav').read_bytes()
    rows=[]
    for mode in ('google_web','offline'):
        began=time.perf_counter()
        try:
            result=speech.recognize_with_fallback(audio,'en-US',{'speech_provider':mode},stop)
            rows.append({'case':'dictation-'+mode,'successful':bool(result['text']),'text':result['text'],'provider':result['provider'],'seconds':round(time.perf_counter()-began,3)})
        except Exception as error:rows.append({'case':'dictation-'+mode,'successful':False,'error':str(error)})
    try:
        with patch('speech.recognize_google_web',side_effect=speech.SpeechError('Online route must not run when local English succeeds.')) as online:
            value=speech.recognize_with_fallback(audio,'en-US',{'speech_provider':'auto'},stop)
        rows.append({'case':'auto-English-local-primary','successful':value['provider']=='offline' and online.call_count==0,'provider':value['provider'],'text':value['text'],'online_upload':False})
    except Exception as error:rows.append({'case':'auto-English-local-primary','successful':False,'error':str(error)})
    try:
        french=(Path(__file__).resolve().parents[1]/'resources'/'test'/'fr-speech.wav').read_bytes()
        with patch('speech.recognize_google_web',side_effect=speech.SpeechError('Online route must not run when local French succeeds.')) as online:
            value=speech.recognize_with_fallback(french,'fr-FR',{'speech_provider':'auto'},stop)
        rows.append({'case':'auto-French-local-primary','successful':value['provider']=='offline' and online.call_count==0,'provider':value['provider'],'text':value['text'],'online_upload':False})
    except Exception as error:rows.append({'case':'auto-French-local-primary','successful':False,'error':str(error)})
    try:
        arabic=(Path(__file__).resolve().parents[1]/'resources'/'test'/'ar-speech.wav').read_bytes()
        with patch('speech.recognize_google_web',side_effect=speech.SpeechError('Injected online unavailability for actual Arabic local fallback.')) as online:
            value=speech.recognize_with_fallback(arabic,'ar-SA',{'speech_provider':'auto'},stop)
        rows.append({'case':'actual-Arabic-offline-fallback','successful':value['provider']=='offline' and online.call_count==1,'provider':value['provider'],'text':value['text'],'injected_online_failure':True})
    except Exception as error:rows.append({'case':'actual-Arabic-offline-fallback','successful':False,'error':str(error)})
    for lang,text in [('en-US','Please bring two copies.'),('fr-FR','Bonjour.'),('fa-IR','لطفاً دو نسخه بیاورید.'),('ps-AF','مهرباني وکړئ دوه نقلونه راوړئ.')]:
        began=time.perf_counter()
        try:
            prepared=speech._prepare_voice_direct('edge_free',text,lang,{'_audio_dir':tempfile.gettempdir()},stop,30)
            wav=prepared['audio'];_,duration=speech._voice_pcm(wav)
            with wave.open(io.BytesIO(wav),'rb') as value:
                valid=(value.getframerate(),value.getnchannels(),value.getsampwidth())==(16000,1,2) and value.getnframes()>0
            rows.append({'case':'free-voice-'+lang,'successful':valid,'provider':'edge_free','decoded_duration_seconds':round(duration,3),'seconds':round(time.perf_counter()-began,3),'physical_playback':False,'preparation':{key:value for key,value in prepared.items() if key!='audio'}})
        except Exception as error:rows.append({'case':'free-voice-'+lang,'successful':False,'error':str(error)})
    try:
        wav,duration=speech.mp3_to_wav(speech.google_tts_audio('Please bring two copies.','en-US',stop))
        rows.append({'case':'google-free-voice-fallback','successful':duration>0,'decoded_duration_seconds':round(duration,3),'physical_playback':False})
    except Exception as error:rows.append({'case':'google-free-voice-fallback','successful':False,'error':str(error)})
    with tempfile.TemporaryDirectory(prefix='grayfeather-live-workers-') as scratch:
        settings={'speech_provider':'google_web','voice_provider':'auto','_audio_dir':scratch}
        began=time.perf_counter()
        try:
            value=speech._speech_cloud_worker('recognize',french,'fr-FR',settings,stop,20)
            rows.append({'case':'isolated-free-online-preview-worker','successful':bool(value['text'].strip()),'text':value['text'],'provider':value['provider'],'seconds':round(time.perf_counter()-began,3),'scope':'Actual same-executable worker and free recognition; the UI alone marks provisional status.'})
        except Exception as error:rows.append({'case':'isolated-free-online-preview-worker','successful':False,'error':str(error)})
        for locale,text in [('fr-FR','Bonjour. Apportez deux copies.'),('fa-IR','لطفاً دو نسخه بیاورید.')]:
            began=time.perf_counter();speech.clear_voice_cache()
            try:
                with patch('speech._play_wav_audio',return_value=True):
                    value=speech.speak_free(text,locale,settings,stop)
                rows.append({'case':'complete-reserve-router-'+locale,'successful':bool(value.get('complete')) and value.get('locale')==locale,'result':value,'seconds':round(time.perf_counter()-began,3),'physical_playback':False})
            except Exception as error:rows.append({'case':'complete-reserve-router-'+locale,'successful':False,'error':str(error)})
        began=time.perf_counter();speech.clear_voice_cache()
        try:
            def unavailable_edge(*args,**kwargs):raise speech.SpeechError('Injected Edge unavailability to verify actual Google reserve worker.')
            with patch('speech.edge_tts_audio',side_effect=unavailable_edge),patch('speech._play_wav_audio',return_value=True):
                value=speech.speak_free('Please bring two copies.','en-US',settings,stop)
            rows.append({'case':'actual-google-voice-reserve-after-edge-failure','successful':value.get('provider')=='google_web' and value.get('complete') is True,'result':value,'seconds':round(time.perf_counter()-began,3),'injected_edge_failure':True,'physical_playback':False})
        except Exception as error:rows.append({'case':'actual-google-voice-reserve-after-edge-failure','successful':False,'error':str(error)})
        cancel=threading.Event();timer=threading.Timer(.1,cancel.set);timer.start();began=time.perf_counter()
        try:
            speech._speech_cloud_worker('voice','Synthetic cancellation test.','en-US',{**settings,'voice_provider':'google_web'},cancel,10)
            rows.append({'case':'actual-worker-hard-cancellation','successful':False,'error':'Cancelled worker returned a completed result.'})
        except speech.SpeechError:
            elapsed=time.perf_counter()-began
            rows.append({'case':'actual-worker-hard-cancellation','successful':cancel.is_set() and elapsed<3,'seconds':round(elapsed,3),'private_request_files_remaining':len(list(Path(scratch).glob('speech-worker-*')))})
        finally:timer.cancel()
    return {'version':VERSION,'successful':all(r['successful'] for r in rows),'scope':'Actual bundled speech libraries, live free online dictation and voice, native offline recognition, same-executable preview/reserve workers and hard cancellation. Injected provider failures verify real surviving routes. Public-domain/synthetic fixtures only; no personal microphone capture or paid calls. Decode/preparation are real; physical playback is verified in the separate UI workflow.', 'tests':len(rows),'results':rows}
