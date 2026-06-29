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


def add_labeled_file_upload(
    modal: discord.ui.Modal,
    label: str,
    **kwargs: Any,
) -> discord.ui.FileUpload:
    """Add a discord.py 2.7 modal file upload with its required Label wrapper."""
    file_upload = discord.ui.FileUpload(**kwargs)
    modal.add_item(discord.ui.Label(text=label, component=file_upload))
    return file_upload
