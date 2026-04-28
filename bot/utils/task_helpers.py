import logging
from typing import Any


async def wait_until_ready_or_stop(bot: Any, loop: Any, loop_name: str) -> bool:
    """Wait for a logged-in bot, or stop a background loop during offline smoke."""
    try:
        await bot.wait_until_ready()
    except RuntimeError:
        logging.info(
            "Skipping %s background loop because the Discord client is not logged in.",
            loop_name,
        )
        loop.stop()
        return False
    return True
