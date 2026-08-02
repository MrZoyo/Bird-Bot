import logging
import os
import tempfile
from datetime import datetime

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands, tasks

from bot.utils import check_channel_validity, config, fmt_channel, fmt_user
from bot.utils.components_v2 import clear_legacy_message_payload
from bot.utils.i18n import t
from bot.utils.shop_db import ShopDatabaseManager
from bot.utils.task_helpers import wait_until_ready_or_stop

from .modals import BalanceModifyModal
from .views import CheckinEmbedView, TransactionHistoryView


class ShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Load configurations
        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        # Shop-specific configurations
        self.conf = config.get_config('shop')

        # Initialize database manager
        self.db = ShopDatabaseManager(self.db_path, self.conf)
        self._embed_views_recovered = False

    async def cog_load(self):
        """Initialize database when cog loads."""
        await self.db.initialize_database()
        
        # Set up checkin panel view
        self.checkin_view = CheckinEmbedView(self, self.bot, self.db, self.conf)
        self.bot.add_view(self.checkin_view)
        
        # Start daily panel update task
        if not self.update_daily_embeds.is_running():
            self.update_daily_embeds.start()

    def cog_unload(self):
        if self.update_daily_embeds.is_running():
            self.update_daily_embeds.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Recover existing check-in panels after channel caches are available."""
        if self._embed_views_recovered:
            return
        await self.recover_embed_views()
        self._embed_views_recovered = True

    @tasks.loop(minutes=30)
    async def update_daily_embeds(self):
        """Check and update daily check-in panels every 30 minutes."""
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            active_embeds = await self.db.get_active_checkin_embeds()

            for embed_data in active_embeds:
                if embed_data['created_date'] != current_date:
                    refreshed = await self._refresh_checkin_panel_message(
                        embed_data,
                        current_date,
                    )
                    if refreshed:
                        await self.db.reset_daily_embed_stats(
                            current_date,
                            embed_id=embed_data['id'],
                        )
        except Exception as e:
            logging.error(f"Error in daily embed update: {e}")

    @update_daily_embeds.before_loop
    async def before_update_daily_embeds(self):
        await wait_until_ready_or_stop(
            self.bot,
            self.update_daily_embeds,
            'ShopCog.update_daily_embeds',
        )

    async def _get_panel_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            return channel
        return await self.bot.fetch_channel(channel_id)

    async def _refresh_checkin_panel_message(
        self,
        embed_data: dict,
        date_str: str,
    ) -> bool:
        """Refresh one panel, retaining it when Discord has a transient failure."""
        channel = None
        try:
            channel = await self._get_panel_channel(embed_data['channel_id'])
            message = await channel.fetch_message(embed_data['message_id'])
            view = await self.create_daily_checkin_view(date_str)
            payload = clear_legacy_message_payload()
            payload["attachments"] = [self.create_checkin_image_file()]
            await message.edit(**payload, view=view)
            return True
        except discord.NotFound:
            logging.warning(
                "Checkin panel message unknown (%s) in %s no longer exists; deactivating it.",
                embed_data['message_id'],
                fmt_channel(channel or embed_data['channel_id']),
            )
            await self.db.deactivate_checkin_embed(embed_data['id'])
        except discord.Forbidden:
            logging.error(
                "No permission to refresh checkin panel message unknown (%s) in %s; "
                "keeping it active for retry.",
                embed_data['message_id'],
                fmt_channel(channel or embed_data['channel_id']),
            )
        except discord.HTTPException as e:
            logging.warning(
                "Discord HTTP %s (code %s) while refreshing checkin panel message "
                "unknown (%s) in %s; keeping it active for retry.",
                e.status,
                e.code,
                embed_data['message_id'],
                fmt_channel(channel or embed_data['channel_id']),
            )
        except Exception:
            logging.exception(
                "Unexpected error refreshing checkin panel message unknown (%s) in %s; "
                "keeping it active for retry.",
                embed_data['message_id'],
                fmt_channel(channel or embed_data['channel_id']),
            )
        return False

    async def recover_embed_views(self):
        """Recover check-in panel views after bot restart."""
        try:
            active_embeds = await self.db.get_active_checkin_embeds()
            current_date = datetime.now().strftime('%Y-%m-%d')
            for embed_data in active_embeds:
                refreshed = await self._refresh_checkin_panel_message(
                    embed_data,
                    current_date,
                )
                if refreshed and embed_data['created_date'] != current_date:
                    await self.db.reset_daily_embed_stats(
                        current_date,
                        embed_id=embed_data['id'],
                    )
        except Exception as e:
            logging.error(f"Error recovering embed views: {e}")

    def create_checkin_image_file(self) -> discord.File:
        image_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'resources', 'images', 'checkin.png')
        return discord.File(image_path, filename="checkin.png")

    async def create_daily_checkin_view(self, date_str: str) -> CheckinEmbedView:
        """Create the daily check-in Components v2 panel."""
        today_count = await self.db.get_today_checkin_count(date_str)
        first_user_id = await self.db.get_today_first_checkin_user(date_str)

        if first_user_id:
            first_user = self.bot.get_user(first_user_id)
            first_user_text = first_user.mention if first_user else f"<@{first_user_id}>"
        else:
            first_user_text = None

        return CheckinEmbedView(
            self,
            self.bot,
            self.db,
            self.conf,
            panel_date=date_str,
            today_count=today_count,
            first_user_text=first_user_text,
        )

    async def update_checkin_embeds_after_checkin(self, user_id: int):
        """Update all active checkin embeds after someone checks in."""
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            active_embeds = await self.db.get_active_checkin_embeds()

            for embed_data in active_embeds:
                await self._refresh_checkin_panel_message(embed_data, current_date)
        except Exception as e:
            logging.error(f"Critical error in update_checkin_embeds_after_checkin: {e}")

    @app_commands.command(
        name="create_checkin_embed",
        description=locale_str(
            "Create a check-in panel (admin)",
            key="shop.create_checkin_embed.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "Channel where the check-in panel will be posted",
            key="shop.create_checkin_embed.params.channel",
        ),
    )
    async def create_checkin_embed(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Create a checkin embed panel in the specified channel."""
        if not await check_channel_validity(interaction):
            return
        
        await interaction.response.defer()
        
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # Create Components v2 panel and image attachment.
            view = await self.create_daily_checkin_view(current_date)
            file = self.create_checkin_image_file()
            
            # Send panel with view
            message = await channel.send(
                file=file, 
                view=view
            )
            
            # Save to database (will automatically deactivate any existing embed)
            success = await self.db.create_checkin_embed_record(
                channel.id, 
                message.id, 
                current_date
            )
            
            if success:
                await interaction.followup.send(
                    t('shop.create_embed_success').format(channel=channel.mention) + 
                    "\n💡 如果该频道之前有签到面板，旧的已自动停用"
                )
            else:
                await interaction.followup.send(
                    t('shop.create_embed_error').format(error="数据库保存失败")
                )
                
        except Exception as e:
            logging.error(f"Error creating checkin embed: {e}")
            await interaction.followup.send(
                t('shop.create_embed_error').format(error=str(e))
            )


    @app_commands.command(
        name="balance_change",
        description=locale_str(
            "Modify a user's balance (admin only)",
            key="shop.balance_change.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "User whose balance to modify",
            key="shop.balance_change.params.user",
        ),
    )
    async def balance_change(self, interaction: discord.Interaction, user: discord.User):
        """Admin command to modify a user's balance."""
        # Verify the command is used in an admin channel
        if not await check_channel_validity(interaction):
            return

        # Show the modal to input amount and reason
        balance = await self.db.get_user_balance(user.id)
        modal = BalanceModifyModal(self.db, user, self.conf, balance)
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="balance_history",
        description=locale_str(
            "View balance transaction history",
            key="shop.balance_history.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "Target user (admin only)",
            key="shop.balance_history.params.user",
        ),
    )
    async def balance_history(self, interaction: discord.Interaction, user: discord.User = None):
        """View balance transaction history."""
        target_user = user or interaction.user

        # If checking another user's history, verify admin channel
        if user and user.id != interaction.user.id:
            if not await check_channel_validity(interaction):
                return

        # Defer response as this might take time
        await interaction.response.defer(ephemeral=True)

        # Get total transaction count
        total_transactions = await self.db.get_transaction_count(target_user.id, exclude_checkin=True)

        if total_transactions == 0:
            await interaction.followup.send(
                t('shop.history_no_transactions'),
                ephemeral=True
            )
            return

        # Create and send paginated view
        view = TransactionHistoryView(self.bot, self.db, target_user.id, interaction.user.id, self.conf)
        # Initialize buttons correctly
        await view.update_buttons()
        embed = await view.format_page()

        message = await interaction.followup.send(
            embed=embed,
            view=view,
            ephemeral=True
        )
        view.message = message

    @app_commands.command(
        name="checkin_history",
        description=locale_str(
            "View detailed check-in history for a user (admin)",
            key="shop.checkin_history.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "User to inspect (required)",
            key="shop.checkin_history.params.user",
        ),
    )
    async def checkin_history(self, interaction: discord.Interaction, user: discord.User):
        """Admin-only command to view comprehensive checkin details for a user."""
        # Admin channel validation
        if not await check_channel_validity(interaction):
            return

        # Defer response as this might take time
        await interaction.response.defer(ephemeral=True)

        # Get user balance and checkin status
        balance = await self.db.get_user_balance(user.id)
        checkin_status = await self.db.get_checkin_status(user.id)
        
        # Create comprehensive admin embed
        embed = discord.Embed(
            title=t('shop.admin_history_title').format(user_name=user.display_name),
            color=discord.Color.blue()
        )
        
        # Add user avatar
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        # Add comprehensive information fields
        embed.add_field(
            name=t('shop.admin_history_balance_field'),
            value=str(balance),
            inline=True
        )
        
        embed.add_field(
            name=t('shop.admin_history_current_streak_field'),
            value=f"{checkin_status['streak']}天",
            inline=True
        )
        
        embed.add_field(
            name=t('shop.admin_history_max_streak_field'),
            value=f"{checkin_status['max_streak']}天",
            inline=True
        )
        
        # Last checkin date
        if checkin_status["last_checkin"]:
            last_date = datetime.fromisoformat(checkin_status["last_checkin"]).strftime('%Y-%m-%d')
        else:
            last_date = t('shop.admin_history_no_last_checkin')
            
        embed.add_field(
            name=t('shop.admin_history_last_checkin_field'),
            value=last_date,
            inline=False
        )

        # Get monthly check-in history
        checkin_history = await self.db.get_checkin_history_by_month(user.id)
        
        logging.info("Checkin history for %s: %s", fmt_user(user), checkin_history)

        if checkin_history:
            # Format check-in history for the temporary file
            formatted_history = self.format_checkin_history(checkin_history)
            logging.info(f"Formatted history length: {len(formatted_history)}")

            # Create a temporary file
            with tempfile.NamedTemporaryFile('w+', encoding='utf-8', suffix='.txt', delete=False) as temp_file:
                temp_file.write(formatted_history)
                temp_file_path = temp_file.name

            try:
                # Send embed with file (public response)
                file = discord.File(temp_file_path, filename=f"checkin_history_{user.name}.txt")
                await interaction.followup.send(
                    embed=embed,
                    file=file,
                    ephemeral=False
                )
                logging.info("Sent checkin history file for %s", fmt_user(user))
            except Exception as e:
                logging.error(f"Error sending checkin history file: {e}")
                # Send embed without file if file sending fails
                await interaction.followup.send(embed=embed, ephemeral=False)
            finally:
                # Clean up
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass
        else:
            # Send just the embed if no history (public response)
            logging.info("No checkin history found for %s", fmt_user(user))
            await interaction.followup.send(embed=embed, ephemeral=False)

    def format_checkin_history(self, checkin_history):
        """Format check-in history into a readable text format."""
        # Define column widths
        month_width = 9  # Width for YYYY-MM format
        count_width = 9  # Width for day count

        # Get header from config
        header = t('shop.checkin_history_header')

        # Use header directly without adjusting its format
        formatted_text = header + "\n"
        formatted_text += "-" * (month_width + count_width + 40) + "\n"  # Divider line

        # Data rows
        for month_data in checkin_history:
            year_month, days = month_data

            # Count days
            day_count = len(days)

            # Compress the days into ranges
            compressed_days = self.compress_day_ranges(days)

            # Add row with proper alignment
            formatted_text += f"{year_month:^{month_width}}|{day_count:^{count_width}}| {compressed_days}\n"

        return formatted_text

    def compress_day_ranges(self, days):
        """Convert a list of days into a compressed range format like 1-5,7,9-12."""
        if not days:
            return ""

        # Sort days
        days = sorted(int(day) for day in days)

        # Group consecutive days
        ranges = []
        range_start = days[0]
        range_end = days[0]

        for day in days[1:]:
            if day == range_end + 1:
                range_end = day
            else:
                # End of a range
                if range_start == range_end:
                    ranges.append(str(range_start))
                else:
                    ranges.append(f"{range_start}-{range_end}")
                range_start = range_end = day

        # Add the last range
        if range_start == range_end:
            ranges.append(str(range_start))
        else:
            ranges.append(f"{range_start}-{range_end}")

        # Join all ranges with commas
        return ", ".join(ranges)
