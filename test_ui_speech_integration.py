"""Qt + actual Service + SQLite speech boundaries, with synthetic audio only."""
from __future__ import annotations
import io
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import Service
import speech
from ui import MainWindow


class RealSpeechServiceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.service = Service(Path(self.temp.name))
        preferences = self.service.settings()
        preferences["voice_enabled"] = preferences["auto_speak"] = False
        self.service.save_settings(preferences)
        self.service.translate = lambda text, source, target, **kwargs: {"text": "TEST FINAL TRANSLATION: " + text, "provider": "fixture", "warnings": [], "checks": []}
        self.window = MainWindow(self.service)
        self.window.show()
        self.application.processEvents()
        self.capture_started = threading.Event()
        self.capture_stop = None
        stream = io.BytesIO()
        with wave.open(stream, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x23\x01" * 12000)
        self.audio = stream.getvalue()

    def tearDown(self):
        self.window.stop_everything()
        self.wait_idle()
        self.window.close()
        self.application.processEvents()
        self.service.shutdown()
        self.temp.cleanup()

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.application.processEvents()
            QTest.qWait(5)
            if not self.window.jobs and not getattr(self.window, "pending_final_translation", None):
                break
        self.application.processEvents()
        self.assertFalse(self.window.jobs)

    def record_fixture(self, stop):
        self.capture_stop = stop
        self.capture_started.set()
        if not stop.wait(2):
            raise RuntimeError("Test capture did not receive a stop signal")
        return self.audio, {"complete": True, "duration_ms": 750, "limit_reached": False}

    def record_preview_fixture(self, stop, locale, settings, preview_callback=None):
        return self.record_fixture(stop)

    def start_record(self):
        self.assertEqual(self.service.settings()["speech_provider"], "auto")
        self.assertFalse(self.service.settings()["speech_key"])
        panel = self.window.panels["1"]
        self.assertTrue(panel.record_button.isEnabled())
        panel.source.setPlainText("Preserved typed words")
        panel.record_button.click()
        deadline = time.monotonic() + 1
        while not self.capture_started.is_set() and time.monotonic() < deadline:
            self.application.processEvents()
            QTest.qWait(5)
        self.assertTrue(self.capture_started.is_set())
        return panel

    def test_no_key_stop_commits_through_real_service_and_persists_capture(self):
        result = {"text": "TEST DICTATION: Do not pay 38 until Friday.", "provider": "google_web", "complete": True, "warnings": []}
        with patch.object(speech, "record_with_previews", side_effect=self.record_preview_fixture), patch.object(speech, "recognize_with_fallback", return_value=result) as recognize:
            panel = self.start_record()
            panel.record_button.click()
            self.wait_idle()
            recognize.assert_called_once()
            self.assertEqual(recognize.call_args.args[0], self.audio)
            self.assertEqual(recognize.call_args.args[1], "en-US")
            self.assertIs(recognize.call_args.args[3], self.capture_stop.abort_event)
            self.assertFalse(self.capture_stop.abort_event.is_set())
        self.assertEqual(panel.source.toPlainText(), "Preserved typed words\n" + result["text"])
        saved = self.service.load_conversation(self.window.conversation["id"])
        self.assertEqual(saved["drafts"]["1"], panel.source.toPlainText())
        self.assertEqual(saved["metadata"]["last_dictation"]["1"]["provider"], "google_web")
        self.assertEqual(saved["metadata"]["last_dictation"]["1"]["duration_ms"], 750)
        self.assertEqual(saved["turns"][0]["raw_source"], panel.source.toPlainText())
        self.assertEqual(saved["turns"][0]["dictation"]["provider"], "google_web")
        self.assertTrue(saved["turns"][0]["translated_text"].startswith("TEST FINAL TRANSLATION"))

    def test_escape_aborts_actual_service_before_recognizer_transmission(self):
        with patch.object(speech, "record_with_previews", side_effect=self.record_preview_fixture), patch.object(speech, "recognize_with_fallback") as recognize:
            panel = self.start_record()
            self.window.activateWindow()
            panel.source.setFocus()
            self.application.processEvents()
            QTest.keyClick(panel.source, Qt.Key.Key_Escape)
            self.wait_idle()
            self.assertTrue(self.capture_stop.is_set())
            self.assertTrue(self.capture_stop.abort_event.is_set())
            recognize.assert_not_called()
        self.assertEqual(panel.source.toPlainText(), "Preserved typed words")
        self.assertEqual(self.window.status_heading.text(), "Task cancelled")
        self.assertTrue(self.window._save())
        saved = self.service.load_conversation(self.window.conversation["id"])
        self.assertEqual(saved["drafts"]["1"], "Preserved typed words")
        self.assertNotIn("last_dictation", saved.get("metadata", {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
