# Changelog

This file preserves the release notes that previously lived at the bottom of `README.md`. Entries describe the code at the time of each release; current runtime behavior is documented in [FEATURES.md](docs/FEATURES.md).

## 2.0.2 — 2026-08-02

- Fixed check-in panels becoming permanently inactive after a transient Discord API failure during refresh or startup recovery.
- Deactivated check-in panel records only when Discord confirms that the channel or message no longer exists; permission and other HTTP failures remain retryable.
- Advanced daily rollover state per panel only after that panel message was edited successfully, preventing displayed dates and stored dates from diverging.
- Added regression coverage for transient HTTP failures, missing messages, successful edit-before-reset ordering, and per-panel daily-stat resets.

## 2.0.1 — 2026-07-04

- Added InviteGuard to silently clean active Discord invites older than the configured retention window.
- Added dry-run support, invite-code and creator whitelists, scheduled cleanup, and cleanup summaries.
- Added invite attribution storage and a Components v2 Top 15 invite leaderboard with viewer-local relative update time and bot avatar thumbnail.
- Added `/invite_sync`, `/invite_check_user`, and `/invite_create_embed` operator commands.
- Added configurable Shop point rewards for newly counted valid invites; the default is 60 points.
- Added pooled invite attribution with batch settlement and serialized invite-cache access.
- Added inviter reward DMs with a Components v2 layout, reward image, and leaderboard link when a valid panel exists.
- Documented required Discord invite permissions and the convention that default owner/admin access maps to `main.admin_channel_id`.

## 2.0.0 — 2026-06-27

- Completed the config 2.0 runtime migration: YAML configuration, locale-backed UI text, package-based cogs, and database-backed mutable feature data are now the active runtime path.
- Removed runtime registration for NotebookCog, RatingCog, and the old channel-based TicketsCog; historical code moved to `legacy-old-files-archive`.
- Added fake Discord interaction-flow tests for retained modules.
- Changed stale PrivateRoom renewals to extend from the current time instead of charging for already-expired days.
- Standardized Discord entity logging with name and ID formatting.
- Added migration tooling for pre-config-2.0 JSON deployments and expanded public YAML template documentation.
- Retired giveaway-related achievement categories while keeping GiveawayCog active.

## 1.9.1 — 2026-04-14

- Locked the Python runtime and dependency environment with `.python-version` and the project lock files.
- Added role-ID preflight validation before creating achievement, zodiac, MBTI, and gender pickup panels.
- Allowed optional `achievement_start_role_id` and `social_start_role_id` values in RoleCog.
- Hid feature-linked achievement content when its related module is disabled.
- Changed `/tickets_init` follow-up messages to public responses.
- Fixed VoiceStateCog startup ordering so `temp_channels` exists before cleanup begins.
- Updated BanCog task creation for current runtime compatibility and cleaner task cleanup.

## 1.9.0 — 2026-04-14

- Added feature toggles for per-module loading.
- Disabled modules and modules without valid config now skip cleanly without startup errors.
- Skipped modules no longer register their commands.

## 1.8.4 — 2026-01-11

### Bug fixes

- Fixed a PrivateRoom renewal path that could allow indefinite renewals in specific states.
- Added an in-room reminder when the user has disabled DMs and a room can be renewed.

## 1.8.3 — 2025-12-19

- Extended the makeup check-in application window to 180 days.
- Removed synchronization buttons and bottom prompts for full or already-complete parties.
- Enhanced `/print_voice_status` with daily/monthly peaks and yearly monthly charts.
- Removed duplicate guild-level command synchronization after restart or manual sync.

## 1.8.2b — 2025-10-23

- Fixed a PrivateRoom creation error and removed unused database methods and tables.
- Enabled automatic command synchronization for all commands.

## 1.8.1b — 2025-10-21

- Added a separate room-activity log for control-panel creation and team-up cleanup events.
- Added PrivateRoom renewal reminder DMs.
- Simplified `/check_log` with a log-type selector.
- Removed legacy database migration compatibility code and streamlined initialization.

## 1.8.0b — 2025-10-10

- Added the interactive voice-room control panel with unlock, lock, full, and soundboard actions.
- Added dynamic room-type colors and panel recovery after restart.
- Added automatic team-up full-state updates with database message tracking.

## 1.7.0b — 2025-09-09

- Added the interface-based daily check-in system with automatic panel refresh.
- Reworked channel-selection commands to use Discord's native channel selectors.
- Added hybrid channel selection and raw-ID removal for deleted channels.

## 1.6.5b — 2025-08-20

- Fixed room creation failures caused by blocked user IDs.
- Removed the old ticket system and its migration code.
- Added automatic cleanup for tickets whose channels no longer exist.

## 1.6.4b — 2025-08-13

- Fixed private-ticket permission handling.
- Fixed one-click archiving for old tickets.
- Added a temporary conversion command for non-private tickets in the new system.

## 1.6.3b — 2025-07-08

- Fixed achievement checks crashing when a user had many achievements.

## 1.6.2b — 2025-07-06

- Rebuilt AchievementCog and RoleCog around separated database and logic layers.
- Added total-check-in and consecutive-check-in achievement categories.
- Fixed the Accept button showing the wrong status in closed tickets.

## 1.6.1 — 2025-07-04

- Fixed TeamupDisplay rendering and removed the unwanted `@` section.
- Restored the legacy `/tickets_archive` command at the time; the old ticket system is no longer active in config 2.0.

## 1.6.0b — 2025-07-02

- Added the TeamupDisplay system with a two-minute refresh, game-type categorization, cleanup, and native Discord time/channel links.
- Removed the Rating system; its data was preserved but its commands were discontinued.

## 1.5.2b — 2025-06-30

- Fixed BanCog database uniqueness errors and ban logging.

## 1.5.1b — 2025-06-29

- Fixed automatic processing of expired temporary bans.
- Added `/ban_list_tempbans` and improved startup recovery of temporary bans.

## 1.5.0b — 2025-06-29

- Added BanCog with permanent bans, temporary bans, Discord timeouts, role/user administrator lists, notifications, persistence, and restart recovery.
- Updated the new thread-based ticket command structure.
- Marked the old channel-based ticket system as deprecated.

## 1.4.1b2 — 2025-06-17

- Fixed closed-ticket number display.

## 1.4.1b — 2025-06-17

- Added one-month PrivateRoom extensions.
- Added monthly makeup check-ins paid with Shop points.

## 1.4.0b — 2025-06-16

- Introduced the thread-based ticket system with modal confirmations, persistent controls, type-specific administrators, DM notifications, and rate-limited administrator additions.
- Added separate main and keyword-detection logs with configurable paths and UTF-8 support.

## Historical terminology

Older entries use names such as `Tickets_New_Cog`, `Rating_Cog`, and JSON config filenames. Those names describe historical releases only. See [LEGACY_ARCHIVE.md](LEGACY_ARCHIVE.md) for the archived implementation branch and [FEATURES.md](docs/FEATURES.md) for the current runtime.
