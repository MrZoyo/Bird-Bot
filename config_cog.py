# Author: MrZoyo
# Version: 0.7.0
# Date: 2024-06-20
# ========================================
import json
import discord
from discord.ext import commands


class ConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = self.read_config('config.json')

    def read_config(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                config = json.load(file)
        except FileNotFoundError:
            print(f"Configuration file {file_path} not found. Please create it.")
            config = {}
        except json.JSONDecodeError:
            print(f"Could not parse the JSON configuration file {file_path}. Please check its syntax.")
            config = {}

        # Check for required keys
        required_keys = ['token', 'logging_file', 'db_path', 'guild_id']
        for key in required_keys:
            if key not in config:
                print(f"Missing key {key} in configuration file {file_path}. Please add it.")
                config[key] = None  # You can set a default value here if you want

        return config
