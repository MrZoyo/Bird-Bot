# Author: MrZoyo
# Version: 0.6.0
# Date: 2024-06-10
# ========================================
import io
import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
import logging
import aiohttp


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

        # Get the config from the ConfigCog
        config = self.bot.get_cog('ConfigCog').config

        # Set the parameters from the config
        self.welcome_channel_id = config['welcome_channel_id']
        self.text_color = tuple(config['text_color'])
        self.font_path = config['font_path']
        self.font_size = config['font_size']
        self.avatar_size = tuple(config['avatar_size'])
        self.welcome_text_1_distance = config['welcome_text_1_distance']
        self.welcome_text_2_distance = config['welcome_text_2_distance']
        self.welcome_text_picture_1 = config['welcome_text_picture_1']
        self.welcome_text_picture_2 = config['welcome_text_picture_2']
        self.welcome_text = config['welcome_text']
        self.background_image = config['background_image']

    async def cog_unload(self):
        await self.session.close()

    async def download_avatar(self, url):
        async with self.session.get(url) as response:
            avatar_bytes = await response.read()
        return avatar_bytes

    def create_welcome_image(self, user_name, member_number, avatar_bytes):
        with Image.open(self.background_image) as background:
            background = background.convert("RGBA")

            # Convert byte data to image
            avatar_image = Image.open(io.BytesIO(avatar_bytes))
            avatar_image = avatar_image.resize(self.avatar_size)

            # Create avatar mask for circular avatar
            mask = Image.new('L', self.avatar_size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0) + self.avatar_size, fill=255)

            # Calculate position for the avatar (middle, a bit towards the top)
            bg_width, bg_height = background.size
            avatar_position = ((bg_width - self.avatar_size[0]) // 2, (bg_height - self.avatar_size[1]) // 3)
            background.paste(avatar_image, avatar_position, mask)  # Use the mask here

            # Creating a draw object to draw text on a background image
            draw = ImageDraw.Draw(background)
            font = ImageFont.truetype(self.font_path, self.font_size)

            # First line of text
            text1 = self.welcome_text_picture_1.format(user_name=user_name)
            text1_width = draw.textlength(text1, font=font)
            text1_height = self.font_size  # Assuming single line, this might need adjustment

            # Second line of text
            text2 = self.welcome_text_picture_2.format(member_number=member_number)
            text2_width = draw.textlength(text2, font=font)

            # Position for the first line of text, placed below the avatar with some space
            text1_x = (background.width - text1_width) // 2
            text1_y = avatar_position[1] + self.avatar_size[1] + self.welcome_text_1_distance  # pixels below the avatar

            # Position for the second line of text, placed below the first line
            text2_x = (background.width - text2_width) // 2
            text2_y = text1_y + text1_height + self.welcome_text_2_distance  # pixels space between lines

            # Drawing the text
            draw.text((text1_x, text1_y), text1, fill=self.text_color, font=font)
            draw.text((text2_x, text2_y), text2, fill=self.text_color, font=font)

            # Convert to bytes
            final_buffer = io.BytesIO()
            background.save(final_buffer, "PNG")
            final_buffer.seek(0)

        return final_buffer

    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel = self.bot.get_channel(self.welcome_channel_id)
        if channel:
            # Get the member count for the welcome message
            member_count = member.guild.member_count
            avatar_bytes = await self.download_avatar(member.display_avatar.url)
            welcome_image = self.create_welcome_image(member.name, member_count, avatar_bytes)
            discord_file = discord.File(fp=welcome_image, filename='welcome_image.png')
            # Send the welcome message with text and the welcome image
            welcome_message = self.welcome_text.format(member=member)
            await channel.send(content=welcome_message.format(member=member), file=discord_file)

    @commands.command(name='testwelcome')
    async def test_welcome_command(self, ctx):
        """Send a test welcome message using the command interface."""
        if ctx.channel.id == self.welcome_channel_id:
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
        if interaction.channel_id != self.welcome_channel_id:
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
        welcome_message = self.welcome_text.format(member=member)

        if interaction:
            # First, defer the response without any content
            await interaction.response.defer(ephemeral=True)
            # Then send a followup message with the content and the file
            await interaction.followup.send(content=welcome_message, files=[discord_file])
        else:
            # Regular send for non-slash command contexts
            await channel.send(content=welcome_message, file=discord_file)

