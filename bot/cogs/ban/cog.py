import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands, tasks

from bot.utils import BanDatabaseManager, config
from bot.utils.i18n import t
from bot.utils.task_helpers import wait_until_ready_or_stop

from .service import (
    build_ban_notification_embed,
    build_mute_dm_embed,
    build_mute_notification_embed,
    build_tempban_dm_embed,
    is_admin_channel,
    is_valid_discord_invite_link,
    member_has_ban_permission,
    parse_duration,
)
from .views import RejoinServerView


class BanCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_data = config.get_config('ban')
        self.db = BanDatabaseManager(config.get_config()['db_path'])
        self.tempban_tasks = {}
        self._tempban_recovery_done = False
        self.cleanup_tempbans.start()
        self.check_expired_tempbans.start()

    def cog_unload(self):
        self.cleanup_tempbans.cancel()
        self.check_expired_tempbans.cancel()
        for task in self.tempban_tasks.values():
            task.cancel()

    async def cog_load(self):
        await self.db.initialize_database()

    @commands.Cog.listener()
    async def on_ready(self):
        # READY can fire on every reconnect; recover tempbans only once per process
        # and only after the guild cache is populated so bot.get_guild() resolves.
        if self._tempban_recovery_done:
            return
        self._tempban_recovery_done = True
        await self.recover_tempbans()

    async def save_config(self):
        """Persist ban config via the unified writer (see P2-3).

        Delegates to ``config.save_config('ban', ...)`` which round-trips
        through ruamel.yaml (comments on each admin role / user id entry
        are preserved), writes atomically via tempfile + os.replace,
        and reloads the in-memory cache. If the write fails (disk full,
        permission error), the error is logged and state is not
        clobbered — admins can retry.
        """
        try:
            reloaded = await config.save_config('ban', self.config_data)
            self.config_data = reloaded
        except Exception as e:
            logging.error(f"Error saving ban config: {e}")

    async def is_admin_channel_only_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is in admin channel without sending error message"""
        main_config = config.get_config('main')
        admin_channel_id = main_config.get('admin_channel_id')
        return is_admin_channel(interaction.channel_id, admin_channel_id)

    async def recover_tempbans(self):
        """Recover active tempbans from database after bot restart."""
        try:
            # 使用新方法获取所有活跃的tempbans（包括过期的）
            active_tempbans = await self.db.get_all_active_tempbans_including_expired()
            current_time = discord.utils.utcnow()
            expired_count = 0
            recovered_count = 0

            for tempban in active_tempbans:
                tempban_id, user_id, guild_id, banned_by, reason, banned_at, unban_at, delete_message_days = tempban
                # Ensure unban_time is timezone-aware
                if isinstance(unban_at, str):
                    unban_time = datetime.fromisoformat(unban_at.replace('Z', '+00:00'))
                    if unban_time.tzinfo is None:
                        unban_time = unban_time.replace(tzinfo=discord.utils.utc)
                elif isinstance(unban_at, datetime):
                    # If it's already a datetime object, make sure it's timezone-aware
                    unban_time = unban_at.replace(tzinfo=discord.utils.utc) if unban_at.tzinfo is None else unban_at
                else:
                    # Handle SQLite datetime objects
                    unban_time = datetime.fromisoformat(str(unban_at))
                    if unban_time.tzinfo is None:
                        unban_time = unban_time.replace(tzinfo=discord.utils.utc)

                # Get guild object
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    # Mark as inactive if guild not found
                    success = await self.db.deactivate_tempban(tempban_id)
                    logging.info(f"Deactivated tempban {tempban_id} - guild {guild_id} not found - success: {success}")
                    continue

                # Process expired tempbans
                if unban_time <= current_time:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        # Try to unban the user
                        await guild.unban(user, reason="Automatic unban after tempban period (startup recovery)")
                        logging.info(f"Unbanned expired tempban user {user_id} from guild {guild_id}")
                    except discord.NotFound:
                        # User was already unbanned
                        logging.info(f"User {user_id} was already unbanned from guild {guild_id}")
                    except Exception as e:
                        logging.warning(f"Failed to unban expired tempban user {user_id}: {e}")

                    # Mark as inactive in database regardless
                    success = await self.db.deactivate_tempban(tempban_id)
                    if success:
                        expired_count += 1
                        logging.info(f"Successfully deactivated expired tempban {tempban_id}")
                    else:
                        logging.error(f"Failed to deactivate expired tempban {tempban_id}")
                    continue

                # Schedule future unbans for active tempbans
                try:
                    user = await self.bot.fetch_user(user_id)
                    await self.schedule_unban_with_db(guild, user, unban_time, tempban_id)
                    recovered_count += 1
                except Exception as e:
                    logging.warning(f"Failed to recover tempban for user {user_id}: {e}")
                    # Mark as inactive if we can't recover it
                    await self.db.deactivate_tempban(tempban_id)

            logging.info(f"Tempban recovery completed: {recovered_count} recovered, {expired_count} expired and processed")
        except Exception as e:
            logging.error(f"Failed to recover tempbans: {e}", exc_info=True)

    @tasks.loop(minutes=5)
    async def check_expired_tempbans(self):
        """Check for expired tempbans and process them."""
        # Wait for bot to be ready
        if not self.bot.is_ready():
            return

        try:
            expired_tempbans = await self.db.get_expired_tempbans()

            if expired_tempbans:
                logging.info(f"Processing {len(expired_tempbans)} expired tempbans")

            for tempban in expired_tempbans:
                tempban_id, user_id, guild_id, banned_by, reason, banned_at, unban_at, delete_message_days = tempban

                guild = self.bot.get_guild(guild_id)
                if not guild:
                    success = await self.db.deactivate_tempban(tempban_id)
                    logging.warning(f"Guild {guild_id} not found, deactivating tempban {tempban_id} - success: {success}")
                    continue

                try:
                    user = await self.bot.fetch_user(user_id)
                    await guild.unban(user, reason="Automatic unban after tempban period")
                    logging.info(f"Successfully unbanned user {user_id} from guild {guild_id}")
                except discord.NotFound:
                    # User was already unbanned
                    logging.info(f"User {user_id} was already unbanned from guild {guild_id}")
                except Exception as e:
                    logging.error(f"Failed to unban user {user_id}: {e}")

                # Always deactivate the tempban in database
                success = await self.db.deactivate_tempban(tempban_id)
                if success:
                    logging.info(f"Successfully deactivated tempban {tempban_id}")
                else:
                    logging.error(f"Failed to deactivate tempban {tempban_id} in database")

                # Clean up task if exists
                if user_id in self.tempban_tasks:
                    self.tempban_tasks[user_id].cancel()
                    del self.tempban_tasks[user_id]

        except Exception as e:
            logging.error(f"Error checking expired tempbans: {e}", exc_info=True)

    @check_expired_tempbans.before_loop
    async def before_check_expired_tempbans(self):
        """Wait for bot to be ready before starting the loop."""
        await wait_until_ready_or_stop(
            self.bot,
            self.check_expired_tempbans,
            'BanCog.check_expired_tempbans',
        )

    async def has_ban_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to use ban commands"""
        return member_has_ban_permission(interaction.user, self.config_data)

    def parse_duration(self, duration_str: str) -> Optional[timedelta]:
        """Parse duration string (e.g., '1d', '2h', '30m') to timedelta"""
        return parse_duration(duration_str)

    async def send_ban_notification(self, user: discord.User, reason: str, duration: Optional[str] = None,
                                    unban_time: Optional[datetime] = None):
        """Send ban notification to configured channel"""
        channel_id = self.config_data.get('ban_notification_channel_id')
        if not channel_id:
            logging.warning("Ban notification channel ID not configured")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            logging.error(f"Ban notification channel {channel_id} not found")
            return

        # 添加权限检查日志
        guild = channel.guild
        bot_member = guild.get_member(self.bot.user.id)
        perms = channel.permissions_for(bot_member)

        if not perms.send_messages:
            logging.error(f"Bot lacks Send Messages permission in channel {channel_id}")
            return

        if not perms.embed_links:
            logging.error(f"Bot lacks Embed Links permission in channel {channel_id}")
            return

        embed = build_ban_notification_embed(
            self.bot.user,
            user,
            reason,
            duration,
            unban_time,
        )

        try:
            await channel.send(embed=embed)
            logging.info(f"Successfully sent ban notification for user {user.id} to channel {channel_id}")
        except discord.Forbidden:
            logging.error(f"Bot lacks permission to send message in channel {channel_id}")
        except discord.HTTPException as e:
            logging.error(f"Failed to send ban notification for user {user.id}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error sending ban notification: {type(e).__name__}: {e}")

    async def send_mute_notification(self, user: discord.User, reason: str, duration: str, unmute_time: datetime):
        """Send mute notification to configured channel"""
        channel_id = self.config_data.get('ban_notification_channel_id')
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        embed = build_mute_notification_embed(
            self.bot.user,
            user,
            reason,
            duration,
            unmute_time,
        )

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logging.error(f"Failed to send mute notification for user {user.id}")

    async def send_tempban_dm(self, user: discord.User, guild: discord.Guild, reason: str, duration: str, unban_time: datetime):
        """Send tempban notification DM to user"""
        try:
            embed = build_tempban_dm_embed(user, guild, reason, duration, unban_time)

            # Create view with rejoin button if invite link is set
            view = None
            invite_link = self.config_data.get('invite_link')
            if invite_link:
                view = RejoinServerView(invite_link, t('ban.rejoin_button_label'))

            # Send DM
            await user.send(embed=embed, view=view)
            logging.info(f"Sent tempban DM to user {user.id}")

        except discord.Forbidden:
            logging.warning(f"Cannot send DM to user {user.id} - DMs disabled or blocked")
        except Exception as e:
            logging.error(f"Failed to send tempban DM to user {user.id}: {e}")

    async def send_mute_dm(self, user: discord.User, guild: discord.Guild, reason: str, duration: str, unmute_time: datetime):
        """Send mute notification DM to user"""
        try:
            embed = build_mute_dm_embed(user, guild, reason, duration, unmute_time)

            # Send DM
            await user.send(embed=embed)
            logging.info(f"Sent mute DM to user {user.id}")

        except discord.Forbidden:
            logging.warning(f"Cannot send DM to user {user.id} - DMs disabled or blocked")
        except Exception as e:
            logging.error(f"Failed to send mute DM to user {user.id}: {e}")

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
        task = asyncio.create_task(unban_task())
        self.tempban_tasks[user.id] = task

    @tasks.loop(minutes=5)
    async def cleanup_tempbans(self):
        """Clean up completed tempban tasks"""
        completed_tasks = [user_id for user_id, task in self.tempban_tasks.items() if task.done()]
        for user_id in completed_tasks:
            del self.tempban_tasks[user_id]

    @app_commands.command(
        name="ban",
        description=locale_str(
            "Ban a user from the server",
            key="ban.ban.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "The user to ban",
            key="ban.ban.params.user",
        ),
        reason=locale_str(
            "Reason for the ban",
            key="ban.ban.params.reason",
        ),
        delete_message_days=locale_str(
            "Number of days of messages to delete (0-7)",
            key="ban.ban.params.delete_message_days",
        ),
    )
    async def ban_command(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: str,
        delete_message_days: Optional[int] = 0
    ):
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Validate delete_message_days
        if delete_message_days is None:
            delete_message_days = 0
        elif delete_message_days < 0 or delete_message_days > 7:
            await interaction.response.send_message(
                t('ban.invalid_delete_days'),
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
            await interaction.response.send_message(
                t('ban.ban_success').format(user=user.mention),
                ephemeral=False
            )

            # Send notification
            await self.send_ban_notification(user, reason)

            logging.info(f"User {user.id} banned by {interaction.user.id} in guild {interaction.guild.id}")

        except discord.Forbidden:
            await interaction.response.send_message(
                t('ban.ban_failed_permissions'),
                ephemeral=False
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                t('ban.ban_failed_error'),
                ephemeral=False
            )
            logging.error(f"Failed to ban user {user.id}: {e}")

    @app_commands.command(
        name="tempban",
        description=locale_str(
            "Temporarily ban a user from the server",
            key="ban.tempban.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "The user to temporarily ban",
            key="ban.tempban.params.user",
        ),
        duration=locale_str(
            "Duration of the ban (e.g., 1m, 1h, 1d, 1w)",
            key="ban.tempban.params.duration",
        ),
        reason=locale_str(
            "Reason for the ban",
            key="ban.tempban.params.reason",
        ),
        delete_message_days=locale_str(
            "Number of days of messages to delete (0-7)",
            key="ban.tempban.params.delete_message_days",
        ),
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
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Parse duration
        ban_duration = self.parse_duration(duration)
        if not ban_duration:
            await interaction.response.send_message(
                t('ban.invalid_duration'),
                ephemeral=False
            )
            return

        # Check minimum duration (1 minute)
        if ban_duration < timedelta(minutes=1):
            await interaction.response.send_message(
                t('ban.duration_too_short'),
                ephemeral=False
            )
            return

        # Validate delete_message_days
        if delete_message_days is None:
            delete_message_days = 0
        elif delete_message_days < 0 or delete_message_days > 7:
            await interaction.response.send_message(
                t('ban.invalid_delete_days'),
                ephemeral=False
            )
            return

        try:
            # Check if user already has an active tempban
            existing_tempban = await self.db.get_user_tempban(user.id, interaction.guild.id)
            if existing_tempban:
                await interaction.response.send_message(
                    t('ban.user_already_tempbanned').format(user=user.mention),
                    ephemeral=False
                )
                return

            # Calculate unban time (use timezone-aware datetime)
            unban_time = discord.utils.utcnow() + ban_duration

            # Send DM to user BEFORE banning (so they can receive it)
            await self.send_tempban_dm(user, interaction.guild, reason, duration, unban_time)

            # Ban the user
            await interaction.guild.ban(
                user,
                reason=f"Temporary ban: {reason} (Duration: {duration})",
                delete_message_days=delete_message_days
            )

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
            await interaction.response.send_message(
                t('ban.tempban_success').format(
                    user=user.mention,
                    duration=duration
                ),
                ephemeral=False
            )

            # Send notification
            await self.send_ban_notification(user, reason, duration, unban_time)

            logging.info(f"User {user.id} temporarily banned for {duration} by {interaction.user.id} in guild {interaction.guild.id}")

        except discord.Forbidden:
            await interaction.response.send_message(
                t('ban.ban_failed_permissions'),
                ephemeral=False
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                t('ban.ban_failed_error'),
                ephemeral=False
            )
            logging.error(f"Failed to temporarily ban user {user.id}: {e}")

    @app_commands.command(
        name="mute",
        description=locale_str(
            "Mute a user in the server",
            key="ban.mute.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "The user to mute",
            key="ban.mute.params.user",
        ),
        duration=locale_str(
            "Duration of the mute (e.g., 1m, 1h, 1d, 1w)",
            key="ban.mute.params.duration",
        ),
        reason=locale_str(
            "Reason for the mute",
            key="ban.mute.params.reason",
        ),
    )
    async def mute_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: str,
        reason: str
    ):
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Parse duration
        mute_duration = self.parse_duration(duration)
        if not mute_duration:
            await interaction.response.send_message(
                t('ban.invalid_duration'),
                ephemeral=False
            )
            return

        # Check minimum duration (1 minute)
        if mute_duration < timedelta(minutes=1):
            await interaction.response.send_message(
                t('ban.duration_too_short'),
                ephemeral=False
            )
            return

        # Check maximum duration (28 days - Discord timeout limit)
        if mute_duration > timedelta(days=28):
            await interaction.response.send_message(
                t('ban.mute_duration_too_long'),
                ephemeral=False
            )
            return

        try:
            # Calculate unmute time
            unmute_time = discord.utils.utcnow() + mute_duration

            # Send DM to user BEFORE muting (so they can receive it)
            await self.send_mute_dm(user, interaction.guild, reason, duration, unmute_time)

            # Mute the user using Discord's timeout feature
            await user.timeout(unmute_time, reason=reason)

            # Send success response
            await interaction.response.send_message(
                t('ban.mute_success').format(
                    user=user.mention,
                    duration=duration
                ),
                ephemeral=False
            )

            # Send notification
            await self.send_mute_notification(user, reason, duration, unmute_time)

            logging.info(f"User {user.id} muted for {duration} by {interaction.user.id} in guild {interaction.guild.id}")

        except discord.Forbidden:
            await interaction.response.send_message(
                t('ban.mute_failed_permissions'),
                ephemeral=False
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                t('ban.mute_failed_error'),
                ephemeral=False
            )
            logging.error(f"Failed to mute user {user.id}: {e}")

    @app_commands.command(
        name="ban_admin_list",
        description=locale_str(
            "Show current ban admin permissions",
            key="ban.ban_admin_list.description",
        ),
    )
    async def ban_admin_list(self, interaction: discord.Interaction):
        """Show current ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            await interaction.response.send_message(
                t('ban.admin_channel_only'),
                ephemeral=False
            )
            return

        # Get current permissions
        admin_roles = self.config_data.get('admin_roles', [])
        admin_users = self.config_data.get('admin_users', [])

        embed = discord.Embed(
            title=t('ban.admin_list_title'),
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
                name=t('ban.admin_roles_title'),
                value='\n'.join(role_mentions) if role_mentions else t('ban.none'),
                inline=False
            )
        else:
            embed.add_field(
                name=t('ban.admin_roles_title'),
                value=t('ban.none'),
                inline=False
            )

        # Admin users
        if admin_users:
            user_mentions = []
            for user_id in admin_users:
                try:
                    user = await self.bot.fetch_user(user_id)
                    user_mentions.append(f"{user.mention} ({user.display_name})")
                except (discord.NotFound, discord.HTTPException):
                    user_mentions.append(f"<@{user_id}> (不存在)")

            embed.add_field(
                name=t('ban.admin_users_title'),
                value='\n'.join(user_mentions) if user_mentions else t('ban.none'),
                inline=False
            )
        else:
            embed.add_field(
                name=t('ban.admin_users_title'),
                value=t('ban.none'),
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
            channel_text = t('ban.none')

        embed.add_field(
            name=t('ban.notification_channel_title'),
            value=channel_text,
            inline=False
        )

        # Invite link
        invite_link = self.config_data.get('invite_link')
        if invite_link:
            invite_text = f"[点击查看]({invite_link})"
        else:
            invite_text = t('ban.none')

        embed.add_field(
            name="🔗 邀请链接",
            value=invite_text,
            inline=False
        )

        # Set footer with admin note
        embed.set_footer(
            text=t('ban.admin_note')
        )

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(
        name="ban_admin_add_role",
        description=locale_str(
            "Add a role to ban admin permissions",
            key="ban.ban_admin_add_role.description",
        ),
    )
    @app_commands.describe(
        role=locale_str(
            "The role to add to ban admin permissions",
            key="ban.ban_admin_add_role.params.role",
        ),
    )
    async def ban_admin_add_role(self, interaction: discord.Interaction, role: discord.Role):
        """Add a role to ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            await interaction.response.send_message(
                t('ban.admin_channel_only'),
                ephemeral=False
            )
            return

        # Check if role is already in admin roles
        admin_roles = self.config_data.get('admin_roles', [])
        if role.id in admin_roles:
            await interaction.response.send_message(
                t('ban.role_already_admin').format(role=role.mention),
                ephemeral=False
            )
            return

        # Add role to admin roles
        admin_roles.append(role.id)
        self.config_data['admin_roles'] = admin_roles

        # Save config
        await self.save_config()

        await interaction.response.send_message(
            t('ban.role_added_success').format(role=role.mention),
            ephemeral=False
        )

    @app_commands.command(
        name="ban_admin_delete_role",
        description=locale_str(
            "Remove a role from ban admin permissions",
            key="ban.ban_admin_delete_role.description",
        ),
    )
    @app_commands.describe(
        role=locale_str(
            "The role to remove from ban admin permissions",
            key="ban.ban_admin_delete_role.params.role",
        ),
    )
    async def ban_admin_delete_role(self, interaction: discord.Interaction, role: discord.Role):
        """Remove a role from ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            await interaction.response.send_message(
                t('ban.admin_channel_only'),
                ephemeral=False
            )
            return

        # Check if role is in admin roles
        admin_roles = self.config_data.get('admin_roles', [])
        if role.id not in admin_roles:
            await interaction.response.send_message(
                t('ban.role_not_admin').format(role=role.mention),
                ephemeral=False
            )
            return

        # Remove role from admin roles
        admin_roles.remove(role.id)
        self.config_data['admin_roles'] = admin_roles

        # Save config
        await self.save_config()

        await interaction.response.send_message(
            t('ban.role_removed_success').format(role=role.mention),
            ephemeral=False
        )

    @app_commands.command(
        name="ban_admin_add_user",
        description=locale_str(
            "Add a user to ban admin permissions",
            key="ban.ban_admin_add_user.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "The user to add to ban admin permissions",
            key="ban.ban_admin_add_user.params.user",
        ),
    )
    async def ban_admin_add_user(self, interaction: discord.Interaction, user: discord.User):
        """Add a user to ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            await interaction.response.send_message(
                t('ban.admin_channel_only'),
                ephemeral=False
            )
            return

        # Check if user is already in admin users
        admin_users = self.config_data.get('admin_users', [])
        if user.id in admin_users:
            await interaction.response.send_message(
                t('ban.user_already_admin').format(user=user.mention),
                ephemeral=False
            )
            return

        # Add user to admin users
        admin_users.append(user.id)
        self.config_data['admin_users'] = admin_users

        # Save config
        await self.save_config()

        await interaction.response.send_message(
            t('ban.user_added_success').format(user=user.mention),
            ephemeral=False
        )

    @app_commands.command(
        name="ban_admin_delete_user",
        description=locale_str(
            "Remove a user from ban admin permissions",
            key="ban.ban_admin_delete_user.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "The user to remove from ban admin permissions",
            key="ban.ban_admin_delete_user.params.user",
        ),
    )
    async def ban_admin_delete_user(self, interaction: discord.Interaction, user: discord.User):
        """Remove a user from ban admin permissions"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            await interaction.response.send_message(
                t('ban.admin_channel_only'),
                ephemeral=False
            )
            return

        # Check if user is in admin users
        admin_users = self.config_data.get('admin_users', [])
        if user.id not in admin_users:
            await interaction.response.send_message(
                t('ban.user_not_admin').format(user=user.mention),
                ephemeral=False
            )
            return

        # Remove user from admin users
        admin_users.remove(user.id)
        self.config_data['admin_users'] = admin_users

        # Save config
        await self.save_config()

        await interaction.response.send_message(
            t('ban.user_removed_success').format(user=user.mention),
            ephemeral=False
        )

    @app_commands.command(
        name="ban_set_notification_channel",
        description=locale_str(
            "Set the channel for ban notifications",
            key="ban.ban_set_notification_channel.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "The channel where ban notifications will be sent",
            key="ban.ban_set_notification_channel.params.channel",
        ),
    )
    async def ban_set_notification_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the ban notification channel"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            await interaction.response.send_message(
                t('ban.admin_channel_only'),
                ephemeral=False
            )
            return

        # Set the notification channel
        self.config_data['ban_notification_channel_id'] = channel.id

        # Save config
        await self.save_config()

        await interaction.response.send_message(
            t('ban.notification_channel_set').format(channel=channel.mention),
            ephemeral=False
        )

    @app_commands.command(
        name="ban_remove_notification_channel",
        description=locale_str(
            "Remove the ban notification channel",
            key="ban.ban_remove_notification_channel.description",
        ),
    )
    async def ban_remove_notification_channel(self, interaction: discord.Interaction):
        """Remove the ban notification channel"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            await interaction.response.send_message(
                t('ban.admin_channel_only'),
                ephemeral=False
            )
            return

        # Check if notification channel is set
        if not self.config_data.get('ban_notification_channel_id'):
            await interaction.response.send_message(
                t('ban.notification_channel_not_set'),
                ephemeral=False
            )
            return

        # Remove the notification channel
        self.config_data['ban_notification_channel_id'] = None

        # Save config
        await self.save_config()

        await interaction.response.send_message(
            t('ban.notification_channel_removed'),
            ephemeral=False
        )

    @app_commands.command(
        name="ban_set_invite_link",
        description=locale_str(
            "Set the invite link for tempbanned users",
            key="ban.ban_set_invite_link.description",
        ),
    )
    @app_commands.describe(
        invite_link=locale_str(
            "The permanent invite link for rejoining the server",
            key="ban.ban_set_invite_link.params.invite_link",
        ),
    )
    async def ban_set_invite_link(self, interaction: discord.Interaction, invite_link: str):
        """Set the invite link for tempbanned users"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            await interaction.response.send_message(
                t('ban.admin_channel_only'),
                ephemeral=False
            )
            return

        # Validate invite link format (basic check)
        if not is_valid_discord_invite_link(invite_link):
            await interaction.response.send_message(
                t('ban.invalid_invite_link'),
                ephemeral=False
            )
            return

        # Set the invite link
        self.config_data['invite_link'] = invite_link

        # Save config
        await self.save_config()

        await interaction.response.send_message(
            t('ban.invite_link_set').format(link=invite_link),
            ephemeral=False
        )



    @app_commands.command(
        name="ban_list_tempbans",
        description=locale_str(
            "List all active temporary bans",
            key="ban.ban_list_tempbans.description",
        ),
    )
    async def ban_list_tempbans(self, interaction: discord.Interaction):
        """List all active temporary bans in the server"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        try:
            active_tempbans = await self.db.get_active_tempbans(interaction.guild.id)

            if not active_tempbans:
                await interaction.response.send_message(
                    t('ban.no_active_tempbans'),
                    ephemeral=False
                )
                return

            embed = discord.Embed(
                title=t('ban.active_tempbans_title'),
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )

            # Add each tempban as a field
            for tempban in active_tempbans[:10]:  # Limit to 10 to avoid embed limits
                tempban_id, user_id, guild_id, banned_by, reason, banned_at, unban_at, delete_message_days = tempban

                try:
                    user = await self.bot.fetch_user(user_id)
                    banned_by_user = await self.bot.fetch_user(banned_by)

                    # Convert unban_at to proper datetime if needed
                    if isinstance(unban_at, str):
                        unban_time = discord.utils.parse_time(unban_at)
                    else:
                        unban_time = unban_at

                    embed.add_field(
                        name=f"👤 {user.display_name}",
                        value=f"**ID:** {user_id}\n**原因:** {reason}\n**管理员:** {banned_by_user.display_name}\n**解封时间:** <t:{int(unban_time.timestamp())}:R>",
                        inline=False
                    )
                except (discord.NotFound, discord.HTTPException):
                    embed.add_field(
                        name=f"👤 用户 {user_id}",
                        value=f"**原因:** {reason}\n**解封时间:** <t:{int(unban_time.timestamp())}:R>",
                        inline=False
                    )

            if len(active_tempbans) > 10:
                embed.set_footer(text=f"显示前10个，总共{len(active_tempbans)}个活跃临时封禁")

            await interaction.response.send_message(embed=embed, ephemeral=False)

        except Exception as e:
            logging.error(f"Error listing tempbans: {e}")
            await interaction.response.send_message(
                t('ban.tempban_list_error'),
                ephemeral=False
            )

    @app_commands.command(
        name="ban_remove_invite_link",
        description=locale_str(
            "Remove the invite link for tempbanned users",
            key="ban.ban_remove_invite_link.description",
        ),
    )
    async def ban_remove_invite_link(self, interaction: discord.Interaction):
        """Remove the invite link for tempbanned users"""
        # Check if user has permission
        if not await self.has_ban_permission(interaction):
            await interaction.response.send_message(
                t('ban.no_permission'),
                ephemeral=False
            )
            return

        # Check if in admin channel
        if not await self.is_admin_channel_only_check(interaction):
            await interaction.response.send_message(
                t('ban.admin_channel_only'),
                ephemeral=False
            )
            return

        # Check if invite link is set
        if not self.config_data.get('invite_link'):
            await interaction.response.send_message(
                t('ban.invite_link_not_set'),
                ephemeral=False
            )
            return

        # Remove the invite link
        self.config_data['invite_link'] = None

        # Save config
        await self.save_config()

        await interaction.response.send_message(
            t('ban.invite_link_removed'),
            ephemeral=False
        )

    @mute_command.error
    async def mute_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle mute command errors"""
        if isinstance(error, app_commands.TransformerError):
            await interaction.response.send_message(
                t('ban.member_not_found'),
                ephemeral=False
            )
        else:
            # Re-raise other errors for default handling
            raise error
