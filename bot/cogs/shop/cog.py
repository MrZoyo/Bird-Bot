import logging
import os
import tempfile
from datetime import datetime

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands, tasks

from bot.utils import check_channel_validity, config, fmt_channel, fmt_user
from bot.utils.i18n import t
from bot.utils.shop_db import ShopDatabaseManager

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

    async def cog_load(self):
        """Initialize database when cog loads."""
        await self.db.initialize_database()
        
        # Set up checkin embed view
        self.checkin_view = CheckinEmbedView(self, self.bot, self.db, self.conf)
        self.bot.add_view(self.checkin_view)
        
        # Start daily embed update task
        if not self.update_daily_embeds.is_running():
            self.update_daily_embeds.start()
        
        # Recover existing embed views on bot restart
        await self.recover_embed_views()

    @tasks.loop(minutes=30)
    async def update_daily_embeds(self):
        """Check and update daily embeds every 30 minutes."""
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            active_embeds = await self.db.get_active_checkin_embeds()
            
            for embed_data in active_embeds:
                # Check if embed needs daily update
                if embed_data['created_date'] != current_date:
                    # Reset daily stats in database
                    await self.db.reset_daily_embed_stats(current_date)
                    
                    # Update the actual embed message
                    try:
                        channel = self.bot.get_channel(embed_data['channel_id'])
                        if channel:
                            message = await channel.fetch_message(embed_data['message_id'])
                            if message:
                                new_embed = await self.create_daily_checkin_embed(current_date)
                                await message.edit(embed=new_embed, view=self.checkin_view)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        # If embed message no longer exists, deactivate it
                        await self.db.deactivate_checkin_embed(embed_data['id'])
        except Exception as e:
            logging.error(f"Error in daily embed update: {e}")

    async def recover_embed_views(self):
        """Recover embed views after bot restart."""
        try:
            active_embeds = await self.db.get_active_checkin_embeds()
            for embed_data in active_embeds:
                try:
                    channel = self.bot.get_channel(embed_data['channel_id'])
                    if channel:
                        message = await channel.fetch_message(embed_data['message_id'])
                        if message:
                            # Re-add the view to existing embed
                            await message.edit(view=self.checkin_view)
                        else:
                            # Message not found, deactivate
                            await self.db.deactivate_checkin_embed(embed_data['id'])
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    # Channel or message not accessible, deactivate
                    await self.db.deactivate_checkin_embed(embed_data['id'])
        except Exception as e:
            logging.error(f"Error recovering embed views: {e}")

    async def create_daily_checkin_embed(self, date_str: str) -> discord.Embed:
        """Create the daily checkin embed."""
        # Get today's statistics
        today_count = await self.db.get_today_checkin_count(date_str)
        first_user_id = await self.db.get_today_first_checkin_user(date_str)
        
        # Create embed with date in title
        embed = discord.Embed(
            title=t('shop.checkin_embed_title').format(date=date_str),
            description=t('shop.checkin_embed_description'),
            color=int(self.conf['checkin_embed_color'], 16)
        )
        
        # Add checkin count field
        count_text = str(today_count) if today_count > 0 else t('shop.checkin_embed_no_checkin')
        embed.add_field(
            name=t('shop.checkin_embed_count_field'),
            value=count_text,
            inline=True
        )
        
        # Add first checkin user field
        if first_user_id:
            first_user = self.bot.get_user(first_user_id)
            first_user_text = first_user.mention if first_user else f"<@{first_user_id}>"
        else:
            first_user_text = t('shop.checkin_embed_no_checkin')
        
        embed.add_field(
            name=t('shop.checkin_embed_first_field'),
            value=first_user_text,
            inline=True
        )
        
        # Set footer with bot avatar
        footer_text = t('shop.checkin_embed_footer')
        if self.bot.user.avatar:
            embed.set_footer(text=footer_text, icon_url=self.bot.user.avatar.url)
        else:
            embed.set_footer(text=footer_text)
        
        # Set checkin image
        embed.set_image(url="attachment://checkin.png")
        
        return embed

    async def update_checkin_embeds_after_checkin(self, user_id: int):
        """Update all active checkin embeds after someone checks in."""
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            active_embeds = await self.db.get_active_checkin_embeds()
            
            # Pre-create the file object once to avoid path issues
            image_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'resources', 'images', 'checkin.png')
            
            for embed_data in active_embeds:
                try:
                    channel = self.bot.get_channel(embed_data['channel_id'])
                    if not channel:
                        await self.db.deactivate_checkin_embed(embed_data['id'])
                        continue
                    
                    try:
                        message = await channel.fetch_message(embed_data['message_id'])
                    except discord.NotFound:
                        await self.db.deactivate_checkin_embed(embed_data['id'])
                        continue
                    except discord.Forbidden:
                        logging.error("No permission to fetch message in %s", fmt_channel(channel))
                        continue
                    
                    # Update embed with new statistics
                    new_embed = await self.create_daily_checkin_embed(current_date)
                    
                    # Create fresh file object for each message
                    file = discord.File(image_path, filename="checkin.png")
                    
                    try:
                        await message.edit(embed=new_embed, attachments=[file])
                    except discord.HTTPException as e:
                        logging.error("Failed to update checkin embed in %s: %s", fmt_channel(channel), e)
                    except discord.Forbidden:
                        logging.error("No permission to edit message in %s", fmt_channel(channel))
                        
                except Exception as e:
                    logging.error(f"Error processing embed {embed_data.get('id', 'unknown')}: {e}")
                    try:
                        await self.db.deactivate_checkin_embed(embed_data['id'])
                    except Exception:
                        logging.exception(f"Failed to deactivate checkin embed {embed_data.get('id', 'unknown')}")
                        
        except Exception as e:
            logging.error(f"Critical error in update_checkin_embeds_after_checkin: {e}")
            import traceback
            logging.error(traceback.format_exc())

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
            
            # Create embed
            embed = await self.create_daily_checkin_embed(current_date)
            
            # Read checkin image file
            image_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'resources', 'images', 'checkin.png')
            file = discord.File(image_path, filename="checkin.png")
            
            # Send embed with view
            message = await channel.send(
                embed=embed, 
                file=file, 
                view=self.checkin_view
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
