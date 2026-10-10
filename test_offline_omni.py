"""Portable native ASR boundaries, complete recording coverage and routing."""
from __future__ import annotations
import array
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import offline_omni as omni
import speech

ROOT=Path(__file__).resolve().parent

def pcm(seconds=1):
    return array.array('h',[1800,-1800]*int(8000*seconds)).tobytes()

class OmniTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='omni-tests-café-',dir=ROOT); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name); self.assets=self.base/'assets'; self.assets.mkdir()
        self.files={name:(4,hashlib.sha256(b'test').hexdigest()) for name in ('sherpa-onnx-offline.exe','model.int8.onnx','tokens.txt')}
        self.patch=patch.dict(omni.MODEL_FILES,self.files); self.patch.start(); self.addCleanup(self.patch.stop)
        for name in omni.MODEL_FILES: (self.assets/name).write_bytes(b'test')
        (self.assets/'sherpa-onnx-offline.exe').touch()
        self.config={'_omni_resources':str(self.assets),'_audio_dir':str(self.base/'private فارسی')}
        omni._VALIDATED.clear(); self.instances=[]

    def process(self,text='kopii lama malee sadii miti',hang=False,code=0,callback=None,raw=None):
        testcase=self
        class Process:
            returncode=None; killed=False
            def __init__(self,args,**kwargs):
                testcase.instances.append(self); self.args=args; self.kwargs=kwargs
                testcase.assertEqual(kwargs['cwd'],testcase.assets)
                testcase.assertIn('--omnilingual-asr-model=model.int8.onnx',args)
                testcase.assertIn('--tokens=tokens.txt',args)
                testcase.assertTrue(Path(args[-1]).is_file()); testcase.assertNotIn('PIPE',str(kwargs))
                data=raw if raw is not None else json.dumps({'text':text}).encode('utf-8')+b'\n'
                kwargs['stdout'].write(data); kwargs['stdout'].flush()
                if callback: callback(self)
                if not hang: self.returncode=code
            def poll(self): return self.returncode
            def kill(self): self.killed=True; self.returncode=-1
            def wait(self,timeout=None): return self.returncode
        return Process

    def recognize(self,seconds=1,locale='om-ET',cancel=None):
        return omni.recognize(omni._wav(pcm(seconds)),locale,self.config,cancel)

    def assert_clean(self):
        folder=Path(self.config['_audio_dir'])
        self.assertTrue(not folder.exists() or list(folder.iterdir())==[])

    def test_release_registry_requires_actual_native_locale_proofs(self):
        self.assertEqual(set(omni.LOCALES),{'om-ET','ckb-IQ'})
        self.assertTrue(omni.available('om-ET',self.config))
        for locale in ('fa-AF','fa-IR','ti-ET','ku-TR','en-US'):
            self.assertFalse(omni.available(locale,self.config))
            with self.subTest(locale=locale),patch.object(omni.subprocess,'Popen') as process,self.assertRaises(omni.OmniError):
                self.recognize(locale=locale)
            process.assert_not_called()

    def test_complete_result_identifies_local_unconditioned_engine(self):
        with patch.object(omni.subprocess,'Popen',self.process()): value=self.recognize()
        self.assertEqual(value['provider'],'omnilingual'); self.assertTrue(value['complete']); self.assertTrue(value['offline'])
        self.assertEqual(value['chunks'],1); self.assertFalse(value['language_conditioned']); self.assertTrue(value['warnings'])
        self.assert_clean()

    def test_contiguous_chunk_boundaries_preserve_every_sample_and_tail(self):
        raw=bytearray(pcm(50)); point=28*16000
        raw[(point-320)*2:(point+320)*2]=b'\0'*1280
        parts=omni.segments(bytes(raw))
        self.assertEqual(b''.join(parts),bytes(raw)); self.assertEqual(sum(map(len,parts)),50*32000)
        self.assertTrue(all(0<len(part)<40*32000 and len(part)%2==0 for part in parts))
        self.assertLess(abs(len(parts[0])/32000-28),.05)
        self.assertEqual(parts[-1][-32:],bytes(raw)[-32:])

    def test_later_chunk_failure_rejects_whole_turn_without_partial_return(self):
        classes=[self.process(),self.process(code=1)]
        def create(*args,**kwargs): return classes.pop(0)(*args,**kwargs)
        with patch.object(omni.subprocess,'Popen',side_effect=create),self.assertRaisesRegex(omni.OmniError,'complete recording'):
            self.recognize(50)
        self.assertEqual(len(self.instances),2); self.assert_clean()

    def test_cancel_before_start_creates_no_requests_or_audio(self):
        cancel=threading.Event(); cancel.set()
        with patch.object(omni.subprocess,'Popen') as process,self.assertRaisesRegex(omni.OmniError,'cancelled'):
            self.recognize(cancel=cancel)
        process.assert_not_called(); self.assert_clean()

    def test_native_cancellation_kills_process_and_cleans_private_files(self):
        cancel=threading.Event(); timer=threading.Timer(.06,cancel.set)
        timer.start(); self.addCleanup(timer.cancel); started=time.monotonic()
        with patch.object(omni.subprocess,'Popen',self.process(hang=True)),self.assertRaisesRegex(omni.OmniError,'cancelled'):
            self.recognize(cancel=cancel)
        self.assertLess(time.monotonic()-started,.5); self.assertTrue(self.instances[0].killed); self.assert_clean()

    def test_native_deadline_kills_without_a_later_retry(self):
        with patch.object(omni,'time_budget',return_value=.06),patch.object(omni.subprocess,'Popen',self.process(hang=True)),self.assertRaisesRegex(omni.OmniError,'time budget'):
            self.recognize()
        self.assertEqual(len(self.instances),1); self.assertTrue(self.instances[0].killed); self.assert_clean()

    def test_expired_deadline_and_cancel_never_start_native_request(self):
        for stopped in (False,True):
            cancel=threading.Event()
            if stopped: cancel.set()
            with self.subTest(stopped=stopped),patch.object(omni.subprocess,'Popen') as process,self.assertRaises(omni.OmniError):
                omni._native(self.assets,self.base/'none.wav',self.base/'none.json',cancel,time.monotonic()-1)
            process.assert_not_called()

    def test_bad_model_hash_and_missing_tokens_fail_before_native(self):
        (self.assets/'model.int8.onnx').write_bytes(b'evil')
        with patch.object(omni.subprocess,'Popen') as process,self.assertRaisesRegex(omni.OmniError,'integrity'):
            self.recognize()
        process.assert_not_called(); (self.assets/'tokens.txt').unlink()
        self.assertFalse(omni.available('om-ET',self.config)); self.assert_clean()

    def test_validation_cache_rechecks_replaced_model(self):
        with patch.object(omni.subprocess,'Popen',self.process()): self.recognize()
        old=(self.assets/'model.int8.onnx').stat().st_mtime_ns
        (self.assets/'model.int8.onnx').write_bytes(b'evil')
        import os
        os.utime(self.assets/'model.int8.onnx',ns=(old+1000000,old+1000000))
        with patch.object(omni.subprocess,'Popen') as process,self.assertRaises(omni.OmniError): self.recognize()
        process.assert_not_called(); self.assert_clean()

    def test_invalid_and_oversized_response_never_returns_text(self):
        for raw in (b'\xff',b'{}\n',b'[]\n',b'{"text":1}\n',b'{"text":"a"}\n{}\n',b'a'*(1024*1024+1)):
            with self.subTest(raw=raw[:15]),patch.object(omni.subprocess,'Popen',self.process(raw=raw)),self.assertRaises(omni.OmniError): self.recognize()
            self.assert_clean()

    def test_wrong_script_and_silence_are_not_claimed_as_dictation(self):
        with patch.object(omni.subprocess,'Popen',self.process(text='different script')),self.assertRaisesRegex(omni.OmniError,'script'):
            self.recognize(locale='ckb-IQ')
        with patch.object(omni.subprocess,'Popen') as process,self.assertRaisesRegex(omni.OmniError,'signal'):
            omni.recognize(omni._wav(b'\0'*32000),'om-ET',self.config)
        process.assert_not_called(); self.assert_clean()

    def test_bad_pcm_and_duration_budget_rejected(self):
        with patch.object(omni.subprocess,'Popen') as process,self.assertRaises(omni.OmniError): omni.recognize(b'invalid','om-ET',self.config)
        process.assert_not_called()
        self.assertEqual(omni.time_budget(1),15); self.assertLessEqual(omni.time_budget(50),60)
        for duration in (True,0,-1,51,'1',float('nan')):
            with self.subTest(duration=duration),self.assertRaises(omni.OmniError): omni.time_budget(duration)

