# bot/cogs/shop_cog.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import os
import tempfile
from datetime import datetime, timedelta
import re
from collections import defaultdict
from typing import Optional

from bot.utils import config, check_channel_validity, check_voice_state
from bot.utils.shop_db import ShopDatabaseManager


class CheckinMakeupModal(discord.ui.Modal):
    def __init__(self, db, user_id, conf, remaining_count, balance, cost, missed_date):
        super().__init__(title=conf['makeup_modal_title'])
        self.db = db
        self.user_id = user_id
        self.conf = conf
        self.remaining_count = remaining_count
        self.balance = balance
        self.cost = cost
        self.missed_date = missed_date
        
        self.info_field = discord.ui.TextInput(
            label=conf['makeup_modal_info_label'],
            default=conf['makeup_modal_info_format'].format(
                remaining=remaining_count,
                total=conf['makeup_checkin_limit_per_month'],
                cost=cost,
                balance=balance
            ),
            style=discord.TextStyle.paragraph,
            required=False
        )
        
        self.confirm_field = discord.ui.TextInput(
            label=conf['makeup_modal_confirm_label'],
            placeholder=conf['makeup_modal_confirm_placeholder'],
            required=True,
            max_length=10,
            style=discord.TextStyle.short
        )
        
        self.add_item(self.info_field)
        self.add_item(self.confirm_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        confirm_text = self.confirm_field.value.strip().lower()
        if confirm_text not in ['yes', 'y']:
            await interaction.followup.send(
                self.conf['makeup_modal_invalid_confirm'], 
                ephemeral=True
            )
            return
        
        # Check balance again
        current_balance = await self.db.get_user_balance(self.user_id)
        if current_balance < self.cost:
            await interaction.followup.send(
                self.conf['makeup_checkin_insufficient_balance_description'].format(
                    cost=self.cost, 
                    balance=current_balance
                ),
                ephemeral=True
            )
            return
        
        # Perform makeup checkin
        success = await self.db.add_makeup_record(self.user_id, self.missed_date)
        if not success:
            await interaction.followup.send(
                self.conf['makeup_checkin_no_quota_description'].format(
                    limit=self.conf['makeup_checkin_limit_per_month']
                ),
                ephemeral=True
            )
            return
        
        # Deduct balance
        new_balance = await self.db.update_user_balance_with_record(
            self.user_id,
            -self.cost,
            "makeup_checkin",
            self.user_id,
            f"Makeup check-in for {self.missed_date}"
        )
        
        await interaction.followup.send(
            self.conf['makeup_modal_success_private'].format(
                date=self.missed_date,
                cost=self.cost
            ),
            ephemeral=True
        )


class CheckinEmbedView(discord.ui.View):
    def __init__(self, cog, bot, db, conf):
        super().__init__(timeout=None)
        self.cog = cog
        self.bot = bot
        self.db = db
        self.conf = conf
        
        # Update button labels from config
        for item in self.children:
            if hasattr(item, 'custom_id'):
                if item.custom_id == "checkin_daily":
                    item.label = conf['checkin_button_daily_text']
                elif item.custom_id == "checkin_makeup":
                    item.label = conf['checkin_button_makeup_text']
                elif item.custom_id == "checkin_query":
                    item.label = conf['checkin_button_query_text']
    
    @discord.ui.button(
        label="✅ 每日签到",
        style=discord.ButtonStyle.primary,
        custom_id="checkin_daily"
    )
    async def daily_checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        # Check if user is in voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                self.conf['checkin_daily_not_in_voice_private'],
                ephemeral=True
            )
            return
        
        user_id = interaction.user.id
        checkin_result = await self.db.record_checkin(user_id)
        
        if not checkin_result["already_checked_in"]:
            # Successful checkin
            reward = self.conf['checkin_daily_reward']
            new_balance = await self.db.update_user_balance_with_record(
                user_id,
                reward,
                "checkin",
                user_id,
                f"Daily check-in (streak: {checkin_result['streak']})"
            )
            
            # Create private embed response
            embed = self.create_private_checkin_embed(
                interaction.user,
                new_balance,
                checkin_result["streak"],
                checkin_result["max_streak"],
                False
            )
            
            # IMPORTANT: Respond to interaction first to avoid timeout
            await interaction.response.send_message(
                self.conf['checkin_daily_success_private'].format(reward=reward),
                embed=embed,
                ephemeral=True
            )
            
            # Update embed statistics and refresh all embed panels (async, non-blocking)
            try:
                await self.cog.update_checkin_embeds_after_checkin(user_id)
            except Exception as e:
                logging.error(f"Error updating embeds after checkin: {e}")
        else:
            # Already checked in
            balance = await self.db.get_user_balance(user_id)
            checkin_status = await self.db.get_checkin_status(user_id)
            
            # Create private embed with last checkin date
            embed = self.create_private_checkin_embed(
                interaction.user,
                balance,
                checkin_status["streak"],
                checkin_status["max_streak"],
                True,
                checkin_status["last_checkin"]
            )
            
            await interaction.response.send_message(
                self.conf['checkin_daily_already_private'],
                embed=embed,
                ephemeral=True
            )
    
    @discord.ui.button(
        label="⏰ 补签",
        style=discord.ButtonStyle.success,
        custom_id="checkin_makeup"
    )
    async def makeup_checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        user_id = interaction.user.id
        
        # Check remaining makeup count
        remaining_count = await self.db.get_remaining_makeup_count(user_id)
        if remaining_count <= 0:
            await interaction.response.send_message(
                self.conf['makeup_checkin_no_quota_description'].format(
                    limit=self.conf['makeup_checkin_limit_per_month']
                ),
                ephemeral=True
            )
            return
        
        # Find missed date
        missed_date = await self.db.find_latest_missed_checkin(user_id)
        if not missed_date:
            await interaction.response.send_message(
                self.conf['makeup_checkin_no_missed_days_description'],
                ephemeral=True
            )
            return
        
        # Check balance
        balance = await self.db.get_user_balance(user_id)
        cost = self.conf['makeup_checkin_cost']
        
        if balance < cost:
            await interaction.response.send_message(
                self.conf['makeup_checkin_insufficient_balance_description'].format(
                    cost=cost,
                    balance=balance
                ),
                ephemeral=True
            )
            return
        
        # Show modal
        modal = CheckinMakeupModal(
            self.db, user_id, self.conf, 
            remaining_count, balance, cost, missed_date
        )
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="🔍 签到查询",
        style=discord.ButtonStyle.secondary,
        custom_id="checkin_query"
    )
    async def query_checkin_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        
        await interaction.response.defer(ephemeral=True)
        
        user = interaction.user
        balance = await self.db.get_user_balance(user.id)
        checkin_status = await self.db.get_checkin_status(user.id)
        
        # Create status embed
        embed = self.create_query_embed(user, balance, checkin_status)
        
        # Get checkin history file
        checkin_history = await self.db.get_checkin_history_by_month(user.id)
        if checkin_history:
            formatted_history = self.format_checkin_history_file(checkin_history)
            
            with tempfile.NamedTemporaryFile('w+', encoding='utf-8', suffix='.txt', delete=False) as temp_file:
                temp_file.write(formatted_history)
                temp_file_path = temp_file.name
            
            try:
                file = discord.File(
                    temp_file_path, 
                    filename=self.conf['query_button_file_name'].format(user_name=user.name)
                )
                await interaction.followup.send(
                    embed=embed,
                    file=file,
                    ephemeral=True
                )
            finally:
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    def create_private_checkin_embed(self, user, balance, streak, max_streak, already_checked_in=False, last_checkin=None):
        """Create private embed for checkin response."""
        embed = discord.Embed(
            title=self.conf['checkin_private_embed_title'].format(user_name=user.display_name),
            color=discord.Color.gold()
        )
        
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        embed.add_field(
            name="",
            value=self.conf['checkin_embed_balance'].format(balance=balance),
            inline=False
        )
        
        embed.add_field(
            name="",
            value=self.conf['checkin_embed_streak'].format(streak=streak),
            inline=True
        )
        
        embed.add_field(
            name="",
            value=self.conf['checkin_embed_max_streak'].format(max_streak=max_streak),
            inline=True
        )
        
        if already_checked_in and last_checkin:
            last_date = datetime.fromisoformat(last_checkin).strftime('%Y-%m-%d')
            embed.add_field(
                name="📅 最后签到",
                value=last_date,
                inline=False
            )
        
        embed.set_footer(
            text=self.conf['checkin_footer'].format(reward=self.conf['checkin_daily_reward'])
        )
        
        return embed
    
    def create_query_embed(self, user, balance, checkin_status):
        """Create embed for query response."""
        embed = discord.Embed(
            title=self.conf['query_button_response_title'],
            color=discord.Color.blue()
        )
        
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        embed.add_field(
            name="👤 用户",
            value=user.display_name,
            inline=False
        )
        
        embed.add_field(
            name="💰 当前积分",
            value=f"{balance}",
            inline=True
        )
        
        embed.add_field(
            name="🔥 连续签到",
            value=f"{checkin_status['streak']}天",
            inline=True
        )
        
        embed.add_field(
            name="⭐ 最大连续签到",
            value=f"{checkin_status['max_streak']}天",
            inline=True
        )
        
        if checkin_status["last_checkin"]:
            last_date = datetime.fromisoformat(checkin_status["last_checkin"]).strftime('%Y-%m-%d')
            embed.add_field(
                name="📅 最后签到",
                value=last_date,
                inline=False
            )
        
        return embed
    
    def format_checkin_history_file(self, checkin_history):
        """Format checkin history for file output."""
        month_width = 9
        count_width = 9
        
        header = self.conf['checkin_history_header']
        formatted_text = header + "\n"
        formatted_text += "-" * (month_width + count_width + 40) + "\n"
        
        for month_data in checkin_history:
            year_month, days = month_data
            day_count = len(days)
            compressed_days = self.compress_day_ranges(days)
            formatted_text += f"{year_month:^{month_width}}|{day_count:^{count_width}}| {compressed_days}\n"
        
        return formatted_text
    
    def compress_day_ranges(self, days):
        """Compress days into ranges."""
        if not days:
            return ""
        
        days = sorted(int(day) for day in days)
        ranges = []
        range_start = days[0]
        range_end = days[0]
        
        for day in days[1:]:
            if day == range_end + 1:
                range_end = day
            else:
                if range_start == range_end:
                    ranges.append(str(range_start))
                else:
                    ranges.append(f"{range_start}-{range_end}")
                range_start = range_end = day
        
        if range_start == range_end:
            ranges.append(str(range_start))
        else:
            ranges.append(f"{range_start}-{range_end}")
        
        return ", ".join(ranges)


