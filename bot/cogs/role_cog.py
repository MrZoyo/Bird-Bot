# bot/cogs/role_cog.py
import discord
from discord import app_commands, components
from discord.ext import commands
from discord.ui import Button, View
import aiosqlite
import logging

from bot.utils import config, check_channel_validity


class AchievementRoleView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # No interaction time limit
        self.bot = bot

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.achievement_config = config.get_config('achievements')

        self.role_config = config.get_config('role')
        self.achievements = self.achievement_config['achievements']
        self.role_type_name = self.role_config['role_type_name']
        self.achievement_start_role_id = self.role_config['achievement_start_role_id']
        self.role_no_column_name_message = self.role_config['role_no_column_name_message']
        self.role_no_progress_message = self.role_config['role_no_progress_message']
        self.role_no_achievement_message = self.role_config['role_no_achievement_message']
        self.role_success_message = self.role_config['role_success_message']
        self.role_remove_message = self.role_config['role_remove_message']

        for role in self.role_type_name:
            button = Button(style=components.ButtonStyle.green,
                            label=role['name'],
                            custom_id=role['type'])
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        # Defer the interaction to avoid timeouts
        await interaction.response.defer()
        # Get the type from the button's custom_id
        achievement_type = interaction.data['custom_id']

        # Get the user's id
        user_id = interaction.user.id

        # Check if the user has the achievement start role
        if discord.utils.get(interaction.user.roles, id=self.achievement_start_role_id) is None:
            # add the achievement start role to the user
            start_role = discord.utils.get(interaction.guild.roles, id=self.achievement_start_role_id)
            await interaction.user.add_roles(start_role, reason="Adding achievement start role")

        # Get the column name for the achievement type
        column_name = next((role['data'] for role in self.role_type_name if role['type'] == achievement_type), None)
        if column_name is None:
            await interaction.followup.send(self.role_no_column_name_message, ephemeral=True)
            return

        # Connect to the database
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Get the user's progress for the achievement type
            await cursor.execute(f"SELECT {column_name} FROM achievements WHERE user_id = ?", (user_id,))
            user_achievement = await cursor.fetchone()

        # If the user has no progress for this achievement type, do nothing
        if user_achievement is None or user_achievement[0] is None:
            await interaction.followup.send(self.role_no_progress_message, ephemeral=True)
            return

        # If the achievement type is 'time_spent', divide the user's data by 60
        if achievement_type == 'time_spent':
            user_achievement = (user_achievement[0] / 60,)

        # Filter the achievements to only include those of the same type
        same_type_achievements = [a for a in self.achievements if a['type'] == achievement_type]
        # Sort achievements by threshold in descending order
        same_type_achievements.sort(key=lambda x: x['threshold'], reverse=True)

        # Find the highest achievement the user is eligible for
        highest_eligible_achievement = next(
            (a for a in same_type_achievements if user_achievement[0] >= a['threshold']), None)

        if highest_eligible_achievement is None:
            await interaction.followup.send(self.role_no_achievement_message, ephemeral=True)
            return

        # Get the role for the highest eligible achievement
        highest_eligible_role = discord.utils.get(interaction.guild.roles, id=highest_eligible_achievement['role_id'])

        # Get the user's current achievement role for this type, if any
        current_achievement_role = None
        for achievement in same_type_achievements:
            role = discord.utils.get(interaction.user.roles, id=achievement['role_id'])
            if role:
                current_achievement_role = role
                break

        # If user has their highest eligible role, they can remove it
        if current_achievement_role and current_achievement_role.id == highest_eligible_role.id:
            # Remove all achievement roles of this type
            achievement_roles = [discord.utils.get(interaction.guild.roles, id=a['role_id']) for a in
                                 same_type_achievements]
            await interaction.user.remove_roles(*achievement_roles, reason="Removing achievement roles")
            await interaction.followup.send(
                self.role_remove_message.format(name=current_achievement_role.name),
                ephemeral=True
            )
            logging.info(f"User {user_id} has removed their {current_achievement_role.name} role")
            return

        # If user has a role lower than their highest eligible role
        if current_achievement_role:
            # Remove the current role and give them their highest eligible role
            other_roles = [discord.utils.get(interaction.guild.roles, id=a['role_id']) for a in same_type_achievements]
            await interaction.user.remove_roles(*other_roles, reason="Removing other achievement roles")
            await interaction.user.add_roles(highest_eligible_role, reason="Adding higher achievement role")
            await interaction.followup.send(
                self.role_success_message.format(name=highest_eligible_role.name),
                ephemeral=True
            )
            logging.info(
                f"User {user_id} upgraded from {current_achievement_role.name} to {highest_eligible_role.name}")
            return

        # If user has no role yet, give them their highest eligible role
        await interaction.user.add_roles(highest_eligible_role, reason="Adding achievement role")
        await interaction.followup.send(
            self.role_success_message.format(name=highest_eligible_role.name),
            ephemeral=True
        )
        logging.info(f"User {user_id} has been awarded the {highest_eligible_role.name} role")


