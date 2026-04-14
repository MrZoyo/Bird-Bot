# bot/cogs/achievement_cog.py
import discord
import datetime
import re
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
from discord.ui import Button, View
from bot.utils import config, check_channel_validity, AchievementDatabaseManager


FEATURE_LINKED_ACHIEVEMENT_TYPES = {
    'giveaway': {'giveaway'},
    'shop': {'checkin_sum', 'checkin_combo'},
}


class AchievementRefreshView(View):
    def __init__(self, bot, user_id, db_manager):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user_id = user_id
        self.message = None
        self.db = db_manager

        self.achievement_config = config.get_config('achievements')

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def format_page(self):
        # Get user achievements using database manager
        user_achievements = await self.db.get_user_achievements(self.user_id)
        achievement_cog = self.bot.get_cog('AchievementCog')

        # Load the achievements from the config.json file
        achievements = achievement_cog.get_visible_achievements()

        # Add the count for each achievement
        for achievement in achievements:
            achievement['count'] = achievement_cog.get_achievement_count_value(
                user_achievements, achievement['type']
            )

        # Group all achievements by type
        achievement_groups = {}
        for achievement in achievements:
            achievement_groups.setdefault(achievement['type'], []).append(achievement)

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
        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        
        # Add user avatar to embed
        embed.set_author(name=user_name, icon_url=user.display_avatar.url)

        first_group = True
        for _, achievements_list in achievement_groups.items():
            if not achievements_list:
                continue
                
            # Add separator between groups
            if not first_group:
                embed.add_field(name="", value="​", inline=False)
            first_group = False
            
            # Build the field value for this category
            category_value = ""
            for achievement in achievements_list:
                is_completed = achievement["count"] >= achievement["threshold"]
                
                if is_completed:
                    # For completed achievements, show checkmark with bold name
                    category_value += f"{achievements_finish_emoji} **{achievement['name']}**\n"
                else:
                    # For incomplete achievements, show bold name and progress bar
                    progress = min(1, achievement["count"] / achievement["threshold"])
                    progress_bar = f"**{achievement['name']}**\n{achievement['description']} → `{int(achievement['count'])}/{int(achievement['threshold'])}`\n`{'█' * int(progress * 20)}{' ' * (20 - int(progress * 20))}` `{progress * 100:.2f}%`\n"
                    category_value += progress_bar
            
            # Add the field for this category without name
            embed.add_field(name="", value=category_value.strip(), inline=False)
        
        return embed


    async def format_page_monthly(self, date):
        year, month = date.split("-")
        # Get user monthly achievements using database manager
        user_achievements = await self.db.get_monthly_achievements(self.user_id, int(year), int(month))
        achievement_cog = self.bot.get_cog('AchievementCog')

        # Get the user's mention and name
        user = await self.bot.fetch_user(self.user_id)
        user_mention = user.mention
        user_name = user.name

        # Create an embed with the user's achievements progress
        title = self.achievement_config['achievements_progress_title'].format(date=date)
        type_names = achievement_cog.get_visible_achievement_type_names()

        embed = discord.Embed(title=title, color=discord.Color.blue())
        embed.set_author(icon_url=user.display_avatar.url, name=user.name)

        for type_name, value in achievement_cog.get_monthly_progress_items(user_achievements):
            embed.add_field(name=type_names[type_name], value=value, inline=False)

        return embed


class ConfirmationView(View):
    def __init__(self, bot, member_id, reactions, messages, time_spent, giveaways, operation, db_manager):
        super().__init__(timeout=120.0)
        self.bot = bot
        self.member_id = member_id
        self.reactions = reactions
        self.messages = messages
        self.time_spent = time_spent
        self.giveaways = giveaways
        self.operation = operation
        self.db = db_manager

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

        # Apply changes using database manager
        changes = {
            'message_count': self.messages,
            'reaction_count': self.reactions,
            'time_spent': self.time_spent,
        }
        if self.bot.get_cog('AchievementCog').is_achievement_type_visible('giveaway'):
            changes['giveaway_count'] = self.giveaways
        
        # Apply the changes
        success = await self.db.apply_manual_changes(self.member_id, changes, self.operation)
        
        if success:
            # Log the operation
            await self.db.log_manual_operation(interaction.user.id, self.member_id, self.operation, changes)
            await interaction.edit_original_response(content=f"**Operation {self.operation} complete!**", view=None)
        else:
            await interaction.edit_original_response(content="**Error processing request!**", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="**Operation cancelled!**", view=self)


