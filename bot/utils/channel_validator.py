# bot/utils/channel_validator.py
import discord
from .config import config


async def check_channel_validity(ctx_or_interaction, allowed_channel_id=None):
    """
    Check if the command is used in the correct channel.

    Args:
        ctx_or_interaction: Context or Interaction from Discord
        allowed_channel_id: Optional specific channel ID to check. If None, uses default from config.

    Returns:
        bool: True if channel is valid, False otherwise
    """
    # Get channel ID from either Context or Interaction
    channel_id = ctx_or_interaction.channel.id if isinstance(ctx_or_interaction,
                                                             discord.ext.commands.Context) else ctx_or_interaction.channel_id

    # If no specific channel ID is provided, use the default from config
    if allowed_channel_id is None:
        allowed_channel_id = config.get_config()['admin_channel_id']
    else:
        allowed_channel_id = int(allowed_channel_id)

    # Check if channel is valid
    if channel_id != allowed_channel_id:
        message = "This command can only be used in specific channels."
        if isinstance(ctx_or_interaction, discord.ext.commands.Context):
            await ctx_or_interaction.send(message)
        else:
            await ctx_or_interaction.response.send_message(message, ephemeral=True)
        return False
    return True