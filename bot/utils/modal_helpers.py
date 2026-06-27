from typing import Any

import discord


def add_labeled_text_input(
    modal: discord.ui.Modal,
    label: str,
    **kwargs: Any,
) -> discord.ui.TextInput:
    """Add a discord.py 2.7 modal text input with its required Label wrapper."""
    text_input = discord.ui.TextInput(**kwargs)
    modal.add_item(discord.ui.Label(text=label, component=text_input))
    return text_input
