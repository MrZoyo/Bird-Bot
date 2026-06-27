import logging
import os
import tempfile
from datetime import datetime

import discord

from bot.utils.components_v2 import build_panel_container
from bot.utils.i18n import t

from .modals import CheckinMakeupModal


class CheckinEmbedView(discord.ui.LayoutView):
    def __init__(
            self,
            cog,
            bot,
            db,
            conf,
            *,
            panel_date: str | None = None,
            today_count: int | None = None,
            first_user_text: str | None = None,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.bot = bot
        self.db = db
        self.conf = conf

        daily_button = discord.ui.Button(
            label=t('shop.checkin_button_daily_text'),
            style=discord.ButtonStyle.primary,
            custom_id="checkin_daily",
        )
        daily_button.callback = self.daily_checkin_button
        makeup_button = discord.ui.Button(
            label=t('shop.checkin_button_makeup_text'),
            style=discord.ButtonStyle.success,
            custom_id="checkin_makeup",
        )
        makeup_button.callback = self.makeup_checkin_button
        query_button = discord.ui.Button(
            label=t('shop.checkin_button_query_text'),
            style=discord.ButtonStyle.secondary,
            custom_id="checkin_query",
        )
        query_button.callback = self.query_checkin_button

        date_str = panel_date or datetime.now().strftime('%Y-%m-%d')
        count_text = str(today_count) if today_count and today_count > 0 else t('shop.checkin_embed_no_checkin')
        first_text = first_user_text or t('shop.checkin_embed_no_checkin')
        description_parts = [
            t('shop.checkin_embed_description'),
            f"**{t('shop.checkin_embed_count_field')}**\n{count_text}",
            f"**{t('shop.checkin_embed_first_field')}**\n{first_text}",
        ]
        description = "\n\n".join(part for part in description_parts if part)

        self.add_item(build_panel_container(
            title=t('shop.checkin_embed_title').format(date=date_str),
            description=description,
            footer=t('shop.checkin_embed_footer'),
            accent_color=int(self.conf.get('checkin_embed_color', 'FFD700'), 16),
            media_url="attachment://checkin.png",
            media_description=t('shop.checkin_embed_title').format(date=date_str),
            buttons=[daily_button, makeup_button, query_button],
        ))

    async def daily_checkin_button(self, interaction: discord.Interaction):
        
        # Check if user is in voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                t('shop.checkin_daily_not_in_voice_private'),
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
                t('shop.checkin_daily_success_private').format(reward=reward),
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
                t('shop.checkin_daily_already_private'),
                embed=embed,
                ephemeral=True
            )
    
    async def makeup_checkin_button(self, interaction: discord.Interaction):
        
        user_id = interaction.user.id
        
        # Check remaining makeup count
        remaining_count = await self.db.get_remaining_makeup_count(user_id)
        if remaining_count <= 0:
            await interaction.response.send_message(
                t('shop.makeup_checkin_no_quota_description').format(
                    limit=self.conf['makeup_checkin_limit_per_month']
                ),
                ephemeral=True
            )
            return
        
        # Find missed date
        missed_date = await self.db.find_latest_missed_checkin(user_id)
        if not missed_date:
            await interaction.response.send_message(
                t('shop.makeup_checkin_no_missed_days_description'),
                ephemeral=True
            )
            return
        
        # Check balance
        balance = await self.db.get_user_balance(user_id)
        cost = self.conf['makeup_checkin_cost']
        
        if balance < cost:
            await interaction.response.send_message(
                t('shop.makeup_checkin_insufficient_balance_description').format(
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
    
    async def query_checkin_button(self, interaction: discord.Interaction):
        
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
                    filename=t('shop.query_button_file_name').format(user_name=user.name)
                )
                await interaction.followup.send(
                    embed=embed,
                    file=file,
                    ephemeral=True
                )
            finally:
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    def create_private_checkin_embed(self, user, balance, streak, max_streak, already_checked_in=False, last_checkin=None):
        """Create private embed for checkin response."""
        embed = discord.Embed(
            title=t('shop.checkin_private_embed_title').format(user_name=user.display_name),
            color=discord.Color.gold()
        )
        
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        embed.add_field(
            name="",
            value=t('shop.checkin_embed_balance').format(balance=balance),
            inline=False
        )
        
        embed.add_field(
            name="",
            value=t('shop.checkin_embed_streak').format(streak=streak),
            inline=True
        )
        
        embed.add_field(
            name="",
            value=t('shop.checkin_embed_max_streak').format(max_streak=max_streak),
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
            text=t('shop.checkin_footer').format(reward=self.conf['checkin_daily_reward'])
        )
        
        return embed
    
    def create_query_embed(self, user, balance, checkin_status):
        """Create embed for query response."""
        embed = discord.Embed(
            title=t('shop.query_button_response_title'),
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
        
        header = t('shop.checkin_history_header')
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
            emoji=t('shop.history_prev_button_emoji'),
            style=discord.ButtonStyle.gray,
            disabled=True
        )
        self.prev_button.callback = self.previous_page

        self.next_button = discord.ui.Button(
            emoji=t('shop.history_next_button_emoji'),
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
            title=t('shop.history_title').format(user_name=target_name),
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
            value = t('shop.history_transaction_format').format(
                time=tx_time,
                amount=f"{sign}{amount}",
                balance=new_balance,
                operator=operator_name,
                note=note or t('shop.history_no_note')
            )

            # Determine emoji based on operation type
            emoji = self.conf['history_type_emoji'].get(op_type, self.conf['history_default_emoji'])

            embed.add_field(
                name=t('shop.history_field_title').format(
                    emoji=emoji,
                    type=op_type.capitalize(),
                    id=tx_id
                ),
                value=value,
                inline=False
            )

        # If no transactions found
        if not transactions:
            embed.description = t('shop.history_no_transactions')

        # Add pagination info
        embed.set_footer(text=t('shop.history_footer').format(
            current_page=self.page + 1,
            total_pages=total_pages,
            total_records=total_records
        ))

        return embed
