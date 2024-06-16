# Author: MrZoyo
# Version: 0.6.6
# Date: 2024-06-16
# ========================================

import discord
from discord.ext import commands
from illegal_team_act_cog import IllegalTeamActCog
import os
import tempfile


class EmbedGenerator:
    @staticmethod
    def create_people_embed(total_people, category_counts):
        embed = discord.Embed(title="Voice Channel Statistics", color=discord.Color.blue())
        for category, count in category_counts.items():
            embed.add_field(name=category, value=f"{count} people", inline=False)
        embed.add_field(name="Total People in Voice Channels", value=f"{total_people} people", inline=False)
        return embed

    @staticmethod
    def create_channel_embed(total_channels, category_counts):
        embed = discord.Embed(title="Active Voice Channel Statistics", color=discord.Color.blue())
        for category, count in category_counts.items():
            embed.add_field(name=category, value=f"{count} active channels", inline=False)
        embed.add_field(name="Total Active Channels", value=f"{total_channels} channels", inline=False)
        return embed


class MemberPositionView(discord.ui.View):
    def __init__(self, bot, url):
        super().__init__()
        self.bot = bot

        config = self.bot.get_cog('ConfigCog').config
        self.logging_file = config['logging_file']
        self.where_is_join_button_label = config['where_is_join_button_label']

        # Create a link button that directs to the user's channel
        self.add_item(discord.ui.Button(label=self.where_is_join_button_label, url=url))


class CheckStatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.illegal_act_cog = IllegalTeamActCog(bot)

        config = self.bot.get_cog('ConfigCog').config
        self.logging_file = config['logging_file']
        self.where_is_not_found_message = config['where_is_not_found_message']
        self.where_is_title_message = config['where_is_title_message']
        self.current_channel_name_message = config['current_channel_name_message']
        self.current_channel_members_message = config['current_channel_members_message']

    @discord.app_commands.command(name="check_log")
    @discord.app_commands.describe(x="Number of lines from the end of the log file to return.")
    async def check_log(self, interaction: discord.Interaction, x: int):
        """Returns the last x lines of the log file."""
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return
        try:
            with open(self.logging_file, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            await interaction.response.send_message("The log file does not exist.")
            return
        last_x_lines = ''.join(lines[-x:])
        if len(last_x_lines) > 2000:
            # If the message is too long, write it to a temporary file and send the file
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp:
                temp.write(last_x_lines.encode())
                temp_file_name = temp.name
            await interaction.response.send_message("The log is too long to display, sending as a file instead.",
                                                    file=discord.File(temp_file_name))
            os.remove(temp_file_name)  # Delete the temporary file
        else:
            await interaction.response.send_message(f"**Last {x} lines of the log file**:\n```{last_x_lines}```")

    @discord.app_commands.command(name="check_people_number")
    async def check_people_number(self, interaction: discord.Interaction):
        """Returns the number of people in each category and the total number of people in voice channels."""
        await interaction.response.defer()
        try:
            category_counts = {}
            total_people = 0
            for guild in self.bot.guilds:
                for channel in guild.voice_channels:
                    if channel.category is not None:
                        if channel.category.name not in category_counts:
                            category_counts[channel.category.name] = 0
                        category_counts[channel.category.name] += len(channel.members)
                        total_people += len(channel.members)
            # Remove categories with no active players
            category_counts = {k: v for k, v in category_counts.items() if v > 0}
            embed = EmbedGenerator.create_people_embed(total_people, category_counts)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="check_channel_number")
    async def check_channel_number(self, interaction: discord.Interaction):
        """Returns the number of active channels in each category and the total number of active channels."""
        await interaction.response.defer()
        try:
            category_counts = {}
            total_channels = 0
            for guild in self.bot.guilds:
                for channel in guild.voice_channels:
                    if channel.category is not None and len(channel.members) > 0:
                        if channel.category.name not in category_counts:
                            category_counts[channel.category.name] = 0
                        category_counts[channel.category.name] += 1
                        total_channels += 1
            embed = EmbedGenerator.create_channel_embed(total_channels, category_counts)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="where_is")
    @discord.app_commands.describe(member="The member to check the position for")
    async def check_member_position(self, interaction: discord.Interaction, member: discord.Member):
        """Returns the current channel of the member and a list of members within the channel."""
        await interaction.response.defer(ephemeral=True)
        try:
            if member.voice is None or member.voice.channel is None:
                await interaction.followup.send(self.where_is_not_found_message.format(name=member.display_name), ephemeral=True)
                return

            channel = member.voice.channel
            members_in_channel = [m.display_name for m in channel.members]

            guild_id = member.guild.id
            channel_id = member.voice.channel.id
            vc_url_direct = f"https://discord.com/channels/{guild_id}/{channel_id}"

            embed = discord.Embed(title=self.where_is_title_message.format(name=member.display_name), color=discord.Color.blue())
            embed.add_field(name=self.current_channel_name_message, value="".join(vc_url_direct), inline=False)
            embed.add_field(name=self.current_channel_members_message, value="\n".join(members_in_channel), inline=False)

            view = MemberPositionView(self.bot, vc_url_direct)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
