# Discord privileged-intent application guide

<p align="center">
  <a href="../../README.md"><img src="https://img.shields.io/badge/README-HOME-2EA44F?style=for-the-badge" alt="Back to the English README"></a>
  <a href="../zh-CN/DISCORD_INTENT_APPLICATION_GUIDE.md"><img src="https://img.shields.io/badge/READ_IN-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in Simplified Chinese"></a>
</p>

This guide is for the person submitting the Discord Developer Portal application. Describe the current `main` branch and public repository. Do not request intents that the current code does not use.

## Links

Privacy policy:

```text
https://github.com/MrZoyo/Bird-Bot/blob/main/docs/en/PRIVACY.md
```

Screenshots for the application form:

```text
Achievement panel:
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/achievement-panel.png

Ranking panel:
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/rank-panel.png

Team-up invitation panel:
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/teamup-panel.png
```

Use these raw links if the form requires direct image URLs:

```text
https://raw.githubusercontent.com/MrZoyo/Bird-Bot/main/pics/discord-intent-review/achievement-panel.png
https://raw.githubusercontent.com/MrZoyo/Bird-Bot/main/pics/discord-intent-review/rank-panel.png
https://raw.githubusercontent.com/MrZoyo/Bird-Bot/main/pics/discord-intent-review/teamup-panel.png
```

## Intent selection

Request these Privileged Gateway Intents:

```text
Server Members Intent: Request
Message Content Intent: Request
Presence Intent: Do not request
```

The current code enables only `members` and `message_content` and explicitly disables `presences`. Bird Bot does not use online/offline status, activities, platform status, or rich presence data.

## App details

Question: What does your app do? Describe its features in detail and include relevant image or video links.

Suggested answer:

```text
Bird Bot is a server-management and community-interaction bot for Discord communities. Its main features are:

1. Automatic voice rooms: when a user joins a configured voice channel, the bot creates a temporary room and moves the user into it. The bot deletes an empty room automatically. Room owners can use a control panel to switch between public and private access, mark the room as full, and enable or disable the soundboard.
2. Team-up invitations: when a user sends a matching team-up message in a text channel, the bot detects configured keywords, creates a panel linked to the user's current voice room, and adds the entry to a live team-up board.
3. Welcome flow: when a new member joins, the bot sends a welcome-channel message, creates a welcome image, and can send onboarding instructions by DM.
4. Achievements and rankings: the bot counts member messages, reactions, voice time, and check-ins for achievement progress, achievement role pickup, and ranking displays.
5. Shop and daily check-in: members can check in each day, use points for a makeup check-in, and view their point balance. Administrators can manage point transactions.
6. Private rooms: members can buy and renew private rooms. The bot records expiry dates and deletes expired rooms.
7. Tickets: members can create private thread-based tickets. The bot adds the administrators assigned to each ticket type and records ticket state.
8. Role pickup: members can select zodiac, MBTI, gender, and achievement roles and set a personal signature.
9. Supporting operations: giveaways, temporary bans, database backups, and server voice-status queries.

The bot uses Discord data only for server administration, member interaction, achievement tracking, and panel recovery. It does not sell Discord data, share it with third parties, or use it to train machine-learning or AI models.

Screenshots:
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/teamup-panel.png
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/achievement-panel.png
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/rank-panel.png
```

Question: Have you published a public privacy policy that explains how user data is used?

Select:

```text
Yes
```

Privacy policy URL:

```text
https://github.com/MrZoyo/Bird-Bot/blob/main/docs/en/PRIVACY.md
```

## Server Members Intent

Question: Why do you need the Server Members Intent?

Suggested answer:

```text
The bot needs the Server Members Intent for core features that depend on Discord members:

1. The welcome flow receives member-join events, creates welcome messages and images, displays the member count, and sends onboarding instructions to the new member by DM.
2. The ticket system reads the members of configured administrator roles so it can add those members to the appropriate private ticket threads and notify them.
3. Achievements, role pickup, private rooms, and administration commands need reliable Discord Member objects, role membership, and member permissions.
4. Voice-status tools display a member's current voice channel and the other members in that channel.
5. Private rooms and some administration features check whether a member has a configured role, such as an eligibility or discount role.

The bot uses this data only to run features inside the server, check permissions, recover panels, and support administration audits. It does not use the data for advertising or profiling, sell it, or share it outside the deployment.
```

Question: Provide screenshots and/or video links that demonstrate these use cases.

