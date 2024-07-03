# Author: MrZoyo
# Version: 0.7.6
# Date: 2024-07-02
# ========================================
import re
import discord
import datetime
from discord.ext import commands
from discord import app_commands
import aiosqlite
from datetime import datetime, timezone
from discord.ui import Button, View
from illegal_team_act_cog import IllegalTeamActCog


class AchievementRefreshView(View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=180.0)  # Specify the timeout directly here if needed
        self.bot = bot
        self.user_id = user_id
        self.message = None  # This will hold the reference to the message

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def format_page(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (self.user_id,))
            user_record = await cursor.fetchone()

            if user_record is None:
                # This user is not in the database, so create a new record for them
                await cursor.execute(
                    "INSERT INTO achievements (user_id) VALUES (?)",
                    (self.user_id,))
                message_count, reaction_count, time_spent, giveaway_count = 0, 0, 0, 0
            else:
                _, message_count, reaction_count, time_spent, giveaway_count = user_record

            await db.commit()

        # Load the achievements from the config.json file
        achievements = self.bot.get_cog('AchievementCog').achievements

        # Add the count for each achievement
        for achievement in achievements:
            if achievement['type'] == 'reaction':
                achievement['count'] = reaction_count
            elif achievement['type'] == 'message':
                achievement['count'] = message_count
            elif achievement['type'] == 'time_spent':
                achievement['count'] = time_spent / 60  # Convert seconds to minutes
            elif achievement['type'] == 'giveaway':
                achievement['count'] = giveaway_count

        # Count the number of completed achievements
        completed_achievements = sum(1 for a in achievements if a["count"] >= a["threshold"])

        # Get the user's mention and name
        user = await self.bot.fetch_user(self.user_id)
        user_mention = user.mention
        user_name = user.name

        # Create an embed with the user's achievements
        config = self.bot.get_cog('ConfigCog').config
        title = config['achievements_page_title'].format(user_name=user_name)
        description = config['achievements_page_description'].format(user_mention=user_mention,
                                                                     completed_achievements=completed_achievements,
                                                                     total_achievements=len(achievements))
        achievements_finish_emoji = config['achievements_finish_emoji']
        achievements_incomplete_emoji = config['achievements_incomplete_emoji']

        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())

        for achievement in achievements:
            emoji = achievements_finish_emoji if achievement["count"] >= achievement[
                "threshold"] else achievements_incomplete_emoji
            progress = min(1, achievement["count"] / achievement["threshold"])
            progress_bar = f"{emoji} **{achievement['description']}** → `{int(achievement['count'])}/{int(achievement['threshold'])}`\n`{'█' * int(progress * 20)}{' ' * (20 - int(progress * 20))}` `{progress * 100:.2f}%`"
            embed.add_field(name=achievement["name"], value=progress_bar, inline=False)

        return embed

    async def format_page_monthly(self, date):
        year, month = date.split("-")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT * FROM monthly_achievements WHERE user_id = ? AND year = ? AND month = ?",
                                 (self.user_id, year, month))
            user_record = await cursor.fetchone()

            if user_record is None:
                # This user is not in the database, so create a new record for them
                await cursor.execute(
                    "INSERT INTO monthly_achievements (user_id, year, month) VALUES (?, ?, ?)",
                    (self.user_id, year, month))
                message_count, reaction_count, time_spent, giveaway_count = 0, 0, 0, 0
            else:
                _, _, _, message_count, reaction_count, time_spent, giveaway_count = user_record

            await db.commit()

        # Get the user's mention and name
        user = await self.bot.fetch_user(self.user_id)
        user_mention = user.mention
        user_name = user.name

        # Create an embed with the user's achievements progress
        config = self.bot.get_cog('ConfigCog').config
        title = config['achievements_progress_title'].format(date=date)
        type_names = config['achievements_type_name']

        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.set_author(icon_url=user.display_avatar.url, name=user.name)

        embed.add_field(name=type_names['reaction'], value=reaction_count, inline=False)
        embed.add_field(name=type_names['message'], value=message_count, inline=False)
        embed.add_field(name=type_names['time_spent'], value=int(time_spent/60), inline=False)
        embed.add_field(name=type_names['giveaway'], value=giveaway_count, inline=False)

        return embed



