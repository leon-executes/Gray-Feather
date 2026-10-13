"""Gray Feather Desktop: native, portable, recoverable two-person translation.

Public entry point. The engine, UI, settings and speech boundaries remain separately
inspectable so transport, persistence and native failures cannot silently mutate turns.
"""
from __future__ import annotations
import argparse
import copy
import ctypes
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
import traceback
import unittest
import uuid

VERSION = '1.4.1'

def portable_root():
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

def ensure_data(path):
    probe = path / ('.write-check-' + uuid.uuid4().hex)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b'')
        probe.unlink()
    except OSError as error:
        raise RuntimeError('The data folder could not be opened for writing. Choose a writable folder or use --data-dir.') from error
    return path

class Service:
    def __init__(self, data_dir):
        from settings import Settings
        import engine
        self.data_dir = ensure_data(Path(data_dir))
        self._settings = Settings(self.data_dir / 'settings.json')
        self.store = engine.Store(self.data_dir / 'conversations.sqlite3')
        self._save_lock = threading.RLock()
        self._audio_stop = threading.Event()
        self._shutting_down = threading.Event()
        self._voice_cache = []
        self._voice_checked = False
        self._voice_session = None
        self.languages = []
        for item in engine.LANGUAGES:
            record = dataclasses.asdict(item) if dataclasses.is_dataclass(item) else dict(item)
            self.languages.append({'code': record['code'], 'name': record['name'], 'native': record.get('native', record['name']), 'rtl': record.get('rtl', False), 'bcp47': record.get('bcp47', record.get('locale', record['code']))})
        self._translator = None
        self._preview_translator = None
        self._reinforced_translator = None
        self._dirty_history = False

    def settings(self):
        result = self._settings.get()
        result['notice'] = self._settings.notice
        return result

    def save_settings(self, values):
        previous = self.settings()
        result = self._settings.save(values)
        if any(previous.get(key) != result.get(key) for key in ('providers', 'free_fallback', 'provider', 'context')):
            self._translator = None
            self._preview_translator = None
            self._reinforced_translator = None
        return result

    def reset_settings(self):
        from settings import DEFAULTS
        current = self.settings()
        values = copy.deepcopy(DEFAULTS)
        for key in ('providers', 'speech_key', 'speech_region', 'context'):
            values[key] = copy.deepcopy(current[key])
        return self.save_settings(values)

    def _make_translator(self):
        import engine
        if self._translator is not None:
            return self._translator
        settings = self.settings()
        configs = [engine.ProviderConfig(provider=name, timeout=8)
                   for name in ('google_web', 'bing_web', 'mymemory')]
        for provider, values in settings['providers'].items():
            if str(values.get('key', '')).strip():
                endpoint = values.get('endpoint', '').strip()
                if provider == 'deepl' and 'free' in values and not endpoint:
                    endpoint = 'https://api-free.deepl.com/v2/translate' if values['free'] else 'https://api.deepl.com/v2/translate'
                configs.append(engine.ProviderConfig(provider=provider, key=values['key'].strip(), region=values.get('region', '').strip(), endpoint=endpoint, timeout=15, glossary_id=values.get('glossary_id', '').strip()))
        # Free engines are the default path. A paid account is optional and never
        # needed to start translating; fallback restarts the whole turn.
        self._translator = engine.Translator(configs, enabled_order=[c.provider for c in configs],
                                            allow_fallback=bool(settings.get('free_fallback', True)))
        return self._translator

    def translate(self, text, source, target, provider='auto', reinforce=None, cancel_event=None, context=''):
        from settings import RETIRED_TRANSLATION_PROVIDERS
        if provider in RETIRED_TRANSLATION_PROVIDERS:
            import engine
            raise engine.TranslationError('settings', 'Offline text translation was removed. Choose an online translation engine.')
        settings = self.settings()
        translator = self._make_translator()
        improved = bool(settings.get('reinforce', True) if reinforce is None else reinforce)
        if improved or provider in ('reinforced', 'index_web'):
            if self._reinforced_translator is None:
                from reinforced_engine import ReinforcedTranslator
                self._reinforced_translator = ReinforcedTranslator(translator, shutdown=self._shutting_down)
            result = self._reinforced_translator.translate(text, source, target, provider=provider,
                cancel=cancel_event, context=context, backtranslate=bool(settings.get('backtranslate', False)), improve=improved or provider == 'reinforced')
        else:
            result = translator.translate(text, source, target, provider=None if provider == 'auto' else provider,
                cancel=cancel_event, context=context, independent_review=False,
                backtranslate=bool(settings.get('backtranslate', False)))
        result = dataclasses.asdict(result) if dataclasses.is_dataclass(result) else dict(result)
        result['checks'] = copy.deepcopy(result.get('warnings', []))
        result['warnings'] = [w.get('message', str(w)) if isinstance(w, dict) else str(w) for w in result.get('warnings', [])]
        return result

    def translate_preview(self, text, source, target, cancel_event=None):
        import engine
        if self._preview_translator is None:
            configs = list(self._make_translator().configs.values())
            self._preview_translator = engine.Translator(configs, enabled_order=[c.provider for c in configs],
                allow_fallback=bool(self.settings().get('free_fallback', True)), cache_size=12, cache_chars=200_000)
        settings = self.settings()
        provider = settings.get('provider', 'auto')
        from settings import RETIRED_TRANSLATION_PROVIDERS
        if provider in RETIRED_TRANSLATION_PROVIDERS:
            raise engine.TranslationError('settings', 'Offline text translation was removed. Choose an online translation engine.')
        if provider == 'index_web':
            from index_engine import IndexTranslator
            value = IndexTranslator().translate(text,source,target,cancel_event=cancel_event,deadline_seconds=6)
            value.update(provisional=True,complete=False)
            return value
        result = self._preview_translator.translate(text, source, target,
            provider=None if provider in ('auto', 'reinforced') else provider, cancel=cancel_event,
            context=settings.get('context', '') if provider == 'deepl' else '',
            independent_review=False, backtranslate=False, deadline_seconds=6.0)
        value = dataclasses.asdict(result)
        value.update(provisional=True, complete=False)
        return value

    def available_opinion_providers(self, source_code, target_code, used_providers=()):
        from index_engine import supports as index_supports
        from settings import RETIRED_TRANSLATION_PROVIDERS
        used = tuple(used_providers)
        web_used = tuple(p for p in used if p not in RETIRED_TRANSLATION_PROVIDERS and p != 'index_web')
        options = list(self._make_translator().available_opinion_providers(source_code, target_code, web_used))
        if source_code != target_code and 'index_web' not in used and index_supports(source_code, target_code):
            options.insert(0, {'provider': 'index_web', 'label': 'Index Translate · free AI',
                'family': 'bilibili_index', 'independent': 'index_local' not in used})
        return tuple(options)

    def add_opinion(self, source, source_code, target_code, used_providers=(), cancel_event=None):
        import engine
        options = self.available_opinion_providers(source_code, target_code, used_providers)
        if not options:
            raise engine.TranslationError('opinion_unavailable', 'No further available engine supports this exact language pair.')
        if options[0]['provider'] == 'index_web':
            from reinforced_engine import ReinforcedTranslator
            if self._reinforced_translator is None:
                self._reinforced_translator = ReinforcedTranslator(self._make_translator(), shutdown=self._shutting_down)
            result = self._reinforced_translator.translate(source, source_code, target_code,
                provider='index_web', cancel=cancel_event, improve=False)
        else:
            from settings import RETIRED_TRANSLATION_PROVIDERS
            web_used = tuple(p for p in used_providers if p not in RETIRED_TRANSLATION_PROVIDERS and p != 'index_web')
            result = self._make_translator().additional_opinion(source, source_code, target_code,
                used_providers=web_used, cancel=cancel_event)
        value = dataclasses.asdict(result)
        value['checks'] = copy.deepcopy(value.get('warnings', []))
        value['warnings'] = [w.get('message', str(w)) if isinstance(w, dict) else str(w) for w in value.get('warnings', [])]
        value.update(complete=True, provisional=False)
        return value

    def list_conversations(self, query=''):
        return self.store.list_conversations(query=query)

    def load_conversation(self, identifier):
        return self._flatten(self.store.get_conversation(identifier))

    @staticmethod
    def _flatten(conversation):
        value = copy.deepcopy(conversation)
        for key in ('source1', 'source2'):
            if key in value.get('metadata', {}):
                value[key] = value['metadata'][key]
        for turn in value['turns']:
            for key, item in turn.get('metadata', {}).items():
                if key not in turn:
                    turn[key] = item
        return value

    def save_conversation(self, conversation):
        with self._save_lock:
            data = copy.deepcopy(conversation)
            data.setdefault('metadata', {}).update({k: data[k] for k in ('source1', 'source2') if k in data})
            for turn in data['turns']:
                turn.setdefault('metadata', {}).update({k: turn[k] for k in ('status', 'error', 'elapsed_ms', 'review_text', 'review_provider', 'backtranslation', 'backtranslation_provider', 'trace', 'checks', 'ui_generation', 'capture_complete', 'opinions', 'extra_opinions', 'dictation') if k in turn})
                if turn.get('revision', 0) == 0:
                    turn.pop('seq', None)
            result = self._flatten(self.store.save_conversation(data))
            self._dirty_history = True
            return result

    def delete_conversation(self, identifier):
        self._dirty_history = True
        return self.store.delete_conversation(identifier)

    def delete_conversations(self, identifiers):
        with self._save_lock:
            count = self.store.delete_conversations(identifiers)
            self._dirty_history = True
            return count

    def shred_history(self):
        with self._save_lock:
            result = self.store.shred_history()
            self._dirty_history = False
            self._translator = self._preview_translator = self._reinforced_translator = None
            # Only the app-managed backup names; never follow links or delete user exports.
            root = self.data_dir.resolve()
            backup_dir = self.data_dir / 'backups'
            paths = [backup_dir / name for name in ('latest.sqlite3', 'previous.sqlite3', 'next.sqlite3')]
            try:
                # A crash during automatic backup can leave its private staging file.
                if backup_dir.resolve() == root / 'backups' and not backup_dir.is_symlink():
                    paths.extend(backup_dir.glob('.next.sqlite3.*.tmp'))
            except OSError:
                result['issues'].append('Could not check interrupted automatic backups. Retry Shred History.')
            for path in paths:
                name = path.name
                try:
                    if not path.exists():
                        continue
                    if path.is_symlink() or path.parent.is_symlink() or path.resolve().parent != root / 'backups':
                        raise OSError('Linked backup location')
                    with path.open('r+b', buffering=0) as stream:
                        remaining = path.stat().st_size
                        zeros = bytes(1024 * 1024)
                        while remaining:
                            written = stream.write(zeros[:min(remaining, len(zeros))])
                            if not written:
                                raise OSError('Backup overwrite failed')
                            remaining -= written
                        os.fsync(stream.fileno())
                        stream.truncate(0)
                        os.fsync(stream.fileno())
                    path.unlink()
                except OSError:
                    result['issues'].append('Could not purge automatic backup ' + name + '. Close any program using it and retry Shred History.')
            return result

    def backup_history(self, path):
        # Include backup publication in the purge lock, not just SQLite copying.
        with self._save_lock:
            destination = self._safe_output_path(path)
            self.store.backup(destination)
        return {'path': str(path), 'verified': True}

    def _safe_output_path(self, path):
        destination = Path(path).resolve()
        protected = [(self.data_dir / 'settings.json').resolve(), self.store.path.resolve(),
                     (self.data_dir / '.instance.lock').resolve()]
        protected.extend(Path(str(self.store.path) + suffix).resolve() for suffix in ('-journal', '-wal', '-shm'))
        if destination in protected:
            raise ValueError('A saved file cannot overwrite application settings or active history.')
        return destination

    def export_conversation(self, conversation, path, format):
        # Export the captured visible snapshot even when typing continues during file writing.
        destination = self._safe_output_path(path)
        if format.lower() == 'docx':
            from docx_export import export_docx
            return export_docx(copy.deepcopy(conversation), destination)
        return self.store.export(conversation['id'], format=format, destination=destination, snapshot=copy.deepcopy(conversation))

    def _locale(self, code):
        item = next((x for x in self.languages if x['code'] == code), None)
        if not item:
            raise ValueError('Choose a supported language.')
        return item['bcp47']

    def capabilities(self, lang):
        import speech
        settings = self.settings()
        locale_code = self._locale(lang)
        # Avoid COM at startup. Native voices are discovered on demand and failure is isolated.
        azure_voice = settings.get('voice_provider') == 'azure' and bool(settings.get('speech_key')) and locale_code in speech.AZURE_VOICES
        native = bool(speech.matching_sapi_voice(locale_code, self._voice_cache, exact=True))
        selected = settings.get('speech_provider', 'auto')
        keyless = selected in ('auto', 'google_web', 'offline', 'omnilingual')
        mic = speech.recognition_supported(locale_code, selected) and (keyless or bool(settings.get('speech_key')))
        if selected == 'offline':
            mic = mic and speech.offline_available(lang=locale_code)
        if selected == 'omnilingual':
            import offline_omni
            mic = mic and offline_omni.available(locale_code, settings)
        free_voice = speech.voice_supported(locale_code, settings)
        if mic and keyless:
            if selected in ('offline', 'omnilingual') or locale_code not in speech.GOOGLE_STT_LOCALES:
                reason = 'Bundled local dictation. Press Record Speech, speak, then Stop.'
            elif selected == 'google_web':
                reason = 'Free online dictation. Press Record Speech, speak, then Stop.'
            elif locale_code in ('en-US', 'fr-FR') or locale_code in speech.OMNI_FIRST:
                reason = 'Bundled local dictation with free online fallback. Press Record Speech, speak, then Stop.'
            elif locale_code == 'fa-IR':
                reason = 'Free online dictation with bundled multilingual fallback.'
            elif len(speech.recognition_routes(locale_code)) == 1:
                reason = 'Free online dictation. No verified automatic offline reserve for this language.'
            else:
                reason = 'Free online dictation with supported local fallback. Press Record Speech, speak, then Stop.'
        elif not mic:
            reason = ('Offline Persian is unavailable after quality checks. Select Automatic for free online dictation.'
                      if selected == 'offline' and locale_code == 'fa-IR' else 'This language has no supported dictation route. Text translation is available.')
        else:
            reason = 'Press Record Speech, speak, then Stop.'
        return {'mic_enabled': mic, 'voice_enabled': azure_voice or native or free_voice,
                'reason': reason,
                'voice_reason': ('Dari uses approximate Persian pronunciation.' if locale_code == 'fa-AF' else 'Dedicated voice where available; basic robotic or explicitly approximate pronunciation is the last reserve.'),
                'native_voice_checked': self._voice_checked}

    def check_native_voices(self):
        import speech
        try:
            self._voice_cache = speech.sapi_voices()
            self._voice_checked = True
            return {'count': len(self._voice_cache), 'voices': [v['name'] for v in self._voice_cache]}
        except Exception as error:
            self._voice_cache = []
            self._voice_checked = True
            raise speech.SpeechError('The Windows voice service is unavailable here. Free online voices remain available.') from error

    def recognize(self, source_lang, cancel_event, preview_callback=None):
        import speech
        settings = self.settings()
        if not speech.recognition_supported(self._locale(source_lang), settings.get('speech_provider')):
            raise speech.SpeechError('The selected dictation route does not support this language. Text translation remains available.')
        settings['_audio_dir'] = str(self.data_dir / 'audio-temp')
        if preview_callback is None:
            audio, metadata = speech.record_wav(cancel_event)
        else:
            audio, metadata = speech.record_with_previews(cancel_event, self._locale(source_lang), settings, preview_callback)
        abort = getattr(cancel_event, 'abort_event', self._shutting_down)
        if abort.is_set() or self._shutting_down.is_set():
            raise speech.SpeechError('Recording cancelled.')
        result = speech.recognize_with_fallback(audio, self._locale(source_lang), settings, abort)
        return {**result, **metadata}

    def speak(self, text, lang, cancel_event, on_prepared=None):
        import speech
        self._audio_stop = cancel_event
        settings = self.settings()
        locale_code = self._locale(lang)
        settings['_audio_dir'] = str(self.data_dir / 'audio-temp')
        if self._voice_session is None:
            self._voice_session = speech.VoiceSession()
        settings['_voice_session'] = self._voice_session
        if on_prepared is not None: settings['_voice_ready'] = on_prepared
        return speech.speak_free(text, locale_code, settings, cancel_event)

    def speak_with_feedback(self, text, lang, cancel_event, callback):
        return self.speak(text, lang, cancel_event, callback)

    def stop_audio(self):
        self._audio_stop.set()
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass

    def shutdown(self):
        self._shutting_down.set()
        self.stop_audio()
        if self._dirty_history:
            try:
                backup_dir = self.data_dir / 'backups'
                backup_dir.mkdir(parents=True, exist_ok=True)
                staged = backup_dir / 'next.sqlite3'
                self.store.backup(staged)
                latest = backup_dir / 'latest.sqlite3'
                if latest.exists():
                    os.replace(latest, backup_dir / 'previous.sqlite3')
                os.replace(staged, latest)
            except Exception:
                try:
                    write_report(self.data_dir / 'backup-status.json', {'successful': False, 'message': 'Automatic history backup could not complete. The active history was preserved.'})
                except Exception:
                    pass
        if hasattr(self.store, 'close'):
            self.store.close()

