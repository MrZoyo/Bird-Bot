# DCGameServerHelper Developer Guide

This file is the detailed project guide for coding agents and maintainers. `AGENTS.md` is intentionally short and points here.

## Agent Workflow

- Read this file first, then inspect the code relevant to the current task.
- For manual feature testing, follow `REFACTORING_TEST_CHECKLIST.md`.
- For refactor state and historical decisions, consult `REFACTORING_PROGRESS.md` and `REFACTORING_PLAN.md`.
- When the user asks to continue, fix, refactor, or test, execute directly. Ask only when the requirement is genuinely ambiguous or risky.
- Communicate with the user in Chinese. Keep command, path, and log excerpts concise, and do not expose secrets.
- Per user preference, environment validation, imports, compile checks, tests, `uv`, and dependency checks should be run outside the sandbox with approval/escalation. If the venv is missing packages, install/sync them as part of the task.

## Project Overview

DCGameServerHelper is a Discord bot built on `discord.py`. It uses a modular cog architecture, YAML runtime configuration, locale YAML files for user-facing text, and SQLite for persistent state.

The current refactor target is config 2.0 and package-based cogs. Legacy JSON config files and removed cogs are historical inputs only; the runtime path is YAML + package cogs.

## Repository Structure

- `run.py`: launcher; imports `bot.main.run_bot()`.
- `bot/main.py`: bot factory, `COG_SPECS`, setup hook, cog loading, logging setup, command sync.
- `bot/cogs/`: active feature packages. Each active cog is a package, not a flat `*_cog.py` module.
- `bot/utils/`: shared helpers, config loader, DB managers, i18n, path helpers, logging format helpers.
- `bot/config/*.yaml.example`: public templates. Operators copy these to `*.yaml`.
- `bot/config/*.yaml`: real local runtime config, gitignored and sensitive.
- `bot/locales/<lang>/<cog>.yaml`: locale files loaded through `bot.utils.i18n.t()`.
- `tools/`: migration, locale check, DB seed, and maintenance scripts.
- `tests/`: pytest smoke coverage for offline-verifiable behavior.
- `data/bot.db`: default local SQLite database, gitignored.
- `backup/`: database backups.
- `.cache/`: local scratch/backup output, not for commits.

## Active Cogs

`bot/main.py::COG_SPECS` is the source of truth. Current active cogs:

- `VoiceStateCog` in `bot.cogs.voice_channel`
- `WelcomeCog` in `bot.cogs.welcome`
- `CreateInvitationCog` in `bot.cogs.create_invitation`
- `DnDCog` in `bot.cogs.games.dnd`
- `CheckStatusCog` in `bot.cogs.check_status`
- `AchievementCog` in `bot.cogs.achievement`
- `SpyModeCog` in `bot.cogs.games.spymode`
- `GiveawayCog` in `bot.cogs.giveaway`
- `RoleCog` in `bot.cogs.role`
- `BackupCog` in `bot.cogs.backup`
- `TicketsCog` in `bot.cogs.tickets`
- `ShopCog` in `bot.cogs.shop`
- `PrivateRoomCog` in `bot.cogs.privateroom`
- `BanCog` in `bot.cogs.ban`
- `TeamupDisplayCog` in `bot.cogs.teamup_display`

NotebookCog, RatingCog, and the old channel-based TicketsCog are removed from runtime. Do not reintroduce tests or active docs for removed cogs unless the user explicitly asks to restore them.

## Configuration

Runtime config is YAML:

- `main.yaml`: token, guild, database path, log paths, locale, feature flags.
- Per-feature YAML files: `voicechannel.yaml`, `tickets.yaml`, `shop.yaml`, etc.
- `Config` in `bot/utils/config.py` loads `bot/config/<name>.yaml`, caches it, validates `main`, and normalizes runtime paths from repo root.
- Relative paths such as `./data/bot.db` resolve from the repository root, not the process CWD.
- Keep both `.yaml.example` templates and local real YAML commented. Comments should explain units, Discord ID targets, DB/locale ownership, and whether a key is currently read by runtime code.
- Known config follow-up: signature change cooldown is still hard-coded to 7 days in `RoleDatabaseManager`, and teamup invitation expiry is still hard-coded to 5 minutes in `TeamupDisplayManager`; P3-10 tracks making both configurable while preserving those defaults.

Legacy JSON:

