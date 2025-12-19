# bot/cogs/voice_channel_cog.py
import asyncio
from asyncio import sleep

import aiosqlite
import logging
import discord
from discord.ui import Button
from discord.ext import commands, tasks
from discord import app_commands, ui
import json
import aiofiles
from pathlib import Path

from bot.utils import config, check_channel_validity


class AddChannelForm(ui.Modal):
    name_prefix = ui.TextInput(
        label='Room Name Prefix',
        placeholder='Enter the prefix for created rooms (e.g., "游戏房")',
        required=True,
        max_length=10
    )
    channel_type = ui.TextInput(
        label='Channel Type',
        placeholder='Enter "public" or "private"',
        required=True,
        max_length=7,
        default="public"
    )

    def __init__(self, cog, channel):
        super().__init__(title=f'Configure Voice Channel: {channel.name}')
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Validate channel type
        if self.channel_type.value.lower() not in ['public', 'private']:
            await interaction.followup.send("Channel type must be either 'public' or 'private'.", ephemeral=True)
            return

        # Add the new channel configuration
        config_data = {
            "name_prefix": self.name_prefix.value,
            "type": self.channel_type.value.lower()
        }

        # Update the cog's channel_configs
        self.cog.channel_configs[self.channel.id] = config_data

        # Save to file
        await self.cog.save_channel_configs()

        # Create and send embed with all configurations
        embed = await self.cog.format_channel_configs_embed(
            title="Voice Channel Configuration Added",
            description=f"Successfully added configuration for {self.channel.mention}",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)


