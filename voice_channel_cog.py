import aiosqlite
import discord
from discord.ext import commands

# Use a dictionary to manage all configurations. The channel ID corresponds to the channel type name and type
CHANNEL_CONFIGS = {
    11451419198101: {"name_prefix": "GameRoom", "type": "public"},
    11451419198102: {"name_prefix": "RelaxRoom", "type": "public"},
    81019191145141: {"name_prefix": "PrivateRoom", "type": "private"},
    81019191145142: {"name_prefix": "PVP Room", "type": "public"}
}


class VoiceStateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'bot.db'  # Path to SQLite database

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if after.channel and after.channel.id in CHANNEL_CONFIGS:
            config = CHANNEL_CONFIGS[after.channel.id]
            if config["type"] == "public" or config["type"] == "private":
                await self.handle_channel(member, after, config, public=config["type"] == "public")

        if before.channel:
            await self.cleanup_channel(before.channel.id)

    async def handle_channel(self, member, after, config, public=True):
        category = after.channel.category
        temp_channel_name = f"{config['name_prefix']}-{member.display_name}"
        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=public),
            member: discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True, speak=True,
                                                mute_members=True, move_members=True)
        }
        temp_channel = await after.channel.guild.create_voice_channel(name=temp_channel_name, category=category,
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
