# Bird Bot feature reference

<p align="center">
  <a href="../../README.md"><img src="https://img.shields.io/badge/README-HOME-2EA44F?style=for-the-badge" alt="Back to the English README"></a>
  <a href="../zh-CN/FEATURES.md"><img src="https://img.shields.io/badge/READ_IN-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in Simplified Chinese"></a>
</p>

Last reviewed: 2026-08-16

This document describes every active cog, its runtime behavior, and its slash commands. For installation and the shortest setup path, start with the [project README](../../README.md).

`bot/main.py::COG_SPECS` is the source of truth for active cogs and config dependencies. Slash command names come from the command decorators in each cog; Discord displays localized descriptions and option help from `bot/locales/zh_CN/commands.yaml`.

## Voice rooms and team-up

### VoiceStateCog

Feature key: `voicechannel`
Config: `bot/config/voicechannel.yaml`

VoiceStateCog turns configured entry channels into temporary-room launchers. When a member joins an entry channel, the bot creates a room, moves the member, records the room in SQLite, and removes the room after the last member leaves.

Each managed room receives a control panel with four actions:

- unlock the room;
- lock the room;
- mark the associated team-up invitation as full;
- enable or disable the soundboard permission.

The cog restores recorded panels after restart and removes stale database rows for Discord channels that no longer exist. Entry-channel rules live in SQLite and are managed through commands; `voicechannel.yaml` holds panel colors.

| Command | Purpose |
| --- | --- |
| `/check_temp_channel_records` | List recorded temporary rooms and help identify stale records |
| `/vc_add <channel>` | Register a voice entry channel |
| `/vc_remove [channel] [channel_id]` | Remove an entry channel by selection or raw ID |
| `/vc_list` | List registered entry channels |

### CreateInvitationCog

Feature key: `invitation`
Config: `bot/config/invitation.yaml`

CreateInvitationCog creates team-up messages with a direct link to the author's current voice room. It supports explicit `/invt` calls and automatic detection of team-up phrases in ordinary messages.

Automatic detection first requires a marker (`缺`, `等`, `=`, `＝`, or `q`) followed by a count. Only after this base match succeeds does the detector inspect the character before the marker. A standalone `1`, `１`, or `一` selects the gentler single-person prompt. For example, `1q4` and `一等全世界` qualify, while `1等`, `一q`, and the ordinary phrase `稍微一等` do not trigger detection.

Messages of exactly six characters are silently ignored when they contain no equals sign, Chinese character, or whitespace. This compatibility filter does not apply when the message contains `flex`, `rank`, `aram`, or `hks`, case-insensitively.

The invitation can include the author's signature. If the author is outside voice, the response links to the configured room-entry channel and uses either the normal room-creation prompt or the gentler single-person prompt. Ignore lists prevent automatic handling for selected users and text channels. The room control panel and invitation panel share the same full-room update path, so both produce the same final state.

| Command | Purpose |
| --- | --- |
| `/invt [title]` | Create a team-up invitation for the current voice room |
| `/invt_checkignorelist` | Show ignored users and channels |
| `/invt_addignorelist <channel>` | Add a text channel to the ignore list |
| `/invt_removeignorelist [channel] [channel_id]` | Remove an ignored channel by selection or raw ID |

### TeamupDisplayCog

Feature key: `teamup_display`
Config: `bot/config/teamup_display.yaml`

TeamupDisplayCog maintains one or more live boards for active team-up invitations. Boards group entries by the game types stored in SQLite, use direct room links, and refresh every two minutes.

The cog also removes expired or invalid invitation records. `display.refresh_interval_minutes` remains a compatibility field: the current task interval is fixed at two minutes in code. `display.invitation_expire_minutes` is no longer used because team-up entries link directly to rooms instead of generated Discord invites.

| Command | Purpose |
| --- | --- |
| `/teamup_init <channel>` | Create or register a display board |
| `/teamup_type_add <channel> <game_type>` | Map a source channel to a game type |
| `/teamup_type_delete [channel] [channel_id]` | Remove a game-type mapping |
| `/teamup_type_list` | List game-type mappings |

## Onboarding and community state

### WelcomeCog

Feature key: `welcome`
Config: `bot/config/welcome.yaml`

WelcomeCog reacts to member joins with a configurable welcome-channel message, a generated image containing the member avatar and member count, and an optional DM. Fonts and images come from `resources/`; generic DM copy comes from the locale file.

`welcome_text` is intentionally deployment-owned config because it often includes real server URLs and custom emoji IDs. A failed DM does not prevent the public welcome message.

