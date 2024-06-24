# Author: MrZoyo
# Version: 0.7.2
# Date: 2024-06-24
# ========================================
import discord
from discord import app_commands, ui, components
from discord.ext import commands, tasks
from discord.ui import Button, View
import aiosqlite
import logging

from illegal_team_act_cog import IllegalTeamActCog


class AchievementRoleView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # No interaction time limit
        self.bot = bot

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']
        self.achievements = config['achievements']
        self.role_type_name = config['role_type_name']
        self.achievement_start_role_id = config['achievement_start_role_id']
        self.role_no_column_name_message = config['role_no_column_name_message']
        self.role_no_progress_message = config['role_no_progress_message']
        self.role_no_achievement_message = config['role_no_achievement_message']
        self.role_success_message = config['role_success_message']

        for role in self.role_type_name:
            button = Button(style=components.ButtonStyle.green,
                            label=role['name'],
                            custom_id=role['type'])
            # print(f"Button {role['name']} maps to column {role['data']} with custom_id {role['type']}")  # Debug print
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        # Defer the interaction to avoid timeouts
        await interaction.response.defer()
        # Get the type from the button's custom_id
        achievement_type = interaction.data['custom_id']

        # Get the user's id
        user_id = interaction.user.id

        # print(f"User {user_id} clicked the {achievement_type} button.")

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

        # print(f"User {user_id} has {user_achievement[0]} progress on the {achievement_type} achievement.")
        # Filter the achievements to only include those of the same type
        same_type_achievements = [a for a in self.achievements if a['type'] == achievement_type]
        # Find the highest achievement of the same type that the user is closest to completing
        closest_achievement = max((a for a in same_type_achievements if user_achievement[0] >= a['threshold']),
                                  key=lambda a: a['threshold'], default=None)
        if closest_achievement is None:
            await interaction.followup.send(self.role_no_achievement_message, ephemeral=True)
            return
        # print(f"Closest achievement: {closest_achievement['name']} with threshold {closest_achievement['threshold']}")
        # Get the role for the closest achievement
        role = discord.utils.get(interaction.guild.roles, id=closest_achievement['role_id'])

        # Remove other achievement roles of the same type from the user
        other_roles = [discord.utils.get(interaction.guild.roles, id=a['role_id']) for a in same_type_achievements if
                       a['threshold'] != closest_achievement['threshold']]
        # print(f"Removing lower roles: {[r.name for r in lower_roles]}")
        await interaction.user.remove_roles(*other_roles, reason="Removing other achievement roles")

        # Add the role for the closest achievement to the user
        await interaction.user.add_roles(role, reason="Adding achievement role")

        # Notify the user after successfully adding the role
        await interaction.followup.send(self.role_success_message.format(name=role.name), ephemeral=True)
        logging.info(f"User {user_id} has been awarded the {role.name} role for achieving {closest_achievement['name']}.")


class RoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.illegal_act_cog = IllegalTeamActCog(bot)

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']
        self.achievements = config['achievements']
        self.role_type_name = config['role_type_name']
        self.role_pickup_footer = config['role_pickup_footer']
        self.role_pickup_title = config['role_pickup_title']

    @app_commands.command(
        name="create_role_pickup",
        description="Creates a message on a specific channel for role pickup."
    )
    @app_commands.describe(channel_id="The channel where the message will be created.")
    async def create_role_pickup(self, interaction: discord.Interaction, channel_id: str):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        await interaction.response.defer()

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            await interaction.response.send_message("Channel not found.", ephemeral=True)
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
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('INSERT INTO role_views (message_id, channel_id) VALUES (?, ?)',
                                 (message.id, channel.id))
            await db.commit()
            await cursor.close()

        await interaction.followup.send(f"Role pickup message created in {channel.mention}.")

    async def load_role_views(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT message_id, channel_id FROM role_views')
            records = await cursor.fetchall()
            await cursor.close()

        for message_id, channel_id in records:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                logging.error(f"Error: Channel {channel_id} not found, removing from database")
                await self.remove_role_view(message_id, channel_id)
                continue

            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                logging.error(f"Error: Message {message_id} not found in channel {channel_id}, removing from database")
                await self.remove_role_view(message_id, channel_id)
                continue

            # Recreate the AchievementRoleView and add it to the message
            view = AchievementRoleView(self.bot)
            await message.edit(view=view)

    async def remove_role_view(self, message_id, channel_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('DELETE FROM role_views WHERE message_id = ? AND channel_id = ?',
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
            await db.commit()

        await self.load_role_views()
