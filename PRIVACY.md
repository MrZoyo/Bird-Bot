# Privacy and Data Handling

This document describes what Bird Bot stores, why it stores it, and how an
operator should protect it. Bird Bot is self-hosted: data is stored in the
operator's local SQLite database and local log/backup files, not in a hosted
service controlled by this repository.

## Discord Privileged Intents

Bird Bot requests only the gateway intents it currently needs:

- `Guild Members`: welcome messages, member-count display, role-based ticket admin expansion, and member objects selected in slash commands.
- `Message Content`: team-up keyword detection and message-count achievements.
- `Voice States`: temporary voice rooms, voice-time achievements, private-room eligibility, and voice status commands.
- `Guild Messages` and `Guild Reactions`: message/reaction achievements, panels, and interaction recovery.

Bird Bot does not request `Guild Presences`. It does not use online/offline
status, activities, platform information, or rich presence data.

Discord's privileged-intent review guide lists `Guild Presences`, `Guild
Members`, and `Message Content` as privileged intents, and says these intents
are disabled by default because of the data they grant. Operators should enable
only the two privileged intents Bird Bot uses: Server Members Intent and
Message Content Intent.

Reference: https://docs.discord.com/developers/gateway/getting-started-with-privileged-intent-review

## Stored Data

The bot stores Discord snowflake IDs and feature state required to restore
panels, track progress, and continue scheduled tasks after restart.

- Voice rooms: temporary voice channel IDs, creator user IDs, control-panel message IDs, room type, soundboard state, and timestamps.
- Team-up display: user IDs, source channel IDs, voice channel IDs, short team-up message content, player count, game type, invitation message IDs, and expiration timestamps.
- Achievements: user IDs, message/reaction counts, voice time, monthly counters, active voice sessions, and manual admin operation records.
- Shop and check-in: user IDs, point balances, transaction records, check-in dates, streaks, makeup check-in state, and check-in panel message IDs.
- Private rooms: owner user IDs, private-room channel/category IDs, start/end dates, status flags, and shop panel message IDs.
- Tickets: thread IDs, ticket creator IDs, type names, ticket numbers, member IDs added to the ticket, accept/close state, and close reasons.
- Role and signature features: persistent role panel message IDs, user IDs, user-provided signatures, signature change timestamps, and signature-disable flags.
- Ban features: user IDs, guild IDs, moderator IDs, ban reasons, unban timestamps, active/inactive state, and Discord delete-message-day setting.
- Giveaways: giveaway IDs, channel/message IDs, creator IDs, prize/description text, participant IDs, winner IDs, requirements, and end state.
- Check-status samples: timestamped aggregate voice counts and active channel counts.
- Config tables: feature setup state such as ticket types, voice-channel rules, game-type mapping, and panel message locations.

The bot does not intentionally store Discord access tokens in the database.
Bot tokens and runtime configuration live in ignored local YAML files under
`bot/config/*.yaml`.

## Logs and Backups

Runtime logs are local files configured in `main.yaml`:

- Main bot log.
- Keyword detection log.
- Room activity log.

Logs identify Discord entities with names and IDs so server operators can
debug moderation and room-management issues. The log retention count is
controlled by `log_backup_count`.

`BackupCog` copies the SQLite database every 6 hours and keeps the latest 20
automatic backups, plus manual backups created through `/backup_now`. If
database encryption is enabled, these backups remain encrypted because they
are byte-for-byte copies of the encrypted database file.

## Database Encryption

Bird Bot uses SQLCipher-backed at-rest encryption for the SQLite database when
a key is configured. The runtime key must come from the environment, not YAML:

- `DCGSH_DB_KEY`: passphrase used by SQLCipher.
- `DCGSH_DB_KEY_FILE`: path to a file containing the passphrase.
- `DCGSH_DB_CREATE_KEY_FILE=1`: generate `DCGSH_DB_KEY_FILE` once if it
  does not exist.
- `DCGSH_DB_REQUIRE_ENCRYPTION=1`: fail startup if no key is configured.

When a key is configured, all runtime database managers open SQLite through
`bot.utils.db_connect.connect_database()`, which applies `PRAGMA key` and
verifies that the database is readable before feature SQL runs.

To encrypt an existing plaintext database:

```bash
export DCGSH_DB_KEY_FILE='/secure/bird-bot/db.key'
export DCGSH_DB_CREATE_KEY_FILE=1
python tools/encrypt_database.py data/bot.db data/bot.encrypted.db \
  --backup-source backup/db_backup_manual/plain-before-encryption.db
mv data/bot.encrypted.db data/bot.db
unset DCGSH_DB_CREATE_KEY_FILE
export DCGSH_DB_REQUIRE_ENCRYPTION=1
```

For PowerShell:

```powershell
$env:DCGSH_DB_KEY_FILE = 'C:\secure\bird-bot\db.key'
$env:DCGSH_DB_CREATE_KEY_FILE = '1'
python tools/encrypt_database.py data/bot.db data/bot.encrypted.db --backup-source backup/db_backup_manual/plain-before-encryption.db
Move-Item -Force data/bot.encrypted.db data/bot.db
Remove-Item Env:DCGSH_DB_CREATE_KEY_FILE
$env:DCGSH_DB_REQUIRE_ENCRYPTION = '1'
```

The plaintext backup created during migration is sensitive. Move it to an
offline encrypted backup location or delete it after validating the encrypted
database.

The generated key file is also sensitive. Keep a secure offline copy; if the
key is lost, existing encrypted database and backup files cannot be decrypted.

## Retention and Deletion

- Team-up invitations expire after the configured runtime window; the current runtime default is 5 minutes.
- Temporary voice room rows are removed when the managed channel no longer exists.
- Inactive temporary ban records can be cleaned by the ban database cleanup path; active records are kept until unban handling completes.
- Logs rotate according to `log_backup_count`.
- Automatic DB backups keep the latest 20 backup files per backup directory.
- User signatures can be cleared by an administrator through the role/signature tools.
- Other feature data is retained while the feature needs it for auditability, rankings, restore-after-restart behavior, or moderation history. Operators can remove data manually from the SQLite database after backing it up.

## Operator Checklist

- Enable only the required privileged intents in the Discord Developer Portal: Server Members Intent and Message Content Intent.
- Do not enable Presence Intent unless a future feature explicitly needs presence data and this document is updated.
- Keep `bot/config/*.yaml`, `.env` files, `data/*.db`, backup files, and logs out of git.
- Set `DCGSH_DB_REQUIRE_ENCRYPTION=1` in production after migrating the database.
- Store `DCGSH_DB_KEY` in the host secret manager, or store `DCGSH_DB_KEY_FILE` outside the repo with restricted permissions.
- Use `DCGSH_DB_CREATE_KEY_FILE=1` only for first-run key-file generation, then remove it.
- Do not paste bot tokens, DB keys, full logs, or plaintext database dumps into support channels.
- Test migrations on a copy of the database before replacing production `data/bot.db`.
