# DiscordGameServerHelper
---
---
## Package Usage

discord.py, sqlite3, PIL, logging, aiohttp, aiosqlite, os, tempfile, re, random, 

---
## Setup
1. Install the required packages.
2. Replace __all the parameters__ in the `config.json` with your own values.
3. Run the `bot.py` file. If you are using a Linux server, you can use `nohup python3 bot.py &` to run the bot in the background.
4. Invite the bot to your server and give it the necessary permissions.(Required permissions: bot, application command, administrator)

---
## Function Introduction
### Voice_Channel_Cog
When a user enters a specific channel, the bot creates a new channel of the corresponding type and moves the user to the new channel.
Similarly, if the channel was created by the bot, the bot will delete the channel when the last user leaves the channel.
### Create_Invitation_Cog
A user sends a teaming message and bot replies with an invitation link to that user's channel to make it easy for other users to quickly join the user's room.
If the user is not currently on a channel, bot will prompt the user to create a new channel using `Voice_Channel_Cog` first.
### Welcome_Cog
When a new user joins the server, the bot sends a welcome message to the user in the welcome channel. 

This includes a more complex feature: creating a unique welcome image with the current server population for a user using a specified background image, specified text content, their id and avatar.

This feature contains command functions that allow the welcome message to be summoned manually by the user.
- `!testwelcome` - Send the welcome message for who use this command.
- `/testwelcome <member> <member_number>` - Send the welcome message for specific member with specific number.
- For default `<member>` is the user who uses the command, `<member_number>` is the total number of people in the server.

### Illegal_Team_Act_Cog
For users who are not in the server's channel but sent a teaming message, the bot will record their id, what they sent and when they sent it.
If the user resends a normal teaming message, the bot deletes their illegal teaming record for 5 minutes.

Provides commands to search for records:
- `!check_illegal_teaming` or `/check_illegal_teaming`- Query the 20 users with the most records of illegal teaming behaviour.
- `!check_user_records <number>` or `/check_user_records <number>` - Query all users whose number of illegal teaming behaviours is greater than `<number>`.
- `/check_member <member>` - Query all illegal teaming records for the specified `member`.
- `/check_member_by_id <member_id>` - Query all illegal teaming records for the specified `member_id`.
- `/add_illegal_record <member> <content> <time>` - Manually add a record for a specified member.

### DnD_Cog
Provides Dungeons & Dragons (DnD) players with a convenient way to generate random roll dice points.
-  `/dnd_roll <expression> <x>` - The command takes an expression as an argument, which represents the dice roll in DnD notation. 
For example, an expression like `3+4d6` would represent rolling four 6-sided dice and adding 3 to the result. The command parses the expression, performs the dice roll, and sends a message back to the user with the result and the details of the roll.
Command `/dnd_roll` has an optional parameter `x` to specify the number of times to repeat the roll. 
- Expression `5#3+4d6` can repeat a roll of `3+4d6` for 5 times quickly. Use the expression to specify that the number before the `#` has a higher priority than the parameter `x`.

### CheckStatusCog
Provides the ability to quickly query log files from the robot side.
- `/check_log <number=x>` - Returns the last `x` lines of the log file. If the number of lines exceeds the limit, the bot will send a file with the log content.
Provides commands to query the number of active rooms and the number of in-voice users within the current server.
- `/check_people_number` - Returns the number of people in the server. 
- `/check_channel_number` - Returns the number of active channels in the server.

### Achievement_Cog

It is designed to track and display user achievements based on their activity in the server. 

**Features**
- Message Count: The bot tracks the number of messages a user sends in the server. Achievements are awarded when a user reaches certain message count thresholds.  
- Reaction Count: The bot also keeps track of the number of reactions a user adds to messages. Achievements are given when a user reaches certain reaction count thresholds.  
- Time Spent in Voice Channels: The bot monitors the amount of time a user spends in voice channels. Achievements are granted when a user reaches certain time thresholds.  


It listens to message, reaction, and voice state update events to track user activity.  
To view a user's achievements, use the `/achievements` command. 
If no user is specified, the command will display the achievements of the user who invoked the command.  
To manually increase or decrease a user's achievement progress, use the `/increase_achievement` and `/decrease_achievement` commands respectively. 

These commands require the following parameters:  
- `member`: The member whose achievement progress to modify.
- `reactions:int`: The number of reactions to add or subtract.
- `messages:int`: The number of messages to add or subtract.
- `time_spent:int`: The time spent on the server to add or subtract (in seconds).

