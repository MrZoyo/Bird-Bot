import logging
import re

import discord
from discord.utils import format_dt

from bot.utils import config
from bot.utils.i18n import t


class TeamInvitationView(discord.ui.View):
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
        self.invite_embed_footer = t('invitation.invite_embed_footer')
        self.interaction_target_error_message = t('invitation.interaction_target_error_message')
        self.roomfull_set_message = t('invitation.roomfull_set_message')
        self.not_in_vc_message = t('invitation.not_in_vc_message')
        self.extract_channel_id_error = t('invitation.extract_channel_id_error')

        # Adding the join room button
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=self.invite_button_label, url=self.url))

        # Adding the room full button (for rooms without control panel, like private rooms)
        self.room_full_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=self.roomfull_button_label,
            custom_id="room_full_button"
        )
        self.room_full_button.callback = self.room_full_button_callback
        self.add_item(self.room_full_button)

    async def create_embed(self, obj):
        # Get the current time
        current_time = discord.utils.utcnow()
        # Format the timestamp for the embed
        elapsed_time = format_dt(current_time, style='R')
        original_time = format_dt(current_time, style='f')

        # Check if the passed object is a message or an interaction
        if isinstance(obj, discord.Message):
            author = obj.author
            content = obj.content
        elif isinstance(obj, discord.Interaction):
            author = obj.user
            content = obj.data.get('name')  # Get the name of the slash command
        else:
            raise ValueError("The passed object must be a discord.Message or a discord.Interaction.")

        # Get user's signature if exists (owned by role_db)
        sig = await self.role_db.get_user_signature(author.id)
        signature = sig['signature'] if sig and not sig['is_disabled'] else None

        guild_id = author.guild.id
        channel_id = author.voice.channel.id
        vc_url_direct = f"https://discord.com/channels/{guild_id}/{channel_id}"

        # Remove mentions from content
        content = re.sub(r'<@\d+>', '', content)
        content = re.sub(r'<@&\d+>', '', content)

        # Truncate the content
        if len(content) > 256:
            content = content[:253] + "..."

        embed = discord.Embed(
            title=content,
            description=self.invite_embed_content.format(vc_url=vc_url_direct, mention=author.mention,
                                                         time=elapsed_time),
            color=discord.Color.blue()
        )

        # Add signature field if exists
        if signature:
            embed.add_field(name="", value=signature, inline=False)

        # Set thumbnail
        if author.avatar:
            embed.set_thumbnail(url=author.avatar.url)
        # If the author doesn't have an avatar, check if the bot has an avatar
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        embed.timestamp = current_time
        embed.set_footer(text=self.invite_embed_footer)

        return embed

    async def room_full_button_callback(self, interaction: discord.Interaction):
        """房间满员按钮回调 - 使用抽象出来的满员逻辑"""
        # Defer the response
        await interaction.response.defer(ephemeral=True)

        # 检查是否是按钮的拥有者
        if interaction.user != self.user:
            await interaction.followup.send(self.interaction_target_error_message, ephemeral=True)
            return

        # Extract the channel ID from the URL in the embed description
        embed = interaction.message.embeds[0]
        match = re.search(r"https://discord.com/channels/\d+/(\d+)", embed.description)
        if not match:
            await interaction.followup.send(self.extract_channel_id_error, ephemeral=True)
            return

        original_channel_id = int(match.group(1))

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
