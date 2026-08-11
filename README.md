# Bird Bot

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py 2.7.1+](https://img.shields.io/badge/discord.py-2.7.1%2B-5865F2?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Bird Bot is a self-hosted Discord bot for Chinese-speaking gaming communities. It combines temporary voice rooms, team-up tools, achievements, an economy, tickets, moderation, and server operations in one modular service.

All persistent data stays in the operator's local SQLite database, logs, and backups. SQLCipher encryption is available for deployments that need encrypted storage at rest.

[![Bird Gaming Discord](https://discord.com/api/guilds/1146359014968537089/widget.png?style=banner2)](https://discord.gg/birdgaming)

> Bird Bot currently supports one Discord guild per process. The bundled interface language is `zh_CN`; multi-guild operation and additional locales are not implemented.

## Features

| Area | What Bird Bot provides |
| --- | --- |
| Voice rooms and team-up | Temporary voice rooms, room control panels, keyword-triggered invitations, and a live team-up board |
| Community onboarding | Welcome images, welcome-channel messages, and configurable welcome DMs |
| Achievements and roles | Message, reaction, voice-time, and check-in achievements; rankings; role pickup panels; user signatures |
| Economy and private rooms | Daily check-in, makeup check-in, balances, transaction history, private-room purchase, renewal, and expiry |
| Tickets | Thread-based tickets, per-type administrators, persistent controls, status tracking, and statistics |
| Moderation | Permanent bans, temporary bans, timeouts, notification channels, and restart-safe temporary-ban recovery |
| Invite management | Expired-invite cleanup, invite attribution, pooled batch settlement, leaderboards, and configurable point rewards |
| Giveaways and games | Persistent giveaways, D&D dice expressions, and an interactive SpyMode game |
| Operations | Log inspection, voice activity reports, automatic database backups, and manual backups |

Persistent Discord panels recover after a restart where the corresponding feature supports them. Feature flags let each deployment load only the cogs it needs.

For command-by-command behavior and feature-specific gotchas, see the [feature reference](docs/FEATURES.md). The runtime boundaries and shared helpers are described in [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Preview

| Team-up panel | Achievement panel | Ranking panel |
| --- | --- | --- |
| ![Team-up panel](pics/discord-intent-review/teamup-panel.png) | ![Achievement panel](pics/discord-intent-review/achievement-panel.png) | ![Ranking panel](pics/discord-intent-review/rank-panel.png) |

## Requirements

- Python 3.12 or newer; this repository pins Python 3.12.3 in `.python-version`
- [`uv`](https://docs.astral.sh/uv/) for the locked environment
- A Discord application with a bot user
- Discord **Server Members Intent** and **Message Content Intent** enabled
- A host that can write the configured database, log, and backup paths

Bird Bot does not request Presence Intent. The simplest initial permission setup uses the `bot` and `applications.commands` scopes with Administrator permission. Operators can reduce permissions after validating every enabled feature; InviteGuard, temporary rooms, tickets, moderation, and role assignment require their corresponding Discord permissions.

## Quick start

### 1. Create the Discord bot

In the [Discord Developer Portal](https://discord.com/developers/applications):

1. Create an application and add a bot user.
2. Enable **Server Members Intent** and **Message Content Intent** under the bot settings.
3. Invite the bot with the `bot` and `applications.commands` scopes.
4. Save the bot token, guild ID, and an administrator channel ID for configuration.

See [DISCORD_INTENT_APPLICATION_GUIDE.md](DISCORD_INTENT_APPLICATION_GUIDE.md) if the application needs Discord's privileged-intent review.

### 2. Install the project

```bash
git clone https://github.com/MrZoyo/Bird-Bot.git
cd Bird-Bot
uv sync --python 3.12.3
```

The direct dependencies live in `pyproject.toml`; `uv.lock` is the reproducible lock file. Do not edit `requirements.lock` by hand—it is a compatibility export.

### 3. Create local configuration

Copy the main template and the templates for the features you plan to enable:

```bash
cp bot/config/main.yaml.example bot/config/main.yaml
cp bot/config/voicechannel.yaml.example bot/config/voicechannel.yaml
```

On PowerShell, replace `cp` with `Copy-Item`.

Edit `bot/config/main.yaml` and set at least:

- `token`
- `guild_id`
- `admin_channel_id`
- the database and log paths, if the defaults do not fit the deployment
- each key under `features`

Disable every feature you have not configured. Enabled cogs with a missing or empty required config are skipped at startup, and their commands are not registered.

Real `bot/config/*.yaml` files are gitignored because they contain deployment IDs and secrets. Commit only the sanitized `*.yaml.example` templates.

### 4. Start the bot

```bash
uv run python run.py
```

At startup, Bird Bot loads enabled cogs, restores supported persistent views and background tasks, then synchronizes global slash commands. The console lists loaded and skipped cogs.

## Configuration

`bot/main.py::COG_SPECS` is the source of truth for active cogs and their required config files.

| Feature key | Cog | Required local config |
| --- | --- | --- |
| `voicechannel` | Temporary voice rooms | `voicechannel.yaml` |
| `welcome` | Welcome image, channel message, and DM | `welcome.yaml` |
| `invitation` | Team-up keyword detection and invitations | `invitation.yaml` |
| `invite_guard` | Invite cleanup, attribution, leaderboard, and rewards | `invite_guard.yaml` |
| `dnd` | D&D dice roller | None |
| `checkstatus` | Log and voice status tools | None |
| `achievements` | Achievements and rankings | `achievements.yaml` |
| `spymode` | SpyMode game | None |
| `giveaway` | Giveaways | `giveaway.yaml` |
| `role` | Role pickup and signatures | `role.yaml`, `achievements.yaml` |
| `backup` | Database backups | None |
| `tickets` | Thread-based tickets | `tickets.yaml` |
| `shop` | Check-in and point economy | `shop.yaml` |
| `privateroom` | Private-room purchase and renewal | `privateroom.yaml`, `role.yaml` |
| `ban` | Ban, temporary ban, and timeout tools | `ban.yaml` |
| `teamup_display` | Team-up display board | `teamup_display.yaml` |

Configuration follows four rules:

1. Relative paths such as `./data/bot.db` resolve from the repository root, not the process working directory.
2. User-facing text belongs in `bot/locales/<lang>/`; runtime IDs, paths, colors, prices, limits, and content metadata belong in config YAML.
3. Mutable setup data, including voice-room entry rules and ticket types, is stored in SQLite and managed through Discord commands.
4. `welcome_text` remains in `welcome.yaml` because deployments commonly embed server-specific URLs and custom emoji IDs in it.

## First-run Discord setup

After the bot is online, initialize only the features you enabled:

| Feature | Common setup commands |
| --- | --- |
| Temporary voice rooms | `/vc_add`, `/vc_list`, `/vc_remove` |
| Team-up board | `/teamup_init`, `/teamup_type_add`, `/teamup_type_list` |
| Tickets | `/tickets_init`, `/tickets_add_type`, `/tickets_admin_list` |
| Check-in economy | `/create_checkin_embed` |
| Private rooms | `/privateroom_setup`, `/privateroom_init` |
| Role and signature panels | `/create_role_pickup`, `/create_starsign_pickup`, `/create_mbti_pickup`, `/create_gender_pickup`, `/create_signature_pickup` |
| Invite leaderboard | `/invite_create_embed`, `/invite_sync` |
| Welcome flow | `/testwelcome` |

Slash command descriptions and option help appear in Discord's command picker. Some administrative commands must run in `main.admin_channel_id` or require feature-specific role and user permissions.

## Data, privacy, and encryption

Bird Bot stores only the state needed for enabled features: Discord IDs, panel locations, achievements, balances, tickets, moderation records, invite attribution, logs, and backups. It does not send this data to a service operated by this repository.

Keep these files out of source control and support messages:

- `bot/config/*.yaml`
- `.env` and `.local_secrets/`
- `data/*.db`
- logs and database backups
- SQLCipher keys

Database encryption is controlled through environment variables:

| Variable | Purpose |
| --- | --- |
| `DCGSH_DB_KEY` | Supplies the SQLCipher passphrase directly |
| `DCGSH_DB_KEY_FILE` | Reads the passphrase from a file |
| `DCGSH_DB_CREATE_KEY_FILE=1` | Generates the key file once when it does not exist |
| `DCGSH_DB_REQUIRE_ENCRYPTION=1` | Refuses to start without an encryption key |

`run.py` reads an ignored repository-root `.env` file for local deployments without overriding variables already supplied by the launcher. Production deployments should use host environment variables or a secret manager.

Read [PRIVACY.md](PRIVACY.md) before production use. It contains the complete data inventory, retention behavior, backup notes, and the plaintext-to-SQLCipher migration procedure.

## Upgrading a deployment

Production servers may customize tracked locale files under `bot/locales/` and images under `resources/images/`. Preserve those changes during upgrades:

```bash
git stash push -m "production overrides"
git pull --ff-only
git stash pop
uv sync --frozen --python 3.12.3
```

Before upgrading:

1. Back up `data/bot.db`.
2. Back up the matching SQLCipher key file if encryption is enabled.
3. Review upstream config-template changes and apply relevant keys to the local YAML files.
4. Restart the bot and inspect startup logs for skipped cogs or migration errors.

Database schema migrations run during startup where required. Never use `git reset --hard` or another force-overwriting update on a production checkout with server-specific locale or image changes.

## Migrating from pre-2.0 JSON configuration

Config 2.0 uses YAML, locale files, and database-backed mutable setup data. Test migration against copies of the old configuration and database:

```bash
uv run python tools/migrate_config_to_yaml.py
# Review tools/migration_report.md and the generated YAML/locale output.
uv run python tools/seed_db.py
```

The migration maps legacy `config_tickets_new.json` data to the current ticket system and skips removed RatingCog and old TicketsCog sources. Migration outputs can contain real Discord IDs and are gitignored.

See [REFACTORING_PROGRESS.md](REFACTORING_PROGRESS.md) for the full upgrade protocol and historical decisions.

## Project layout

```text
.
├── run.py                    # Loads local environment data and starts the bot
├── bot/
│   ├── main.py               # Bot factory, feature registry, cog loading, command sync
│   ├── cogs/                 # Active feature packages
│   ├── config/               # Public *.yaml.example and ignored local *.yaml
│   ├── locales/              # User-facing locale text
│   └── utils/                # Config, database, i18n, logging, media, and shared helpers
├── resources/                # Runtime fonts and images
├── docs/                     # Detailed feature and architecture references
├── tools/                    # Migration, encryption, locale, and maintenance tools
├── tests/                    # Offline pytest and fake Discord interaction coverage
├── data/                     # Local database and logs; runtime files are ignored
└── backup/                   # Automatic and manual database backups
```

Each active cog is a package under `bot/cogs/`. Runtime database access goes through `bot.utils.db_connect.connect_database()` so plaintext and SQLCipher deployments use the same connection path.

## Development

Install the test and lint extras:

```bash
uv sync --extra test --extra lint --python 3.12.3
```

Run the local verification suite:

```bash
uv run pytest -q
uv run ruff check bot tests tools
uv run python -m compileall bot tests tools
uv run python -X utf8 tools/check_locales.py
uv lock --check
```

The automated suite uses temporary databases and fake Discord interactions. Use a staging guild for behavior that depends on Discord itself, including permissions, command synchronization, persistent views after restart, rate limits, DMs, and client rendering. Follow [REFACTORING_TEST_CHECKLIST.md](REFACTORING_TEST_CHECKLIST.md) for manual validation.

Before contributing, read [CLAUDE.md](CLAUDE.md). It defines the current architecture, logging format, migration rules, testing commands, and safety requirements. Keep active docs and tests aligned with `bot/main.py::COG_SPECS`; NotebookCog, RatingCog, and the old channel-based TicketsCog are retired.

## Documentation

| Document | Purpose |
| --- | --- |
| [FEATURES.md](docs/FEATURES.md) | Detailed active-cog behavior, commands, defaults, and gotchas |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Runtime flow, data ownership, database layer, UI, and extension points |
| [CHANGELOG.md](CHANGELOG.md) | Release history moved out of the README |
| [PRIVACY.md](PRIVACY.md) | Stored data, privileged intents, retention, backups, and SQLCipher |
| [DISCORD_INTENT_APPLICATION_GUIDE.md](DISCORD_INTENT_APPLICATION_GUIDE.md) | Discord privileged-intent application guidance |
| [REFACTORING_PROGRESS.md](REFACTORING_PROGRESS.md) | Config 2.0 state, upgrade protocol, and completed work |
| [REFACTORING_PLAN.md](REFACTORING_PLAN.md) | Refactor design and migration rationale |
| [REFACTORING_TEST_CHECKLIST.md](REFACTORING_TEST_CHECKLIST.md) | Automated gate and staging-guild checklist |
| [LEGACY_ARCHIVE.md](LEGACY_ARCHIVE.md) | Location of archived legacy implementations and templates |

## License

Bird Bot is available under the [MIT License](LICENSE).
