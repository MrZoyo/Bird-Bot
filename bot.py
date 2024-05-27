import discord
from discord.ext import commands
from collections import defaultdict
import logging
import sqlite3
from voice_channel_cog import VoiceStateCog
from welcome_cog import WelcomeCog
from illegal_team_act_cog import IllegalTeamActCog
from create_invitation_cog import CreateInvitationCog

# Your bot token
TOKEN = 'Your_Token_Here'

intents = discord.Intents.all()
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Store information about temporary channels
temp_channels = defaultdict(dict)

# Configure the logging system
logging.basicConfig(level=logging.INFO, filename='bot.log', filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')


@bot.event
async def on_ready():
    logging.info(f'Logged in as {bot.user.name}')
    for guild in bot.guilds:
        logging.info(f"\nBot connected to server {guild.name}\n")
        print(f"\nBot connected to server {guild.name}\n")
        await bot.change_presence(activity=discord.Game(name=f"Working in {guild.name}"))


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
    await bot.add_cog(VoiceStateCog(bot))
    await bot.add_cog(WelcomeCog(bot))
    await bot.add_cog(IllegalTeamActCog(bot))
    await bot.add_cog(CreateInvitationCog(bot, bot.get_cog("IllegalTeamActCog")))


def initialize_database():
    conn = sqlite3.connect('bot.db')  # Ensure this matches your database file
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS illegal_teaming (
            user_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            message TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


@bot.event
async def setup_hook():
    await setup()


initialize_database()
bot.run(TOKEN)
