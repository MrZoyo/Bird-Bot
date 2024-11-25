# bot/cogs/game_spymode_cog.py
from ..utils import config
import discord
from discord.ext import commands
from discord import app_commands
import random
from discord.ui import View, Button


class JoinBlueTeamButton(discord.ui.Button):
    view = None

    def __init__(self, view):
        self.conf = config.get_config('spymode')
        super().__init__(label=self.conf['blue_team_button_label'], style=discord.ButtonStyle.primary)
        self.view = view

    async def callback(self, interaction: discord.Interaction):
        await self.view.join_blue_team(interaction, self)


class JoinRedTeamButton(discord.ui.Button):
    view = None

    def __init__(self, view):
        self.conf = config.get_config('spymode')
        super().__init__(label=self.conf['red_team_button_label'], style=discord.ButtonStyle.danger)
        self.view = view

    async def callback(self, interaction: discord.Interaction):
        await self.view.join_red_team(interaction, self)


class RandomSpyButton(discord.ui.Button):
    view = None

    def __init__(self, view):
        self.conf = config.get_config('spymode')
        super().__init__(label=self.conf['random_button_label'], style=discord.ButtonStyle.secondary)
        self.view = view

    async def callback(self, interaction: discord.Interaction):
        await self.view.random_spy(interaction, self)