| Command | Purpose |
| --- | --- |
| `/testwelcome [member] [member_number]` | Preview the welcome flow for a selected member and count |

### AchievementCog

Feature key: `achievements`
Config: `bot/config/achievements.yaml`

AchievementCog records reactions, messages, voice time, and check-in statistics. It exposes member progress, monthly views, category rankings, a button-driven `/rank` panel, and audited administrator adjustments.

The current, non-monthly `/achievements` page uses a Components v2 container with native separators between achievement categories. Its large thumbnail uses the queried user's custom avatar first, then the bot's custom avatar, then the user's default Discord avatar. Dated monthly views remain embeds.

Achievement definitions and their role IDs live in `achievements.yaml`. Categories tied to disabled features are hidden at runtime. In particular, `checkin_sum` and `checkin_combo` disappear when ShopCog is disabled. Retired giveaway achievement categories remain hidden even when GiveawayCog is enabled.

| Command | Purpose |
| --- | --- |
| `/achievements [member] [date]` | Show achievement progress, optionally for a month such as `2026-08` |
| `/increase_achievement <member> [reactions] [messages] [time_spent]` | Add progress after confirmation |
| `/decrease_achievement <member> [reactions] [messages] [time_spent]` | Remove progress after confirmation |
| `/achievement_ranking [date]` | Show category leaderboards |
| `/check_ach_ops` | Review manual achievement operations |
| `/rank [date]` | Open the interactive ranking panel |

### RoleCog

Feature key: `role`
Config: `bot/config/role.yaml`, `bot/config/achievements.yaml`

RoleCog creates persistent pickup panels for achievement, zodiac, MBTI, and gender roles. It validates configured role IDs before publishing a panel and supports optional starter roles.

The signature subsystem checks voice-time eligibility through achievement data. Each user has three fixed signature-change slots; `role.signature.cooldown_days` controls when a used slot becomes available again. `role.signature.max_changes_per_week` is retained for compatibility but is not read by runtime code.

| Command | Purpose |
| --- | --- |
| `/create_role_pickup <channel>` | Create the achievement-role panel |
| `/create_starsign_pickup <channel>` | Create the zodiac-role panel |
| `/create_mbti_pickup <channel>` | Create the MBTI-role panel |
| `/create_gender_pickup <channel>` | Create the gender-role panel |
| `/create_signature_pickup <channel>` | Create the signature panel |
| `/signature_permission_toggle <user_id> <disable>` | Enable or disable signatures for one user |
| `/signature_clear <user_id>` | Clear a user's signature and change history |
| `/signature_set_requirement <minutes>` | Set the voice-time requirement |
| `/signature_check <user_id>` | Inspect a user's signature status |

## Economy and private rooms

### ShopCog

Feature key: `shop`
Config: `bot/config/shop.yaml`

ShopCog provides a point balance, transaction history, daily check-in, and makeup check-in. The public check-in panel is persistent and shows each user private feedback for check-in and query actions.

The example config awards 10 points for a daily check-in, charges 50 points per makeup check-in, and permits three makeup check-ins per month. Deployments can change all three values. Makeup validation prevents dates before the first manual check-in and recalculates streak data after a successful write.

Panel refresh is retry-safe: transient Discord HTTP or permission failures keep a panel active, while a confirmed missing channel or message deactivates it. Daily state advances only after Discord accepts the panel edit.

| Command | Purpose |
| --- | --- |
| `/create_checkin_embed <channel>` | Create and register a check-in panel |
| `/balance_change <user>` | Adjust a balance through the administrator form |
| `/balance_history [user]` | Browse transaction history |
| `/checkin_history <user>` | Review one user's check-in details |

### PrivateRoomCog

Feature key: `privateroom`
Config: `bot/config/privateroom.yaml`, `bot/config/role.yaml`

PrivateRoomCog sells time-limited private voice rooms through Shop balances. It creates the configured Discord channel structure, stores ownership and expiry in SQLite, applies voice-activity and booster discounts, and removes expired rooms.

The example config grants 31 days for a purchase, allows renewal during the final seven days, and extends a renewal by 31 days. A normal renewal extends from the stored `end_date`; a stale active room whose date has already passed extends from the current time, so the user is not charged for elapsed days.

Users can restore saved room settings when the recorded room is missing. Administrators can initialize the shop, inspect rooms, repair expiry state, reset setup, and block a user from the feature.

