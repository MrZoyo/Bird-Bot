# Author: MrZoyo
# Version: 0.6.0
# Date: 2024-06-10
# ========================================
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
import sqlite3
from datetime import datetime, timedelta
import aiosqlite


class PaginationView(View):
    def __init__(self, bot, records, user_id, format_type):
        super().__init__(timeout=180.0)  # Specify the timeout directly here if needed
        self.bot = bot
        self.records = records
        self.user_id = user_id
        self.page = 0
        self.total_pages = (len(records) - 1) // 20 + 1
        self.total_records = len(records)
        self.message = None  # This will hold the reference to the message
        self.format_type = format_type  # 'user_records' or 'illegal_teaming'

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']

        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.blurple, disabled=True)
        self.next_button = Button(label="Next", style=discord.ButtonStyle.green, disabled=len(records) <= 20)
        self.previous_button.callback = self.previous_button_callback
        self.next_button.callback = self.next_button_callback
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def update_buttons(self):
        self.previous_button.disabled = self.page == 0
        self.next_button.disabled = (self.page + 1) * 20 >= len(self.records)
        if self.message:
            await self.message.edit(view=self)

    async def previous_button_callback(self, interaction: discord.Interaction):
        self.page -= 1
        await self.update_buttons()
        if self.format_type == 'user_records':
            await interaction.response.edit_message(embed=self.format_page_for_check_user_records(), view=self)
        else:
            await interaction.response.edit_message(embed=self.format_page(), view=self)

    async def next_button_callback(self, interaction: discord.Interaction):
        self.page += 1
        await self.update_buttons()
        if self.format_type == 'user_records':
            await interaction.response.edit_message(embed=self.format_page_for_check_user_records(), view=self)
        else:
            await interaction.response.edit_message(embed=self.format_page(), view=self)

    def safe_strptime(self, date_str, formats):
        if not isinstance(date_str, str):
            date_str = str(date_str)  # Convert to string if not already

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue  # Skip to the next format if the current one fails

        raise ValueError(f"time data {date_str} does not match any format")

    def format_page(self):
        start = self.page * 20
        end = min(start + 20, self.total_records)
        page_entries = self.records[start:end]
        formats = ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S']  # With and without milliseconds
        description = "\n".join([
            f"**Time:** {self.safe_strptime(record[1], formats).strftime('%Y-%m-%d %H:%M:%S')} **Message:** {record[2]}"
            for record in page_entries
        ])
        embed = discord.Embed(description=description, color=discord.Color.blue())
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} - Total records: {self.total_records}")
        return embed

    def format_page_for_check_user_records(self):
        start = self.page * 20
        end = min(start + 20, self.total_records)
        page_entries = self.records[start:end]

        description = "\n".join([
            f"**User:** {self.bot.get_user(int(record[0])).mention if self.bot.get_user(int(record[0])) else 'Unknown User'} **Records:** {record[1]}"
            for record in page_entries
        ])

        embed = discord.Embed(description=description, color=discord.Color.blue())
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} - Total records: {self.total_records}")
        return embed

    def format_page_for_check_illegal_teaming(self):
        start = self.page * 20
        end = min(start + 20, self.total_records)
        page_entries = self.records[start:end]
        description = "\n".join([
            f"**User:** {self.bot.get_user(int(record[0])).mention if self.bot.get_user(int(record[0])) else 'Unknown User'} **Logs:** {record[1]}"
            for record in page_entries
        ])
        embed = discord.Embed(description=description, color=discord.Color.blue())
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} - Total records: {self.total_records}")
        return embed


