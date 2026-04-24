import discord


class RejoinServerView(discord.ui.View):
    def __init__(self, invite_link: str, button_label: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label=button_label,
            url=invite_link,
            style=discord.ButtonStyle.link
        ))
