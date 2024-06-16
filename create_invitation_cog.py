# Author: MrZoyo
# Version: 0.6.3
# Date: 2024-06-13
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


class CreateInvitationCog(commands.Cog):
    def __init__(self, bot, illegal_act_cog):
        self.bot = bot
        self.illegal_act_cog = illegal_act_cog
        self.config = self.bot.get_cog('ConfigCog').config
        self.illegal_team_response = self.config['illegal_team_response']
        self.default_invite_embed_title = self.config['default_invite_embed_title']

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

        # check if the message meets the ignore conditions: only 6 characters and does not contain an equal sign,
        # Chinese characters, or spaces,
        # but if it contains "flex" or "rank" or "aram" (regardless of case), it should not be ignored.
        if (len(message.content) == 6 and
                not re.search(r"[=＝\s]", message.content) and  # Check for any equal sign or space
                not re.search(r"(?i)(flex|rank|aram)", message.content) and
                not re.search(r"[\u4e00-\u9FFF]", message.content)):  # Check for any Chinese character
            return  # Ignore this message

        # If the message contains a link, do not reply
        if re.search(r"https?:\/\/", message.content):
            return

        # Check if the message sender is in the list of users who should not be replied to
        if message.author.id in IGNORE_USER_IDS:
            return  # If in the list, do not process this message

        # 前缀：匹配"缺"、"等"、"="、"＝"、"q"、"Q"。
        # 主体：匹配数字、"一"到"五"的汉字、"n"、"N"、"全世界"、"W/world"。
        # 排除：不应该后跟"分"、"分钟"、"min"、"个钟"、"小时"。
        pattern = r"(?:(缺|等|[=＝]|[Qq]))(?:(\d|[一二三四五]|[nN]|全世界|world|World))(?!(分|分钟|min|个钟|小时))"

        # find all matching content
        matches = re.findall(pattern, message.content, re.IGNORECASE)
        # filter out valid matches, excluding cases where a number is followed by a letter
        valid_matches = [match for match in matches if not re.search(r'\d[A-Z]$', message.content, re.IGNORECASE)]

        # Define a default value for reply_message
        reply_message = ""

        if valid_matches:
            logging.info(f'Detected content from {message.author}: {message.content}, match items: {valid_matches}!')

            # check if the user is in a voice channel
            if message.author.voice and message.author.voice.channel:
                # remove the user's illegal team behavior within 5 minutes
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
                # log the illegal behavior
                await self.illegal_act_cog.log_illegal_activity(str(message.author.id), message.content)
                reply_message = self.illegal_team_response.format(mention=message.author.mention)

            # Only reply if reply_message is not empty
            if reply_message:
                await message.reply(reply_message)
            # Ends after replying to the first match, ensuring that don't repeatedly
            # reply to the same message with multiple matches
            return

    @app_commands.command(name="invitation")
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
                await interaction.followup.send(embed=embed, view=view)
            except Exception as e:
                await interaction.followup.send(f"Failed to create an invitation: {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send(self.illegal_team_response.format(mention=interaction.user.mention),
                                                    ephemeral=True)
