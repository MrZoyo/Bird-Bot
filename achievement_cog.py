import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from datetime import datetime, timezone
from discord.ui import Button, View
from illegal_team_act_cog import IllegalTeamActCog


class AchievementRefreshView(View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=180.0)  # Specify the timeout directly here if needed
        self.db_path = 'bot.db'  # Path to SQLite database
        self.bot = bot
        self.user_id = user_id
        self.message = None  # This will hold the reference to the message

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
                    "INSERT INTO achievements (user_id, message_count, reaction_count, time_spent) VALUES (?, ?, ?, ?)",
                    (self.user_id, 0, 0, 0))
                message_count, reaction_count, time_spent = 0, 0, 0
            else:
                _, message_count, reaction_count, time_spent = user_record

            await db.commit()

        # Define the achievements and their thresholds
        achievements = [
            {"name": "Express Emotion", "description": "Add reactions to 10 messages", "threshold": 10,
             "count": reaction_count},
            {"name": "Tagging Master", "description": "Add reactions to 100 messages", "threshold": 100,
             "count": reaction_count},
            {"name": "How to Comment...", "description": "Add reactions to 1000 messages", "threshold": 1000,
             "count": reaction_count},
            {"name": "Hello!", "description": "Speak 10 times", "threshold": 10, "count": message_count},
            {"name": "Is Anyone There?", "description": "Speak 100 times", "threshold": 100, "count": message_count},
            {"name": "Super Speaker", "description": "Speak 1000 times", "threshold": 1000, "count": message_count},
            {"name": "I'm Always Speaking", "description": "Speak 10000 times", "threshold": 10000,
             "count": message_count},
            {"name": "First Time Chatting", "description": "Stay in voice channel for 60 minutes", "threshold": 60,
             "count": time_spent / 60},
            {"name": "First Day Chatting", "description": "Stay in voice channel for 24 hours", "threshold": 1440,
             "count": time_spent / 60},
            {"name": "Been Chatting for a Month", "description": "Stay in voice channel for 1 month",
             "threshold": 43200, "count": time_spent / 60},
            {"name": "999 Hours of Company", "description": "Stay in voice channel for 999 hours", "threshold": 59940,
             "count": time_spent / 60},
            {"name": "More Time Than Home", "description": "Stay in voice channel for 1 year",
             "threshold": 525600, "count": time_spent / 60},
        ]

        # Count the number of completed achievements
        completed_achievements = sum(1 for a in achievements if a["count"] >= a["threshold"])

        # Get the user's mention and name
        user = await self.bot.fetch_user(self.user_id)
        user_mention = user.mention
        user_name = user.name

        # Create an embed with the user's achievements
        embed = discord.Embed(title=f"Achievements of {user_name}",
                              description=f"{user_mention} completed {completed_achievements}/12 achievements!\n**---------**",
                              color=discord.Color.blue()
                              )

        for achievement in achievements:
            emoji = ":white_check_mark:" if achievement["count"] >= achievement["threshold"] else ":wheelchair:"
            progress = min(1, achievement["count"] / achievement["threshold"])
            progress_bar = f"{emoji} **{achievement['description']}** → `{int(achievement['count'])}/{int(achievement['threshold'])}`\n`{'█' * int(progress * 20)}{' ' * (20 - int(progress * 20))}` `{progress * 100:.2f}%`"
            embed.add_field(name=achievement["name"], value=progress_bar, inline=False)

        return embed


class ConfirmationView(View):
    def __init__(self, bot, member_id, reactions, messages, time_spent, operation):
        super().__init__(timeout=120.0)
        self.bot = bot
        self.member_id = member_id
        self.reactions = reactions
        self.messages = messages
        self.time_spent = time_spent
        self.db_path = 'bot.db'
        self.operation = operation  # 'increase' or 'decrease'

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
                    "INSERT INTO achievements (user_id, message_count, reaction_count, time_spent) VALUES (?, ?, ?, ?)",
                    (self.member_id, 0, 0, 0))
            new_values = (self.messages, self.reactions, self.time_spent, self.member_id)
            if self.operation == 'increase':
                await cursor.execute(
                    "UPDATE achievements SET message_count = message_count + ?, reaction_count = reaction_count + ?, time_spent = time_spent + ? WHERE user_id = ?",
                    new_values)
            elif self.operation == 'decrease':
                await cursor.execute(
                    "UPDATE achievements SET message_count = message_count - ?, reaction_count = reaction_count - ?, time_spent = time_spent - ? WHERE user_id = ?",
                    new_values)
            await db.commit()

        await interaction.edit_original_response(content=f"**Operation {self.operation} complete!**", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="**Operation cancelled!**", view=self)


