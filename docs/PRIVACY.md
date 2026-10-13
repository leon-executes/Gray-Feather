# Data and privacy

## Keep your sessions

- Data folder: `GrayFeather-data` beside the executable, unless you set `--data-dir`.
- Upgrade: close Gray Feather, keep that folder, extract the new release, then restore the folder beside the new executable.
- Backup: use **Back up history**. Automatic backups retain the latest two copies.
- Restore: close the app; preserve the current folder; replace `conversations.sqlite3` with a verified backup. Keep `settings.json`.

Backups may retain conversations removed from the active database. Optional credentials are separate from database-only backups. Windows DPAPI credentials may need re-entry on another account or computer. Local history and exported documents are not encrypted by this app.

## Delete or shred

In **Saved sessions**, check the boxes and press **Delete selected**. Checked sessions stay selected through search and refresh; the confirmation includes any hidden selection. Ordinary deletion keeps backups.

**Shred History** asks for confirmation, then purges all sessions, drafts and revisions with SQLite secure deletion and compaction. It overwrites and removes the app-managed `backups/latest.sqlite3`, `previous.sqlite3` and `next.sqlite3` files, including interrupted automatic-backup staging files, and clears the open session. Settings remain. Any purge failure is reported so you can retry.

There is no in-app Undo. This is not a guarantee of forensic erasure: SSD wear levelling, filesystem snapshots, operating-system copies and separate backups/exports may retain data. Other extracted copies of the app have separate data folders and are not touched.

## Know what leaves the PC

| Action | Data handling |
| --- | --- |
| Automatic online translation / additional opinions | Source text and applicable requested context go to eligible services. |
| Online dictation and its previews | Audio goes to the recognition service. |
| Online voice / automatic reading | Translated text goes to the selected speech service; bounded reserves may prepare it too. |
| Offline speech | Supported bundled dictation and voices run locally. Text translation requires internet. |
| History and export | Stored locally; exporting does not upload the document. |

Recognition and playback have separate engine choices. Supported offline speech routes keep that stage local; text translation requires internet. Working audio is temporary and is not retained as conversation history. No telemetry, account, background updater or automatic model download is included.

When reporting a problem, remove personal text, recordings, credentials and local paths from attachments. Start with version, language pair, selected engines and a synthetic reproduction.
