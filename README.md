# DiscordGameServerHelper
---
## V0.3.0 - 2024-05-25
### Update the bot to support the following features:
- Bots will now log users' illegal teaming behaviour in the `bot.db` file. The record can be erased by a normal teaming within 5 minutes.
- Use the command `!check_illegal_teaming` in a specific channel to query the 20 users with the most records of illegal teaming behaviour.
- Use the command `!check_user_records <number>` in a specific channel to query all users whose number of illegal teaming behaviours is greater than `<number>`.
---
## V0.2.5 - 2024-05-24
### Bug fixes
- Fixed a bug that caused the bot to reply to the same message multiple times when the user sent a message with multiple matches.
- Fixed a bug that caused a user's teaming information containing `flex` or `rank` to be incorrectly ignored.
---
## V0.2.4 - 2024-04-19
Skipped a version number to align with the version number of the main bot.
### Update the bot to support the following features:
- Add a new slash command `/testwelcome` to test the welcome message. 
- Reorganised the structure of regular expressions into three matching parts.
- Added matching words for the new regular expression.
---
## V0.2.2 - 2024-03-31
### Update the bot to support the following features:
- Add two new parameters at the top of the code to customise the welcome message:
  - `WELCOME_TEXT_1_DISTANCE` - The distance between the first welcome text and the top of the picture.
  - `WELCOME_TEXT_2_DISTANCE` - The distance between the second welcome text and the top of the picture.
### Bug fixes
- Fixed a bug that in some environments the background image is not converted to the correct format.
---
## V0.2.1 - 2024-03-23
### Update the bot to support the following features:
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
## V0.2.0 - 2024-03-22
### Update the bot to support the following features:
#### New Welcome message System
- Add a welcome message system to send a welcome message when they join the server.
- You can define the welcome channel ID by setting the `WELCOME_CHANNEL_ID` variable.
- You can edit the background of the welcome pictures by setting the `BACKGROUND_IMAGE` variable.
- You can adjust the welcome content and specific styles in the code if needed.
  - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/welcome.png)
---
## V0.1.3 - 2024-03-20
### Update the bot to support the following features:
#### New Channel Dictionary System
- Add a channel dictionary to store the channel ID which the bot will support multiple public and private channels. You can define the channel ID, the channel type and the channel name prefix in the `CHANNEL_CONFIGS` dictionary.
---
## V0.1.2 - 2024-03-14
### Update the bot to support the following features:
#### Support for multiple public and private channels
- Just add the channel ID to the `PUBLIC_CHANNEL_ID_LIST` and `PRIVATE_CHANNEL_ID_LIST` arrays, and the bot will support multiple public and private channels.
---
## V0.1.1 - 2024-02-29
### Update the bot to support the following features:
#### New blacklist system
- Added a blacklist system that allows bot to not reply to users in the blacklist.
### Bug fixes
- Fixed a bug that had caused the bot to reply to the same message multiple times when the user sent a message with multiple matches.
- Fixed a bug that caused some special URLs to be replied incorrectly.
---
## V0.1.0 - 2024-02-20
### Update the bot to support the following features:
#### New log system
- Add a new log system to record the user's operation and the robot's response. The log will be saved in the `bot.log` file.
- Delete the old log system with timestamp. So the bug of the old timestamp system will be fixed.
#### New version control system
- The first number of the version number will be updated when the bot is almost completely rewritten.
- The second number of the version number will be updated when the bot is updated with large new features.
- The third number of the version number will be updated when the bot is updated with small new features or bug fixes.
---
## V0.0.2 - 2024-02-19
### Update the bot to support the following features:
#### Create channels for players
- Replace `RELAX_CHANNEL_ID` with the ID of the channel you want to use as the relax channel creator. When a user joins this channel, a new voice channel will be created for them. And they be moved to the new channel. Only this user has the ability to edit the channel name. 
- Added a timestamp to the detection log output by the robot. (defaults to Berlin time)
### Fixed a bug where the bot would incorrectly recognise the meaning of some Chinese words.
- 包括负向前瞻，确保\[一二三四五\]后面不是"分/分钟/min/个钟/小时"
---
## V0.0.1 - 2024-02-13
### A Discord bot to help manage game servers
#### Used to quickly create temporary voice channels for players and automatically create room invitation codes
---
 - Remember to replace `TOKEN` with your own token.
#### Create channels for players
 - Replace `PUBLIC_CHANNEL_ID` with the ID of the channel you want to use as the public channel creator. When a user joins this channel, a new voice channel will be created for them. And they be moved to the new channel. Only this user has the ability to edit the channel name. 
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/public01.png) ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/public02.png)
 - Replace `PRIVATE_CHANNEL_ID` with the ID of the channel you want to use as the private channel creator. When a user joins this channel, a new voice channel will be created for them. And they be moved to the new channel. 
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/private01.png) ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/private02.png)
 - When the last user leaves the channel, the empty channel will be deleted.
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/pics/main/afterwork.png)

--- 
#### Create room invitation(more for Chinese User)
 - When a user sends a group message in a text channel(for example: flex 4=1/aram 2q3), the bot will automatically create a room invitation link for the user.
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/normal.png)
   - If the user is not in a voice channel, the bot will send a message to remind the user to join a voice channel.
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/pics/notinchannel.png)
 - Valorant Invitation Code (6 bytes long) will not be detected.
 - Some Chinese features:
   - "4缺1","2等3","二等一"等使用“等”、“缺”以及“一二三四五”中文小写数字的组合也可以被识别。
