import discord
from discord.ext import commands
from collections import defaultdict
import re
import logging

# Use a dictionary to manage all configurations. The channel ID corresponds to the channel type name and type
CHANNEL_CONFIGS = {
    11451419198101: {"name_prefix": "GameRoom", "type": "public"},
    11451419198102: {"name_prefix": "RelaxRoom", "type": "public"},
    81019191145141: {"name_prefix": "PrivateRoom", "type": "private"},
    81019191145142: {"name_prefix": "PVP Room", "type": "public"}
}

# Your bot token
TOKEN = 'Your_Token_Here'

# List of user IDs that the bot will ignore
IGNORE_USER_IDS = [1234567899786574, 1145141919810]

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
        await bot.change_presence(activity=discord.Game(name=f"Working in {guild.name}"))


@bot.event
async def on_voice_state_update(member, before, after):
    # PUBLIC_CHANNEL_ID_LIST Public channel
    # PRIVATE_CHANNEL_ID_LIST Private channel

    # Check if the user has joined a specific channel
    if after.channel and after.channel.id in CHANNEL_CONFIGS:
        config = CHANNEL_CONFIGS[after.channel.id]
        if config["type"] == "public":
            await handle_channel(member, after, config, public=True)
        elif config["type"] == "private":
            await handle_channel(member, after, config, public=False)

    # Check if a user has left a temporary channel
    if before.channel and before.channel.id in temp_channels:
        # If the channel now has no users
        if len(before.channel.members) == 0:
            # Delete the channel
            await before.channel.delete()
            # Remove the channel from the dictionary
            del temp_channels[before.channel.id]


async def handle_channel(member, after, config, public=True):
    category = after.channel.category
    temp_channel_name = f"{config['name_prefix']}-{member.display_name}"

    if public:  # public channel
        overwrites = {
            after.channel.guild.default_role: discord.PermissionOverwrite(view_channel=True),
            member: discord.PermissionOverwrite(manage_channels=True, view_channel=True, connect=True, speak=True)
        }
    else:  # private channel
        overwrites = {
            after.channel.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
        }

    # Create a new voice channel
    temp_channel = await after.channel.guild.create_voice_channel(
        name=temp_channel_name, category=category, overwrites=overwrites)

    # Store the channel ID and the user ID in the dictionary
    temp_channels[temp_channel.id] = member.id

    # Move the user to the new channel
    await member.move_to(temp_channel)


@bot.listen('on_message')
async def on_message(message):
    # Avoid the bot responding to its own messages
    if message.author == bot.user:
        return

    # Check for a message that only has 6 characters and does not contain certain patterns
    if len(message.content) == 6 and not re.search(r"[=＝一二三四五\s]", message.content):
        return  # Ignore this message

    # Check if the message contains a URL
    if re.search(r"https?:\/\/", message.content):
        return

    # Ignore messages from specific users
    if message.author.id in IGNORE_USER_IDS:
        return

    # Regex pattern without negative lookbehind assertion
    pattern = r"(缺\d|等\d|[=＝]\d|[Qq]\d|缺[一二三四五]|等[一二三四五]|缺[nN]|等[nN]|[=＝]N|[=＝]n)(?!(分|分钟|min|个钟|小时))"

    # Find all matches in the content
    matches = re.findall(pattern, message.content, re.IGNORECASE)

    # Filter valid matches
    valid_matches = []
    for match in matches:
        if not re.search(r'\d[A-Z]$', message.content, re.IGNORECASE):
            valid_matches.append(match)

    if valid_matches:
        logging.info(f'Detected content from {message.author}: {message.content}, Matches: {valid_matches}!')

        # Check if the user is in a voice channel
        if message.author.voice and message.author.voice.channel:
            try:
                vc_url = await message.author.voice.channel.create_invite(max_age=600)  # Link valid for 10 minutes
                reply_message = f"{vc_url}"
            except Exception as e:
                reply_message = "Error creating invite link, please check my permissions."
        else:
            reply_message = f'{message.author.mention}, it is forbidden to pull privately, please start a voice channel!'

        await message.reply(reply_message)

    # Process commands
    await bot.process_commands(message)

bot.run(TOKEN)
