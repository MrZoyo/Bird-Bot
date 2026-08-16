# Bird Bot architecture

<p align="center">
  <a href="../../README.md"><img src="https://img.shields.io/badge/README-HOME-2EA44F?style=for-the-badge" alt="Back to the English README"></a>
  <a href="../zh-CN/ARCHITECTURE.md"><img src="https://img.shields.io/badge/READ_IN-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in Simplified Chinese"></a>
</p>

Last reviewed: 2026-08-16

This document explains the runtime boundaries and shared modules behind Bird Bot. The project guide in [CLAUDE.md](../../CLAUDE.md) remains the canonical source for development, migration, logging, and testing rules.

## Runtime flow

Bird Bot starts through `run.py`:

1. Resolve the repository root.
2. Load the ignored root `.env` file through `runtime_env.load_env_file()`.
3. Import `bot.main.run_bot()` only after environment loading completes.
4. Read and validate `bot/config/main.yaml`.
5. Build explicit Discord intents: members, message content, voice states, guild messages, and guild reactions; Presence Intent stays disabled.
6. Iterate over `bot.main.COG_SPECS`, skipping disabled cogs and cogs with missing required config.
7. Initialize each loaded cog, its database managers, persistent views, and background tasks.
8. Synchronize application commands.
9. Close retained database managers after cog tasks stop during shutdown.

`COG_SPECS` is the active-module registry. Additions and removals must update code, config templates, locale files, tests, and user documentation together.

## Package boundaries

```text
bot/
├── main.py               # Bot factory, active-cog registry, loading, logging, command sync
├── cogs/                 # One package per active feature
├── config/               # Public templates and ignored deployment config
├── locales/              # Locale-backed user-facing text
└── utils/                # Shared config, database, UI, path, logging, and task helpers
```

Active cogs are packages rather than flat `*_cog.py` files. A feature package commonly contains:

- `cog.py` for event listeners, commands, orchestration, and background tasks;
- `views.py` for buttons and persistent views;
- `modals.py` for user input;
- focused helpers such as `embeds.py`, `service.py`, or `full_message.py` when the feature needs them.

Cogs coordinate Discord interactions. Persistent data access belongs in the feature database manager under `bot/utils/`, and reusable cross-feature behavior belongs in a shared helper.

## Data ownership

Bird Bot separates deployment settings, translated text, mutable state, and binary assets.

| Data | Owner | Examples |
| --- | --- | --- |
| Deployment config | Ignored `bot/config/*.yaml` | token, guild/channel/role IDs, paths, prices, limits, colors |
| Public config schema | Tracked `bot/config/*.yaml.example` | sanitized defaults and field comments |
| User-facing text | `bot/locales/<lang>/*.yaml` | responses, panel titles, modal labels, command translations |
| Mutable runtime state | SQLite or SQLCipher database | balances, tickets, achievements, rooms, panel message IDs |
| Deployment content | Config, locale, or `resources/` according to type | welcome URLs, fonts, panel images |
| Historical inputs | `legacy-old-files-archive` branch | legacy JSON templates and removed implementations |

`welcome_text` is the deliberate config exception for user-facing prose because deployments embed real Discord URLs and custom emoji IDs in it. Achievement definitions and role pickup option names also remain structured content metadata because their text is coupled to thresholds, type IDs, and role IDs.

## Configuration and locale loading

`bot.utils.config.Config` loads `bot/config/<name>.yaml`, caches the result, and uses ruamel.yaml round-trip mode so comments survive command-driven writes. Config updates use a sibling temporary file and `os.replace()` for atomic replacement.

Relative runtime paths resolve from the repository root through `bot.utils.paths`; launching the bot from another working directory does not redirect the database or logs.

`bot.utils.i18n.t()` resolves runtime response text under `bot/locales/<lang>/` using the deployment's `main.locale`, with `zh_CN` as the fallback. `bot.utils.slash_translator.SlashTranslator` localizes slash-command descriptions and parameter help per Discord client; command names remain English. The repository ships `zh_CN` as its complete sample locale. To add another language, provide the matching locale files and map the Discord locale in `slash_translator.py`.

Keep IDs, paths, colors, time formats, numeric limits, and feature metadata in config. Keep general responses, form labels, button text, and panel copy in locale files.

## Database layer

Every runtime connection goes through `bot.utils.db_connect.connect_database()`. This single entry point:

- opens the configured SQLite path;
- applies the SQLCipher key from `DCGSH_DB_KEY` or `DCGSH_DB_KEY_FILE`;
- verifies that the database is readable before feature queries run;
- enforces `DCGSH_DB_REQUIRE_ENCRYPTION=1` when production requires a key.

Feature managers own schema creation and queries. Cross-version schema changes use `bot.utils.schema_migrations`. Several managers keep async connections open, so shutdown collects managers from loaded cogs and closes them after background loops stop.

### Database managers