| Command | Purpose |
| --- | --- |
| `/privateroom_init` | Initialize or refresh the private-room system |
| `/privateroom_setup <channel>` | Configure the shop panel and category |
| `/privateroom_reset` | Reset private-room setup state |
| `/privateroom_fix <user> <days>` | Set the remaining validity of an active room |
| `/privateroom_list` | List active rooms |
| `/privateroom_ban <user>` | Block a user from private-room operations |

## Tickets and moderation

### TicketsCog

Feature key: `tickets`
Config: `bot/config/tickets.yaml`

TicketsCog uses private Discord threads. Ticket types, panel locations, thread records, and type-specific administrators live in SQLite; `tickets.yaml` supplies the global role and user administrator lists.

The cog provides modal confirmation, pending/accepted/closed states, automatic administrator membership, DM notifications with jump links, persistent controls, statistics, and startup cleanup for missing Discord threads. DM failures do not stop ticket creation or closure.

| Command | Purpose |
| --- | --- |
| `/tickets_init [ticket_channel] [info_channel]` | Initialize the system, creating channels when omitted |
| `/tickets_add_user <user>` | Add a member to the current ticket |
| `/tickets_stats` | Show ticket statistics |
| `/tickets_admin_list` | Show global administrator configuration |
| `/tickets_admin_add_role <role>` | Add a global administrator role |
| `/tickets_admin_remove_role <role>` | Remove a global administrator role |
| `/tickets_admin_add_user <user>` | Add a global administrator user |
| `/tickets_admin_remove_user <user>` | Remove a global administrator user |
| `/tickets_accept` | Accept the current ticket |
| `/tickets_close [reason]` | Close the current ticket |
| `/tickets_refresh_buttons` | Refresh controls for existing tickets |
| `/tickets_refresh_main` | Refresh the main ticket panel |
| `/tickets_add_type` | Add a ticket type through a modal |
| `/tickets_edit_type` | Edit ticket metadata, guide, color, or administrators |
| `/tickets_delete_type` | Delete a ticket type and refresh the main panel |

### BanCog

Feature key: `ban`
Config: `bot/config/ban.yaml`

BanCog provides permanent bans, scheduled temporary bans, Discord timeouts, and an optional automatic defense against unauthorized `@everyone` spam. It persists active temporary bans, restores their timers after restart, records moderator actions, and sends configurable notifications.

Feature access uses the role and user lists in `ban.yaml`. The notification channel and temporary-ban return link can be updated through commands. Durations accept values such as `30m`, `12h`, `7d`, and `2w`; Discord limits timeouts to 28 days. Spam defense is disabled by default. Its example duration is one day, and it deletes the previous hour of message history. Older `delete_message_days` settings remain compatible. The defense exempts the guild owner, Discord administrators, configured Ban administrators, and members who can send messages in `main.admin_channel_id`. Temporary-ban DMs remind users who clicked a malicious advertisement to enable multi-factor authentication before rejoining.

| Command | Purpose |
| --- | --- |
| `/ban <user> <reason> [delete_message_days]` | Permanently ban a member |
| `/tempban <user> <duration> <reason> [delete_message_days]` | Ban a member until the parsed duration expires |
| `/mute <user> <duration> <reason>` | Apply a Discord timeout |
| `/ban_list_tempbans` | List active temporary bans |
| `/ban_admin_list` | Show administrator and notification settings |
| `/ban_admin_add_role <role>` | Grant moderation access to a role |
| `/ban_admin_delete_role <role>` | Revoke moderation access from a role |
| `/ban_admin_add_user <user>` | Grant moderation access to a user |
| `/ban_admin_delete_user <user>` | Revoke moderation access from a user |
| `/ban_set_notification_channel <channel>` | Set the moderation notification channel |
| `/ban_remove_notification_channel` | Clear the notification channel |
| `/ban_set_invite_link <invite_link>` | Set the return link used in temporary-ban DMs |
| `/ban_remove_invite_link` | Clear the return link |

### InviteGuardCog

Feature key: `invite_guard`
Config: `bot/config/invite_guard.yaml`

InviteGuardCog combines invite cleanup with an invite leaderboard. The cleanup task scans the configured guild, deletes old invites outside the code and creator whitelists, and supports dry-run mode. The example config uses a three-day maximum age and a 24-hour interval.

The leaderboard compares cached and current Discord invite `uses` values when members join. It stores inviter totals, member attribution locks, join/leave counts, and invite-link metadata. Rejoins do not grant another reward.

