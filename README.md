# Bird Bot 

`Version: 1.6.4b`

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
  - [Check_Status_Cog](#check_status_cog)
  - [Achievement_Cog](#achievement_cog)
  - [Role_Cog](#role_cog)
  - [Notebook_Cog](#notebook_cog)
  - [Backup_Cog](#backup_cog)
  - [Giveaway_Cog](#giveaway_cog)
  - [Rating_Cog (Legacy)](#rating_cog)
  - [TeamupDisplay_Cog](#teamupdisplay_cog)
  - [Tickets_New_Cog](#tickets_new_cog)
  - [Tickets_Cog (Legacy)](#tickets_cog-legacy)
  - [Ban_Cog](#ban_cog)
  - [Shop_Cog](#shop_cog)
  - [PrivateRoom_Cog](#privateroom_cog)
  - [Game_DnD_Cog](#game_dnd_cog)
  - [Game_Spymode_Cog](#game_spymode_cog)
- [Utilities and Tools](#utilities-and-tools)
  - [config](#config)
  - [channel_validator](#channel_validator)
  - [tickets_new_db](#tickets_new_db)
  - [tickets_db](#tickets_db)
  - [file_utils](#file_utils)
  - [media_handler](#media_handler)
  - [shop_db](#shop_db)
  - [privateroom_db](#privateroom_db)
  - [achievement_db](#achievement_db)
  - [role_db](#role_db)
  - [ban_db](#ban_db)
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
6. For some cogs like `tickets_new_cog`, you need to use command `/tickets_setup` to initialize the ticket system. Please check function introduction for more details.

---
## Function Introduction
### Voice_Channel_Cog
When a user enters a specific channel, the bot creates a new channel of the corresponding type and moves the user to the new channel.
Similarly, if the channel was created by the bot, the bot will delete the channel when the last user leaves the channel.
- `/check_temp_channel_records`: Query the temporary voice channel records of the current server. This command is mainly used to check that the robot's mechanism of automatically deleting rooms that no longer exist every hour is working properly.
- `/set_soundboard`: Change the soundboard status of the channel between `on` and `off`. Only the owner of the channel can use this command.
- `/vc_add`: Add a voice channel that automatically creates new voice channels.
- `/vc_remove`: Remove a voice channel that automatically creates new voice channels.
- `/vc_list`: List all voice channels that automatically create new voice channels.

### Create_Invitation_Cog
A user sends a teaming message and bot replies with an invitation link to that user's channel to make it easy for other users to quickly join the user's room.
If the user is not currently on a channel, bot will prompt the user to create a new channel using `Voice_Channel_Cog` first.

**Enhanced Features:**
- **Intelligent keyword detection** using regex patterns to automatically detect team-up requests
- **User signature system** allowing personalized signatures in invitations
- **Room status tracking** with "room full" functionality
- **Separate logging system** for keyword detection activities

**Commands:**
- `/invt <title>`: Create an invitation with a specified title(optional).
- `/invt_checkignorelist`: Check the current server's invitation channel ignore list.
- `/invt_addignorelist <channel_id>`: Add a channel to the invitation channel ignore list.
- `/invt_removeignorelist <channel_id>`: Remove a channel from the invitation channel ignore list.

### Welcome_Cog
When a new user joins the server, the bot sends a welcome message to the user in the welcome channel with enhanced features:

**Features:**
- **Dynamic welcome images** with user avatars and member count
- **Customizable welcome messages** with font and styling support
- **Automatic DM system** sending personalized direct messages to new members
- **Resource verification system** to ensure required assets are available
- **Server statistics integration** displaying current member count

**Commands:**
- `/testwelcome <member> <member_number>` - Send the welcome message for specific member with specific number.
  - For default `<member>` is the user who uses the command, `<member_number>` is the total number of people in the server.

### Check_Status_Cog
Provide enhanced monitoring and status checking functions with comprehensive data tracking.

**Enhanced Logging System:**
- **Dual log system** supporting both main application logs and keyword detection logs
- **Log file size management** with automatic file generation for large logs
- **Chinese interface** for better user experience

**Voice Monitoring:**
- **Real-time voice statistics** with database storage
- **Automated data collection** every 10 minutes for trend analysis
- **Chart generation** capabilities for activity visualization
- **Category-based tracking** of voice channel usage

**Commands:**
- `/check_log <number=x> [keyword_log=False]` - Returns the last `x` lines of the specified log file. Use `keyword_log=True` to check keyword detection logs instead of main logs.
- `/check_voice_status` - Returns comprehensive voice channel statistics and member counts.
- `/where_is <member>` - Returns the position of the selected member within the channel. Only visible to user.
- `/print_voice_status` - Print the longtime server voice channel and number information.
- `/test_keyword_log [test_message]` - Test the keyword detection logging system.

### Achievement_Cog
Comprehensive achievement tracking system for user activity monitoring.

**Features:**
- **Message Count Tracking**: Monitor user message activity with milestone achievements
- **Reaction Count Tracking**: Track reaction usage with progress rewards  
- **Voice Time Tracking**: Monitor time spent in voice channels with time-based achievements
- **Monthly Statistics**: View achievements and rankings by specific months
- **Admin Management**: Manual adjustment capabilities for achievement progress

**Commands:**
- `/achievements [member] [date]`: View user achievements. Use `<date>` format like "2024-07" for monthly views.
- `/increase_achievement <member> [reactions] [messages] [time_spent]`: Manually increase achievement progress.
- `/decrease_achievement <member> [reactions] [messages] [time_spent]`: Manually decrease achievement progress.
- `/achievement_ranking [date]`: Show top 10 users in various achievement categories.
- `/check_achi_op`: Check manual operation history for the achievement system.
- `/rank`: Enhanced ranking system interface for server leaderboards.

### Role_Cog
Comprehensive role assignment system with multiple assignment categories.

**Features:**
- **Achievement-based role assignment** with automatic role updates
- **Star sign role system** with 12 zodiac options
- **MBTI personality role system** with all 16 types
- **Gender role assignment** with inclusive options
- **User signature system** with permission management and voice time requirements

**Commands:**
- `/create_role_pickup <channel_id>`: Create achievement role selection interface
- `/create_starsign_pickup <channel_id>`: Create star sign role selection interface
- `/create_mbti_pickup <channel_id>`: Create MBTI role selection interface
- `/create_gender_pickup <channel_id>`: Create gender role selection interface
- `/create_signature_pickup <channel_id>`: Create signature management interface
- `/signature_permission_toggle <user_id> <disable>`: Toggle user's signature permissions
- `/signature_clear <user_id>`: Clear user's signature and history
- `/signature_set_requirement <minutes>`: Set voice time requirement for signatures
- `/signature_check <user_id>`: Check user's signature information

### Notebook_Cog
Administrative event logging system for tracking member incidents and administrative actions.

**Features:**
- **Admin permission system** with database tracking of authorized users
- **Event logging** with timestamps and serial numbering
- **Member-specific event histories** with paginated viewing
- **Event deletion capabilities** for record management
- **Channel-restricted usage** for security

**Commands:**
- `/notebook_log <member> <event>`: Log an event for a specific member (admin only)
- `/notebook_member <member>`: View event log for a specific member (admin only)
- `/notebook_all`: View event logs for all members in the server (admin only)
- `/notebook_delete <member> <event_serial_number>`: Delete a specific event from member's log (admin only)

### Backup_Cog
Automated database backup system with scheduled and manual backup capabilities.

**Features:**
- **Automated backups** every 6 hours (0:00, 6:00, 12:00, 18:00)
- **Backup rotation** maintaining latest 20 backups with automatic cleanup
- **Manual backup capability** for immediate backup needs
- **Backup limit management** to prevent storage overflow

**Commands:**
- `/backup_now`: Create an immediate backup file manually

### Giveaway_Cog
Comprehensive giveaway management system with achievement-based restrictions.

**Features:**
- **Achievement-based entry requirements** for reaction, message, and voice time thresholds
- **Time-based giveaway management** with flexible duration formats
- **Winner selection system** with configurable winner counts
- **Archive system** preserving original giveaway information
- **Interactive forms** for detailed giveaway configuration

**Commands:**
- `/ga_create <reaction_req> <message_req> <timespent_req>`: Create new giveaway with requirements
- `/ga_cancel <giveaway_id>`: Cancel active giveaway
- `/ga_end <giveaway_id>`: End giveaway early and select winners
- `/ga_time_extend <giveaway_id> <time>`: Extend giveaway duration
- `/ga_participant <giveaway_id>`: List all giveaway participants
- `/ga_description <giveaway_id> <description>`: Update giveaway description
- `/ga_sendtowinner <giveaway_id>`: Send message to giveaway winners

### Rating_Cog
**⚠️ Deprecated system** - The rating system has been removed in version 1.6.0b.

**Important:** This system is no longer available. All rating-related commands and functionality have been discontinued. Rating data remains in the database but is no longer accessible through bot commands.

**Previous Features:**
- **10-point rating scale** with anonymous submissions
- **Manual start/end control** for rating periods
- **Statistical analysis** showing average scores and distribution
- **Rating item management** with unique ID system

**Previous Commands (No longer available):**
- `/rt_create`: Create new rating item with interactive form
- `/rt_end <rating_id>`: End rating and display statistics
- `/rt_cancel <rating_id>`: Cancel rating without showing results
- `/rt_description <rating_id> <description>`: Modify rating description

### TeamupDisplay_Cog
Real-time teamup information display system for organizing team activities.

**Features:**
- **Real-time display board** with automatic updates every 2 minutes
- **Game type categorization** for organized teamup information
- **Automatic cleanup** of expired invitations and invalid data
- **Discord integration** with native time formatting and channel links

**Commands:**
- `/teamup_init <channel_id>`: Create teamup display board in specified channel
- `/teamup_type_add <channel_id> <game_type>`: Add game type configuration
- `/teamup_type_delete <channel_id>`: Delete game type configuration
- `/teamup_type_list`: View all game type configurations

### Tickets_New_Cog
**🆕 Recommended ticket system** using Discord's native thread architecture for enhanced performance and user experience.

**Key Features:**
- **Thread-based tickets** leveraging Discord's native functionality
- **Modal confirmations** preventing accidental ticket creation
- **Dynamic button states** that update based on ticket status (pending/accepted/closed)
- **Comprehensive admin system** with type-specific and global permissions
- **Automatic admin notifications** via DM with jump buttons
- **Persistent state management** surviving bot restarts
- **Statistics and analytics** for ticket system monitoring

**Admin Management:**
- **Type-specific permissions** allowing different admins for different ticket types
- **Global admin system** for overall ticket management
- **Automatic admin addition** to ticket threads with rate limiting
- **Permission inheritance** from Discord roles and individual user assignments

**Commands:**
- `/tickets_init`: Initialize the new ticket system
- `/tickets_new_stats`: Display comprehensive ticket statistics
- `/tickets_admin_list`: Show current admin configuration
- `/tickets_admin_add_role <role>`: Add admin role with type selection
- `/tickets_admin_remove_role <role>`: Remove admin role from system
- `/tickets_admin_add_user <user>`: Add individual admin user
- `/tickets_admin_remove_user <user>`: Remove individual admin user
- `/tickets_new_add_user <user>`: Add user to current ticket
- `/tickets_new_accept`: Accept current ticket (admin only)
- `/tickets_new_close <reason>`: Close current ticket with reason
- `/tickets_refresh_buttons`: Refresh all ticket button states
- `/tickets_refresh_main`: Refresh main ticket creation page

**User Experience:**
- **Jump buttons** for easy navigation to ticket threads
- **Rich embeds** with comprehensive ticket information
- **Button state indicators** showing ticket status at a glance
- **Modal confirmations** for important actions

### Tickets_Cog (Legacy)
**⚠️ Deprecated system** - The original channel-based ticket system is being phased out.

**Features:**
- **Category-based archive functionality** for tickets with complete message history and file download

**Commands:**
- `/tickets_archive`: Archive all tickets in the current category with complete message history and attachment download (≤50MB per file)

### Shop_Cog
**🔥 Enhanced point-based economy system** with makeup check-in functionality and improved user experience.

**Core Features:**
- **Balance management** with point tracking and transfer capabilities
- **Daily check-in system** with streak bonuses and reward tracking
- **Advanced makeup check-in system** for missed days (NEW in v1.7.1b)
- **Transaction history** with detailed logging and monthly views
- **Admin controls** for manual balance adjustments with audit trails
- **Check-in streaks** encouraging daily engagement with accurate tracking

**🆕 Makeup Check-in System:**
- **Monthly limit**: 3 makeup check-ins per month with intelligent quota management
- **Smart validation**: Prevents makeup before first manual check-in
- **Cost-based system**: 20 points per makeup (configurable) vs 10 points earned per check-in
- **Automatic streak recalculation** ensuring accurate statistics after makeup
- **Comprehensive UI** showing remaining quotas and streak information

**Commands:**
- `/checkin`: Perform daily check-in to earn points (must be in voice channel)
- `/checkin_makeup`: **NEW** - Make up for missed check-in days (costs 20 points)
- `/checkin_check [user]`: View check-in status with enhanced interface
- `/checkin_history [user]`: View complete check-in history including makeup records
- `/balance_change <user>`: (Admin) Modify user balance with detailed forms
- `/balance_history [user]`: View transaction history with pagination

### PrivateRoom_Cog
**🏠 Enhanced private voice channel system** with intelligent settings preservation and restoration capabilities.

**Core Features:**
- **Temporary ownership system** with configurable expiration periods (32 days default)
- **Point-based purchasing** integrated with shop system and voice activity discounts
- **Activity-based discounts** rewarding active voice users (up to 100% off)
- **Room restoration** for accidentally deleted channels within validity period
- **Automatic cleanup** of expired rooms with smart scheduling

**🆕 Settings Preservation System:**
- **Automatic settings backup** when rooms expire or are deleted
- **Complete permission preservation** including user-specific and role-based permissions
- **Channel name preservation** maintaining user customizations
- **Intelligent restoration options** when purchasing new rooms
- **6-month storage period** for saved settings with automatic cleanup
- **Smart UI choices** between restoring previous settings or creating fresh rooms

**Enhanced User Experience:**
- **Dual purchase options**: Restore previous settings vs create new room
- **Settings preview interface** showing saved room name, permissions count, and save date
- **Seamless permission restoration** automatically applying saved configurations
- **Invalid user handling** gracefully skipping users who left the server

**Commands:**
- `/privateroom_init`: (Admin) Initialize private room system with settings table
- `/privateroom_setup`: (Admin) Configure private room shop interface
- `/privateroom_reset`: (Admin) Reset entire private room system
- `/privateroom_list`: List all active private rooms with pagination
- `/privateroom_ban <user>`: (Admin) Ban user from private room system

**Shop Interface:**
- **🛍️ Purchase Button**: Buy new private room with intelligent settings detection
- **🔄 Restore Button**: Restore previously owned room if available within validity period
- **⚙️ Smart Settings Choice**: Automatically detects saved settings and offers restoration options

### Game_DnD_Cog
Advanced Dungeons & Dragons dice rolling system with comprehensive notation support.

**Features:**
- **Advanced dice notation** supporting complex expressions (3+4d6, 2d04 for 0-4 range)
- **Multiple roll support** with detailed breakdown of each roll
- **Zero-inclusive dice** (d06 for 0-6 range vs d6 for 1-6 range)
- **Batch rolling** with expression-based repetition (5#3+4d6)
- **Table format results** for easy reading

**Commands:**
- `/dnd_roll <expression> [x]`: Roll dice using DnD notation
  - Examples: `3+4d6` (roll 4 six-sided dice and add 3)
  - `d02` (roll 0-2 inclusive die)
  - `5#3+4d6` (repeat `3+4d6` roll 5 times)
  - Parameter `x` specifies repetition count (overridden by `#` in expression)

### Game_Spymode_Cog
Interactive spy-based team game system for voice channel activities.

**Features:**
- **Team formation system** with button-based signup
- **Voice channel validation** ensuring participants are in voice
- **Spy randomization** with secret DM notifications
- **Multi-stage game flow** from setup to reveal
- **Interactive buttons** for team management and game control

**Commands:**
- `/spy_mode <team_size> <spy>`: Create spy mode game with specified team size and spy count
  - Example: `/spy_mode 5 1` creates 5v5 teams with 1 spy per team

**Game Flow:**
1. **Setup Phase**: Define team sizes and spy counts
2. **Registration Phase**: Players join teams via buttons
3. **Game Start**: Spy assignments sent via DM
4. **Reveal Phase**: Show spy identities to all participants

### Ban_Cog
**🔨 Comprehensive moderation system** providing ban, tempban, and mute functionality with automated management.

**Key Features:**
- **Permanent bans** with configurable message deletion periods
- **Temporary bans** with automatic unban scheduling and DM notifications
- **Mute system** using Discord's native timeout feature (up to 28 days)
- **Admin permission system** with role and user-based access control
- **Notification system** with customizable channel alerts
- **Automatic recovery** of active tempbans after bot restart

**Enhanced Functionality:**
- **Duration parsing** supporting multiple formats (1m, 1h, 1d, 1w)
- **Database persistence** for tempban tracking and recovery
- **User DM notifications** with server rejoin links for tempbans
- **Rich embed notifications** with user avatars and timestamps
- **Comprehensive admin management** with role and user assignment

**Commands:**
- `/ban <user> <reason> [delete_message_days]`: Permanently ban a user
- `/tempban <user> <duration> <reason> [delete_message_days]`: Temporarily ban a user
- `/mute <user> <duration> <reason>`: Mute a user using Discord timeout
- `/ban_list_tempbans`: List all active temporary bans in the server
- `/ban_admin_list`: Display current admin permissions and settings
- `/ban_admin_add_role <role>`: Add role to ban admin permissions
- `/ban_admin_delete_role <role>`: Remove role from ban admin permissions
- `/ban_admin_add_user <user>`: Add user to ban admin permissions
- `/ban_admin_delete_user <user>`: Remove user from ban admin permissions
- `/ban_set_notification_channel <channel>`: Set ban notification channel
- `/ban_remove_notification_channel`: Remove ban notification channel
- `/ban_set_invite_link <invite_link>`: Set rejoin link for tempbanned users
- `/ban_remove_invite_link`: Remove rejoin link setting

---

## Utilities and Tools

### config
Enhanced configuration bridge with lazy loading and caching capabilities.
- **Multi-file configuration** support for different cog types
- **Lazy loading** improving startup performance
- **Configuration caching** reducing file I/O operations
- **Type-specific configuration** management

### channel_validator
Unified validation system supporting both Context and Interaction objects.
- **Admin channel validation** for command restrictions
- **Voice state checking** utilities for voice-dependent features
- **Flexible validation** supporting multiple Discord API patterns

### tickets_new_db
Comprehensive database manager for the new thread-based ticket system.
- **Thread-based ticket management** with full CRUD operations
- **Member tracking** with addition timestamps and relationship management
- **Statistics collection** for reporting and analytics
- **Configuration storage** in database for dynamic updates

### tickets_db
Legacy database manager for the original channel-based ticket system.
- **Channel-based ticket** management for compatibility
- **Archive functionality** for ticket data preservation
- **Statistics tracking** for legacy system monitoring

### file_utils
Enhanced file operations module with advanced capabilities.
- **Directory tree generation** for archive organization
- **File size validation** before processing
- **Automatic cleanup** of temporary files
- **Archive creation** with compression support

### media_handler
Media processing module with validation and security features.
- **File size validation** before download with configurable limits
- **Hash-based file naming** preventing conflicts and duplicates
- **Automatic directory creation** for organized storage
- **Size limit enforcement** for resource management

### shop_db
**🔥 Enhanced database integration module** for the comprehensive economy system.
- **Transaction tracking** with detailed logging and categorization
- **Balance management** with comprehensive audit trails
- **Advanced check-in streak tracking** with makeup support and accurate recalculation
- **Makeup check-in management** with monthly quota tracking and intelligent validation
- **Monthly statistics** generation for reporting and analytics
- **First check-in tracking** for makeup validation and user progress monitoring

### privateroom_db
**🏠 Enhanced database manager** for the intelligent private voice channel system.
- **Room ownership tracking** with comprehensive expiration management
- **Settings preservation system** with JSON-based permission storage
- **Purchase history** with pricing calculations and discount tracking
- **Activity-based discount** calculations for user engagement rewards
- **Automatic cleanup** of expired room data and settings with configurable retention
- **Permission restoration capabilities** with user/role validation and fallback handling

### achievement_db
**🏆 Comprehensive achievement tracking database manager** for user progress monitoring.
- **Multi-category achievement tracking** for messages, reactions, voice time, and giveaways
- **Monthly statistics system** with separate tracking for monthly achievements
- **Voice session management** with start/stop tracking and time calculation
- **Leaderboard generation** with ranking and extended leaderboard support
- **Manual operation logging** for admin adjustments with audit trails
- **Checkin integration** with shop system for total and streak-based achievements

### role_db
**🎭 Role assignment database manager** for interactive role systems.
- **View persistence management** for role selection interfaces across different types
- **Achievement progress queries** with unified data retrieval from multiple sources
- **Signature system management** with time-slot based change tracking and cooldowns
- **Voice time requirement checking** for signature permissions
- **Permission management** with user signature enable/disable functionality
- **Database operations** for role views, star sign, MBTI, gender, and signature systems

### ban_db
**🔨 Comprehensive moderation database manager** for the ban system.
- **Tempban tracking** with automatic expiration management
- **Ban history storage** with detailed logging and timestamps
- **Active tempban recovery** ensuring continuity after bot restarts
- **Database cleanup** of expired records with configurable retention
- **Admin permission persistence** with role and user tracking

---

## Update Log
### V1.6.4b - 2025-08-13
#### 🐛 Critical Bug Fixes
- Fixed an issue with ticket permissions, which now correctly uses private tickets.
- Fixed the archiving function for old tickets. Now you can conveniently archive old tickets with one click.
- Added a temporary command to convert non-private tickets in the new version to private tickets.

---
### V1.6.3b - 2025-07-08
#### 🐛 Critical Bug Fixes
- Quick fix for the achievement check crash when there are too many achievements.
---
### V1.6.2b - 2025-07-06
#### New Features
- Reconstructed the achievement cog and role cog. Used a more advanced database and logic separation architecture.
- Support for achievements related to total check-ins and consecutive check-ins has been created.
#### Bug Fixes
- Fixed an issue where the ‘Accept’ button displayed an incorrect status in closed tickets.

---
### V1.6.1 - 2025-07-04
#### 🐛 Critical Bug Fixes
- **TeamupDisplay System Fixes**: 
  - Optimised the display of the teamup dashboard and blocked the display of the @ section.
  
- **Old Tickets System**: 
  - Restored the `/tickets_archive` command to archive all tickets.
  
---
### V1.6.0b - 2025-07-02
#### 🆕 Major New Features
- **TeamupDisplay System Implementation**: Added comprehensive `TeamupDisplay_Cog` with real-time team organization capabilities
  - Real-time display board with automatic updates every 2 minutes
  - Game type categorization for organized teamup information
  - Automatic cleanup of expired invitations and invalid data
  - Discord integration with native time formatting and channel links

#### ⚠️ Important Changes
- **Rating System Removal**: Completely removed `Rating_Cog` functionality
  - All rating-related commands and features have been discontinued
  - Rating data will be preserved in database but no longer accessible through bot commands

### V1.5.2b - 2025-06-30
#### 🐛 Critical Bug Fixes
- **Ban System Fixes**: 
  - Fixed database unique errors
  - Fixed ban logging issues

---
### V1.5.1b - 2025-06-29
#### 🐛 Critical Bug Fixes
- **Tempban System Fixes**: Resolved major issues with temporary ban management
  - Fixed automatic unban logic that wasn't processing expired tempbans correctly
#### 📋 New Features
- **Administrative Tools**: 
  - `/ban_list_tempbans` - View all active temporary bans in the server
  - Improved startup logic with better expired tempban processing
---

### V1.5.0b - 2025-06-29
#### 🆕 Major New Features
- **Ban System Implementation**: Added comprehensive `Ban_Cog` with moderation capabilities
  - Permanent ban functionality with configurable message deletion
  - Temporary ban system with automatic unban scheduling
  - Mute system using Discord's native timeout feature
  - Advanced admin permission management with roles and users
  - Rich notification system with channel alerts and user DMs
  - Database persistence and automatic recovery after restarts

#### ⚠️ Important Changes
- **Tickets System Update**: Modified command structure in new ticket system
  - Updated command names and functionality for better user experience
  - Enhanced thread-based ticket management
- **Legacy Tickets Deprecation**: Old `Tickets_Cog` marked as deprecated
  - Legacy system will be removed in future versions
  - Users should migrate to `Tickets_New_Cog` for continued support
---

### V1.4.1b2 - 2025-06-17
#### 🐛 Bug Fixes
- Fixed an issue with close ticket number display in the new ticket system.

### V1.4.1b - 2025-06-17
#### 🎯 Major Feature Enhancements
- **Private room system extend**
  - Users can now extend their private rooms by one month in advance.
- **Check In make up**
  - Users can now spend a certain number of points each month to make up for three missed sign-ins.
---

### V1.4.0b - 2025-06-16
#### 🆕 Major New Features
- **Complete Ticket System Overhaul**: Introduced `Tickets_New_Cog` with thread-based architecture
  - Thread-based tickets using Discord's native functionality
  - Modal confirmations for ticket creation
  - Dynamic button states with persistent management
  - Comprehensive admin system with type-specific permissions
  - Automatic DM notifications with jump buttons
  - Rate-limited admin addition to prevent API limits

- **Dual Logging System**: Implemented separate logging for main application and keyword detection
  - Main application logs: `./data/bot.log`
  - Keyword detection logs: `./data/keyword_detection.log`
  - Enhanced `/check_log` command with `keyword_log` parameter
  - UTF-8 encoding support and configurable log paths
---