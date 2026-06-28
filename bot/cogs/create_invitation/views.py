import logging
import re

import discord
from discord.utils import format_dt

from bot.utils import config
from bot.utils.components_v2 import build_panel_container
from bot.utils.i18n import t


class TeamInvitationView(discord.ui.LayoutView):
    def __init__(self, bot, channel, user, role_db):
        super().__init__(timeout=600)
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
        self.room_full_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=self.roomfull_button_label,
            custom_id="room_full_button"
        )
        self.room_full_button.callback = self.room_full_button_callback

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

        guild_id = author.guild.id
        channel_id = author.voice.channel.id
        vc_url_direct = f"https://discord.com/channels/{guild_id}/{channel_id}"

        panel_title = title or content
        # Remove mentions from content
        panel_title = re.sub(r'<@\d+>', '', panel_title)
        panel_title = re.sub(r'<@&\d+>', '', panel_title)

        # Truncate the content
        if len(panel_title) > 256:
            panel_title = panel_title[:253] + "..."

        description_parts = [
            self.invite_embed_content.format(
                vc_url=vc_url_direct,
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
        """房间满员按钮回调 - 使用抽象出来的满员逻辑"""
        # Defer the response
        await interaction.response.defer(ephemeral=True)

        # 检查是否是按钮的拥有者
        if interaction.user != self.user:
            await interaction.followup.send(self.interaction_target_error_message, ephemeral=True)
            return

        original_channel_id = self.channel.id

        # 检查用户是否在语音频道
        if not self.user.voice or self.user.voice.channel.id != original_channel_id:
            await interaction.followup.send(self.not_in_vc_message, ephemeral=True)
            return

        # 获取CreateInvitationCog实例来调用抽象的方法
        invitation_cog = self.bot.get_cog('CreateInvitationCog')
        if invitation_cog:
            # 调用抽象出来的满员方法
            await invitation_cog.update_message_to_full(interaction.message)
        else:
            # 如果cog不存在，直接处理（不应该发生）
            logging.error("CreateInvitationCog not found")
            await interaction.followup.send("❌ 内部错误，请联系管理员", ephemeral=True)
            return

        # 从展示板移除组队信息
        teamup_cog = self.bot.get_cog('TeamupDisplayCog')
        if teamup_cog:
            await teamup_cog.remove_teamup_from_display(self.user.id, original_channel_id)

        await interaction.followup.send(self.roomfull_set_message, ephemeral=True)


class DefaultRoomView(discord.ui.View):
    def __init__(self, bot, url):
        super().__init__(timeout=600)
        self.bot = bot
        self.url = url
        self.conf = config.get_config('invitation')
        self.default_create_room_channel_id = self.conf['default_create_room_channel_id']
        self.default_create_room_button = t('invitation.default_create_room_button')

        self.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=self.default_create_room_button, url=self.url))
