"""Bounded preview intake and complete voice reserve regressions; no services."""
from __future__ import annotations
import ctypes
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
import wave
import speech

WORK = Path(__file__).resolve().parent


def audio(frames=4000):
    return speech._wav_from_pcm((b'\x20\x01\xe0\xfe' * ((frames+1)//2))[:frames*2])


def prepared(provider, text='complete passage', lang='en-US'):
    return {'audio': audio(), 'provider': provider, 'voice': provider+' voice',
            'locale': lang, 'characters': len(text), 'cache_hit': False}


def until(event, seconds=1):
    if not event.wait(seconds): raise AssertionError('Worker did not reach the bounded test checkpoint.')


class PreviewTests(unittest.TestCase):
    def test_native_snapshots_use_completed_copies_at_bounded_cadence(self):
        from test_app_extra import FakeWinMM
        clock, previews = [0.0], []
        class Capture(FakeWinMM):
            def add(self, handle, pointer, size):
                result=super().add(handle,pointer,size)
                header=ctypes.cast(pointer,ctypes.POINTER(speech.WaveHeader)).contents
                ctypes.memmove(header.data,b'Z'*6400,6400)  # queued driver-owned memory
                return result
            def fill(self):
                for index,header in enumerate(self.headers):
                    ctypes.memmove(header.data,bytes([65+index])*6400,6400)
                    header.recorded=6400; header.flags=1
            def start(self,handle): clock[0]=.8; self.fill(); return 0
            def reset(self,handle):
                self.reset_count+=1
                if self.reset_count==1:
                    header=self.headers[0]; ctypes.memmove(header.data,b'E'*2000,2000); header.recorded=2000
                return 0
        device=Capture()
        class Stop(threading.Event):
            def wait(self,timeout=None):
                clock[0]+=.8
                if clock[0]>=8: self.set()
                else: device.fill()
                return self.is_set()
        def receive(value,metadata): previews.append((clock[0],value,metadata))
        with patch.object(speech.ctypes,'WinDLL',return_value=device),patch.object(speech.time,'monotonic',side_effect=lambda:clock[0]):
            final,metadata=speech.record_wav(Stop(),10,receive)
        self.assertGreaterEqual(len(previews),2)
        final_pcm=speech._pcm16(final)
        for timestamp,value,status in previews:
            self.assertGreaterEqual(timestamp,3); self.assertNotIn(b'Z',speech._pcm16(value))
            self.assertTrue(final_pcm.startswith(speech._pcm16(value)))
            self.assertTrue(status['provisional']); self.assertFalse(status['complete'])
        self.assertGreaterEqual(previews[1][0]-previews[0][0],2.5)
        self.assertTrue(final_pcm.endswith(b'E'*2000)); self.assertEqual(metadata['preview_snapshots'],len(previews))
        self.assertEqual(device.closed,1); self.assertEqual(device.unprepared,4)

    def test_native_preview_limits_cpu_threads_without_changing_final(self):
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            resources=Path(folder)/'resources'; resources.mkdir()
            (resources/'whisper-cli.exe').touch(); (resources/speech.OFFLINE_MODEL).touch()
            arguments=[]
            class Process:
                returncode=0
                def __init__(self,args,**kwargs):
                    arguments.append(args); kwargs['stdout'].write(b'Two copies.'); kwargs['stdout'].flush()
                def poll(self): return 0
                def wait(self,timeout=None): return 0
            with patch.object(speech.subprocess,'Popen',Process),patch.object(speech.os,'cpu_count',return_value=8):
                for preview in (True,False): speech.recognize_offline(audio(),'en-US',{'_speech_resources':str(resources),'_audio_dir':folder,'_preview':preview})
            self.assertEqual([args[args.index('--threads')+1] for args in arguments],['2','4'])

    def test_latest_snapshot_replaces_pending_without_parallel_asr(self):
        entered, release, last = threading.Event(), threading.Event(), threading.Event()
        calls, received, active = [], [], [0, 0]
        def recognize(value, lang, config, cancel):
            active[0] += 1; active[1] = max(active[1], active[0]); calls.append(value)
            self.assertTrue(config['_preview'])
            if len(calls) == 1: entered.set(); until(release)
            active[0] -= 1
            return {'text': value.decode(), 'provider': 'fixture'}
        def receiver(value): received.append(value); last.set() if value['sequence'] == 3 else None
        with patch.object(speech, 'recognize_with_fallback', side_effect=recognize):
            coordinator = speech.PreviewRecognizer(threading.Event(), 'en-US', {}, receiver)
            try:
                coordinator.submit(b'first', {'sequence': 1}); until(entered)
                coordinator.submit(b'obsolete', {'sequence': 2}); coordinator.submit(b'latest', {'sequence': 3})
                release.set(); until(last)
            finally: coordinator.close(); coordinator.thread.join(1)
        self.assertEqual(calls, [b'first', b'latest']); self.assertEqual(active[1], 1)
        self.assertTrue(all(row['provisional'] and not row['complete'] for row in received))

    def test_duplicate_whitespace_case_text_does_not_repeat_callback(self):
        attempted = threading.Event(); received = []
        values = iter(('Two copies.', ' TWO  copies. '))
        def recognize(*args):
            value = next(values)
            if value.startswith(' '): attempted.set()
            return {'text': value, 'provider': 'fixture'}
        with patch.object(speech, 'recognize_with_fallback', side_effect=recognize):
            coordinator = speech.PreviewRecognizer(threading.Event(), 'en-US', {}, received.append)
            try:
                coordinator.submit(b'1', {});
                end = time.monotonic()+1
                while not received and time.monotonic() < end: time.sleep(.005)
                coordinator.submit(b'2', {}); until(attempted)
            finally: coordinator.close(); coordinator.thread.join(1)
        self.assertEqual(len(received), 1)

    def test_stop_never_waits_for_preview_and_late_result_is_not_emitted(self):
        entered, release = threading.Event(), threading.Event(); received = []
        def recognize(*args): entered.set(); until(release); return {'text': 'late', 'provider': 'fixture'}
        def capture(stop, limit, submit): submit(audio(), {'sequence': 1}); until(entered); return audio(8000), {'complete': True}
        try:
            with patch.object(speech, 'recognize_with_fallback', side_effect=recognize), patch.object(speech, 'record_wav', side_effect=capture):
                start = time.monotonic(); final, status = speech.record_with_previews(threading.Event(), 'en-US', {}, received.append)
                self.assertLess(time.monotonic()-start, .3); self.assertEqual(final, audio(8000)); self.assertTrue(status['complete'])
                release.set(); time.sleep(.05)
        finally: release.set()
        self.assertEqual(received, [])

    def test_abort_propagates_to_preview_recognition(self):
        entered, cancelled = threading.Event(), threading.Event(); stop = threading.Event(); stop.abort_event = threading.Event()
        def recognize(value, lang, config, cancel):
            entered.set(); self.assertTrue(cancel.wait(.5)); cancelled.set(); raise speech.SpeechError('cancelled')
        with patch.object(speech, 'recognize_with_fallback', side_effect=recognize):
            coordinator = speech.PreviewRecognizer(stop, 'en-US', {}, lambda value: self.fail('Cancelled preview emitted.'))
            try: coordinator.submit(audio(), {}); until(entered); stop.abort_event.set(); until(cancelled)
            finally: coordinator.close(); coordinator.thread.join(1)

    def test_preview_failure_does_not_discard_full_final_audio(self):
        def capture(stop, limit, submit): submit(audio(), {}); time.sleep(.03); return audio(8000), {'complete': True}
        with patch.object(speech, 'recognize_with_fallback', side_effect=speech.SpeechError('network unavailable')), patch.object(speech, 'record_wav', side_effect=capture):
            result, metadata = speech.record_with_previews(threading.Event(), 'en-US', {}, lambda value: None)
        self.assertEqual(result, audio(8000)); self.assertEqual(metadata['preview_error'], 'network unavailable')

    def test_no_preview_receiver_keeps_original_capture_path(self):
        with patch.object(speech, 'record_wav', return_value=(audio(), {})) as capture:
            speech.record_with_previews(threading.Event(), 'en-US', {}, None)
        capture.assert_called_once_with(unittest.mock.ANY, 50.0)

    def test_bad_preview_receiver_is_rejected_before_microphone_opens(self):
        with patch.object(speech,'record_wav') as capture,self.assertRaises(speech.SpeechError):
            speech.record_with_previews(threading.Event(),'en-US',{},'not callable')
        capture.assert_not_called()

    def test_cloud_preview_uses_hard_worker_boundary_and_silence_guard(self):
        config = {'speech_provider': 'google_web', '_preview': True}
        with patch.object(speech, '_speech_cloud_worker', return_value={'text': 'Two copies.'}) as worker:
            self.assertEqual(speech.recognize_wav(audio(), 'en-US', config), 'Two copies.')
            worker.assert_called_once(); self.assertEqual(worker.call_args.kwargs['timeout'], 10)
        with patch.object(speech, '_speech_cloud_worker') as worker, self.assertRaises(speech.SpeechError):
            speech.recognize_wav(speech._wav_from_pcm(b'\0\0'*4000), 'en-US', config)
        worker.assert_not_called()


class PrivateWorkerTests(unittest.TestCase):
    def worker(self, request, output, reply=None, payload_audio=None, hang=False):
        testcase = self
        class Process:
            returncode = None; killed = False
            def __init__(self, args, **kwargs):
                testcase.assertNotIn('private-key', ' '.join(args)); testcase.assertNotIn('Two copies', ' '.join(args))
                value = json.loads(Path(args[-3]).read_text(encoding='utf-8'))
                request.append(value); output.append(Path(args[-1]))
                if not hang:
                    if payload_audio: (output[-1].parent/'voice.wav').write_bytes(payload_audio)
                    output[-1].write_text(json.dumps(reply or {'version': 1, 'provider': 'google_web', 'text': 'Two copies.'}), encoding='utf-8')
                    self.returncode = 0
            def poll(self): return self.returncode
            def kill(self): self.killed = True; self.returncode = -1
            def wait(self, timeout=None): return self.returncode
        return Process

    def test_request_credentials_are_private_and_files_are_removed(self):
        request, outputs = [], []
        with tempfile.TemporaryDirectory(dir=WORK) as folder, patch.object(speech.subprocess, 'Popen', self.worker(request, outputs)):
            result = speech._speech_cloud_worker('recognize', audio(), 'en-US', {'speech_provider':'google_web', 'speech_key':'private-key', '_audio_dir':folder})
            self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertEqual(result['text'], 'Two copies.'); self.assertEqual(request[0]['config']['speech_key'], 'private-key')

    def test_voice_worker_requires_valid_complete_exact_locale_audio(self):
        for lang, waveform in (('fr-FR', audio()), ('en-US', audio()[:-2])):
            with self.subTest(lang=lang), tempfile.TemporaryDirectory(dir=WORK) as folder:
                reply = {'version':1,'provider':'google_web','voice':'fixture','locale':lang,'audio_file':'voice.wav'}
                with patch.object(speech.subprocess,'Popen',self.worker([], [], reply, waveform)), self.assertRaises(speech.SpeechError):
                    speech._speech_cloud_worker('voice','Two copies.','en-US',{'voice_provider':'google_web','_audio_dir':folder})
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_timeout_kills_worker_and_cleans_private_files(self):
        request, output, instances = [], [], []
        factory = self.worker(request, output, hang=True)
        def create(*args, **kwargs): process=factory(*args, **kwargs); instances.append(process); return process
        with tempfile.TemporaryDirectory(dir=WORK) as folder, patch.object(speech.subprocess,'Popen',side_effect=create):
            start=time.monotonic()
            with self.assertRaises(speech.SpeechError): speech._speech_cloud_worker('recognize',audio(),'en-US',{'speech_provider':'google_web','_audio_dir':folder},timeout=.1)
            self.assertLess(time.monotonic()-start,.4); self.assertEqual(list(Path(folder).iterdir()),[])
        self.assertTrue(instances[0].killed)

    def test_cancel_kills_worker_before_deadline(self):
        instances=[]; factory=self.worker([],[],hang=True); cancel=threading.Event()
        def create(*args,**kwargs): process=factory(*args,**kwargs); instances.append(process); cancel.set(); return process
        with tempfile.TemporaryDirectory(dir=WORK) as folder, patch.object(speech.subprocess,'Popen',side_effect=create), self.assertRaises(speech.SpeechError):
            speech._speech_cloud_worker('voice','Two copies.','en-US',{'voice_provider':'google_web','_audio_dir':folder},cancel)
        self.assertTrue(instances[0].killed)

    def test_offline_nested_worker_and_path_traversal_are_refused(self):
        with patch.object(speech.subprocess,'Popen') as process, self.assertRaises(speech.SpeechError):
            speech._speech_cloud_worker('recognize',audio(),'en-US',{'speech_provider':'offline'})
        process.assert_not_called()
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            request=Path(folder)/'request.json'; output=Path(folder)/'result.json'
            request.write_text(json.dumps({'version':1,'task':'recognize','locale':'en-US','provider':'google_web','timeout':10,'config':{},'audio_file':'../other.wav'}))
            with patch.object(speech,'recognize_wav') as recognize: self.assertEqual(speech.run_speech_preview_worker(request,output),1)
            recognize.assert_not_called(); self.assertFalse(output.exists())

    def test_private_worker_produces_voice_without_playing(self):
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            request=Path(folder)/'request.json'; output=Path(folder)/'result.json'
            request.write_text(json.dumps({'version':1,'task':'voice','locale':'en-US','provider':'google_web','timeout':10,'config':{},'text':'Two copies.'}))
            with patch.object(speech,'_prepare_voice_direct',return_value=prepared('google_web')), patch.object(speech.winsound,'PlaySound') as play:
                self.assertEqual(speech.run_speech_preview_worker(request,output),0)
            play.assert_not_called(); self.assertEqual((Path(folder)/'voice.wav').read_bytes(),audio())


class VoiceReserveTests(unittest.TestCase):
    def setUp(self): speech.clear_voice_cache()
    def speak(self, fake, config=None, lang='en-US'):
        with tempfile.TemporaryDirectory(dir=WORK) as folder, patch.object(speech,'_prepare_voice',side_effect=fake), patch.object(speech,'_play_wav_audio',return_value=True) as play:
            start=time.monotonic(); result=speech.speak_free('Two copies, not three.',lang,{'_audio_dir':folder,**(config or {})},threading.Event())
            return result, time.monotonic()-start, play

    def test_slow_preferred_has_short_grace_then_ready_reserve_once(self):
        cancelled=threading.Event(); active=[0,0]; lock=threading.Lock()
        def prepare(provider,text,lang,config,stop,timeout):
            with lock: active[0]+=1; active[1]=max(active[1],active[0])
            try:
                if provider=='edge_free': self.assertTrue(stop.wait(1)); cancelled.set(); raise speech.SpeechError('Voice cancelled.')
                self.assertEqual(provider,'google_web'); return prepared(provider,text,lang)
            finally:
                with lock: active[0]-=1
        result, elapsed, play=self.speak(prepare)
        self.assertEqual(result['provider'],'google_web'); self.assertLess(elapsed,.75); self.assertGreaterEqual(elapsed,.30)
        self.assertEqual(active[1],2); self.assertTrue(cancelled.is_set()); play.assert_called_once()
        self.assertIn('short quality grace',' '.join(result['trace']))

    def test_preferred_ready_within_grace_wins_over_reserve(self):
        def prepare(provider,text,lang,*args):
            if provider=='edge_free': time.sleep(.06)
            return prepared(provider,text,lang)
        result, elapsed, play=self.speak(prepare)
        self.assertEqual(result['provider'],'edge_free'); self.assertLess(elapsed,.4); play.assert_called_once()

    def test_explicit_windows_avoids_cloud_until_real_native_failure(self):
        calls=[]
        def prepare(provider,text,lang,*args): calls.append(provider); return prepared(provider,text,lang)
        result, _, play=self.speak(prepare,{'voice_provider':'windows'})
        self.assertEqual(calls,['windows']); self.assertEqual(result['provider'],'windows'); play.assert_called_once()
        calls=[]
        def fail_windows(provider,text,lang,*args):
            calls.append(provider)
            if provider=='windows': raise speech.SpeechError('No matching installed voice.')
            return prepared(provider,text,lang)
        result, _, play=self.speak(fail_windows,{'voice_provider':'windows'})
        self.assertEqual(calls[0],'windows'); self.assertEqual(result['provider'],'edge_free'); play.assert_called_once()

    def test_unmapped_locale_attempts_only_exact_native(self):
        calls=[]
        def prepare(provider,text,lang,*args): calls.append(provider); return prepared(provider,text,lang)
        result, _, _=self.speak(prepare,lang='ti-ET')
        self.assertEqual(calls,['windows']); self.assertEqual(result['locale'],'ti-ET')
        self.assertIsNone(speech.matching_sapi_voice('en-GB',[{'locales':['en-US']}],exact=True))

    def test_native_renderer_freezes_pcm_format_and_never_outputs_sound(self):
        initialized=[]; testcase=self
        token=types.SimpleNamespace(Id='voice-token')
        class Stream:
            def Open(self,path,mode,events): self.path=Path(path); testcase.assertEqual((mode,events),(3,False))
            def Close(self): self.path.write_bytes(audio())
        class Voice:
            AllowAudioOutputFormatChangesOnNextSet=True
            def GetVoices(self): return [token]
            def Speak(self,text,flags):
                testcase.assertFalse(self.AllowAudioOutputFormatChangesOnNextSet)
                testcase.assertIsInstance(self.AudioOutputStream,Stream); testcase.assertEqual(flags,17)
                testcase.assertEqual(self.AudioOutputStream.Format.Type,18)
            def WaitUntilDone(self,milliseconds): return True
        voice,stream,format=Voice(),Stream(),types.SimpleNamespace(Type=0)
        client=types.SimpleNamespace(Dispatch=lambda name:{'SAPI.SpVoice':voice,'SAPI.SpFileStream':stream,'SAPI.SpAudioFormat':format}[name])
        package=types.ModuleType('win32com'); package.client=client
        com=types.SimpleNamespace(CoInitialize=lambda:initialized.append(True),CoUninitialize=lambda:initialized.append(False))
        with tempfile.TemporaryDirectory(dir=WORK) as folder,patch.dict('sys.modules',{'pythoncom':com,'win32com':package,'win32com.client':client}),patch.object(speech,'sapi_voices',return_value=[{'id':'voice-token','name':'Exact fixture','locales':['en-us']}]),patch.object(speech.winsound,'PlaySound') as player:
            result=speech._prepare_native_voice('Two copies.','en-US',threading.Event(),folder)
            self.assertEqual(result['audio'],audio()); self.assertEqual(list(Path(folder).iterdir()),[])
        self.assertEqual(initialized,[True,False]); player.assert_not_called()

    def test_paid_voice_only_on_explicit_selection_even_with_azure_asr_key(self):
        config={'speech_provider':'azure','speech_key':'private-key','speech_region':'uksouth'}
        self.assertNotIn('azure',speech.voice_route_plan('en-US',config)['providers'])
        config['voice_provider']='azure'
        self.assertEqual(speech.voice_route_plan('en-US',config)['providers'][0],'azure')
        with patch.object(speech,'request',return_value=audio()) as request:
            speech._azure_voice_audio('Two copies.','en-US',{**config,'speech_provider':'auto'},threading.Event())
        self.assertEqual(request.call_args.kwargs['maximum'],8*1024*1024)

    def test_actual_failures_only_change_auto_session_order(self):
        session=speech.VoiceSession()
        def prepare(provider,text,lang,*args):
            if provider=='edge_free': raise speech.SpeechError('Service actually failed.')
            return prepared(provider,text,lang)
        self.speak(prepare,{'_voice_session':session})
        self.assertEqual(speech.voice_route_plan('en-US',{'_voice_session':session})['providers'][0],'google_web')
        self.assertEqual(speech.voice_route_plan('en-US',{'_voice_session':session,'voice_provider':'edge_free'})['providers'][0],'edge_free')
        self.assertNotIn(('windows','en-US'),session.failures)

    def test_failed_reserves_never_produce_partial_or_double_audio(self):
        def prepare(provider,*args): raise speech.SpeechError('Late chunk failed.')
        with tempfile.TemporaryDirectory(dir=WORK) as folder, patch.object(speech,'_prepare_voice',side_effect=prepare), patch.object(speech,'_play_wav_audio') as play, self.assertRaises(speech.SpeechError):
            speech.speak_free('Two copies.','en-US',{'_audio_dir':folder},threading.Event())
        play.assert_not_called()

    def test_cancellation_stops_both_reserves_without_playback(self):
        stop=threading.Event(); entered=threading.Event(); count=[0]; lock=threading.Lock()
        def prepare(provider,text,lang,config,cancel,timeout):
            with lock:
                count[0]+=1
                if count[0]==2: entered.set()
            self.assertTrue(cancel.wait(1)); raise speech.SpeechError('Voice cancelled.')
        timer=threading.Thread(target=lambda:(until(entered),stop.set())); timer.start()
        try:
            with tempfile.TemporaryDirectory(dir=WORK) as folder, patch.object(speech,'_prepare_voice',side_effect=prepare), patch.object(speech,'_play_wav_audio') as play, self.assertRaises(speech.SpeechError):
                start=time.monotonic(); speech.speak_free('Two copies.','en-US',{'_audio_dir':folder},stop)
            self.assertLess(time.monotonic()-start,.5); play.assert_not_called()
        finally: stop.set(); timer.join(1)

    def test_cache_reuses_validated_complete_audio_without_worker(self):
        with patch.object(speech,'_speech_cloud_worker',return_value=prepared('google_web')) as worker:
            first=speech._prepare_voice('google_web','Two copies.','en-US',{},threading.Event(),10)
            second=speech._prepare_voice('google_web','Two copies.','en-US',{},threading.Event(),10)
        self.assertFalse(first['cache_hit']); self.assertTrue(second['cache_hit']); worker.assert_called_once()

    def test_cache_scope_locale_text_provider_credentials_ttl_and_bound(self):
        base=speech._voice_cache_key('azure','Two copies.','en-US',{'speech_key':'a'})
        variants=[speech._voice_cache_key('azure','Two copies.','en-US',{'speech_key':'b'}),speech._voice_cache_key('azure','Three copies.','en-US',{'speech_key':'a'}),speech._voice_cache_key('azure','Two copies.','fr-FR',{'speech_key':'a'}),speech._voice_cache_key('edge_free','Two copies.','en-US',{})]
        self.assertTrue(all(key!=base for key in variants))
        for index in range(5): speech._voice_cache_put(index,prepared('google_web'))
        self.assertEqual(len(speech._VOICE_CACHE),4); self.assertIsNone(speech._voice_cache_get(0))
        with patch.object(speech.time,'monotonic',return_value=time.monotonic()+121): self.assertIsNone(speech._voice_cache_get(4))
        self.assertEqual(len(speech._VOICE_CACHE),0)

    def test_cache_memory_bound_and_fresh_installed_windows_voice(self):
        for index in range(4): speech._voice_cache_put(index,{**prepared('google_web'),'audio':b'x'*(6*1024*1024)})
        self.assertLessEqual(sum(len(row[1]['audio']) for row in speech._VOICE_CACHE.values()),20*1024*1024)
        self.assertEqual(len(speech._VOICE_CACHE),3)
        with patch.object(speech,'_speech_cloud_worker',return_value=prepared('windows')) as worker:
            for _ in range(2): speech._prepare_voice('windows','Two copies.','en-US',{},threading.Event(),10)
        self.assertEqual(worker.call_count,2)

    def test_serial_player_failure_and_cancel_remove_private_pcm(self):
        with tempfile.TemporaryDirectory(dir=WORK) as folder, patch.object(speech.winsound,'PlaySound',side_effect=[OSError('Output device gone'),None]),self.assertRaises(OSError):
            speech._play_wav_audio(audio(),threading.Event(),folder)
        self.assertFalse(speech._VOICE_PLAYBACK_LOCK.locked())
        stop=threading.Event(); stop.set()
        with tempfile.TemporaryDirectory(dir=WORK) as folder,patch.object(speech.winsound,'PlaySound') as play:
            self.assertFalse(speech._play_wav_audio(audio(),stop,folder)); self.assertEqual(list(Path(folder).iterdir()),[])
        play.assert_not_called()

    def test_cached_cancelled_request_never_plays_or_prepares(self):
        stop=threading.Event(); stop.set()
        with patch.object(speech,'_prepare_voice') as prepare, patch.object(speech,'_play_wav_audio') as play, self.assertRaises(speech.SpeechError):
            speech.speak_free('Two copies.','en-US',{},stop)
        prepare.assert_not_called(); play.assert_not_called()


class TransientEdgeVoiceTests(unittest.TestCase):
    def setUp(self):
        speech.clear_voice_cache()
        # These tests isolate the existing Edge retry path. Offline reserve
        # integration has its own complete-audio/cancellation tests.
        self.offline=patch.object(speech,'offline_voice_available',return_value=False)
        self.offline.start(); self.addCleanup(self.offline.stop)
    def test_persian_tts_unsupported_google_route_removed_without_disabling_asr(self):
        self.assertNotIn('fa-IR',speech.GOOGLE_TTS_LOCALES)
        self.assertIn('fa-IR',speech.GOOGLE_STT_LOCALES)
        self.assertEqual(speech.voice_route_plan('fa-IR')['providers'],['edge_free','windows'])
        with patch.object(speech,'request') as request,self.assertRaises(speech.SpeechError):
            speech.google_tts_audio('دو نسخه','fa-IR')
        request.assert_not_called()

    def test_transient_edge_failure_retries_once_then_one_full_playback(self):
        with tempfile.TemporaryDirectory(dir=WORK) as folder,patch.object(speech,'edge_tts_audio',side_effect=[speech._TransientVoiceError('Missing worker result'),b'complete']) as edge,patch.object(speech,'mp3_to_wav',return_value=(audio(),.25)),patch.object(speech,'_speech_cloud_worker') as native,patch.object(speech,'google_tts_audio') as google,patch.object(speech,'_play_wav_audio',return_value=True) as play:
            result=speech.speak_free('دو نسخه بیاورید','fa-IR',{'_audio_dir':folder},threading.Event())
        self.assertEqual(edge.call_count,2); self.assertEqual(result['synthesis_attempts'],2)
        self.assertEqual(result['provider'],'edge_free'); self.assertTrue(result['complete'])
        self.assertEqual(len(result['preparation_trace']),1); play.assert_called_once(); google.assert_not_called(); native.assert_not_called()

    def test_late_chunk_failure_discards_all_prior_chunks_and_rebuilds_passage(self):
        text='x'*700
        with patch.object(speech,'edge_tts_audio',side_effect=[b'old',speech._TransientVoiceError('Missing worker result'),b'new-first',b'new-last']) as edge,patch.object(speech,'mp3_to_wav',side_effect=[(audio(1000),.1),(audio(2000),.1),(audio(3000),.1)]),patch.object(speech,'_play_wav_audio') as play:
            result=speech._prepare_voice_direct('edge_free',text,'fa-IR',{},threading.Event(),60)
        self.assertEqual([call.args[0] for call in edge.call_args_list],['x'*500,'x'*200,'x'*500,'x'*200])
        pcm,duration=speech._voice_pcm(result['audio']); self.assertEqual(len(pcm),10000)
        self.assertEqual(result['synthesis_attempts'],2); play.assert_not_called()

    def test_second_transient_failure_stops_and_never_caches_partial_audio(self):
        with patch.object(speech,'edge_tts_audio',side_effect=speech._TransientVoiceError('Missing worker result')) as edge,patch.object(speech,'_play_wav_audio') as play,self.assertRaises(speech.SpeechError):
            speech._prepare_voice('edge_free','Two copies.','en-US',{},threading.Event(),60)
        self.assertEqual(edge.call_count,2); self.assertEqual(len(speech._VOICE_CACHE),0); play.assert_not_called()

    def test_cancelled_first_failure_never_starts_retry(self):
        stop=threading.Event()
        def fail(*args,**kwargs): stop.set(); raise speech._TransientVoiceError('Missing worker result')
        with patch.object(speech,'edge_tts_audio',side_effect=fail) as edge,self.assertRaises(speech.SpeechError):
            speech._prepare_voice_direct('edge_free','Two copies.','en-US',{},stop,60)
        edge.assert_called_once()

    def test_retry_shares_original_deadline_and_does_not_extend_it(self):
        clock=[0.0]; budgets=[]
        def synthesize(text,lang,stop,timeout,**kwargs):
            budgets.append(timeout); clock[0]+=.4
            if len(budgets)==1: raise speech._TransientVoiceError('Missing worker result')
            return b'complete'
        with patch.object(speech.time,'monotonic',side_effect=lambda:clock[0]),patch.object(speech,'edge_tts_audio',side_effect=synthesize),patch.object(speech,'mp3_to_wav',return_value=(audio(),.25)):
            result=speech._prepare_voice_direct('edge_free','Two copies.','en-US',{},threading.Event(),1)
        self.assertEqual(budgets,[1,.6]); self.assertEqual(result['synthesis_attempts'],2)
        clock=[0.0]
        def expire(*args,**kwargs): clock[0]=1; raise speech._TransientVoiceError('Missing worker result')
        with patch.object(speech.time,'monotonic',side_effect=lambda:clock[0]),patch.object(speech,'edge_tts_audio',side_effect=expire) as edge,self.assertRaises(speech.SpeechError):
            speech._prepare_voice_direct('edge_free','Two copies.','en-US',{},threading.Event(),1)
        edge.assert_called_once()

    def test_bad_locale_text_or_decoded_pcm_never_retries(self):
        for lang,text in (('fa-AF','Two copies.'),('en-US','x'*6001),('en-US','')):
            with self.subTest(lang=lang,text_length=len(text)),patch.object(speech,'edge_tts_audio') as edge,self.assertRaises(speech.SpeechError):
                speech._prepare_voice_direct('edge_free',text,lang,{},threading.Event(),60)
            edge.assert_not_called()
        with patch.object(speech,'edge_tts_audio',return_value=b'invalid') as edge,patch.object(speech,'mp3_to_wav',return_value=(audio()[:-2],.25)),self.assertRaises(speech.SpeechError):
            speech._prepare_voice_direct('edge_free','Two copies.','en-US',{},threading.Event(),60)
        edge.assert_called_once()

    def test_ordinary_validation_or_service_errors_are_not_retryable(self):
        for error in (speech.SpeechError('Invalid audio'),speech.SpeechError('Voice cancelled.'),speech.SpeechError('Unsupported locale')):
            with self.subTest(error=str(error)),patch.object(speech,'edge_tts_audio',side_effect=error) as edge,self.assertRaises(speech.SpeechError):
                speech._prepare_voice_direct('edge_free','Two copies.','en-US',{},threading.Event(),60)
            edge.assert_called_once()


if __name__=='__main__': unittest.main(verbosity=2)