`member` is a required parameter, while the other parameters are at least 1 optional.

Use `/achievement_ranking` to show the top 10 users with the every highest achievement indicators in the server.

### Notebook_Cog
The Notebook_Cog is a feature in the bot that allows administrators to manually log user events. This can be useful for tracking user behavior, recording important events, or keeping a record of specific interactions.

#### `/log_event <member> <event>`
This command allows to manually log a user event. 
This command can only be used on specific channels. Users who have used this command become **administrators**.

The command takes the following parameters:  

- `member`: The member whose event you want to log.
- `event`: The event that you want to log for the member.

#### `/check_member_event <member>`
This command allows **administrators** to check the event log for a specific member. 

The command takes the following parameter:
- `member`: The member whose event log you want to check.

#### `/check_all_event`
This command allows **administrators** to check the event log for all members in the server.

#### `/delete_event <member> <event_serial_number>`
This command allows to delete a specific event from a member's event log. This command can only be used on specific channels. 

The command takes the following parameters:
- `member`: The member whose event log you want to delete an event from.
- `event_serial_number`: The serial number of the event you want to delete.

---
## Update Log
### V0.6.2 - 2024-06-13
#### New features:
- Added a new `notebook_cog` for administrators to manually log user events. User events can now be logged via the `/log_event` command.
- Details can be viewed in the [Notebook_Cog](###Notebook_Cog) section of the Function Introduction.
#### Bug fixes
- Optimised matching for builds, now ignores messages from other bots.
- Fixed an issue where an empty url error would occur if a user without an avatar used `/invitation` command.
---
### V0.6.1 - 2024-06-12
#### New features:
- Optimised the display of invitation links, now creates a nice looking embed message to display the invitation link.
- Added a new command `/invitation` for creating an invitation link without sending a message using the command.
#### Bug fixes
-  Optimised what is returned when querying an illegal group, for users who have already left their user id will be returned.
-  Fixed an issue that would cause error text to appear in rooms after using the room_full button.

---
### V0.6.0 - 2024-06-10
#### New features:
- Added new `config_cog` for sharing configuration information across all cogs. Configuration information in all cogs will now be read from `config.json`.
- Optimised the interface returned when querying an illegal group. Optimised performance when querying illegal groups on low performance platforms.
- Added a command to manually record illegal team behaviours. Illegal team behaviours can now be recorded via `/add_illegal_record`.
- Optimised logging of achievement progress before and after bot restarts, now the bot will log a portion of the achievement progress after restarting that could not be logged otherwise.
- Renamed `LogFileCog` to `CheckStatusCog`, added two new commands `/check_people_number` and `/check_channel_number` to check the number of people and channels on the server.
---
### V0.5.4 - 2024-06-08
#### Bug fixes
- Optimised regular expression matching for items, now it won't ignore messages containing "aram" or messages of length 6 containing Chinese characters.
- Fixed wrong permission override for room creation.
---
### V0.5.3 - 2024-06-06
#### Bug fixes
- Fixed an issue that had caused Bot to not be able to create new rooms when the number of channels reached the limit (50) for the same category in discord.
Now the bot will create a new category with the same name below the current category and create a new channel there. It will delete these categories when they are empty.
#### New features:
- Added a new parameter `<member_number>` to the `/testwelcome` command to specify the number of the welcome image. 
`/testwelcome <member> <member_number
---
### V0.5.2 - 2024-06-04
#### Bug fixes
- Fixed a bug that would cause the Achievement system to timeout on replies in low performance environments. 
- Optimised the `/check_log` command's limit on the number of characters, which would send a file when the character limit was exceeded.
- Optimised response times for low performance servers.
---
### V0.5.1 - 2024-06-04
#### New features:
- Added a slash command `/achievement_ranking` to show the top 10 users with the every highest achievement indicators in the server.
---
### V0.5.0 - 2024-06-04
#### New features:
- New Achievement System, which is designed to track and display user achievements based on their activity in the server.
- To view a user's achievements, use the `/achievements` command. If no user is specified, the command will display the achievements of the user who invoked the command.  
- To manually increase or decrease a user's achievement progress, use the `/increase_achievement` and `/decrease_achievement` commands respectively. 

---
### V0.4.2 - 2024-06-02
#### New features:
- Provides the ability to quickly query log files from the robot side. Use the slash command `/check_log x` in the specific channel to query the last `x` lines of the log file.
---
### V0.4.1 - 2024-06-01
#### New features:
- Added the ability to query the illegal teaming records of users who have left the server. Use slash command `/check_member_by_id` in the specific channel to query.
- Added the ability to repeat roll points multiple times and improved the result display format. 
Command `/dnd_roll` now has an optional parameter `x` to specify the number of times to repeat the roll.
- Updated the expression for DnD to quickly repeat roll dice. For example `5#3+4d6` can repeat a roll of `3+4d6` for 5 times quickly. Use the expression to specify that the number before the `#` has a higher priority than the parameter `x`.
- Improved the error throwing mechanism for some features.
---
### V0.4.0 - 2024-05-31
#### New features:
- Added new feature `DnD_Cog`. this feature provides Dungeons & Dragons (DnD) players with a convenient way to generate random roll dice points.
- Use slash command `/dnd_roll`. The command takes an expression as an argument, which represents the dice roll in DnD notation. For example, an expression like `3+4d6` would represent rolling four 6-sided dice and adding 3 to the result. The command parses the expression, performs the dice roll, and sends a message back to the user with the result and the details of the roll.
---
### V0.3.8 - 2024-05-28
#### Bug fixes
- Fixed a bug that would cause empty rooms to not be deleted correctly in some cases.

---
### V0.3.7 - 2024-05-27
#### New features:
- Refactored the method of creating and deleting temporary channels, which will now use a database to store information about temporary channels so that they can continue to be managed after the bot is restarted. 
- Optimised some code to improve readability and maintainability.
---
### V0.3.6 - 2024-05-27
#### New features:
- Add a new slash command `check_member` to list all illegal teaming records for the specified `member`.
#### Bug fixes
- Asynchronous database operations were used, thus fixing a bug that would cause high-frequency private pulls from the same user to clog the database.
---
### V0.3.5 - 2024-05-26
#### Bug fixes
- In some environments it may lead to the problem that the database table is missing in the initial run
- In some environments the welcome command does not take effect
- Adjusted the permission setting of the private room, now it can be seen normally but cannot be joined.
---
### V0.3.4 - 2024-05-25
#### Bug fixes
- Fixed a bug that caused the bot to reply to the same message twice when the user sent specific command.
---
### V0.3.3 - 2024-05-25
#### New features:
- Added slash command to all commands.
- Note, please tick the application command permission for your bot and re-invite to the server to update the display and description of the slash command.
---
### V0.3.2 - 2024-05-25
#### New features:
- The structure of the code has been refactored to package each part of the function into separate cogs for tweaking and calling. Now please adjust the parameters of the response function in the corresponding cog.
- The usage is exactly the same as before, you just need to run `bot.py`.
---
### V0.3.1 - 2024-05-25
#### New features:
- Add `CHECK_ILLEGAL_TEAMING_CHANNEL_ID` to customise the channel ID for the `!check_illegal_teaming` and `!check_user_records` commands.
---
### V0.3.0 - 2024-05-25
#### New features:
- Bots will now log users' illegal teaming behaviour in the `bot.db` file. The record can be erased by a normal teaming within 5 minutes.
- Use the command `!check_illegal_teaming` in a specific channel to query the 20 users with the most records of illegal teaming behaviour.
- Use the command `!check_user_records <number>` in a specific channel to query all users whose number of illegal teaming behaviours is greater than `<number>`.
---
### V0.2.5 - 2024-05-24
#### Bug fixes
- Fixed a bug that caused the bot to reply to the same message multiple times when the user sent a message with multiple matches.
- Fixed a bug that caused a user's teaming information containing `flex` or `rank` to be incorrectly ignored.
---
### V0.2.4 - 2024-04-19
Skipped a version number to align with the version number of the main bot.
#### New features:
- Add a new slash command `/testwelcome` to test the welcome message. 
- Reorganised the structure of regular expressions into three matching parts.
- Added matching words for the new regular expression.
---
### V0.2.2 - 2024-03-31
#### New features:
- Add two new parameters at the top of the code to customise the welcome message:
  - `WELCOME_TEXT_1_DISTANCE` - The distance between the first welcome text and the top of the picture.
  - `WELCOME_TEXT_2_DISTANCE` - The distance between the second welcome text and the top of the picture.
#### Bug fixes
- Fixed a bug that in some environments the background image is not converted to the correct format.
---
### V0.2.1 - 2024-03-23
#### New features:
- Add a new command `!testwelcome` to test the welcome message.
- Optimised the code by placing the welcome message setting parameter at the top of the code. You can now easily customise your welcome message by customising the following parameters:
  - `BACKGROUND_IMAGE` - The background image of the welcome picture. Note that if your background image size changes. You will also need to adjust the other parameters in turn.
  - `TEXT_COLOR` - The text color of the welcome picture.
  - `FONT_SIZE` - The text size of the welcome picture.
  - `FONT_PATH` - The font path of the welcome picture.
  - `AVATAR_SIZE` - The size of the avatar in the welcome picture.
  - `WELCOME_TEXT` - The welcome message text.
  - `WELCOME_TEXT_PICTURE_1` - The first welcome text in picture.
  - `WELCOME_TEXT_PICTURE_2` - The second welcome text in picture.
- ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/testwelcome.png)
---
### V0.2.0 - 2024-03-22
#### New features:
##### New Welcome message System
- Add a welcome message system to send a welcome message when they join the server.
- You can define the welcome channel ID by setting the `WELCOME_CHANNEL_ID` variable.
- You can edit the background of the welcome pictures by setting the `BACKGROUND_IMAGE` variable.
- You can adjust the welcome content and specific styles in the code if needed.
  - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/welcome.png)
