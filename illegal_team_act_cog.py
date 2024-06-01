import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
import sqlite3
from datetime import datetime, timedelta
import aiosqlite

# Checks for illegal teaming are only allowed in certain channels.
CHECK_ILLEGAL_TEAMING_CHANNEL_ID = 114514114514114514


class PaginationView(View):
    def __init__(self, bot, records, user_id):
        super().__init__(timeout=180.0)  # Specify the timeout directly here if needed
        self.bot = bot
        self.records = records
        self.user_id = user_id
        self.page = 0
        self.total_pages = (len(records) - 1) // 20 + 1
        self.total_records = len(records)
        self.message = None  # This will hold the reference to the message
        self.db_path = 'bot.db'  # Path to SQLite database

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
        await interaction.response.edit_message(embed=self.format_page(), view=self)

    async def next_button_callback(self, interaction: discord.Interaction):
        self.page += 1
        await self.update_buttons()
        await interaction.response.edit_message(embed=self.format_page(), view=self)

    def safe_strptime(self, date_str, formats):
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
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


class IllegalTeamActCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'bot.db'  # Path to SQLite database

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
        allowed_channel_id = CHECK_ILLEGAL_TEAMING_CHANNEL_ID
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
        if not await self.check_channel_validity(interaction):
            return
        await self.send_illegal_teaming_stats(interaction)

    async def send_illegal_teaming_stats(self, ctx_or_interaction):
        top_users = await self.get_illegal_teaming_stats()
        if not top_users:
            message = "No illegal teaming records found."
        else:
            message = "Top 20 illegal teaming users:\n"
            for user_id, count in top_users:
                user = self.bot.get_user(int(user_id))
                user_msg = f"{user.mention} with {count} records." if user else f"User ID {user_id} with {count} records is not in the server anymore."
                message += user_msg + "\n"
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(message)
        else:
            await ctx_or_interaction.response.send_message(message)

    @commands.command(name='check_user_records')
    async def check_user_records_command(self, ctx, x: int):
        if not await self.check_channel_validity(ctx):
            return
        await self.send_user_records_stats(ctx, x)

    @app_commands.command(name="check_user_records")
    @app_commands.describe(x="The minimum number of records to query for.")
    async def check_user_records(self, interaction: discord.Interaction, x: int):
        """Slash command to list users who have been recorded greater than x times."""
        if not await self.check_channel_validity(interaction):
            return
        await self.send_user_records_stats(interaction, x)

    async def send_user_records_stats(self, ctx_or_interaction, x):
        top_users = await self.get_users_with_min_records(x)
        if not top_users:
            message = f"No users with more than {x} records found."
        else:
            message = f"Users with more than {x} records:\n"
            for user_id, count in top_users:
                user = self.bot.get_user(int(user_id))
                user_msg = f"{user.mention} with {count} records." if user else f"User ID {user_id} with {count} records is not in the server anymore."
                message += user_msg + "\n"
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(message)
        else:
            await ctx_or_interaction.response.send_message(message)

    @check_user_records_command.error
    async def check_user_records_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'x':
                await ctx.send("You need to specify a number. Usage: `!check_user_records <number>`")
        else:
            await ctx.send("An unexpected error occurred. Please try again.")

    @app_commands.command(name="check_member")
    @app_commands.describe(member="The member to fetch illegal team records for")
    async def check_member(self, interaction: discord.Interaction, member: discord.Member):
        """Lists all illegal teaming records for the specified member."""
        try:
            if not await self.check_channel_validity(interaction):
                return
            if member is None:
                await interaction.response.send_message("You must mention a user.", ephemeral=True)
                return
            records = await self.fetch_records_for_user(member.id)
            if not records:
                await interaction.response.send_message("No records found for this user.", ephemeral=True)
                return
            view = PaginationView(self.bot, records, member.id)
            message = await interaction.response.send_message(content=f"Records for <@{member.id}>",
                                                              embed=view.format_page(),
                                                              view=view)
            view.message = message
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

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
        try:
            if not await self.check_channel_validity(interaction):
                return
            records = await self.fetch_records_for_user(user_id)
            if not records:
                await interaction.response.send_message("No records found for this user.", ephemeral=True)
                return
            view = PaginationView(self.bot, records, int(user_id))  # Convert user_id to int
            message = await interaction.response.send_message(content=f"Records for user ID {user_id}",
                                                              embed=view.format_page(),
                                                              view=view)
            view.message = message
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {str(e)}", ephemeral=True)

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
