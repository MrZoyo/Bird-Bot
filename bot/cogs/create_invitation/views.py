import re

import discord
from discord.utils import format_dt

from bot.utils import config
from bot.utils.components_v2 import build_panel_container
from bot.utils.i18n import t
from .interactions import acknowledge


def invitation_custom_id(invitation_id):
    return f'teamup:full:v1:{invitation_id}'


class InvitationFullButton(discord.ui.DynamicItem[discord.ui.Button],
                           template=r'teamup:full:v1:(?P<invitation_id>[0-9]+)'):
    def __init__(self, invitation_id):
        self.invitation_id = invitation_id
        super().__init__(discord.ui.Button(
            style=discord.ButtonStyle.danger, label=t('invitation.roomfull_button_label'),
            custom_id=invitation_custom_id(invitation_id),
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match['invitation_id']))

    async def callback(self, interaction):
        await dispatch_full(interaction, invitation_id=self.invitation_id)


class LegacyInvitationFullButton(discord.ui.DynamicItem[discord.ui.Button], template=r'room_full_button'):
    def __init__(self):
        super().__init__(discord.ui.Button(
            style=discord.ButtonStyle.danger, label=t('invitation.roomfull_button_label'),
            custom_id='room_full_button',
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls()

    async def callback(self, interaction):
        await dispatch_full(interaction)


async def dispatch_full(interaction, *, invitation_id=None):
    cog = interaction.client.get_cog('CreateInvitationCog')
    if cog:
        await cog.lifecycle.finish(interaction, invitation_id=invitation_id)
    elif await acknowledge(interaction):
        await interaction.followup.send(t('invitation.finish_failed'), ephemeral=True)


class TeamInvitationView(discord.ui.LayoutView):
    def __init__(self, bot, channel, user, role_db, *, invitation_id=None):
        super().__init__(timeout=None)
        self.invitation_id = invitation_id
        self.bot = bot
        self.user = user
        self.channel = channel
        self.role_db = role_db
        self.url = f"https://discord.com/channels/{channel.guild.id}/{channel.id}"

        self.conf = config.get_config('invitation')
        self.roomfull_button_label = t('invitation.roomfull_button_label')
        self.invite_button_label = t('invitation.invite_button_label')
        self.invite_embed_content = t('invitation.invite_embed_content')
        self.interaction_target_error_message = t('invitation.interaction_target_error_message')
        self.roomfull_set_message = t('invitation.roomfull_set_message')
        self.not_in_vc_message = t('invitation.not_in_vc_message')
        self.extract_channel_id_error = t('invitation.extract_channel_id_error')

        self.invite_button = discord.ui.Button(
            style=discord.ButtonStyle.link,
            label=self.invite_button_label,
            url=self.url,
        )
        self.room_full_button = (InvitationFullButton(invitation_id)
                                 if invitation_id is not None else LegacyInvitationFullButton())

    async def populate_panel(self, obj, *, title: str | None = None) -> None:
        # Get the current time
        current_time = discord.utils.utcnow()
        # Format the timestamp for the embed
        elapsed_time = format_dt(current_time, style='R')

        # Check if the passed object is a message or an interaction
        if isinstance(obj, discord.Message) or hasattr(obj, "author"):
            author = obj.author
            content = obj.content
        elif isinstance(obj, discord.Interaction) or hasattr(obj, "user"):
            author = obj.user
            content = getattr(obj, "data", {}).get('name')  # Get the name of the slash command
        else:
            raise ValueError("The passed object must be a discord.Message or a discord.Interaction.")

        # Get user's signature if exists (owned by role_db)
        sig = await self.role_db.get_user_signature(author.id)
        signature = sig['signature'] if sig and not sig['is_disabled'] else None

        channel_name = re.sub(r'([\\`*_~|\[\]()])', r'\\\1', self.channel.name)
        channel_name = discord.utils.escape_mentions(channel_name)
        vc_link = f"[{channel_name}]({self.url})"

        panel_title = title or content
        # Remove mentions from content
        panel_title = re.sub(r'<@\d+>', '', panel_title)
        panel_title = re.sub(r'<@&\d+>', '', panel_title)

        # Truncate the content
        if len(panel_title) > 256:
            panel_title = panel_title[:253] + "..."

        description_parts = [
            self.invite_embed_content.format(
                vc_url=vc_link,
                mention=author.mention,
                time=elapsed_time,
            ),
        ]

        if signature:
            description_parts.append(signature)

        thumbnail_url = None
        if author.avatar:
            thumbnail_url = author.avatar.url
        elif self.bot.user.avatar:
            thumbnail_url = self.bot.user.avatar.url

        self.clear_items()
        self.add_item(build_panel_container(
            title=panel_title,
            description="\n\n".join(description_parts),
            accent_color=discord.Color.blue(),
            thumbnail_url=thumbnail_url,
            buttons=[self.invite_button, self.room_full_button],
        ))

    async def room_full_button_callback(self, interaction: discord.Interaction):
        await self.bot.get_cog('CreateInvitationCog').lifecycle.finish(
            interaction, invitation_id=self.invitation_id,
        )


class DefaultRoomView(discord.ui.View):
    def __init__(self, bot, url):
        super().__init__(timeout=600)
        self.bot = bot
        self.url = url
        self.conf = config.get_config('invitation')
        self.default_create_room_channel_id = self.conf['default_create_room_channel_id']
        self.default_create_room_button = t('invitation.default_create_room_button')

        self.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=self.default_create_room_button, url=self.url))