class StarSignView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # No interaction time limit
        self.bot = bot
        self.buttons_per_row = 4

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.role_config = config.get_config('role')
        self.starsign_name = self.role_config['starsign_name']
        self.social_start_role_id = self.role_config['social_start_role_id']
        self.starsign_success_message = self.role_config['starsign_success_message']
        self.starsign_remove_message = self.role_config['starsign_remove_message']

        for index, star_sign in enumerate(self.starsign_name):
            row = index % self.buttons_per_row  # Calculate the row for the button
            button = Button(style=components.ButtonStyle.primary,
                            label=star_sign['emoji'],
                            custom_id=star_sign['name'],
                            row=row)
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        await interaction.response.defer()

        star_sign_name = interaction.data['custom_id']

        # Get the role for the clicked star sign
        star_sign_role_id = next(
            (star_sign['role_id'] for star_sign in self.starsign_name if star_sign['name'] == star_sign_name), None)
        star_sign_role = discord.utils.get(interaction.guild.roles, id=star_sign_role_id)

        # Check if user already has this role
        if star_sign_role in interaction.user.roles:
            # Remove the role and send removal message
            await interaction.user.remove_roles(star_sign_role, reason="User removed star sign role")
            await interaction.followup.send(self.starsign_remove_message.format(name=star_sign_role.name),
                                            ephemeral=True)
            logging.info(f"User {interaction.user.id} has removed the {star_sign_role.name} role")
            return

        # Check if the user has the social start role
        if discord.utils.get(interaction.user.roles, id=self.social_start_role_id) is None:
            # add the social start role to the user
            start_role = discord.utils.get(interaction.guild.roles, id=self.social_start_role_id)
            await interaction.user.add_roles(start_role, reason="Adding social start role")

        # Remove other star sign roles from the user
        other_roles = [discord.utils.get(interaction.guild.roles, id=star_sign['role_id']) for star_sign in
                       self.starsign_name if star_sign['name'] != star_sign_name]
        await interaction.user.remove_roles(*other_roles, reason="Removing other star sign roles")

        # Add the role for the clicked star sign to the user
        await interaction.user.add_roles(star_sign_role, reason="Adding star sign role")

        # Notify the user after successfully adding the role
        await interaction.followup.send(self.starsign_success_message.format(name=star_sign_role.name), ephemeral=True)
        logging.info(f"User {interaction.user.id} has been awarded the {star_sign_role.name} role")


