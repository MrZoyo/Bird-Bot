import discord

from bot.utils.i18n import t


class MemberPositionView(discord.ui.View):
    def __init__(self, bot, url):
        super().__init__()
        self.bot = bot
        self.add_item(
            discord.ui.Button(
                label=t('checkstatus.where_is_join_button_label'),
                url=url,
            )
        )
