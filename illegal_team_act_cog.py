import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime, timedelta

# Checks for illegal teaming are only allowed in certain channels.
CHECK_ILLEGAL_TEAMING_CHANNEL_ID = 114514114514114514


class IllegalTeamActCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def log_illegal_activity(self, user_id, message):
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        now = datetime.now()
        formatted_now = now.strftime('%Y-%m-%d %H:%M:%S')
        c.execute('INSERT INTO illegal_teaming (user_id, timestamp, message) VALUES (?, ?, ?)',
                  (user_id, formatted_now, message))
        conn.commit()
        conn.close()

    def remove_illegal_activity(self, user_id):
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        threshold = datetime.now() - timedelta(minutes=5)
        formatted_threshold = threshold.strftime('%Y-%m-%d %H:%M:%S')
        c.execute('DELETE FROM illegal_teaming WHERE user_id = ? AND timestamp > ?', (user_id, formatted_threshold))
        conn.commit()
        conn.close()

    def get_illegal_teaming_stats(self):
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        c.execute('''
            SELECT user_id, COUNT(*) as count FROM illegal_teaming
            GROUP BY user_id
            ORDER BY count DESC
            LIMIT 20
        ''')
        results = c.fetchall()
        conn.close()
        return results

    def get_users_with_min_records(self, min_records):
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        c.execute('''
            SELECT user_id, COUNT(*) as count FROM illegal_teaming
            GROUP BY user_id
            HAVING COUNT(*) > ?
            ORDER BY count DESC
        ''', (min_records,))
        results = c.fetchall()
        conn.close()
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
        top_users = self.get_illegal_teaming_stats()
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
        top_users = self.get_users_with_min_records(x)
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
