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


class HistoryDeletionTests(unittest.TestCase):
    setUpClass = GuiStorageIntegrationTests.__dict__['setUpClass']
    setUp = GuiStorageIntegrationTests.setUp
    tearDown = GuiStorageIntegrationTests.tearDown
    wait = GuiStorageIntegrationTests.wait
    translate = GuiStorageIntegrationTests.translate
    # Use the real UI/service/database with synthetic data only.
    def seed(self):
        self.translate("Private history marker 839147")
        first = self.window.conversation['id']
        self.window.new_conversation()
        self.translate("Keep this separate session")
        return first, self.window.conversation['id']

    def check(self, identities):
        from PySide6.QtCore import Qt
        for i in range(self.window.history_list.count()):
            item = self.window.history_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) in identities:
                item.setCheckState(Qt.CheckState.Checked)

    def confirm_shred(self, accept=True):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        def click(box):
            if accept:
                next(b for b in box.buttons() if b.text() == 'Shred History').click()
            else:
                box.button(QMessageBox.StandardButton.Cancel).click()
        with patch.object(QMessageBox, 'exec', click):
            self.window.shred_history()

    def test_checks_survive_refresh_and_search_and_delete_only_checked(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        first, second = self.seed()
        self.check([first])
        self.window.history_search.setText('no matching session')
        self.window._refresh_history()
        self.assertEqual(len(self.window._checked_history_items()), 1)
        self.assertIn('(1)', self.window.delete_history_button.text())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes) as confirm:
            self.window.delete_history()
        self.assertIn('hidden', confirm.call_args.args[2])
        self.assertEqual([x['id'] for x in self.service.list_conversations()], [second])
        self.assertFalse(self.window.delete_history_button.isEnabled())

    def test_multi_delete_current_does_not_resave_deleted_drafts(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        first, second = self.seed()
        self.window.panels['1'].source.setPlainText('An unsaved draft')
        self.check([first, second])
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.window.delete_history()
        self.window._save()
        self.assertEqual(self.service.list_conversations(), [])
        self.assertEqual(self.window.panels['1'].source.toPlainText(), '')

    def test_multi_delete_missing_member_rolls_back_entire_selection(self):
        first, second = self.seed()
        with self.assertRaises(Exception):
            self.service.delete_conversations([first, 'missing-id', second])
        self.assertEqual(len(self.service.list_conversations()), 2)

    def test_cancel_deletion_and_shred_preserve_sessions(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        first, second = self.seed()
        self.check([first, second])
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            self.window.delete_history()
        self.confirm_shred(False)
        self.assertEqual(len(self.service.list_conversations()), 2)

    def test_shred_purges_revisions_backups_and_ui_but_keeps_settings_and_exports(self):
        import sqlite3
        from contextlib import closing
        first, second = self.seed()
        settings_before = self.service.settings()
        root = Path(self.temp.name)
        for name in ('latest.sqlite3', 'previous.sqlite3', 'next.sqlite3'):
            self.service.store.backup(root/'backups'/name)
        (root/'backups/.next.sqlite3.synthetic.tmp').write_bytes(b'Interrupted automatic backup with private history')
        exported = root/'my-export.sqlite3'
        self.service.store.backup(exported)
        self.window.panels['1'].source.setPlainText('Pending draft to purge')
        self.confirm_shred()
        self.window._save()
        self.service.shutdown()
        self.assertEqual(self.service.list_conversations(), [])
        self.assertFalse(self.window.draft_timer.isActive())
        self.assertIsNone(self.window.undo_snapshot)
        self.assertEqual(self.window.panels['1'].source.toPlainText(), '')
        self.assertEqual(self.window.panels['1'].received.toPlainText(), '')
        self.assertEqual(list((root/'backups').iterdir()), [])
        self.assertTrue(exported.exists())
        self.assertEqual(self.service.settings(), settings_before)
        with closing(sqlite3.connect(self.service.store.path)) as db:
            for table in ('conversations', 'turns', 'turn_revisions'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertNotIn(b'Private history marker 839147', self.service.store.path.read_bytes())
        self.assertFalse(Path(str(self.service.store.path)+'-journal').exists())
        reopened = Service(root)
        self.assertEqual(reopened.list_conversations(), [])
        reopened.shutdown()

    def test_compaction_failure_still_clears_ui_and_allows_retry_and_new_session(self):
        import sqlite3
        from unittest.mock import patch
        self.seed()
        original = self.service.store._connection
        def fail_compaction(write=False):
            if not write:
                raise sqlite3.OperationalError('Synthetic compaction failure')
            return original(write=write)
        with patch.object(self.service.store, '_connection', fail_compaction), patch.object(self.window, '_show_error') as error:
            self.confirm_shred()
        self.assertTrue(error.called)
        self.window._save()
        self.assertEqual(self.service.list_conversations(), [])
        self.confirm_shred()
        self.translate('New session after purge')
        self.assertEqual(len(self.service.list_conversations()), 1)

    def test_partial_backup_failure_is_reported_without_resurrecting_history(self):
        from unittest.mock import patch
        self.seed()
        root = Path(self.temp.name)
        target = root/'backups/latest.sqlite3'
        self.service.store.backup(target)
        real_open = Path.open
        def fail_backup(path, *args, **kwargs):
            if path == target and args and args[0] == 'r+b':
                raise PermissionError('Synthetic locked backup')
            return real_open(path, *args, **kwargs)
        with patch.object(Path, 'open', fail_backup), patch.object(self.window, '_show_error') as error:
            self.confirm_shred()
        self.assertIn('latest.sqlite3', error.call_args.args[0])
        self.window._save()
        self.assertEqual(self.service.list_conversations(), [])
        self.assertTrue(target.exists())
        self.confirm_shred()
        self.assertFalse(target.exists())

    def test_late_job_result_cannot_repopulate_shredded_session(self):
        import threading
        self.seed()
        self.window.jobs['synthetic-late-job'] = (None, threading.Event())
        self.confirm_shred()
        self.window._deliver_callback('synthetic-late-job', lambda _: self.window.panels['1'].source.setPlainText('Resurrected'), None)
        self.window._job_finished('synthetic-late-job')
        self.window._save()
        self.assertEqual(self.service.list_conversations(), [])
        self.assertEqual(self.window.panels['1'].source.toPlainText(), '')

    def test_backup_publication_and_purge_are_serialized(self):
        import threading
        from unittest.mock import patch
        self.seed()
        entered, release, purge_done = threading.Event(), threading.Event(), threading.Event()
        backup_path = Path(self.temp.name)/'backups/latest.sqlite3'
        real_backup = self.service.store.backup
        errors = []
        def blocked_backup(path):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('Test release timed out')
            return real_backup(path)
        def run_backup():
            try: self.service.backup_history(backup_path)
            except Exception as exc: errors.append(exc)
        def run_purge():
            try: self.service.shred_history()
            except Exception as exc: errors.append(exc)
            finally: purge_done.set()
        with patch.object(self.service.store, 'backup', blocked_backup):
            backup = threading.Thread(target=run_backup)
            purge = threading.Thread(target=run_purge)
            backup.start()
            try:
                self.assertTrue(entered.wait(2))
                purge.start()
                self.assertFalse(purge_done.wait(.05))
            finally:
                release.set()
                backup.join(3)
                if purge.ident is not None: purge.join(3)
        self.assertFalse(errors)
        self.assertTrue(purge_done.is_set())
        self.assertFalse(backup_path.exists())
        self.window._load_conversation(self.window._empty_conversation())

    def test_legacy_database_upgrade_keeps_originals_and_drafts(self):
        import sqlite3
        from contextlib import closing
        first, second = self.seed()
        before = self.service.load_conversation(first)
        with closing(sqlite3.connect(self.service.store.path)) as db:
            db.execute('ALTER TABLE turns DROP COLUMN deleted')
            db.commit()
        reopened = Service(Path(self.temp.name))
        after = reopened.load_conversation(first)
        self.assertEqual(after['drafts'], before['drafts'])
        self.assertEqual(after['turns'][0]['raw_source'], before['turns'][0]['raw_source'])
        self.assertEqual(after['turns'][0]['translated_text'], before['turns'][0]['translated_text'])
        self.assertEqual(len(reopened.list_conversations()), 2)
        reopened.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
