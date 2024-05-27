import discord
from discord.ext import commands
from collections import defaultdict

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
        self.temp_channels = defaultdict(dict)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if after.channel and after.channel.id in CHANNEL_CONFIGS:
            config = CHANNEL_CONFIGS[after.channel.id]
            if config["type"] == "public":
                await self.handle_channel(member, after, config, public=True)
            elif config["type"] == "private":
                await self.handle_channel(member, after, config, public=False)

        if before.channel and before.channel.id in self.temp_channels:
            if len(before.channel.members) == 0:
                await before.channel.delete()
                del self.temp_channels[before.channel.id]

    async def handle_channel(self, member, after, config, public=True):
        category = after.channel.category
        temp_channel_name = f"{config['name_prefix']}-{member.display_name}"

        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=public),
            member: discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True, speak=True,
                                                mute_members=True, move_members=True)
        }

        temp_channel = await after.channel.guild.create_voice_channel(
            name=temp_channel_name, category=category, overwrites=overwrites)
        self.temp_channels[temp_channel.id] = member.id
        await member.move_to(temp_channel)
