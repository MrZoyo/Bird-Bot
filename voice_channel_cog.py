# Author: MrZoyo
# Version: 0.6.0
# Date: 2024-06-10
# ========================================
import discord
from discord.ext import commands
import aiosqlite


class VoiceStateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        config = self.bot.get_cog('ConfigCog').config
        self.channel_configs = {int(channel_id): config for channel_id, config in config['channel_configs'].items()}
        self.db_path = config['db_path']

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
                raise discord.errors.HTTPException("Member not connected to voice")
        except (discord.HTTPException, discord.NotFound):
            # Handle exceptions by cleaning up the newly created channel if the move fails
            await temp_channel.delete(reason="Cleanup unused channel due to user disconnect")
            return  # Exit function to avoid further operations

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
                    await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (channel_id,))
                    await db.commit()
                    await channel.delete(reason="Temporary channel cleanup")
                    if not channel.category.channels:  # If the category is empty, delete it
                        await channel.category.delete(reason="Temporary category cleanup")

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

