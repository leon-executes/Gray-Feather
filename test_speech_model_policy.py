"""Measured model/routing policy regression tests; no network, model or microphone."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import speech
from test_free_speech import wav_data


class ModelPolicyTests(unittest.TestCase):
    def setUp(self): self.audio = wav_data(80000, varying=True)

    def test_auto_english_uses_local_without_online_upload(self):
        for mode in ('auto', 'free'):
            with self.subTest(mode=mode), patch.object(speech, 'recognize_offline', return_value='Bring two copies, not three.') as local, patch.object(speech, 'recognize_google_web') as online:
                result = speech.recognize_with_fallback(self.audio, 'en-US', {'speech_provider': mode})
            local.assert_called_once(); online.assert_not_called()
            self.assertEqual(result['provider'], 'offline')
            self.assertIn('small-q5_1', ' '.join(result['trace']))

    def test_failed_english_local_uses_online_once(self):
        with patch.object(speech, 'recognize_offline', side_effect=speech.SpeechError('Native failure')) as local, patch.object(speech, 'recognize_google_web', return_value='Bring two copies, not three.') as online:
            result = speech.recognize_with_fallback(self.audio, 'en-US')
        local.assert_called_once(); online.assert_called_once()
        self.assertEqual(result['provider'], 'google_web')
        self.assertIn('offline route: Native failure', result['trace'])
        self.assertTrue(any('free online' in warning for warning in result['warnings']))

    def test_english_two_failures_do_not_retry_local(self):
        with patch.object(speech, 'recognize_offline', side_effect=speech.SpeechError('Native failure')) as local, patch.object(speech, 'recognize_google_web', side_effect=speech.SpeechError('Online failure')) as online, self.assertRaisesRegex(speech.SpeechError, 'Native failure.*Online failure'):
            speech.recognize_with_fallback(self.audio, 'en-US')
        local.assert_called_once(); online.assert_called_once()

    def test_cancelled_english_local_never_uploads_audio(self):
        cancel = threading.Event()
        def stopped(*args): cancel.set(); raise speech.SpeechError('Stopped')
        with patch.object(speech, 'recognize_offline', side_effect=stopped), patch.object(speech, 'recognize_google_web') as online, self.assertRaises(speech.SpeechError):
            speech.recognize_with_fallback(self.audio, 'en-US', cancel=cancel)
        online.assert_not_called()

    def test_cancellation_after_completed_native_response_discards_text(self):
        cancel = threading.Event()
        def stopped(*args): cancel.set(); return 'Do not pay 50'
        with patch.object(speech, 'recognize_offline', side_effect=stopped), patch.object(speech, 'recognize_google_web') as online, self.assertRaisesRegex(speech.SpeechError, 'cancelled'):
            speech.recognize_with_fallback(self.audio, 'en-US', cancel=cancel)
        online.assert_not_called()

    def test_other_supported_languages_use_online_first(self):
        for lang in ('ar-SA', 'tr-TR', 'zh-CN'):
            with self.subTest(lang=lang), patch.object(speech, 'recognize_google_web', return_value='fixture') as online, patch.object(speech, 'recognize_offline') as local:
                self.assertEqual(speech.recognize_with_fallback(self.audio, lang)['provider'], 'google_web')
            online.assert_called_once(); local.assert_not_called()

    def test_french_local_first_preserves_quantity_and_can_fall_back(self):
        with patch.object(speech, 'recognize_offline', return_value='Apportez deux copies, pas trois.') as local, patch.object(speech, 'recognize_google_web') as online:
            result = speech.recognize_with_fallback(self.audio, 'fr-FR')
        local.assert_called_once(); online.assert_not_called()
        self.assertEqual(result['provider'], 'offline')
        with patch.object(speech, 'recognize_offline', side_effect=speech.SpeechError('Native failure')) as local, patch.object(speech, 'recognize_google_web', return_value='Apportez deux copies, pas trois.') as online:
            result = speech.recognize_with_fallback(self.audio, 'fr-FR')
        local.assert_called_once(); online.assert_called_once()
        self.assertEqual(result['provider'], 'google_web')

    def test_persian_has_online_support_without_poor_offline_fallback(self):
        self.assertTrue(speech.recognition_supported('fa-IR', 'auto'))
        self.assertTrue(speech.recognition_supported('fa-IR', 'google_web'))
        self.assertFalse(speech.recognition_supported('fa-IR', 'offline'))
        with patch.object(speech, 'recognize_google_web', return_value='لطفاً دو نسخه بیاورید.'), patch.object(speech, 'recognize_offline') as local:
            result = speech.recognize_with_fallback(self.audio, 'fa-IR')
        local.assert_not_called(); self.assertEqual(result['provider'], 'google_web')
        self.assertIn('sidelined', ' '.join(result['trace']))
        with patch.object(speech, 'recognize_google_web', side_effect=speech.SpeechError('Online failure')), patch.object(speech, 'recognize_offline') as local, self.assertRaises(speech.SpeechError):
            speech.recognize_with_fallback(self.audio, 'fa-IR')
        local.assert_not_called()

    def test_explicit_persian_offline_refused_before_native_process(self):
        with patch.object(speech.subprocess, 'Popen') as process, self.assertRaisesRegex(speech.SpeechError, 'Persian.*sidelined'):
            speech.recognize_offline(self.audio, 'fa-IR')
        process.assert_not_called()

    def test_auto_entry_points_share_the_same_policy(self):
        with patch.object(speech, 'recognize_with_fallback', return_value={'text': 'two copies'}) as policy:
            self.assertEqual(speech.recognize_wav(self.audio, 'en-US', {'speech_provider': 'auto'}), 'two copies')
            self.assertEqual(speech.recognize_wav(self.audio, 'en-US', {'speech_provider': 'free'}), 'two copies')
        self.assertEqual(policy.call_count, 2)

    def test_only_pinned_small_weight_file_counts_as_available(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder); (root/'whisper-cli.exe').write_bytes(b'fixture')
            (root/'ggml-base.bin').write_bytes(b'old fixture')
            self.assertFalse(speech.offline_available({'_speech_resources': folder}))
            (root/speech.OFFLINE_MODEL).write_bytes(b'new fixture')
            self.assertTrue(speech.offline_available({'_speech_resources': folder}))

    def test_native_launch_failure_is_recoverable_online_and_cleans_audio(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            (root/'whisper-cli.exe').write_bytes(b'fixture'); (root/speech.OFFLINE_MODEL).write_bytes(b'fixture')
            with patch.object(speech.subprocess, 'Popen', side_effect=OSError('invalid executable')), patch.object(speech, 'recognize_google_web', return_value='two copies') as online:
                result = speech.recognize_with_fallback(self.audio, 'en-US', {'_speech_resources': folder, '_audio_dir': folder})
            online.assert_called_once(); self.assertEqual(result['provider'], 'google_web')
            self.assertEqual(sorted(p.name for p in root.iterdir()), sorted((speech.OFFLINE_MODEL, 'whisper-cli.exe')))

    def test_recording_duration_has_loading_floor_and_bounded_budget(self):
        self.assertEqual(speech.offline_timeout(.1), 20)
        self.assertEqual(speech.offline_timeout(5), 20)
        self.assertEqual(speech.offline_timeout(30), 55)
        self.assertEqual(speech.offline_timeout(50), 85)
        for invalid in (0, -1, 51, True, '5', float('nan'), float('inf')):
            with self.subTest(invalid=invalid), self.assertRaises(speech.SpeechError): speech.offline_timeout(invalid)

    def test_stuck_short_native_process_killed_on_twenty_second_budget(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            (root/'whisper-cli.exe').write_bytes(b'fixture'); (root/speech.OFFLINE_MODEL).write_bytes(b'fixture')
            class Process:
                returncode = None
                killed = False
                def poll(self): return self.returncode
                def kill(self): self.killed = True; self.returncode = -9
                def wait(self, timeout): return self.returncode
            process = Process()
            with patch.object(speech.subprocess, 'Popen', return_value=process), patch.object(speech.time, 'monotonic', side_effect=(100, 121)), patch.object(speech.time, 'sleep'), self.assertRaisesRegex(speech.SpeechError, 'time limit'):
                speech.recognize_offline(self.audio, 'en-US', {'_speech_resources': folder, '_audio_dir': folder})
            self.assertTrue(process.killed)
            self.assertEqual(sorted(p.name for p in root.iterdir()), sorted((speech.OFFLINE_MODEL, 'whisper-cli.exe')))

    def test_direct_offline_trace_names_selected_model_and_chinese_caveat(self):
        with patch.object(speech, 'recognize_offline', return_value='请带两份副本。'):
            result = speech.recognize_with_fallback(self.audio, 'zh-CN', {'speech_provider': 'offline'})
        self.assertIn('small-q5_1', ' '.join(result['trace']))
        self.assertTrue(any('Chinese' in warning for warning in result['warnings']))

if __name__ == '__main__': unittest.main()