| Module | Responsibility |
| --- | --- |
| `achievement_db.py` | Achievement counters, monthly state, voice sessions, rankings, and manual operations |
| `ban_db.py` | Temporary-ban lifecycle, moderation history, and active task recovery |
| `check_status_db.py` | Aggregate voice-activity samples |
| `giveaway_db.py` | Giveaways, participants, requirements, and winners |
| `invite_guard_db.py` | Invite links, attribution locks, join/leave totals, and leaderboard counts |
| `privateroom_db.py` | Room ownership, expiry, saved settings, bans, and shop panels |
| `role_db.py` | Persistent pickup views, signature state, change slots, and permission flags |
| `shop_db.py` | Balances, transactions, check-ins, makeup quotas, and panel records |
| `tickets_db.py` | Ticket types, configuration, thread state, membership, administrators, and statistics |
| `voice_channel_db.py` | Entry-channel rules, temporary rooms, and control-panel state |
| `teamup_display_manager.py` | Display boards, game-type mappings, and active team-up entries |

Before a migration or direct maintenance task touches a deployment database, back it up. See [PRIVACY.md](PRIVACY.md) for encryption and key-handling procedures.

## Discord UI and persistence

Bird Bot uses both embeds and Discord Components v2. Persistent panels store their channel and message IDs in SQLite, then register compatible views again after startup.

`bot.utils.components_v2` contains shared construction helpers. Feature-local `views.py` modules own interaction callbacks, while `modal_helpers.py` handles reusable modal patterns. Text inputs target discord.py 2.7.1 and are wrapped with `discord.ui.Label`.

The default `/achievements` response is a Components v2 layout with native category separators and a large avatar thumbnail. Its avatar fallback order is the queried user's custom avatar, the bot's custom avatar, then the user's default Discord avatar.

The full-room state for team-up invitations has one shared formatter: `bot.cogs.create_invitation.full_message.update_invitation_message_to_full()`. Both the invitation panel and voice-room panel call it so embeds and Components v2 messages converge on the same red, button-free final state.

## Shared utilities

| Module | Responsibility |
| --- | --- |
| `channel_validator.py` | Default administrator-channel checks and voice-state validation for contexts and interactions |
| `components_v2.py` | Common Components v2 construction and payload helpers |
| `db_connect.py` | Plain SQLite and SQLCipher connection entry point |
| `db_lifecycle.py` | Discovery and orderly closing of database managers |
| `file_utils.py` | Directory trees, archive creation, size checks, and temporary-file cleanup |
| `i18n.py` | Runtime locale lookup |
| `log_helpers.py` | Standard formatting for Discord users, channels, roles, and guilds |
| `media_handler.py` | Bounded media downloads, hashing, naming, and cleanup |
| `modal_helpers.py` | Shared modal response and validation helpers |
| `paths.py` | Repository-root path normalization and parent-directory creation |
| `role_helpers.py` | Shared role lookup and assignment behavior |
| `schema_migrations.py` | Ordered database schema migrations |
| `signature_cooldown.py` | Fixed-slot signature cooldown calculations |
| `slash_translator.py` | Discord application-command translation from locale keys |
| `task_helpers.py` | Login-aware startup guards for background tasks |

## Background tasks

Background loops must wait for a usable Discord client and stop cleanly during cog unload. `bot.utils.task_helpers.wait_until_ready_or_stop()` prevents offline tests or shutdown races from leaving unhandled tasks.

Current recurring work includes:

- voice activity sampling every ten minutes;
- team-up board refresh every two minutes;
- automatic database backup every six hours;
- temporary-room cleanup and panel recovery;
- giveaway completion and persistent-view recovery;
- private-room expiry processing;
- temporary-ban recovery and scheduled unban;
- InviteGuard cleanup, invite-link sync, batch attribution, and leaderboard refresh;
- check-in panel refresh and daily rollover.

When a task mutates state and then edits Discord, define the ordering explicitly and cover it with a fake interaction or task test. For example, check-in daily state advances only after its panel edit succeeds, and private-room renewal reads back the persisted expiry before charging the user.

## Logging

The root logger writes the main bot log. Dedicated non-propagating loggers write keyword-detection and room-activity logs. Paths and rotation retention come from `main.yaml`.

Every Discord entity should include a name and ID:

- user: `display_name / username (id)` when names differ, otherwise `display_name (id)`;
- channel, thread, role, or guild: `name (id)`;
- unresolved raw ID: `unknown (id)`.

Use `fmt_user`, `fmt_channel`, `fmt_role`, and `fmt_guild`. Numeric IDs use ASCII parentheses.

## Production customization

The repository contains generic locale text and images. A production clone may intentionally edit tracked files under `bot/locales/` and `resources/images/` for its community while keeping real YAML config ignored.

Preserve that drift with `git stash`, pull the upstream changes, then apply the stash and resolve content conflicts deliberately. Never run `git reset --hard` or another force-overwriting update on a production checkout with local content changes.

Generic improvements belong upstream. Server names, invite codes, timezone assumptions, and other deployment facts stay in ignored config or deployment-owned content.

## Extending the bot

When adding an active cog:

1. Create a package under `bot/cogs/` using the nearest existing feature as the pattern.
2. Add the cog to `bot.main.COG_SPECS` with its feature key and required config names.
3. Add sanitized, commented `*.yaml.example` templates for structured runtime data.
4. Add user-facing and command locale keys.
5. Route database access through a manager and `connect_database()`.
6. Add offline tests for config metadata, database behavior, and interaction ordering.
7. Update [FEATURES.md](FEATURES.md), the README configuration table, and the relevant tests.

Use a staging guild only for behavior that requires Discord itself: permissions, command sync, persistent views after restart, rate limits, DM delivery, and client-side rendering.