Suggested answer:

```text
Achievement panel:
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/achievement-panel.png

Ranking panel:
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/rank-panel.png
```

Question: Do you store any API data outside Discord?

Select:

```text
Yes
```

Question: Do you retain the API data for no more than 30 days?

Recommended selection:

```text
No
```

Bird Bot retains some data required for long-running server features, including achievement statistics, check-in history, point balances, ticket records, private-room expiry dates, temporary voice-room records, giveaway records, temporary-ban records, and panel message IDs. The bot uses this state for recovery, rankings, audits, and administration; it is not a temporary cache.

Question: How can users contact you to request deletion of their active data?

Suggested answer:

```text
Users can request data deletion from the server's administration team in either of these ways:

1. Contact a server administrator directly.
2. Submit a data-deletion request through the bot's ticket system.

After confirming the request, an administrator can delete or clear the user's active data, including signatures, ticket records, points and check-in records, achievement statistics, private-room records, team-up records, and other feature state.
```

Question: Is stored data encrypted at rest as required by the Developer Policy?

Select:

```text
Yes
```

The current code supports SQLCipher encryption at rest. Production deployments should configure `DCGSH_DB_KEY` or `DCGSH_DB_KEY_FILE` and set `DCGSH_DB_REQUIRE_ENCRYPTION=1`.

## Message Content Intent

Question: Can users opt out of message-content tracking?

Select:

```text
Yes
```

Optional explanation:

```text
Users can contact a server administrator or submit a ticket to request opt-out or data deletion. Administrators can also add specific channels or users to the team-up keyword detector's ignore list, so the bot no longer processes team-up messages from those locations or users.
```

Question: Do you store message-content data outside Discord?

Select:

```text
Yes
```

Bird Bot stores team-up keyword message content temporarily for the live team-up display and troubleshooting, and it writes keyword-detection events to local logs. Ordinary feature state and user-submitted values are stored in a local SQLite database.

Question: Do you retain user message-content data for no more than 30 days?

Recommended selection:

```text
No
```

The default runtime configuration keeps 14 daily rotated log backups, and team-up display entries expire after about five minutes. However, operators may retain manual backups or change log-retention policy, so `No` is the conservative answer. Select `Yes` only if the production deployment guarantees that all message-content logs and backups are removed within 30 days and its actual operations match that claim.

Question: How can users contact you to request deletion of their active data?

Suggested answer:

```text
Users can contact the server's administration team or submit a deletion request through the bot's ticket system. After confirming the request, an administrator can clear the user's message-content data, including team-up display records, personal signatures, ticket-related records, and user-submitted text stored by other features.
```

Question: Is stored data encrypted at rest as required by the Developer Policy?

Select:

```text
Yes
```

Question: Do you use message-content data to train machine-learning or AI models?

Select:

```text
No
```

Question: Why do you need the Message Content Intent?

Suggested answer:

```text
The bot needs the Message Content Intent for team-up keyword detection and message-count achievements inside the server:

1. The team-up invitation system reads ordinary text-channel messages and uses configured rules and regular expressions to identify team-up phrases, such as queue status, missing-player notices, and party size. It then replies with a panel linked to the user's voice room.
2. The achievement system listens for member messages to count total messages and build monthly message rankings.
3. The bot does not use message content for advertising or profiling, sell it, share it outside the deployment, or use it for AI or machine-learning training.
4. For the team-up display, the bot stores only the short team-up text, channel ID, user ID, voice-channel ID, and expiry time required for the temporary display. Expired invitations are removed. Other persistent text is limited to feature data that users or administrators submit intentionally, such as personal signatures, ticket close reasons, and giveaway descriptions.
```

Question: Provide screenshots and/or video links that demonstrate these use cases.

Suggested answer:

```text
Team-up invitation panel:
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/teamup-panel.png

Achievement panel:
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/achievement-panel.png

Ranking panel:
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/rank-panel.png
```

## Pre-submission checklist

Confirm these points before submitting:

```text
1. Request only Server Members Intent and Message Content Intent.
2. Do not request Presence Intent.
3. Use the public repository's docs/en/PRIVACY.md as the privacy-policy URL.
4. State that users can request deletion by contacting an administrator or submitting a ticket.
5. Select Yes for encryption at rest, and confirm that the production deployment has enabled SQLCipher database encryption.
6. Select No for machine-learning or AI training.
7. Use public GitHub screenshot links from the main branch.
```
