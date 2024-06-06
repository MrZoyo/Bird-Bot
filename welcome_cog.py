import io
import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
import logging
import aiohttp

# The bot will send a welcome message to this channel
WELCOME_CHANNEL_ID = 114514114514114514
# Checks for illegal teaming are only allowed in certain channels.
CHECK_ILLEGAL_TEAMING_CHANNEL_ID = 1220876330913234944
# Background image for the welcome picture
BACKGROUND_IMAGE = "background.png"
# Text color for the welcome picture
TEXT_COLOR = (255, 255, 255)  # RGB
# Font path for the welcome picture
FONT_PATH = "simhei.ttf"
# Font size for the welcome picture
FONT_SIZE = 60
# Avatar size for the welcome picture
AVATAR_SIZE = (250, 250)
# Distance between the first line of text and the avatar
WELCOME_TEXT_1_DISTANCE = 20
# Distance between the second line of text and the first line of text
WELCOME_TEXT_2_DISTANCE = 5
# Text for the welcome message
WELCOME_TEXT = "Welcome to the server, {member.mention}! Have a great time here."
# Text for the welcome picture
WELCOME_TEXT_PICTURE_1 = "Welcome {user_name} to this server！"
WELCOME_TEXT_PICTURE_2 = "You are the No.{member_number} member!"


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        await self.session.close()

    async def download_avatar(self, url):
        async with self.session.get(url) as response:
            avatar_bytes = await response.read()
        return avatar_bytes

    def create_welcome_image(self, user_name, member_number, avatar_bytes):
        with Image.open(BACKGROUND_IMAGE) as background:
            background = background.convert("RGBA")

            # Convert byte data to image
            avatar_image = Image.open(io.BytesIO(avatar_bytes))
            avatar_image = avatar_image.resize(AVATAR_SIZE)

            # Create avatar mask for circular avatar
            mask = Image.new('L', AVATAR_SIZE, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0) + AVATAR_SIZE, fill=255)

            # Calculate position for the avatar (middle, a bit towards the top)
            bg_width, bg_height = background.size
            avatar_position = ((bg_width - AVATAR_SIZE[0]) // 2, (bg_height - AVATAR_SIZE[1]) // 3)
            background.paste(avatar_image, avatar_position, mask)  # Use the mask here

            # Creating a draw object to draw text on a background image
            draw = ImageDraw.Draw(background)
            font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

            # First line of text
            text1 = WELCOME_TEXT_PICTURE_1.format(user_name=user_name)
            text1_width = draw.textlength(text1, font=font)
            text1_height = FONT_SIZE  # Assuming single line, this might need adjustment

            # Second line of text
            text2 = WELCOME_TEXT_PICTURE_2.format(member_number=member_number)
            text2_width = draw.textlength(text2, font=font)

            # Position for the first line of text, placed below the avatar with some space
            text1_x = (background.width - text1_width) // 2
            text1_y = avatar_position[1] + AVATAR_SIZE[1] + WELCOME_TEXT_1_DISTANCE  # pixels below the avatar

            # Position for the second line of text, placed below the first line
            text2_x = (background.width - text2_width) // 2
            text2_y = text1_y + text1_height + WELCOME_TEXT_2_DISTANCE  # pixels space between lines

            # Drawing the text
            draw.text((text1_x, text1_y), text1, fill=TEXT_COLOR, font=font)
            draw.text((text2_x, text2_y), text2, fill=TEXT_COLOR, font=font)

            # Convert to bytes
            final_buffer = io.BytesIO()
            background.save(final_buffer, "PNG")
            final_buffer.seek(0)

        return final_buffer

    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel = self.bot.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            # Get the member count for the welcome message
            member_count = member.guild.member_count
            avatar_bytes = await self.download_avatar(member.display_avatar.url)
            welcome_image = self.create_welcome_image(member.name, member_count, avatar_bytes)
            discord_file = discord.File(fp=welcome_image, filename='welcome_image.png')
            # Send the welcome message with text and the welcome image
            welcome_message = WELCOME_TEXT.format(member=member)
            await channel.send(content=welcome_message.format(member=member), file=discord_file)

    @commands.command(name='testwelcome')
    async def test_welcome_command(self, ctx):
        """Send a test welcome message using the command interface."""
        if ctx.channel.id == WELCOME_CHANNEL_ID:
            member_number = len(ctx.guild.members)  # Get the number of members in the guild
            await self.send_welcome(ctx.author, ctx.channel, member_number)
        else:
            await ctx.send("Please use this command in the 'welcome' channel.")

    @app_commands.command(name="testwelcome")
    @app_commands.describe(member="Select a member to test the welcome message.")
    @app_commands.describe(member_number="Customize the 'xth member of the server' message.")
    async def test_welcome(self, interaction: discord.Interaction, member: discord.Member = None,
                           member_number: int = None):
        """Send a test welcome message using the slash command interface."""
        if interaction.channel_id != WELCOME_CHANNEL_ID:
            await interaction.response.send_message("This command can only be used in the welcome channel.",
                                                    ephemeral=True)
            return

        member = member or interaction.user
        member_number = member_number or member.guild.member_count  # Use the provided member number or the actual member count

        # Call send_welcome and edit the original response with the result
        await self.send_welcome(member, interaction.channel, member_number, interaction)

        logging.info(f"Test welcome message sent to {member}")

    async def send_welcome(self, member, channel, member_number, interaction=None):
        """A unified method to send a welcome message to a member."""
        if not isinstance(channel, discord.TextChannel):
            # Ensures we're sending in a text channel
            return

        avatar_bytes = await self.download_avatar(member.display_avatar.url)
        welcome_image = self.create_welcome_image(member.display_name, member_number, avatar_bytes)
        discord_file = discord.File(fp=welcome_image, filename='welcome_image.png')
        welcome_message = WELCOME_TEXT.format(member=member)

        if interaction:
            # First, defer the response without any content
            await interaction.response.defer(ephemeral=True)
            # Then send a followup message with the content and the file
            await interaction.followup.send(content=welcome_message, files=[discord_file])
        else:
            # Regular send for non-slash command contexts
            await channel.send(content=welcome_message, file=discord_file)