class AchievementRankingView(View):
    def __init__(self, bot, db_manager, year=None, month=None):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.year = year
        self.month = month
        self.db = db_manager

        self.achievement_config = config.get_config('achievements')

    async def format_page(self):
        achievement_cog = self.bot.get_cog('AchievementCog')
        ranking_configs = achievement_cog.get_visible_achievement_rankings()

        # Fetch leaderboards using database manager
        top_users = {}
        if self.year is None and self.month is None:
            for ranking in ranking_configs:
                achievement_type = ranking["type"]
                top_users[achievement_type] = await self.db.get_leaderboard(achievement_type, 10)
        else:
            for ranking in ranking_configs:
                achievement_type = ranking["type"]
                top_users[achievement_type] = await self.db.get_monthly_leaderboard(
                    self.year, self.month, achievement_type, 10
                )

        # Define the emojis for the ranks
        rank_emojis = self.achievement_config['achievements_ranking_emoji']

        # Load the achievement_ranking
        achievements_ranking = ranking_configs

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

            operation_lines = [
                f"Operation: {operation}",
                f"Reactions: {reaction_count}",
                f"Messages: {message_count}",
                f"Time Spent: {time_spent}",
            ]
            if self.bot.get_cog('AchievementCog').is_achievement_type_visible('giveaway'):
                operation_lines.append(f"Giveaways: {giveaway_count}")

            embed.add_field(name=f"{timestamp} - {user.name} -> {target_user.name}",
                            value="\n".join(operation_lines),
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

        self.achievement_config = config.get_config('achievements')
        self.rank_config = self.achievement_config.get('rank', {})
        self.achievement_cog = bot.get_cog('AchievementCog')
        self.visible_rankings = self.achievement_cog.get_visible_achievement_rankings()
        self.visible_type_names = self.achievement_cog.get_visible_achievement_type_names()

        # Add buttons for category selection
        self.all_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=self.rank_config.get('all_button_label', "全部排名"),
            custom_id="all"
        )
        self.all_button.callback = self.all_button_callback

        # Create a button for each achievement type
        self.type_buttons = []
        for achievement in self.visible_rankings:
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
        for achievement in self.visible_rankings:
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
            (a for a in self.visible_rankings if a.get('type') == type_name),
            {}
        )

        display_name = achievement_info.get('name', type_name)
        type_display_name = self.visible_type_names.get(type_name, type_name)

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
        self.hidden_achievement_types = self._resolve_hidden_achievement_types()
        self.achievements = self.get_visible_achievements()
        
        # Initialize database manager
        self.db = AchievementDatabaseManager(self.db_path, self.achievement_config)

    def _resolve_hidden_achievement_types(self) -> set[str]:
        hidden_types = set()
        for feature_name, achievement_types in FEATURE_LINKED_ACHIEVEMENT_TYPES.items():
            if not config.is_feature_enabled(feature_name):
                hidden_types.update(achievement_types)
        return hidden_types

    def is_achievement_type_visible(self, achievement_type: str) -> bool:
        return achievement_type not in self.hidden_achievement_types

    def get_visible_achievements(self) -> list[dict]:
        return [
            achievement.copy()
            for achievement in self.achievement_config.get('achievements', [])
            if self.is_achievement_type_visible(achievement.get('type'))
        ]

    def get_visible_achievement_rankings(self) -> list[dict]:
        return [
            ranking.copy()
            for ranking in self.achievement_config.get('achievements_ranking', [])
            if self.is_achievement_type_visible(ranking.get('type'))
        ]

    def get_visible_achievement_type_names(self) -> dict[str, str]:
        return {
            achievement_type: label
            for achievement_type, label in self.achievement_config.get('achievements_type_name', {}).items()
            if self.is_achievement_type_visible(achievement_type)
        }

    def get_achievement_count_value(self, user_achievements: dict, achievement_type: str) -> int | float:
        if achievement_type == 'reaction':
            return user_achievements['reaction_count']
        if achievement_type == 'message':
            return user_achievements['message_count']
        if achievement_type == 'time_spent':
            return user_achievements['time_spent'] / 60
        if achievement_type == 'giveaway':
            return user_achievements['giveaway_count']
        if achievement_type == 'checkin_sum':
            return user_achievements['checkin_sum']
        if achievement_type == 'checkin_combo':
            return user_achievements['checkin_combo']
        return 0

    def get_monthly_progress_items(self, user_achievements: dict) -> list[tuple[str, int]]:
        items = [
            ('reaction', user_achievements['reaction_count']),
            ('message', user_achievements['message_count']),
            ('time_spent', int(user_achievements['time_spent'] / 60)),
            ('giveaway', user_achievements['giveaway_count']),
        ]
        return [
            (achievement_type, value)
            for achievement_type, value in items
            if self.is_achievement_type_visible(achievement_type)
        ]

    async def cog_load(self):
        await self.db.initialize_database()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        current_year, current_month = datetime.now().year, datetime.now().month

        # Update achievements using database manager
        await self.db.update_achievement_count(message.author.id, "message", 1)
        await self.db.update_monthly_achievement_count(message.author.id, "message", 1, current_year, current_month)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        current_year, current_month = datetime.now().year, datetime.now().month

        # Update achievements using database manager
        await self.db.update_achievement_count(user.id, "reaction", 1)
        await self.db.update_monthly_achievement_count(user.id, "reaction", 1, current_year, current_month)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        # When the member leaves a channel
        if before.channel is not None:
            # End voice session and get time spent
            time_spent = await self.db.end_voice_session(member.id, before.channel.id)
            
            if time_spent > 0:
                # Get start time for monthly calculation (approximate using current time)
                current_time = datetime.now(timezone.utc)
                start_time = current_time - timedelta(seconds=time_spent)
                start_month = start_time.month
                start_year = start_time.year
                
                # Update achievements
                await self.db.update_achievement_count(member.id, "time_spent", int(time_spent))
                await self.db.update_monthly_achievement_count(member.id, "time_spent", int(time_spent), start_year, start_month)

        # Handle joining a new channel
        if after.channel is not None:
            # Start new voice session
            await self.db.start_voice_session(member.id, after.channel.id)

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

        view = AchievementRefreshView(self.bot, member.id, self.db)

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

        # Ensure user exists in database
        await self.db.create_user_if_not_exists(member.id)

        if not self.is_achievement_type_visible('giveaway'):
            giveaways = 0

        # Create a confirmation view and send it with an embed
        view = ConfirmationView(self.bot, member.id, reactions, messages, time_spent, giveaways, 'increase', self.db)
        embed = discord.Embed(title="Increase Achievement Progress",
                              description=f"You will increase the achievement progress of {member.mention}.",
                              color=discord.Color.blue())
        embed.add_field(name="Reactions to Add", value=str(reactions), inline=True)
        embed.add_field(name="Messages to Add", value=str(messages), inline=True)
        embed.add_field(name="", value="\u200b", inline=False)
        embed.add_field(name="Time to Add (seconds)", value=str(time_spent), inline=True)
        if self.is_achievement_type_visible('giveaway'):
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

        # Ensure user exists in database
        await self.db.create_user_if_not_exists(member.id)

        if not self.is_achievement_type_visible('giveaway'):
            giveaways = 0

        # Create a confirmation view and send it with an embed
        view = ConfirmationView(self.bot, member.id, reactions, messages, time_spent, giveaways, 'decrease', self.db)
        embed = discord.Embed(title="Decrease Achievement Progress",
                              description=f"You will decrease the achievement progress of {member.mention}.",
                              color=discord.Color.blue())
        embed.add_field(name="Reactions to Subtract", value=str(reactions), inline=True)
        embed.add_field(name="Messages to Subtract", value=str(messages), inline=True)
        embed.add_field(name="", value="\u200b", inline=False)
        embed.add_field(name="Time to Subtract (seconds)", value=str(time_spent), inline=True)
        if self.is_achievement_type_visible('giveaway'):
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
            view = AchievementRankingView(self.bot, self.db)
        else:
            year, month = date.split("-")
            view = AchievementRankingView(self.bot, self.db, int(year), int(month))

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
            operations = await self.db.get_all_operations()
        except Exception as e:
            await interaction.edit_original_response(
                content=f"An error occurred while fetching the records. Error: {e}")
            return

        view = AchievementOperationView(self.bot, interaction.user.id, operations)
        embed = await view.format_page()
        message = await interaction.edit_original_response(embeds=[embed], view=view)
        view.message = message


    async def fetch_extended_rankings(self, year=None, month=None):
        """Fetch top 40 users for each achievement type using database manager"""
        # Define result structure based on achievement_ranking config
        achievement_types = []
        for achievement in self.get_visible_achievement_rankings():
            achievement_types.append(achievement.get('type'))

        if year is None and month is None:
            # Get all-time rankings
            return await self.db.get_all_leaderboards(achievement_types, 40)
        else:
            # Get monthly rankings  
            return await self.db.get_all_monthly_leaderboards(year, month, achievement_types, 40)


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

        type_name = self.get_visible_achievement_type_names()

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
        # Clean up invalid voice sessions
        valid_sessions = []
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                for member in voice_channel.members:
                    if not member.bot:
                        valid_sessions.append((member.id, voice_channel.id))
        
        await self.db.cleanup_invalid_voice_sessions(valid_sessions)