class DeleteChannelConfirmView(discord.ui.View):
    def __init__(self, cog, channel_id):
        super().__init__(timeout=60)
        self.cog = cog
        self.channel_id = channel_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Remove the channel configuration
        if self.channel_id in self.cog.channel_configs:  # Check for integer ID
            del self.cog.channel_configs[self.channel_id]
            await self.cog.save_channel_configs()

            embed = discord.Embed(
                title="Voice Channel Configuration Removed",
                description=f"Configuration for channel <#{self.channel_id}> has been removed.",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title="Error",
                description=f"No configuration found for channel <#{self.channel_id}>",
                color=discord.Color.red()
            )

        self.disable_all_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Operation Cancelled",
            description="Channel configuration removal cancelled.",
            color=discord.Color.blue()
        )
        self.disable_all_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    def disable_all_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True


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

    def __init__(self, bot, voice_channel, creator, soundboard_enabled=True, room_type="public"):
        super().__init__(timeout=None)  # 永久有效
        self.bot = bot
        self.voice_channel = voice_channel
        self.voice_channel_id = voice_channel.id
        self.creator = creator
        self.creator_id = creator.id
        self.soundboard_enabled = soundboard_enabled
        self.room_type = room_type

        # 加载配置
        self.conf = config.get_config('voicechannel')
        self.control_panel_conf = self.conf['control_panel']
        self.messages = self.control_panel_conf['messages']
        self.button_labels = self.control_panel_conf['buttons']

        # 添加四个按钮
        self.unlock_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=self.button_labels['unlock_label'],
            custom_id=f"unlock_{voice_channel.id}"
        )
        self.unlock_button.callback = self.unlock_callback

        self.lock_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=self.button_labels['lock_label'],
            custom_id=f"lock_{voice_channel.id}"
        )
        self.lock_button.callback = self.lock_callback

        self.full_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=self.button_labels['full_label'],
            custom_id=f"full_{voice_channel.id}"
        )
        self.full_button.callback = self.full_callback

        self.soundboard_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=self.button_labels['soundboard_label'],
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
                await interaction.followup.send(self.messages['not_in_voice'], ephemeral=True)
                return

            # 获取语音频道
            voice_channel = self.bot.get_channel(self.voice_channel_id)
            if not voice_channel:
                await interaction.followup.send(self.messages['channel_not_found'], ephemeral=True)
                return

            # 设置权限
            try:
                await voice_channel.set_permissions(
                    voice_channel.guild.default_role,
                    connect=True
                )
            except discord.Forbidden:
                await interaction.followup.send(self.messages['permission_error'], ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.followup.send(self.messages['http_error'], ephemeral=True)
                return

            # 更新数据库
            main_config = config.get_config('main')
            async with aiosqlite.connect(main_config['db_path']) as db:
                await db.execute('''
                    UPDATE temp_channels
                    SET current_room_type = 'public'
                    WHERE channel_id = ?
                ''', (self.voice_channel_id,))
                await db.commit()

            # 更新room_type并刷新embed
            self.room_type = "public"
            await self.update_panel_embed(interaction.message)

            await interaction.followup.send(self.messages['unlock_success'], ephemeral=True)

        except Exception as e:
            logging.error(f"Error in unlock_callback: {e}", exc_info=True)
            await interaction.followup.send(self.messages['unknown_error'], ephemeral=True)

    async def lock_callback(self, interaction: discord.Interaction):
        """上锁按钮 - 设置房间为私密"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 检查用户是否在语音频道内
            if not interaction.user.voice or interaction.user.voice.channel.id != self.voice_channel_id:
                await interaction.followup.send(self.messages['not_in_voice'], ephemeral=True)
                return

            # 获取语音频道
            voice_channel = self.bot.get_channel(self.voice_channel_id)
            if not voice_channel:
                await interaction.followup.send(self.messages['channel_not_found'], ephemeral=True)
                return

            # 设置权限
            try:
                await voice_channel.set_permissions(
                    voice_channel.guild.default_role,
                    connect=False
                )
            except discord.Forbidden:
                await interaction.followup.send(self.messages['permission_error'], ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.followup.send(self.messages['http_error'], ephemeral=True)
                return

            # 更新数据库
            main_config = config.get_config('main')
            async with aiosqlite.connect(main_config['db_path']) as db:
                await db.execute('''
                    UPDATE temp_channels
                    SET current_room_type = 'private'
                    WHERE channel_id = ?
                ''', (self.voice_channel_id,))
                await db.commit()

            # 更新room_type并刷新embed
            self.room_type = "private"
            await self.update_panel_embed(interaction.message)

            await interaction.followup.send(self.messages['lock_success'], ephemeral=True)

        except Exception as e:
            logging.error(f"Error in lock_callback: {e}", exc_info=True)
            await interaction.followup.send(self.messages['unknown_error'], ephemeral=True)

    async def full_callback(self, interaction: discord.Interaction):
        """满员按钮 - 标记房间满员并从展示板移除"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 检查用户是否在语音频道内
            if not interaction.user.voice or interaction.user.voice.channel.id != self.voice_channel_id:
                await interaction.followup.send(self.messages['not_in_voice'], ephemeral=True)
                return

            # 获取TeamupDisplayCog
            teamup_cog = self.bot.get_cog('TeamupDisplayCog')
            if not teamup_cog:
                await interaction.followup.send(self.messages['full_error'], ephemeral=True)
                return

            # 查询该房间最后一条组队信息
            last_invitation = await teamup_cog.db_manager.get_last_invitation_by_voice_channel(self.voice_channel_id)

            if not last_invitation:
                await interaction.followup.send(self.messages['full_no_invitation'], ephemeral=True)
                return

            # 获取消息
            try:
                text_channel = self.bot.get_channel(last_invitation['invitation_channel_id'])
                if not text_channel:
                    logging.warning(f"Text channel {last_invitation['invitation_channel_id']} not found")
                    await interaction.followup.send(self.messages['full_channel_not_found'], ephemeral=True)
                    return

                message = await text_channel.fetch_message(last_invitation['invitation_message_id'])
            except discord.NotFound:
                logging.warning(f"Invitation message {last_invitation['invitation_message_id']} not found")
                # 清理数据库中的无效记录
                await teamup_cog.db_manager.remove_invalid_invitation(self.voice_channel_id)
                await interaction.followup.send(self.messages['full_message_deleted'], ephemeral=True)
                return
            except discord.Forbidden:
                logging.error(f"No permission to fetch message {last_invitation['invitation_message_id']}")
                await interaction.followup.send(self.messages['full_no_permission'], ephemeral=True)
                return

            # 更新消息为满员状态
            await self.update_message_to_full(message)

            # 从展示板移除
            await teamup_cog.remove_teamup_from_display(interaction.user.id, self.voice_channel_id)

            await interaction.followup.send(self.messages['full_success'], ephemeral=True)

        except Exception as e:
            logging.error(f"Error in full_callback: {e}", exc_info=True)
            await interaction.followup.send(self.messages['full_error'], ephemeral=True)

    async def soundboard_callback(self, interaction: discord.Interaction):
        """声音板按钮 - 切换声音板功能"""
        await interaction.response.defer(ephemeral=True)

        try:
            # 检查是否是房主
            if interaction.user.id != self.creator_id:
                await interaction.followup.send(self.messages['not_room_owner'], ephemeral=True)
                return

            # 获取语音频道
            voice_channel = self.bot.get_channel(self.voice_channel_id)
            if not voice_channel:
                await interaction.followup.send(self.messages['channel_not_found'], ephemeral=True)
                return

            # 切换声音板权限
            try:
                current_overwrites = voice_channel.overwrites_for(voice_channel.guild.default_role)
                new_soundboard_state = not self.soundboard_enabled

                current_overwrites.update(use_soundboard=new_soundboard_state)
                await voice_channel.set_permissions(voice_channel.guild.default_role, overwrite=current_overwrites)

            except discord.Forbidden:
                await interaction.followup.send(self.messages['permission_error'], ephemeral=True)
                return
            except discord.HTTPException:
                await interaction.followup.send(self.messages['http_error'], ephemeral=True)
                return

            # 更新数据库
            main_config = config.get_config('main')
            async with aiosqlite.connect(main_config['db_path']) as db:
                await db.execute('''
                    UPDATE temp_channels
                    SET is_soundboard_enabled = ?
                    WHERE channel_id = ?
                ''', (1 if new_soundboard_state else 0, self.voice_channel_id))
                await db.commit()

            # 更新状态并刷新embed
            self.soundboard_enabled = new_soundboard_state
            await self.update_panel_embed(interaction.message)

            message = self.messages['soundboard_enabled'] if new_soundboard_state else self.messages['soundboard_disabled']
            await interaction.followup.send(message, ephemeral=True)

        except Exception as e:
            logging.error(f"Error in soundboard_callback: {e}", exc_info=True)
            await interaction.followup.send(self.messages['unknown_error'], ephemeral=True)

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
        description = self.control_panel_conf['description_template'].format(
            owner_mention=self.creator.mention,
            soundboard_status=soundboard_status
        )

        color = self.control_panel_conf['colors'][self.room_type]

        embed = discord.Embed(
            title=self.control_panel_conf['title'],
            description=description,
            color=color
        )

        # 设置缩略图为bot头像
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        embed.set_footer(text=self.control_panel_conf['footer'])

        return embed

    async def update_message_to_full(self, message):
        """将组队消息更新为满员状态"""
        try:
            if not message.embeds:
                return

            # 获取create_invitation_cog的配置
            invitation_conf = config.get_config('invitation')
            roomfull_title = invitation_conf.get('roomfull_title', '【已满员】')
            invite_embed_content_edited = invitation_conf.get('invite_embed_content_edited', '')

            embed = message.embeds[0]

            # 从原embed的description中提取语音频道信息
            # 原格式可能是：- 📢 语音频道: ...
            # 需要从中提取URL和其他信息
            # 尝试从description中提取voice channel URL
            import re
            voice_channel_match = re.search(r'https://discord\.com/channels/\d+/(\d+)', embed.description)

            if voice_channel_match:
                # 提取必要信息
                voice_channel_id = voice_channel_match.group(1)
                guild_id_match = re.search(r'https://discord\.com/channels/(\d+)/\d+', embed.description)
                guild_id = guild_id_match.group(1) if guild_id_match else ""
                url = f"https://discord.com/channels/{guild_id}/{voice_channel_id}"

                # 提取mention和time
                mention_match = re.search(r'<@\d+>', embed.description)
                mention = mention_match.group(0) if mention_match else ""

                # 提取时间（相对时间格式）
                time_match = re.search(r'<t:\d+:R>', embed.description)
                time = time_match.group(0) if time_match else ""

                # 从voice_channel获取name
                voice_channel = self.bot.get_channel(int(voice_channel_id))
                channel_name = voice_channel.name if voice_channel else "未知频道"

                # 使用配置的格式创建新description
                new_description = invite_embed_content_edited.format(
                    name=channel_name,
                    url=url,
                    mention=mention,
                    time=time
                )
            else:
                # 如果无法提取，保持原description
                new_description = embed.description

            # 创建新embed
            new_embed = discord.Embed(
                title=f"{roomfull_title} ~~{embed.title}~~",
                description=new_description,
                color=discord.Color.red()
            )

            # 保留原有字段
            for field in embed.fields:
                new_embed.add_field(name=field.name, value=field.value, inline=field.inline)

            # 保留缩略图；满员后移除 footer 避免残留按钮提示
            if embed.thumbnail:
                new_embed.set_thumbnail(url=embed.thumbnail.url)
            # 不保留时间戳，避免右下角显示旧时间

            # 移除所有按钮（统一格式：满员后按钮全部消失）
            await message.edit(embed=new_embed, view=None)

        except discord.Forbidden:
            logging.error(f"No permission to edit message {message.id}")
        except discord.NotFound:
            logging.warning(f"Message {message.id} not found when trying to update to full")
        except Exception as e:
            logging.error(f"Error updating message to full: {e}", exc_info=True)


class VoiceStateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.conf = config.get_config('voicechannel')
        self.channel_configs = {int(channel_id): c for channel_id, c in self.conf['channel_configs'].items()}

        # Start the cleanup task
        self.cleanup_task.start()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if after.channel and after.channel.id in self.channel_configs:
            conf = self.channel_configs[after.channel.id]
            if conf["type"] == "public" or conf["type"] == "private":
                await self.handle_channel(member, after, conf, public=conf["type"] == "public")

        if before.channel:
            await self.cleanup_channel(before.channel.id)

    async def handle_channel(self, member, after, conf, public=True):
        guild = after.channel.guild
        temp_channel_name = f"{conf['name_prefix']}-{member.display_name}"
        fallback_channel_name = f"{conf['name_prefix']}-id被discord屏蔽请及时修改"
        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=public),
            member: discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True, speak=True,
                                                move_members=True)
        }

        # Get all categories with the same name as the current one
        categories = [category for category in guild.categories if category.name == after.channel.category.name]

        # Sort the categories by position
        categories.sort(key=lambda category: category.position)

        temp_channel = None
        for category in categories:
            try:
                # First try with the original name
                temp_channel = await guild.create_voice_channel(name=temp_channel_name, category=category,
                                                                overwrites=overwrites)
                break  # If the channel creation is successful, break the loop
            except discord.errors.HTTPException as e:
                if e.code == 50035 and "Contains words not allowed" in str(e):
                    # If the error is about inappropriate words, try with fallback name
                    try:
                        temp_channel = await guild.create_voice_channel(name=fallback_channel_name, category=category,
                                                                        overwrites=overwrites)
                        break
                    except discord.errors.HTTPException as e2:
                        if e2.code == 50035 and "Maximum number of channels" in str(e2):
                            continue  # Category is full, try next one
                        else:
                            raise e2
                elif e.code == 50035 and "Maximum number of channels" in str(e):
                    continue  # If the category is full, continue to the next one
                else:
                    raise e  # If it's another error, raise it
        else:  # If all categories are full
            # Before creating a new category, increment the position of all categories with a position
            # greater than or equal to the new category's position
            new_category_position = categories[-1].position
            # print(f"Creating new category at position {new_category_position}")

            new_category = await guild.create_category(name=after.channel.category.name,
                                                       position=new_category_position)
            try:
                temp_channel = await guild.create_voice_channel(name=temp_channel_name, category=new_category,
                                                                overwrites=overwrites)
            except discord.errors.HTTPException as e:
                if e.code == 50035 and "Contains words not allowed" in str(e):
                    # If the error is about inappropriate words, use fallback name
                    temp_channel = await guild.create_voice_channel(name=fallback_channel_name, category=new_category,
                                                                    overwrites=overwrites)
                else:
                    raise e

        # Move the member and handle exceptions if the member is no longer connected
        try:
            if member.voice:
                await member.move_to(temp_channel)
            else:
                raise RuntimeError("Member not connected to voice")
        except (discord.HTTPException, discord.NotFound, RuntimeError) as e:
            # Handle exceptions by cleaning up the newly created channel if the move fails
            if isinstance(e, RuntimeError) or "Target user is not connected to voice" in str(e):
                await temp_channel.delete(reason="Cleanup unused channel due to user disconnect")
                if not temp_channel.category.channels:
                    await temp_channel.category.delete(reason="Cleanup unused category")
                return  # 直接返回，不创建控制面板

        # Determine initial room type (default to public unless explicitly set to private)
        initial_room_type = "private" if conf["type"] == "private" else "public"

        # Record the temporary channel in the database
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO temp_channels
                (channel_id, creator_id, is_soundboard_enabled, current_room_type)
                VALUES (?, ?, ?, ?)
            ''', (temp_channel.id, member.id, 1, initial_room_type))
            await db.commit()

        # Send control panel in the voice channel's text chat after a small delay
        await asyncio.sleep(0.5)
        await self.send_control_panel(temp_channel, member, initial_room_type)

    async def send_control_panel(self, voice_channel, creator, room_type):
        """发送房间控制面板到语音频道的文字聊天"""
        try:
            # 创建控制面板View和Embed
            view = RoomControlPanelView(
                self.bot,
                voice_channel,
                creator,
                soundboard_enabled=True,
                room_type=room_type
            )

            embed = view.create_panel_embed()

            # 直接在语音频道的文字聊天中发送消息
            message = await voice_channel.send(embed=embed, view=view)

            # 保存控制面板消息ID到数据库
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    UPDATE temp_channels
                    SET control_panel_message_id = ?, control_panel_channel_id = ?
                    WHERE channel_id = ?
                ''', (message.id, voice_channel.id, voice_channel.id))
                await db.commit()

            # Log to room activity log
            room_logger = logging.getLogger('room_activity')
            room_logger.info(f"Control panel sent for room {voice_channel.id}")

        except Exception as e:
            logging.error(f"Error sending control panel: {e}", exc_info=True)

    async def cleanup_channel(self, channel_id):
        channel = self.bot.get_channel(channel_id)
        if channel and not channel.members:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('SELECT channel_id FROM temp_channels WHERE channel_id = ?', (channel_id,))
                result = await cursor.fetchone()
                if result:
                    # await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (channel_id,))
                    # await db.commit()
                    await channel.delete(reason="Temporary channel cleanup")
                    await sleep(0.5)  # Sleep for a short time to let the channel delete
                    if not channel.category.channels:  # If the category is empty, delete it
                        await channel.category.delete(reason="Temporary category cleanup")

    @tasks.loop(hours=1)
    async def cleanup_task(self):
        logging.info("Running cleanup task")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT channel_id FROM temp_channels')
            channels = await cursor.fetchall()
            for (channel_id,) in channels:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    # The channel no longer exists, so clean up the database entry
                    await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (channel_id,))
                    await db.commit()

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="check_temp_channel_records",
        description="Check the records of temporary channels"
    )
    async def check_temp_channel_records(self, interaction: discord.Interaction):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        # Fetch the records from the database
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT * FROM temp_channels ORDER BY created_at DESC')
            records = await cursor.fetchall()

        if not records:
            await interaction.edit_original_response(content="No records found.")
            return

        view = CheckTempChannelView(self.bot, interaction.user.id, records)
        embed = await view.format_page()
        message = await interaction.edit_original_response(embeds=[embed], view=view)
        view.message = message


    async def format_channel_configs_embed(self, title=None, description=None, color=None):
        """Helper method to create an embed showing all voice channel configurations."""
        embed = discord.Embed(
            title=title or "Voice Channel Configurations",
            description=description,
            color=color or discord.Color.blue()
        )

        config_list = []
        for channel_id, config in self.channel_configs.items():
            channel = self.bot.get_channel(channel_id)
            if channel:
                config_list.append(
                    f"• {channel.mention} (ID: {channel_id})\n"
                    f"  Name Prefix: {config['name_prefix']}\n"
                    f"  Type: {config['type'].capitalize()}\n"
                )
            else:
                config_list.append(
                    f"• Invalid Channel (ID: {channel_id})\n"
                    f"  Name Prefix: {config['name_prefix']}\n"
                    f"  Type: {config['type'].capitalize()}\n"
                )

        embed.add_field(
            name="Configured Channels",
            value="\n".join(config_list) if config_list else "No channels configured.",
            inline=False
        )

        return embed

    @app_commands.command(
        name="vc_list",
        description="List all configured voice channels"
    )
    async def list_voice_channels(self, interaction: discord.Interaction):
        """List all configured voice channels."""
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()
        embed = await self.format_channel_configs_embed()
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="vc_add",
        description="Add a new voice channel for room creation"
    )
    @app_commands.describe(channel="Select the voice channel to configure")
    async def add_voice_channel(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        """Add a new voice channel configuration for room creation."""
        if not await check_channel_validity(interaction):
            return

        # Check if channel already has configuration
        if channel.id in self.channel_configs:
            await interaction.response.send_message(
                f"Channel {channel.mention} already has a configuration.", 
                ephemeral=True
            )
            return

        # Show the modal with channel info
        await interaction.response.send_modal(AddChannelForm(self, channel))

    @app_commands.command(
        name="vc_remove",
        description="Remove a voice channel from room creation"
    )
    @app_commands.describe(
        channel="Select voice channel to remove (if channel still exists)",
        channel_id="Enter channel ID manually (if channel was deleted)"
    )
    async def remove_voice_channel(
        self, 
        interaction: discord.Interaction, 
        channel: discord.VoiceChannel = None,
        channel_id: str = None
    ):
        """Remove a voice channel configuration."""
        if not await check_channel_validity(interaction):
            return

        # Parameter validation: at least one must be provided
        if not channel and not channel_id:
            await interaction.response.send_message(
                "Please provide either a channel selection or channel ID.", 
                ephemeral=True
            )
            return
        
        await interaction.response.defer()

        # Determine target channel ID (prioritize channel_id if both provided)
        if channel_id:
            try:
                target_channel_id = int(channel_id)
            except ValueError:
                await interaction.followup.send("Invalid channel ID format.", ephemeral=True)
                return
            
            # Get channel object for display (might be None if channel was deleted)
            target_channel = self.bot.get_channel(target_channel_id)
        else:
            target_channel_id = channel.id
            target_channel = channel

        # Check if channel has configuration
        if target_channel_id not in self.channel_configs:
            await interaction.followup.send("No configuration found for this channel.", ephemeral=True)
            return

        # Create confirmation embed and view
        channel_mention = target_channel.mention if target_channel else f"Channel ID: {target_channel_id} (deleted)"
        embed = discord.Embed(
            title="Confirm Channel Removal",
            description=f"Are you sure you want to remove the configuration for {channel_mention}?",
            color=discord.Color.yellow()
        )
        embed.add_field(
            name="Current Configuration",
            value=f"Name Prefix: {self.channel_configs[target_channel_id]['name_prefix']}\n"
                  f"Type: {self.channel_configs[target_channel_id]['type'].capitalize()}",
            inline=False
        )

        class DeleteChannelConfirmView(discord.ui.View):
            def __init__(self, cog, channel_id, channel_obj=None):
                super().__init__(timeout=60)
                self.cog = cog
                self.channel_id = channel_id
                self.channel = channel_obj

            @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                # Remove the channel configuration
                if self.channel_id in self.cog.channel_configs:
                    del self.cog.channel_configs[self.channel_id]
                    await self.cog.save_channel_configs()

                    # Create embed with updated configurations
                    channel_mention = self.channel.mention if self.channel else f"Channel ID: {self.channel_id} (deleted)"
                    embed = await self.cog.format_channel_configs_embed(
                        title="Voice Channel Configuration Removed",
                        description=f"Configuration for {channel_mention} has been removed.",
                        color=discord.Color.green()
                    )
                else:
                    channel_mention = self.channel.mention if self.channel else f"Channel ID: {self.channel_id} (deleted)"
                    embed = discord.Embed(
                        title="Error",
                        description=f"No configuration found for channel {channel_mention}",
                        color=discord.Color.red()
                    )

                self.disable_all_buttons()
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                embed = discord.Embed(
                    title="Operation Cancelled",
                    description="Channel configuration removal cancelled.",
                    color=discord.Color.blue()
                )
                self.disable_all_buttons()
                await interaction.response.edit_message(embed=embed, view=self)

            def disable_all_buttons(self):
                for child in self.children:
                    if isinstance(child, discord.ui.Button):
                        child.disabled = True

        view = DeleteChannelConfirmView(self, target_channel_id, target_channel)
        await interaction.followup.send(embed=embed, view=view)

    async def restore_control_panels(self):
        """恢复所有房间控制面板（Bot重启后调用）"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    SELECT channel_id, creator_id, control_panel_message_id,
                           is_soundboard_enabled, current_room_type
                    FROM temp_channels
                    WHERE control_panel_message_id IS NOT NULL
                ''')
                records = await cursor.fetchall()

            restored_count = 0
            failed_count = 0
            cleaned_count = 0

            for record in records:
                try:
                    voice_channel_id, creator_id, message_id, soundboard, room_type = record

                    # 检查语音频道（语音频道本身就是文字聊天的位置）
                    voice_channel = self.bot.get_channel(voice_channel_id)
                    if not voice_channel:
                        logging.warning(f"Voice channel {voice_channel_id} not found during restore")
                        failed_count += 1
                        continue

                    # 获取消息（从语音频道的文字聊天中）
                    try:
                        message = await voice_channel.fetch_message(message_id)
                    except discord.NotFound:
                        logging.warning(f"Control panel message {message_id} not found")
                        # 清理数据库
                        await self.clear_control_panel_data(voice_channel_id)
                        cleaned_count += 1
                        failed_count += 1
                        continue
                    except discord.Forbidden:
                        logging.error(f"No permission to fetch message {message_id}")
                        failed_count += 1
                        continue

                    # 获取创建者
                    try:
                        creator = await self.bot.fetch_user(creator_id)
                    except:
                        creator = None
                        logging.warning(f"Creator {creator_id} not found")

                    # 重新附加View
                    view = RoomControlPanelView(
                        self.bot,
                        voice_channel,
                        creator,
                        soundboard_enabled=bool(soundboard),
                        room_type=room_type or "public"
                    )

                    await message.edit(view=view)
                    restored_count += 1

                except Exception as e:
                    logging.error(f"Error restoring control panel for record {record}: {e}", exc_info=True)
                    failed_count += 1
                    continue

            logging.info(f"Control panels restored: {restored_count} success, {failed_count} failed, {cleaned_count} cleaned")

        except Exception as e:
            logging.error(f"Critical error in restore_control_panels: {e}", exc_info=True)

    async def clear_control_panel_data(self, voice_channel_id: int):
        """清理控制面板数据"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    UPDATE temp_channels
                    SET control_panel_message_id = NULL, control_panel_channel_id = NULL
                    WHERE channel_id = ?
                ''', (voice_channel_id,))
                await db.commit()
        except Exception as e:
            logging.error(f"Error clearing control panel data: {e}", exc_info=True)

    async def save_channel_configs(self):
        """Save the channel configurations to the JSON file."""
        config_path = Path('./bot/config/config_voicechannel.json')

        async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            config_data = json.loads(content)

        # Update the channel_configs in the config data
        # Convert all keys to strings for JSON serialization
        config_data['channel_configs'] = {
            str(channel_id): config
            for channel_id, config in self.channel_configs.items()
        }

        async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(config_data, indent=2, ensure_ascii=False))

    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure the table exists and migrate existing tables
        async with aiosqlite.connect(self.db_path) as db:
            # Create table if not exists (for new installations)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS temp_channels (
                    channel_id INTEGER PRIMARY KEY,
                    creator_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    control_panel_message_id INTEGER,
                    control_panel_channel_id INTEGER,
                    is_soundboard_enabled BOOLEAN DEFAULT 1,
                    current_room_type TEXT DEFAULT 'public'
                );
            ''')

            # ===== AUTO MIGRATION (v1.7.1+) - Can be removed after a few versions =====
            # Check and add missing columns for existing installations
            cursor = await db.execute("PRAGMA table_info(temp_channels)")
            existing_columns = {row[1] for row in await cursor.fetchall()}

            columns_to_add = [
                ("control_panel_message_id", "INTEGER"),
                ("control_panel_channel_id", "INTEGER"),
                ("is_soundboard_enabled", "BOOLEAN DEFAULT 1"),
                ("current_room_type", "TEXT DEFAULT 'public'")
            ]

            for col_name, col_type in columns_to_add:
                if col_name not in existing_columns:
                    logging.info(f"[MIGRATION] Adding column {col_name} to temp_channels")
                    await db.execute(f"ALTER TABLE temp_channels ADD COLUMN {col_name} {col_type}")
            # ===== END AUTO MIGRATION =====

            await db.commit()

            # Check for empty channels on startup
            cursor = await db.execute('SELECT channel_id FROM temp_channels')
            channels = await cursor.fetchall()
            for (channel_id,) in channels:
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    # The channel no longer exists, so clean up the database entry
                    await db.execute('DELETE FROM temp_channels WHERE channel_id = ?', (channel_id,))
                    await db.commit()
                elif not channel.members:
                    # If the channel exists and is empty, delete it
                    await self.cleanup_channel(channel_id)

            # Check for empty categories on startup
            for guild in self.bot.guilds:
                # Get the category names from CHANNEL_CONFIGS
                category_names = [self.bot.get_channel(channel_id).category.name
                                  for channel_id in self.channel_configs.keys()
                                  if self.bot.get_channel(channel_id) is not None]
                for category in guild.categories:
                    if not category.channels and category.name in category_names:
                        await category.delete(reason="Temporary category cleanup")

            # Restore control panels for existing rooms
            await self.restore_control_panels()
