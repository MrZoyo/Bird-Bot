# bot/cogs/welcome_cog.py
import io
import os
import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
import logging
import aiohttp
from pathlib import Path

from bot.utils import config, check_channel_validity


class WelcomeDMView(discord.ui.View):
    def __init__(self, member_count):
        super().__init__(timeout=None)  # No timeout for this button

        self.conf = config.get_config('welcome')

        # Add the member count button
        button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            label=self.conf.get('member_count_button').format(member_count=member_count) if self.conf.get('member_count_button') else f"你是小鸟的第 {member_count} 名成员",
            disabled=True  # Make it non-clickable
        )
        self.add_item(button)


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

        # Get the config from the ConfigCog
        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']

        self.conf = config.get_config('welcome')
        # Set the parameters from the config
        self.welcome_channel_id = self.conf['welcome_channel_id']
        self.text_color = tuple(self.conf['text_color'])

        self.font_size = self.conf['font_size']
        self.avatar_size = tuple(self.conf['avatar_size'])
        self.welcome_text_1_distance = self.conf['welcome_text_1_distance']
        self.welcome_text_2_distance = self.conf['welcome_text_2_distance']
        self.welcome_text_picture_1 = self.conf['welcome_text_picture_1']
        self.welcome_text_picture_2 = self.conf['welcome_text_picture_2']
        self.welcome_text = self.conf['welcome_text']

        self.base_path = Path(__file__).parent.parent.parent
        self.font_path = str(self.base_path / "resources" / "fonts" / Path(self.conf['font_path']).name)
        self.background_image = str(self.base_path / "resources" / "images" / Path(self.conf['background_image']).name)

        # Add new config parameters for DM welcome message
        self.dm_config = self.conf.get('dm', {})
        self.welcome_dm_image = str(self.base_path / "resources" / "images" / Path(self.dm_config.get('dm_image', "welcome_dm.png")).name)

        # Verify resources exist
        self._verify_resources()

    def _verify_resources(self):
        """Verify that required resource files exist"""
        if not os.path.exists(self.font_path):
            raise FileNotFoundError(f"Font file not found at {self.font_path}")
        if not os.path.exists(self.background_image):
            raise FileNotFoundError(f"Background image not found at {self.background_image}")
        logging.info(f"Resources verified - Font: {self.font_path}, Background: {self.background_image}")

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

        # Send the welcome DM
        await self.send_welcome_dm(member)

    @app_commands.command(name="testwelcome")
    @app_commands.describe(member="Select a member to test the welcome message.")
    @app_commands.describe(member_number="Customize the 'xth member of the server' message.")
    async def test_welcome(self, interaction: discord.Interaction, member: discord.Member = None,
                           member_number: int = None):
        """Send a test welcome message using the slash command interface."""
        if interaction.channel_id != self.welcome_channel_id and not await check_channel_validity(interaction):
            await interaction.response.send_message("This command can only be used in the welcome channel or admin channel.",
                                                    ephemeral=True)
            return

        member = member or interaction.user
        member_number = member_number or member.guild.member_count  # Use the provided member number or the actual member count

        # Call send_welcome and edit the original response with the result
        await self.send_welcome(member, interaction.channel, member_number, interaction)

        # Only send DM if:
        # 1. Member is the command user themselves, or
        # 2. Command is used in admin channel
        if member == interaction.user or await check_channel_validity(interaction):
            await self.send_welcome_dm(member)
            logging.info(f"Test welcome message and DM sent to {member}")
        else:
            logging.info(f"Test welcome message sent to {member} (DM skipped - not admin channel)")

        await interaction.followup.send(
            f"Test welcome message {'and DM ' if member == interaction.user or await check_channel_validity(interaction) else ''}sent for {member.mention}",
            ephemeral=True
        )

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

    async def send_welcome_dm(self, member):
        """Send a welcome DM to the new member"""
        try:
            # Create the embed
            embed = discord.Embed(
                description="",
                color=discord.Color.from_rgb(*self.dm_config.get('color', [107, 104, 180]))
            )

            # Set author with member's avatar
            embed.set_author(
                name=self.dm_config.get('description0_title'),
                icon_url=member.display_avatar.url
            )

            # Add the first description
            embed.add_field(
                name=self.dm_config.get('description1_title'),
                value="\n".join(line.format(user=member.mention) for line in self.dm_config.get('description1', [])),
                inline=False
            )

            # Add the second description
            embed.add_field(
                name=self.dm_config.get('description2_title'),
                value="\n".join(self.dm_config.get('description2', [])),
                inline=False
            )

            # Set the bot's avatar as the thumbnail
            if self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)

            # Add the rules text and channel mention
            rules_channel = member.guild.get_channel(int(self.dm_config.get('rules_channel_id')))
            if rules_channel:
                embed.add_field(
                    name=self.dm_config.get('rules', {}).get('rules_title'),
                    value=f"{self.dm_config.get('rules', {}).get('rules_text')}\n{rules_channel.mention}",
                    inline=False
                )

            # Set footer with bot avatar
            if self.bot.user.avatar:
                embed.set_footer(
                    text=self.dm_config.get('footer'),
                    icon_url=self.bot.user.avatar.url
                )

            # Create view with member count button
            view = WelcomeDMView(member.guild.member_count)

            # Attach the welcome image if it exists
            if os.path.exists(self.welcome_dm_image):
                file = discord.File(self.welcome_dm_image, filename="welcome_image.png")
                embed.set_image(url="attachment://welcome_image.png")
                await member.send(embed=embed, file=file, view=view)
            else:
                await member.send(embed=embed, view=view)

        except discord.Forbidden:
            logging.warning(f"Could not send welcome DM to {member.name} - DMs are closed")
        except Exception as e:
            logging.error(f"Error sending welcome DM to {member.name}: {str(e)}")
