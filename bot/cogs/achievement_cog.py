# bot/cogs/achievement_cog.py
import discord
import datetime
import re
from discord.ext import commands
from discord import app_commands
import aiosqlite
from datetime import datetime, timezone
from discord.ui import Button, View
from bot.utils import config, check_channel_validity


class AchievementRefreshView(View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user_id = user_id
        self.message = None

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.achievement_config = config.get_config('achievements')

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
        title = self.achievement_config['achievements_page_title'].format(user_name=user_name)
        description = self.achievement_config['achievements_page_description'].format(user_mention=user_mention,
                                                                          completed_achievements=completed_achievements,
                                                                          total_achievements=len(achievements))
        achievements_finish_emoji = self.achievement_config['achievements_finish_emoji']
        achievements_incomplete_emoji = self.achievement_config['achievements_incomplete_emoji']

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
        title = self.achievement_config['achievements_progress_title'].format(date=date)
        type_names = self.achievement_config['achievements_type_name']

        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.set_author(icon_url=user.display_avatar.url, name=user.name)

        embed.add_field(name=type_names['reaction'], value=reaction_count, inline=False)
        embed.add_field(name=type_names['message'], value=message_count, inline=False)
        embed.add_field(name=type_names['time_spent'], value=int(time_spent / 60), inline=False)
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
        self.operation = operation

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.achievement_config = config.get_config('achievements')

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
        self.year = year
        self.month = month

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.achievement_config = config.get_config('achievements')

    async def format_page(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            if self.year is None and self.month is None:
                # Fetch the top 10 users for each category from the achievements table
                await cursor.execute(
                    "SELECT user_id, reaction_count FROM achievements ORDER BY reaction_count DESC LIMIT 10")
                top_reactions = await cursor.fetchall()
                await cursor.execute(
                    "SELECT user_id, message_count FROM achievements ORDER BY message_count DESC LIMIT 10")
                top_messages = await cursor.fetchall()
                await cursor.execute(
                    "SELECT user_id, time_spent FROM achievements ORDER BY time_spent DESC LIMIT 10")
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
        rank_emojis = self.achievement_config['achievements_ranking_emoji']

        # Load the achievement_ranking
        achievements_ranking = self.achievement_config['achievements_ranking']

        # Create an embed with the rankings
        title = self.achievement_config['achievements_ranking_title']
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
            embed.add_field(name=achievement["name"], value=ranking if ranking else "No data", inline=False)

        return embed


class AchievementOperationView(discord.ui.View):
    def __init__(self, bot, user_id, operations, page=1):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user_id = user_id
        self.operations = operations
        self.page = page
        self.message = None  # This will hold the reference to the message

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.achievement_config = config.get_config('achievements')

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
        await interaction.response.defer()
        self.page -= 1
        embed = await self.format_page()
        await interaction.edit_original_response(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page += 1
        embed = await self.format_page()
        await interaction.edit_original_response(embed=embed, view=self)


class RankView(discord.ui.View):
    def __init__(self, bot, year=None, month=None, all_rankings=None):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.year = year
        self.month = month
        self.all_rankings = all_rankings  # Store all pre-fetched rankings
        self.message = None  # Will hold reference to the message

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.achievement_config = config.get_config('achievements')
        self.rank_config = self.achievement_config.get('rank', {})

        # Add buttons for category selection
        self.all_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=self.rank_config.get('all_button_label', "全部排名"),
            custom_id="all"
        )
        self.all_button.callback = self.all_button_callback

        # Create a button for each achievement type
        self.type_buttons = []
        for achievement in self.achievement_config.get('achievements_ranking', []):
            type_name = achievement.get('type')  # This is exactly "time_spent" for the time button
            button_label = self.rank_config.get('type_button_labels', {}).get(type_name, type_name)
            button = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label=button_label,
                custom_id=f"type_{type_name}"  # This becomes "type_time_spent"
            )
            button.callback = self.type_button_callback
            self.type_buttons.append(button)

        # Add all buttons to the view
        self.add_item(self.all_button)
        for button in self.type_buttons:
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Allow anyone to interact with the buttons
        return True

    async def all_button_callback(self, interaction: discord.Interaction):
        """Handle click on the 'All Rankings' button"""
        await interaction.response.defer()

        # Format and display all rankings (like the original achievement_ranking)
        embed = self.format_all_rankings_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    async def type_button_callback(self, interaction: discord.Interaction):
        """Handle click on an individual ranking type button"""
        await interaction.response.defer()

        # Extract type from button custom_id
        type_name_parts = interaction.data['custom_id'].split('_')[1:]  # Get everything after "type"
        type_name = "_".join(type_name_parts)  # Reconstruct full name

        # print(f"Fetching ranking for: {type_name}")  # Debugging log

        # Now it should correctly fetch "time_spent" instead of "time"
        embed = self.format_single_type_embed(type_name)
        await interaction.edit_original_response(embed=embed, view=self)

    def format_all_rankings_embed(self):
        """Format embed showing all rankings (limited to 10 per type)"""
        title = self.achievement_config['achievements_ranking_title']
        if self.year is not None and self.month is not None:
            embed = discord.Embed(
                title=self.rank_config.get('embed_title_date_format', '{title} ({year}-{month})').format(
                    title=title, year=self.year, month=self.month
                ),
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(title=title, color=discord.Color.blue())

        # Define the emojis for the ranks
        rank_emojis = self.achievement_config['achievements_ranking_emoji']

        # Add each achievement type as a field
        for achievement in self.achievement_config.get('achievements_ranking', []):
            type_name = achievement.get('type')
            display_name = achievement.get('name', type_name)

            # Get the top 10 users for this type
            top_users = self.all_rankings.get(type_name, [])[:10]  # Limit to first 10

            ranking = ""
            for i, (user_id, count) in enumerate(top_users):
                if i >= len(rank_emojis):
                    break
                user = self.bot.get_user(int(user_id))
                if type_name == "time_spent":
                    count /= 60  # Convert seconds to minutes
                ranking += f"{rank_emojis[i]} {user.mention if user else f'User ID: {user_id}'} - {int(count)}\n"

            embed.add_field(
                name=display_name,
                value=ranking if ranking else self.rank_config.get('no_data_message', "暂无数据"),
                inline=False
            )

        return embed

    def format_single_type_embed(self, type_name):
        """Format embed showing extended rankings (up to 40) for a single type"""
        # Find the achievement ranking configuration for this type
        achievement_info = next(
            (a for a in self.achievement_config.get('achievements_ranking', []) if a.get('type') == type_name),
            {}
        )

        display_name = achievement_info.get('name', type_name)
        type_display_name = self.achievement_config.get('achievements_type_name', {}).get(type_name, type_name)

        # Create the embed title
        title = self.rank_config.get('embed_title_single', "🏆 {type_name}排行榜 🏆").format(
            type_name=type_display_name
        )

        # Add date to title if provided
        if self.year is not None and self.month is not None:
            title = self.rank_config.get('embed_title_date_format', '{title} ({year}-{month})').format(
                title=title, year=self.year, month=self.month
            )

        embed = discord.Embed(title=title, color=discord.Color.blue())

        # Get the extended top users for this type (up to 40)
        top_users = self.all_rankings.get(type_name, [])[:40]  # Get up to 40 users

        if not top_users:
            embed.description = self.rank_config.get('no_data_message', "暂无数据")
            return embed

        # Get emojis for first 10 ranks
        rank_emojis = self.achievement_config['achievements_ranking_emoji']

        # Split the list into chunks of 10 for better readability
        chunks = [top_users[i:i + 10] for i in range(0, len(top_users), 10)]

        for chunk_index, chunk in enumerate(chunks):
            start_rank = chunk_index * 10 + 1
            end_rank = start_rank + len(chunk) - 1

            ranking = ""
            for i, (user_id, count) in enumerate(chunk):
                rank = start_rank + i

                # Use rank emojis for first 10, then just numbers
                if rank <= 10 and rank - 1 < len(rank_emojis):
                    rank_display = rank_emojis[rank - 1]
                else:
                    rank_display = self.rank_config.get('rank_prefix', "#{rank}").format(rank=rank)

                # Make sure user_id is treated as an integer
                user_id = int(user_id)
                user = self.bot.get_user(user_id)

                # Make sure to handle the time_spent conversion consistently
                display_count = count
                if type_name == "time_spent":
                    display_count = count / 60  # Convert seconds to minutes

                ranking += f"{rank_display} {user.mention if user else f'User ID: {user_id}'} - {int(display_count)}\n"

            field_name = self.rank_config.get('pagination_field_name', "排名 {start}-{end}").format(
                start=start_rank, end=end_rank
            )
            embed.add_field(name=field_name, value=ranking, inline=False)

        return embed


class AchievementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_state = {}  # To track the time users join a voice channel

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.achievement_config = config.get_config('achievements')
        self.achievements = self.achievement_config['achievements']

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
                    await cursor.execute(
                        "SELECT time_spent FROM monthly_achievements WHERE user_id = ? AND year = ? AND month = ?",
                        (member.id, start_year, start_month))
                    user_record = await cursor.fetchone()
                    if user_record:
                        await cursor.execute(
                            "UPDATE monthly_achievements SET time_spent = time_spent + ? WHERE user_id = ? AND year = ? AND month = ?",
                            (time_spent, member.id, start_year, start_month))
                    else:
                        await cursor.execute(
                            "INSERT INTO monthly_achievements (user_id, year, month, time_spent) VALUES (?, ?, ?, ?)",
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
        if not await check_channel_validity(interaction):
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
        if not await check_channel_validity(interaction):
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
        if not await check_channel_validity(interaction):
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

    async def fetch_extended_rankings(self, year=None, month=None):
        """Fetch top 40 users for each achievement type"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Define result structure based on achievement_ranking config
            results = {}
            for achievement in self.achievement_config.get('achievements_ranking', []):
                type_name = achievement.get('type')
                results[type_name] = []

            # Query for each achievement type separately
            if year is None and month is None:
                # All-time rankings
                await cursor.execute(
                    "SELECT user_id, reaction_count FROM achievements WHERE reaction_count > 0 ORDER BY reaction_count DESC LIMIT 40"
                )
                results["reaction"] = await cursor.fetchall()

                await cursor.execute(
                    "SELECT user_id, message_count FROM achievements WHERE message_count > 0 ORDER BY message_count DESC LIMIT 40"
                )
                results["message"] = await cursor.fetchall()

                # Specifically query time_spent data
                await cursor.execute(
                    "SELECT user_id, time_spent FROM achievements WHERE time_spent > 0 ORDER BY time_spent DESC LIMIT 40"
                )
                results["time_spent"] = await cursor.fetchall()

                await cursor.execute(
                    "SELECT user_id, giveaway_count FROM achievements WHERE giveaway_count > 0 ORDER BY giveaway_count DESC LIMIT 40"
                )
                results["giveaway"] = await cursor.fetchall()
            else:
                # Monthly rankings
                await cursor.execute(
                    "SELECT user_id, reaction_count FROM monthly_achievements WHERE year = ? AND month = ? AND reaction_count > 0 ORDER BY reaction_count DESC LIMIT 40",
                    (year, month)
                )
                results["reaction"] = await cursor.fetchall()

                await cursor.execute(
                    "SELECT user_id, message_count FROM monthly_achievements WHERE year = ? AND month = ? AND message_count > 0 ORDER BY message_count DESC LIMIT 40",
                    (year, month)
                )
                results["message"] = await cursor.fetchall()

                # Specifically query time_spent data for the month
                await cursor.execute(
                    "SELECT user_id, time_spent FROM monthly_achievements WHERE year = ? AND month = ? AND time_spent > 0 ORDER BY time_spent DESC LIMIT 40",
                    (year, month)
                )
                results["time_spent"] = await cursor.fetchall()

                await cursor.execute(
                    "SELECT user_id, giveaway_count FROM monthly_achievements WHERE year = ? AND month = ? AND giveaway_count > 0 ORDER BY giveaway_count DESC LIMIT 40",
                    (year, month)
                )
                results["giveaway"] = await cursor.fetchall()

            return results

    @app_commands.command(
        name="rank",
        description="View achievement rankings in an interactive format"
    )
    @app_commands.describe(date="Optional lookup date in format YYYY-MM (eg. 2024-07)")
    async def rank(self, interaction: discord.Interaction, date: str = None):
        """Interactive command to view achievement rankings with filtering options"""
        # Defer the interaction
        await interaction.response.defer()

        # Validate date format
        year = None
        month = None
        if date:
            if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", date):
                await interaction.followup.send("Invalid date format. Please use YYYY-MM.", ephemeral=True)
                return
            year, month = date.split("-")

        # Pre-fetch rankings for all categories (top 40 for each)
        rankings = await self.fetch_extended_rankings(year, month)

        # Create the view with all pre-fetched data
        view = RankView(self.bot, year, month, rankings)

        # Create an intro embed that explains the command functionality
        intro_embed = discord.Embed(
            title=self.achievement_config.get('rank', {}).get('intro_title', "🏆 成就排行榜 🏆"),
            description=self.achievement_config.get('rank', {}).get('intro_description',
                                                                    "请点击下方按钮查看不同类型的成就排行："),
            color=discord.Color.gold()
        )

        # Add explanations for each button
        all_button_text = self.achievement_config.get('rank', {}).get('intro_all_button',
                                                                      "查看所有类型的成就排行（每类显示前10名）")

        type_name = self.achievement_config['achievements_type_name']

        intro_embed.add_field(name=view.all_button.label, value=all_button_text, inline=False)

        # Add fields for each category button
        for button in view.type_buttons:
            # Extract full type name
            button_type_parts = button.custom_id.split('_')[1:]  # Get everything after "type"
            button_type = "_".join(button_type_parts)  # Reconstruct full type name

            # print(f"Button type: {button_type}")  # Debugging log

            # Look up the intro text directly from the config using the exact same type key
            type_buttons_config = self.achievement_config.get('rank', {}).get('intro_type_buttons', {})

            # Use the exact same key from the achievements_ranking type
            button_text = type_buttons_config.get(button_type, f"查看{button.label}排行（显示前40名）")

            # Add field with button label and description
            intro_embed.add_field(name=f"{type_name.get(button_type)}", value=button_text, inline=False)

        # Add footer text and timestamp
        intro_embed.set_footer(text=self.achievement_config.get('rank', {}).get('intro_footer', "点击按钮查看详细排名"))
        intro_embed.timestamp = datetime.now()

        # Set the bot's avatar as the thumbnail if available
        if self.bot.user.avatar:
            intro_embed.set_thumbnail(url=self.bot.user.avatar.url)

        # Send the intro message with buttons
        message = await interaction.followup.send(embed=intro_embed, view=view)
        view.message = message

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
