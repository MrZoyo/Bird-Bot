# Author: MrZoyo
# Version: 0.7.4
# Date: 2024-06-26
# ========================================

import os
import discord
import shutil
import asyncio
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import logging

from bot.utils import config, check_channel_validity


class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_folder = './backup/db_backup'
        self.backup_folder_manual = './backup/db_backup_manual'
        self.backup_database.start()
        self.file_limit = 20

        self.conf = config.get_config()
        self.db_path = self.conf['db_path']

    @tasks.loop(hours=6)
    async def backup_database(self, manual=False):
        if manual:
            folder = self.backup_folder_manual
        else:
            folder = self.backup_folder

        # Create the backup folder if it doesn't exist
        if not os.path.exists(folder):
            os.makedirs(folder)

        # Copy the database to the backup folder with the current time appended to the name
        backup_name = f"database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

        shutil.copy2(self.db_path, os.path.join(folder, backup_name))
        logging.info(f"Database backup created: {backup_name}")

        # Get a list of all backup files sorted by modification time
        backups = sorted(os.listdir(folder),
                         key=lambda x: os.path.getmtime(os.path.join(folder, x)))

        # If there are too many backups, delete the oldest one
        while len(backups) > self.file_limit:
            os.remove(os.path.join(folder, backups.pop(0)))
            logging.info("Deleted the oldest backup file")

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

    @app_commands.command(name='backup_now', description='Manually create a database backup')
    async def backup_now(self, interaction: discord.Interaction):
        if not await check_channel_validity(interaction):
            return

        await self.backup_database(manual=True)
        await interaction.response.send_message("Database backup created")