def diagnose(data_dir):
    import sqlite3
    import PySide6
    from settings import Settings
    settings = Settings(Path(data_dir) / 'settings.json').get()
    return {'application': 'Gray Feather', 'version': VERSION, 'python': platform.python_version(),
            'qt_bindings': PySide6.__version__, 'sqlite': sqlite3.sqlite_version,
            'windows': platform.platform(), 'architecture': platform.machine(),
            'frozen': bool(getattr(sys, 'frozen', False)), 'data_directory': str(data_dir),
            'configured_translation_providers': [p for p, c in settings['providers'].items() if c.get('key')],
            'free_translation_providers': ['google_web', 'bing_web', 'index_web', 'mymemory'],
            'speech_configured': True, 'speech_mode': settings.get('speech_provider', 'auto'),
            'provider_credentials': 'Windows user-bound DPAPI; re-enter on another account',
            'online_services_required': True, 'transcript_contents_in_report': False}

def write_report(path, report):
    from settings import atomic_json
    atomic_json(Path(path), report)
    if sys.stdout:
        print(json.dumps(report, ensure_ascii=True, indent=2))

def self_test(report_path):
    import tempfile
    temporary_root = Path(report_path).parent / '.self-test-temp'
    temporary_root.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temporary_root)
    from tests import test_engine
    from tests import test_app
    from tests import test_app_extra
    from tests import test_ui
    from tests import test_ui_storage
    from tests import test_free_speech
    from tests import test_ui_speech_integration
    from tests import test_speech_model_policy
    from tests import test_workflow_service
    from tests import test_ui_ux
    from tests import test_live_speech
    from tests import test_reinforcement
    from tests import test_reinforced_engine
    from tests import test_translation_removal
    from tests import test_offline_voice
    from tests import test_index_engine
    from tests import test_offline_omni
    from tests import test_voice_reserve
    from tests import test_speech_hotfix
    from tests import test_release_package
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(module) for module in (test_engine, test_app, test_app_extra, test_ui, test_ui_storage, test_free_speech, test_ui_speech_integration, test_speech_model_policy, test_workflow_service, test_ui_ux, test_live_speech, test_reinforcement, test_reinforced_engine, test_translation_removal, test_offline_voice, test_index_engine, test_offline_omni, test_voice_reserve, test_speech_hotfix, test_release_package)])
    import io
    log = io.StringIO()
    started = time.perf_counter()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    report = {'version': VERSION, 'frozen': bool(getattr(sys, 'frozen', False)), 'tests': result.testsRun,
              'passed': result.testsRun - len(result.errors) - len(result.failures) - len(result.skipped),
              'errors': len(result.errors), 'failures': len(result.failures), 'skipped': len(result.skipped),
              'elapsed_seconds': round(time.perf_counter() - started, 3),
              'successful': result.wasSuccessful(), 'log': log.getvalue(),
              'scope': 'Deterministic application correctness; mocked transports; no semantic translation accuracy claim.'}
    write_report(report_path, report)
    return 0 if result.wasSuccessful() else 1

