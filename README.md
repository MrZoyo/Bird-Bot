# DiscordGameServerHelper
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
- Fixed a bug that caused some special URLs to be replied to incorrectly.
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
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/public01.png) ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/public02.png)
 - Replace `PRIVATE_CHANNEL_ID` with the ID of the channel you want to use as the private channel creator. When a user joins this channel, a new voice channel will be created for them. And they be moved to the new channel. 
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/private01.png) ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/private02.png)
 - When the last user leaves the channel, the empty channel will be deleted.
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/afterwork.png)

--- 
#### Create room invitation(more for Chinese User)
 - When a user sends a group message in a text channel(for example: flex 4=1/aram 2q3), the bot will automatically create a room invitation link for the user.
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/normal.png)
   - If the user is not in a voice channel, the bot will send a message to remind the user to join a voice channel.
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/notinchannel.png)
 - Valorant Invitation Code (6 bytes long) will not be detected.
 - Some Chinese features:
   - "4缺1","2等3","二等一"等使用“等”、“缺”以及“一二三四五”中文小写数字的组合也可以被识别。
