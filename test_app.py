"""Portable runtime checks. Synthetic data only; no microphone or paid service calls."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

import settings
import speech

class ServiceIntegrationTests(unittest.TestCase):
    def test_data_path_file_is_preserved_and_explained(self):
        from app import ensure_data
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / 'existing-file'
            selected.write_bytes(b'preserve this file')
            with self.assertRaisesRegex(RuntimeError, 'writable folder'):
                ensure_data(selected)
            self.assertEqual(selected.read_bytes(), b'preserve this file')

    def test_saved_snapshot_preserves_review_metadata_and_languages(self):
        from app import Service
        with tempfile.TemporaryDirectory() as directory:
            service = Service(directory)
            conversation = {'id': 'synthetic-conversation', 'title': 'Synthetic test', 'source1': 'en', 'source2': 'ar',
                'drafts': {'1':'Next question 38.5 at 14:30','2':''}, 'turns':[
                    {'id':'synthetic-turn','speaker':'1','source_lang':'en','target_lang':'ar',
                     'raw_source':'Do not pay £50.', 'reviewed_source':'Do not pay £50.',
                     'translated_text':'Synthetic only', 'provider':'fixture','status':'complete',
                     'warnings':['Review negation'], 'review_text':'Alternative fixture',
                     'trace':[{'provider':'fixture','status':'complete'}]}]}
            saved = service.save_conversation(conversation)
            self.assertEqual(saved['turns'][0]['seq'],1)
            loaded = service.load_conversation(saved['id'])
            self.assertEqual(loaded['source2'],'ar')
            self.assertEqual(loaded['turns'][0]['review_text'],'Alternative fixture')
            self.assertEqual(loaded['drafts']['1'],'Next question 38.5 at 14:30')
            self.assertEqual(loaded['turns'][0]['status'],'complete')
            service.shutdown()
            self.assertTrue((Path(directory)/'backups/latest.sqlite3').exists())

    def test_export_uses_visible_translation_revision(self):
        from app import Service
        with tempfile.TemporaryDirectory() as directory:
            service = Service(directory)
            conversation = service.save_conversation({'id':'export-fixture','title':'Synthetic', 'turns':[
                {'id':'turn','speaker':'1','source_lang':'en','target_lang':'fr','raw_source':'Original',
                 'translated_text':'Before','provider':'fixture'}]})
            conversation['turns'][0]['translated_text'] = 'After'
            destination = Path(directory)/'export.txt'
            service.export_conversation(conversation,destination,'txt')
            self.assertIn('After',destination.read_text(encoding='utf-8'))
            self.assertNotIn('Before',destination.read_text(encoding='utf-8'))
            service.shutdown()

    def test_export_captured_snapshot_survives_newer_autosave(self):
        from app import Service
        with tempfile.TemporaryDirectory() as directory:
            service = Service(directory)
            visible = service.save_conversation({'id':'export-race','title':'Synthetic', 'turns':[
                {'id':'turn','speaker':'1','source_lang':'en','target_lang':'fr','raw_source':'Original',
                 'translated_text':'Captured visible version','provider':'fixture'}]})
            newer = copy.deepcopy(visible)
            newer['turns'][0]['translated_text'] = 'Newer version'
            service.save_conversation(newer)
            destination = Path(directory)/'snapshot.txt'
            service.export_conversation(visible,destination,'txt')
            self.assertIn('Captured visible version',destination.read_text(encoding='utf-8'))
            self.assertNotIn('Newer version',destination.read_text(encoding='utf-8'))
            self.assertEqual(service.load_conversation(visible['id'])['turns'][0]['translated_text'],'Newer version')
            service.shutdown()

    def test_export_refuses_overwriting_settings(self):
        from app import Service
        with tempfile.TemporaryDirectory() as directory:
            service = Service(directory)
            with self.assertRaises(ValueError):
                service.export_conversation({'id':'synthetic','turns':[]},Path(directory)/'settings.json','json')
            service.shutdown()

    def test_no_credentials_uses_free_translation_and_same_language_without_network(self):
        from app import Service
        with tempfile.TemporaryDirectory() as directory:
            service = Service(directory)
            def response(provider, *args, **kwargs):
                return [[['Bonjour', 'Hello']]] if provider == 'google_web' else [{'translations': [{'text': 'Hello', 'to': 'en'}]}]
            with patch('engine.HTTPTransport.request_json', side_effect=response) as transport:
                result = service.translate('Hello','en','fr',reinforce=False)
                self.assertEqual(result['text'], 'Bonjour')
                self.assertEqual(result['provider'], 'google_web')
                self.assertEqual(transport.call_args_list[0].args[0], 'google_web')
                self.assertEqual(result['backtranslation'], 'Hello')
                self.assertEqual(result['backtranslation_provider'], 'bing_web')
                self.assertEqual(transport.call_count, 2)
                transport.reset_mock()
                same = service.translate('Preserve this exactly.','en','en')
                self.assertEqual(same['text'], 'Preserve this exactly.')
                transport.assert_not_called()
            service.shutdown()

    def test_backup_refuses_active_settings_history_and_sidecars(self):
        from app import Service
        with tempfile.TemporaryDirectory() as directory:
            service = Service(directory)
            service.save_settings({'theme': 'light'})
            settings_path = Path(directory) / 'settings.json'
            before = settings_path.read_bytes()
            for path in (settings_path, service.store.path, Path(str(service.store.path) + '-journal'),
                         Path(str(service.store.path) + '-wal'), Path(str(service.store.path) + '-shm'),
                         Path(directory) / '.instance.lock'):
                with self.subTest(path=path.name), self.assertRaises(ValueError):
                    service.backup_history(path)
            self.assertEqual(settings_path.read_bytes(), before)
            self.assertEqual(settings.Settings(settings_path).get()['theme'], 'light')
            backup = Path(directory) / 'history-backup.sqlite3'
            self.assertTrue(service.backup_history(backup)['verified'])
            self.assertTrue(backup.exists())
            service.shutdown()

class SettingsTests(unittest.TestCase):
    def test_atomic_settings_unicode_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            store = settings.Settings(path)
            store.save({'source2': 'ar', 'theme': 'light'})
            self.assertEqual(settings.Settings(path).get()['source2'], 'ar')
            self.assertFalse(path.with_name('settings.json.tmp').exists())

    def test_secrets_are_protected_and_reopened(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            store = settings.Settings(path)
            key = 'synthetic-secret-key-that-is-not-real'
            store.save({'providers': {'azure': {'key': key, 'region': 'uksouth'}}, 'speech_key': key + '-speech'})
            raw = path.read_text(encoding='utf-8')
            self.assertNotIn(key, raw)
            reopened = settings.Settings(path).get()
            self.assertEqual(reopened['providers']['azure']['key'], key)
            self.assertEqual(reopened['speech_key'], key + '-speech')

    def test_unreadable_credentials_do_not_erase_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            settings.atomic_json(path, {'version': 1, 'settings': {'theme': 'light'}, 'credentials': 'bad'})
            store = settings.Settings(path)
            self.assertEqual(store.get()['theme'], 'light')
            self.assertEqual(store.get()['speech_key'], '')
            self.assertTrue(store.notice)

    def test_failed_write_rolls_back_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            store = settings.Settings(Path(directory) / 'settings.json')
            before = store.get()
            with patch('settings.atomic_json', side_effect=OSError('synthetic disk failure')):
                with self.assertRaises(OSError):
                    store.save({'theme': 'light'})
            self.assertEqual(store.get(), before)

    def test_malformed_json_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text('{broken', encoding='utf-8')
            store = settings.Settings(path)
            self.assertTrue(store.notice)
            self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_invalid_types_reset_to_valid_defaults(self):
        for invalid in ({'providers': 'oops'}, {'reinforce': 'false'}, {'theme': 'unknown'}):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'settings.json'
                settings.atomic_json(path, {'version': 1, 'settings': invalid})
                store = settings.Settings(path)
                self.assertIsInstance(store.get()['providers'], dict)
                self.assertTrue(store.get()['reinforce'])
                self.assertEqual(store.get()['theme'], 'dark')
                self.assertTrue(store.notice)

class SpeechTests(unittest.TestCase):
    def dictation_audio(self):
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\x64\0\x9c\xff' * 8000)
        return stream.getvalue()

    def test_no_substitute_language_voice(self):
        voices = [{'id': 'tr', 'name': 'Turkish', 'locales': ['tr-tr']},
                  {'id': 'ptbr', 'name': 'Brazil', 'locales': ['pt-br']}]
        self.assertIsNone(speech.matching_sapi_voice('ku-TR', voices))
        self.assertIsNone(speech.matching_sapi_voice('pt-PT', voices))
        self.assertIsNone(speech.matching_sapi_voice('om-ET', voices))
        self.assertEqual(speech.matching_sapi_voice('tr-TR', voices)['id'], 'tr')

    def test_invalid_recording_fails_before_transmission(self):
        with patch('speech.request') as request:
            with self.assertRaises(speech.SpeechError):
                speech.recognize_wav(b'not transmitted', 'en-US', {})
            request.assert_not_called()

    def test_azure_recognition_parsing(self):
        reply = {'RecognitionStatus': 'Success', 'NBest': [{'Display': 'Do not pay £50 at 14:30.'}]}
        with patch('speech.request', return_value=json.dumps(reply).encode('utf-8')):
            text = speech.recognize_wav(self.dictation_audio(), 'en-US', {'speech_provider': 'azure', 'speech_key': 'fake', 'speech_region': 'uksouth'})
        self.assertEqual(text, 'Do not pay £50 at 14:30.')

    def test_silence_does_not_create_transcript(self):
        with patch('speech.request', return_value=b'{"RecognitionStatus":"NoMatch"}'):
            with self.assertRaises(speech.SpeechError):
                speech.recognize_wav(self.dictation_audio(), 'en-US', {'speech_provider': 'azure', 'speech_key': 'fake', 'speech_region': 'uksouth'})

    def test_invalid_region_never_receives_key(self):
        with patch('speech.request') as request:
            with self.assertRaises(speech.SpeechError):
                speech.recognize_wav(self.dictation_audio(), 'en-US', {'speech_provider': 'azure', 'speech_key': 'fake', 'speech_region': 'example.org/path'})
            request.assert_not_called()

    def test_invalid_audio_is_not_played(self):
        config = {'speech_provider': 'azure', 'speech_key': 'fake', 'speech_region': 'uksouth', 'speech_provider': 'azure'}
        with patch('speech.request', return_value=b'not audio'), patch('speech.winsound.PlaySound') as play:
            with self.assertRaises(speech.SpeechError):
                speech.speak_azure('Test', 'en-US', config, threading.Event())
            play.assert_not_called()

    def test_valid_audio_uses_file_and_is_removed(self):
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0\0' * 32)
        with tempfile.TemporaryDirectory() as directory:
            config = {'speech_provider': 'azure', 'speech_key': 'fake', 'speech_region': 'uksouth', 'speech_provider': 'azure', '_audio_dir': directory}
            with patch('speech.request', return_value=audio.getvalue()), patch('speech.winsound.PlaySound') as play:
                speech.speak_azure('Test', 'en-US', config, threading.Event())
            filename = play.call_args_list[0].args[0]
            self.assertFalse(Path(filename).exists())
            self.assertEqual(play.call_args_list[-1].args, (None, 0))

    def test_cancelled_request_returns_promptly(self):
        event = threading.Event(); event.set()
        with patch('speech.urllib.request.urlopen', side_effect=OSError('synthetic offline')) as transport:
            with self.assertRaises(speech.SpeechError):
                speech.request('https://example.invalid', b'', {}, event, timeout=.2)
            transport.assert_not_called()

    def test_unsupported_dialect_fails_before_transmission(self):
        with patch('speech.request') as transport:
            with self.assertRaises(speech.SpeechError):
                speech.recognize_wav(self.dictation_audio(), 'fa-AF', {'speech_provider': 'azure', 'speech_key': 'fake', 'speech_region': 'uksouth'})
            transport.assert_not_called()

    def test_capture_preserves_unmasked_source(self):
        with patch('speech.request', return_value=b'{"RecognitionStatus":"Success","DisplayText":"Test"}') as transport:
            speech.recognize_wav(self.dictation_audio(), 'en-US', {'speech_provider': 'azure', 'speech_key': 'fake', 'speech_region': 'uksouth'})
        self.assertIn('profanity=raw', transport.call_args.args[0])

if __name__ == '__main__':
    unittest.main()