class ConfirmationView(View):
    def __init__(self, bot, user_id, member, content, time):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user_id = user_id
        self.member = member
        self.content = content
        self.time = time

        self.confirm_button = Button(style=discord.ButtonStyle.green, label="Confirm")
        self.cancel_button = Button(style=discord.ButtonStyle.red, label="Cancel")

        self.confirm_button.callback = self.confirm
        self.cancel_button.callback = self.cancel

        self.add_item(self.confirm_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def confirm(self, interaction: discord.Interaction):
        cog = self.bot.get_cog('IllegalTeamActCog')
        content_with_member = f"{self.content} - Logged by {interaction.user.name}"
        formatted_time = datetime.strptime(self.time, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S.%f')
        await cog.add_illegal_record_to_db(self.member.id, content_with_member, formatted_time)
        self.remove_item(self.confirm_button)
        self.remove_item(self.cancel_button)
        await interaction.message.edit(content="Illegal teaming record added.", view=self)

    async def cancel(self, interaction: discord.Interaction):
        self.remove_item(self.confirm_button)
        self.remove_item(self.cancel_button)
        await interaction.message.edit(content="Cancelled.", view=self)


class IllegalTeamActCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']
        self.check_illegal_teaming_channel_id = config['check_illegal_teaming_channel_id']

    async def log_illegal_activity(self, user_id, message):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            now = datetime.now()
            formatted_now = now.strftime('%Y-%m-%d %H:%M:%S.%f')  # Using microseconds
            try:
                await cursor.execute('INSERT INTO illegal_teaming (user_id, timestamp, message) VALUES (?, ?, ?)',
                                     (user_id, formatted_now, message))
                await db.commit()
            except sqlite3.IntegrityError:
                print("Duplicate entry. Skipping.")
            await cursor.close()

    async def remove_illegal_activity(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            threshold = datetime.now() - timedelta(minutes=5)
            formatted_threshold = threshold.strftime('%Y-%m-%d %H:%M:%S')
            try:
                await cursor.execute('DELETE FROM illegal_teaming WHERE user_id = ? AND timestamp > ?',
                                     (user_id, formatted_threshold))
                await db.commit()
            except sqlite3.Error as e:
                print(f"An error occurred: {e}")
            await cursor.close()

    async def get_illegal_teaming_stats(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('''
                SELECT user_id, COUNT(*) as count FROM illegal_teaming
                GROUP BY user_id
                ORDER BY count DESC
                LIMIT 20
            ''')
            results = await cursor.fetchall()
            await cursor.close()
            return results

    async def get_users_with_min_records(self, min_records):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('''
                SELECT user_id, COUNT(*) as count FROM illegal_teaming
                GROUP BY user_id
                HAVING COUNT(*) > ?
                ORDER BY count DESC
            ''', (min_records,))
            results = await cursor.fetchall()
            await cursor.close()
            return results

    async def check_channel_validity(self, ctx_or_interaction):
        """Helper function to check if the command is used in the correct channel."""
        channel_id = ctx_or_interaction.channel.id if isinstance(ctx_or_interaction,
                                                                 commands.Context) else ctx_or_interaction.channel_id
        allowed_channel_id = self.check_illegal_teaming_channel_id
        if channel_id != allowed_channel_id:
            message = "This command can only be used in specific channels."
            if isinstance(ctx_or_interaction, commands.Context):
                await ctx_or_interaction.send(message)
            else:
                await ctx_or_interaction.response.send_message(message, ephemeral=True)
            return False
        return True

    @commands.command(name='check_illegal_teaming')
    async def check_illegal_teaming_command(self, ctx):
        if not await self.check_channel_validity(ctx):
            return
        await self.send_illegal_teaming_stats(ctx)

    @app_commands.command(name="check_illegal_teaming")
    async def check_illegal_teaming(self, interaction: discord.Interaction):
        """Slash command to list the 20 most recorded users."""
        await interaction.response.defer()
        if not await self.check_channel_validity(interaction):
            return
        await self.send_illegal_teaming_stats(interaction)

    async def send_illegal_teaming_stats(self, ctx_or_interaction):
        top_users = await self.get_illegal_teaming_stats()
        if not top_users:
            message = "No illegal teaming records found."
        else:
            user_id = ctx_or_interaction.author.id if isinstance(ctx_or_interaction,
                                                                 commands.Context) else ctx_or_interaction.user.id
            view = PaginationView(self.bot, top_users, user_id, 'illegal_teaming')
            embed = view.format_page_for_check_illegal_teaming()
            if isinstance(ctx_or_interaction, commands.Context):
                message = await ctx_or_interaction.send(content="Top 20 illegal teaming users:",
                                                        embed=embed,
                                                        view=view)
            else:  # This is an Interaction
                message = await ctx_or_interaction.edit_original_response(content="Top 20 illegal teaming users:",
                                                                          embed=embed,
                                                                          view=view)
        view.message = message

    @commands.command(name='check_user_records')
    async def check_user_records_command(self, ctx, x: int):
        if not await self.check_channel_validity(ctx):
            return
        await self.send_user_records_stats(ctx, x)

    @app_commands.command(name="check_user_records")
    @app_commands.describe(x="The minimum number of records to query for.")
    async def check_user_records(self, interaction: discord.Interaction, x: int):
        """Slash command to list users who have been recorded greater than x times."""
        await interaction.response.defer()
        if not await self.check_channel_validity(interaction):
            return
        await self.send_user_records_stats(interaction, x)

    async def send_user_records_stats(self, ctx_or_interaction, x):
        top_users = await self.get_users_with_min_records(x)
        if not top_users:
            message = f"No users with more than {x} records found."
        else:
            user_id = ctx_or_interaction.author.id if isinstance(ctx_or_interaction,
                                                                 commands.Context) else ctx_or_interaction.user.id
            view = PaginationView(self.bot, top_users, user_id, 'user_records')
            embed = view.format_page_for_check_user_records()
            if isinstance(ctx_or_interaction, commands.Context):
                message = await ctx_or_interaction.send(content=f"Users with more than {x} records:",
                                                        embed=embed,
                                                        view=view)
            else:  # This is an Interaction
                message = await ctx_or_interaction.edit_original_response(content=f"Users with more than {x} records:",
                                                                          embed=embed,
                                                                          view=view)
        view.message = message

    @check_user_records_command.error
    async def check_user_records_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'x':
                await ctx.send("You need to specify a number. Usage: `!check_user_records <number>`")
        else:
            # print(error)
            await ctx.send("An unexpected error occurred. Please try again.")

    @app_commands.command(name="check_member")
    @app_commands.describe(member="The member to fetch illegal team records for")
    async def check_member(self, interaction: discord.Interaction, member: discord.Member):
        """Lists all illegal teaming records for the specified member."""
        await interaction.response.defer()
        try:
            if not await self.check_channel_validity(interaction):
                return
            if member is None:
                await interaction.followup.send("You must mention a user.", ephemeral=True)
                return
            records = await self.fetch_records_for_user(member.id)
            if not records:
                await interaction.followup.send("No records found for this user.", ephemeral=True)
                return
            view = PaginationView(self.bot, records, member.id, 'check_member')
            message = await interaction.followup.send(content=f"Records for <@{member.id}>",
                                                      embed=view.format_page(),
                                                      view=view)
            view.message = message
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    async def fetch_records_for_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT user_id, timestamp, message FROM illegal_teaming WHERE user_id = ?',
                                 (user_id,))
            records = await cursor.fetchall()
            await cursor.close()
            return records

    @app_commands.command(name="check_member_by_id")
    @app_commands.describe(user_id="The user ID to fetch illegal team records for")
    async def check_member_by_id(self, interaction: discord.Interaction, user_id: str):
        """Lists all illegal teaming records for the specified user ID."""
        await interaction.response.defer()
        try:
            if not await self.check_channel_validity(interaction):
                return
            records = await self.fetch_records_for_user(user_id)
            if not records:
                await interaction.followup.send("No records found for this user.", ephemeral=True)
                return
            view = PaginationView(self.bot, records, int(user_id), 'check_member')  # Convert user_id to int
            message = await interaction.followup.send(content=f"Records for user ID {user_id}",
                                                      embed=view.format_page(),
                                                      view=view)
            view.message = message
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @app_commands.command(name="add_illegal_record")
    @app_commands.describe(
        member="The member to add the illegal teaming record for",
        content="The content of the illegal teaming record",
        time="The time of the illegal teaming record (optional). Format: 'YYYY-MM-DD HH:MM:SS"
    )
    async def add_illegal_record(self, interaction: discord.Interaction, member: discord.Member, content: str,
                                 time: str = None):
        if not await self.check_channel_validity(interaction):
            return

        await interaction.response.defer()

        if time is None:
            time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        view = ConfirmationView(self.bot, interaction.user.id, member, content, time)
        embed = discord.Embed(title="Add Illegal Teaming Record",
                              description=f"You will add an illegal teaming record for {member.mention}.",
                              color=discord.Color.blue())
        embed.add_field(name="Content", value=content, inline=False)
        embed.add_field(name="Time", value=time, inline=False)
        await interaction.edit_original_response(embed=embed, view=view)

    async def add_illegal_record_to_db(self, user_id, content, time):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('INSERT INTO illegal_teaming (user_id, timestamp, message) VALUES (?, ?, ?)',
                                 (user_id, time, content))
            await db.commit()
            await cursor.close()

    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure the table exists
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS illegal_teaming (
                    user_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message TEXT NOT NULL
                )
            ''')
            await db.commit()
