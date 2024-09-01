# Author: MrZoyo
# Version: 0.8.0
# Date: 2024-09-01
# ========================================
import discord
from discord.ext import commands
import logging

from achievement_cog import AchievementCog
from backup_cog import BackupCog
from config_cog import ConfigCog
from check_status_cog import CheckStatusCog
from create_invitation_cog import CreateInvitationCog
from game_dnd_cog import DnDCog
from game_spymode_cog import SpyModeCog
from giveaway_cog import GiveawayCog
from illegal_team_act_cog import IllegalTeamActCog
from notebook_cog import NotebookCog
from rating_cog import RatingCog
from role_cog import RoleCog
from voice_channel_cog import VoiceStateCog
from welcome_cog import WelcomeCog

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
GUILD_ID = config['guild_id']

# 配置日志系统
logging.basicConfig(level=logging.INFO, filename=LOGGING_FILE, filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8')


@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user.name}')
    for guild in bot.guilds:
        if guild.id == GUILD_ID:
            logging.info(f"\nThe robot is connected to the server {guild.name}\n")
            print(f"\nThe robot is connected to the server {guild.name}\n")
            await bot.change_presence(activity=discord.Game(name=f"Working on {guild.name}"))
            await bot.tree.sync()
            print("Commands Synced.")

        else:
            logging.info(f"Bot not allowed to connect to {guild.name}")
            print(f"Bot not allowed to connect to {guild.name}")


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
    await bot.add_cog(NotebookCog(bot))
    await bot.add_cog(SpyModeCog(bot))
    await bot.add_cog(GiveawayCog(bot))
    await bot.add_cog(RoleCog(bot))
    await bot.add_cog(BackupCog(bot))
    await bot.add_cog(RatingCog(bot))


@bot.event
async def setup_hook():
    await setup()


bot.run(TOKEN)
