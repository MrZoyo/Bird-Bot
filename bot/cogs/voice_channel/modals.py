import discord
from discord import ui


class AddChannelForm(ui.Modal):
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

    def __init__(self, cog, channel):
        super().__init__(title=f'Configure Voice Channel: {channel.name}')
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Validate channel type
        if self.channel_type.value.lower() not in ['public', 'private']:
            await interaction.followup.send("Channel type must be either 'public' or 'private'.", ephemeral=True)
            return

        # Add the new channel configuration
        config_data = {
            "name_prefix": self.name_prefix.value,
            "type": self.channel_type.value.lower()
        }

        # Persist via the channel_configs DB table (P2-5: migrated from
        # config_voicechannel.json). The in-memory dict mirrors the DB so
        # on_voice_state_update can still do its hot-path lookup without
        # a SELECT on every voice transition.
        await self.cog.db.upsert_channel_config(
            self.channel.id,
            config_data['name_prefix'],
            config_data['type'],
        )
        self.cog.channel_configs[self.channel.id] = config_data

        # Create and send embed with all configurations
        embed = await self.cog.format_channel_configs_embed(
            title="Voice Channel Configuration Added",
            description=f"Successfully added configuration for {self.channel.mention}",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)
