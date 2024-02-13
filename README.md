# DiscordGameServerHelper
## V0.0.1 - 2024-02-13
### A Discord bot to help manage game servers
#### Used to quickly create temporary voice channels for players and automatically create room invitation codes
---
 - Remember to replace `TOKEN` with your own token.
#### Create channels for players
 - replace `PUBLIC_CHANNEL_ID` with the ID of the channel you want to use as the public channel creator. When a user joins this channel, a new voice channel will be created for them. And they be moved to the new channel. Only this user has the ability to edit the channel name. 
   - ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/public01.png) ![image](https://github.com/MrZoyo/DiscordGameServerHelper/blob/main/public02.png)
 - replace `PRIVATE_CHANNEL_ID` with the ID of the channel you want to use as the private channel creator. When a user joins this channel, a new voice channel will be created for them. And they be moved to the new channel. 
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
