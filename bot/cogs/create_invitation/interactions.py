import asyncio
import logging
import time

import discord

from bot.utils import fmt_channel, fmt_user


async def acknowledge(interaction):
    """Acknowledge before DB/network work; an expired request has no side effects."""
    started = time.monotonic()
    created = getattr(interaction, 'created_at', None)
    age = (discord.utils.utcnow() - created).total_seconds() if created else None
    try:
        await interaction.response.defer(ephemeral=True)
    except (discord.HTTPException, asyncio.TimeoutError, OSError) as exc:
        logging.warning(
            'Invitation acknowledgement failed: interaction=%s message=%s user=%s channel=%s '
            'age_seconds=%s elapsed_seconds=%.3f code=%s',
            getattr(interaction, 'id', None), getattr(getattr(interaction, 'message', None), 'id', None),
            fmt_user(interaction.user), fmt_channel(getattr(interaction, 'channel', None)),
            age, time.monotonic() - started, getattr(exc, 'code', type(exc).__name__),
        )
        return False
    return True
