# Author: MrZoyo
# Version: 0.6.8
# Date: 2024-06-17
# ========================================

import aiosqlite
import asyncio
import logging
import discord
from discord.ui import Button, View
from discord.ext import commands, tasks
from discord import app_commands

from illegal_team_act_cog import IllegalTeamActCog


class CheckTempChannelView(discord.ui.View):
    def __init__(self, bot, user_id, records, page=1):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user_id = user_id
        self.records = records
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
        self.illegal_act_cog = IllegalTeamActCog(bot)

        config = self.bot.get_cog('ConfigCog').config
        self.channel_configs = {int(channel_id): config for channel_id, config in config['channel_configs'].items()}
        self.db_path = config['db_path']

        # Start the cleanup task
        self.cleanup_task.start()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if after.channel and after.channel.id in self.channel_configs:
            config = self.channel_configs[after.channel.id]
            if config["type"] == "public" or config["type"] == "private":
                await self.handle_channel(member, after, config, public=config["type"] == "public")

        if before.channel:
            await self.cleanup_channel(before.channel.id)

    async def handle_channel(self, member, after, config, public=True):
        guild = after.channel.guild
        temp_channel_name = f"{config['name_prefix']}-{member.display_name}"
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
        if not await self.illegal_act_cog.check_channel_validity(interaction):
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