class ConfirmationView(View):
    def __init__(self, bot, member_id, reactions, messages, time_spent, giveaways, operation):
        super().__init__(timeout=120.0)
        self.bot = bot
        self.member_id = member_id
        self.reactions = reactions
        self.messages = messages
        self.time_spent = time_spent
        self.giveaways = giveaways
        self.operation = operation  # 'increase' or 'decrease'

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        self.stop()  # Optionally stop further interactions if desired
        await self.message.edit(content="**Timeout: No longer accepting interactions.**", view=self)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Immediate feedback
        await interaction.response.edit_message(content="**Processing your request...**", view=None)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (self.member_id,))
            user_record = await cursor.fetchone()

            if user_record is None:
                await cursor.execute(
                    "INSERT INTO achievements (user_id) VALUES (?)",
                    (self.member_id,))
            new_values = (self.messages, self.reactions, self.time_spent, self.giveaways, self.member_id)
            if self.operation == 'increase':
                await cursor.execute(
                    "UPDATE achievements SET message_count = message_count + ?, reaction_count = reaction_count + ?, time_spent = time_spent + ?, giveaway_count = giveaway_count + ? WHERE user_id = ?",
                    new_values)

                # Record the operation in the achievement_operation table
                await cursor.execute(
                    "INSERT INTO achievement_operation (user_id, target_user_id, operation, message_count, reaction_count, time_spent, giveaway_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (interaction.user.id, self.member_id, 'increase', self.messages, self.reactions, self.time_spent,
                     self.giveaways))

            elif self.operation == 'decrease':
                await cursor.execute(
                    "UPDATE achievements SET message_count = message_count - ?, reaction_count = reaction_count - ?, time_spent = time_spent - ?, giveaway_count = giveaway_count - ? WHERE user_id = ?",
                    new_values)

                # Record the operation in the achievement_operation table
                await cursor.execute(
                    "INSERT INTO achievement_operation (user_id, target_user_id, operation, message_count, reaction_count, time_spent, giveaway_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (interaction.user.id, self.member_id, 'decrease', self.messages, self.reactions, self.time_spent,
                     self.giveaways))

            await db.commit()

        await interaction.edit_original_response(content=f"**Operation {self.operation} complete!**", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="**Operation cancelled!**", view=self)


