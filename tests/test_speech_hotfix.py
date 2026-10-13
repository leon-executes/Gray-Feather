"""Regression checks for usable routes, reversible masking and playback completion."""
import threading,time,tempfile,unittest
from unittest.mock import patch, Mock
import types
from pathlib import Path
import speech
from safe_speech import mask
from tests.test_voice_reserve import wav_data

class SafeSpeechTests(unittest.TestCase):
    def test_fully_filtered_passage_does_not_fail_or_send_punctuation_to_tts(self):
        with patch.object(speech,'_prepare_voice') as prepare:
            result=speech.speak_free('fuck shit','en-US',{},threading.Event())
        self.assertTrue(result['filtered']);self.assertTrue(result['complete']);prepare.assert_not_called()
    def test_mask_and_off_are_reversible_without_touching_medical_terms(self):
        source='Do not take 2 tablets. Sexual assault, abuse, rape and breast cancer. Fuck this shit.'
        safe=mask(source)
        self.assertIn('2 tablets. Sexual assault, abuse, rape and breast cancer.',safe)
        self.assertNotIn('Fuck',safe);self.assertNotIn('shit',safe)
        self.assertEqual(mask(source,False),source)
        self.assertEqual(mask('Scunthorpe and a class assignment.'),'Scunthorpe and a class assignment.')
    def test_multilingual_and_obfuscated_terms(self):
        for text in ('f.u.c.k','کسکش','merde','siktir'):
            self.assertIn('[filtered]',mask(text),text)
        for text in ('got','mavi','کون','کیر','کُس', 'sexual assault'):
            self.assertEqual(mask(text),text)
    def test_filter_runs_before_any_provider_or_cache(self):
        seen=[]
        def prepare(provider,text,*args):
            seen.append(text);return {'provider':provider,'audio':wav_data()}
        with patch.object(speech,'voice_route_plan',return_value={'providers':['offline_basic'],'selected_provider':'auto'}),patch.object(speech,'_prepare_voice',side_effect=prepare),patch.object(speech,'_play_wav_audio',return_value=True):
            speech.speak_free('This is shit. Keep 12.', 'en-US',{},threading.Event())
            self.assertNotIn('shit',seen[0]);self.assertIn('12',seen[0])
            speech.speak_free('This is shit.', 'en-US',{'safe_speech':False},threading.Event())
            self.assertIn('shit',seen[-1])

class PlaybackTests(unittest.TestCase):
    def device(self, delay, started=None):
        state={};timer=[]
        def write(handle,header,size):
            state['header']=header._obj
            if started:started.set()
            t=threading.Timer(delay,lambda:setattr(header._obj,'flags',1));t.daemon=True;t.start();timer.append(t)
            return 0
        def reset(handle):
            for t in timer:t.cancel()
            if 'header' in state:state['header'].flags=1
            return 0
        return types.SimpleNamespace(waveOutOpen=Mock(return_value=0),waveOutPrepareHeader=Mock(return_value=0),waveOutWrite=Mock(side_effect=write),waveOutReset=Mock(side_effect=reset),waveOutUnprepareHeader=Mock(return_value=0),waveOutClose=Mock(return_value=0))
    def test_slow_device_is_not_cut_at_file_duration(self):
        device=self.device(.4);start=time.monotonic()
        with tempfile.TemporaryDirectory() as folder,patch.object(speech,'_waveout_device',return_value=device):
            self.assertTrue(speech._play_wav_audio(wav_data(),threading.Event(),folder))
            self.assertEqual(list(Path(folder).iterdir()),[])
        self.assertGreaterEqual(time.monotonic()-start,.4)
        device.waveOutClose.assert_called_once();device.waveOutUnprepareHeader.assert_called_once()
    def test_cancel_waits_for_windows_to_release_audio(self):
        stop=threading.Event();began=threading.Event();device=self.device(2,began)
        timer=threading.Thread(target=lambda:(began.wait(2),stop.set()),daemon=True);timer.start()
        start=time.monotonic()
        with tempfile.TemporaryDirectory() as folder,patch.object(speech,'_waveout_device',return_value=device):
            self.assertFalse(speech._play_wav_audio(wav_data(),stop,folder))
            self.assertEqual(list(Path(folder).iterdir()),[])
        self.assertLess(time.monotonic()-start,.5)
        device.waveOutReset.assert_called_once();device.waveOutClose.assert_called_once()
        self.assertFalse(speech._VOICE_PLAYBACK_LOCK.locked())
    def test_failed_device_write_closes_and_releases_buffer(self):
        device=self.device(0);device.waveOutWrite=Mock(return_value=5)
        with patch.object(speech,'_waveout_device',return_value=device),self.assertRaises(speech.SpeechError):
            speech._play_wav_audio(wav_data(),threading.Event())
        device.waveOutClose.assert_called_once();device.waveOutUnprepareHeader.assert_called_once()

class RouteTests(unittest.TestCase):
    def test_good_local_voices_stay_first_and_webapp_reserves_precede_robotic(self):
        with patch.object(speech,'offline_voice_available',return_value=False),patch('offline_reserve.available',return_value=True):
            for lang in ('ti-ET','ckb-IQ','om-ET'):
                routes=speech.voice_route_plan(lang)['providers']
                self.assertEqual(routes[0],'offline_neural')
                self.assertLess(next(i for i,p in enumerate(routes) if p.startswith('reference:')),routes.index('offline_basic'))
            for lang in ('ku-TR','sd-PK'):
                self.assertTrue(speech.voice_route_plan(lang)['providers'][0].startswith('reference:'))
    def test_explicit_local_mode_never_uses_webapp_or_google_substitute(self):
        for lang in speech.REFERENCE_VOICES:
            for mode in ('offline','basic'):
                self.assertFalse(any(p.startswith('reference') for p in speech.voice_route_plan(lang,{'voice_provider':mode})['providers']))
    def test_substitutes_report_actual_voice_and_requested_language(self):
        with patch.object(speech,'_prepare_voice_direct',return_value={'audio':wav_data(),'voice':'Turkish voice','locale':'tr-TR'}),patch.object(speech,'_speech_cloud_worker',return_value={'audio':wav_data(),'voice':'Turkish voice','locale':'tr-TR'}):
            result=speech._prepare_voice('reference:tr-TR','Spas','ku-TR',{},threading.Event(),3)
        self.assertTrue(result['approximate']);self.assertEqual(result['locale'],'ku-TR');self.assertTrue(result['warnings'])

class DisplayTests(unittest.TestCase):
    def test_joined_controls_and_safe_toggle_restore_original_translation(self):
        import ui
        from tests import test_ui
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        service=test_ui.FakeService();window=ui.MainWindow(service)
        try:
            panel=window.panels['1']
            turn={'translated_text':'This is shit. Take 2 tablets.','target_lang':'fr'}
            panel.show_received(turn)
            self.assertNotIn('shit',panel.received.toPlainText())
            self.assertIn('shit',turn['translated_text'])
            window._toggle_safe_speech(False);panel.show_received(turn)
            self.assertIn('shit',panel.received.toPlainText())
            self.assertEqual(window.voice_button.text(),'Enabled')
            self.assertEqual(window.safe_on.text(),'On')
            self.assertFalse(service.settings()['safe_speech'])
        finally:window.close();app.processEvents()

if __name__=='__main__':unittest.main()
