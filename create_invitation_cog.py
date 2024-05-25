import discord
from discord.ext import commands
import re
import logging

# List of user IDs that the bot will ignore
IGNORE_USER_IDS = [1020063451613241534, 1145141919810]


class CreateInvitationCog(commands.Cog):
    def __init__(self, bot, illegal_act_cog):
        self.bot = bot
        self.illegal_act_cog = illegal_act_cog

    @commands.Cog.listener()
    async def on_message(self, message):
        # Avoid the bot responding to its own messages
        if message.author == self.bot.user:
            return

        # Check for a message that only has 6 characters and does not contain certain patterns
        # However, if it contains "flex" or "rank" (in either case), it is not ignored.
        if (len(message.content) == 6 and
                not re.search(r"[=＝一二三四五\s]", message.content) and
                not re.search(r"(?i)(flex|rank)", message.content)):
            # print(f"Ignore message: {message.content}")
            return  # Ignore the message

        # Check if the message contains a URL
        if re.search(r"https?:\/\/", message.content):
            return

        # Ignore messages from specific users
        if message.author.id in IGNORE_USER_IDS:
            return

        # Prefix:  match "缺"|"等"|"="|"＝"|"q"|"Q"
        # Subject: match numbers|"一" to "五" Chinese characters|"n""N"|"全世界"|"Wworld"
        # Exclude: not followed by"分"|"分钟"|"min"|"个钟"|"小时"
        pattern = r"(?:(缺|等|[=＝]|[Qq]))(?:(\d|[一二三四五]|[nN]|全世界|world|World))(?!(分|分钟|min|个钟|小时))"

        # Find all matches in the content
        matches = re.findall(pattern, message.content, re.IGNORECASE)

        # Filter valid matches
        valid_matches = [match for match in matches if not re.search(r'\d[A-Z]$', message.content, re.IGNORECASE)]

        if valid_matches:
            logging.info(f'Detected content from {message.author}: {message.content}, Matches: {valid_matches}!')

            # Check if the user is in a voice channel
            if message.author.voice and message.author.voice.channel:
                # Remove illegal teaming behaviour by users
                self.illegal_act_cog.remove_illegal_activity(str(message.author.id))
                try:
                    vc_url = await message.author.voice.channel.create_invite(max_age=600)
                    reply_message = f"{vc_url}"
                except Exception as e:
                    reply_message = "Error creating invite link, please check my permissions."

            else:
                # Recording of illegal teaming behaviour by users
                self.illegal_act_cog.log_illegal_activity(str(message.author.id), message.content)
                reply_message = f'{message.author.mention}, it is forbidden to teaming privately, please request a ' \
                                f'voice channel! '

            await message.reply(reply_message)
            # Ends after the first match is replied to, ensuring that the same message is not replied to repeatedly
            return