def main():
    parser = argparse.ArgumentParser(description='Gray Feather portable Windows interpreter')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--native-self-test', action='store_true')
    parser.add_argument('--diagnose', action='store_true')
    parser.add_argument('--ui-smoke', action='store_true')
    parser.add_argument('--ui-live-check', action='store_true')
    parser.add_argument('--live-benchmark', action='store_true')
    parser.add_argument('--speech-check', action='store_true')
    parser.add_argument('--translation-types-check', action='store_true')
    parser.add_argument('--all-language-check', action='store_true')
    parser.add_argument('--edge-voice-worker', type=Path)
    parser.add_argument('--edge-voice-output', type=Path)
    parser.add_argument('--speech-preview-worker', type=Path)
    parser.add_argument('--speech-preview-output', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--version', action='store_true')
    args = parser.parse_args()
    if args.edge_voice_worker is not None or args.edge_voice_output is not None:
        if args.edge_voice_worker is None or args.edge_voice_output is None:
            return 1
        from speech import run_edge_voice_worker
        return run_edge_voice_worker(args.edge_voice_worker, args.edge_voice_output)
    if args.speech_preview_worker is not None or args.speech_preview_output is not None:
        if args.speech_preview_worker is None or args.speech_preview_output is None:
            return 1
        from speech import run_speech_preview_worker
        return run_speech_preview_worker(args.speech_preview_worker, args.speech_preview_output)
    data_dir = args.data_dir or portable_root() / 'GrayFeather-data'
    report = args.report or data_dir / ('self-test.json' if args.self_test else 'diagnostics.json')
    try:
        ensure_data(data_dir)
        if args.version:
            write_report(report, {'version': VERSION})
            return 0
        if args.self_test:
            return self_test(report)
        if args.native_self_test:
            from tests.native_bundle_check import run
            result = run()
            result.update(version=VERSION, frozen=bool(getattr(sys,'frozen',False)))
            write_report(report,result)
            return 0 if result['successful'] else 1
        if args.diagnose:
            write_report(report, diagnose(data_dir))
            return 0
        if args.speech_check:
            from tests.runtime_checks import run
            result = run()
            write_report(report, result)
            return 0 if result['successful'] else 1
        if args.live_benchmark or args.translation_types_check or args.all_language_check:
            if args.all_language_check:
                from tests.language_corpus_check import run
            elif args.translation_types_check:
                from translation_types_check import run
            else:
                from tests.live_benchmark import run
            service = Service(data_dir)
            try:
                if args.all_language_check:
                    partial = []
                    def progress(index, total, row):
                        partial.append(row)
                        if index % 10 == 0 or index == total:
                            from settings import atomic_json
                            atomic_json(report, {'version': VERSION, 'incomplete': True, 'completed': index, 'expected': total, 'results': partial})
                    result = run(service, progress=progress)
                else:
                    result = run(service)
                write_report(report, result)
                return 0 if not result['failed_cases'] else 1
            finally:
                service.shutdown()
        from PySide6.QtCore import QTimer, QLockFile
        from PySide6.QtWidgets import QApplication, QMessageBox
        application = QApplication(sys.argv[:1])
        application.setApplicationName('Gray Feather')
        application.setOrganizationName('Gray Feather')
        lock = QLockFile(str(data_dir / '.instance.lock'))
        lock.setStaleLockTime(0)
        if not (args.ui_smoke or args.ui_live_check) and not lock.tryLock(0):
            handle = ctypes.windll.user32.FindWindowW(None, 'Gray Feather')
            if handle:
                ctypes.windll.user32.ShowWindow(handle, 9)
                ctypes.windll.user32.SetForegroundWindow(handle)
            else:
                QMessageBox.information(None, 'Gray Feather', 'Gray Feather is already open for this data folder.')
            return 0
        service = Service(data_dir)
        from ui import MainWindow
        from PySide6.QtGui import QIcon
        window = MainWindow(service)
        window.setWindowTitle('Gray Feather')
        window.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / 'grayfeather.png')))
        window.show()
        application.aboutToQuit.connect(service.shutdown)
        if args.ui_live_check:
            from tests import ui_live_check
            QTimer.singleShot(200,lambda: ui_live_check.start(window,service,application,report))
        if args.ui_smoke:
            def finish_smoke():
                try:
                    screenshot = report.with_suffix('.png')
                    window.grab().save(str(screenshot))
                    write_report(report, {'successful': True, 'window_title': window.windowTitle(),
                                         'size': [window.width(), window.height()], 'screenshot': str(screenshot),
                                         'frozen': bool(getattr(sys, 'frozen', False)), 'languages': len(service.languages),
                                         'device_pixel_ratio': window.devicePixelRatioF(),
                                         'available_geometry': list(window.screen().availableGeometry().getRect()),
                                         'frame_geometry': list(window.frameGeometry().getRect())})
                except Exception as error:
                    write_report(report, {'successful': False, 'error_type': type(error).__name__})
                application.quit()
            QTimer.singleShot(1200, finish_smoke)
        return application.exec()
    except Exception as error:
        report_written = False
        try:
            write_report(report, {'successful': False, 'error_type': type(error).__name__, 'message': str(error)})
            report_written = True
        except Exception:
            pass
        if not (args.self_test or args.native_self_test or args.diagnose or args.ui_smoke or args.ui_live_check or args.live_benchmark or args.speech_check or args.translation_types_check or args.all_language_check):
            try:
                detail = f'\n\nDiagnostic report: {report}' if report_written else '\n\nA diagnostic file could not be written to the selected location.'
                ctypes.windll.user32.MessageBoxW(None, str(error) + detail, 'Gray Feather could not start', 0x10)
            except Exception:
                pass
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
