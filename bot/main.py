# bot/main.py
import discord
from discord.ext import commands
import logging
from pathlib import Path

from bot.utils import config
from bot.cogs import (
    AchievementCog, BackupCog, CheckStatusCog,
    CreateInvitationCog, DnDCog, SpyModeCog, GiveawayCog,
    # IllegalTeamActCog,  # Moved to old_function
    NotebookCog, # RatingCog, 
    RoleCog, VoiceStateCog, WelcomeCog,
    ShopCog, PrivateRoomCog, TicketsNewCog, BanCog, TeamupDisplayCog
)


def create_bot():
    intents = discord.Intents.all()
    intents.members = True
    intents.guilds = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        guild_id = config.get_config()['guild_id']

        logging.info(f'Logged in as {bot.user.name}')
        for guild in bot.guilds:
            if guild.id == guild_id:
                logging.info(f"\n机器人已连接到服务器 {guild.name}\n")
                print(f"\n机器人已连接到服务器 {guild.name}\n")
                await bot.change_presence(activity=discord.Game(name=f"在 {guild.name} 上搬砖"))
                await bot.tree.sync(guild=guild)
                print("Commands Synced.")
            else:
                logging.info(f"Bot not allowed to connect to {guild.name}")
                print(f"Bot not allowed to connect to {guild.name}")

    @bot.command()
    async def synccommands(ctx):
        try:
            guild_id = config.get_config()['guild_id']
            guild = discord.Object(id=guild_id)
            await bot.tree.sync(guild=guild)
            await ctx.send("Commands Synced!")
            logging.info("Commands successfully synced.")
            print("Commands Synced!")
        except Exception as e:
            logging.error(f"Error syncing commands: {e}")
            await ctx.send(f"Failed to sync commands: {e}")
            print("Failed to sync commands!")

    return bot


async def setup_bot(bot):
    # Load configuration
    conf = config.get_config()

    # Configure main logging
    logging.basicConfig(
        level=logging.INFO,
        filename=conf['logging_file'],
        filemode='a',
        format='%(asctime)s - %(levelname)s - %(message)s',
        encoding='utf-8'
    )
    
    # Configure keyword detection logging
    keyword_logger = logging.getLogger('keyword_detection')
    keyword_logger.setLevel(logging.INFO)
    
    # Create separate handler for keyword detection logs
    keyword_log_file = conf.get('keyword_log_file', './data/keyword_detection.log')
    keyword_handler = logging.FileHandler(keyword_log_file, mode='a', encoding='utf-8')
    keyword_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    keyword_logger.addHandler(keyword_handler)
    
    # Prevent keyword logs from appearing in main log
    keyword_logger.propagate = False

    # Add all cogs
    # illegal_act_cog = IllegalTeamActCog(bot)  # Moved to old_function
    # await bot.add_cog(illegal_act_cog)
    await bot.add_cog(VoiceStateCog(bot))
    await bot.add_cog(WelcomeCog(bot))
    await bot.add_cog(CreateInvitationCog(bot))
    await bot.add_cog(DnDCog(bot))
    await bot.add_cog(CheckStatusCog(bot))
    await bot.add_cog(AchievementCog(bot))
    await bot.add_cog(NotebookCog(bot))
    await bot.add_cog(SpyModeCog(bot))
    await bot.add_cog(GiveawayCog(bot))
    await bot.add_cog(RoleCog(bot))
    await bot.add_cog(BackupCog(bot))
    # await bot.add_cog(RatingCog(bot))
    await bot.add_cog(TicketsNewCog(bot))
    await bot.add_cog(ShopCog(bot))
    await bot.add_cog(PrivateRoomCog(bot))
    await bot.add_cog(BanCog(bot))
    await bot.add_cog(TeamupDisplayCog(bot))

    return conf['token']


async def setup_hook(bot):
    await setup_bot(bot)


def run_bot():
    bot = create_bot()
    bot.setup_hook = lambda: setup_hook(bot)
    bot.run(config.get_config()['token'])