class BalanceModifyModal(discord.ui.Modal):
    def __init__(self, db, target_user, conf):
        super().__init__(title=conf['modify_balance_modal_title'].format(user_name=target_user.display_name))
        self.db = db
        self.target_user = target_user
        self.conf = conf

        self.amount = discord.ui.TextInput(
            label=conf['modify_balance_amount_label'],
            placeholder=conf['modify_balance_amount_placeholder'],
            required=True
        )

        self.operation_type = discord.ui.TextInput(
            label=conf['modify_balance_type_label'],
            placeholder=conf['modify_balance_type_placeholder'],
            required=False
        )

        self.reason = discord.ui.TextInput(
            label=conf['modify_balance_reason_label'],
            placeholder=conf['modify_balance_reason_placeholder'],
            style=discord.TextStyle.paragraph,
            required=True
        )

        self.add_item(self.amount)
        self.add_item(self.operation_type)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Parse and validate amount
            amount = int(self.amount.value)

            # Validate operation type
            op_type = self.operation_type.value.strip().lower()
            if not op_type or op_type not in ["shop", "admin"]:
                op_type = "admin"

            # Get reason
            reason = self.reason.value.strip()

            # Update balance with record
            new_balance = await self.db.update_user_balance_with_record(
                self.target_user.id,
                amount,
                op_type,
                interaction.user.id,
                reason
            )

            # Send success message
            await interaction.followup.send(
                self.conf['modify_balance_success'].format(
                    user_name=self.target_user.display_name,
                    amount=('+' if amount > 0 else '') + str(amount),
                    balance=new_balance
                ),
            )

        except ValueError:
            await interaction.followup.send(
                self.conf['modify_balance_invalid_amount'],
                ephemeral=True
            )


