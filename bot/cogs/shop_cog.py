# bot/cogs/shop_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import tempfile
from datetime import datetime, timedelta
import re
from collections import defaultdict

from bot.utils import config, check_channel_validity, check_voice_state
from bot.utils.shop_db import ShopDatabaseManager


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

    @app_commands.command(name="checkin", description="每日签到！")
    async def checkin(self, interaction: discord.Interaction):
        """Daily check-in command to earn points."""
        # Check if user is in a voice channel
        if not await check_voice_state(interaction):
            await interaction.response.send_message(
                self.conf['checkin_not_in_voice_message'],
                ephemeral=True
            )
            return

        # Attempt to check in
        user_id = interaction.user.id
        checkin_result = await self.db.record_checkin(user_id)

        if not checkin_result["already_checked_in"]:
            # Successful new check-in
            reward = self.conf['checkin_daily_reward']

            # Update balance and record transaction
            new_balance = await self.db.update_user_balance_with_record(
                user_id,
                reward,
                "checkin",
                user_id,
                f"Daily check-in (streak: {checkin_result['streak']})"
            )

            response_message = self.conf['checkin_success_message'].format(reward=reward)
        else:
            # Already checked in today
            new_balance = await self.db.get_user_balance(user_id)
            response_message = self.conf['checkin_already_message']

        # Create embed with check-in information
        embed = self.create_checkin_embed(
            interaction.user,
            new_balance,
            checkin_result["streak"],
            checkin_result["max_streak"]
        )

        # Send response (visible to everyone)
        await interaction.response.send_message(response_message, embed=embed)

    def create_checkin_embed(self, user, balance, streak, max_streak):
        """Create an embed showing check-in information."""
        embed = discord.Embed(
            title=self.conf['checkin_embed_title'].format(user_name=user.display_name),
            color=discord.Color.gold()
        )

        # Add user avatar as thumbnail
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        # else use bot avatar instead
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        # Add fields with check-in information
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

        # Add footer with reward info
        embed.set_footer(
            text=self.conf['checkin_footer'].format(reward=self.conf['checkin_daily_reward'])
        )

        return embed

    def create_checkin_status_embed(self, user, balance, streak, max_streak):
        """Create an embed showing check-in status information (different from actual check-in)."""
        embed = discord.Embed(
            title=self.conf['checkin_check_embed_title'],
            description=self.conf['checkin_check_embed_description'],
            color=discord.Color.blue()
        )

        # Add user avatar as thumbnail
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        # Add fields with check-in information
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
            value=f"{streak}天",
            inline=True
        )

        embed.add_field(
            name="⭐ 最大连续签到",
            value=f"{max_streak}天",
            inline=True
        )

        return embed

    @app_commands.command(name="checkin_check", description="查看签到与余额信息")
    @app_commands.describe(user="要查看的用户 (默认为自己)")
    async def checkin_check(self, interaction: discord.Interaction, user: discord.User = None):
        """Check balance and check-in status for any user."""
        target_user = user or interaction.user

        # Get user balance and check-in status
        balance = await self.db.get_user_balance(target_user.id)
        checkin_status = await self.db.get_checkin_status(target_user.id)

        # Create an embed with the information
        embed = self.create_checkin_status_embed(
            target_user,
            balance,
            checkin_status["streak"],
            checkin_status["max_streak"]
        )

        # Add last check-in date if available
        if checkin_status["last_checkin"]:
            last_date = datetime.fromisoformat(checkin_status["last_checkin"]).strftime('%Y-%m-%d')
            embed.add_field(
                name="📅 最后签到",
                value=last_date,
                inline=False
            )

        await interaction.response.send_message(embed=embed)

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

    @app_commands.command(name="checkin_history", description="查看签到历史记录")
    @app_commands.describe(user="指定用户(仅管理员)")
    async def checkin_history(self, interaction: discord.Interaction, user: discord.User = None):
        """View check-in history by month."""
        target_user = user or interaction.user

        # If checking another user's history, verify admin channel
        if user and user.id != interaction.user.id:
            if not await check_channel_validity(interaction):
                return

        # Defer response as this might take time
        await interaction.response.defer(ephemeral=True)

        # Get monthly check-in history
        checkin_history = await self.db.get_checkin_history_by_month(target_user.id)

        if not checkin_history:
            await interaction.followup.send(
                self.conf['checkin_history_no_data'],
                ephemeral=True
            )
            return

        # Format check-in history for the temporary file
        formatted_history = self.format_checkin_history(checkin_history)

        # Create a temporary file
        with tempfile.NamedTemporaryFile('w+', encoding='utf-8', suffix='.txt', delete=False) as temp_file:
            temp_file.write(formatted_history)
            temp_file_path = temp_file.name

        try:
            # Send the file
            file = discord.File(temp_file_path, filename=f"checkin_history_{target_user.name}.txt")
            await interaction.followup.send(
                self.conf['checkin_history_message'].format(user_name=target_user.display_name),
                file=file,
                ephemeral=True
            )
        finally:
            # Clean up
            try:
                os.unlink(temp_file_path)
            except:
                pass

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

    @app_commands.command(name="checkin_makeup", description="补签功能，消耗积分补签漏签日期")
    async def checkin_makeup(self, interaction: discord.Interaction):
        """Makeup check-in command to make up for missed days."""
        user_id = interaction.user.id
        
        # Check remaining makeup count
        remaining_count = await self.db.get_remaining_makeup_count(user_id)
        if remaining_count <= 0:
            embed = discord.Embed(
                title=self.conf['makeup_checkin_no_quota_title'],
                description=self.conf['makeup_checkin_no_quota_description'].format(
                    limit=self.conf['makeup_checkin_limit_per_month']
                ),
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Check if user has any manual check-ins first
        first_checkin = await self.db.get_first_checkin_date(user_id)
        if not first_checkin:
            embed = discord.Embed(
                title=self.conf['makeup_checkin_no_manual_checkin_title'],
                description=self.conf['makeup_checkin_no_manual_checkin_description'],
                color=discord.Color.orange()
            )
            embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Find the latest missed check-in date
        missed_date = await self.db.find_latest_missed_checkin(user_id)
        if not missed_date:
            embed = discord.Embed(
                title=self.conf['makeup_checkin_no_missed_days_title'],
                description=self.conf['makeup_checkin_no_missed_days_description'],
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Check user balance
        current_balance = await self.db.get_user_balance(user_id)
        makeup_cost = self.conf['makeup_checkin_cost']
        
        if current_balance < makeup_cost:
            embed = discord.Embed(
                title=self.conf['makeup_checkin_insufficient_balance_title'],
                description=self.conf['makeup_checkin_insufficient_balance_description'].format(
                    cost=makeup_cost,
                    balance=current_balance
                ),
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Perform makeup check-in
        success = await self.db.add_makeup_record(user_id, missed_date)
        if not success:
            embed = discord.Embed(
                title=self.conf['makeup_checkin_no_quota_title'],
                description=self.conf['makeup_checkin_no_quota_description'].format(
                    limit=self.conf['makeup_checkin_limit_per_month']
                ),
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Deduct balance and record transaction
        new_balance = await self.db.update_user_balance_with_record(
            user_id,
            -makeup_cost,
            "makeup_checkin",
            user_id,
            f"Makeup check-in for {missed_date}"
        )
        
        # Get updated remaining count
        new_remaining_count = await self.db.get_remaining_makeup_count(user_id)
        
        # Get updated check-in status for streak information
        updated_checkin_status = await self.db.get_checkin_status(user_id)
        
        # Create success embed
        embed = discord.Embed(
            title=self.conf['makeup_checkin_success_title'],
            description=self.conf['makeup_checkin_success_description'].format(cost=makeup_cost),
            color=discord.Color.green()
        )
        
        # Add user avatar as thumbnail
        if interaction.user.avatar:
            embed.set_thumbnail(url=interaction.user.avatar.url)
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        # Add fields
        embed.add_field(
            name="📅 补签日期",
            value=missed_date,
            inline=True
        )
        
        embed.add_field(
            name="💰 当前积分",
            value=f"{new_balance}",
            inline=True
        )
        
        embed.add_field(
            name=self.conf['makeup_checkin_remaining_field'],
            value=f"{new_remaining_count}/{self.conf['makeup_checkin_limit_per_month']}",
            inline=True
        )
        
        # Add streak information
        embed.add_field(
            name="🔥 连续签到",
            value=f"{updated_checkin_status['streak']}天",
            inline=True
        )
        
        embed.add_field(
            name="⭐ 最大连续签到",
            value=f"{updated_checkin_status['max_streak']}天",
            inline=True
        )
        
        # Add footer
        embed.set_footer(text=f"💸 补签消耗 {makeup_cost} 积分")
        
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(ShopCog(bot))