---
### V0.1.3 - 2024-03-20
#### New features:
##### New Channel Dictionary System
- Add a channel dictionary to store the channel ID which the bot will support multiple public and private channels. You can define the channel ID, the channel type and the channel name prefix in the `CHANNEL_CONFIGS` dictionary.
---
### V0.1.2 - 2024-03-14
#### New features:
##### Support for multiple public and private channels
- Just add the channel ID to the `PUBLIC_CHANNEL_ID_LIST` and `PRIVATE_CHANNEL_ID_LIST` arrays, and the bot will support multiple public and private channels.
---
### V0.1.1 - 2024-02-29
#### New features:
##### New blacklist system
- Added a blacklist system that allows bot to not reply to users in the blacklist.
#### Bug fixes
- Fixed a bug that had caused the bot to reply to the same message multiple times when the user sent a message with multiple matches.
- Fixed a bug that caused some special URLs to be replied incorrectly.
---
### V0.1.0 - 2024-02-20
#### New features:
##### New log system
- Add a new log system to record the user's operation and the robot's response. The log will be saved in the `bot.log` file.
- Delete the old log system with timestamp. So the bug of the old timestamp system will be fixed.
##### New version control system
- The first number of the version number will be updated when the bot is almost completely rewritten.
- The second number of the version number will be updated when the bot is updated with large new features.
- The third number of the version number will be updated when the bot is updated with small new features or bug fixes.
---
### V0.0.2 - 2024-02-19
#### New features:
##### Create channels for players
- Replace `RELAX_CHANNEL_ID` with the ID of the channel you want to use as the relax channel creator. When a user joins this channel, a new voice channel will be created for them. And they be moved to the new channel. Only this user has the ability to edit the channel name. 
- Added a timestamp to the detection log output by the robot. (defaults to Berlin time)
#### Fixed a bug where the bot would incorrectly recognise the meaning of some Chinese words.
- 包括负向前瞻，确保\[一二三四五\]后面不是"分/分钟/min/个钟/小时"
---
### V0.0.1 - 2024-02-13
#### A Discord bot to help manage game servers
##### Used to quickly create temporary voice channels for players and automatically create room invitation codes

 - Remember to replace `TOKEN` with your own token.
##### Create channels for players
 - Replace `PUBLIC_CHANNEL_ID` with the ID of the channel you want to use as the public channel creator. When a user joins this channel, a new voice channel will be created for them. And they be moved to the new channel. Only this user has the ability to edit the channel name. 
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/public01.png) ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/public02.png)
 - Replace `PRIVATE_CHANNEL_ID` with the ID of the channel you want to use as the private channel creator. When a user joins this channel, a new voice channel will be created for them. And they be moved to the new channel. 
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/private01.png) ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/private02.png)
 - When the last user leaves the channel, the empty channel will be deleted.
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/pics/main/afterwork.png)

--- 
##### Create room invitation(more for Chinese User)
 - When a user sends a group message in a text channel(for example: flex 4=1/aram 2q3), the bot will automatically create a room invitation link for the user.
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/normal.png)
   - If the user is not in a voice channel, the bot will send a message to remind the user to join a voice channel.
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/notinchannel.png)
 - Valorant Invitation Code (6 bytes long) will not be detected.
 - Some Chinese features:
   - "4缺1","2等3","二等一"等使用“等”、“缺”以及“一二三四五”中文小写数字的组合也可以被识别。
