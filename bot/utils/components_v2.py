from collections.abc import Sequence

import discord


def build_panel_container(
    *,
    title: str,
    description: str,
    buttons: Sequence[discord.ui.Button],
    footer: str | None = None,
    accent_color: discord.Color | int | None = None,
    thumbnail_url: str | None = None,
    media_url: str | None = None,
    media_description: str | None = None,
) -> discord.ui.Container:
    """Build a compact Components v2 panel container with optional action buttons."""
    children: list[discord.ui.Item] = []
    body = f"### {title}\n{description}"

    if thumbnail_url:
        children.append(
            discord.ui.Section(
                body,
                accessory=discord.ui.Thumbnail(thumbnail_url),
            )
        )
    else:
        children.append(discord.ui.TextDisplay(body))

    if media_url:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=media_url, description=media_description)
        children.append(discord.ui.Separator())
        children.append(gallery)

    if footer:
        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# {footer}"))

    for index in range(0, len(buttons), 5):
        children.append(discord.ui.ActionRow(*buttons[index:index + 5]))

    return discord.ui.Container(
        *children,
        accent_color=accent_color,
    )


def clear_legacy_message_payload() -> dict[str, object]:
    """Return edit kwargs required when replacing embed/content messages with LayoutView."""
    return {
        "content": None,
        "embed": None,
        "attachments": [],
    }
