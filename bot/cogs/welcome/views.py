import discord

from bot.utils import config


class WelcomeDMView(discord.ui.View):
    def __init__(self, member_count):
        super().__init__(timeout=None)  # No timeout for this button

        self.conf = config.get_config('welcome')

        # The button template lives under welcome.yaml `dm:` subtree
        # (same subtree as the rest of the DM copy). Reading from the
        # top level silently fell back to the hardcoded "アルタ"
        # placeholder on every real deploy — fixed in 2026-04-23.
        dm_conf = self.conf.get('dm', {}) if isinstance(self.conf, dict) else {}
        template = dm_conf.get('member_count_button') or \
            "你是本服务器的第 {member_count} 名成员"

        button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            label=template.format(member_count=member_count),
            disabled=True,  # Make it non-clickable
        )
        self.add_item(button)
