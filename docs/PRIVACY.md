# Data and privacy

## Keep your sessions

- Data folder: `GrayFeather-data` beside the executable, unless you set `--data-dir`.
- Upgrade: close Gray Feather, keep that folder, extract the new release, then restore the folder beside the new executable.
- Backup: use **Back up history**. Automatic backups retain the latest two copies.
- Restore: close the app; preserve the current folder; replace `conversations.sqlite3` with a verified backup. Keep `settings.json`.

Backups may retain conversations removed from the active database. Optional credentials are separate from database-only backups. Windows DPAPI credentials may need re-entry on another account or computer. Local history and exported documents are not encrypted by this app.

## Know what leaves the PC

| Action | Data handling |
| --- | --- |
| Automatic online translation / additional opinions | Source text and applicable requested context go to eligible services. |
| Online dictation and its previews | Audio goes to the recognition service. |
| Online voice / automatic reading | Translated text goes to the selected speech service; bounded reserves may prepare it too. |
| Explicit offline translation / offline speech route | That operation runs locally. Unsupported offline languages remain unsupported. |
| History and export | Stored locally; exporting does not upload the document. |

Changing translation to offline does not automatically change recognition or playback. Choose each engine separately if every stage must remain local. Working audio is temporary and is not retained as conversation history. No telemetry, account, background updater or automatic model download is included.

When reporting a problem, remove personal text, recordings, credentials and local paths from attachments. Start with version, language pair, selected engines and a synthetic reproduction.
