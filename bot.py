# Author: MrZoyo
# Version: 0.6.0
# Date: 2024-06-10
# ========================================
import discord
from discord.ext import commands
import logging

from config_cog import ConfigCog
from check_status_cog import CheckStatusCog
from voice_channel_cog import VoiceStateCog
from welcome_cog import WelcomeCog
from illegal_team_act_cog import IllegalTeamActCog
from create_invitation_cog import CreateInvitationCog
from dnd_cog import DnDCog
from achievement_cog import AchievementCog

intents = discord.Intents.all()
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Call the function to get the configuration
config_cog = ConfigCog(bot)
config = config_cog.read_config('config.json')

# Then replace the hardcoded values with the values from the configuration
TOKEN = config['token']
LOGGING_FILE = config['logging_file']

# Configure the logging system
logging.basicConfig(level=logging.INFO, filename=LOGGING_FILE, filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')


@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user.name}')
    for guild in bot.guilds:
        logging.info(f"\nBot connected to server {guild.name}\n")
        print(f"\nBot connected to server {guild.name}\n")
        await bot.change_presence(activity=discord.Game(name=f"Working in {guild.name}"))

    await bot.tree.sync()
    print("Commands Synced.")


@bot.command()
async def synccommands(ctx):
    try:
        await bot.tree.sync()
        await ctx.send("Commands Synced!")
        logging.info("Commands successfully synced.")
        print("Commands Synced!")
    except Exception as e:
        logging.error(f"Error syncing commands: {e}")
        await ctx.send(f"Failed to sync commands: {e}")
        print("Failed to sync commands!")


# add cogs
async def setup():
    await bot.add_cog(ConfigCog(bot))
    await bot.add_cog(VoiceStateCog(bot))
    await bot.add_cog(WelcomeCog(bot))
    await bot.add_cog(IllegalTeamActCog(bot))
    await bot.add_cog(CreateInvitationCog(bot, bot.get_cog("IllegalTeamActCog")))
    await bot.add_cog(DnDCog(bot))
    await bot.add_cog(CheckStatusCog(bot))
    await bot.add_cog(AchievementCog(bot))


@bot.event
async def setup_hook():
    await setup()


bot.run(TOKEN)
