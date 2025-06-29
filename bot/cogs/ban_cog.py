import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

import aiofiles
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.utils import config, BanDatabaseManager, check_channel_validity


class RejoinServerView(discord.ui.View):
    def __init__(self, invite_link: str, button_label: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label=button_label,
            url=invite_link,
            style=discord.ButtonStyle.link
        ))


class BanCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_data = config.get_config('ban')
        self.db = BanDatabaseManager(config.get_config()['db_path'])
        self.tempban_tasks = {}
        self.bot.loop.create_task(self.initialize_db())
        self.cleanup_tempbans.start()
        self.check_expired_tempbans.start()

    def cog_unload(self):
        self.cleanup_tempbans.cancel()
        self.check_expired_tempbans.cancel()
        for task in self.tempban_tasks.values():
            task.cancel()

    async def initialize_db(self):
        """Initialize the database and recover existing tempbans."""
        await self.db.initialize_database()
        await self.recover_tempbans()

    async def save_config(self):
        """Save the current configuration back to the JSON file"""
        config_path = Path('./bot/config/config_ban.json')
        
        try:
            # Read existing config file
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                config_data = json.loads(content)
            
            # Update with current in-memory config
            config_data.update(self.config_data)
            
            # Write back to file with proper formatting
            async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(config_data, indent=2, ensure_ascii=False))
            
            # Reload config to get updated values
            from bot.utils.config import Config
            config_instance = Config()
            self.config_data = config_instance.reload_config('ban')
            
        except Exception as e:
            logging.error(f"Error saving ban config: {e}")

    async def is_admin_channel_only_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is in admin channel without sending error message"""
        # Reuse the same logic as check_channel_validity but return boolean only
        # This avoids duplicating the channel ID extraction and comparison logic
        main_config = config.get_config('main')
        admin_channel_id = main_config.get('admin_channel_id')
        
        if not admin_channel_id:
            return False
        
        # Same logic as check_channel_validity line 18-19 and 28
        channel_id = interaction.channel_id
        return channel_id == admin_channel_id

    async def recover_tempbans(self):
        """Recover active tempbans from database after bot restart."""
        try:
            active_tempbans = await self.db.get_active_tempbans()
            current_time = discord.utils.utcnow()
            
            for tempban in active_tempbans:
                tempban_id, user_id, guild_id, banned_by, reason, banned_at, unban_at, delete_message_days = tempban
                # Ensure unban_time is timezone-aware
                if isinstance(unban_at, str):
                    unban_time = datetime.fromisoformat(unban_at.replace('Z', '+00:00'))
                elif isinstance(unban_at, datetime):
                    # If it's already a datetime object, make sure it's timezone-aware
                    unban_time = unban_at.replace(tzinfo=discord.utils.utc) if unban_at.tzinfo is None else unban_at
                else:
                    # Handle SQLite datetime objects
                    unban_time = datetime.fromisoformat(str(unban_at)).replace(tzinfo=discord.utils.utc)
                
                # Skip if already expired
                if unban_time <= current_time:
                    continue
                
                # Get guild and user objects
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                try:
                    user = await self.bot.fetch_user(user_id)
                except:
                    continue
                
                # Schedule the unban
                await self.schedule_unban_with_db(guild, user, unban_time, tempban_id)
                
            logging.info(f"Recovered {len(active_tempbans)} active tempbans")
        except Exception as e:
            logging.error(f"Failed to recover tempbans: {e}")

    @tasks.loop(minutes=5)
    async def check_expired_tempbans(self):
        """Check for expired tempbans and process them."""
        try:
            expired_tempbans = await self.db.get_expired_tempbans()
            
            for tempban in expired_tempbans:
                tempban_id, user_id, guild_id, banned_by, reason, banned_at, unban_at, delete_message_days = tempban
                
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    await self.db.deactivate_tempban(tempban_id)
                    continue
                
                try:
                    user = await self.bot.fetch_user(user_id)
                    await guild.unban(user, reason="Automatic unban after tempban period")
                    await self.db.deactivate_tempban(tempban_id)
                    
                    # Clean up task if exists
                    if user_id in self.tempban_tasks:
                        self.tempban_tasks[user_id].cancel()
                        del self.tempban_tasks[user_id]
                    
                    logging.info(f"Automatically unbanned user {user_id} from guild {guild_id}")
                except Exception as e:
                    logging.error(f"Failed to unban user {user_id}: {e}")
                    await self.db.deactivate_tempban(tempban_id)
                    
        except Exception as e:
            logging.error(f"Error checking expired tempbans: {e}")

    async def has_ban_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to use ban commands"""
        member = interaction.user
        
        # Check if user has administrator permission
        if member.guild_permissions.administrator:
            return True
        
        # Check admin roles
        admin_roles = self.config_data.get('admin_roles', [])
        if any(role.id in admin_roles for role in member.roles):
            return True
        
        # Check admin users
        admin_users = self.config_data.get('admin_users', [])
        if member.id in admin_users:
            return True
        
        return False

    def parse_duration(self, duration_str: str) -> Optional[timedelta]:
        """Parse duration string (e.g., '1d', '2h', '30m') to timedelta"""
        pattern = r'^(\d+)([mhdw])$'
        match = re.match(pattern, duration_str.lower())
        
        if not match:
            return None
        
        amount, unit = match.groups()
        amount = int(amount)
        
        if amount == 0:
            return None
        
        if unit == 'm':
            return timedelta(minutes=amount)
        elif unit == 'h':
            return timedelta(hours=amount)
        elif unit == 'd':
            return timedelta(days=amount)
        elif unit == 'w':
            return timedelta(weeks=amount)
        
        return None

    async def send_ban_notification(self, user: discord.User, reason: str, duration: Optional[str] = None, unban_time: Optional[datetime] = None):
        """Send ban notification to configured channel"""
        channel_id = self.config_data.get('ban_notification_channel_id')
        if not channel_id:
            return
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        
        messages = self.config_data.get('messages', {})
        
        # Create embed
        if duration:
            title = messages.get('tempban_notification_title', 'User Temporarily Banned')
            description = messages.get('tempban_notification_description', 'User {user} has been temporarily banned')
        else:
            title = messages.get('ban_notification_title', 'User Banned')
            description = messages.get('ban_notification_description', 'User {user} has been banned')
        
        embed = discord.Embed(
            title=title,
            description=description.format(user=user.mention),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        
        # Set bot avatar as thumbnail
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        # Add user avatar to footer
        embed.set_footer(
            text=f"User: {user.display_name}",
            icon_url=user.display_avatar.url
        )
        
        # Add fields
        embed.add_field(
            name=messages.get('reason_field', 'Reason'),
            value=reason or messages.get('no_reason', 'No reason provided'),
            inline=False
        )
        
        if duration:
            embed.add_field(
                name=messages.get('duration_field', 'Duration'),
                value=duration,
                inline=True
            )
            
            if unban_time:
                embed.add_field(
                    name=messages.get('unban_time_field', 'Unban Time'),
                    value=f"<t:{int(unban_time.timestamp())}:F>",
                    inline=True
                )
        else:
            embed.add_field(
                name=messages.get('duration_field', 'Duration'),
                value=messages.get('permanent', 'Permanent'),
                inline=True
            )
        
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logging.error(f"Failed to send ban notification for user {user.id}")

    async def send_mute_notification(self, user: discord.User, reason: str, duration: str, unmute_time: datetime):
        """Send mute notification to configured channel"""
        channel_id = self.config_data.get('ban_notification_channel_id')
        if not channel_id:
            return
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        
        messages = self.config_data.get('messages', {})
        
        # Create embed
        title = messages.get('mute_notification_title', 'User Muted')
        description = messages.get('mute_notification_description', 'User {user} has been muted')
        
        embed = discord.Embed(
            title=title,
            description=description.format(user=user.mention),
            color=discord.Color.yellow(),
            timestamp=discord.utils.utcnow()
        )
        
        # Set bot avatar as thumbnail
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        # Add user avatar to footer
        embed.set_footer(
            text=f"User: {user.display_name}",
            icon_url=user.display_avatar.url
        )
        
        # Add fields
        embed.add_field(
            name=messages.get('mute_reason_field', 'Reason'),
            value=reason or messages.get('no_reason', 'No reason provided'),
            inline=False
        )
        
        embed.add_field(
            name=messages.get('mute_duration_field', 'Duration'),
            value=duration,
            inline=True
        )
        
        embed.add_field(
            name=messages.get('mute_end_time_field', 'Unmute Time'),
            value=f"<t:{int(unmute_time.timestamp())}:F>",
            inline=True
        )
        
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logging.error(f"Failed to send mute notification for user {user.id}")

    async def send_tempban_dm(self, user: discord.User, guild: discord.Guild, reason: str, duration: str, unban_time: datetime):
        """Send tempban notification DM to user"""
        try:
            messages = self.config_data.get('messages', {})
            
            # Create embed for DM
            embed = discord.Embed(
                title=messages.get('tempban_dm_title', 'You have been temporarily banned'),
                description=messages.get('tempban_dm_description', 'You have been temporarily banned from **{guild_name}**.').format(guild_name=guild.name),
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            
            # Set guild icon as thumbnail
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            
            # Add fields
            embed.add_field(
                name=messages.get('tempban_dm_reason_field', 'Reason'),
                value=reason,
                inline=False
            )
            
            embed.add_field(
                name=messages.get('tempban_dm_duration_field', 'Duration'),
                value=duration,
                inline=True
            )
            
            embed.add_field(
                name=messages.get('tempban_dm_unban_time_field', 'Unban Time'),
                value=f"<t:{int(unban_time.timestamp())}:F>",
                inline=True
            )
            
            # Set footer
            embed.set_footer(
                text=messages.get('tempban_dm_footer', 'You can rejoin the server after the ban ends.'),
                icon_url=user.display_avatar.url
            )
            
            # Create view with rejoin button if invite link is set
            view = None
            invite_link = self.config_data.get('invite_link')
            if invite_link:
                view = RejoinServerView(invite_link, messages.get('rejoin_button_label', 'Rejoin Server'))
            
            # Send DM
            await user.send(embed=embed, view=view)
            logging.info(f"Sent tempban DM to user {user.id}")
            
        except discord.Forbidden:
            logging.warning(f"Cannot send DM to user {user.id} - DMs disabled or blocked")
        except Exception as e:
            logging.error(f"Failed to send tempban DM to user {user.id}: {e}")

    async def schedule_unban_with_db(self, guild: discord.Guild, user: discord.User, unban_time: datetime, tempban_id: int):
        """Schedule automatic unban with database integration"""
        async def unban_task():
            try:
                await discord.utils.sleep_until(unban_time)
                await guild.unban(user, reason="Automatic unban after tempban period")
                
                # Mark as inactive in database
                await self.db.deactivate_tempban(tempban_id)
                
                # Clean up task
                if user.id in self.tempban_tasks:
                    del self.tempban_tasks[user.id]
                
                logging.info(f"Automatically unbanned user {user.id} from guild {guild.id}")
            except Exception as e:
                logging.error(f"Failed to automatically unban user {user.id}: {e}")
                # Still mark as inactive in database even if unban failed
                await self.db.deactivate_tempban(tempban_id)
                if user.id in self.tempban_tasks:
                    del self.tempban_tasks[user.id]
        
        # Cancel existing task if any
        if user.id in self.tempban_tasks:
            self.tempban_tasks[user.id].cancel()
        
        # Create new task
        task = self.bot.loop.create_task(unban_task())
        self.tempban_tasks[user.id] = task

    @tasks.loop(minutes=5)
    async def cleanup_tempbans(self):
        """Clean up completed tempban tasks"""
        completed_tasks = [user_id for user_id, task in self.tempban_tasks.items() if task.done()]
        for user_id in completed_tasks:
            del self.tempban_tasks[user_id]

    @app_commands.command(name="ban", description="Ban a user from the server")
    @app_commands.describe(
        user="The user to ban",
        reason="Reason for the ban",
        delete_message_days="Number of days of messages to delete (0-7)"
    )
    async def ban_command(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: str,
        delete_message_days: Optional[int] = 0
    ):
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Validate delete_message_days
        if delete_message_days is None:
            delete_message_days = 0
        elif delete_message_days < 0 or delete_message_days > 7:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('invalid_delete_days', 'Delete message days must be between 0 and 7.'),
                ephemeral=False
            )
            return
        
        try:
            # Ban the user
            await interaction.guild.ban(
                user,
                reason=reason,
                delete_message_days=delete_message_days
            )
            
            # Send success response
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('ban_success', 'User {user} has been banned.').format(user=user.mention),
                ephemeral=False
            )
            
            # Send notification
            await self.send_ban_notification(user, reason)
            
            logging.info(f"User {user.id} banned by {interaction.user.id} in guild {interaction.guild.id}")
            
        except discord.Forbidden:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('ban_failed_permissions', 'Failed to ban user. Missing permissions.'),
                ephemeral=False
            )
        except discord.HTTPException as e:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('ban_failed_error', 'Failed to ban user due to an error.'),
                ephemeral=False
            )
            logging.error(f"Failed to ban user {user.id}: {e}")

    @app_commands.command(name="tempban", description="Temporarily ban a user from the server")
    @app_commands.describe(
        user="The user to temporarily ban",
        duration="Duration of the ban (e.g., 1m, 1h, 1d, 1w)",
        reason="Reason for the ban",
        delete_message_days="Number of days of messages to delete (0-7)"
    )
    async def tempban_command(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        duration: str,
        reason: str,
        delete_message_days: Optional[int] = 0
    ):
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Parse duration
        ban_duration = self.parse_duration(duration)
        if not ban_duration:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('invalid_duration', 'Invalid duration format. Use formats like: 1m, 1h, 1d, 1w (minimum 1 minute).'),
                ephemeral=False
            )
            return
        
        # Check minimum duration (1 minute)
        if ban_duration < timedelta(minutes=1):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('duration_too_short', 'Ban duration must be at least 1 minute.'),
                ephemeral=False
            )
            return
        
        # Validate delete_message_days
        if delete_message_days is None:
            delete_message_days = 0
        elif delete_message_days < 0 or delete_message_days > 7:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('invalid_delete_days', 'Delete message days must be between 0 and 7.'),
                ephemeral=False
            )
            return
        
        try:
            # Ban the user
            await interaction.guild.ban(
                user,
                reason=f"Temporary ban: {reason} (Duration: {duration})",
                delete_message_days=delete_message_days
            )
            
            # Calculate unban time (use timezone-aware datetime)
            unban_time = discord.utils.utcnow() + ban_duration
            
            # Save to database
            tempban_id = await self.db.add_tempban(
                user.id, 
                interaction.guild.id, 
                interaction.user.id, 
                reason, 
                unban_time, 
                delete_message_days
            )
            
            # Schedule unban
            await self.schedule_unban_with_db(interaction.guild, user, unban_time, tempban_id)
            
            # Send success response
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('tempban_success', 'User {user} has been temporarily banned for {duration}.').format(
                    user=user.mention,
                    duration=duration
                ),
                ephemeral=False
            )
            
            # Send notification
            await self.send_ban_notification(user, reason, duration, unban_time)
            
            # Send DM to user
            await self.send_tempban_dm(user, interaction.guild, reason, duration, unban_time)
            
            logging.info(f"User {user.id} temporarily banned for {duration} by {interaction.user.id} in guild {interaction.guild.id}")
            
        except discord.Forbidden:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('ban_failed_permissions', 'Failed to ban user. Missing permissions.'),
                ephemeral=False
            )
        except discord.HTTPException as e:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('ban_failed_error', 'Failed to ban user due to an error.'),
                ephemeral=False
            )
            logging.error(f"Failed to temporarily ban user {user.id}: {e}")

    @app_commands.command(name="mute", description="Mute a user in the server")
    @app_commands.describe(
        user="The user to mute",
        duration="Duration of the mute (e.g., 1m, 1h, 1d, 1w)",
        reason="Reason for the mute"
    )
    async def mute_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: str,
        reason: str
    ):
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Parse duration
        mute_duration = self.parse_duration(duration)
        if not mute_duration:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('invalid_duration', 'Invalid duration format. Use formats like: 1m, 1h, 1d, 1w (minimum 1 minute).'),
                ephemeral=False
            )
            return
        
        # Check minimum duration (1 minute)
        if mute_duration < timedelta(minutes=1):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('duration_too_short', 'Mute duration must be at least 1 minute.'),
                ephemeral=False
            )
            return
        
        # Check maximum duration (28 days - Discord timeout limit)
        if mute_duration > timedelta(days=28):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('mute_duration_too_long', 'Mute duration cannot exceed 28 days (Discord limit).'),
                ephemeral=False
            )
            return
        
        try:
            # Calculate unmute time
            unmute_time = discord.utils.utcnow() + mute_duration
            
            # Mute the user using Discord's timeout feature
            await user.timeout(unmute_time, reason=reason)
            
            # Send success response
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('mute_success', 'User {user} has been muted for {duration}.').format(
                    user=user.mention,
                    duration=duration
                ),
                ephemeral=False
            )
            
            # Send notification
            await self.send_mute_notification(user, reason, duration, unmute_time)
            
            logging.info(f"User {user.id} muted for {duration} by {interaction.user.id} in guild {interaction.guild.id}")
            
        except discord.Forbidden:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('mute_failed_permissions', 'Failed to mute user. Missing permissions.'),
                ephemeral=False
            )
        except discord.HTTPException as e:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('mute_failed_error', 'Failed to mute user due to an error.'),
                ephemeral=False
            )
            logging.error(f"Failed to mute user {user.id}: {e}")

    @app_commands.command(name="ban_admin_list", description="Show current ban admin permissions")
    async def ban_admin_list(self, interaction: discord.Interaction):
        """Show current ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('admin_channel_only', 'This command can only be used in the admin channel.'),
                ephemeral=False
            )
            return
        
        # Get current permissions
        admin_roles = self.config_data.get('admin_roles', [])
        admin_users = self.config_data.get('admin_users', [])
        
        messages = self.config_data.get('messages', {})
        embed = discord.Embed(
            title=messages.get('admin_list_title', 'Ban Admin Permissions'),
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Admin roles
        if admin_roles:
            role_mentions = []
            for role_id in admin_roles:
                role = interaction.guild.get_role(role_id)
                if role:
                    role_mentions.append(role.mention)
                else:
                    role_mentions.append(f"<@&{role_id}> (不存在)")
            
            embed.add_field(
                name=messages.get('admin_roles_title', 'Admin Roles'),
                value='\n'.join(role_mentions) if role_mentions else messages.get('none', 'None'),
                inline=False
            )
        else:
            embed.add_field(
                name=messages.get('admin_roles_title', 'Admin Roles'),
                value=messages.get('none', 'None'),
                inline=False
            )
        
        # Admin users
        if admin_users:
            user_mentions = []
            for user_id in admin_users:
                try:
                    user = await self.bot.fetch_user(user_id)
                    user_mentions.append(f"{user.mention} ({user.display_name})")
                except:
                    user_mentions.append(f"<@{user_id}> (不存在)")
            
            embed.add_field(
                name=messages.get('admin_users_title', 'Admin Users'),
                value='\n'.join(user_mentions) if user_mentions else messages.get('none', 'None'),
                inline=False
            )
        else:
            embed.add_field(
                name=messages.get('admin_users_title', 'Admin Users'),
                value=messages.get('none', 'None'),
                inline=False
            )
        
        # Ban notification channel
        notification_channel_id = self.config_data.get('ban_notification_channel_id')
        if notification_channel_id:
            notification_channel = interaction.guild.get_channel(notification_channel_id)
            if notification_channel:
                channel_text = notification_channel.mention
            else:
                channel_text = f"<#{notification_channel_id}> (不存在)"
        else:
            channel_text = messages.get('none', 'None')
        
        embed.add_field(
            name=messages.get('notification_channel_title', 'Notification Channel'),
            value=channel_text,
            inline=False
        )
        
        # Invite link
        invite_link = self.config_data.get('invite_link')
        if invite_link:
            invite_text = f"[点击查看]({invite_link})"
        else:
            invite_text = messages.get('none', 'None')
        
        embed.add_field(
            name="🔗 邀请链接",
            value=invite_text,
            inline=False
        )
        
        # Set footer with admin note
        embed.set_footer(
            text=messages.get('admin_note', 'Users with Administrator permission can also use ban commands.')
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="ban_admin_add_role", description="Add a role to ban admin permissions")
    @app_commands.describe(role="The role to add to ban admin permissions")
    async def ban_admin_add_role(self, interaction: discord.Interaction, role: discord.Role):
        """Add a role to ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('admin_channel_only', 'This command can only be used in the admin channel.'),
                ephemeral=False
            )
            return
        
        # Check if role is already in admin roles
        admin_roles = self.config_data.get('admin_roles', [])
        if role.id in admin_roles:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('role_already_admin', 'Role {role} is already an admin role.').format(role=role.mention),
                ephemeral=False
            )
            return
        
        # Add role to admin roles
        admin_roles.append(role.id)
        self.config_data['admin_roles'] = admin_roles
        
        # Save config
        await self.save_config()
        
        messages = self.config_data.get('messages', {})
        await interaction.response.send_message(
            messages.get('role_added_success', 'Role {role} has been added to ban admin permissions.').format(role=role.mention),
            ephemeral=False
        )

    @app_commands.command(name="ban_admin_delete_role", description="Remove a role from ban admin permissions")
    @app_commands.describe(role="The role to remove from ban admin permissions")
    async def ban_admin_delete_role(self, interaction: discord.Interaction, role: discord.Role):
        """Remove a role from ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('admin_channel_only', 'This command can only be used in the admin channel.'),
                ephemeral=False
            )
            return
        
        # Check if role is in admin roles
        admin_roles = self.config_data.get('admin_roles', [])
        if role.id not in admin_roles:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('role_not_admin', 'Role {role} is not an admin role.').format(role=role.mention),
                ephemeral=False
            )
            return
        
        # Remove role from admin roles
        admin_roles.remove(role.id)
        self.config_data['admin_roles'] = admin_roles
        
        # Save config
        await self.save_config()
        
        messages = self.config_data.get('messages', {})
        await interaction.response.send_message(
            messages.get('role_removed_success', 'Role {role} has been removed from ban admin permissions.').format(role=role.mention),
            ephemeral=False
        )

    @app_commands.command(name="ban_admin_add_user", description="Add a user to ban admin permissions")
    @app_commands.describe(user="The user to add to ban admin permissions")
    async def ban_admin_add_user(self, interaction: discord.Interaction, user: discord.User):
        """Add a user to ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('admin_channel_only', 'This command can only be used in the admin channel.'),
                ephemeral=False
            )
            return
        
        # Check if user is already in admin users
        admin_users = self.config_data.get('admin_users', [])
        if user.id in admin_users:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('user_already_admin', 'User {user} is already an admin user.').format(user=user.mention),
                ephemeral=False
            )
            return
        
        # Add user to admin users
        admin_users.append(user.id)
        self.config_data['admin_users'] = admin_users
        
        # Save config
        await self.save_config()
        
        messages = self.config_data.get('messages', {})
        await interaction.response.send_message(
            messages.get('user_added_success', 'User {user} has been added to ban admin permissions.').format(user=user.mention),
            ephemeral=False
        )

    @app_commands.command(name="ban_admin_delete_user", description="Remove a user from ban admin permissions")
    @app_commands.describe(user="The user to remove from ban admin permissions")
    async def ban_admin_delete_user(self, interaction: discord.Interaction, user: discord.User):
        """Remove a user from ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('admin_channel_only', 'This command can only be used in the admin channel.'),
                ephemeral=False
            )
            return
        
        # Check if user is in admin users
        admin_users = self.config_data.get('admin_users', [])
        if user.id not in admin_users:
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('user_not_admin', 'User {user} is not an admin user.').format(user=user.mention),
                ephemeral=False
            )
            return
        
        # Remove user from admin users
        admin_users.remove(user.id)
        self.config_data['admin_users'] = admin_users
        
        # Save config
        await self.save_config()
        
        messages = self.config_data.get('messages', {})
        await interaction.response.send_message(
            messages.get('user_removed_success', 'User {user} has been removed from ban admin permissions.').format(user=user.mention),
            ephemeral=False
        )

    @app_commands.command(name="ban_set_notification_channel", description="Set the channel for ban notifications")
    @app_commands.describe(channel="The channel where ban notifications will be sent")
    async def ban_set_notification_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the ban notification channel"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('admin_channel_only', 'This command can only be used in the admin channel.'),
                ephemeral=False
            )
            return
        
        # Set the notification channel
        self.config_data['ban_notification_channel_id'] = channel.id
        
        # Save config
        await self.save_config()
        
        messages = self.config_data.get('messages', {})
        await interaction.response.send_message(
            messages.get('notification_channel_set', 'Ban notification channel has been set to {channel}.').format(channel=channel.mention),
            ephemeral=False
        )

    @app_commands.command(name="ban_remove_notification_channel", description="Remove the ban notification channel")
    async def ban_remove_notification_channel(self, interaction: discord.Interaction):
        """Remove the ban notification channel"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('admin_channel_only', 'This command can only be used in the admin channel.'),
                ephemeral=False
            )
            return
        
        # Check if notification channel is set
        if not self.config_data.get('ban_notification_channel_id'):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('notification_channel_not_set', 'Ban notification channel is not set.'),
                ephemeral=False
            )
            return
        
        # Remove the notification channel
        self.config_data['ban_notification_channel_id'] = None
        
        # Save config
        await self.save_config()
        
        messages = self.config_data.get('messages', {})
        await interaction.response.send_message(
            messages.get('notification_channel_removed', 'Ban notification channel has been removed.'),
            ephemeral=False
        )

    @app_commands.command(name="ban_set_invite_link", description="Set the invite link for tempbanned users")
    @app_commands.describe(invite_link="The permanent invite link for rejoining the server")
    async def ban_set_invite_link(self, interaction: discord.Interaction, invite_link: str):
        """Set the invite link for tempbanned users"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('admin_channel_only', 'This command can only be used in the admin channel.'),
                ephemeral=False
            )
            return
        
        # Validate invite link format (basic check)
        if not (invite_link.startswith('https://discord.gg/') or invite_link.startswith('https://discord.com/invite/')):
            await interaction.response.send_message(
                "请提供有效的Discord邀请链接 (格式: https://discord.gg/xxx 或 https://discord.com/invite/xxx)",
                ephemeral=False
            )
            return
        
        # Set the invite link
        self.config_data['invite_link'] = invite_link
        
        # Save config
        await self.save_config()
        
        messages = self.config_data.get('messages', {})
        await interaction.response.send_message(
            messages.get('invite_link_set', 'Invite link has been set to: {link}').format(link=invite_link),
            ephemeral=False
        )

    @app_commands.command(name="ban_remove_invite_link", description="Remove the invite link for tempbanned users")
    async def ban_remove_invite_link(self, interaction: discord.Interaction):
        """Remove the invite link for tempbanned users"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('no_permission', 'You do not have permission to use this command.'),
                ephemeral=False
            )
            return
        
        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('admin_channel_only', 'This command can only be used in the admin channel.'),
                ephemeral=False
            )
            return
        
        # Check if invite link is set
        if not self.config_data.get('invite_link'):
            messages = self.config_data.get('messages', {})
            await interaction.response.send_message(
                messages.get('invite_link_not_set', 'Invite link is not set.'),
                ephemeral=False
            )
            return
        
        # Remove the invite link
        self.config_data['invite_link'] = None
        
        # Save config
        await self.save_config()
        
        messages = self.config_data.get('messages', {})
        await interaction.response.send_message(
            messages.get('invite_link_removed', 'Invite link has been removed.'),
            ephemeral=False
        )


async def setup(bot):
    await bot.add_cog(BanCog(bot))