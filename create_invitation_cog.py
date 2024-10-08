# Author: MrZoyo
# Version: 0.8.0
# Date: 2024-09-01
# ========================================
import discord
from discord.ext import commands
from discord import app_commands
import re
import logging
import datetime
from discord.utils import format_dt


class TeamInvitationView(discord.ui.View):
    def __init__(self, bot, url, user):
        super().__init__(timeout=600)
        self.bot = bot
        self.user = user
        self.url = url

        self.config = self.bot.get_cog('ConfigCog').config
        self.roomfull_button_label = self.config['roomfull_button_label']
        self.invite_button_label = self.config['invite_button_label']
        self.invite_embed_content = self.config['invite_embed_content']
        self.invite_embed_footer = self.config['invite_embed_footer']
        self.interaction_target_error_message = self.config['interaction_target_error_message']
        self.roomfull_title = self.config['roomfull_title']
        self.invite_embed_content_edited = self.config['invite_embed_content_edited']
        self.roomfull_set_message = self.config['roomfull_set_message']
        self.not_in_vc_message = self.config['not_in_vc_message']
        self.extract_channel_id_error = self.config['extract_channel_id_error']

        # Adding the join room button
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=self.invite_button_label, url=self.url))

        # Adding the room full button
        self.room_full_button = discord.ui.Button(style=discord.ButtonStyle.danger, label=self.roomfull_button_label,
                                                  custom_id="room_full_button")
        self.room_full_button.callback = self.room_full_button_callback
        self.add_item(self.room_full_button)

    def create_embed(self, obj):
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

        guild_id = author.guild.id
        channel_id = author.voice.channel.id
        vc_url_direct = f"https://discord.com/channels/{guild_id}/{channel_id}"

        # Remove parts of the message that match the pattern <@digits> (for member mentions)
        content = re.sub(r'<@\d+>', '', content)

        # Remove parts of the message that match the pattern <@&digits> (for role mentions)
        content = re.sub(r'<@&\d+>', '', content)

        # Truncate the content to 240 characters if longer
        if len(content) > 256:
            content = content[:253] + "..."
        embed = discord.Embed(
            title=content,
            description=self.invite_embed_content.format(vc_url=vc_url_direct, mention=author.mention,
                                                         time=elapsed_time),
            color=discord.Color.blue()
        )

        # Check if the author has an avatar
        if author.avatar:
            embed.set_thumbnail(url=author.avatar.url)
        # If the author doesn't have an avatar, check if the bot has an avatar
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        embed.timestamp = current_time  # Set the timestamp to the message time

        # Add the original time to the footer
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
        if match:
            original_channel_id = int(match.group(1))
        else:
            await interaction.followup.send(self.extract_channel_id_error, ephemeral=True)
            return

        # Check if the user is still in the original voice channel
        if not self.user.voice or self.user.voice.channel.id != original_channel_id:
            await interaction.followup.send(self.not_in_vc_message, ephemeral=True)
            return

        # Update the embed title and description to reflect the room is full
        embed = interaction.message.embeds[0]
        embed.title = f"{self.roomfull_title} ~~{embed.title}~~"
        embed.description = self.invite_embed_content_edited.format(name=self.user.voice.channel.name,
                                                                    url=self.url,
                                                                    mention=self.user.mention,
                                                                    time=embed.description.split('\n\n')[-1]
                                                                    )
        embed.color = discord.Color.red()

        # Disable the "Join Room" button
        self.children[0].disabled = True  # Assuming the first button is the join button
        # Disable the "Room Full" button itself
        self.room_full_button.disabled = True

        # Update the message with the disabled buttons
        await interaction.edit_original_response(embed=embed, view=self)

        # Send a follow-up message to confirm the room is now full
        await interaction.followup.send(self.roomfull_set_message, ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.user


class DefaultRoomView(discord.ui.View):
    def __init__(self, bot, url):
        super().__init__(timeout=600)
        self.bot = bot
        self.url = url
        self.config = self.bot.get_cog('ConfigCog').config
        self.default_create_room_channel_id = self.config['default_create_room_channel_id']
        self.default_create_room_button = self.config['default_create_room_button']

        self.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=self.default_create_room_button, url=self.url))


class CreateInvitationCog(commands.Cog):
    def __init__(self, bot, illegal_act_cog):
        self.bot = bot
        self.illegal_act_cog = illegal_act_cog
        self.config = self.bot.get_cog('ConfigCog').config
        self.illegal_team_response = self.config['illegal_team_response']
        self.default_invite_embed_title = self.config['default_invite_embed_title']
        self.default_create_room_channel_id = self.config['default_create_room_channel_id']

    @commands.Cog.listener()
    async def on_message(self, message):
        # Use the config values
        IGNORE_USER_IDS = self.config['ignore_user_ids']
        FAILED_INVITE_RESPONSES = self.config['failed_invite_responses']

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
        if message.author.id in IGNORE_USER_IDS:
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
            logging.info(f'检测到 {message.author} 的内容: {message.content}, 匹配项: {valid_matches}!')

            # Check if the author is in a voice channel
            if message.author.voice and message.author.voice.channel:
                # Remove illegal teaming behaviour from users for 5 minutes
                await self.illegal_act_cog.remove_illegal_activity(str(message.author.id))
                try:
                    invite = await message.author.voice.channel.create_invite(max_age=600)
                    vc_url = invite.url  # Get the URL from the Invite object
                    view = TeamInvitationView(self.bot, vc_url, message.author)
                    embed = view.create_embed(message)
                    await message.reply(embed=embed, view=view)
                except Exception as e:
                    reply_message = FAILED_INVITE_RESPONSES + str(e)

            else:
                # Log the illegal teaming activity
                await self.illegal_act_cog.log_illegal_activity(str(message.author.id), message.content)
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
                invite = await interaction.user.voice.channel.create_invite(max_age=600)
                vc_url = invite.url  # Get the URL from the Invite object
                view = TeamInvitationView(self.bot, vc_url, interaction.user)
                embed = view.create_embed(interaction)
                embed.title = title or self.default_invite_embed_title
                # Truncate the content to 256 characters if longer
                if len(embed.title) > 256:
                    embed.title = embed.title[:253] + "..."
                await interaction.followup.send(embed=embed, view=view)
            except Exception as e:
                await interaction.followup.send(f"Failed to create an invitation: {str(e)}", ephemeral=True)
        else:
            reply_message = self.illegal_team_response.format(mention=interaction.user.mention)

            # Create the URL for the default room
            guild_id = interaction.guild.id
            default_room_url = f"https://discord.com/channels/{guild_id}/{self.default_create_room_channel_id}"
            view = DefaultRoomView(self.bot, default_room_url)

            await interaction.followup.send(reply_message, view=view, ephemeral=True)
