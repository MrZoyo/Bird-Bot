import re
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from bot.utils import AchievementDatabaseManager, check_channel_validity, config
from bot.utils.achievement_visibility import (
    filter_visible_achievement_rankings,
    filter_visible_achievement_type_names,
    filter_visible_achievements,
    is_achievement_type_visible,
    resolve_hidden_achievement_types,
)
from bot.utils.i18n import t

from .views import (
    AchievementOperationView,
    AchievementRankingView,
    AchievementRefreshView,
    ConfirmationView,
    RankView,
)
from .rank_locale import rank_button_display_name, rank_intro_type_buttons


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
        return resolve_hidden_achievement_types()

    def is_achievement_type_visible(self, achievement_type: str) -> bool:
        return is_achievement_type_visible(
            achievement_type,
            self.hidden_achievement_types,
        )

    def get_visible_achievements(self) -> list[dict]:
        return filter_visible_achievements(
            self.achievement_config.get('achievements', []),
            self.hidden_achievement_types,
        )

    def get_visible_achievement_rankings(self) -> list[dict]:
        return filter_visible_achievement_rankings(
            self.achievement_config.get('achievements_ranking', []),
            self.hidden_achievement_types,
        )

    def get_visible_achievement_type_names(self) -> dict[str, str]:
        return filter_visible_achievement_type_names(
            self.achievement_config.get('achievements_type_name', {}),
            self.hidden_achievement_types,
        )

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
        description=locale_str(
            "Query the current progress of achievements",
            key="achievements.achievements.description",
        ),
    )
    @app_commands.describe(
        member=locale_str(
            "The member to query. Defaults to self if not provided",
            key="achievements.achievements.params.member",
        ),
        date=locale_str(
            "Optional lookup date in format YYYY-MM (eg. 2024-07)",
            key="achievements.achievements.params.date",
        ),
    )
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
        description=locale_str(
            "Increase the achievement progress of a member",
            key="achievements.increase_achievement.description",
        ),
    )
    @app_commands.describe(
        member=locale_str(
            "The member whose achievement progress to increase",
            key="achievements.increase_achievement.params.member",
        ),
        reactions=locale_str(
            "The number of reactions to increase",
            key="achievements.increase_achievement.params.reactions",
        ),
        messages=locale_str(
            "The number of messages to increase",
            key="achievements.increase_achievement.params.messages",
        ),
        time_spent=locale_str(
            "The time spent on the server to increase (in seconds)",
            key="achievements.increase_achievement.params.time_spent",
        ),
        giveaways=locale_str(
            "The number of giveaways to increase",
            key="achievements.increase_achievement.params.giveaways",
        ),
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
        description=locale_str(
            "Decrease the achievement progress of a member",
            key="achievements.decrease_achievement.description",
        ),
    )
    @app_commands.describe(
        member=locale_str(
            "The member whose achievement progress to decrease",
            key="achievements.decrease_achievement.params.member",
        ),
        reactions=locale_str(
            "The number of reactions to decrease",
            key="achievements.decrease_achievement.params.reactions",
        ),
        messages=locale_str(
            "The number of messages to decrease",
            key="achievements.decrease_achievement.params.messages",
        ),
        time_spent=locale_str(
            "The time spent on the server to decrease (in seconds)",
            key="achievements.decrease_achievement.params.time_spent",
        ),
        giveaways=locale_str(
            "The number of giveaways to decrease",
            key="achievements.decrease_achievement.params.giveaways",
        ),
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
        description=locale_str(
            "Display the achievement rankings",
            key="achievements.achievement_ranking.description",
        ),
    )
    @app_commands.describe(
        date=locale_str(
            "Optional lookup date in format YYYY-MM (eg. 2024-07)",
            key="achievements.achievement_ranking.params.date",
        ),
    )
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
        description=locale_str(
            "Check the records of manual operations on achievements",
            key="achievements.check_ach_ops.description",
        ),
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
        description=locale_str(
            "View achievement rankings in an interactive format",
            key="achievements.rank.description",
        ),
    )
    @app_commands.describe(
        date=locale_str(
            "Optional lookup date in format YYYY-MM (eg. 2024-07)",
            key="achievements.rank.params.date",
        ),
    )
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
            title=t('achievements.rank.intro_title'),
            description=t('achievements.rank.intro_description'),
            color=discord.Color.gold()
        )

        # Add explanations for each button
        all_button_text = t('achievements.rank.intro_all_button')
        intro_type_buttons = rank_intro_type_buttons()
        type_name = self.get_visible_achievement_type_names()

        intro_embed.add_field(
            name=rank_button_display_name('all', view.all_button.label),
            value=all_button_text,
            inline=False,
        )

        # Add fields for each category button
        for button in view.type_buttons:
            # Extract full type name
            button_type_parts = button.custom_id.split('_')[1:]  # Get everything after "type"
            button_type = "_".join(button_type_parts)  # Reconstruct full type name

            # print(f"Button type: {button_type}")  # Debugging log

            # Use the exact same key from the achievements_ranking type
            button_text = intro_type_buttons.get(
                button_type,
                t(
                    'achievements.rank.intro_type_button_default',
                    button_label=button.label
                )
            )

            # Add field with button label and description
            intro_embed.add_field(
                name=type_name.get(button_type, rank_button_display_name(button_type, button.label)),
                value=button_text,
                inline=False,
            )

        # Add footer text and timestamp
        intro_embed.set_footer(text=t('achievements.rank.intro_footer'))
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
