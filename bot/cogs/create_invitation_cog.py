# bot/cogs/create_invitation_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import re
import logging
import datetime
import json
import asyncio
from discord.utils import format_dt
from pathlib import Path
import aiofiles
from bot.utils import config, check_channel_validity
import aiosqlite


class TeamInvitationView(discord.ui.View):
    def __init__(self, bot, channel, user):
        super().__init__(timeout=600)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.url = f"https://discord.com/channels/{channel.guild.id}/{channel.id}"

        # Get main config for db_path
        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.conf = config.get_config('invitation')
        self.roomfull_button_label = self.conf['roomfull_button_label']
        self.invite_button_label = self.conf['invite_button_label']
        self.invite_embed_content = self.conf['invite_embed_content']
        self.invite_embed_footer = self.conf['invite_embed_footer']
        self.interaction_target_error_message = self.conf['interaction_target_error_message']
        self.roomfull_set_message = self.conf['roomfull_set_message']
        self.not_in_vc_message = self.conf['not_in_vc_message']
        self.extract_channel_id_error = self.conf['extract_channel_id_error']

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

        # Get user's signature if exists
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'SELECT signature, is_disabled FROM user_signatures WHERE user_id = ?',
                (author.id,)
            )
            result = await cursor.fetchone()
            signature = result[0] if result and not result[1] else None

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
        self.default_create_room_button = self.conf['default_create_room_button']

        self.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=self.default_create_room_button, url=self.url))


class CreateInvitationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.conf = config.get_config('invitation')
        self.illegal_team_response = self.conf['illegal_team_response']
        self.default_invite_embed_title = self.conf['default_invite_embed_title']
        self.default_create_room_channel_id = self.conf['default_create_room_channel_id']
        self.ignore_channel_message = self.conf['ignore_channel_message']
        self.failed_invite_responses = self.conf['failed_invite_responses']
        self.ignore_user_ids = self.conf['ignore_user_ids']
        self.ignore_channel_ids = self.conf['ignore_channel_ids']
        self.roomfull_title = self.conf.get('roomfull_title', '【已满员】')

    async def update_message_to_full(self, message):
        """将组队消息更新为满员状态（可复用方法）"""
        try:
            if not message.embeds:
                return

            embed = message.embeds[0]
            invite_embed_content_edited = self.conf.get('invite_embed_content_edited', '')

            # 从原embed的description中提取语音频道信息
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

                # 使用配置的格式创建新description（带"偷看一眼"链接）
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
                title=f"{self.roomfull_title} ~~{embed.title}~~",
                description=new_description,
                color=discord.Color.red()
            )

            # 保留原有字段
            for field in embed.fields:
                new_embed.add_field(name=field.name, value=field.value, inline=field.inline)

            # 保留缩略图；满员时移除 footer 避免残留按钮指示
            if embed.thumbnail:
                new_embed.set_thumbnail(url=embed.thumbnail.url)
            # 不保留时间戳，避免右下角显示旧的时间

            # 移除所有按钮（Link按钮无法disabled，所以直接移除）
            await message.edit(embed=new_embed, view=None)

        except discord.Forbidden:
            logging.error(f"No permission to edit message {message.id}")
        except discord.NotFound:
            logging.warning(f"Message {message.id} not found when trying to update to full")
        except Exception as e:
            logging.error(f"Error updating message to full: {e}", exc_info=True)

    async def mark_old_invitation_full(self, old_invitation):
        """异步将旧的组队消息设置为满员"""
        try:
            # 1. 获取消息
            text_channel = self.bot.get_channel(old_invitation['invitation_channel_id'])
            if not text_channel:
                logging.warning(f"Old invitation channel {old_invitation['invitation_channel_id']} not found")
                return

            try:
                old_message = await text_channel.fetch_message(old_invitation['invitation_message_id'])
            except discord.NotFound:
                logging.warning(f"Old invitation message {old_invitation['invitation_message_id']} not found, already deleted")
                return
            except discord.Forbidden:
                logging.error(f"No permission to fetch old invitation message")
                return

            # 2. 更新为满员状态
            await self.update_message_to_full(old_message)

        except Exception as e:
            logging.error(f"Error marking old invitation as full: {e}", exc_info=True)
            # 不向用户抛出错误，静默处理

    @commands.Cog.listener()
    async def on_message(self, message):
        # If the message author is the bot itself, return immediately
        if message.author == self.bot.user:
            return

        # If the message author is a bot, return immediately
        if message.author.bot:
            return

        # 检查是否满足忽略条件：仅有6个字符且不包含等号、中文字、空格，
        # 但如果包含 "flex" 或 "rank" 或 "aram"（无论大小写），则不忽略。
        if (len(message.content) == 6 and
                not re.search(r"[=＝\s]", message.content) and  # Check for any equal sign or space
                not re.search(r"(?i)(flex|rank|aram)", message.content) and
                not re.search(r"[\u4e00-\u9FFF]", message.content)):  # Check for any Chinese character
            # print(f"忽略的消息: {message.content}")
            return  # 忽略这条消息

        # if the message contains a URL, not process it
        if re.search(r"https?:\/\/", message.content):
            return

        # check if the user is in the ignore list
        if message.author.id in self.ignore_user_ids:
            return  # Ignore the message

        # 前缀：匹配"缺"、"等"、"="、"＝"、"q"、"Q"。
        # 主体：匹配数字、"一"到"五"的汉字、"n"、"N"、"全世界"、"W/world"。
        # 排除：不应该后跟"分"、"分钟"、"min"、"个钟"、"小时"。
        pattern = r"(?:(缺|等|[=＝]|[Qq]))(?:(\d|[一二三四五]|[nN]|全世界|world|World))(?!(分|分钟|min|个钟|小时))"

        # Find all matches in the message content
        matches = re.findall(pattern, message.content, re.IGNORECASE)
        # Filter out matches that end with a digit followed by a letter
        valid_matches = [match for match in matches if not re.search(r'\d[A-Z]$', message.content, re.IGNORECASE)]

        # Define a default value for reply_message
        reply_message = ""

        if valid_matches:
            # Check if the message is in an ignored channel
            if message.channel.id in self.conf['ignore_channel_ids']:
                await message.reply(self.ignore_channel_message, delete_after=10)
                return

            # Use keyword detection logger
            keyword_logger = logging.getLogger('keyword_detection')
            keyword_logger.info(f'检测到 {message.author} 的内容: {message.content}, 匹配项: {valid_matches}!')

            # Check if the author is in a voice channel
            if message.author.voice and message.author.voice.channel:
                try:
                    channel = message.author.voice.channel

                    # ===== 步骤1: 获取旧的组队消息ID（如果存在）=====
                    old_invitation = None
                    teamup_cog = self.bot.get_cog('TeamupDisplayCog')

                    if teamup_cog:
                        old_invitation = await teamup_cog.db_manager.get_last_invitation_by_voice_channel(channel.id)

                    # ===== 步骤2: 立即创建并发送新的组队消息 =====
                    view = TeamInvitationView(self.bot, channel, message.author)
                    embed = await view.create_embed(message)
                    new_message = await message.reply(embed=embed, view=view)

                    # ===== 步骤3: 添加到展示板并保存新消息ID =====
                    if teamup_cog:
                        # 添加到展示板（这会替换旧的记录）
                        await teamup_cog.add_teamup_to_display(
                            message.author.id,
                            message.channel.id,
                            channel.id,
                            message.content
                        )

                        # 保存新消息ID
                        await teamup_cog.db_manager.save_invitation_message(
                            channel.id,
                            new_message.id,
                            message.channel.id
                        )

                    # ===== 步骤4: 异步处理旧消息（设置为满员）=====
                    if old_invitation:
                        # 使用 asyncio.create_task 异步执行，不阻塞
                        asyncio.create_task(self.mark_old_invitation_full(old_invitation))

                except Exception as e:
                    reply_message = self.failed_invite_responses + str(e)

            else:
                reply_message = self.illegal_team_response.format(mention=message.author.mention)

                # Create the URL for the default room
                guild_id = message.guild.id
                default_room_url = f"https://discord.com/channels/{guild_id}/{self.default_create_room_channel_id}"
                view = DefaultRoomView(self.bot, default_room_url)

            # Only reply if reply_message is not empty
            if reply_message:
                await message.reply(reply_message, view=view)
            # Ends after replying to the first match, ensuring that not repeatedly reply to
            # the same message with multiple matches
            return

    @app_commands.command(name="invt")
    @app_commands.describe(title="Optional title for the invitation.")
    async def invitation(self, interaction: discord.Interaction, title: str = None):
        """Create an invitation to the voice channel the user is currently in."""
        # Defer the response
        await interaction.response.defer()

        if interaction.user.voice and interaction.user.voice.channel:
            try:
                channel = interaction.user.voice.channel

                # ===== 步骤1: 获取旧的组队消息ID（如果存在）=====
                old_invitation = None
                teamup_cog = self.bot.get_cog('TeamupDisplayCog')

                if teamup_cog:
                    old_invitation = await teamup_cog.db_manager.get_last_invitation_by_voice_channel(channel.id)

                # ===== 步骤2: 立即创建并发送新的组队消息 =====
                view = TeamInvitationView(self.bot, channel, interaction.user)
                embed = await view.create_embed(interaction)
                embed.title = title or self.default_invite_embed_title

                # Truncate the content to 256 characters if longer
                if len(embed.title) > 256:
                    embed.title = embed.title[:253] + "..."

                new_message = await interaction.followup.send(embed=embed, view=view)

                # ===== 步骤3: 添加到展示板并保存新消息ID =====
                if teamup_cog:
                    content = title or self.default_invite_embed_title
                    # 添加到展示板（这会替换旧的记录）
                    await teamup_cog.add_teamup_to_display(
                        interaction.user.id,
                        interaction.channel.id,
                        channel.id,
                        content
                    )

                    # 保存新消息ID
                    await teamup_cog.db_manager.save_invitation_message(
                        channel.id,
                        new_message.id,
                        interaction.channel.id
                    )

                # ===== 步骤4: 异步处理旧消息（设置为满员）=====
                if old_invitation:
                    # 使用 asyncio.create_task 异步执行，不阻塞
                    asyncio.create_task(self.mark_old_invitation_full(old_invitation))

            except Exception as e:
                await interaction.followup.send(f"Failed to create an invitation: {str(e)}")
        else:
            reply_message = self.illegal_team_response.format(mention=interaction.user.mention)

            # Create the URL for the default room
            guild_id = interaction.guild.id
            default_room_url = f"https://discord.com/channels/{guild_id}/{self.default_create_room_channel_id}"
            view = DefaultRoomView(self.bot, default_room_url)

            await interaction.followup.send(reply_message, view=view)

    async def save_config(self):
        """Save the current configuration back to the JSON file."""
        config_path = Path('./bot/config/config_invitation.json')
        async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            config_data = json.loads(content)

        # Update the ignore_user_ids in the config data
        config_data['ignore_channel_ids'] = self.conf['ignore_channel_ids']

        async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(config_data, indent=2, ensure_ascii=False))

    @app_commands.command(name="invt_checkignorelist")
    async def check_ignore_list(self, interaction: discord.Interaction):
        """Check the current list of ignored channels."""
        if not await check_channel_validity(interaction):
            return

        embed = discord.Embed(
            title="Ignored Channels List",
            description="These channels are currently being ignored by the invitation system:",
            color=discord.Color.blue()
        )

        ignored_channels = []
        for channel_id in self.conf['ignore_channel_ids']:
            channel = self.bot.get_channel(channel_id)
            if channel:
                ignored_channels.append(f"• {channel.mention} (ID: {channel_id})")
            else:
                ignored_channels.append(f"• Invalid Channel (ID: {channel_id})")

        if ignored_channels:
            embed.add_field(
                name="Ignored Channels",
                value="\n".join(ignored_channels),
                inline=False
            )
        else:
            embed.add_field(
                name="Ignored Channels",
                value="No channels are currently being ignored.",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    async def format_ignore_list_embed(self, title, description):
        """Helper method to create an embed showing the current ignore list."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )

        ignored_channels = []
        for channel_id in self.conf['ignore_channel_ids']:
            channel = self.bot.get_channel(channel_id)
            if channel:
                ignored_channels.append(f"• {channel.mention} (ID: {channel_id})")
            else:
                ignored_channels.append(f"• Invalid Channel (ID: {channel_id})")

        embed.add_field(
            name="Ignored Channels",
            value="\n".join(ignored_channels) if ignored_channels else "No channels are currently being ignored.",
            inline=False
        )

        return embed

    @app_commands.command(name="invt_addignorelist")
    @app_commands.describe(channel="The channel to add to the ignore list")
    async def add_ignore_list(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Add a channel to the ignore list."""
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        try:
            if channel.id in self.conf['ignore_channel_ids']:
                await interaction.followup.send(f"Channel {channel.mention} is already in the ignore list.",
                                                ephemeral=True)
                return

            self.conf['ignore_channel_ids'].append(channel.id)
            await self.save_config()

            embed = await self.format_ignore_list_embed(
                "Channel Added to Ignore List",
                f"Successfully added {channel.mention} to the ignore list."
            )
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error adding channel to ignore list: {e}")
            await interaction.followup.send("Failed to add channel to ignore list.", ephemeral=True)

    @app_commands.command(name="invt_removeignorelist")
    @app_commands.describe(
        channel="Select channel to remove from ignore list (if channel still exists)",
        channel_id="Enter channel ID manually (if channel was deleted)"
    )
    async def remove_ignore_list(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel = None,
        channel_id: str = None
    ):
        """Remove a channel from the ignore list."""
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

        try:
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

            if target_channel_id not in self.conf['ignore_channel_ids']:
                channel_mention = target_channel.mention if target_channel else f"Channel ID: {target_channel_id} (deleted)"
                await interaction.followup.send(
                    f"Channel {channel_mention} is not in the ignore list.",
                    ephemeral=True
                )
                return

            self.conf['ignore_channel_ids'].remove(target_channel_id)
            await self.save_config()

            channel_mention = target_channel.mention if target_channel else f"Channel ID: {target_channel_id} (deleted)"
            embed = await self.format_ignore_list_embed(
                "Channel Removed from Ignore List",
                f"Successfully removed {channel_mention} from the ignore list."
            )
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error removing channel from ignore list: {e}")
            await interaction.followup.send("Failed to remove channel from ignore list.", ephemeral=True)
