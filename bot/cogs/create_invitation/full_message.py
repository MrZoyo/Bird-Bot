import logging
import re
from typing import Any

import discord

from bot.utils import fmt_channel
from bot.utils.i18n import t


async def update_invitation_message_to_full(bot: Any, message: discord.Message) -> None:
    """Update a team invitation message to the shared "room full" style."""
    try:
        if not message.embeds:
            return

        embed = message.embeds[0]
        new_description = _build_full_description(bot, embed.description or "")

        new_embed = discord.Embed(
            title=f"{t('invitation.roomfull_title')} ~~{embed.title}~~",
            description=new_description,
            color=discord.Color.red(),
        )

        for field in embed.fields:
            new_embed.add_field(name=field.name, value=field.value, inline=field.inline)

        if embed.thumbnail:
            new_embed.set_thumbnail(url=embed.thumbnail.url)

        # Link buttons cannot be disabled. Removing the view keeps both
        # invitation-message paths visually identical after the room is full.
        await message.edit(embed=new_embed, view=None)

    except discord.Forbidden:
        logging.error(
            "No permission to edit invitation message %s in channel %s",
            getattr(message, 'id', 'unknown'),
            fmt_channel(getattr(message, 'channel', None)),
        )
    except discord.NotFound:
        logging.warning(
            "Invitation message %s not found when updating to full in channel %s",
            getattr(message, 'id', 'unknown'),
            fmt_channel(getattr(message, 'channel', None)),
        )
    except Exception as e:
        logging.error("Error updating invitation message to full: %s", e, exc_info=True)


def _build_full_description(bot: Any, description: str) -> str:
    voice_channel_match = re.search(
        r'https://discord\.com/channels/\d+/(\d+)',
        description,
    )
    if not voice_channel_match:
        return description

    voice_channel_id = voice_channel_match.group(1)
    guild_id_match = re.search(
        r'https://discord\.com/channels/(\d+)/\d+',
        description,
    )
    guild_id = guild_id_match.group(1) if guild_id_match else ''
    url = f"https://discord.com/channels/{guild_id}/{voice_channel_id}"

    mention_match = re.search(r'<@\d+>', description)
    mention = mention_match.group(0) if mention_match else ''

    time_match = re.search(r'<t:\d+:R>', description)
    time = time_match.group(0) if time_match else ''

    voice_channel = bot.get_channel(int(voice_channel_id))
    channel_name = voice_channel.name if voice_channel else '未知频道'

    return t('invitation.invite_embed_content_edited').format(
        name=channel_name,
        url=url,
        mention=mention,
        time=time,
    )
