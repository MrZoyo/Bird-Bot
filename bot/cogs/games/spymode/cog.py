import random

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from bot.utils.i18n import t

from .views import SpyModeView


class SpyModeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="spymode",
        description=locale_str(
            "Initiate a spy mode game",
            key="spymode.spymode.description",
        ),
    )
    @app_commands.describe(
        team_size=locale_str(
            "Number of players per side",
            key="spymode.spymode.params.team_size",
        ),
        spy=locale_str(
            "Number of spies per side",
            key="spymode.spymode.params.spy",
        ),
    )
    async def spymode(self, interaction: discord.Interaction, team_size: int = 5, spy: int = 1):
        """Initiate a spy mode game."""
        await interaction.response.defer()

        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.followup.send(t('spymode.spymode_not_in_channel_message'), ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel

        if team_size < 3:
            await interaction.followup.send(t('spymode.spymode_wrong_team_size_message'), ephemeral=True)
            return

        if spy >= team_size or spy < 1:
            await interaction.followup.send(t('spymode.spymode_wrong_spy_size_message'), ephemeral=True)
            return

        game_id = random.randint(10000, 99999)
        view = SpyModeView(self.bot, team_size, spy, interaction.user, voice_channel, game_id)

        embed = discord.Embed(
            title=t('spymode.spymode_embed_title', game_id=game_id),
            color=discord.Color.blue(),
        )
        game_info = t(
            'spymode.spymode_gameinfo',
            name=interaction.user.mention,
            team_size=team_size,
            spy=spy,
        )
        embed.add_field(name="", value=game_info, inline=False)
        embed.add_field(
            name=t('spymode.blue_team_name', team_size=team_size),
            value="\n",
            inline=True,
        )
        embed.add_field(
            name=t('spymode.red_team_name', team_size=team_size),
            value="\n",
            inline=True,
        )
        embed.set_footer(text=t('spymode.spymode_embed_footer'))

        await interaction.followup.send(embed=embed, view=view)
