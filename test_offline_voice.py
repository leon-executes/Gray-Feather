"""Native offline preparation boundaries; fake native process, real PCM codec."""
from __future__ import annotations
import array
import hashlib
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import offline_voice
import speech

WORK=Path(__file__).resolve().parent


def raw_pcm(frames=2205):
    return array.array('h',(int(8000*math.sin(index*2*math.pi*330/22050)) for index in range(frames))).tobytes()


class OfflineVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='voice-tests-',dir=WORK); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name); self.assertTrue(self.base.resolve().is_relative_to(WORK.resolve()))
        self.config={'_offline_voice_resources':str(self.base),'_audio_dir':str(self.base/'scratch')}
        (self.base/'piper'/'espeak-ng-data').mkdir(parents=True); (self.base/'models'/'fa-IR').mkdir(parents=True)
        for name in offline_voice._RUNTIME_FILES: (self.base/'piper'/name).touch()
        (self.base/'piper'/'espeak-ng-data'/'phondata').touch()
        self.model={'id':'fa_IR-amir-medium','name':'Fixture Persian','filename':'fa_IR-amir-medium.onnx','sample_rate':22050,
                    'model_bytes':4,'model_sha256':hashlib.sha256(b'test').hexdigest(),'espeak_voice':'fa'}
        self.model_path=self.base/'models'/'fa-IR'/self.model['filename']; self.model_path.write_bytes(b'test')
        self.metadata={'audio':{'sample_rate':22050},'num_speakers':1,'phoneme_type':'espeak','espeak':{'voice':'fa'}}
        self.config_path=self.model_path.with_name(self.model_path.name+'.json'); self.config_path.write_text(json.dumps(self.metadata))
        self.registry=patch.dict(offline_voice.VOICE_MODELS,{'fa-IR':self.model}); self.registry.start(); self.addCleanup(self.registry.stop)
        offline_voice._VALIDATED.clear(); speech.clear_voice_cache()
        self.instances=[]

    def process(self,output=raw_pcm(),hang=False,exit_code=0,callback=None):
        testcase=self
        class Process:
            returncode=None; killed=False
            def __init__(self,args,**kwargs):
                testcase.instances.append(self); self.args=args; self.kwargs=kwargs
                payload=json.load(kwargs['stdin']); testcase.assertEqual(payload['text'],'دو نسخه بیاورید.\nدر را باز نکنید.')
                testcase.assertNotIn(payload['text'],' '.join(args)); testcase.assertEqual(args[args.index('--model')+1],'fa_IR-amir-medium.onnx')
                testcase.assertEqual(kwargs['cwd'],testcase.base/'models'/'fa-IR')
                testcase.assertTrue(all(argument.isascii() for argument in args[1:])); testcase.assertNotIn('PIPE',str(kwargs))
                kwargs['stdout'].write(output); kwargs['stdout'].flush()
                if callback: callback(self)
                if not hang: self.returncode=exit_code
            def poll(self): return self.returncode
            def kill(self): self.killed=True; self.returncode=-1
            def wait(self,timeout=None): return self.returncode
        return Process

    def prepare(self,stop=None,timeout=1):
        return offline_voice.prepare('دو نسخه بیاورید.\nدر را باز نکنید.','fa-IR',self.config,stop,timeout)

    def test_exact_registry_never_borrows_persian_for_dari_or_kurdish(self):
        self.assertTrue(offline_voice.available('fa-IR',self.config))
        for locale in ('fa-AF','prs-AF','ckb-IQ','ku-TR','ti-ET'):
            self.assertFalse(offline_voice.available(locale,self.config))
            with self.subTest(locale=locale),patch.object(offline_voice.subprocess,'Popen') as process,self.assertRaises(offline_voice.OfflineVoiceError):
                offline_voice.prepare('test',locale,self.config)
            process.assert_not_called()

    def test_release_voice_has_creator_pinned_provenance(self):
        # Inspect the saved original registry rather than our synthetic model.
        self.registry.stop()
        try:
            value=offline_voice.VOICE_MODELS['fa-IR']
            self.assertEqual(value['id'],'fa_IR-gyro-medium')
            self.assertEqual(value['model_license'],'MIT')
            self.assertEqual(value['model_sha256'],'37dfae43c82ee38ca9e6aac4ffef76a74d6b282ccbc397b27761f35d355c99ba')
            self.assertIn(value['creator_revision'],value['source'])
        finally: self.registry.start()

    def test_complete_native_audio_is_resampled_before_return_without_playback(self):
        with patch.object(offline_voice.subprocess,'Popen',self.process()),patch.object(speech.winsound,'PlaySound') as play:
            result=self.prepare()
        pcm,duration=speech._voice_pcm(result['audio']); self.assertGreater(duration,.09); self.assertLess(duration,.11)
        self.assertEqual(result['provider'],'offline_piper'); self.assertEqual(result['locale'],'fa-IR')
        self.assertTrue(result['offline']); self.assertTrue(result['complete_preparation']); self.assertGreater(len(pcm),3100)
        play.assert_not_called(); self.assertEqual(list((self.base/'scratch').iterdir()),[])

    def test_missing_assets_disable_capability_before_process(self):
        self.model_path.unlink()
        self.assertFalse(offline_voice.available('fa-IR',self.config))
        with patch.object(offline_voice.subprocess,'Popen') as process,self.assertRaises(offline_voice.OfflineVoiceError): self.prepare()
        process.assert_not_called()

    def test_missing_native_dependency_disables_capability(self):
        (self.base/'piper'/'piper_phonemize.dll').unlink()
        self.assertFalse(offline_voice.available('fa-IR',self.config))
        with patch.object(offline_voice.subprocess,'Popen') as process,self.assertRaises(offline_voice.OfflineVoiceError): self.prepare()
        process.assert_not_called()

    def test_corrupt_model_or_wrong_config_never_loads_native_model(self):
        for corruption in ('model','config'):
            with self.subTest(corruption=corruption):
                self.model_path.write_bytes(b'fake' if corruption=='model' else b'test')
                self.config_path.write_text(json.dumps({**self.metadata,'num_speakers':2} if corruption=='config' else self.metadata))
                with patch.object(offline_voice.subprocess,'Popen') as process,self.assertRaises(offline_voice.OfflineVoiceError): self.prepare()
                process.assert_not_called()

    def test_cached_model_validation_is_invalidated_by_file_change(self):
        offline_voice._validate_model('fa-IR',self.base)
        self.assertEqual(len(offline_voice._VALIDATED),1)
        self.model_path.write_bytes(b'fake')
        with self.assertRaises(offline_voice.OfflineVoiceError): offline_voice._validate_model('fa-IR',self.base)

    def test_cancel_before_preparation_never_starts_process(self):
        stop=threading.Event(); stop.set()
        with patch.object(offline_voice.subprocess,'Popen') as process,self.assertRaises(offline_voice.OfflineVoiceError): self.prepare(stop)
        process.assert_not_called()

    def test_cancel_during_native_inference_kills_and_cleans_output(self):
        stop=threading.Event()
        with patch.object(offline_voice.subprocess,'Popen',self.process(hang=True,callback=lambda process:stop.set())),self.assertRaises(offline_voice.OfflineVoiceError): self.prepare(stop)
        self.assertTrue(self.instances[0].killed); self.assertEqual(list((self.base/'scratch').iterdir()),[])

    def test_deadline_kills_native_process_with_no_partial_result(self):
        with patch.object(offline_voice.subprocess,'Popen',self.process(hang=True)),self.assertRaises(offline_voice.OfflineVoiceError):
            start=time.monotonic(); self.prepare(timeout=.1)
        self.assertLess(time.monotonic()-start,.35); self.assertTrue(self.instances[0].killed)
        self.assertEqual(list((self.base/'scratch').iterdir()),[])

    def test_empty_odd_oversized_or_nonzero_exit_audio_never_escapes(self):
        for output,exit_code in ((b'',0),(b'\0',0),(b'\0'*(240*22050*2+2),0),(raw_pcm(),1)):
            with self.subTest(bytes=len(output),exit_code=exit_code),patch.object(offline_voice.subprocess,'Popen',self.process(output,exit_code=exit_code)),self.assertRaises(offline_voice.OfflineVoiceError): self.prepare()
            self.assertEqual(list((self.base/'scratch').iterdir()),[])

    def test_text_unicode_size_and_timeout_boundaries_never_start_process(self):
        for text,timeout in (('',1),('x'*6001,1),('\ud800',1),('test',0),('test',True),('test',61)):
            with self.subTest(text_length=len(text),timeout=timeout),patch.object(offline_voice.subprocess,'Popen') as process,self.assertRaises(offline_voice.OfflineVoiceError):
                offline_voice.prepare(text,'fa-IR',self.config,timeout=timeout)
            process.assert_not_called()

    def test_local_only_selection_excludes_every_network_route(self):
        plan=speech.voice_route_plan('fa-IR',{**self.config,'voice_provider':'offline','speech_key':'paid-key'})
        self.assertEqual(plan['providers'],['offline_piper','windows']); self.assertTrue(plan['local_only'])
        self.assertEqual(speech.voice_route_plan('en-US',{**self.config,'voice_provider':'offline'})['providers'],['windows'])

    def test_automatic_persian_reserve_survives_edge_failure_and_plays_once(self):
        original=speech._prepare_voice
        def prepare(provider,*args):
            if provider=='edge_free': raise speech.SpeechError('403 Edge unavailable')
            if provider=='windows': raise AssertionError('Bundled working reserve must precede Windows.')
            return original(provider,*args)
        with patch.object(speech,'_prepare_voice',side_effect=prepare),patch.object(offline_voice.subprocess,'Popen',self.process()),patch.object(speech,'_play_wav_audio',return_value=True) as play:
            result=speech.speak_free('دو نسخه بیاورید.\nدر را باز نکنید.','fa-IR',self.config,threading.Event())
        self.assertEqual(result['provider'],'offline_piper'); self.assertTrue(result['complete']); play.assert_called_once()
        self.assertIn('403 Edge unavailable',' '.join(result['trace']))

    def test_offline_voice_cache_contains_complete_audio_and_model_identity(self):
        with patch.object(offline_voice.subprocess,'Popen',self.process()) as process:
            first=speech._prepare_voice('offline_piper','دو نسخه بیاورید.\nدر را باز نکنید.','fa-IR',self.config,threading.Event(),1)
            second=speech._prepare_voice('offline_piper','دو نسخه بیاورید.\nدر را باز نکنید.','fa-IR',self.config,threading.Event(),1)
        self.assertEqual(len(self.instances),1); self.assertFalse(first['cache_hit']); self.assertTrue(second['cache_hit'])
        key=speech._voice_cache_key('offline_piper','test','fa-IR',self.config)
        self.assertEqual(key[2],offline_voice.cache_identity('fa-IR'))


if __name__=='__main__': unittest.main(verbosity=2)
