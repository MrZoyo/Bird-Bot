import random

import discord

from bot.utils.i18n import t


class JoinBlueTeamButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(
            label=t('spymode.blue_team_button_label'),
            style=discord.ButtonStyle.primary,
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        await self.view_ref.join_blue_team(interaction, self)


class JoinRedTeamButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(
            label=t('spymode.red_team_button_label'),
            style=discord.ButtonStyle.danger,
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        await self.view_ref.join_red_team(interaction, self)


class RandomSpyButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(
            label=t('spymode.random_button_label'),
            style=discord.ButtonStyle.secondary,
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        await self.view_ref.random_spy(interaction, self)


class SpyModeView(discord.ui.View):
    def __init__(self, bot, team_size: int, spy: int, command_user: discord.Member,
                 voice_channel: discord.VoiceChannel, game_id: int):
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

        self.add_item(JoinBlueTeamButton(self))
        self.add_item(JoinRedTeamButton(self))
        self.add_item(RandomSpyButton(self))

    async def join_blue_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        if interaction.user.voice is None or interaction.user.voice.channel != self.voice_channel:
            await interaction.followup.send(t('spymode.spymode_wrong_channel_message'), ephemeral=True)
            return

        if len(self.blue_team) > self.team_size:
            await interaction.followup.send(t('spymode.full_team_message'), ephemeral=True)
            return

        if interaction.user in self.blue_team:
            self.blue_team.remove(interaction.user)
            await self.update_embed(interaction)
            return

        if interaction.user not in self.blue_team:
            if interaction.user in self.red_team:
                self.red_team.remove(interaction.user)
            self.blue_team.append(interaction.user)
            await self.update_embed(interaction)

    async def join_red_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        if interaction.user.voice is None or interaction.user.voice.channel != self.voice_channel:
            await interaction.followup.send(t('spymode.spymode_wrong_channel_message'), ephemeral=True)
            return

        if len(self.red_team) > self.team_size:
            await interaction.followup.send(t('spymode.full_team_message'), ephemeral=True)
            return

        if interaction.user in self.red_team:
            self.red_team.remove(interaction.user)
            await self.update_embed(interaction)
            return

        if interaction.user not in self.red_team:
            if interaction.user in self.blue_team:
                self.blue_team.remove(interaction.user)
            self.red_team.append(interaction.user)
            await self.update_embed(interaction)

    async def random_spy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.interaction_count == 0:
            if interaction.user != self.command_user:
                await interaction.followup.send(t('spymode.spymode_wrong_user_message'), ephemeral=True)
                return

            if (len(self.blue_team) != self.team_size) or (len(self.red_team) != self.team_size):
                await interaction.followup.send(t('spymode.spymode_wrong_start_message'), ephemeral=True)
                return

            self.interaction_count += 1
            button.label = t('spymode.result_button_label')
            for child in self.children:
                if child != button:
                    child.disabled = True

            await self.randomize_spies()

            embed = discord.Embed(
                title=t('spymode.spymode_embed_start_title', game_id=self.game_id),
                color=discord.Color.orange(),
            )
            game_info = t(
                'spymode.spymode_gameinfo',
                name=self.command_user.mention,
                team_size=self.team_size,
                spy=self.spy,
            )
            embed.add_field(name="", value=game_info, inline=False)
            embed.add_field(
                name=t('spymode.blue_team_name', team_size=self.team_size),
                value="\n".join([u.display_name for u in self.blue_team]),
                inline=True,
            )
            embed.add_field(
                name=t('spymode.red_team_name', team_size=self.team_size),
                value="\n".join([u.display_name for u in self.red_team]),
                inline=True,
            )
            embed.set_footer(text=t('spymode.spymode_embed_footer'))
            await interaction.message.edit(embed=embed, view=self)

        elif self.interaction_count == 1:
            if interaction.user != self.command_user:
                await interaction.followup.send(t('spymode.spymode_wrong_user_message'), ephemeral=True)
                return

            button.disabled = True

            embed = discord.Embed(
                title=t('spymode.spymode_embed_end_title', game_id=self.game_id),
                color=discord.Color.red(),
            )
            game_info = t(
                'spymode.spymode_gameinfo',
                name=self.command_user.mention,
                team_size=self.team_size,
                spy=self.spy,
            )
            embed.add_field(name="", value=game_info, inline=False)
            embed.add_field(
                name=t('spymode.blue_team_name', team_size=self.team_size),
                value="\n".join([u.display_name for u in self.blue_team]),
                inline=True,
            )
            embed.add_field(
                name=t('spymode.red_team_name', team_size=self.team_size),
                value="\n".join([u.display_name for u in self.red_team]),
                inline=True,
            )
            embed.add_field(name="", value="​", inline=False)
            embed.add_field(
                name=t('spymode.blue_team_result'),
                value="\n".join([u.display_name for u in self.blue_team if u in self.spies]),
                inline=True,
            )
            embed.add_field(
                name=t('spymode.red_team_result'),
                value="\n".join([u.display_name for u in self.red_team if u in self.spies]),
                inline=True,
            )
            embed.set_footer(text=t('spymode.spymode_embed_footer'))
            await interaction.message.edit(embed=embed, view=self)

    async def update_embed(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=t('spymode.spymode_embed_title', game_id=self.game_id),
            color=discord.Color.blue(),
        )
        game_info = t(
            'spymode.spymode_gameinfo',
            name=self.command_user.mention,
            team_size=self.team_size,
            spy=self.spy,
        )
        embed.add_field(name="", value=game_info, inline=False)
        embed.add_field(
            name=t('spymode.blue_team_name', team_size=self.team_size),
            value="\n".join([u.display_name for u in self.blue_team]),
            inline=True,
        )
        embed.add_field(
            name=t('spymode.red_team_name', team_size=self.team_size),
            value="\n".join([u.display_name for u in self.red_team]),
            inline=True,
        )
        embed.set_footer(text=t('spymode.spymode_embed_footer'))
        await interaction.message.edit(embed=embed, view=self)

    async def randomize_spies(self):
        spies_blue = random.sample(self.blue_team, min(len(self.blue_team), self.spy))
        spies_red = random.sample(self.red_team, min(len(self.red_team), self.spy))

        self.spies = spies_blue + spies_red

        embed = discord.Embed(
            title=t('spymode.spymode_embed_saved_title', game_id=self.game_id),
            color=discord.Color.green(),
        )
        game_info = t(
            'spymode.spymode_gameinfo',
            name=self.command_user.display_name,
            team_size=self.team_size,
            spy=self.spy,
        )
        embed.add_field(name="", value=game_info, inline=False)
        embed.add_field(
            name=t('spymode.blue_team_name', team_size=self.team_size),
            value="\n".join([u.display_name for u in self.blue_team]),
            inline=True,
        )
        embed.add_field(
            name=t('spymode.red_team_name', team_size=self.team_size),
            value="\n".join([u.display_name for u in self.red_team]),
            inline=True,
        )

        spy_msg = t('spymode.you_are_spy')
        not_spy_msg = t('spymode.you_are_not_spy')
        for user in self.blue_team + self.red_team:
            if user in spies_blue or user in spies_red:
                await user.send(spy_msg, embed=embed)
            else:
                await user.send(not_spy_msg, embed=embed)