class AchievementRankingView(View):
    def __init__(self, bot):
        super().__init__(timeout=180.0)
        self.db_path = 'bot.db'  # Path to SQLite database
        self.bot = bot
        self.message = None  # This will hold the reference to the message

    async def format_page(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Fetch the top 10 users for each category
            await cursor.execute("SELECT user_id, reaction_count FROM achievements ORDER BY reaction_count DESC LIMIT 10")
            top_reactions = await cursor.fetchall()
            await cursor.execute("SELECT user_id, message_count FROM achievements ORDER BY message_count DESC LIMIT 10")
            top_messages = await cursor.fetchall()
            await cursor.execute("SELECT user_id, time_spent FROM achievements ORDER BY time_spent DESC LIMIT 10")
            top_time_spent = await cursor.fetchall()

        # Define the emojis for the ranks
        rank_emojis = [":first_place:", ":second_place:", ":third_place:"] + [f":{i}:" for i in ['four', 'five', 'six', 'seven', 'eight', 'nine', 'keycap_ten']]

        # Create an embed with the rankings
        embed = discord.Embed(title=":crown:Achievement Ranking:crown:", color=discord.Color.blue())

        # Define the achievements and their thresholds
        achievements = [
            {"name": ":heart: Add Most Reaction :heart: ", "type": "reactions", "top_users": top_reactions},
            {"name": ":green_heart: Send Most Message :green_heart: ", "type": "messages", "top_users": top_messages},
            {"name": ":yellow_heart: Spent Most Time(min) :yellow_heart: ", "type": "time_spent",
             "top_users": top_time_spent}
        ]

        for achievement in achievements:
            ranking = ""
            for i, (user_id, count) in enumerate(achievement["top_users"]):
                user = await self.bot.fetch_user(user_id)
                if achievement["type"] == "time_spent":
                    count /= 60  # Convert seconds to minutes
                ranking += f"{rank_emojis[i]} {user.mention} - {int(count)}\n"
            embed.add_field(name=achievement["name"], value=ranking, inline=False)

        return embed


class AchievementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'bot.db'  # Path to SQLite database
        self.voice_state = {}  # To track the time users join a voice channel
        self.illegal_act_cog = IllegalTeamActCog(bot)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (message.author.id,))
            user = await cursor.fetchone()

            if user is None:
                # This user is not in the database, so create a new record for them
                await cursor.execute(
                    "INSERT INTO achievements (user_id, message_count, reaction_count, time_spent) VALUES (?, ?, ?, ?)",
                    (message.author.id, 1, 0, 0))
            else:
                # This user is in the database, so increment their message count
                await cursor.execute("UPDATE achievements SET message_count = message_count + 1 WHERE user_id = ?",
                                     (message.author.id,))

            await db.commit()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (user.id,))
            user_record = await cursor.fetchone()

            if user_record is None:
                # This user is not in the database, so create a new record for them
                await cursor.execute(
                    "INSERT INTO achievements (user_id, message_count, reaction_count, time_spent) VALUES (?, ?, ?, ?)",
                    (user.id, 0, 1, 0))
            else:
                # This user is in the database, so increment their reaction count
                await cursor.execute("UPDATE achievements SET reaction_count = reaction_count + 1 WHERE user_id = ?",
                                     (user.id,))

            await db.commit()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        current_time = datetime.now(timezone.utc)

        # If the user was in a voice channel before the update
        if before.channel is not None:
            start_time = self.voice_state.pop(member.id, None)
            if start_time is not None:
                time_spent = (current_time - start_time).total_seconds()

                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.cursor()
                    await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (member.id,))
                    user_record = await cursor.fetchone()

                    if user_record is None:
                        # This user is not in the database, so create a new record for them
                        await cursor.execute(
                            "INSERT INTO achievements (user_id, message_count, reaction_count, time_spent) VALUES (?, ?, ?, ?)",
                            (member.id, 0, 0, time_spent))
                    else:
                        # This user is in the database, so increment their time spent
                        await cursor.execute("UPDATE achievements SET time_spent = time_spent + ? WHERE user_id = ?",
                                             (time_spent, member.id))

                    await db.commit()

        # If the user is in a voice channel after the update
        if after.channel is not None:
            self.voice_state[member.id] = current_time

    @app_commands.command(
        name="achievements",
        description="Query the current progress of achievements"
    )
    @app_commands.describe(member="The member to query. Defaults to self if not provided")
    async def achievements(self, interaction: discord.Interaction, member: discord.Member = None):
        # Defer the interaction
        await interaction.response.defer()

        if member is None:
            member = interaction.user  # Default to the user who invoked the command

        view = AchievementRefreshView(self.bot, member.id)
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
        time_spent="The time spent on the server to increase (in seconds)"
    )
    async def increase_achievement_progress(self, interaction: discord.Interaction, member: discord.Member,
                                            reactions: int = 0,
                                            messages: int = 0, time_spent: int = 0):
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
                    "INSERT INTO achievements (user_id, message_count, reaction_count, time_spent) VALUES (?, ?, ?, ?)",
                    (member.id, 0, 0, 0))
            await db.commit()

            # Create a confirmation view and send it with an embed
            view = ConfirmationView(self.bot, member.id, reactions, messages, time_spent, 'increase')
            embed = discord.Embed(title="Increase Achievement Progress",
                                  description=f"You will increase the achievement progress of {member.mention}.",
                                  color=discord.Color.blue())
            embed.add_field(name="Reactions to Add", value=str(reactions), inline=True)
            embed.add_field(name="Messages to Add", value=str(messages), inline=True)
            embed.add_field(name="Time to Add (seconds)", value=str(time_spent), inline=True)
            await interaction.edit_original_response(embed=embed, view=view)

    @app_commands.command(
        name="decrease_achievement",
        description="Decrease the achievement progress of a member"
    )
    @app_commands.describe(
        member="The member whose achievement progress to decrease",
        reactions="The number of reactions to decrease",
        messages="The number of messages to decrease",
        time_spent="The time spent on the server to decrease (in seconds)"
    )
    async def decrease_achievement_progress(self, interaction: discord.Interaction, member: discord.Member,
                                            reactions: int = 0,
                                            messages: int = 0, time_spent: int = 0):
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
                    "INSERT INTO achievements (user_id, message_count, reaction_count, time_spent) VALUES (?, ?, ?, ?)",
                    (member.id, 0, 0, 0))
            await db.commit()

            # Create a confirmation view and send it with an embed
            view = ConfirmationView(self.bot, member.id, reactions, messages, time_spent, 'decrease')
            embed = discord.Embed(title="Decrease Achievement Progress",
                                  description=f"You will decrease the achievement progress of {member.mention}.",
                                  color=discord.Color.blue())
            embed.add_field(name="Reactions to Subtract", value=str(reactions), inline=True)
            embed.add_field(name="Messages to Subtract", value=str(messages), inline=True)
            embed.add_field(name="Time to Subtract (seconds)", value=str(time_spent), inline=True)
            await interaction.edit_original_response(embed=embed, view=view)

    @app_commands.command(
        name="achievement_ranking",
        description="Display the achievement rankings"
    )
    async def achievement_ranking(self, interaction: discord.Interaction):
        # Defer the interaction
        await interaction.response.defer()

        view = AchievementRankingView(self.bot)
        embed = await view.format_page()
        # Correct method to edit the message after deferring
        await interaction.edit_original_response(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_ready(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    user_id INTEGER PRIMARY KEY,
                    message_count INTEGER DEFAULT 0,
                    reaction_count INTEGER DEFAULT 0,
                    time_spent INTEGER DEFAULT 0
                )
            """)
            await db.commit()