class OmniRoutingTests(unittest.TestCase):
    def test_automatic_gap_routes_never_call_an_unrelated_cloud_provider(self):
        for locale in ('om-ET','ckb-IQ'):
            with self.subTest(locale=locale),patch.object(speech,'recognize_omnilingual',return_value='fixture') as omni_call,patch.object(speech,'recognize_google_web') as google,patch.object(speech,'recognize_offline') as whisper:
                value=speech.recognize_with_fallback(speech._wav_from_pcm(pcm()),locale,{'speech_provider':'auto'})
            self.assertEqual(value['provider'],'omnilingual'); self.assertIn('audio stayed on this PC',' '.join(value['trace']))
            omni_call.assert_called_once(); google.assert_not_called(); whisper.assert_not_called()

    def test_unproven_exact_locales_and_dari_are_not_borrowed(self):
        for locale in ('fa-AF','ti-ET','ku-TR'):
            self.assertFalse(speech.recognition_supported(locale,'omnilingual'))
            self.assertFalse(speech.recognition_supported(locale,'auto'))
            with self.subTest(locale=locale),patch.object(speech,'recognize_omnilingual') as recognize,self.assertRaises(speech.SpeechError):
                speech.recognize_with_fallback(speech._wav_from_pcm(pcm()),locale,{'speech_provider':'auto'})
            recognize.assert_not_called()

if __name__=='__main__': unittest.main()
