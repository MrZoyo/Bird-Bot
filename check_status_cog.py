# Author: MrZoyo
# Version: 0.6.0
# Date: 2024-06-10
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


class CheckStatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.illegal_act_cog = IllegalTeamActCog(bot)

        config = self.bot.get_cog('ConfigCog').config
        self.logging_file = config['logging_file']

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
