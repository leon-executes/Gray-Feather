"""Speech routing and isolated voice boundaries; no network or physical audio."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import offline_reserve as reserve
import speech
from tests.test_free_speech import wav_data
from voice_text import spell_numbers

class ReserveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config={'_reserve_resources':str(self.root),'_audio_dir':str(self.root/'private')}
        (self.root/'helper').mkdir();(self.root/'helper'/'GrayFeatherVoice.exe').write_bytes(b'test')
        self.model=self.root/'models'/'ckb-IQ';self.model.mkdir(parents=True)
        self.entry={'kind':'vekol','enabled':True,'files':{}}
        for name in ('model.onnx','config.json'):
            (self.model/name).write_bytes(b'test')
            self.entry['files'][name]={'bytes':4,'sha256':hashlib.sha256(b'test').hexdigest()}
        self.catalog({'ckb-IQ':self.entry});reserve._VALIDATED.clear()
    def catalog(self,value):
        (self.root/'catalog.json').write_text(json.dumps(value),encoding='utf-8')
    def test_missing_or_bad_catalog_disables_neural_without_exception(self):
        for value in ([],None,2,{'ckb-IQ':True},{'ckb-IQ':{'enabled':True,'files':[]}}):
            with self.subTest(value=value):
                self.catalog(value);self.assertFalse(reserve.available('ckb-IQ','neural',self.config))
    def test_catalog_path_escape_rejected(self):
        self.entry['files']['../../outside']={'bytes':4,'sha256':'0'*64}
        self.catalog({'ckb-IQ':self.entry})
        self.assertFalse(reserve.available('ckb-IQ','neural',self.config))
    def test_model_hash_checked_before_native_process(self):
        (self.model/'model.onnx').write_bytes(b'evil')
        with patch.object(reserve.subprocess,'Popen') as process,self.assertRaisesRegex(reserve.ReserveError,'integrity'):
            reserve.prepare('دەقی تاقیکردنەوە','ckb-IQ','neural',self.config)
        process.assert_not_called()
    def test_missing_model_falls_through_capability(self):
        self.assertTrue(reserve.available('ckb-IQ','neural',self.config))
        (self.model/'model.onnx').unlink()
        self.assertFalse(reserve.available('ckb-IQ','neural',self.config))
    def test_cancel_before_start_creates_no_audio(self):
        stop=threading.Event();stop.set()
        with patch.object(reserve.subprocess,'Popen') as process,self.assertRaisesRegex(reserve.ReserveError,'cancelled'):
            reserve.prepare('test','ckb-IQ','neural',self.config,stop)
        process.assert_not_called();self.assertFalse((self.root/'private').exists())
    def test_deadline_and_input_guards(self):
        for timeout in (True,0,61,float('nan'),float('inf')):
            with self.subTest(timeout=timeout),self.assertRaises(reserve.ReserveError):
                reserve.prepare('test','ckb-IQ','neural',self.config,timeout=timeout)
        for text in ('',None,'x'*6001,'two\0not three'):
            with self.subTest(text=str(text)[:10]),self.assertRaises(reserve.ReserveError):
                reserve.prepare(text,'ckb-IQ','neural',self.config)
    def test_native_hang_is_killed_and_private_audio_removed(self):
        class Process:
            returncode=None
            def poll(self):return self.returncode
            def kill(self):self.returncode=-9
            def wait(self,timeout):return self.returncode
        process=Process()
        with patch.object(reserve.subprocess,'Popen',return_value=process),self.assertRaisesRegex(reserve.ReserveError,'deadline'):
            reserve.prepare('test','ckb-IQ','neural',self.config,timeout=.1)
        self.assertEqual(process.returncode,-9)
        self.assertEqual(list((self.root/'private').iterdir()),[])
    def test_cancellation_while_waiting_never_starts_helper(self):
        stop=threading.Event();reserve._SLOT.acquire()
        timer=threading.Timer(.05,stop.set);timer.start()
        try:
            with patch.object(reserve.subprocess,'Popen') as process,self.assertRaisesRegex(reserve.ReserveError,'cancelled'):
                reserve.prepare('test','ckb-IQ','neural',self.config,stop)
            process.assert_not_called()
        finally:reserve._SLOT.release();timer.cancel()

class RoutingTests(unittest.TestCase):
    def test_measured_local_routes_do_not_upload_healthy_audio(self):
        for lang in speech.OMNI_FIRST:
            with self.subTest(lang=lang),patch.object(speech,'recognize_omnilingual',return_value='native transcript') as local,patch.object(speech,'recognize_google_web') as cloud:
                value=speech.recognize_with_fallback(wav_data(varying=True),lang)
            self.assertEqual(value['provider'],'omnilingual');local.assert_called_once();cloud.assert_not_called()
    def test_google_false_language_candidates_not_enabled(self):
        for lang in ('ckb-IQ','ku-TR','sd-PK'):
            self.assertNotIn(lang,speech.GOOGLE_STT_LOCALES)

    def test_unusable_whisper_results_are_not_automatic_reserves(self):
        for lang in ('am-ET','so-SO','sd-PK','bn-BD','pa-IN'):
            self.assertNotIn('offline',speech.recognition_routes(lang))
    def test_tigrinya_and_dari_have_local_reserve(self):
        for lang in ('ti-ET','fa-AF'):
            with self.subTest(lang=lang),patch.object(speech,'recognize_google_web',side_effect=speech.SpeechError('offline')),patch.object(speech,'recognize_omnilingual',return_value='native transcript'):
                self.assertEqual(speech.recognize_with_fallback(wav_data(varying=True),lang)['provider'],'omnilingual')
    def test_explicit_local_modes_never_include_online_routes(self):
        for mode in ('offline','basic'):
            for lang in ('fa-AF','ti-ET','om-ET','ckb-IQ','ku-TR','sd-PK','en-US'):
                with self.subTest(mode=mode,lang=lang):
                    plan=speech.voice_route_plan(lang,{'voice_provider':mode})
                    self.assertTrue(plan['local_only'])
                    self.assertTrue(all(p.startswith('offline_') or p=='windows' for p in plan['providers']))
    def test_dari_approximation_never_claims_native_voice(self):
        prepared={'audio':wav_data(),'provider':'offline_piper','locale':'fa-IR'}
        with patch('offline_voice.prepare',return_value=prepared):
            speech.clear_voice_cache()
            result=speech._prepare_voice('offline_persian_approx','text','fa-AF',{},threading.Event(),5)
        self.assertTrue(result['approximate']);self.assertTrue(result['warnings'])
        self.assertEqual(result['provider'],'offline_persian_approx')
    def test_dari_prefers_female_edge_with_local_reserve(self):
        with patch.object(speech,'offline_voice_available',return_value=True):
            self.assertEqual(speech.voice_route_plan('fa-AF')['providers'][:2],['edge_persian_approx','offline_persian_approx'])
            self.assertEqual(speech.voice_route_plan('fa-AF',{'voice_provider':'edge_free'})['providers'][0],'edge_persian_approx')
    def test_unverified_cross_language_basic_voices_are_deferred(self):
        for locale in ('ti-ET','ckb-IQ'):
            self.assertNotIn(locale,reserve.BASIC)
            self.assertNotIn('offline_basic',speech.voice_route_plan(locale)['providers'])
    def test_failed_cloud_can_use_complete_basic_passage_once(self):
        seen=[]
        def prepare(provider,text,lang,*args):
            seen.append((provider,text))
            if provider!='offline_basic':raise speech.SpeechError('unavailable')
            return {'audio':wav_data(),'provider':provider,'locale':lang,'warnings':['Robotic fallback']}
        with patch.object(speech,'voice_route_plan',return_value={'providers':['edge_free','google_web','windows','offline_basic'],'selected_provider':'auto'}),patch.object(speech,'_prepare_voice',side_effect=prepare),patch.object(speech,'_play_wav_audio',return_value=True) as play:
            value=speech.speak_free('Whole passage. Do not pay 50.','en-US',{},threading.Event())
        self.assertEqual(value['provider'],'offline_basic');play.assert_called_once()
        self.assertTrue(all(text=='Whole passage. Do not pay 50.' for _,text in seen))

    def test_local_failure_gives_online_reserve_its_turn_before_robotic_voice(self):
        seen=[]
        def prepare(provider,*args):
            seen.append(provider)
            if provider=='offline_persian_approx':raise speech.SpeechError('Unavailable model')
            if provider=='edge_persian_approx':
                threading.Event().wait(.08)
                return {'audio':wav_data(),'provider':provider,'locale':'fa-AF'}
            raise AssertionError('Lower quality reserve started ahead of the working online reserve')
        plan={'providers':['offline_persian_approx','edge_persian_approx','windows','offline_basic'],'selected_provider':'auto'}
        with patch.object(speech,'voice_route_plan',return_value=plan),patch.object(speech,'_prepare_voice',side_effect=prepare),patch.object(speech,'_play_wav_audio',return_value=True):
            value=speech.speak_free('Complete passage','fa-AF',{},threading.Event())
        self.assertEqual(value['provider'],'edge_persian_approx')
        self.assertEqual(seen,['offline_persian_approx','edge_persian_approx'])

    def test_voice_feedback_precedes_playback_and_cancel_is_respected(self):
        stop=threading.Event();feedback=[]
        def ready(value):feedback.append(value);stop.set()
        with patch.object(speech,'voice_route_plan',return_value={'providers':['offline_basic'],'selected_provider':'auto'}),patch.object(speech,'_prepare_voice',return_value={'audio':wav_data(),'provider':'offline_basic','warnings':['Robotic fallback']}),patch.object(speech,'_play_wav_audio') as play,self.assertRaisesRegex(speech.SpeechError,'cancelled'):
            speech.speak_free('text','en-US',{'_voice_ready':ready},stop)
        self.assertEqual(feedback[0]['warnings'],['Robotic fallback']);play.assert_not_called()

class NumberTests(unittest.TestCase):
    def test_leading_zeros_and_decimal_digits_preserved(self):
        self.assertEqual(spell_numbers('001.25','ckb').strip(),'سفر سفر یەک خاڵ دوو پێنج')
        self.assertEqual(spell_numbers('۰۰۱٫۲۵','ckb').strip(),'سفر سفر یەک خاڵ دوو پێنج')
    def test_negative_and_percent_preserved(self):
        self.assertEqual(spell_numbers('−2%','tir').strip(),'ኣሉታ ክልተ ሚእታዊት')
    def test_date_order_never_inferred(self):
        self.assertEqual(spell_numbers('09:30','ckb').strip(),'سفر نۆ دوو خاڵ سێ سفر')
        self.assertIn('سلەش',spell_numbers('01/02/2026','ckb'))
        self.assertEqual(spell_numbers('09፡30','tir'),spell_numbers('09:30','tir'))
    def test_unknown_symbols_remain_for_strict_guard(self):
        self.assertIn('€',spell_numbers('€2','tir'))
        self.assertIn('≤',spell_numbers('≤2','ckb'))
    def test_unknown_language_is_unchanged(self):
        self.assertEqual(spell_numbers('001.25','unknown'),'001.25')

    def test_somali_plain_integers_only_never_lose_numeric_punctuation(self):
        self.assertEqual(spell_numbers('00123','som').strip(),'eber eber kow laba saddex')
        for text in ('12.5','09:30','-2','12%','1,234','01/02/2026'):
            self.assertEqual(spell_numbers(text,'som'),text)

    def test_null_never_truncates_native_voice(self):
        with self.assertRaises(speech.SpeechError):speech._voice_chunks('two\0not three')

    def test_passage_specific_failure_does_not_demote_next_neural_turn(self):
        session=speech.VoiceSession()
        session.failed('offline_neural','om-ET',speech.SpeechError('Unsupported number'))
        self.assertEqual(session.order(['offline_neural','offline_basic'],'om-ET'),['offline_neural','offline_basic'])

if __name__=='__main__':unittest.main()
