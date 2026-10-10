"""Native GUI + real application service + SQLite integration regressions."""
from __future__ import annotations
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import Service
from ui import MainWindow


class GuiStorageIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = Service(Path(self.temp.name))
        settings = self.service.settings()
        settings["providers"]["azure"]["key"] = "test-fixture-not-a-live-key"
        settings["source1"], settings["source2"] = "en", "fr"
        settings["voice_enabled"] = settings["auto_speak"] = False
        self.service.save_settings(settings)
        self.requests = []
        def fixture(text, source, target, **kwargs):
            self.requests.append(text)
            return {"text": "TEST TRANSLATION " + text, "provider": "azure", "warnings": [], "elapsed_ms": 2,
                    "review_text": "TEST SECOND OPINION", "review_provider": "google", "trace": ["fixture only"]}
        self.service.translate = fixture
        self.service.capabilities = lambda code: {"mic_enabled": False, "voice_enabled": False, "reason": "Fixture, no live audio"}
        self.window = MainWindow(self.service)
        self.window.show()
        self.application.processEvents()

    def tearDown(self):
        self.window.close()
        self.application.processEvents()
        self.service.shutdown()
        self.temp.cleanup()

    def wait(self):
        deadline = time.monotonic() + 3
        while self.window.jobs and time.monotonic() < deadline:
            self.application.processEvents()
            QTest.qWait(5)
        self.assertFalse(self.window.jobs)

    def translate(self, words, side="1"):
        self.window.panels[side].source.setPlainText(words)
        self.window.translate_side(side)
        self.wait()
        return self.window.conversation["turns"][-1]

    def test_real_storage_retains_turns_drafts_comparisons_and_revisions(self):
        self.translate("First 38.50 at 14:30. test@example.com")
        self.translate("Deuxième", "2")
        self.translate("Third turn")
        self.window.panels["1"].source.setPlainText("Untranslated next draft")
        self.assertTrue(self.window._save())
        saved = self.service.load_conversation(self.window.conversation["id"])
        self.assertEqual(len(saved["turns"]), 3)
        self.assertEqual(saved["turns"][0]["raw_source"], "First 38.50 at 14:30. test@example.com")
        self.assertEqual(saved["turns"][0]["review_text"], "TEST SECOND OPINION")
        self.assertEqual(saved["drafts"]["1"], "Untranslated next draft")
        self.assertEqual(saved["revision"], self.window.conversation["revision"])
        self.assertTrue(all(turn["status"] == "complete" for turn in saved["turns"]))

    def test_real_remove_append_undo_does_not_lose_new_turn(self):
        first = self.translate("First")
        second = self.translate("Second")
        self.window.turn_table.selectRow(1)
        self.window.remove_selected_turn()
        saved = self.service.load_conversation(self.window.conversation["id"])
        self.assertEqual([turn["id"] for turn in saved["turns"]], [first["id"]])
        third = self.translate("Third after removal")
        self.assertGreater(third["seq"], second["seq"])
        self.window.undo_removal()
        saved = self.service.load_conversation(self.window.conversation["id"])
        self.assertEqual([turn["id"] for turn in saved["turns"]], [first["id"], second["id"], third["id"]])
        self.assertEqual(len(self.window.conversation["turns"]), 3)

    def test_real_reviewed_source_keeps_raw_and_turn_identity(self):
        turn = self.translate("Do not pay 50 today")
        identity = turn["id"]
        turn.update(reviewed_source="Do not pay £50 today.", ui_generation=2, status="pending")
        self.assertTrue(self.window._save())
        self.window._translate_turn(turn, turn["reviewed_source"])
        self.wait()
        saved = self.service.load_conversation(self.window.conversation["id"])["turns"][0]
        self.assertEqual(saved["id"], identity)
        self.assertEqual(saved["raw_source"], "Do not pay 50 today")
        self.assertEqual(saved["reviewed_source"], "Do not pay £50 today.")
        self.assertEqual(saved["translated_text"], "TEST TRANSLATION Do not pay £50 today.")

    def test_save_conflict_blocks_new_network_request(self):
        self.translate("First")
        other = self.service.load_conversation(self.window.conversation["id"])
        other["title"] = "Changed externally"
        self.service.save_conversation(other)
        self.window.panels["1"].source.setPlainText("Second")
        self.window.translate_side("1")
        self.assertEqual(self.requests, ["First"])
        self.assertEqual(self.window.panels["1"].source.toPlainText(), "Second")
        # Restore current revision for a clean close; the conflict itself was explicit.
        self.window.conversation["revision"] = self.service.load_conversation(other["id"])["revision"]


if __name__ == "__main__":
    unittest.main(verbosity=2)
