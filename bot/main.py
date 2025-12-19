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

        # Debug: Print all commands in the tree
        # print(f"\n=== Debug: Commands in bot.tree ===")
        # all_commands = bot.tree.get_commands()
        # print(f"Total commands in tree: {len(all_commands)}")
        # for cmd in all_commands:
        #     print(f"  - {cmd.name} (type: {type(cmd).__name__})")
        # print("===================================\n")

        for guild in bot.guilds:
            if guild.id == guild_id:
                logging.info(f"\n机器人已连接到服务器 {guild.name}\n")
                print(f"\n机器人已连接到服务器 {guild.name}\n")
                await bot.change_presence(activity=discord.Game(name=f"在 {guild.name} 上搬砖"))

                # 清理旧的 guild 级别指令副本，避免与全局指令重复
                bot.tree.clear_commands(guild=guild)
                await bot.tree.sync(guild=guild)

                # Sync global commands once; avoid duplicating with guild-specific copies
                global_synced = await bot.tree.sync()
                print(f"Global commands synced: {len(global_synced)}")
            else:
                logging.info(f"Bot not allowed to connect to {guild.name}")
                print(f"Bot not allowed to connect to {guild.name}")

    @bot.command()
    async def synccommands(ctx):
        try:
            guild_id = config.get_config()['guild_id']
            guild = discord.Object(id=guild_id)
            # 清理 guild 级别指令副本，防止重复
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)

            global_synced = await bot.tree.sync()
            print(f"Global commands synced via manual sync: {len(global_synced)}")

            await ctx.send(f"Commands Synced! ({len(global_synced)} commands)")
            logging.info(f"Commands successfully synced. {len(global_synced)} commands synced.")
            print("Commands Synced!")
        except Exception as e:
            logging.error(f"Error syncing commands: {e}")
            await ctx.send(f"Failed to sync commands: {e}")
            print(f"Failed to sync commands! Error: {e}")

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

    # Configure room activity logging
    room_logger = logging.getLogger('room_activity')
    room_logger.setLevel(logging.INFO)

    # Create separate handler for room activity logs
    room_log_file = conf.get('room_log_file', './data/room_activity.log')
    room_handler = logging.FileHandler(room_log_file, mode='a', encoding='utf-8')
    room_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    room_logger.addHandler(room_handler)

    # Prevent room logs from appearing in main log
    room_logger.propagate = False

    # Add all cogs
    cogs_to_load = [
        ("VoiceStateCog", VoiceStateCog(bot)),
        ("WelcomeCog", WelcomeCog(bot)),
        ("CreateInvitationCog", CreateInvitationCog(bot)),
        ("DnDCog", DnDCog(bot)),
        ("CheckStatusCog", CheckStatusCog(bot)),
        ("AchievementCog", AchievementCog(bot)),
        ("NotebookCog", NotebookCog(bot)),
        ("SpyModeCog", SpyModeCog(bot)),
        ("GiveawayCog", GiveawayCog(bot)),
        ("RoleCog", RoleCog(bot)),
        ("BackupCog", BackupCog(bot)),
        ("TicketsNewCog", TicketsNewCog(bot)),
        ("ShopCog", ShopCog(bot)),
        ("PrivateRoomCog", PrivateRoomCog(bot)),
        ("BanCog", BanCog(bot)),
        ("TeamupDisplayCog", TeamupDisplayCog(bot)),
    ]

    for cog_name, cog_instance in cogs_to_load:
        try:
            await bot.add_cog(cog_instance)
            # logging.info(f"Successfully loaded cog: {cog_name}")
            # print(f"✓ Loaded: {cog_name}")
        except Exception as e:
            logging.error(f"Failed to load cog {cog_name}: {e}", exc_info=True)
            print(f"✗ Failed to load {cog_name}: {e}")

    return conf['token']


async def setup_hook(bot):
    await setup_bot(bot)


def run_bot():
    bot = create_bot()
    bot.setup_hook = lambda: setup_hook(bot)
    bot.run(config.get_config()['token'])
