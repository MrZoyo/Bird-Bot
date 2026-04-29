import logging

import discord
from discord.ui import Button

from bot.cogs.create_invitation.full_message import update_invitation_message_to_full
from bot.utils import config
from bot.utils.i18n import t


class CheckTempChannelView(discord.ui.View):
    def __init__(self, bot, user_id, records, page=1):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user_id = user_id
        self.records = records
        self.page = page
        self.message = None  # This will hold the reference to the message

        self.conf = config.get_config()
        self.db_path = self.conf['db_path']

        # Define the buttons
        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.primary, disabled=True)
        self.next_button = Button(label="Next", style=discord.ButtonStyle.green, disabled=True)

        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        # Add the buttons to the view
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

        self.item_each_page = 5
        self.total_pages = (len(records) - 1) // self.item_each_page + 1
        self.total_records = len(records)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def format_page(self):
        # Fetch the records for the current page from memory
        records = self.records[(self.page - 1) * self.item_each_page: self.page * self.item_each_page]

        # Enable or disable the buttons based on the existence of more records
        self.children[0].disabled = (self.page == 1)
        self.children[1].disabled = ((self.page * self.item_each_page) >= len(self.records))

        # Create an embed with the records
        embed = discord.Embed(title="Temp Channel Records", color=discord.Color.blue())

        records_str = ""
        for record in records:
            channel_id = record[0]
            creator_id = record[1]
            created_at = record[2]
            records_str += (f"Time: {created_at}\n"
                            f"Channel: <#{channel_id}>\n"
                            f"Channel ID: {channel_id}\n"
                            f"Creator: <@{creator_id}>\n\n")

        embed.add_field(name="Records", value=records_str, inline=False)

        # Add footer
        embed.set_footer(text=f"Page {self.page}/{self.total_pages} - Total channels: {self.total_records}")

        return embed

    async def previous_page(self, interaction: discord.Interaction):
        self.page -= 1
        embed = await self.format_page()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        embed = await self.format_page()
        await interaction.response.edit_message(embed=embed, view=self)


