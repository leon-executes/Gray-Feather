"""User-facing v1.2 workflows with explicit deterministic fixtures, never live APIs."""
import copy
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog
import ui
import test_ui as fixtures


class PreviewService(fixtures.FakeService):
    def __init__(self):
        super().__init__()
        self.prefs.update(voice_enabled=True, auto_speak=True, voice_provider="auto", text_size=12)
        self.preview_requests = []
        self.preview_hold = None
        self.preview_callback = None
        self.opinion_requests = []

    def recognize(self, code, event, preview_callback=None):
        self.recognition_requests.append((code, event))
        self.preview_callback = preview_callback
        if preview_callback:
            preview_callback({"text": "TEST PROVISIONAL WORDS", "provider": "offline", "sequence": 1, "complete": False})
        event.wait(2)
        if event.abort_event.is_set():
            return {"text": "", "cancelled": True, "complete": False}
        self.recognition_uploads.append(code)
        return copy.deepcopy(self.recognition_result)

    def translate_preview(self, text, source, target, event):
        self.preview_requests.append((text, source, target, event))
        if self.preview_hold:
            self.preview_hold.wait(2)
        return {"text": "TEST PROVISIONAL TRANSLATION", "provider": "google_web"}

    def available_opinion_providers(self, source, target, used):
        return ({"provider": "mymemory", "independent": False},) if "mymemory" not in used else ()

    def add_opinion(self, source, source_code, target_code, used, event):
        self.opinion_requests.append((source, source_code, target_code, used))
        return {"text": "TEST COMPLETE THIRD OPINION\nFull preserved wording.", "provider": "mymemory", "warnings": [], "independent": False}


class UxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.UiTests.setUpClass.__func__(cls)

    wait_idle = fixtures.UiTests.wait_idle
    tearDown = fixtures.UiTests.tearDown
    translate = fixtures.UiTests.translate

    def setUp(self):
        self.service = PreviewService()
        self.window = ui.MainWindow(self.service)
        self.window.show()
        self.application.processEvents()

    def wait_for(self, condition, description):
        deadline = time.monotonic() + 2
        while not condition() and time.monotonic() < deadline:
            self.application.processEvents()
            QTest.qWait(5)
        self.assertTrue(condition(), description)

    def test_translation_stays_with_source_and_target_direction(self):
        self.window.panels["2"].set_code("ar")
        turn = self.translate("Preserve these source words")
        own, other = self.window.panels["1"], self.window.panels["2"]
        self.assertEqual(own.source.toPlainText(), turn["raw_source"])
        self.assertEqual(own.received.toPlainText(), turn["translated_text"])
        self.assertEqual(other.received.toPlainText(), "")
        self.assertEqual(own.received.document().defaultTextOption().textDirection(), Qt.LayoutDirection.RightToLeft)
        self.assertFalse(own.listen_button.isEnabled())  # Target Arabic has no fixture voice.

    def test_source_copy_and_pressable_listen_use_exact_visible_text(self):
        self.window.preferences.update(voice_enabled=False, auto_speak=False)
        turn = self.translate("Exact source\nSecond line")
        panel = self.window.panels["1"]
        panel.source_copy.click()
        self.assertEqual(self.application.clipboard().text(), turn["raw_source"])
        self.assertEqual(self.service.spoken, [])
        panel.listen_button.click()
        self.wait_idle()
        self.assertEqual(self.service.spoken, [(turn["translated_text"], "fr")])

    def test_typing_a_new_source_clears_the_previous_output(self):
        self.translate("Old source")
        panel = self.window.panels["1"]
        panel.source.setPlainText("New source still being written")
        self.assertEqual(panel.received.toPlainText(), "")
        self.window._refresh_turns()
        self.assertEqual(panel.received.toPlainText(), "")
        self.assertEqual(self.window.conversation["turns"][0]["raw_source"], "Old source")

    def test_theme_and_font_apply_immediately_without_replacing_active_settings(self):
        pane = self.window.settings_pane
        self.assertEqual(pane.text_size.value(), 12)
        self.assertEqual(pane.text_size.minimum(), 10)
        pane.theme.setCurrentIndex(pane.theme.findData("light"))
        self.assertEqual(self.service.prefs["theme"], "light")
        self.assertIs(self.window.settings_pane, pane)
        pane.text_size.setValue(17)
        self.assertEqual(self.service.prefs["text_size"], 17)
        self.assertEqual(self.window.panels["1"].source.font().pixelSize(), round(17 * 4 / 3))
        self.assertFalse(pane.apply.isVisible())

    def test_three_provider_choices_apply_independently(self):
        pane = self.window.settings_pane
        pane.provider.setCurrentIndex(pane.provider.findData("bing_web"))
        pane.speech_provider.setCurrentIndex(pane.speech_provider.findData("offline"))
        pane.voice_provider.setCurrentIndex(pane.voice_provider.findData("windows"))
        self.assertEqual(self.service.prefs["provider"], "bing_web")
        self.assertEqual(self.service.prefs["speech_provider"], "offline")
        self.assertEqual(self.service.prefs["voice_provider"], "windows")

    def test_voice_toggle_and_clear_session_preserve_saved_history(self):
        first = self.translate("Saved previous session")
        identity = self.window.conversation["id"]
        self.window.voice_disabled_button.click()
        self.assertFalse(self.service.prefs["voice_enabled"])
        self.assertTrue(self.window.voice_disabled_button.isChecked())
        self.assertFalse(self.window.voice_button.isChecked())
        self.assertTrue(self.window.voice_button.isVisible())
        self.window.new_button.click()
        self.assertNotEqual(self.window.conversation["id"], identity)
        self.assertEqual(self.window.conversation["turns"], [])
        self.assertEqual(self.service.saved[identity]["turns"][0]["raw_source"], first["raw_source"])

    def test_live_previews_never_save_or_speak_then_final_is_automatic(self):
        panel = self.window.panels["1"]
        panel.record_button.click()
        self.wait_for(lambda: panel.received.toPlainText() == "TEST PROVISIONAL TRANSLATION", "live translation preview missing")
        self.assertEqual(panel.source.toPlainText(), "")
        self.assertEqual(panel.received.toPlainText(), "TEST PROVISIONAL TRANSLATION")
        self.assertIsNone(panel.received_turn)
        self.assertFalse(panel.listen_button.isEnabled())
        self.assertFalse(panel.review_button.isEnabled())
        self.assertEqual(self.service.saved_snapshots, [])
        self.assertEqual(self.service.spoken, [])
        self.assertTrue(panel.record_button.property("recording"))
        panel.record_button.click()
        self.wait_idle()
        self.assertEqual(len(self.service.requests), 1)
        self.assertEqual(self.window.conversation["turns"][0]["raw_source"], "TEST RECOGNIZED WORDS")
        self.assertEqual(self.service.spoken, [("TEST TRANSLATION: TEST RECOGNIZED WORDS", "fr")])
        self.assertFalse(panel.translation_preview_label.isVisible())
        self.assertFalse(panel.record_button.property("recording"))
        self.assertEqual(panel.record_opacity.opacity(), 1.0)
        self.assertNotIn("PROVISIONAL", str(self.service.saved_snapshots))

    def test_cancelled_preview_cannot_replace_the_final_translation(self):
        self.service.preview_hold = threading.Event()
        panel = self.window.panels["1"]
        panel.record_button.click()
        self.wait_for(lambda: bool(self.service.preview_requests), "preview worker missing")
        panel.record_button.click()
        self.wait_for(lambda: bool(self.service.requests), "final translation blocked by preview")
        self.service.preview_hold.set()
        self.wait_idle()
        self.assertEqual(panel.received.toPlainText(), "TEST TRANSLATION: TEST RECOGNIZED WORDS")

    def test_edited_draft_rejects_live_preview_and_preserves_words_in_final(self):
        panel = self.window.panels["1"]
        panel.source.setPlainText("Typed draft")
        panel.record_button.click()
        self.wait_for(lambda: self.service.preview_callback is not None, "recognition callback missing")
        panel.source.setPlainText("Edited draft")
        self.service.preview_callback({"text": "LATE PROVISIONAL", "sequence": 2, "complete": False})
        self.application.processEvents()
        self.assertFalse(panel.dictation_preview.isVisible())
        panel.record_button.click()
        self.wait_idle()
        self.assertEqual(self.window.conversation["turns"][-1]["raw_source"], "Edited draft\nTEST RECOGNIZED WORDS")

    def test_next_record_replaces_completed_source_but_keeps_saved_original(self):
        first = self.translate("Completed previous words")
        panel = self.window.panels["1"]
        panel.record_button.click()
        self.wait_for(lambda: bool(self.service.recognition_requests), "record did not start")
        panel.record_button.click()
        self.wait_idle()
        self.assertEqual(panel.source.toPlainText(), "TEST RECOGNIZED WORDS")
        self.assertEqual([turn["raw_source"] for turn in self.window.conversation["turns"]], [first["raw_source"], "TEST RECOGNIZED WORDS"])

    def test_incomplete_dictation_translates_but_blocks_automatic_voice(self):
        self.service.recognition_result.update(complete=False, limit_reached=True)
        panel = self.window.panels["1"]
        panel.record_button.click()
        self.wait_for(lambda: bool(self.service.recognition_requests), "record missing")
        panel.record_button.click()
        self.wait_idle()
        turn = self.window.conversation["turns"][-1]
        self.assertTrue(turn["translated_text"])
        self.assertTrue(ui.review_messages(turn, playback=True))
        self.assertEqual(self.service.spoken, [])

    def test_generic_dictation_advisories_are_preserved_without_blocking_auto_voice(self):
        self.service.checks = ()  # Actual Service returns the engine warning tuple.
        self.service.recognition_result.update(provider="offline", warnings=["Review dictation before translating; names, numbers and negation can be misheard.", "Review offline wording carefully, especially names, numbers and low-resource languages."], trace=["Test local recognition trace"])
        panel = self.window.panels["1"]
        panel.record_button.click()
        self.wait_for(lambda: bool(self.service.recognition_requests), "record missing")
        panel.record_button.click()
        self.wait_idle()
        turn = self.window.conversation["turns"][-1]
        self.assertEqual(len(self.service.spoken), 1)
        self.assertFalse(ui.review_messages(turn, playback=True))
        self.assertEqual(turn["dictation"]["trace"], ["Test local recognition trace"])
        dialog = ui.TurnDialog(turn, self.window, self.window.language_by_code)
        details = next(editor for editor in dialog.findChildren(ui.QPlainTextEdit) if editor.accessibleName().startswith("Dictation details"))
        self.assertIn("names, numbers", details.toPlainText())
        self.assertIn("Test local recognition trace", details.toPlainText())
        dialog.close()

    def test_generic_source_negation_cue_is_visible_but_does_not_block_voice(self):
        message = "The source contains a possible negation. Confirm that the translated meaning retains it; fact checks cannot establish this."
        self.service.warnings = [message]
        self.service.checks = ({"code": "negation", "message": message},)
        with patch.object(ui.QMessageBox, "question") as question:
            turn = self.translate("Do not cancel the appointment.")
            self.assertEqual(len(self.service.spoken), 1)
            self.window.panels["1"].listen_button.click()
            self.wait_idle()
            question.assert_not_called()
        self.assertIn(message, turn["warnings"])
        self.assertEqual(ui.review_messages(turn), [message])
        self.assertFalse(ui.review_messages(turn, playback=True))
        self.assertTrue(self.window.panels["1"].received_warning.isVisible())

    def test_voice_disable_intent_survives_a_settings_disk_failure(self):
        with patch.object(self.service, "save_settings", side_effect=OSError("TEST DISK FAILURE")):
            self.window.voice_disabled_button.click()
        self.assertFalse(self.window.preferences["voice_enabled"])
        self.assertFalse(self.window.settings_pane.original["voice_enabled"])
        self.translate("Keep this silent")
        self.assertEqual(self.service.spoken, [])

    def test_malformed_service_checks_fail_visibly_and_clear_partial_output(self):
        self.service.checks = 7
        turn = self.translate("Keep these original words")
        self.assertEqual(turn["raw_source"], "Keep these original words")
        self.assertEqual(turn["status"], "failed")
        self.assertEqual(turn["translated_text"], "")
        self.assertEqual(turn["checks"], [])
        saved = self.service.saved[self.window.conversation["id"]]["turns"][-1]
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(self.window.panels["1"].received.toPlainText(), "")
        self.assertTrue(self.window.notice.isVisible())
        self.assertIn("could not be completed safely", self.window.notice.text())
        self.assertIsNone(self.window.translation_token)

    def test_queued_callback_exception_is_visible_and_worker_is_released(self):
        def broken(value):
            raise RuntimeError("TEST CALLBACK FAILURE")
        self.window._run(lambda: "TEST RESPONSE", broken)
        self.wait_idle()
        self.assertTrue(self.window.notice.isVisible())
        self.assertIn("TEST CALLBACK FAILURE", self.window.notice.text())
        self.assertFalse(self.window.jobs)

    def test_additional_actual_opinion_is_complete_attributed_and_persisted(self):
        turn = self.translate("Words for comparison")
        turn.update(provider="google_web", review_provider="bing_web")
        dialog = ui.TurnDialog(turn, self.window, self.window.language_by_code)
        dialog.show()
        self.assertTrue(dialog.add_opinion_button.isEnabled())
        dialog.add_opinion_button.click()
        self.wait_idle()
        opinion = turn["extra_opinions"][0]
        self.assertEqual(opinion["provider"], "mymemory")
        self.assertIn("Full preserved wording.", opinion["text"])
        self.assertFalse(dialog.add_opinion_button.isEnabled())
        self.assertTrue(any("mixed sources; not independent" in editor.accessibleName() for editor in dialog.findChildren(ui.QPlainTextEdit)))
        saved = self.service.saved[self.window.conversation["id"]]["turns"][0]
        self.assertEqual(saved["extra_opinions"], [opinion])
        dialog.close()

    def test_embedded_actions_never_overlap_text_at_compact_large_font(self):
        self.window.preferences["text_size"] = 24
        self.window._apply_theme()
        self.window.resize(780, 620)
        self.application.processEvents()
        for panel in self.window.panels.values():
            for editor, action in ((panel.source, panel.record_button), (panel.received, panel.listen_button)):
                bottom = editor.mapTo(panel, QPoint(0, editor.height())).y()
                action_top = action.mapTo(panel, QPoint(0, 0)).y()
                self.assertLessEqual(bottom, action_top)
            self.assertLess(panel.record_button.x(), panel.translate_button.x())


if __name__ == "__main__":
    unittest.main()