class AchievementRankingView(View):
    def __init__(self, bot, year=None, month=None):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.message = None  # This will hold the reference to the message
        self.year = year
        self.month = month

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']

    async def format_page(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            if self.year is None and self.month is None:
                # Fetch the top 10 users for each category from the achievements table
                await cursor.execute(
                    "SELECT user_id, reaction_count FROM achievements ORDER BY reaction_count DESC LIMIT 10")
                top_reactions = await cursor.fetchall()
                await cursor.execute("SELECT user_id, message_count FROM achievements ORDER BY message_count DESC LIMIT 10")
                top_messages = await cursor.fetchall()
                await cursor.execute("SELECT user_id, time_spent FROM achievements ORDER BY time_spent DESC LIMIT 10")
                top_time_spent = await cursor.fetchall()
                await cursor.execute(
                    "SELECT user_id, giveaway_count FROM achievements ORDER BY giveaway_count DESC LIMIT 10")
                top_giveaways = await cursor.fetchall()
            else:
                # Fetch the top 10 users for each category from the monthly_achievements table
                await cursor.execute(
                    "SELECT user_id, reaction_count FROM monthly_achievements WHERE year = ? AND month = ? ORDER BY reaction_count DESC LIMIT 10",
                    (self.year, self.month))
                top_reactions = await cursor.fetchall()
                await cursor.execute(
                    "SELECT user_id, message_count FROM monthly_achievements WHERE year = ? AND month = ? ORDER BY message_count DESC LIMIT 10",
                    (self.year, self.month))
                top_messages = await cursor.fetchall()
                await cursor.execute(
                    "SELECT user_id, time_spent FROM monthly_achievements WHERE year = ? AND month = ? ORDER BY time_spent DESC LIMIT 10",
                    (self.year, self.month))
                top_time_spent = await cursor.fetchall()
                await cursor.execute(
                    "SELECT user_id, giveaway_count FROM monthly_achievements WHERE year = ? AND month = ? ORDER BY giveaway_count DESC LIMIT 10",
                    (self.year, self.month))
                top_giveaways = await cursor.fetchall()

        # Map the types to the corresponding SQL query results
        top_users = {
            "reaction": top_reactions,
            "message": top_messages,
            "time_spent": top_time_spent,
            "giveaway": top_giveaways
        }

        # Define the emojis for the ranks
        config = self.bot.get_cog('ConfigCog').config
        rank_emojis = config['achievements_ranking_emoji']

        # Load the achievement_ranking
        achievements_ranking = config['achievements_ranking']

        # Create an embed with the rankings
        title = config['achievements_ranking_title']
        if self.year is not None and self.month is not None:
            embed = discord.Embed(title=f"{title} ({self.year}-{self.month})", color=discord.Color.blue())
        else:
            embed = discord.Embed(title=title, color=discord.Color.blue())

        for achievement in achievements_ranking:
            ranking = ""
            for i, (user_id, count) in enumerate(top_users[achievement["type"]]):
                user = await self.bot.fetch_user(user_id)
                if achievement["type"] == "time_spent":
                    count /= 60  # Convert seconds to minutes
                ranking += f"{rank_emojis[i]} {user.mention} - {int(count)}\n"
            embed.add_field(name=achievement["name"], value=ranking, inline=False)

        return embed


class AchievementOperationView(discord.ui.View):
    def __init__(self, bot, user_id, operations, page=1):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user_id = user_id
        self.operations = operations
        self.page = page
        self.message = None  # This will hold the reference to the message

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']

        # Define the buttons
        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.primary, disabled=True)
        self.next_button = Button(label="Next", style=discord.ButtonStyle.green, disabled=True)

        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        # Add the buttons to the view
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

        self.item_each_page = 5
        self.total_pages = (len(operations) - 1) // self.item_each_page + 1
        self.total_records = len(operations)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def format_page(self):
        # Fetch the records for the current page from memory
        records = self.operations[(self.page - 1) * self.item_each_page: self.page * self.item_each_page]

        # Enable or disable the buttons based on the existence of more records
        self.children[0].disabled = (self.page == 1)
        self.children[1].disabled = ((self.page * self.item_each_page) >= len(self.operations))

        # Create an embed with the records
        embed = discord.Embed(title="Achievement Operations Log", color=discord.Color.blue())

        for record in records:
            user = await self.bot.fetch_user(record[0])
            target_user = await self.bot.fetch_user(record[1])
            operation = record[2]
            message_count = record[3]
            reaction_count = record[4]
            time_spent = record[5]
            timestamp = record[6]
            giveaway_count = record[7]

            embed.add_field(name=f"{timestamp} - {user.name} -> {target_user.name}",
                            value=f"Operation: {operation}\n"
                                  f"Reactions: {reaction_count}\n"
                                  f"Messages: {message_count}\n"
                                  f"Time Spent: {time_spent}\n"
                                  f"Giveaways: {giveaway_count}",
                            inline=False)

        # Add the page information to the embed
        embed.set_footer(text=f"Page {self.page}/{self.total_pages} ({self.total_records} records)")

        return embed

    async def previous_page(self, interaction: discord.Interaction):
        self.page -= 1
        embed = await self.format_page()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        embed = await self.format_page()
        await interaction.response.edit_message(embed=embed, view=self)


class AchievementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_state = {}  # To track the time users join a voice channel
        self.illegal_act_cog = IllegalTeamActCog(bot)

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']
        self.achievements = config['achievements']

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        current_year, current_month = datetime.now().year, datetime.now().month

        async with aiosqlite.connect(self.db_path) as db:
            # For table achievements
            cursor = await db.cursor()
            await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (message.author.id,))
            user_record = await cursor.fetchone()

            if user_record is None:
                # This user is not in the database, so create a new record for them
                await cursor.execute(
                    "INSERT INTO achievements (user_id, message_count) VALUES (?, ?)",
                    (message.author.id, 1))
            else:
                # This user is in the database, so increment their message count
                await cursor.execute("UPDATE achievements SET message_count = message_count + 1 WHERE user_id = ?",
                                     (message.author.id,))


            # For table monthly_achievements
            await cursor.execute("SELECT * FROM monthly_achievements WHERE user_id = ? AND year = ? AND month = ?",
                                 (message.author.id, current_year, current_month))
            user_record = await cursor.fetchone()

            if user_record is None:
                await cursor.execute(
                    "INSERT INTO monthly_achievements (user_id, year, month, message_count) VALUES (?, ?, ?, ?)",
                    (message.author.id, current_year, current_month, 1))
            else:
                await cursor.execute(
                    "UPDATE monthly_achievements SET message_count = message_count + 1 WHERE user_id = ? AND year = ? AND month = ?",
                    (message.author.id, current_year, current_month))
            await db.commit()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        current_year, current_month = datetime.now().year, datetime.now().month

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            # For table achievements
            await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (user.id,))
            user_record = await cursor.fetchone()

            if user_record is None:
                # This user is not in the database, so create a new record for them
                await cursor.execute(
                    "INSERT INTO achievements (user_id, reaction_count) VALUES (?, ?)",
                    (user.id, 1))
            else:
                # This user is in the database, so increment their reaction count
                await cursor.execute("UPDATE achievements SET reaction_count = reaction_count + 1 WHERE user_id = ?",
                                     (user.id,))

            # For table monthly_achievements
            await cursor.execute("SELECT * FROM monthly_achievements WHERE user_id = ? AND year = ? AND month = ?",
                                 (user.id, current_year, current_month))
            user_record = await cursor.fetchone()

            if user_record is None:
                await cursor.execute(
                    "INSERT INTO monthly_achievements (user_id, year, month, reaction_count) VALUES (?, ?, ?, ?)",
                    (user.id, current_year, current_month, 1))
            else:
                await cursor.execute(
                    "UPDATE monthly_achievements SET reaction_count = reaction_count + 1 WHERE user_id = ? AND year = ? AND month = ?",
                    (user.id, current_year, current_month))

            await db.commit()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        current_time = datetime.now(timezone.utc)

        # When the member leaves a channel
        if before.channel is not None:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.cursor()
                # Retrieve the start time and channel ID from the database for the user
                await cursor.execute("SELECT start_time, channel_id FROM voice_channel_entries WHERE user_id = ?",
                                     (member.id,))
                entry = await cursor.fetchone()

                # Process time spent only if the user left the same channel they entered
                if entry and entry[1] == before.channel.id:
                    start_time = datetime.fromisoformat(entry[0])
                    time_spent = (current_time - start_time).total_seconds()

                    start_month = start_time.month
                    start_year = start_time.year

                    # Update or insert time spent in achievements
                    await cursor.execute("SELECT time_spent FROM achievements WHERE user_id = ?",
                                         (member.id,))
                    user_record = await cursor.fetchone()
                    if user_record:
                        await cursor.execute("UPDATE achievements SET time_spent = time_spent + ? WHERE user_id = ?",
                                             (time_spent, member.id))
                    else:
                        await cursor.execute("INSERT INTO achievements (user_id, time_spent) VALUES (?, ?)",
                                             (member.id, time_spent))

                    # Update or insert time spent in monthly_achievements
                    await cursor.execute("SELECT time_spent FROM monthly_achievements WHERE user_id = ? AND year = ? AND month = ?",
                                         (member.id, start_year, start_month))
                    user_record = await cursor.fetchone()
                    if user_record:
                        await cursor.execute("UPDATE monthly_achievements SET time_spent = time_spent + ? WHERE user_id = ? AND year = ? AND month = ?",
                                             (time_spent, member.id, start_year, start_month))
                    else:
                        await cursor.execute("INSERT INTO monthly_achievements (user_id, year, month, time_spent) VALUES (?, ?, ?, ?)",
                                             (member.id, start_year, start_month, time_spent))

                    # Delete the entry from voice_channel_entries since the session is complete
                    await cursor.execute("DELETE FROM voice_channel_entries WHERE user_id = ? AND channel_id = ?",
                                         (member.id, before.channel.id))

                await db.commit()

        # Handle joining a new channel
        if after.channel is not None:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.cursor()
                # Record the new channel entry
                await cursor.execute(
                    "REPLACE INTO voice_channel_entries (user_id, channel_id, start_time) VALUES (?, ?, ?)",
                    (member.id, after.channel.id, current_time.isoformat()))
                await db.commit()

    @app_commands.command(
        name="achievements",
        description="Query the current progress of achievements"
    )
    @app_commands.describe(member="The member to query. Defaults to self if not provided",
                           date="Optional lookup date in format YYYY-MM (eg. 2024-07)")
    async def achievements(self, interaction: discord.Interaction, member: discord.Member = None, date: str = None):
        # Defer the interaction
        await interaction.response.defer()

        if member is None:
            member = interaction.user  # Default to the user who invoked the command

        # Validate date format
        if date and not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", date):
            await interaction.followup.send("Invalid date format. Please use YYYY-MM.", ephemeral=True)
            return

        view = AchievementRefreshView(self.bot, member.id)

        if date:
            embed = await view.format_page_monthly(date)
        else:
            embed = await view.format_page()
        message = await interaction.edit_original_response(embeds=[embed], view=view)
        view.message = message

    @app_commands.command(
        name="increase_achievement",
        description="Increase the achievement progress of a member"
    )
    @app_commands.describe(
        member="The member whose achievement progress to increase",
        reactions="The number of reactions to increase",
        messages="The number of messages to increase",
        time_spent="The time spent on the server to increase (in seconds)",
        giveaways="The number of giveaways to increase"
    )
    async def increase_achievement_progress(self, interaction: discord.Interaction, member: discord.Member,
                                            reactions: int = 0,
                                            messages: int = 0,
                                            time_spent: int = 0,
                                            giveaways: int = 0):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        await interaction.response.defer()  # Properly defer to handle possibly lengthy DB operations

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (member.id,))
            user_record = await cursor.fetchone()

            if user_record is None:
                # This user is not in the database, so create a new empty record for them
                await cursor.execute(
                    "INSERT INTO achievements (user_id) VALUES (?)",
                    (member.id,))
            await db.commit()

            # Create a confirmation view and send it with an embed
            view = ConfirmationView(self.bot, member.id, reactions, messages, time_spent, giveaways, 'increase')
            embed = discord.Embed(title="Increase Achievement Progress",
                                  description=f"You will increase the achievement progress of {member.mention}.",
                                  color=discord.Color.blue())
            embed.add_field(name="Reactions to Add", value=str(reactions), inline=True)
            embed.add_field(name="Messages to Add", value=str(messages), inline=True)
            embed.add_field(name="", value="\u200b", inline=False)
            embed.add_field(name="Time to Add (seconds)", value=str(time_spent), inline=True)
            embed.add_field(name="Giveaways to Add", value=str(giveaways), inline=True)
            await interaction.edit_original_response(embed=embed, view=view)

    @app_commands.command(
        name="decrease_achievement",
        description="Decrease the achievement progress of a member"
    )
    @app_commands.describe(
        member="The member whose achievement progress to decrease",
        reactions="The number of reactions to decrease",
        messages="The number of messages to decrease",
        time_spent="The time spent on the server to decrease (in seconds)",
        giveaways="The number of giveaways to decrease"
    )
    async def decrease_achievement_progress(self, interaction: discord.Interaction, member: discord.Member,
                                            reactions: int = 0,
                                            messages: int = 0,
                                            time_spent: int = 0,
                                            giveaways: int = 0):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        await interaction.response.defer()  # Defer interaction for database operations

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (member.id,))
            user_record = await cursor.fetchone()

            if user_record is None:
                # This user is not in the database, so create a new empty record for them
                await cursor.execute(
                    "INSERT INTO achievements (user_id) VALUES (?)",
                    (member.id,))
            await db.commit()

            # Create a confirmation view and send it with an embed
            view = ConfirmationView(self.bot, member.id, reactions, messages, time_spent, giveaways, 'decrease')
            embed = discord.Embed(title="Decrease Achievement Progress",
                                  description=f"You will decrease the achievement progress of {member.mention}.",
                                  color=discord.Color.blue())
            embed.add_field(name="Reactions to Subtract", value=str(reactions), inline=True)
            embed.add_field(name="Messages to Subtract", value=str(messages), inline=True)
            embed.add_field(name="", value="\u200b", inline=False)
            embed.add_field(name="Time to Subtract (seconds)", value=str(time_spent), inline=True)
            embed.add_field(name="Giveaways to Subtract", value=str(giveaways), inline=True)
            await interaction.edit_original_response(embed=embed, view=view)

    @app_commands.command(
        name="achievement_ranking",
        description="Display the achievement rankings"
    )
    @app_commands.describe(date="Optional lookup date in format YYYY-MM (eg. 2024-07)")
    async def achievement_ranking(self, interaction: discord.Interaction, date: str = None):
        # Defer the interaction
        await interaction.response.defer()

        # Validate date format
        if date and not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", date):
            await interaction.followup.send("Invalid date format. Please use YYYY-MM.", ephemeral=True)
            return

        if not date:
            view = AchievementRankingView(self.bot)
        else:
            year, month = date.split("-")
            view = AchievementRankingView(self.bot, year, month)

        embed = await view.format_page()
        # Correct method to edit the message after deferring
        await interaction.edit_original_response(embed=embed, view=view)

    @app_commands.command(
        name="check_ach_ops",
        description="Check the records of manual operations on achievements"
    )
    async def check_ach_ops(self, interaction: discord.Interaction):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        await interaction.response.defer()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT * FROM achievement_operation ORDER BY timestamp DESC")
                operations = await cursor.fetchall()

        except Exception as e:
            await interaction.edit_original_response(
                content=f"An error occurred while fetching the records. Error: {e}")
            return

        view = AchievementOperationView(self.bot, interaction.user.id, operations)
        embed = await view.format_page()
        message = await interaction.edit_original_response(embeds=[embed], view=view)
        view.message = message

    async def check_table_exists(self, table_name='achievements'):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Check if the achievements table exists
            await cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            table_exists = await cursor.fetchone() is not None

            await cursor.close()

        return table_exists

    async def add_giveaway_count_column(self, table_name):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Fetch the information of all columns in the specified table
            await cursor.execute(f"PRAGMA table_info({table_name})")
            columns = await cursor.fetchall()

            # Check if the giveaway_count column exists
            if not any(column[1] == 'giveaway_count' for column in columns):
                # The giveaway_count column does not exist, so add it
                await cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN giveaway_count INTEGER DEFAULT 0")

            await db.commit()
            await cursor.close()

    @app_commands.command(
        name="fix_achievements",
        description="If you have run this bot before version 0.7.0, use this command to repair the database."
    )
    async def fix_achievements(self, interaction: discord.Interaction):
        # if the achievements table exists, add the giveaway_count column
        if await self.check_table_exists(table_name='achievements'):
            await self.add_giveaway_count_column(table_name='achievements')

        # if the achievement_operation table exists, add the giveaway_count column
        if await self.check_table_exists(table_name='achievement_operation'):
            await self.add_giveaway_count_column(table_name='achievement_operation')

        await interaction.response.send_message("The database has been repaired.")

    @commands.Cog.listener()
    async def on_ready(self):

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    user_id INTEGER PRIMARY KEY,
                    message_count INTEGER DEFAULT 0,
                    reaction_count INTEGER DEFAULT 0,
                    time_spent INTEGER DEFAULT 0,
                    giveaway_count INTEGER DEFAULT 0
                )
            """)
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS voice_channel_entries (
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, channel_id)
                )
            """)

            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS achievement_operation (
                    user_id INTEGER NOT NULL,
                    target_user_id INTEGER NOT NULL,
                    operation TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    reaction_count INTEGER DEFAULT 0,
                    time_spent INTEGER DEFAULT 0,
                    giveaway_count INTEGER DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                 )
            """)

            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS monthly_achievements (
                    user_id INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    reaction_count INTEGER DEFAULT 0,
                    time_spent INTEGER DEFAULT 0,
                    giveaway_count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, year, month)
                )
            """)

            # Fetch all the users that have been logged in voice_channel_entries
            await cursor.execute("SELECT user_id, channel_id FROM voice_channel_entries")
            entries = await cursor.fetchall()

            for user_id, channel_id in entries:
                member = None
                for guild in self.bot.guilds:
                    member = guild.get_member(user_id)
                    if member is not None:
                        break
                if member is None or member.voice is None or member.voice.channel.id != channel_id:
                    # The member is no longer on the server or is currently in a different room
                    await cursor.execute("DELETE FROM voice_channel_entries WHERE user_id = ? AND channel_id = ?",
                                         (user_id, channel_id))
            await db.commit()
