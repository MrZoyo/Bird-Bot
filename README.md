# Bird Bot

`Version: 1.2.3`

---

Here are the maximum uses and testbeds for Bird Bot. Note that this is a server mainly for Chinese speakers in Europe, anyone is welcome to join, but please respect the culture of the server and follow the server rules.

[![Discord Banner 2](https://discord.com/api/guilds/1146359014968537089/widget.png?style=banner2)](https://discord.gg/birdgaming)<br>

---

The purpose of developing this bot is to avoid the use of various current e.g. MEE6, ProBot and other existing server managed robots. This allows for maximum personalisation and control of features and interfaces and avoids the introduction of too many public bots.

The bot incorporates the functionality used in several bots and has been developed with additional fun features. Therefore, the bot is currently only intended for use with a single server and there are no plans to support multiple servers at this time. Anyone can download the bot and run it on their own server. All data processing and storage is done locally.

The bot's code is deeply optimised for low-performance devices, using asynchronous handling of API responses and database operations. Therefore, for this bot working on a 10k members and 500 online voice users server, a 1 vCPU + 1GB RAM cloud server for about $5 a month is perfectly adequate for performance.


---

## Table of Contents
- [Package Usage](#package-usage)
- [Setup](#setup)
- [Function Introduction](#function-introduction)
  - [Voice_Channel_Cog](#voice_channel_cog)
  - [Create_Invitation_Cog](#create_invitation_cog)
  - [Welcome_Cog](#welcome_cog)
  - [Illegal_Team_Act_Cog](#illegal_team_act_cog)
  - [Check_Status_Cog](#checkstatuscog)
  - [Achievement_Cog](#achievement_cog)
  - [Role_Cog](#role_cog)
  - [Notebook_Cog](#notebook_cog)
  - [Backup_Cog](#backup_cog)
  - [Giveaway_Cog](#giveaway_cog)
  - [Rating_Cog](#rating_cog)
  - [Tickets_Cog](#tickets_cog)
  - [Game_DnD_Cog](#game_dnd_cog)
  - [Game_Spymode_Cog](#game_spymode_cog)
- [Utilities and Tools](#utilities-and-tools)
  - [config](#config)
  - [channel_validator](#channel_validator)
  - [tickets_db](#tickets_db)
- [Update Log](#update-log)

---
## Package Usage

aiosqlite, matplotlib, aiohttp, pillow, discord.py, aiofiles

---
## Setup
0. Clone the repository and enter the directory.
1. `pip3 install -r requirements.txt`
2. Modify __all the config.example files__ in the `.bot\config\` and delete `.example`.
3. Run `run.py`. If you are using a Linux server, you can use `nohup python3 run.py &` to run the bot in the background.
4. Invite the bot to your server and give it the necessary permissions.(Required permissions: bot, application command, administrator)
5. For updating the bot, you can use the `git pull` command to update the bot to the latest version.
6. For some cogs like `tickets_cog`, you need to use command `/tickets_setup` to initialize the ticket system. Please check function introduction for more details.

---
## Function Introduction
### Voice_Channel_Cog
When a user enters a specific channel, the bot creates a new channel of the corresponding type and moves the user to the new channel.
Similarly, if the channel was created by the bot, the bot will delete the channel when the last user leaves the channel.
- `/check_temp_channel_records`: Query the temporary voice channel records of the current server. This command is mainly used to check that the robot's mechanism of automatically deleting rooms that no longer exist every hour is working properly.
- `/set_soundboard`: Change the soundboard status of the channel between `on` and `off`. Only the owner of the channel can use this command.
- `/vc_add`: Add a voice channel that automatically creates new voice channels.
- `/vc_remove`: Remove a voice channel that automatically creates new voice channels.

### Create_Invitation_Cog
A user sends a teaming message and bot replies with an invitation link to that user's channel to make it easy for other users to quickly join the user's room.
If the user is not currently on a channel, bot will prompt the user to create a new channel using `Voice_Channel_Cog` first.
- `/invt <title>`: Create an invitation with a specified title(optional).
- `/invt_checkignorelist`: Check the current server's invitation channel ignore list.
- `invt_addignorelist <channel_id>`: Add a channel to the invitation channel ignore list.
- `invt_removeignorelist <channel_id>`: Remove a channel from the invitation channel ignore list.

### Welcome_Cog
When a new user joins the server, the bot sends a welcome message to the user in the welcome channel. 

This includes a more complex feature: creating a unique welcome image with the current server population for a user using a specified background image, specified text content, their id and avatar.

The bot will also send a DM to the user who joins the server.

This feature contains command functions that allow the welcome message to be summoned manually by the user.
- `/testwelcome <member> <member_number>` - Send the welcome message for specific member with specific number.
- For default `<member>` is the user who uses the command, `<member_number>` is the total number of people in the server.

### Illegal_Team_Act_Cog(about to be deprecated)
From version `1.0.0`, the bot will not automatically record the user's illegal teaming behaviour.

For users who are not in the server's channel but sent a teaming message, the bot will record their id, what they sent and when they sent it.
If the user resends a normal teaming message, the bot deletes their illegal teaming record for 5 minutes.

Provides commands to search for records:
- `!illegal_ranking` or `/illegal_ranking`- Query the 20 users with the most records of illegal teaming behaviour.
- `!illegal_greater_than <number>` or `/illegal_greater_than` - Query all users whose number of illegal teaming behaviours is greater than `<number>`.
- `/illegal_member <member>` - Query all illegal teaming records for the specified `member`.
- `/illegal_member_by_id <member_id>` - Query all illegal teaming records for the specified `member_id`.
- `/illegal_add_record <member> <content> <time>` - Manually add a record for a specified member.

### Check_Status_Cog
Provide some convenient functions for querying related data.
- `/check_log <number=x>` - Returns the last `x` lines of the log file. If the number of lines exceeds the limit, the bot will send a file with the log content.
Provides commands to query the number of active rooms and the number of in-voice users within the current server.
- `/check_voice_status` - Returns the number of active rooms and the number of in-voice users within the current server.
- `/where_is <member>` - Returns the position of the selected member within the channel. Only visible to user.
- `/print_voice_status` - Print the longtime server voice channel and number information.

### Achievement_Cog
It is designed to track and display user achievements based on their activity in the server. 

**Features**
- Message Count: The bot tracks the number of messages a user sends in the server. Achievements are awarded when a user reaches certain message count thresholds.  
- Reaction Count: The bot also keeps track of the number of reactions a user adds to messages. Achievements are given when a user reaches certain reaction count thresholds.  
- Time Spent in Voice Channels: The bot monitors the amount of time a user spends in voice channels. Achievements are granted when a user reaches certain time thresholds.  


It listens to message, reaction, and voice state update events to track user activity.  
To view a user's achievements, use the `/achievements` command. Use `<member>` to view the achievements of a specific user.
Use `<date>` to view the achievements of a specific month(eg. 2024-07).
If no user is specified, the command will display the achievements of the user who invoked the command.  
To manually increase or decrease a user's achievement progress, use the `/increase_achievement` and `/decrease_achievement` commands respectively. 

These commands require the following parameters:  
- `member`: The member whose achievement progress to modify.
- `reactions:int`: The number of reactions to add or subtract.
- `messages:int`: The number of messages to add or subtract.
- `time_spent:int`: The time spent on the server to add or subtract (in seconds).

`member` is a required parameter, while the other parameters are at least 1 optional.

Use `/achievement_ranking` to show the top 10 users with the every highest achievement indicators in the server. 
Use `<date>` to view the achievements ranking of a specific month(eg. 2024-07).

Use `/check_achi_op` to check the history of manual operation logging for the Achievement System.

### Role_Cog
The Role_Cog is a feature in the bot that allows users to assign roles to users who complete achievements.
Note that in order to use this feature properly, you need to create the role manually and add the role's id to config.

#### `/create_role_pickup <channel_id>`
This command causes the bot to send a message listing all achievements with the 4 achievement type buttons on the specified channel. The user can click on the buttons to update the corresponding type of achievement role.
#### `/create_starsign_pickup <channel_id>`
This command causes the bot to send a message listing all star signs with the 12 star sign buttons on the specified channel. The user can click on the buttons to update the corresponding star sign role.
#### `/create_mbti_pickup <channel_id>`
This command causes the bot to send a message listing all MBTI identities with the 16 MBTI identity buttons on the specified channel. The user can click on the buttons to update the corresponding MBTI identity role.
#### `/create_gender_pickup <channel_id>`
This command causes the bot to send a message listing all genders with 3 gender buttons on the specified channel. The user can click on the buttons to update.
#### `/create_signature_pickup <channel_id>`
This command causes the bot to send a message with a signature setup button and check button on the specified channel. The user can click on the buttons to update and check the signature.
#### `signature_permission_toggle <user_id> <disable>`
This command allows the user to toggle the permission of a member's signature setup permission. If the member has no permission, he/she can not change or check his signature. And the signature will not be displayed in the invitation message.
- `<user_id>` The member's id to be toggled.
- `<disable>` Whether to disable the signature setup button.
#### `signature_clear <user_id>`
Clear a user's signature and change history.
#### `signature_set_requirement <minutes>`
Set the voice time requirement for signature feature.
#### `signature_check <user_id>`
Check a user's signature information.

### Notebook_Cog
The Notebook_Cog is a feature in the bot that allows administrators to manually log user events. This can be useful for tracking user behavior, recording important events, or keeping a record of specific interactions.

#### `/notebook_log <member> <event>`
This command allows to manually log a user event. 
This command can only be used on specific channels. Users who have used this command become **administrators**.

The command takes the following parameters:  

- `member`: The member whose event you want to log.
- `event`: The event that you want to log for the member.

#### `/notebook_member <member>`
This command allows **administrators** to check the event log for a specific member. 

The command takes the following parameter:
- `member`: The member whose event log you want to check.

#### `/notebook_all`
This command allows **administrators** to check the event log for all members in the server.

#### `/notebook_delete <member> <event_serial_number>`
This command allows to delete a specific event from a member's event log. This command can only be used on specific channels. 

The command takes the following parameters:
- `member`: The member whose event log you want to delete an event from.
- `event_serial_number`: The serial number of the event you want to delete.

### Backup_Cog
Backup_Cog is used to create automatic backups of the server's databases for data security.
Backup_Cog creates backups at 0:00, 6:00, 12:00 and 18:00 every day. The current limit is 20 backups, and the oldest backups will be deleted if there are more than 20.
#### `/backup_now`
This command will manually create a backup file. Manually created backup files do not affect automatically saved backups. However, it still follows the 20 backup limit.


Config_Cog is used as a bridge to help other Cogs read settings from `config.json`.

### Giveaway_Cog

Giveaway_Cog creates the Giveaway mechanism. All giveaways will be posted in the Giveaway channel.
#### `/ga_create <reaction_req> <message_req> <timespent_req>` 
- This command allows users to create Giveaway with restrictions.
- The command parameters are as follows:
  - `reaction_req` Limits the achievement progress of added reactions for users participating in Giveaway. Not recommended.
  - `message_req` Limits the progress of the Send Message achievement for users participating in Giveaway. Not recommended.
  - `timespent_req` Limits the progress of the in-channel voice time (in minutes) achievement for users participating in Giveaway. Recommended].

- An interactive form will pop up after using the command, containing the following parameters:
  - `duration` Giveaway duration, support mainstream time abbreviation, recommended format is abbreviation. For example: 1d/24h/60m. winners The number of prizes.
  - `winners` The number of prizes, BOT will draw the corresponding number of winners, default value is 1.
  - `prizes` The name of the prizes. Note that the number of prizes should not be included here.
  - `description` Giveaway description. Please include the Giveaway limitations and description of the prize here. Note that if you use a non-discord default emoticon here, please use the full emoticon code. For example, for the in-server custom emoji :064:, use <a:064:1174704124768550963> instead of :064:.
  - `providers` Prize provider. If left blank, the default value is a custom parameter.
- Giveaway will be displayed in the Giveaway channel after submission. A copy of the original version is generated as an arch. in the channel where the command was sent. Any subsequent changes will not affect the archived version.
  The published Giveaway will be assigned a unique random ID, which will be used to identify the Giveaway.

#### `ga_cancel <giveaway_id>` 
- This command allows the user to cancel the giveaway.
- Cancelling a giveaway immediately ends the giveaway and marks it as a giveaway, no winner will be selected if the giveaway is cancelled.
  - `<giveaway_id>` giveaway identification ID.
  
#### `ga_end <giveaway_id>` 
- This command allows user to end the giveaway early.
- Ending a giveaway early will immediately end the raffle and mark it as a giveaway, ending a giveaway early will result in winners being selected.
  - `<giveaway_id>` giveaway identification ID.
  
#### `ga_time_extend <giveaway_id> <time>` 
- This command allows user to extend the giveaway time.
- The command parameters are as follows:
  - `<giveaway_id>` giveaway identification ID.
  - `<time>` The time is numeric only and is expressed in minutes.

#### `ga_participant <giveaway_id>`
- This command allows user to list all participants in the giveaway.
  - `<giveaway_id>` giveaway identification ID.

#### `ga_description <giveaway_id> <description>`
- This command allows user to change the description of the giveaway.
  - `<giveaway_id>` giveaway identification ID.
  - `<description>` The new description of the giveaway.

#### `ga_sendtowinner <giveaway_id>`
- This command allows user to send message to the winner.
  - `<giveaway_id>` giveaway identification ID.

### Rating_Cog
#### `/rt_create`
- This command allows users to create an event with a rating system. It is set to a 10-point scale, with anonymous scoring, manual start and end of scoring and display of average scores and score distribution statistics when finished.
- Using the command will call out a form that will appear in the `rating_channel` with the description filled in. Each rating item is assigned a unique `rating_id` that is used to manipulate and identify the rating item.

#### `/rt_end <rating_id>`
- This command allows the user to end a rating item.
The ended rating item will no longer allow interaction, and the average score and rating distribution statistics will be displayed when it is ended.
- For closed ratings use this command to query the ratings.

#### `rt_cancel <rating_id>`
- This command allows the user to cancel a rating item.
A cancelled rating item is no longer interactive and no statistics will be displayed.

#### `rt_description <rating_id> <description>`
- This command allows the user to modify the description of a rating item.
- Only the description of an open rating item can be modified.


### Tickets_Cog
The Tickets_Cog provides a comprehensive ticket management system that allows users to create, manage, and track support tickets. It includes features for ticket creation, user management, and statistical tracking.

#### `/tickets_setup`
Initialize the ticket system. This command sets up necessary channels, categories, and messages for the ticket system to function.

#### `/tickets_stats`
Display comprehensive statistics about the ticket system, including:
- Total number of tickets
- Number of active tickets
- Number of closed tickets
- Average response time
- Breakdown by ticket type

#### `/tickets_add_type`
Add a new ticket type to the system. Opens a modal form to input:
- Type name
- Description
- User guide
- Button color (R/G/B)

#### `/tickets_edit_type`
Edit an existing ticket type. Displays a selection menu of existing types and opens a modal form to modify the selected type.

#### `/tickets_delete_type`
Delete an existing ticket type. Displays a selection menu of existing types for deletion.

#### `/tickets_admin_list`
Display current admin configuration, including:
- Admin roles
- Admin users
- Discord permissions that grant admin access

#### `/tickets_admin_add_role`
Add a role to the ticket system's admin roles. There will now be a menu for selecting the corresponding ticket type that needs to be added.

#### `/tickets_admin_remove_role`
Remove a role from the ticket system's admin roles. There will now be a menu for selecting the corresponding ticket type that needs to be removed.

#### `/tickets_admin_add_user`
Add a user to the ticket system's admin users. There will now be a menu for selecting the corresponding ticket type that needs to be added.

#### `/tickets_admin_remove_user`
Remove a user from the ticket system's admin users. There will now be a menu for selecting the corresponding ticket type that needs to be removed.

#### `/tickets_add_user <user>`
Add a user to the current ticket.
- `user`: The user to be added to the ticket

#### `/tickets_accept`
Accept a ticket. This command can only be used by admins in ticket channels.

#### `/tickets_close`
Close a ticket. This command can only be used in ticket channels.


### Game_DnD_Cog
Provides Dungeons & Dragons (DnD) players with a convenient way to generate random roll dice points.
- Supports up to 100 up to 1,000 dice 🎲 Randomized.
-  `/dnd_roll <expression> <x>` - The command takes an expression as an argument, which represents the dice roll in DnD notation. 
For example, an expression like `3+4d6` would represent rolling four 6-sided dice and adding 3 to the result. The command parses the expression, performs the dice roll, and sends a message back to the user with the result and the details of the roll.
Supports the use of 0-containing dice. `d6` means a 6-sided die without `0`, where the result is randomized from `1,2,3,4,5,6`, 
and `d06` means a 7-sided die with 0, where the result is randomized from `0,1,2,3,4,5,6`. Common use case: using a `d02` die with a result of `0,1,2`.
Command `/dnd_roll` has an optional parameter `x` to specify the number of times to repeat the roll. 
- Expression `5#3+4d6` can repeat a roll of `3+4d6` for 5 times quickly. Use the expression to specify that the number before the `#` has a higher priority than the parameter `x`.

### Game_Spymode_Cog
Provides a simple way to play the game in "Spy Mode" in the server.
For example, a 5v5 League of Legends custom duel has a spy on each side who aims to make their opponent win without being detected.
- `/spy_mode <team_size> <spy>`: Set the number of players and spies on each team. Then sign up the teams, start the game and reveal the identity of the spies at the end of the game.


---

## Utilities and Tools
### config
A bridge to help other Cogs read settings from all config files.
### channel_validator
A tool to check if the channel is valid.
### tickets_db
A module that integrates tickets_cog's interaction with the database.

## Update Log
### V1.2.3 - 2025-01-15
#### Bug fixes
- Fixed an issue in `tickets_cog` where permissions for the tickets info channel were not properly assigned to all administrators with permissions for tickets. Fixed an issue where non-global administrators were not receiving tickets properly.

---
### V1.2.2 - 2025-01-05
#### Bug fixes
- Fixed an issue in `tickets_cog` where the `admin_list` saved in memory did not follow the modification changes and resulted in an error stating that there were no administrator privileges.

---
### V1.2.1 - 2024-12-19
#### New features and improvements
- Added `/tickets_accept` command to accept a ticket.
- Added `/tickets_close` command to close a ticket.


---
### V1.2.0 - 2024-12-18
#### New features and improvements
- Now every type of tickets can be set with separate admin users and roles.
- When a new ticket is created, the bot will send a DM to the corresponding admin users.
- Addresses the issue of capping the number of tickets that will occur in the future.
- Added a signature pickup system for the role_cog.
- The signature will be displayed in the invitation message.
- Added a automatic DM message for the welcome_cog. The bot will send a DM message to the user who joins the server.

- Dropped the `!testwelcome` command.

#### Bug fixes
- Fixed an issue with the ticket component id initialization issues.

---
### V1.1.0 - 2024-12-11
#### New features and improvements
- Added new Tickets_Cog for ticket management system with its associated tickets_db.
- Created separate configuration file for Rating_Cog.
- Modified welcome image font style and background file paths in Welcome_Cog.
- Added verification mechanism to Welcome_Cog.

- Dropped config_cog.

#### Bug fixes
- Adjusted Check_Status_Cog's log file character limit from 2000 to 1900 to prevent Discord message length issues.
---

### V1.0.1 - 2024-11-27
#### New features and improvements
- Added `/vc_list` command to list all voice channels that automatically create new voice channels.
#### Bug fixes
- Fixed an issue where bots were not deleting from the ignore channel list correctly.

---
### V1.0.0 - 2024-11-25
#### New features and improvements
- All code was refactored in its entirety.
- A more modern architecture was built for the project.
- Separated config settings files by function.
- Split reused functionality separately.

- It is now possible to add voice channels for creating rooms with commands.
- Channels that do not allow bots to reply can now be added with a command.
- Achievements can now be canceled by clicking again.
- DnD Random Dice now supports dice containing 0.
#### Bug fixes
- Fixed an issue where the number of participants in Giveaway was not recorded properly in the Achievement Ranking System for rankings indexed by month.