class TransactionHistoryView(discord.ui.View):
    def __init__(self, bot, db, target_user_id, viewer_id, conf):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.db = db
        self.target_user_id = target_user_id
        self.viewer_id = viewer_id
        self.page = 0
        self.items_per_page = 10
        self.message = None
        self.conf = conf

        # Add previous/next buttons
        self.prev_button = discord.ui.Button(
            emoji=conf['history_prev_button_emoji'],
            style=discord.ButtonStyle.gray,
            disabled=True
        )
        self.prev_button.callback = self.previous_page

        self.next_button = discord.ui.Button(
            emoji=conf['history_next_button_emoji'],
            style=discord.ButtonStyle.gray
        )
        self.next_button.callback = self.next_page

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.viewer_id

    async def update_buttons(self):
        # Get total pages
        total_records = await self.db.get_transaction_count(self.target_user_id, exclude_checkin=True)
        total_pages = (total_records - 1) // self.items_per_page + 1

        # Update button disabled states
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= total_pages - 1

    async def previous_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.page > 0:
            self.page -= 1
            await self.update_buttons()
            embed = await self.format_page()
            await interaction.edit_original_response(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        # Get total pages
        total_records = await self.db.get_transaction_count(self.target_user_id, exclude_checkin=True)
        total_pages = (total_records - 1) // self.items_per_page + 1

        if self.page < total_pages - 1:
            self.page += 1
            await self.update_buttons()
            embed = await self.format_page()
            await interaction.edit_original_response(embed=embed, view=self)

    async def format_page(self):
        # Get transactions for this page
        offset = self.page * self.items_per_page
        transactions = await self.db.get_transaction_history(
            self.target_user_id,
            self.items_per_page,
            offset,
            exclude_checkin=True
        )

        total_records = await self.db.get_transaction_count(self.target_user_id, exclude_checkin=True)
        total_pages = max(1, (total_records - 1) // self.items_per_page + 1)

        # Get user for display
        target_user = await self.bot.fetch_user(self.target_user_id)
        target_name = target_user.display_name if target_user else f"User {self.target_user_id}"

        # Create embed
        embed = discord.Embed(
            title=self.conf['history_title'].format(user_name=target_name),
            color=discord.Color.blue()
        )

        # Add transactions
        for tx in transactions:
            tx_id, timestamp, op_type, amount, new_balance, operator_id, note = tx

            # Format the timestamp
            tx_time = datetime.fromisoformat(timestamp).strftime(self.conf['history_time_format'])

            # Get operator name
            operator = await self.bot.fetch_user(operator_id)
            operator_name = operator.display_name if operator else f"User {operator_id}"

            # Format amount with sign
            sign = "+" if amount > 0 else ""

            # Create field content
            value = self.conf['history_transaction_format'].format(
                time=tx_time,
                amount=f"{sign}{amount}",
                balance=new_balance,
                operator=operator_name,
                note=note or self.conf['history_no_note']
            )

            # Determine emoji based on operation type
            emoji = self.conf['history_type_emoji'].get(op_type, self.conf['history_default_emoji'])

            embed.add_field(
                name=self.conf['history_field_title'].format(
                    emoji=emoji,
                    type=op_type.capitalize(),
                    id=tx_id
                ),
                value=value,
                inline=False
            )

        # If no transactions found
        if not transactions:
            embed.description = self.conf['history_no_transactions']

        # Add pagination info
        embed.set_footer(text=self.conf['history_footer'].format(
            current_page=self.page + 1,
            total_pages=total_pages,
            total_records=total_records
        ))

        return embed


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
                    except:
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
                except:
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
            title=self.conf['checkin_embed_title'].format(date=date_str),
            description=self.conf['checkin_embed_description'],
            color=int(self.conf['checkin_embed_color'], 16)
        )
        
        # Add checkin count field
        count_text = str(today_count) if today_count > 0 else self.conf['checkin_embed_no_checkin']
        embed.add_field(
            name=self.conf['checkin_embed_count_field'],
            value=count_text,
            inline=True
        )
        
        # Add first checkin user field
        if first_user_id:
            first_user = self.bot.get_user(first_user_id)
            first_user_text = first_user.mention if first_user else f"<@{first_user_id}>"
        else:
            first_user_text = self.conf['checkin_embed_no_checkin']
        
        embed.add_field(
            name=self.conf['checkin_embed_first_field'],
            value=first_user_text,
            inline=True
        )
        
        # Set footer with bot avatar
        footer_text = self.conf['checkin_embed_footer']
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
            image_path = os.path.join(os.path.dirname(__file__), '..', '..', 'resources', 'images', 'checkin.png')
            
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
                        logging.error(f"No permission to fetch message in channel {channel.name}")
                        continue
                    
                    # Update embed with new statistics
                    new_embed = await self.create_daily_checkin_embed(current_date)
                    
                    # Create fresh file object for each message
                    file = discord.File(image_path, filename="checkin.png")
                    
                    try:
                        await message.edit(embed=new_embed, attachments=[file])
                    except discord.HTTPException as e:
                        logging.error(f"Failed to update embed in channel {channel.name}: {e}")
                    except discord.Forbidden:
                        logging.error(f"No permission to edit message in channel {channel.name}")
                        
                except Exception as e:
                    logging.error(f"Error processing embed {embed_data.get('id', 'unknown')}: {e}")
                    try:
                        await self.db.deactivate_checkin_embed(embed_data['id'])
                    except:
                        pass
                        
        except Exception as e:
            logging.error(f"Critical error in update_checkin_embeds_after_checkin: {e}")
            import traceback
            logging.error(traceback.format_exc())

    @app_commands.command(name="create_checkin_embed", description="创建签到面板(管理员)")
    @app_commands.describe(channel="选择要创建签到面板的频道")
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
            image_path = os.path.join(os.path.dirname(__file__), '..', '..', 'resources', 'images', 'checkin.png')
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
                    self.conf['create_embed_success'].format(channel=channel.mention) + 
                    "\n💡 如果该频道之前有签到面板，旧的已自动停用"
                )
            else:
                await interaction.followup.send(
                    self.conf['create_embed_error'].format(error="数据库保存失败")
                )
                
        except Exception as e:
            logging.error(f"Error creating checkin embed: {e}")
            await interaction.followup.send(
                self.conf['create_embed_error'].format(error=str(e))
            )


    @app_commands.command(name="balance_change", description="修改用户余额(仅管理员)")
    @app_commands.describe(user="要修改余额的用户")
    async def balance_change(self, interaction: discord.Interaction, user: discord.User):
        """Admin command to modify a user's balance."""
        # Verify the command is used in an admin channel
        if not await check_channel_validity(interaction):
            return

        # Show the modal to input amount and reason
        modal = BalanceModifyModal(self.db, user, self.conf)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="balance_history", description="查看余额变更历史")
    @app_commands.describe(user="指定用户(仅管理员)")
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
                self.conf['history_no_transactions'],
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

    @app_commands.command(name="checkin_history", description="查看用户签到详情(管理员)")
    @app_commands.describe(user="必须选择用户")
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
            title=self.conf['admin_history_title'].format(user_name=user.display_name),
            color=discord.Color.blue()
        )
        
        # Add user avatar
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        # Add comprehensive information fields
        embed.add_field(
            name=self.conf['admin_history_balance_field'],
            value=str(balance),
            inline=True
        )
        
        embed.add_field(
            name=self.conf['admin_history_current_streak_field'],
            value=f"{checkin_status['streak']}天",
            inline=True
        )
        
        embed.add_field(
            name=self.conf['admin_history_max_streak_field'],
            value=f"{checkin_status['max_streak']}天",
            inline=True
        )
        
        # Last checkin date
        if checkin_status["last_checkin"]:
            last_date = datetime.fromisoformat(checkin_status["last_checkin"]).strftime('%Y-%m-%d')
        else:
            last_date = self.conf['admin_history_no_last_checkin']
            
        embed.add_field(
            name=self.conf['admin_history_last_checkin_field'],
            value=last_date,
            inline=False
        )

        # Get monthly check-in history
        checkin_history = await self.db.get_checkin_history_by_month(user.id)
        
        logging.info(f"Checkin history for user {user.id}: {checkin_history}")

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
                logging.info(f"Sent checkin history file for user {user.id}")
            except Exception as e:
                logging.error(f"Error sending checkin history file: {e}")
                # Send embed without file if file sending fails
                await interaction.followup.send(embed=embed, ephemeral=False)
            finally:
                # Clean up
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
        else:
            # Send just the embed if no history (public response)
            logging.info(f"No checkin history found for user {user.id}")
            await interaction.followup.send(embed=embed, ephemeral=False)

    def format_checkin_history(self, checkin_history):
        """Format check-in history into a readable text format."""
        # Define column widths
        month_width = 9  # Width for YYYY-MM format
        count_width = 9  # Width for day count

        # Get header from config
        header = self.conf['checkin_history_header']

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