- `tools/migrate_config_to_yaml.py` migrates old `config_*.json` into YAML/locale/DB seed outputs.
- `config_tickets_new.json` maps to the current `tickets` target.
- `config_tickets.json` and `config_rating.json` are deprecated source files and are skipped.
- `tools/seed_db.py` loads migrated DB-bound maps into SQLite: `voicechannel.channel_configs` and `tickets.ticket_types`.

Never commit real YAML configs, real JSON configs, `tools/migration_db_seed.json`, or `tools/migration_report.md`.

## Locale And Text

- User-facing text should live in `bot/locales/zh_CN/<cog>.yaml`.
- Code reads text with `bot.utils.i18n.t("cog.key")`.
- Slash command names/descriptions use locale keys under `bot/locales/zh_CN/commands.yaml`.
- Run `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py` after adding or moving locale keys.
- `welcome_text` is the current explicit exception: it may embed real Discord URLs/custom emoji IDs, so it remains in ignored `welcome.yaml` and has a sanitized `.yaml.example` form.
- Welcome DM copy, Shop modal labels, PrivateRoom modal labels, and Achievement rank UI text are locale-backed. Their YAML config should only carry runtime data such as IDs, colours, image paths, prices, limits, and time formats.
- `/rank` category buttons use the Discord Button `emoji` field for colored circles; keep the canonical mapping in `bot/cogs/achievement/rank_locale.py` and strip any locale emoji prefix before assigning the button label. Do not keep or regenerate `rank:` UI text in `bot/config/achievements.yaml`.
- Achievement definitions, role pick-up option names, and ranking type names remain YAML content metadata because they are coupled to thresholds, type ids, and role ids. Treat these as content/config data, not generic UI chrome.

## Database

- Main DB path comes from `main.db_path`, usually `data/bot.db`.
- All runtime SQLite connections must go through `bot.utils.db_connect.connect_database()` so SQLCipher encryption is applied consistently when `DCGSH_DB_KEY` or `DCGSH_DB_KEY_FILE` is set.
- Production encrypted deployments should set `DCGSH_DB_REQUIRE_ENCRYPTION=1`; keys must stay in environment/secret files, never YAML, logs, docs, or git.
- First-run key generation is explicit only: set `DCGSH_DB_KEY_FILE=/secure/path/db.key` and `DCGSH_DB_CREATE_KEY_FILE=1`; after the file is created, keep and back up that file securely and remove the create flag so a missing key fails loudly.
- Existing plaintext databases are migrated with `tools/encrypt_database.py`; back up the plaintext source first and protect or delete that plaintext backup after validation.
- Use feature DB managers in `bot/utils/*_db.py`; do not put raw SQL in cogs unless there is already an established local exception.
- Several managers use persistent async connections. If a one-shot script creates one, close it explicitly before exiting.
- DB schema migrations use `bot/utils/schema_migrations.py` where needed.
- Before touching the local or production DB, back it up.
- PrivateRoom renewal semantics: a normal renewal extends from the current `end_date`; a stale active room whose `end_date` is already in the past extends from the current time, so a user is never charged for days that have already elapsed.

## Logging Rule

All bot logs should identify Discord entities with both name and id:

- Users/members: `display_name / username (id)` via `bot.utils.fmt_user` when nickname/display name and username differ; `display_name (id)` when they are identical.
- Channels/threads: `name (id)` via `bot.utils.fmt_channel`.
- Roles: `name (id)` via `bot.utils.fmt_role`.
- Guilds: `name (id)` via `bot.utils.fmt_guild`.
- If only a raw id is available, log `unknown (id)`.
- Numeric ids must use ASCII parentheses: `(1234567890)`, not `（1234567890）`.

This applies to root logs, `keyword_detection`, `room_activity`, cog logs, DB manager warnings, and future maintenance scripts. Do not log only a bare username, channel name, mention, or id when a Discord object is available.

## Team Invitation Full-State UI

The "room full" state for team invitation messages has one shared implementation:

- Use `bot.cogs.create_invitation.full_message.update_invitation_message_to_full()`.
- The group-channel full button and the room control panel full button must call the shared helper.
- Full state should use the `invitation.roomfull_title` and `invitation.invite_embed_content_edited` locale keys, red embed color, preserved fields/thumbnail, no stale footer/timestamp, and no buttons.

Do not fork a second full-message formatting path in another cog.

## Discord Interaction Tests

Prefer local fake / fixture tests for Discord interaction handlers before adding more manual test-server steps:

