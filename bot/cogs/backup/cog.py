# Author: MrZoyo
# Version: 0.7.4
# Date: 2024-06-26
# ========================================

import discord
import shutil
import asyncio
from discord.ext import commands, tasks
from discord import app_commands
from discord.app_commands import locale_str
from datetime import datetime, timedelta
import logging

from bot.utils import config, check_channel_validity
from bot.utils.paths import project_path, resolve_project_path


class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conf = config.get_config()
        self.db_path = resolve_project_path(self.conf['db_path'])
        self.backup_folder = project_path('backup', 'db_backup')
        self.backup_folder_manual = project_path('backup', 'db_backup_manual')
        self.file_limit = 20
        self.backup_database.start()

    @tasks.loop(hours=6)
    async def backup_database(self, manual=False):
        folder = self.backup_folder_manual if manual else self.backup_folder

        folder.mkdir(parents=True, exist_ok=True)

        # Copy the database to the backup folder with the current time appended to the name
        backup_name = f"database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = folder / backup_name

        shutil.copy2(self.db_path, backup_path)
        logging.info(f"Database backup created: {backup_path}")

        # Get a list of all backup files sorted by modification time
        backups = sorted(
            (path for path in folder.iterdir() if path.is_file() and path.name != '.gitkeep'),
            key=lambda path: path.stat().st_mtime,
        )

        # If there are too many backups, delete the oldest one
        while len(backups) > self.file_limit:
            oldest_backup = backups.pop(0)
            oldest_backup.unlink()
            logging.info(f"Deleted the oldest backup file: {oldest_backup}")

    @backup_database.before_loop
    async def before_backup(self):
        now = datetime.now()
        if now.hour < 6:
            next_run = now.replace(hour=6, minute=0, second=0)
        elif now.hour < 12:
            next_run = now.replace(hour=12, minute=0, second=0)
        elif now.hour < 18:
            next_run = now.replace(hour=18, minute=0, second=0)
        else:
            next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        await asyncio.sleep((next_run - now).total_seconds())

    @app_commands.command(
        name='backup_now',
        description=locale_str(
            'Manually create a database backup',
            key='backup.backup_now.description',
        ),
    )
    async def backup_now(self, interaction: discord.Interaction):
        if not await check_channel_validity(interaction):
            return

        await self.backup_database(manual=True)
        await interaction.response.send_message("Database backup created")
