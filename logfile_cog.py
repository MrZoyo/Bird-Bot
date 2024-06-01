import discord
from discord.ext import commands
from illegal_team_act_cog import IllegalTeamActCog

LOGGING_FILE = 'bot.log'


class LogFileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.illegal_act_cog = IllegalTeamActCog(bot)

    @discord.app_commands.command(name="check_log")
    @discord.app_commands.describe(x="Number of lines from the end of the log file to return.")
    async def check_log(self, interaction: discord.Interaction, x: int):
        """Returns the last x lines of the log file."""
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return
        try:
            with open(LOGGING_FILE, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            await interaction.response.send_message("The log file does not exist.")
            return
        last_x_lines = lines[-x:]
        await interaction.response.send_message(f"**Last {x} lines of the log file**:\n```{''.join(last_x_lines)}```")