- Fake only the attributes and methods a handler actually uses, such as `interaction.user`, `followup.send`, `response.defer`, channel/message `send` or `edit`, and DB manager calls.
- Assert interaction responses, embed/view output, DB side effects, and ordering of critical operations.
- Do not use user tokens, selfbot behavior, or a second bot as the primary slash/button/modal automation strategy.
- Keep real staging guild E2E tests for behavior that needs Discord itself: permissions, command sync, persistent views after restart, rate limits, DM delivery, and client-visible UI.
- PrivateRoom renewal flow tests must preserve the current rule: write and read back the persisted `end_date` before charging or sending success notifications.

## Development Commands

Use the project venv. On this machine the working interpreter is:

```bash
./.venv/Scripts/python.exe
```

Common checks:

```bash
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check bot tests tools
./.venv/Scripts/python.exe -m compileall bot tests tools
./.venv/Scripts/python.exe -X utf8 tools/check_locales.py
./.venv/Scripts/python.exe -m pip check
uv lock --check
uv sync --frozen --dry-run --extra test --extra lint --python 3.12.3
```

## Testing Strategy

Current pytest smoke coverage includes:

- Config templates and runtime cog metadata.
- Locale key integrity.
- Log helper formatting.
- Static logging callsite scan for obvious raw Discord `.id` / `.name` / `.display_name` usage.
- UI metadata smoke for locale-backed Shop, PrivateRoom, Welcome DM, Achievement rank controls, and Components v2 panels.
- Ban fake interaction flow for tempban permission, duplicate-active checks, Discord ban failure, DB record, scheduling, and notification ordering.
- Shop fake interaction flow for daily check-in and makeup check-in modal charging order.
- Modal text inputs target discord.py 2.7.1+: wrap inputs with `discord.ui.Label` instead of using deprecated `discord.ui.TextInput(label=...)`.
- Tickets fake interaction flow for confirmation modal, ticket creation, accept, and close handler ordering.
- PrivateRoom renewal date calculation, including stale active rooms left behind when the daily expiration task did not run.
- PrivateRoom fake interaction renewal flow, including persisted `end_date` readback before charging and failure without charge when DB readback is still expired.
- VoiceChannel fake interaction flow for Lock / Unlock / Soundboard / Full control-panel buttons.
- Giveaway fake interaction flow for join / leave / cancel / early end ordering.
- Role / Signature fake interaction flow for achievement role pickup and signature modal writes.
- Achievement / Rank fake interaction flow for manual operation confirmation and rank type buttons.
- Welcome / Games fake interaction flow for Welcome DM, SpyMode, and DnD roll response.
- CheckStatus / Backup fake interaction flow for Where Is, voice status, log tail, and manual backup.
- Temporary JSON-to-YAML migration smoke.
- Background loop offline guard.
- Offline DB manager smoke for retained modules.
- Shared team invitation full-state formatting for legacy embed messages and Components v2 panels.
- Explicit gateway-intent selection, SQLCipher database encryption helpers, and first-run DB key-file generation.
- Feature-linked achievement visibility: if `main.features.shop` is false, `checkin_sum` / `checkin_combo` disappear from achievement displays, rank buttons, and Role achievement pickup. Giveaway achievement categories are retired and remain hidden even when GiveawayCog is enabled.

Current P3-9 status:

- Done: current fake interaction flow list is complete for PrivateRoom, Shop, Tickets, Ban, VoiceChannel, Giveaway, Role / Signature, Achievement / Rank, Welcome / Games, CheckStatus / Backup.
- Current baseline: `93 passed, 1 warning`.
- Next default target: full automatic gate, then real test-server validation.
- Add more fake interaction tests only for new bugs, payload replay work, or new features.

Real Discord behavior still needs test-server validation for slash commands, permission failures, persistent views, buttons, Discord rate limits, DMs, command sync, and UI screenshots/logs where relevant. Follow `REFACTORING_TEST_CHECKLIST.md`.

## Refactor And Safety Rules

- Prefer existing package/cog patterns over new abstractions.
- Keep edits scoped to the requested module unless shared behavior is clearly involved.
- Use `logging` instead of `print` in runtime code.
- Avoid bare `except:`.
- Do not revert user changes in a dirty worktree.
- Do not commit or print secrets.
- Do not use `old_function/` as an active runtime dependency. Use the `legacy-old-files-archive` branch for old implementation reference.
- If adding a new active cog, update `COG_SPECS`, config templates, locale files, tests/checklist, and documentation together.
