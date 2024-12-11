# bot/main.py
import discord
from discord.ext import commands
import logging
from pathlib import Path

from bot.utils import config
from bot.cogs import (
    AchievementCog, BackupCog, CheckStatusCog,
    CreateInvitationCog, DnDCog, SpyModeCog, GiveawayCog,
    IllegalTeamActCog, NotebookCog, RatingCog, RoleCog,
    VoiceStateCog, WelcomeCog, TicketsCog
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

    return bot


async def setup_bot(bot):
    # Load configuration
    conf = config.get_config()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        filename=conf['logging_file'],
        filemode='a',
        format='%(asctime)s - %(levelname)s - %(message)s',
        encoding='utf-8'
    )

    # Add all cogs
    illegal_act_cog = IllegalTeamActCog(bot)
    await bot.add_cog(illegal_act_cog)
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
    await bot.add_cog(RatingCog(bot))
    await bot.add_cog(TicketsCog(bot))

    return conf['token']


async def setup_hook(bot):
    await setup_bot(bot)


def run_bot():
    bot = create_bot()
    bot.setup_hook = lambda: setup_hook(bot)
    bot.run(config.get_config()['token'])
