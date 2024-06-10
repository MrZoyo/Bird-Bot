# Author: MrZoyo
# Version: 0.6.0
# Date: 2024-06-10
# ========================================
import discord
from discord.ext import commands
import re
import logging


class CreateInvitationCog(commands.Cog):
    def __init__(self, bot, illegal_act_cog):
        self.bot = bot
        self.illegal_act_cog = illegal_act_cog
        self.config = self.bot.get_cog('ConfigCog').config

    @commands.Cog.listener()
    async def on_message(self, message):
        # Use the config values
        IGNORE_USER_IDS = self.config['ignore_user_ids']
        ILLEGAL_TEAM_RESPONSE = self.config['illegal_team_response']
        FAILED_INVITE_RESPONSES = self.config['failed_invite_responses']

        # avoid the bot replying to its own messages
        if message.author == self.bot.user:
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

        if valid_matches:
            logging.info(f'Detected content from {message.author}: {message.content}, match items: {valid_matches}!')

            # check if the user is in a voice channel
            if message.author.voice and message.author.voice.channel:
                # remove the user's illegal team behavior within 5 minutes
                await self.illegal_act_cog.remove_illegal_activity(str(message.author.id))
                try:
                    vc_url = await message.author.voice.channel.create_invite(max_age=600)
                    reply_message = f"{vc_url}"
                except Exception as e:
                    reply_message = FAILED_INVITE_RESPONSES

            else:
                # log the illegal behavior
                await self.illegal_act_cog.log_illegal_activity(str(message.author.id), message.content)
                reply_message = ILLEGAL_TEAM_RESPONSE.format(mention=message.author.mention)

            await message.reply(reply_message)
            # Ends after replying to the first match, ensuring that don't repeatedly
            # reply to the same message with multiple matches
            return
