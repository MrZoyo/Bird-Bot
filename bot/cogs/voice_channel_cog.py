# bot/cogs/voice_channel_cog.py
from asyncio import sleep

import aiosqlite
import logging
import discord
from discord.ui import Button
from discord.ext import commands, tasks
from discord import app_commands, ui
import json
import aiofiles
from pathlib import Path

from bot.utils import config, check_channel_validity


class AddChannelForm(ui.Modal, title='Add Voice Channel Configuration'):
    channel_id = ui.TextInput(
        label='Channel ID',
        placeholder='Enter the voice channel ID',
        required=True,
        min_length=17,
        max_length=20
    )
    name_prefix = ui.TextInput(
        label='Room Name Prefix',
        placeholder='Enter the prefix for created rooms (e.g., "游戏房")',
        required=True,
        max_length=10
    )
    channel_type = ui.TextInput(
        label='Channel Type',
        placeholder='Enter "public" or "private"',
        required=True,
        max_length=7,
        default="public"
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Validate channel ID
        try:
            channel_id = int(self.channel_id.value)
            channel = interaction.guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                await interaction.followup.send("Invalid channel ID or channel is not a voice channel.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("Invalid channel ID format.", ephemeral=True)
            return

        # Validate channel type
        if self.channel_type.value.lower() not in ['public', 'private']:
            await interaction.followup.send("Channel type must be either 'public' or 'private'.", ephemeral=True)
            return

        # Add the new channel configuration
        config_data = {
            "name_prefix": self.name_prefix.value,
            "type": self.channel_type.value.lower()
        }

        # Update the cog's channel_configs
        self.cog.channel_configs[channel_id] = config_data

        # Save to file
        await self.cog.save_channel_configs()

        # Create embed for confirmation
        embed = discord.Embed(
            title="Voice Channel Configuration Added",
            color=discord.Color.green()
        )
        embed.add_field(name="Channel", value=f"<#{channel_id}>", inline=False)
        embed.add_field(name="Name Prefix", value=config_data["name_prefix"], inline=True)
        embed.add_field(name="Type", value=config_data["type"].capitalize(), inline=True)

        await interaction.followup.send(embed=embed)


class DeleteChannelConfirmView(discord.ui.View):
    def __init__(self, cog, channel_id):
        super().__init__(timeout=60)
        self.cog = cog
        self.channel_id = channel_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Remove the channel configuration
        if self.channel_id in self.cog.channel_configs:  # Check for integer ID
            del self.cog.channel_configs[self.channel_id]
            await self.cog.save_channel_configs()

            embed = discord.Embed(
                title="Voice Channel Configuration Removed",
                description=f"Configuration for channel <#{self.channel_id}> has been removed.",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title="Error",
                description=f"No configuration found for channel <#{self.channel_id}>",
                color=discord.Color.red()
            )

        self.disable_all_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Operation Cancelled",
            description="Channel configuration removal cancelled.",
            color=discord.Color.blue()
        )
        self.disable_all_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    def disable_all_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True


class CheckTempChannelView(discord.ui.View):
    def __init__(self, bot, user_id, records, page=1):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user_id = user_id
        self.records = records
        self.page = page
        self.message = None  # This will hold the reference to the message

        self.conf = config.get_config()
        self.db_path = self.conf['db_path']

        # Define the buttons
        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.primary, disabled=True)
        self.next_button = Button(label="Next", style=discord.ButtonStyle.green, disabled=True)

        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        # Add the buttons to the view
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

        self.item_each_page = 5
        self.total_pages = (len(records) - 1) // self.item_each_page + 1
        self.total_records = len(records)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def format_page(self):
        # Fetch the records for the current page from memory
        records = self.records[(self.page - 1) * self.item_each_page: self.page * self.item_each_page]

        # Enable or disable the buttons based on the existence of more records
        self.children[0].disabled = (self.page == 1)
        self.children[1].disabled = ((self.page * self.item_each_page) >= len(self.records))

        # Create an embed with the records
        embed = discord.Embed(title="Temp Channel Records", color=discord.Color.blue())

        records_str = ""
        for record in records:
            channel_id = record[0]
            creator_id = record[1]
            created_at = record[2]
            records_str += (f"Time: {created_at}\n"
                            f"Channel: <#{channel_id}>\n"
                            f"Channel ID: {channel_id}\n"
                            f"Creator: <@{creator_id}>\n\n")

        embed.add_field(name="Records", value=records_str, inline=False)

        # Add footer
        embed.set_footer(text=f"Page {self.page}/{self.total_pages} - Total channels: {self.total_records}")

        return embed

    async def previous_page(self, interaction: discord.Interaction):
        self.page -= 1
        embed = await self.format_page()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        embed = await self.format_page()
        await interaction.response.edit_message(embed=embed, view=self)


class VoiceStateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.conf = config.get_config('voicechannel')
        self.channel_configs = {int(channel_id): c for channel_id, c in self.conf['channel_configs'].items()}

        self.soundboard_not_in_vc_message = self.conf['soundboard_not_in_vc_message']
        self.soundboard_no_permission_message = self.conf['soundboard_no_permission_message']
        self.soundboard_disabled_message = self.conf['soundboard_disabled_message']
        self.soundboard_enabled_message = self.conf['soundboard_enabled_message']

        # Start the cleanup task
        self.cleanup_task.start()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if after.channel and after.channel.id in self.channel_configs:
            conf = self.channel_configs[after.channel.id]
            if conf["type"] == "public" or conf["type"] == "private":
                await self.handle_channel(member, after, conf, public=conf["type"] == "public")

        if before.channel:
            await self.cleanup_channel(before.channel.id)

    async def handle_channel(self, member, after, conf, public=True):
        guild = after.channel.guild
        temp_channel_name = f"{conf['name_prefix']}-{member.display_name}"
        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=public),
            member: discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True, speak=True,
                                                move_members=True)
        }

        # Get all categories with the same name as the current one
        categories = [category for category in guild.categories if category.name == after.channel.category.name]

        # Sort the categories by position
        categories.sort(key=lambda category: category.position)

        for category in categories:
            try:
                temp_channel = await guild.create_voice_channel(name=temp_channel_name, category=category,
                                                                overwrites=overwrites)
                break  # If the channel creation is successful, break the loop
            except discord.errors.HTTPException as e:
                if e.code == 50035:  # Maximum number of channels in category reached
                    continue  # If the category is full, continue to the next one
                else:
                    raise e  # If it's another error, raise it
        else:  # If all categories are full
            # Before creating a new category, increment the position of all categories with a position
            # greater than or equal to the new category's position
            new_category_position = categories[-1].position
            # print(f"Creating new category at position {new_category_position}")

            new_category = await guild.create_category(name=after.channel.category.name,
                                                       position=new_category_position)
            temp_channel = await guild.create_voice_channel(name=temp_channel_name, category=new_category,
                                                            overwrites=overwrites)

        # Move the member and handle exceptions if the member is no longer connected
        try:
            if member.voice:
                await member.move_to(temp_channel)
            else:
                raise RuntimeError("Member not connected to voice")
        except (discord.HTTPException, discord.NotFound, RuntimeError) as e:
            # Handle exceptions by cleaning up the newly created channel if the move fails
            if isinstance(e, RuntimeError) or "Target user is not connected to voice" in str(e):
                await temp_channel.delete(reason="Cleanup unused channel due to user disconnect")
                if not temp_channel.category.channels:
                    await temp_channel.category.delete(reason="Cleanup unused category")
                # return

        # Record the temporary channel in the database
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('INSERT INTO temp_channels (channel_id, creator_id) VALUES (?, ?)',
                             (temp_channel.id, member.id))
            await db.commit()

    async def cleanup_channel(self, channel_id):
        channel = self.bot.get_channel(channel_id)
        if channel and not channel.members:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('SELECT channel_id FROM temp_channels WHERE channel_id = ?', (channel_id,))
                result = await cursor.fetchone()
                if result:
                    # await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (channel_id,))
                    # await db.commit()
                    await channel.delete(reason="Temporary channel cleanup")
                    await sleep(0.5)  # Sleep for a short time to let the channel delete
                    if not channel.category.channels:  # If the category is empty, delete it
                        await channel.category.delete(reason="Temporary category cleanup")

    @tasks.loop(hours=1)
    async def cleanup_task(self):
        logging.info("Running cleanup task")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT channel_id FROM temp_channels')
            channels = await cursor.fetchall()
            for (channel_id,) in channels:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    # The channel no longer exists, so clean up the database entry
                    await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (channel_id,))
                    await db.commit()

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="check_temp_channel_records",
        description="Check the records of temporary channels"
    )
    async def check_temp_channel_records(self, interaction: discord.Interaction):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        # Fetch the records from the database
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM temp_channels ORDER BY created_at DESC')
            records = await cursor.fetchall()

        if not records:
            await interaction.edit_original_response(content="No records found.")
            return

        view = CheckTempChannelView(self.bot, interaction.user.id, records)
        embed = await view.format_page()
        message = await interaction.edit_original_response(embeds=[embed], view=view)
        view.message = message

    @app_commands.command(
        name="set_soundboard",
        description="Toggle the soundboard functionality for the creator's voice channel"
    )
    async def set_soundboard(self, interaction: discord.Interaction):
        member = interaction.user
        voice_state = member.voice

        if not voice_state or not voice_state.channel:
            await interaction.response.send_message(self.soundboard_not_in_vc_message, ephemeral=True)
            return

        channel = voice_state.channel

        # Check if the user is the creator of the channel
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT creator_id FROM temp_channels WHERE channel_id = ?', (channel.id,))
            record = await cursor.fetchone()

        if not record or record[0] != member.id:
            await interaction.response.send_message(self.soundboard_no_permission_message, ephemeral=True)
            return

        # Toggle soundboard functionality
        current_overwrites = channel.overwrites_for(channel.guild.default_role)
        if current_overwrites.use_soundboard is None or current_overwrites.use_soundboard:
            current_overwrites.update(use_soundboard=False)
            await channel.set_permissions(channel.guild.default_role, overwrite=current_overwrites)
            await interaction.response.send_message(self.soundboard_disabled_message,
                                                    ephemeral=True)
        else:
            current_overwrites.update(use_soundboard=True)
            await channel.set_permissions(channel.guild.default_role, overwrite=current_overwrites)
            await interaction.response.send_message(self.soundboard_enabled_message,
                                                    ephemeral=True)

    @app_commands.command(
        name="vc_add",
        description="Add a new voice channel for room creation"
    )
    async def add_voice_channel(self, interaction: discord.Interaction):
        """Add a new voice channel configuration for room creation."""
        if not await check_channel_validity(interaction):
            return

        # Show the modal
        await interaction.response.send_modal(AddChannelForm(self))

    @app_commands.command(
        name="vc_remove",
        description="Remove a voice channel from room creation"
    )
    @app_commands.describe(channel_id="The ID of the voice channel to remove")
    async def remove_voice_channel(self, interaction: discord.Interaction, channel_id: str):
        """Remove a voice channel configuration."""
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            channel_id = int(channel_id)
        except ValueError:
            await interaction.followup.send("Invalid channel ID format.", ephemeral=True)
            return

        # Check if channel exists and has configuration
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.followup.send("Channel not found.", ephemeral=True)
            return

        if channel_id not in self.channel_configs:  # Check for integer ID
            await interaction.followup.send("No configuration found for this channel.", ephemeral=True)
            return

        # Create confirmation embed
        embed = discord.Embed(
            title="Confirm Channel Removal",
            description=f"Are you sure you want to remove the configuration for <#{channel_id}>?",
            color=discord.Color.yellow()
        )
        embed.add_field(
            name="Current Configuration",
            value=f"Name Prefix: {self.channel_configs[channel_id]['name_prefix']}\n"
                  f"Type: {self.channel_configs[channel_id]['type'].capitalize()}",
            inline=False
        )

        # Show confirmation view
        view = DeleteChannelConfirmView(self, channel_id)
        await interaction.followup.send(embed=embed, view=view)

    async def save_channel_configs(self):
        """Save the channel configurations to the JSON file."""
        config_path = Path('./bot/config/config_voicechannel.json')

        async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            config_data = json.loads(content)

        # Update the channel_configs in the config data
        # Convert all keys to strings for JSON serialization
        config_data['channel_configs'] = {
            str(channel_id): config
            for channel_id, config in self.channel_configs.items()
        }

        async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(config_data, indent=2, ensure_ascii=False))

    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure the table exists
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS temp_channels (
                    channel_id INTEGER PRIMARY KEY,
                    creator_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            await db.commit()

            # Check for empty channels on startup
            cursor = await db.execute('SELECT channel_id FROM temp_channels')
            channels = await cursor.fetchall()
            for (channel_id,) in channels:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    # The channel no longer exists, so clean up the database entry
                    await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (channel_id,))
                    await db.commit()
                elif not channel.members:
                    # If the channel exists and is empty, delete it
                    await self.cleanup_channel(channel_id)

            # Check for empty categories on startup
            for guild in self.bot.guilds:
                # Get the category names from CHANNEL_CONFIGS
                category_names = [self.bot.get_channel(channel_id).category.name
                                  for channel_id in self.channel_configs.keys()
                                  if self.bot.get_channel(channel_id) is not None]
                for category in guild.categories:
                    if not category.channels and category.name in category_names:
                        await category.delete(reason="Temporary category cleanup")
