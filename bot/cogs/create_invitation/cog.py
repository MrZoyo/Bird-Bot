import logging
import re

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands, tasks

from bot.utils import (
    RoleDatabaseManager,
    check_channel_validity,
    config,
    fmt_channel,
    fmt_user,
)
from bot.utils.i18n import t

from .full_message import update_invitation_message_to_full
from bot.utils.invitation_db import InvitationDatabaseManager
from bot.utils.task_helpers import wait_until_ready_or_stop

from .lifecycle import InvitationLifecycle
from .views import DefaultRoomView, InvitationFullButton, LegacyInvitationFullButton


TEAMUP_KEYWORD_PATTERN = re.compile(
    r"(?:(缺|等|[=＝]|[Qq]))"
    r"(?:(\d|[一二三四五]|[nN]|全世界|world|World))"
    r"(?!(分|分钟|min|个钟|小时))",
    re.IGNORECASE,
)
SINGLE_PERSON_COUNTS = frozenset({"1", "１", "一"})


def find_teamup_keyword_matches(content: str) -> list[re.Match[str]]:
    """Find teamup expressions using the required marker-before-count grammar."""
    if re.search(r'\d[A-Z]$', content, re.IGNORECASE):
        return []
    return list(TEAMUP_KEYWORD_PATTERN.finditer(content))


def is_single_person_waiting(
    content: str,
    matches: list[re.Match[str]],
) -> bool:
    """Return whether a matched teamup expression has a standalone one before its marker."""
    for match in matches:
        count_index = match.start() - 1
        if count_index < 0 or content[count_index] not in SINGLE_PERSON_COUNTS:
            continue

        previous_index = count_index - 1
        if previous_index < 0 or not content[previous_index].isnumeric():
            return True

    return False


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
        self.invitation_db = InvitationDatabaseManager(self.main_config['db_path'])
        self.lifecycle = InvitationLifecycle(bot, self.invitation_db, self.role_db)

        self.conf = config.get_config('invitation')
        self.illegal_team_response = t('invitation.illegal_team_response')
        self.single_person_waiting_response = t(
            'invitation.single_person_waiting_response'
        )
        self.default_invite_embed_title = t('invitation.default_invite_embed_title')
        self.default_create_room_channel_id = self.conf['default_create_room_channel_id']
        self.ignore_channel_message = t('invitation.ignore_channel_message')
        self.failed_invite_responses = t('invitation.failed_invite_responses')
        self.ignore_user_ids = self.conf['ignore_user_ids']
        self.ignore_channel_ids = self.conf['ignore_channel_ids']

    async def update_message_to_full(self, message):
        """将组队消息更新为满员状态（可复用方法）"""
        await update_invitation_message_to_full(self.bot, message)

    async def cog_load(self):
        await self.role_db.initialize_database()
        await self.invitation_db.initialize()
        self.bot.add_dynamic_items(InvitationFullButton, LegacyInvitationFullButton)
        self.reconcile_invitations.start()

    def cog_unload(self):
        self.reconcile_invitations.cancel()
        self.bot.remove_dynamic_items(InvitationFullButton, LegacyInvitationFullButton)

    @tasks.loop(minutes=1)
    async def reconcile_invitations(self):
        try:
            await self.lifecycle.reconcile()
        except Exception:
            logging.exception('Invitation reconciliation failed; retrying next cycle')

    @reconcile_invitations.before_loop
    async def before_reconcile_invitations(self):
        await wait_until_ready_or_stop(self.bot, self.reconcile_invitations, 'CreateInvitationCog.reconcile')

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if isinstance(channel, discord.VoiceChannel):
            await self.lifecycle.room_deleted(channel.id, voice_channel=channel)

    @commands.Cog.listener()
    async def on_message(self, message):
        # If the message author is the bot itself, return immediately
        if message.author == self.bot.user:
            return

        # If the message author is a bot, return immediately
        if message.author.bot:
            return

        # 检查是否满足忽略条件：仅有6个字符且不包含等号、中文字、空格，
        # 但如果包含 "flex"、"rank"、"aram" 或 "hks"（无论大小写），则不忽略。
        if (len(message.content) == 6 and
                not re.search(r"[=＝\s]", message.content) and  # Check for any equal sign or space
                not re.search(r"(?i)(flex|rank|aram|hks)", message.content) and
                not re.search(r"[\u4e00-\u9FFF]", message.content)):  # Check for any Chinese character
            # print(f"忽略的消息: {message.content}")
            return  # 忽略这条消息

        # if the message contains a URL, not process it
        if re.search(r"https?:\/\/", message.content):
            return

        # check if the user is in the ignore list
        if message.author.id in self.ignore_user_ids:
            return  # Ignore the message

        # 必须先命中“标记 + 人数”的基本组队语法，再判断标记前是否写了当前人数。
        keyword_matches = find_teamup_keyword_matches(message.content)
        valid_matches = [match.group(0) for match in keyword_matches]

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

                    await self.lifecycle.publish(message, channel)

                except Exception as e:
                    reply_message = self.failed_invite_responses + str(e)

            else:
                response_template = (
                    self.single_person_waiting_response
                    if is_single_person_waiting(message.content, keyword_matches)
                    else self.illegal_team_response
                )
                reply_message = response_template.format(mention=message.author.mention)

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

                await self.lifecycle.publish(
                    interaction, channel, title=title or self.default_invite_embed_title,
                )

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
