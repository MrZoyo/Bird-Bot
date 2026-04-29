import discord

from bot.utils.i18n import t


class WelcomeDMView(discord.ui.View):
    def __init__(self, member_count):
        super().__init__(timeout=None)  # No timeout for this button

        button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            label=t('welcome.dm.member_count_button', member_count=member_count),
            disabled=True,  # Make it non-clickable
        )
        self.add_item(button)