Joins settle in a short batch window. When the total invite-use delta matches the batch size, the cog credits each inviter; multi-invite batches use `pooled_count`. Mismatched, ignored, self-invite, or otherwise unreliable batches become ambiguous and award no points. The invite cache lock prevents the five-minute background sync from consuming deltas during settlement.

Successful attribution can credit Shop points even while ShopCog is disabled; the data remains available when ShopCog is enabled again. With a valid leaderboard panel, the cog can DM each rewarded inviter a summary, image, and direct panel link. DM or image failures never roll back attribution or points.

| Command | Purpose |
| --- | --- |
| `/invite_sync` | Refresh invite-link state and the leaderboard panel |
| `/invite_check_user <member>` | Inspect invite totals and attribution state |
| `/invite_create_embed <channel>` | Create the Components v2 leaderboard panel |

Discord does not reveal the invite code in `on_member_join`. Attribution can remain unknown or ambiguous when the bot was offline, lacks invite-list permission, sees a vanity or Discovery join, or receives inconsistent deltas.

## Giveaways and games

### GiveawayCog

Feature key: `giveaway`
Config: `bot/config/giveaway.yaml`

GiveawayCog uses a modal-based draft flow for prize details, duration, provider, activity requirements, winner count, and an optional image. Published giveaways use persistent join controls and private join/leave feedback.

Giveaway state, participants, and winners live in SQLite. The cog restores active giveaway controls after restart, supports cancellation and early ending, and isolates individual DM failures while contacting winners.

| Command | Purpose |
| --- | --- |
| `/ga_create` | Open the giveaway draft |
| `/check_giveaway` | Export current giveaway records |
| `/ga_cancel <giveaway_id>` | Cancel an active giveaway |
| `/ga_end <giveaway_id>` | End a giveaway and choose winners |
| `/ga_time_extend <giveaway_id> <time>` | Extend the end time |
| `/ga_participant <giveaway_id>` | List participants |
| `/ga_description <giveaway_id> <description>` | Replace the public description |
| `/ga_sendtowinner <giveaway_id> <message>` | Send a message to the winners |

### DnDCog

Feature key: `dnd`
Config: none

DnDCog evaluates dice expressions containing signed constants and dice terms. Standard dice such as `d6` roll from 1 through 6; a zero-prefixed term such as `d06` rolls from 0 through 6. Expressions can contain multiple terms, and `5#3+4d6` repeats an expression five times.

Each call permits at most 100 dice per term and 1,000 sides per die.

| Command | Purpose |
| --- | --- |
| `/dnd_roll <expression> [x]` | Roll an expression once or repeat it `x` times |

### SpyModeCog

Feature key: `spymode`
Config: none

SpyModeCog creates a two-team signup panel for members of the command author's voice channel. The author selects the team size and spies per team, starts the game after signup, and the bot sends secret roles through DMs before the reveal stage.

| Command | Purpose |
| --- | --- |
| `/spymode [team_size] [spy]` | Create a game; defaults to five players and one spy per side |

## Operations

### CheckStatusCog

Feature key: `checkstatus`
Config: none beyond `main.yaml`

CheckStatusCog samples aggregate voice activity every ten minutes and stores the counts in SQLite. Operators can inspect the current voice state, generate day/month/year charts, or read the configured main, keyword, and room-activity logs. `/where_is` and the `Where Is` member context menu return private voice-location results with a jump button.

| Command | Purpose |
| --- | --- |
| `/print_voice_status <date>` | Plot stored activity for `YYYY-MM-DD`, `YYYY-MM`, or `YYYY` |
| `/check_log <x> [log_type]` | Return the last `x` lines from the selected log |
| `/check_voice_status` | Show current voice-channel occupancy |
| `/where_is <member>` | Privately locate a member in voice |

### BackupCog

Feature key: `backup`
Config: none beyond `main.yaml`

BackupCog copies the configured SQLite database at 00:00, 06:00, 12:00, and 18:00 in the host's local time. It keeps the latest 20 files in `backup/db_backup/`; manual backups go to `backup/db_backup_manual/` and use the same limit.

SQLCipher databases remain encrypted because backup files are direct copies. Keep the matching key file in a separate protected backup.

| Command | Purpose |
| --- | --- |
| `/backup_now` | Create a manual database backup |

## Removed runtime features

NotebookCog, RatingCog, and the old channel-based TicketsCog are not registered at runtime and must not appear in active config templates or the Discord command picker. Historical implementations and sanitized legacy templates live on the `legacy-old-files-archive` branch; see [LEGACY_ARCHIVE.md](LEGACY_ARCHIVE.md).