class MBTIView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.buttons_per_row = 4

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.role_config = config.get_config('role')
        self.mbti_name = self.role_config['mbti_name']
        self.social_start_role_id = self.role_config['social_start_role_id']
        self.mbti_success_message = self.role_config['mbti_success_message']
        self.mbti_remove_message = self.role_config['mbti_remove_message']

        for index, mbti in enumerate(self.mbti_name):
            row = index % self.buttons_per_row
            button = Button(style=components.ButtonStyle.primary,
                            label=mbti['name'],
                            custom_id=mbti['name'],
                            row=row)
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        await interaction.response.defer()

        mbti_name = interaction.data['custom_id']

        # Get the role for the clicked MBTI type
        mbti_role_id = next(
            (mbti['role_id'] for mbti in self.mbti_name if mbti['name'] == mbti_name), None)
        mbti_role = discord.utils.get(interaction.guild.roles, id=mbti_role_id)

        # Check if user already has this role
        if mbti_role in interaction.user.roles:
            # Remove the role and send removal message
            await interaction.user.remove_roles(mbti_role, reason="User removed MBTI role")
            await interaction.followup.send(self.mbti_remove_message.format(name=mbti_role.name), ephemeral=True)
            logging.info(f"User {interaction.user.id} has removed the {mbti_role.name} role")
            return

        if discord.utils.get(interaction.user.roles, id=self.social_start_role_id) is None:
            start_role = discord.utils.get(interaction.guild.roles, id=self.social_start_role_id)
            await interaction.user.add_roles(start_role, reason="Adding social start role")

        # Remove other MBTI roles from the user
        other_roles = [discord.utils.get(interaction.guild.roles, id=mbti['role_id']) for mbti in
                       self.mbti_name if mbti['name'] != mbti_name]
        await interaction.user.remove_roles(*other_roles, reason="Removing other mbti roles")

        # Add the role for the clicked MBTI type to the user
        await interaction.user.add_roles(mbti_role, reason="Adding mbti role")

        await interaction.followup.send(self.mbti_success_message.format(name=mbti_role.name), ephemeral=True)
        logging.info(f"User {interaction.user.id} has been awarded the {mbti_role.name} role")


class GenderView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.buttons_per_row = 3  # Since we have 3 options

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.role_config = config.get_config('role')
        self.gender_name = self.role_config['gender_name']
        self.gender_success_message = self.role_config['gender_success_message']
        self.gender_remove_message = self.role_config['gender_remove_message']

        for index, gender in enumerate(self.gender_name):
            button = Button(
                style=components.ButtonStyle.primary,
                label=gender['emoji'],
                custom_id=gender['name'],
                row=0  # All buttons in one row since we only have 3
            )
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        await interaction.response.defer()

        gender_name = interaction.data['custom_id']

        # Get the role for the clicked gender
        gender_role_id = next(
            (gender['role_id'] for gender in self.gender_name if gender['name'] == gender_name), None)
        gender_role = discord.utils.get(interaction.guild.roles, id=gender_role_id)

        # Check if user already has this role
        if gender_role in interaction.user.roles:
            # Remove the role and send removal message
            await interaction.user.remove_roles(gender_role, reason="User removed gender role")
            await interaction.followup.send(self.gender_remove_message.format(name=gender_role.name), ephemeral=True)
            logging.info(f"User {interaction.user.id} has removed the {gender_role.name} role")
            return

        # Remove other gender roles from the user
        other_roles = [discord.utils.get(interaction.guild.roles, id=gender['role_id']) for gender in
                       self.gender_name if gender['name'] != gender_name]
        await interaction.user.remove_roles(*other_roles, reason="Removing other gender roles")

        # Add the role for the clicked gender to the user
        await interaction.user.add_roles(gender_role, reason="Adding gender role")

        # Notify the user after successfully adding the role
        await interaction.followup.send(self.gender_success_message.format(name=gender_role.name), ephemeral=True)
        logging.info(f"User {interaction.user.id} has been awarded the {gender_role.name} role")


class RoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.achievement_config = config.get_config('achievements')

        self.role_config = config.get_config('role')
        # Existing config loads
        self.achievements = self.achievement_config['achievements']
        self.role_type_name = self.role_config['role_type_name']

        # StarSign configs
        self.starsign_name = self.role_config['starsign_name']
        self.starsign_pickup_title = self.role_config['starsign_pickup_title']
        self.starsign_pickup_footer = self.role_config['starsign_pickup_footer']
        self.starsign_fire_title = self.role_config['starsign_fire_title']
        self.starsign_fire_description = self.role_config['starsign_fire_description']
        self.starsign_earth_title = self.role_config['starsign_earth_title']
        self.starsign_earth_description = self.role_config['starsign_earth_description']
        self.starsign_air_title = self.role_config['starsign_air_title']
        self.starsign_air_description = self.role_config['starsign_air_description']
        self.starsign_water_title = self.role_config['starsign_water_title']
        self.starsign_water_description = self.role_config['starsign_water_description']

        # MBTI configs
        self.mbti_name = self.role_config['mbti_name']
        self.mbti_pickup_title = self.role_config['mbti_pickup_title']
        self.mbti_pickup_footer = self.role_config['mbti_pickup_footer']
        self.mbti_first_field_title = self.role_config['mbti_first_field_title']
        self.mbti_first_field_description = self.role_config['mbti_first_field_description']
        self.mbti_SP_title = self.role_config['mbti_SP_title']
        self.mbti_SP_description = self.role_config['mbti_SP_description']
        self.mbti_SJ_title = self.role_config['mbti_SJ_title']
        self.mbti_SJ_description = self.role_config['mbti_SJ_description']
        self.mbti_NF_title = self.role_config['mbti_NF_title']
        self.mbti_NF_description = self.role_config['mbti_NF_description']
        self.mbti_NT_title = self.role_config['mbti_NT_title']
        self.mbti_NT_description = self.role_config['mbti_NT_description']

        # Gender configs - new additions
        self.gender_name = self.role_config['gender_name']
        self.gender_pickup_title = self.role_config['gender_pickup_title']
        self.gender_pickup_footer = self.role_config['gender_pickup_footer']
        self.gender_success_message = self.role_config['gender_success_message']
        self.gender_remove_message = self.role_config['gender_remove_message']
        self.gender_tree_title = self.role_config['gender_tree_title']
        self.gender_tree_description = self.role_config['gender_tree_description']
        self.gender_sakura_title = self.role_config['gender_sakura_title']
        self.gender_sakura_description = self.role_config['gender_sakura_description']
        self.gender_ninja_title = self.role_config['gender_ninja_title']
        self.gender_ninja_description = self.role_config['gender_ninja_description']


    @app_commands.command(
        name="create_role_pickup",
        description="Creates a message on a specific channel for role pickup."
    )
    @app_commands.describe(channel_id="The channel where the message will be created.")
    async def create_role_pickup(self, interaction: discord.Interaction, channel_id: str):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            await interaction.followup.send("Channel not found.", ephemeral=True)
            return

        # Create the role pickup message with the AchievementRoleView as its view
        view = AchievementRoleView(self.bot)

        # Create an Embed for each type in the achievement
        embed = discord.Embed(title=self.role_pickup_title, color=discord.Color.blue())
        for role in self.role_type_name:
            achievement_info = "\n".join([f"- **{a['name']}** : `{a['threshold']}`" for a in self.achievements if
                                          a['type'] == role['type']])
            embed.add_field(name=role['name'], value=achievement_info, inline=False)

        embed.set_footer(text=self.role_pickup_footer)

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        message = await channel.send(embed=embed, view=view)

        # Save the view to the database
        await self.save_role_view(message.id, channel.id, table='role_views')

        await interaction.followup.send(f"Role pickup message created in {channel.mention}.")

    @app_commands.command(
        name="create_starsign_pickup",
        description="Creates a message on a specific channel for star sign pickup."
    )
    @app_commands.describe(channel_id="The channel where the message will be created.")
    async def create_starsign_pickup(self, interaction: discord.Interaction, channel_id: str):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            await interaction.response.send_message("Channel not found.", ephemeral=True)
            return

        # Create the role pickup message with the AchievementRoleView as its view
        view = StarSignView(self.bot)

        # Create an Embed for each type in the achievement
        embed = discord.Embed(title=self.starsign_pickup_title, color=discord.Color.purple())
        embed.add_field(name=self.starsign_fire_title, value=self.starsign_fire_description, inline=False)
        embed.add_field(name=self.starsign_earth_title, value=self.starsign_earth_description, inline=False)
        embed.add_field(name=self.starsign_air_title, value=self.starsign_air_description, inline=False)
        embed.add_field(name=self.starsign_water_title, value=self.starsign_water_description, inline=False)

        embed.set_footer(text=self.starsign_pickup_footer)

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        message = await channel.send(embed=embed, view=view)

        # Save the view to the database
        await self.save_role_view(message.id, channel.id, table='starsign_views')

        await interaction.followup.send(f"Star sign pickup message created in {channel.mention}.")

    @app_commands.command(
        name="create_mbti_pickup",
        description="Creates a message on a specific channel for MBTI pickup."
    )
    @app_commands.describe(channel_id="The channel where the message will be created.")
    async def create_mbti_pickup(self, interaction: discord.Interaction, channel_id: str):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            await interaction.response.send_message("Channel not found.", ephemeral=True)
            return

        # Create the role pickup message with the AchievementRoleView as its view
        view = MBTIView(self.bot)

        # Create an Embed for each type in the achievement
        embed = discord.Embed(title=self.mbti_pickup_title, color=discord.Color.gold())

        embed.add_field(name=self.mbti_first_field_title, value=self.mbti_first_field_description, inline=False)
        embed.add_field(name=self.mbti_SP_title, value=self.mbti_SP_description, inline=False)
        embed.add_field(name=self.mbti_SJ_title, value=self.mbti_SJ_description, inline=False)
        embed.add_field(name=self.mbti_NF_title, value=self.mbti_NF_description, inline=False)
        embed.add_field(name=self.mbti_NT_title, value=self.mbti_NT_description, inline=False)

        embed.set_footer(text=self.mbti_pickup_footer)

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        message = await channel.send(embed=embed, view=view)

        # Save the view to the database
        await self.save_role_view(message.id, channel.id, table='mbti_views')

        await interaction.followup.send(f"MBTI pickup message created in {channel.mention}.")

    @app_commands.command(
        name="create_gender_pickup",
        description="Creates a message on a specific channel for gender pickup."
    )
    @app_commands.describe(channel_id="The channel where the message will be created.")
    async def create_gender_pickup(self, interaction: discord.Interaction, channel_id: str):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            await interaction.response.send_message("Channel not found.", ephemeral=True)
            return

        view = GenderView(self.bot)

        embed = discord.Embed(title=self.gender_pickup_title, color=discord.Color.purple())
        embed.add_field(name=self.gender_tree_title, value=self.gender_tree_description, inline=False)
        embed.add_field(name=self.gender_sakura_title, value=self.gender_sakura_description, inline=False)
        embed.add_field(name=self.gender_ninja_title, value=self.gender_ninja_description, inline=False)

        embed.set_footer(text=self.gender_pickup_footer)

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        message = await channel.send(embed=embed, view=view)

        # Save the view to the database
        await self.save_role_view(message.id, channel.id, table='gender_views')

        await interaction.followup.send(f"Gender pickup message created in {channel.mention}.")

    async def save_role_view(self, message_id, channel_id, table='role_views'):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(f'INSERT INTO {table} (message_id, channel_id) VALUES (?, ?)',
                                 (message_id, channel_id))
            await db.commit()
            await cursor.close()

    async def load_role_views(self, table='role_views'):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(f'SELECT message_id, channel_id FROM {table} ')
            records = await cursor.fetchall()
            await cursor.close()

        for message_id, channel_id in records:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                logging.error(f"Error: Channel {channel_id} from {table} not found, removing from database")
                await self.remove_role_view(message_id, channel_id, table=table)
                continue

            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                logging.error(f"Error: Message {message_id} from {table} not found in channel {channel_id}, "
                              f"removing from database")
                await self.remove_role_view(message_id, channel_id, table=table)
                continue

            # Recreate the View and add it to the message
            if table == 'role_views':
                view = AchievementRoleView(self.bot)
            elif table == 'starsign_views':
                view = StarSignView(self.bot)
            elif table == 'mbti_views':
                view = MBTIView(self.bot)
            elif table == 'gender_views':
                view = GenderView(self.bot)

            logging.info(f"Recreating {table} for message {message_id} in channel {channel_id}")

            await message.edit(view=view)

    async def remove_role_view(self, message_id, channel_id, table='role_views'):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(f'DELETE FROM {table} WHERE message_id = ? AND channel_id = ?',
                                 (message_id, channel_id))
            await db.commit()
            await cursor.close()

    @commands.Cog.listener()
    async def on_ready(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Create the role_views table if it does not exist
            await db.execute('''
                CREATE TABLE IF NOT EXISTS role_views (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS starsign_views (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS mbti_views (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS gender_views (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )
            ''')
            await db.commit()

        for table in ['role_views', 'starsign_views', 'mbti_views', 'gender_views']:
            await self.load_role_views(table=table)