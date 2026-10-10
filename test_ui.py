"""Deterministic GUI regressions. All service responses are explicit test fixtures."""
from __future__ import annotations
import copy
import os
import threading
import time
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, QThread, QPoint, QRect
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
import ui


class FakeService:
    languages = [
        {"code": "en", "name": "English", "native": "English", "rtl": False},
        {"code": "fr", "name": "French", "native": "Français", "rtl": False},
        {"code": "ar", "name": "Arabic", "native": "العربية", "rtl": True},
    ]
    def __init__(self):
        self.prefs = {"provider": "azure", "providers": {"azure": {"key": "test-fixture", "region": "uksouth"}}, "source1": "en", "source2": "fr", "theme": "dark", "speech_key": "test-fixture", "speech_provider": "azure", "speech_region": "uksouth"}
        self.saved = {}
        self.requests = []
        self.hold = None
        self.error = ""
        self.warnings = []
        self.checks = []
        self.spoken = []
        self.callback_thread = None
        self.saved_snapshots = []
        self.sequences = {}
        self.recognition_requests = []
        self.recognition_uploads = []
        self.recognition_error = ""
        self.recognition_result = {"text": "TEST RECOGNIZED WORDS", "complete": True, "provider": "google_web", "warnings": [], "duration_ms": 1250}

    def settings(self):
        return copy.deepcopy(self.prefs)

    def save_settings(self, value):
        self.prefs = copy.deepcopy(value)

    def capabilities(self, code):
        return {"mic_enabled": True, "voice_enabled": code != "ar", "reason": "Test fixture speech capability"}

    def list_conversations(self):
        return list(reversed(list(copy.deepcopy(self.saved).values())))

    def save_conversation(self, value):
        self.saved_snapshots.append(copy.deepcopy(value))
        old = self.saved.get(value["id"], {})
        for turn in value["turns"]:
            if not turn.get("seq"):
                self.sequences[value["id"]] = self.sequences.get(value["id"], 0) + 1
                turn["seq"] = self.sequences[value["id"]]
            turn["revision"] = int(turn.get("revision", 0)) + 1
        value["revision"] = int(old.get("revision", 0)) + 1
        value.pop("deleted_turn_ids", None)
        self.saved[value["id"]] = copy.deepcopy(value)
        return copy.deepcopy(value)

    def load_conversation(self, identity):
        return copy.deepcopy(self.saved.get(identity))

    def delete_conversation(self, identity):
        self.saved.pop(identity, None)

    def translate(self, text, source, target, **kwargs):
        self.requests.append((text, source, target, kwargs))
        self.callback_thread = threading.get_ident()
        if self.hold:
            self.hold.wait(2)
        if self.error:
            raise ValueError(self.error)
        return {"text": "TEST TRANSLATION: " + text, "provider": "fixture", "warnings": list(self.warnings), "checks": copy.deepcopy(self.checks), "elapsed_ms": 5,
                "review_text": "TEST SECOND OPINION", "review_provider": "fixture2", "backtranslation": "TEST BACK TRANSLATION", "backtranslation_provider": "fixture2"}

    def recognize(self, code, event):
        self.recognition_requests.append((code, event))
        if self.recognition_error:
            raise ValueError(self.recognition_error)
        event.wait(2)
        if getattr(event, "abort_event", threading.Event()).is_set():
            return {"text": "", "complete": False, "cancelled": True}
        self.recognition_uploads.append(code)
        return copy.deepcopy(self.recognition_result)

    def speak(self, text, code, event):
        self.spoken.append((text, code))

    def stop_audio(self):
        pass


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        if "Segoe UI" not in QFontDatabase.families():
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeuib.ttf")

    def setUp(self):
        self.service = FakeService()
        self.window = ui.MainWindow(self.service)
        self.window.show()
        self.application.processEvents()

    def tearDown(self):
        if self.service.hold:
            self.service.hold.set()
        self.window.stop_everything()
        self.wait_idle()
        self.window.close()
        self.application.processEvents()

    def wait_idle(self):
        stop = time.monotonic() + 3
        while time.monotonic() < stop:
            self.application.processEvents()
            QTest.qWait(5)
            if not self.window.jobs and not getattr(self.window, "pending_final_translation", None):
                break
        self.application.processEvents()
        self.assertFalse(self.window.jobs, "GUI worker did not finish")

    def translate(self, text="Hello", side="1"):
        self.window.panels[side].source.setPlainText(text)
        self.window.translate_side(side)
        self.wait_idle()
        return self.window.conversation["turns"][-1]

    def test_three_alternating_turns_append_and_keep_ids(self):
        turns = [self.translate("First"), self.translate("Second", "2"), self.translate("Third")]
        self.assertEqual([x["raw_source"] for x in turns], ["First", "Second", "Third"])
        self.assertEqual(len({x["id"] for x in turns}), 3)
        self.assertEqual([x["seq"] for x in turns], [1, 2, 3])
        self.assertEqual(len(self.window.conversation["turns"]), 3)

    def test_original_decimal_email_and_date_are_exact(self):
        source = "Pay £38.50 at 14:30. test@example.com\nDo not pay 50 today."
        turn = self.translate(source)
        self.assertEqual(turn["raw_source"], source)
        self.assertEqual(turn["reviewed_source"], source)
        self.assertEqual(self.service.requests[-1][0], source)

    def test_typing_during_request_is_not_cleared(self):
        self.service.hold = threading.Event()
        self.window.panels["1"].source.setPlainText("First draft")
        self.window.translate_side("1")
        self.window.panels["1"].source.setPlainText("New draft while waiting")
        self.service.hold.set()
        self.wait_idle()
        self.assertEqual(self.window.panels["1"].source.toPlainText(), "New draft while waiting")
        self.assertEqual(self.window.conversation["turns"][0]["raw_source"], "First draft")

    def test_cancel_discards_late_translation(self):
        self.service.hold = threading.Event()
        self.window.panels["1"].source.setPlainText("Cancelled words")
        self.window.translate_side("1")
        self.window.cancel_jobs()
        self.service.hold.set()
        self.wait_idle()
        turn = self.window.conversation["turns"][0]
        self.assertEqual(turn["status"], "cancelled")
        self.assertEqual(turn["translated_text"], "")
        self.assertEqual(turn["raw_source"], "Cancelled words")

    def test_old_conversation_cannot_receive_late_result(self):
        self.service.hold = threading.Event()
        self.window.panels["1"].source.setPlainText("Old conversation")
        self.window.translate_side("1")
        self.window.new_conversation()
        self.service.hold.set()
        self.wait_idle()
        self.assertEqual(self.window.conversation["turns"], [])
        self.assertEqual(self.window.panels["1"].received.toPlainText(), "")

    def test_recognition_stop_returns_reviewable_text_and_preserves_edits(self):
        self.window.panels["1"].source.setPlainText("Typed words")
        self.window.record_side("1")
        self.window.panels["1"].source.setPlainText("Edited typed words")
        self.window.record_side("1")
        self.wait_idle()
        self.assertEqual(self.window.panels["1"].source.toPlainText(), "Edited typed words\nTEST RECOGNIZED WORDS")
        self.assertEqual(self.service.requests[-1][0], "Edited typed words\nTEST RECOGNIZED WORDS")

    def test_failure_keeps_raw_and_composer(self):
        self.service.error = "Fixture network failure"
        turn = self.translate("Keep these words")
        self.assertEqual(turn["status"], "failed")
        self.assertEqual(self.window.panels["1"].source.toPlainText(), "Keep these words")
        self.assertEqual(turn["raw_source"], "Keep these words")

    def test_returned_storage_revision_is_propagated(self):
        self.window.panels["1"].source.setPlainText("Saved draft")
        self.window._save()
        initial = self.window.conversation["revision"]
        self.window._save()
        self.assertGreater(self.window.conversation["revision"], initial)

    def test_remove_explicit_intent_undo_and_monotonic_sequence(self):
        first = self.translate("First")
        second = self.translate("Second")
        self.window.turn_table.selectRow(1)
        self.window.remove_selected_turn()
        self.assertEqual(self.service.saved_snapshots[-1]["deleted_turn_ids"], [second["id"]])
        self.window.undo_removal()
        self.assertEqual([x["id"] for x in self.window.conversation["turns"]], [first["id"], second["id"]])
        self.window.turn_table.selectRow(0)
        self.window.remove_selected_turn()
        third = self.translate("Third")
        self.assertEqual(third["seq"], 3)

    def test_reinforcement_payload_survives_save(self):
        self.service.warnings = ["Check changed amount"]
        turn = self.translate("Pay 50")
        self.assertEqual(turn["review_text"], "TEST SECOND OPINION")
        self.assertEqual(turn["backtranslation"], "TEST BACK TRANSLATION")
        self.assertEqual(turn["backtranslation_provider"], "fixture2")
        self.assertTrue(self.window.panels["1"].received_warning.isVisible())

    def test_auto_voice_is_sidelined_when_warning_exists(self):
        self.window.preferences["auto_speak"] = True
        self.service.warnings = ["The translated quantity changed"]
        self.service.checks = [{"code": "numbers", "message": "The translated quantity changed"}]
        self.translate("Pay 50")
        self.assertEqual(self.service.spoken, [])

    def test_normal_second_opinion_is_available_without_warning_modal(self):
        message = "A second provider is available for human comparison. Agreement cannot establish correctness."
        self.service.warnings = [message]
        self.service.checks = [{"code": "independent_review", "message": message}]
        self.window.preferences["auto_speak"] = True
        with patch.object(ui.QMessageBox, "question") as question:
            turn = self.translate("Good morning")
            self.assertEqual(len(self.service.spoken), 1)
            self.window.listen_side("1")
            self.wait_idle()
            question.assert_not_called()
        self.assertFalse(ui.needs_review(turn))
        self.assertFalse(self.window.panels["1"].received_warning.isVisible())
        self.assertEqual(self.window.turn_table.item(0, 4).text(), "Review available")
        self.assertEqual(turn["review_text"], "TEST SECOND OPINION")
        self.assertTrue(self.window.review_button.isEnabled())

    def test_advisory_backtranslation_does_not_prompt_or_block_auto_read(self):
        message = "Backtranslation uses a separate translation engine. A similar round trip cannot establish accuracy."
        self.service.warnings = [message]
        self.service.checks = [{"code": "backtranslation", "message": message}]
        self.window.preferences["auto_speak"] = True
        with patch.object(ui.QMessageBox, "question") as question:
            turn = self.translate("Good morning")
            self.assertEqual(len(self.service.spoken), 1)
            self.window.listen_side("1")
            self.wait_idle()
            question.assert_not_called()
        self.assertFalse(ui.needs_review(turn))
        self.assertFalse(self.window.panels["1"].received_warning.isVisible())
        self.assertEqual(turn["backtranslation"], "TEST BACK TRANSLATION")

    def test_backtranslation_pane_default_and_deliberate_optout_are_preserved(self):
        pane = ui.SettingsPane(self.service.settings())
        self.assertTrue(pane.backtranslate.isChecked())
        results = []
        pane.saved.connect(results.append)
        pane.backtranslate.setChecked(False)
        pane._save()
        self.assertFalse(results[-1]["backtranslate"])
        reopened = ui.SettingsPane(results[-1])
        self.assertFalse(reopened.backtranslate.isChecked())

    def test_keyless_capability_reason_survives_saved_optional_speech_key(self):
        self.window.preferences["speech_provider"] = "offline"
        reason = "Bundled local recognition is unavailable for this language. Choose Automatic for free online dictation."
        self.service.capabilities = lambda code: {"mic_enabled": False, "voice_enabled": False, "reason": reason}
        self.window._refresh_capabilities()
        self.assertEqual(self.window.panels["1"].capability_note.text(), reason)
        self.assertFalse(self.window.panels["1"].record_button.isEnabled())

    def test_changed_number_blocks_auto_voice_and_requires_playback_confirmation(self):
        message = "Numbers changed between the source and translation."
        self.service.warnings = [message]
        self.service.checks = [{"code": "numbers", "message": message}]
        self.window.preferences["auto_speak"] = True
        turn = self.translate("Pay 50")
        self.assertTrue(ui.needs_review(turn))
        self.assertEqual(self.service.spoken, [])
        with patch.object(ui.QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question:
            self.window.listen_side("1")
            question.assert_called_once()
        self.assertEqual(self.service.spoken, [])

    def test_second_opinion_copy_preserves_complete_text_and_engine_attribution(self):
        turn = self.translate("Main source")
        turn.update(provider="google_web", review_text="Bonjour.\nDeuxième phrase complète.", review_provider="bing_web", backtranslation_provider="google_web")
        original = copy.deepcopy(turn)
        dialog = ui.TurnDialog(turn, self.window, self.window.language_by_code)
        details = [editor for editor in dialog.findChildren(ui.QPlainTextEdit) if editor.accessibleName().startswith("Second opinion")]
        self.assertEqual(details[0].toPlainText(), turn["review_text"])
        self.assertIn("Microsoft Bing", details[0].accessibleName())
        self.assertTrue(any("Google Translate" in editor.accessibleName() for editor in dialog.findChildren(ui.QPlainTextEdit)))
        dialog.copy_second_opinion.click()
        self.assertEqual(self.application.clipboard().text(), turn["review_text"])
        self.assertEqual(turn, original)
        dialog.close()

    def test_rtl_text_option_is_correct(self):
        panel = self.window.panels["2"]
        panel.set_code("ar")
        self.assertEqual(panel.source.document().defaultTextOption().textDirection(), Qt.LayoutDirection.RightToLeft)

    def test_credentials_blank_keeps_existing_and_remove_is_explicit(self):
        pane = ui.SettingsPane(self.service.settings())
        results = []
        pane.saved.connect(results.append)
        pane._save()
        self.assertEqual(results[-1]["providers"]["azure"]["key"], "test-fixture")
        pane.removals["azure"].setChecked(True)
        pane._save()
        self.assertEqual(results[-1]["providers"]["azure"]["key"], "")

    def test_worker_operations_run_away_from_gui_thread(self):
        gui_thread = threading.get_ident()
        self.translate()
        self.assertNotEqual(gui_thread, self.service.callback_thread)
        self.assertEqual(self.window.thread(), self.application.thread())

    def test_saved_drafts_restore_without_overwriting(self):
        self.window.panels["1"].source.setPlainText("Untranslated draft")
        self.window.panels["2"].source.setPlainText("Second untranslated draft")
        self.window._save()
        identity = self.window.conversation["id"]
        self.window.new_conversation()
        self.window._load_conversation(self.service.load_conversation(identity))
        self.assertEqual(self.window.panels["1"].source.toPlainText(), "Untranslated draft")
        self.assertEqual(self.window.panels["2"].source.toPlainText(), "Second untranslated draft")

    def test_light_theme_and_small_window_retain_controls(self):
        self.window.preferences.update(theme="light", text_size=18)
        self.window._apply_theme()
        self.window.resize(800, 740)
        self.application.processEvents()
        self.assertTrue(self.window.panels["1"].translate_button.isVisible())
        self.assertTrue(self.window.panels["2"].translate_button.isVisible())
        self.assertGreater(self.window.panels["1"].source.height(), 70)

    def test_layout_has_no_editor_button_overlap_at_compact_and_large_font(self):
        for size, text_size in (((800, 740), 14), ((1000, 800), 14), ((800, 740), 24)):
            self.window.preferences["text_size"] = text_size
            self.window._apply_theme()
            self.window.resize(*size)
            self.application.processEvents()
            for panel in self.window.panels.values():
                source_bottom = panel.source.mapTo(panel, QPoint(0, panel.source.height())).y()
                controls_top = panel.translate_button.mapTo(panel, QPoint(0, 0)).y()
                received_bottom = panel.received.mapTo(panel, QPoint(0, panel.received.height())).y()
                self.assertLessEqual(source_bottom, controls_top)
                self.assertLessEqual(received_bottom, panel.height())
                self.assertGreaterEqual(panel.source.height(), 94)

    def test_language_change_does_not_mislabel_older_translation(self):
        self.translate("English words")
        self.assertTrue(self.window.panels["1"].received.toPlainText())
        self.window.panels["2"].set_code("ar")
        self.assertEqual(self.window.panels["1"].received.toPlainText(), "")
        self.assertEqual(len(self.window.conversation["turns"]), 1)

    def test_revision_clears_stale_output_while_pending_and_after_failure(self):
        turn = self.translate("Original words 50")
        identity, original = turn["id"], turn["raw_source"]
        turn["metadata"] = {key: turn[key] for key in ("review_text", "review_provider", "backtranslation", "backtranslation_provider")}
        self.window.turn_table.selectRow(0)
        self.service.hold = threading.Event()
        self.service.error = "Fixture failure after deliberate source revision"
        with patch.object(ui, "TurnDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.reviewed.toPlainText.return_value = "Reviewed words 500"
            self.window.review_selected_turn()
        self.assertEqual(turn["status"], "pending")
        self.assertEqual(turn["translated_text"], "")
        for key in ("review_text", "review_provider", "backtranslation", "backtranslation_provider"):
            self.assertEqual(turn[key], "")
            self.assertNotIn(key, turn["metadata"])
        self.assertEqual(self.window.panels["1"].received.toPlainText(), "")
        self.assertFalse(self.window.panels["1"].listen_button.isEnabled())
        self.service.hold.set()
        self.wait_idle()
        self.assertEqual(turn["status"], "failed")
        self.assertEqual(turn["translated_text"], "")
        self.assertEqual(turn["review_text"], "")
        self.assertEqual(turn["id"], identity)
        self.assertEqual(turn["raw_source"], original)
        self.assertEqual(turn["reviewed_source"], "Reviewed words 500")
        self.assertEqual(self.window.panels["1"].received.toPlainText(), "")

    def test_removing_last_provider_key_preserves_local_draft_work(self):
        settings = self.service.settings()
        settings["providers"]["azure"]["key"] = ""
        self.window._save_settings(settings)
        self.assertEqual(self.service.prefs["providers"]["azure"]["key"], "")
        self.assertFalse(self.window._has_provider())
        self.window.panels["1"].source.setPlainText("Local draft after removing all provider keys")
        self.assertTrue(self.window._save())
        saved = self.service.saved[self.window.conversation["id"]]
        self.assertEqual(saved["drafts"]["1"], "Local draft after removing all provider keys")
        self.assertFalse(self.service.requests)

    def test_explicit_optional_provider_choice_is_saved_with_inline_help(self):
        settings = self.service.settings()
        settings["provider"] = "deepl"
        self.window._save_settings(settings)
        self.assertEqual(self.service.prefs["provider"], "deepl")
        self.assertIn("DeepL selected", self.window.settings_pane.feedback.text())
        self.assertIn("API key", self.window.settings_pane.feedback.text())
        self.assertIn("free translation service", self.window.settings_pane.feedback.text())
        self.assertFalse(self.service.requests)

    def test_current_language_choices_survive_saving_stale_settings_pane(self):
        stale_settings = self.service.settings()
        self.window.panels["2"].set_code("ar")
        self.window._save_settings(stale_settings)
        self.assertEqual(self.service.prefs["source2"], "ar")
        self.assertEqual(self.window.preferences["source2"], "ar")
        self.window.new_conversation()
        self.assertEqual(self.window.panels["2"].code(), "ar")

    def test_screen_fit_includes_frame_and_first_use_settings_on_short_screen(self):
        available = QRect(0, 0, 960, 540)
        class ShortScreen:
            def availableGeometry(self):
                return available
        with patch.object(ui.MainWindow, "screen", return_value=ShortScreen()):
            self.window._fit_to_screen(center=True)
            self.window._show_settings(True)
            self.application.processEvents()
            self.assertLessEqual(self.window.width(), available.width() - 32)
            self.assertLessEqual(self.window.height(), available.height() - 48)
            self.assertTrue(available.contains(self.window.frameGeometry()))
            self.assertTrue(self.window.settings_dock.isVisible())
            self.assertGreaterEqual(self.window.settings_dock.width(), 340)
            self.assertFalse(self.window.settings_pane.apply.isVisible())
            self.assertTrue(self.window.settings_pane.theme.isVisible())
            self.assertEqual(self.window.settings_dock.widget().tabText(1), "Manual")
            for panel in self.window.panels.values():
                source_bottom = panel.source.mapTo(panel, QPoint(0, panel.source.height())).y()
                button_top = panel.translate_button.mapTo(panel, QPoint(0, 0)).y()
                self.assertLessEqual(source_bottom, button_top)

    def _open_without_keys(self):
        self.window.close()
        self.service.prefs.update(provider="auto", speech_provider="auto", speech_key="", speech_region="")
        for entry in self.service.prefs["providers"].values():
            entry["key"] = ""
        self.window = ui.MainWindow(self.service)
        self.window.show()
        self.application.processEvents()
        QTest.qWait(180)

    def test_no_key_first_use_has_enabled_record_without_setup_drawer(self):
        self._open_without_keys()
        self.assertFalse(self.window.settings_dock.isVisible())
        self.assertFalse(self.window.notice.isVisible())
        self.assertIn("Free translation", self.window.status_detail.text())
        self.assertTrue(self.window.panels["1"].record_button.isEnabled())

    def test_real_record_button_click_without_keys_starts_worker_and_stop_commits(self):
        self._open_without_keys()
        panel = self.window.panels["1"]
        panel.source.setPlainText("Typed words stay")
        panel.record_button.click()
        deadline = time.monotonic() + 1
        while not self.service.recognition_requests and time.monotonic() < deadline:
            self.application.processEvents()
            QTest.qWait(5)
        self.assertEqual(len(self.service.recognition_requests), 1)
        self.assertEqual(self.service.recognition_requests[0][0], "en")
        self.assertIsNotNone(self.window.recording_token)
        self.assertIn("Recording", self.window.status_heading.text())
        self.assertIn("Stop", panel.record_button.text())
        panel.record_button.click()
        self.assertTrue(self.service.recognition_requests[0][1].is_set())
        self.assertFalse(self.service.recognition_requests[0][1].abort_event.is_set())
        self.wait_idle()
        self.assertEqual(panel.source.toPlainText(), "Typed words stay\nTEST RECOGNIZED WORDS")
        self.assertFalse(self.window.recording_timer.isActive())
        self.assertEqual(panel.record_button.text(), "Record Speech")
        self.assertEqual(self.service.requests[-1][0], panel.source.toPlainText())
        self.assertEqual(self.service.recognition_uploads, ["en"])

    def _start_record_fixture(self):
        self._open_without_keys()
        panel = self.window.panels["1"]
        panel.source.setPlainText("Keep this typed draft")
        panel.record_button.click()
        deadline = time.monotonic() + 1
        while not self.service.recognition_requests and time.monotonic() < deadline:
            self.application.processEvents()
            QTest.qWait(5)
        self.assertEqual(len(self.service.recognition_requests), 1)
        return self.service.recognition_requests[0][1]

    def test_escape_aborts_recording_before_fixture_asr_upload(self):
        event = self._start_record_fixture()
        self.window.activateWindow()
        self.window.panels["1"].source.setFocus()
        self.application.processEvents()
        QTest.keyClick(self.window.panels["1"].source, Qt.Key.Key_Escape)
        self.wait_idle()
        self.assertTrue(event.is_set())
        self.assertTrue(event.abort_event.is_set())
        self.assertEqual(self.service.recognition_uploads, [])
        self.assertEqual(self.window.panels["1"].source.toPlainText(), "Keep this typed draft")
        self.assertEqual(self.window.status_heading.text(), "Task cancelled")

    def test_cancel_button_aborts_recording_before_fixture_asr_upload(self):
        event = self._start_record_fixture()
        self.window.cancel_button.click()
        self.wait_idle()
        self.assertTrue(event.is_set())
        self.assertTrue(event.abort_event.is_set())
        self.assertEqual(self.service.recognition_uploads, [])
        self.assertEqual(self.window.panels["1"].source.toPlainText(), "Keep this typed draft")

    def test_dictation_provider_warning_and_capture_metadata_remain_visible(self):
        self.service.recognition_result.update(provider="offline", warnings=["Fixture fallback: online recognition was unavailable."])
        event = self._start_record_fixture()
        self.window.panels["1"].record_button.click()
        self.wait_idle()
        self.assertFalse(event.abort_event.is_set())
        self.assertEqual(self.window.conversation["turns"][-1]["dictation"]["provider"], "offline")
        turn = self.window.conversation["turns"][-1]
        self.assertIn("Recognized with Offline recognition", self.window.panels["1"].capability_note.text())
        self.assertTrue(any("online recognition was unavailable" in message for message in turn["warnings"]))
        self.assertFalse(ui.review_messages(turn, playback=True))
        capture = self.service.saved[self.window.conversation["id"]]["metadata"]["last_dictation"]["1"]
        self.assertEqual(capture["provider"], "offline")
        self.assertTrue(capture["complete"])
        self.assertEqual(capture["duration_ms"], 1250)

    def test_no_key_microphone_failure_is_visible_and_preserves_draft(self):
        self._open_without_keys()
        self.service.recognition_error = "Fixture microphone access failed"
        panel = self.window.panels["1"]
        panel.source.setPlainText("Preserved before microphone failure")
        panel.record_button.click()
        self.wait_idle()
        self.assertIn("microphone access failed", self.window.notice.text())
        self.assertTrue(self.window.notice.isVisible())
        self.assertEqual(panel.source.toPlainText(), "Preserved before microphone failure")
        self.assertIsNone(self.window.recording_token)
        self.assertTrue(panel.record_button.isEnabled())

    def test_free_provider_choices_save_without_api_credentials(self):
        self._open_without_keys()
        pane = self.window.settings_pane
        for provider in ("auto", "google_web", "bing_web", "mymemory"):
            self.assertGreaterEqual(pane.provider.findData(provider), 0)
        self.assertEqual(pane.provider.findData("lingva"), -1)
        self.assertTrue(pane.tabs.isHidden())
        self.assertEqual(pane.speech_provider.currentData(), "auto")
        self.assertFalse(pane.speech_key.isEnabled())
        settings = self.service.settings()
        settings["provider"] = "google_web"
        self.window._save_settings(settings)
        self.assertEqual(self.service.prefs["provider"], "google_web")


class FreeSettingsMigrationTests(unittest.TestCase):
    def test_new_defaults_and_legacy_blank_key_choices_are_usable(self):
        import settings
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary:
            path = Path(temporary) / "settings.json"
            fresh = settings.Settings(path).get()
            self.assertEqual(fresh["provider"], "auto")
            self.assertEqual(fresh["speech_provider"], "auto")
            self.assertTrue(fresh["reinforce"])
            self.assertTrue(fresh["backtranslate"])
            self.assertTrue(fresh["free_fallback"])
            path.write_text(json.dumps({"version": 1, "settings": {"provider": "azure", "speech_provider": "azure", "reinforce": False, "backtranslate": False}, "credentials": ""}), encoding="utf8")
            reopened = settings.Settings(path).get()
            self.assertEqual(reopened["provider"], "auto")
            self.assertEqual(reopened["speech_provider"], "auto")
            self.assertTrue(reopened["reinforce"])
            self.assertTrue(reopened["backtranslate"])

    def test_current_explicit_review_preference_is_preserved(self):
        import settings
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text(json.dumps({"version": 1, "settings": {"provider": "auto", "reinforce": False, "backtranslate": False, "free_fallback": True}, "credentials": ""}), encoding="utf8")
            reopened = settings.Settings(path).get()
            self.assertFalse(reopened["reinforce"])
            self.assertFalse(reopened["backtranslate"])

    def test_decrypted_optional_credentials_keep_explicit_provider_selection(self):
        import settings
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary:
            path = Path(temporary) / "settings.json"
            saved = settings.Settings(path)
            saved.save({"provider": "azure", "speech_provider": "azure", "speech_key": "test-speech-fixture", "providers": {"azure": {"key": "test-translation-fixture"}}})
            reopened = settings.Settings(path).get()
            self.assertEqual(reopened["provider"], "azure")
            self.assertEqual(reopened["speech_provider"], "azure")


if __name__ == "__main__":
    unittest.main(verbosity=2)
