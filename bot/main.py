import logging
from importlib import import_module

import discord
from discord.ext import commands

from bot.utils import config


COG_SPECS = [
    {
        "feature": "voicechannel",
        "cog_name": "VoiceStateCog",
        "module_path": "bot.cogs.voice_channel_cog",
        "class_name": "VoiceStateCog",
        "required_configs": ["voicechannel"],
    },
    {
        "feature": "welcome",
        "cog_name": "WelcomeCog",
        "module_path": "bot.cogs.welcome_cog",
        "class_name": "WelcomeCog",
        "required_configs": ["welcome"],
    },
    {
        "feature": "invitation",
        "cog_name": "CreateInvitationCog",
        "module_path": "bot.cogs.create_invitation_cog",
        "class_name": "CreateInvitationCog",
        "required_configs": ["invitation"],
    },
    {
        "feature": "dnd",
        "cog_name": "DnDCog",
        "module_path": "bot.cogs.game_dnd_cog",
        "class_name": "DnDCog",
        "required_configs": [],
    },
    {
        "feature": "checkstatus",
        "cog_name": "CheckStatusCog",
        "module_path": "bot.cogs.check_status_cog",
        "class_name": "CheckStatusCog",
        "required_configs": ["checkstatus"],
    },
    {
        "feature": "achievements",
        "cog_name": "AchievementCog",
        "module_path": "bot.cogs.achievement_cog",
        "class_name": "AchievementCog",
        "required_configs": ["achievements"],
    },
    {
        "feature": "notebook",
        "cog_name": "NotebookCog",
        "module_path": "bot.cogs.notebook_cog",
        "class_name": "NotebookCog",
        "required_configs": [],
    },
    {
        "feature": "spymode",
        "cog_name": "SpyModeCog",
        "module_path": "bot.cogs.game_spymode_cog",
        "class_name": "SpyModeCog",
        "required_configs": ["spymode"],
    },
    {
        "feature": "giveaway",
        "cog_name": "GiveawayCog",
        "module_path": "bot.cogs.giveaway_cog",
        "class_name": "GiveawayCog",
        "required_configs": ["giveaway"],
    },
    {
        "feature": "role",
        "cog_name": "RoleCog",
        "module_path": "bot.cogs.role_cog",
        "class_name": "RoleCog",
        "required_configs": ["role", "achievements"],
    },
    {
        "feature": "backup",
        "cog_name": "BackupCog",
        "module_path": "bot.cogs.backup_cog",
        "class_name": "BackupCog",
        "required_configs": [],
    },
    {
        "feature": "tickets_new",
        "cog_name": "TicketsNewCog",
        "module_path": "bot.cogs.tickets_new_cog",
        "class_name": "TicketsNewCog",
        "required_configs": ["tickets_new"],
    },
    {
        "feature": "shop",
        "cog_name": "ShopCog",
        "module_path": "bot.cogs.shop_cog",
        "class_name": "ShopCog",
        "required_configs": ["shop"],
    },
    {
        "feature": "privateroom",
        "cog_name": "PrivateRoomCog",
        "module_path": "bot.cogs.privateroom_cog",
        "class_name": "PrivateRoomCog",
        "required_configs": ["privateroom", "role"],
    },
    {
        "feature": "ban",
        "cog_name": "BanCog",
        "module_path": "bot.cogs.ban_cog",
        "class_name": "BanCog",
        "required_configs": ["ban"],
    },
    {
        "feature": "teamup_display",
        "cog_name": "TeamupDisplayCog",
        "module_path": "bot.cogs.teamup_display_cog",
        "class_name": "TeamupDisplayCog",
        "required_configs": ["teamup_display"],
    },
]


def _get_missing_configs(config_names):
    missing_configs = []
    for config_name in config_names:
        if not config.config_exists(config_name):
            missing_configs.append(config_name)
            continue

        if not config.reload_config(config_name, silent=True):
            missing_configs.append(config_name)

    return missing_configs


def _load_cog_class(module_path, class_name):
    module = import_module(module_path)
    return getattr(module, class_name)


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

    loaded_cogs = []

    for spec in COG_SPECS:
        feature_name = spec['feature']
        cog_name = spec['cog_name']

        if not config.is_feature_enabled(feature_name):
            logging.info(f"Skip loading {cog_name}: feature '{feature_name}' is disabled.")
            print(f"- Skipped {cog_name}: feature '{feature_name}' is disabled.")
            continue

        missing_configs = _get_missing_configs(spec['required_configs'])
        if missing_configs:
            missing_text = ', '.join(missing_configs)
            logging.info(f"Skip loading {cog_name}: missing or empty configs: {missing_text}.")
            print(f"- Skipped {cog_name}: missing or empty configs: {missing_text}.")
            continue

        try:
            cog_class = _load_cog_class(spec['module_path'], spec['class_name'])
            await bot.add_cog(cog_class(bot))
            loaded_cogs.append(cog_name)
            logging.info(f"Loaded cog: {cog_name}")
        except Exception as e:
            logging.error(f"Failed to load cog {cog_name}: {e}", exc_info=True)
            print(f"✗ Failed to load {cog_name}: {e}")

    logging.info(f"Loaded {len(loaded_cogs)} cogs: {', '.join(loaded_cogs)}")
    print(f"Loaded {len(loaded_cogs)} cogs: {', '.join(loaded_cogs)}")

    return conf['token']


async def setup_hook(bot):
    await setup_bot(bot)


def run_bot():
    bot = create_bot()
    bot.setup_hook = lambda: setup_hook(bot)
    bot.run(config.get_config()['token'])
