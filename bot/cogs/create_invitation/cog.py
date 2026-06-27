import asyncio
import logging
import re

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from bot.utils import (
    RoleDatabaseManager,
    check_channel_validity,
    config,
    fmt_channel,
    fmt_user,
)
from bot.utils.i18n import t

from .full_message import update_invitation_message_to_full
from .views import DefaultRoomView, TeamInvitationView


def log_keyword_detection(message: discord.Message, valid_matches) -> None:
    keyword_logger = logging.getLogger('keyword_detection')
    keyword_logger.info(
        '检测到用户 %s 在频道 %s 的内容: %s, 匹配项: %s!',
        fmt_user(message.author),
        fmt_channel(message.channel),
        message.content,
        valid_matches,
    )


class CreateInvitationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # user_signatures 表归 role 领域, 这里跨域只读, 复用 RoleDatabaseManager。
        self.main_config = config.get_config('main')
        self.role_db = RoleDatabaseManager(self.main_config['db_path'])

        self.conf = config.get_config('invitation')
        self.illegal_team_response = t('invitation.illegal_team_response')
        self.default_invite_embed_title = t('invitation.default_invite_embed_title')
        self.default_create_room_channel_id = self.conf['default_create_room_channel_id']
        self.ignore_channel_message = t('invitation.ignore_channel_message')
        self.failed_invite_responses = t('invitation.failed_invite_responses')
        self.ignore_user_ids = self.conf['ignore_user_ids']
        self.ignore_channel_ids = self.conf['ignore_channel_ids']

    async def update_message_to_full(self, message):
        """将组队消息更新为满员状态（可复用方法）"""
        await update_invitation_message_to_full(self.bot, message)

    async def mark_old_invitation_full(self, old_invitation):
        """异步将旧的组队消息设置为满员"""
        try:
            # 1. 获取消息
            text_channel = self.bot.get_channel(old_invitation['invitation_channel_id'])
            if not text_channel:
                logging.warning(
                    "Old invitation channel %s not found",
                    fmt_channel(old_invitation['invitation_channel_id']),
                )
                return

            try:
                old_message = await text_channel.fetch_message(old_invitation['invitation_message_id'])
            except discord.NotFound:
                logging.warning(
                    "Old invitation message %s in %s not found, already deleted",
                    old_invitation['invitation_message_id'],
                    fmt_channel(text_channel),
                )
                return
            except discord.Forbidden:
                logging.error(
                    "No permission to fetch old invitation message %s in %s",
                    old_invitation['invitation_message_id'],
                    fmt_channel(text_channel),
                )
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
            log_keyword_detection(message, valid_matches)

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
                    view = TeamInvitationView(self.bot, channel, message.author, self.role_db)
                    await view.populate_panel(message)
                    new_message = await message.reply(view=view)

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

    @app_commands.command(
        name="invt",
        description=locale_str(
            "Create an invitation to your current voice channel",
            key="invitation.invt.description",
        ),
    )
    @app_commands.describe(
        title=locale_str(
            "Optional title for the invitation.",
            key="invitation.invt.params.title",
        ),
    )
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
                view = TeamInvitationView(self.bot, channel, interaction.user, self.role_db)
                await view.populate_panel(
                    interaction,
                    title=title or self.default_invite_embed_title,
                )
                new_message = await interaction.followup.send(view=view)

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
        """Persist invitation config via the unified writer (see P2-3).

        Writes the entire ``self.conf`` snapshot back to
        ``bot/config/invitation.yaml`` through the atomic YAML writer
        (ruamel round-trip + tempfile + os.replace). The old manual
        JSON I/O path is gone; a single source of truth lives in YAML.
        """
        self.conf = await config.save_config('invitation', self.conf)
        self.ignore_user_ids = self.conf['ignore_user_ids']
        self.ignore_channel_ids = self.conf['ignore_channel_ids']

    @app_commands.command(
        name="invt_checkignorelist",
        description=locale_str(
            "Check the current list of ignored channels",
            key="invitation.invt_checkignorelist.description",
        ),
    )
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

    @app_commands.command(
        name="invt_addignorelist",
        description=locale_str(
            "Add a channel to the invitation ignore list",
            key="invitation.invt_addignorelist.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "The channel to add to the ignore list",
            key="invitation.invt_addignorelist.params.channel",
        ),
    )
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

    @app_commands.command(
        name="invt_removeignorelist",
        description=locale_str(
            "Remove a channel from the invitation ignore list",
            key="invitation.invt_removeignorelist.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "Select channel to remove from ignore list (if channel still exists)",
            key="invitation.invt_removeignorelist.params.channel",
        ),
        channel_id=locale_str(
            "Enter channel ID manually (if channel was deleted)",
            key="invitation.invt_removeignorelist.params.channel_id",
        ),
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
