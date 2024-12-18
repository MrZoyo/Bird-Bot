# bot/cogs/create_invitation_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import re
import logging
import datetime
import json
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
        self.roomfull_title = self.conf['roomfull_title']
        self.invite_embed_content_edited = self.conf['invite_embed_content_edited']
        self.roomfull_set_message = self.conf['roomfull_set_message']
        self.not_in_vc_message = self.conf['not_in_vc_message']
        self.extract_channel_id_error = self.conf['extract_channel_id_error']

        # Adding the join room button
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=self.invite_button_label, url=self.url))

        # Adding the room full button
        self.room_full_button = discord.ui.Button(style=discord.ButtonStyle.danger, label=self.roomfull_button_label,
                                                  custom_id="room_full_button")
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
        # Defer the response
        await interaction.response.defer()

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

        # Get user's signature if exists
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'SELECT signature, is_disabled FROM user_signatures WHERE user_id = ?',
                (self.user.id,)
            )
            result = await cursor.fetchone()
            signature = result[0] if result and not result[1] else None

        # Create new embed
        new_embed = discord.Embed(
            title=f"{self.roomfull_title} ~~{embed.title}~~",
            color=discord.Color.red()
        )

        # Get original timestamp
        original_timestamp = embed.timestamp

        # Build new description
        new_embed.description = self.invite_embed_content_edited.format(
            name=self.user.voice.channel.name,
            url=self.url,
            mention=self.user.mention,
            time=discord.utils.format_dt(original_timestamp, style='R')
        )

        # Add signature field if exists
        if signature:
            new_embed.add_field(name="", value=signature, inline=False)

        # Keep original thumbnail
        if embed.thumbnail:
            new_embed.set_thumbnail(url=embed.thumbnail.url)

        # Keep original footer and timestamp
        if embed.footer:
            new_embed.set_footer(text=embed.footer.text)
        new_embed.timestamp = original_timestamp

        # 禁用所有按钮
        self.children[0].disabled = True  # Join Room button
        self.room_full_button.disabled = True

        # 更新消息
        await interaction.message.edit(embed=new_embed, view=self)
        await interaction.followup.send(self.roomfull_set_message, ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.user


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

            logging.info(f'检测到 {message.author} 的内容: {message.content}, 匹配项: {valid_matches}!')

            # Check if the author is in a voice channel
            if message.author.voice and message.author.voice.channel:
                try:
                    channel = message.author.voice.channel
                    view = TeamInvitationView(self.bot, channel, message.author)
                    embed = await view.create_embed(message)
                    await message.reply(embed=embed, view=view)
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
                view = TeamInvitationView(self.bot, channel, interaction.user)
                embed = await view.create_embed(interaction)
                embed.title = title or self.default_invite_embed_title
                # Truncate the content to 256 characters if longer
                if len(embed.title) > 256:
                    embed.title = embed.title[:253] + "..."
                await interaction.followup.send(embed=embed, view=view)
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
    @app_commands.describe(channel_id="The ID of the channel to add to the ignore list")
    async def add_ignore_list(self, interaction: discord.Interaction, channel_id: str):
        """Add a channel to the ignore list."""
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        try:
            channel_id = int(channel_id)
            channel = self.bot.get_channel(channel_id)

            if not channel:
                await interaction.followup.send("Invalid channel ID.", ephemeral=True)
                return

            if channel_id in self.conf['ignore_channel_ids']:
                await interaction.followup.send(f"Channel {channel.mention} is already in the ignore list.",
                                                ephemeral=True)
                return

            self.conf['ignore_channel_ids'].append(channel_id)
            await self.save_config()

            embed = await self.format_ignore_list_embed(
                "Channel Added to Ignore List",
                f"Successfully added {channel.mention} to the ignore list."
            )
            await interaction.followup.send(embed=embed)

        except ValueError:
            await interaction.followup.send("Invalid channel ID format.", ephemeral=True)

    @app_commands.command(name="invt_removeignorelist")
    @app_commands.describe(channel_id="The ID of the channel to remove from the ignore list")
    async def remove_ignore_list(self, interaction: discord.Interaction, channel_id: str):
        """Remove a channel from the ignore list."""
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        try:
            channel_id = int(channel_id)
            channel = self.bot.get_channel(channel_id)

            if channel_id not in self.conf['ignore_channel_ids']:
                await interaction.followup.send(
                    f"Channel {channel.mention if channel else f'ID: {channel_id}'} is not in the ignore list.",
                    ephemeral=True
                )
                return

            self.conf['ignore_channel_ids'].remove(channel_id)
            await self.save_config()

            embed = await self.format_ignore_list_embed(
                "Channel Removed from Ignore List",
                f"Successfully removed {channel.mention if channel else f'ID: {channel_id}'} from the ignore list."
            )
            await interaction.followup.send(embed=embed)

        except ValueError:
            await interaction.followup.send("Invalid channel ID format. Please provide a valid number.", ephemeral=True)
