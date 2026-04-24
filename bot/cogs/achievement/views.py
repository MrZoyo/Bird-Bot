import discord
from discord.ui import Button, View

from bot.utils import config
from bot.utils.i18n import t


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
        title = t('achievements.achievements_page_title', user_name=user_name)
        description = t(
            'achievements.achievements_page_description',
            user_mention=user_mention,
            completed_achievements=completed_achievements,
            total_achievements=len(achievements),
        )
        achievements_finish_emoji = t('achievements.achievements_finish_emoji')
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
        title = t('achievements.achievements_progress_title', date=date)
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
        title = t('achievements.achievements_ranking_title')
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
        title = t('achievements.achievements_ranking_title')
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