class SpyModeView(discord.ui.View):
    def __init__(self, bot, team_size: int, spy: int, command_user: discord.Member, voice_channel: discord.VoiceChannel,
                 game_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.blue_team = []
        self.red_team = []
        self.team_size = team_size
        self.spy = spy
        self.spies = []
        self.command_user = command_user
        self.voice_channel = voice_channel
        self.game_id = game_id
        self.interaction_count = 0

        self.conf = config.get_config('spymode')
        self.blue_team_button_label = self.conf['blue_team_button_label']
        self.red_team_button_label = self.conf['red_team_button_label']
        self.random_button_label = self.conf['random_button_label']
        self.result_button_label = self.conf['result_button_label']
        self.spymode_embed_title = self.conf['spymode_embed_title']
        self.spymode_embed_start_title = self.conf['spymode_embed_start_title']
        self.spymode_embed_saved_title = self.conf['spymode_embed_saved_title']
        self.spymode_embed_end_title = self.conf['spymode_embed_end_title']
        self.spymode_gameinfo = self.conf['spymode_gameinfo']
        self.blue_team_name = self.conf['blue_team_name']
        self.red_team_name = self.conf['red_team_name']
        self.blue_team_result = self.conf['blue_team_result']
        self.red_team_result = self.conf['red_team_result']
        self.you_are_spy = self.conf['you_are_spy']
        self.you_are_not_spy = self.conf['you_are_not_spy']
        self.full_team_message = self.conf['full_team_message']
        self.spymode_wrong_channel_message = self.conf['spymode_wrong_channel_message']
        self.spymode_wrong_user_message = self.conf['spymode_wrong_user_message']
        self.spymode_wrong_start_message = self.conf['spymode_wrong_start_message']
        self.spymode_embed_footer = self.conf['spymode_embed_footer']

        # Initialize buttons with proper labels from the configuration.
        self.add_item(JoinBlueTeamButton(self))
        self.add_item(JoinRedTeamButton(self))
        self.add_item(RandomSpyButton(self))

    async def join_blue_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        # Ensure user is in the same voice channel as the game creator
        if interaction.user.voice is None or interaction.user.voice.channel != self.voice_channel:
            await interaction.followup.send(self.spymode_wrong_channel_message, ephemeral=True)
            return

        if len(self.blue_team) > self.team_size:
            await interaction.followup.send(self.full_team_message, ephemeral=True)
            return

        # If the user is already in the queue, they can exit the queue.
        if interaction.user in self.blue_team:
            self.blue_team.remove(interaction.user)
            await self.update_embed(interaction)
            return

        # Ensure user is not already in the team and team has space
        if interaction.user not in self.blue_team:
            if interaction.user in self.red_team:
                self.red_team.remove(interaction.user)
            self.blue_team.append(interaction.user)
            await self.update_embed(interaction)

    async def join_red_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        # Ensure user is in the same voice channel as the game creator
        if interaction.user.voice is None or interaction.user.voice.channel != self.voice_channel:
            await interaction.followup.send(self.spymode_wrong_channel_message, ephemeral=True)
            return

        if len(self.red_team) > self.team_size:
            await interaction.followup.send(self.full_team_message, ephemeral=True)
            return

        # If the user is already in the queue, they can exit the queue.
        if interaction.user in self.red_team:
            self.red_team.remove(interaction.user)
            await self.update_embed(interaction)
            return

        # Ensure user is not already in the team and team has space
        if interaction.user not in self.red_team:
            if interaction.user in self.blue_team:
                self.blue_team.remove(interaction.user)
            self.red_team.append(interaction.user)
            await self.update_embed(interaction)

    async def random_spy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.interaction_count == 0:
            # Ensure command user is initiating the spy randomization
            if interaction.user != self.command_user:
                await interaction.followup.send(self.spymode_wrong_user_message, ephemeral=True)
                return

            # Check if both teams are full
            if (len(self.blue_team) != self.team_size) or (len(self.red_team) != self.team_size):
                await interaction.followup.send(self.spymode_wrong_start_message, ephemeral=True)
                return

            # Update the interaction count to 1 and update the button label
            self.interaction_count += 1
            button.label = self.result_button_label
            for child in self.children:
                if child != button:
                    child.disabled = True

            await self.randomize_spies()

            # Update the embed interface
            embed = discord.Embed(title=self.spymode_embed_start_title.format(game_id=self.game_id),
                                  color=discord.Color.orange())

            game_info = self.spymode_gameinfo.format(name=self.command_user.mention, team_size=self.team_size,
                                                     spy=self.spy)
            embed.add_field(name="", value=game_info, inline=False)

            embed.add_field(name=self.blue_team_name.format(team_size=self.team_size),
                            value="\n".join([user.display_name for user in self.blue_team]), inline=True)
            embed.add_field(name=self.red_team_name.format(team_size=self.team_size),
                            value="\n".join([user.display_name for user in self.red_team]), inline=True)
            embed.set_footer(text=self.spymode_embed_footer)
            await interaction.message.edit(embed=embed, view=self)

        elif self.interaction_count == 1:
            if interaction.user != self.command_user:
                await interaction.followup.send(self.spymode_wrong_user_message, ephemeral=True)
                return

            # Reveal the spies and disable the random_spy button
            button.disabled = True

            # Update the embed interface
            embed = discord.Embed(title=self.spymode_embed_end_title.format(game_id=self.game_id),
                                  color=discord.Color.red())

            game_info = self.spymode_gameinfo.format(name=self.command_user.mention, team_size=self.team_size,
                                                     spy=self.spy)
            embed.add_field(name="", value=game_info, inline=False)

            embed.add_field(name=self.blue_team_name.format(team_size=self.team_size),
                            value="\n".join([user.display_name for user in self.blue_team]), inline=True)
            embed.add_field(name=self.red_team_name.format(team_size=self.team_size),
                            value="\n".join([user.display_name for user in self.red_team]), inline=True)

            embed.add_field(name="", value="\u200b", inline=False)

            embed.add_field(name=self.blue_team_result,
                            value="\n".join([user.display_name for user in self.blue_team if user in self.spies]),
                            inline=True)
            embed.add_field(name=self.red_team_result,
                            value="\n".join([user.display_name for user in self.red_team if user in self.spies]),
                            inline=True)
            embed.set_footer(text=self.spymode_embed_footer)

            await interaction.message.edit(embed=embed, view=self)

    async def update_embed(self, interaction: discord.Interaction):
        embed = discord.Embed(title=self.spymode_embed_title.format(game_id=self.game_id),
                              color=discord.Color.blue())

        game_info = self.spymode_gameinfo.format(name=self.command_user.mention, team_size=self.team_size, spy=self.spy)
        embed.add_field(name="", value=game_info, inline=False)

        embed.add_field(name=self.blue_team_name.format(team_size=self.team_size),
                        value="\n".join([user.display_name for user in self.blue_team]), inline=True)
        embed.add_field(name=self.red_team_name.format(team_size=self.team_size),
                        value="\n".join([user.display_name for user in self.red_team]), inline=True)
        embed.set_footer(text=self.spymode_embed_footer)
        await interaction.message.edit(embed=embed, view=self)

    async def randomize_spies(self):
        spies_blue = random.sample(self.blue_team, min(len(self.blue_team), self.spy))
        spies_red = random.sample(self.red_team, min(len(self.red_team), self.spy))

        self.spies = spies_blue + spies_red

        # Create a new embed without the buttons
        embed = discord.Embed(title=self.spymode_embed_saved_title.format(game_id=self.game_id),
                              color=discord.Color.green())

        game_info = self.spymode_gameinfo.format(name=self.command_user.display_name, team_size=self.team_size,
                                                 spy=self.spy)
        embed.add_field(name="", value=game_info, inline=False)

        embed.add_field(name=self.blue_team_name.format(team_size=self.team_size),
                        value="\n".join([user.display_name for user in self.blue_team]), inline=True)
        embed.add_field(name=self.red_team_name.format(team_size=self.team_size),
                        value="\n".join([user.display_name for user in self.red_team]), inline=True)

        # Send the embed and a message to all players
        for user in self.blue_team + self.red_team:
            if user in spies_blue or user in spies_red:
                await user.send(self.you_are_spy, embed=embed)
            else:
                await user.send(self.you_are_not_spy, embed=embed)


class SpyModeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conf = config.get_config('spymode')
        self.spymode_gameinfo = self.conf['spymode_gameinfo']
        self.blue_team_name = self.conf['blue_team_name']
        self.red_team_name = self.conf['red_team_name']
        self.spymode_embed_title = self.conf['spymode_embed_title']
        self.spymode_not_in_channel_message = self.conf['spymode_not_in_channel_message']
        self.spymode_wrong_team_size_message = self.conf['spymode_wrong_team_size_message']
        self.spymode_wrong_spy_size_message = self.conf['spymode_wrong_spy_size_message']
        self.spymode_embed_footer = self.conf['spymode_embed_footer']

    @app_commands.command(name="spymode")
    @app_commands.describe(team_size="Number of players per side",
                           spy="Number of spies per side"
                           )
    async def spymode(self, interaction: discord.Interaction, team_size: int = 5, spy: int = 1):
        """
        Initiate a spy mode game.
        """
        await interaction.response.defer()

        # Ensure the command user is in a voice channel
        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.followup.send(self.spymode_not_in_channel_message, ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel

        if team_size < 3:
            await interaction.followup.send(self.spymode_wrong_team_size_message, ephemeral=True)
            return

        if spy >= team_size or spy < 1:
            await interaction.followup.send(self.spymode_wrong_spy_size_message, ephemeral=True)
            return

        game_id = random.randint(10000, 99999)
        view = SpyModeView(self.bot, team_size, spy, interaction.user, voice_channel, game_id)

        embed = discord.Embed(title=self.spymode_embed_title.format(game_id=game_id), color=discord.Color.blue())

        game_info = self.spymode_gameinfo.format(name=interaction.user.mention, team_size=team_size, spy=spy)
        embed.add_field(name="", value=game_info, inline=False)

        embed.add_field(name=self.blue_team_name.format(team_size=team_size), value="\n", inline=True)
        embed.add_field(name=self.red_team_name.format(team_size=team_size), value="\n", inline=True)

        embed.set_footer(text=self.spymode_embed_footer)

        await interaction.followup.send(embed=embed, view=view)