class RoomControlPanelView(discord.ui.View):
    """房间控制面板View - 包含解锁、上锁、满员、声音板四个按钮"""

    def __init__(self, bot, voice_channel, creator, db, soundboard_enabled=True, room_type="public"):
        super().__init__(timeout=None)  # 永久有效
        self.bot = bot
        self.voice_channel = voice_channel
        self.voice_channel_id = voice_channel.id
        self.creator = creator
        self.creator_id = creator.id
        self.db = db
        self.soundboard_enabled = soundboard_enabled
        self.room_type = room_type

        # Only `colors` stays in yaml; all text (title / footer /
        # description / button labels / status messages) is resolved
        # via the t() helper against the voicechannel locale file.
        self.conf = config.get_config('voicechannel')
        self.colors = self.conf['control_panel']['colors']

        # 添加四个按钮
        self.unlock_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=t('voicechannel.control_panel.buttons.unlock_label'),
            custom_id=f"unlock_{voice_channel.id}"
        )
        self.unlock_button.callback = self.unlock_callback

        self.lock_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=t('voicechannel.control_panel.buttons.lock_label'),
            custom_id=f"lock_{voice_channel.id}"
        )
        self.lock_button.callback = self.lock_callback

        self.full_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=t('voicechannel.control_panel.buttons.full_label'),
            custom_id=f"full_{voice_channel.id}"
        )
        self.full_button.callback = self.full_callback

        self.soundboard_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=t('voicechannel.control_panel.buttons.soundboard_label'),
            custom_id=f"soundboard_{voice_channel.id}"
        )
        self.soundboard_button.callback = self.soundboard_callback

        self.add_item(self.unlock_button)
        self.add_item(self.lock_button)
        self.add_item(self.full_button)
        self.add_item(self.soundboard_button)

    async def unlock_callback(self, interaction: discord.Interaction):
        """解锁按钮 - 设置房间为公开"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 检查用户是否在语音频道内
            if not interaction.user.voice or interaction.user.voice.channel.id != self.voice_channel_id:
                await interaction.followup.send(t('voicechannel.control_panel.messages.not_in_voice'), ephemeral=True)
                return

            # 获取语音频道
            voice_channel = self.bot.get_channel(self.voice_channel_id)
            if not voice_channel:
                await interaction.followup.send(t('voicechannel.control_panel.messages.channel_not_found'), ephemeral=True)
                return

            # 设置权限
            try:
                await voice_channel.set_permissions(
                    voice_channel.guild.default_role,
                    connect=True
                )
            except discord.Forbidden:
                await interaction.followup.send(t('voicechannel.control_panel.messages.permission_error'), ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.followup.send(t('voicechannel.control_panel.messages.http_error'), ephemeral=True)
                return

            # 更新数据库
            await self.db.set_room_type(self.voice_channel_id, 'public')

            # 更新room_type并刷新embed
            self.room_type = "public"
            await self.update_panel_embed(interaction.message)

            await interaction.followup.send(t('voicechannel.control_panel.messages.unlock_success'), ephemeral=True)

        except Exception as e:
            logging.error(f"Error in unlock_callback: {e}", exc_info=True)
            await interaction.followup.send(t('voicechannel.control_panel.messages.unknown_error'), ephemeral=True)

    async def lock_callback(self, interaction: discord.Interaction):
        """上锁按钮 - 设置房间为私密"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 检查用户是否在语音频道内
            if not interaction.user.voice or interaction.user.voice.channel.id != self.voice_channel_id:
                await interaction.followup.send(t('voicechannel.control_panel.messages.not_in_voice'), ephemeral=True)
                return

            # 获取语音频道
            voice_channel = self.bot.get_channel(self.voice_channel_id)
            if not voice_channel:
                await interaction.followup.send(t('voicechannel.control_panel.messages.channel_not_found'), ephemeral=True)
                return

            # 设置权限
            try:
                await voice_channel.set_permissions(
                    voice_channel.guild.default_role,
                    connect=False
                )
            except discord.Forbidden:
                await interaction.followup.send(t('voicechannel.control_panel.messages.permission_error'), ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.followup.send(t('voicechannel.control_panel.messages.http_error'), ephemeral=True)
                return

            # 更新数据库
            await self.db.set_room_type(self.voice_channel_id, 'private')

            # 更新room_type并刷新embed
            self.room_type = "private"
            await self.update_panel_embed(interaction.message)

            await interaction.followup.send(t('voicechannel.control_panel.messages.lock_success'), ephemeral=True)

        except Exception as e:
            logging.error(f"Error in lock_callback: {e}", exc_info=True)
            await interaction.followup.send(t('voicechannel.control_panel.messages.unknown_error'), ephemeral=True)

    async def full_callback(self, interaction: discord.Interaction):
        """满员按钮 - 标记房间满员并从展示板移除"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 检查用户是否在语音频道内
            if not interaction.user.voice or interaction.user.voice.channel.id != self.voice_channel_id:
                await interaction.followup.send(t('voicechannel.control_panel.messages.not_in_voice'), ephemeral=True)
                return

            # 获取TeamupDisplayCog
            teamup_cog = self.bot.get_cog('TeamupDisplayCog')
            if not teamup_cog:
                await interaction.followup.send(t('voicechannel.control_panel.messages.full_error'), ephemeral=True)
                return

            # 查询该房间最后一条组队信息
            last_invitation = await teamup_cog.db_manager.get_last_invitation_by_voice_channel(self.voice_channel_id)

            if not last_invitation:
                await interaction.followup.send(t('voicechannel.control_panel.messages.full_no_invitation'), ephemeral=True)
                return

            # 获取消息
            try:
                text_channel = self.bot.get_channel(last_invitation['invitation_channel_id'])
                if not text_channel:
                    logging.warning(f"Text channel {last_invitation['invitation_channel_id']} not found")
                    await interaction.followup.send(t('voicechannel.control_panel.messages.full_channel_not_found'), ephemeral=True)
                    return

                message = await text_channel.fetch_message(last_invitation['invitation_message_id'])
            except discord.NotFound:
                logging.warning(f"Invitation message {last_invitation['invitation_message_id']} not found")
                # 清理数据库中的无效记录
                await teamup_cog.db_manager.remove_invalid_invitation(self.voice_channel_id)
                await interaction.followup.send(t('voicechannel.control_panel.messages.full_message_deleted'), ephemeral=True)
                return
            except discord.Forbidden:
                logging.error(f"No permission to fetch message {last_invitation['invitation_message_id']}")
                await interaction.followup.send(t('voicechannel.control_panel.messages.full_no_permission'), ephemeral=True)
                return

            # 更新消息为满员状态
            await self.update_message_to_full(message)

            # 从展示板移除
            await teamup_cog.remove_teamup_from_display(interaction.user.id, self.voice_channel_id)

            await interaction.followup.send(t('voicechannel.control_panel.messages.full_success'), ephemeral=True)

        except Exception as e:
            logging.error(f"Error in full_callback: {e}", exc_info=True)
            await interaction.followup.send(t('voicechannel.control_panel.messages.full_error'), ephemeral=True)

    async def soundboard_callback(self, interaction: discord.Interaction):
        """声音板按钮 - 切换声音板功能"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 检查是否是房主
            if interaction.user.id != self.creator_id:
                await interaction.followup.send(t('voicechannel.control_panel.messages.not_room_owner'), ephemeral=True)
                return

            # 获取语音频道
            voice_channel = self.bot.get_channel(self.voice_channel_id)
            if not voice_channel:
                await interaction.followup.send(t('voicechannel.control_panel.messages.channel_not_found'), ephemeral=True)
                return

            # 切换声音板权限
            try:
                current_overwrites = voice_channel.overwrites_for(voice_channel.guild.default_role)
                new_soundboard_state = not self.soundboard_enabled

                current_overwrites.update(use_soundboard=new_soundboard_state)
                await voice_channel.set_permissions(voice_channel.guild.default_role, overwrite=current_overwrites)

            except discord.Forbidden:
                await interaction.followup.send(t('voicechannel.control_panel.messages.permission_error'), ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.followup.send(t('voicechannel.control_panel.messages.http_error'), ephemeral=True)
                return

            # 更新数据库
            await self.db.set_soundboard(self.voice_channel_id, new_soundboard_state)

            # 更新状态并刷新embed
            self.soundboard_enabled = new_soundboard_state
            await self.update_panel_embed(interaction.message)

            message = t('voicechannel.control_panel.messages.soundboard_enabled') if new_soundboard_state else t('voicechannel.control_panel.messages.soundboard_disabled')
            await interaction.followup.send(message, ephemeral=True)

        except Exception as e:
            logging.error(f"Error in soundboard_callback: {e}", exc_info=True)
            await interaction.followup.send(t('voicechannel.control_panel.messages.unknown_error'), ephemeral=True)

    async def update_panel_embed(self, message):
        """更新控制面板的embed"""
        try:
            embed = self.create_panel_embed()
            await message.edit(embed=embed, view=self)
        except Exception as e:
            logging.error(f"Error updating panel embed: {e}", exc_info=True)

    def create_panel_embed(self):
        """创建控制面板embed"""
        soundboard_status = "开启" if self.soundboard_enabled else "关闭"
        description = t('voicechannel.control_panel.description_template').format(
            owner_mention=self.creator.mention,
            soundboard_status=soundboard_status
        )

        color = self.colors[self.room_type]

        embed = discord.Embed(
            title=t('voicechannel.control_panel.title'),
            description=description,
            color=color
        )

        # 设置缩略图为bot头像
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        embed.set_footer(text=t('voicechannel.control_panel.footer'))

        return embed

    async def update_message_to_full(self, message):
        """将组队消息更新为满员状态"""
        await update_invitation_message_to_full(self.bot, message)
