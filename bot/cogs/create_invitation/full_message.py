import logging
import re
from typing import Any

import discord

from bot.utils import fmt_channel
from bot.utils.components_v2 import build_panel_container, clear_legacy_message_payload
from bot.utils.i18n import t


async def update_invitation_message_to_full(
    bot: Any, message: discord.Message, *, voice_channel: Any = None,
) -> str:
    """Update a team invitation message to the shared "room full" style."""
    try:
        if message.embeds:
            await _update_legacy_embed_message(bot, message, voice_channel=voice_channel)
            return 'updated'

        panel_data = _extract_panel_data(message)
        if not panel_data:
            return 'invalid'

        title, description, thumbnail_url = panel_data
        full_title = _full_title(title)
        full_description = await _build_full_description(bot, description, voice_channel=voice_channel)
        view = _build_full_panel_view(
            title=full_title,
            description=full_description,
            thumbnail_url=thumbnail_url,
        )

        await message.edit(
            **clear_legacy_message_payload(),
            view=view,
        )
        return 'updated'

    except discord.Forbidden:
        logging.error(
            "No permission to edit invitation message %s in channel %s",
            getattr(message, 'id', 'unknown'),
            fmt_channel(getattr(message, 'channel', None)),
        )
        return 'forbidden'
    except discord.NotFound:
        logging.warning(
            "Invitation message %s not found when updating to full in channel %s",
            getattr(message, 'id', 'unknown'),
            fmt_channel(getattr(message, 'channel', None)),
        )
        return 'missing'
    except Exception as e:
        logging.error("Error updating invitation message to full: %s", e, exc_info=True)
        return 'retry'


def _full_title(title):
    label = t('invitation.roomfull_title')
    if title and title.startswith(label):
        return title
    return f"{label} ~~{title}~~" if title else label


async def _update_legacy_embed_message(bot: Any, message: discord.Message, *, voice_channel: Any = None) -> None:
    embed = message.embeds[0]
    new_description = await _build_full_description(bot, embed.description or "", voice_channel=voice_channel)

    new_embed = discord.Embed(
        title=_full_title(embed.title),
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


def _build_full_panel_view(
    *,
    title: str,
    description: str,
    thumbnail_url: str | None,
) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(build_panel_container(
        title=title,
        description=description,
        accent_color=discord.Color.red(),
        thumbnail_url=thumbnail_url,
        buttons=[],
    ))
    return view


def _extract_panel_data(message: discord.Message) -> tuple[str, str, str | None] | None:
    components = getattr(message, "components", None)
    if not components:
        return None

    payloads = [_component_to_payload(component) for component in components]
    text_blocks = [
        str(component["content"])
        for component in _walk_component_payloads(payloads)
        if component.get("type") == 10 and component.get("content")
    ]
    if not text_blocks:
        return None

    title, description = _split_panel_body(text_blocks[0])
    if len(text_blocks) > 1:
        extra_blocks = [
            block
            for block in text_blocks[1:]
            if not block.startswith("-# ")
        ]
        if extra_blocks:
            description = "\n\n".join([description, *extra_blocks]).strip()

    return title, description, _extract_thumbnail_url(payloads)


def _component_to_payload(component: Any) -> dict[str, Any]:
    if isinstance(component, dict):
        return component
    if hasattr(component, "to_dict"):
        return component.to_dict()

    payload: dict[str, Any] = {}
    component_type = getattr(component, "type", None)
    if component_type is not None:
        payload["type"] = getattr(component_type, "value", component_type)

    content = getattr(component, "content", None)
    if content is not None:
        payload["content"] = content

    children = getattr(component, "children", None) or getattr(component, "components", None)
    if children:
        payload["components"] = [_component_to_payload(child) for child in children]

    accessory = getattr(component, "accessory", None)
    if accessory is not None:
        payload["accessory"] = _component_to_payload(accessory)

    media = getattr(component, "media", None)
    media_url = getattr(media, "url", None) if media is not None else None
    url = getattr(component, "url", None) or media_url
    if url:
        payload["media"] = {"url": url}

    return payload


def _walk_component_payloads(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened = []
    for component in components:
        flattened.append(component)

        children = component.get("components") or []
        if children:
            flattened.extend(_walk_component_payloads(children))

        accessory = component.get("accessory")
        if accessory:
            flattened.extend(_walk_component_payloads([accessory]))

    return flattened


def _split_panel_body(content: str) -> tuple[str, str]:
    if not content.startswith("### "):
        return "", content

    title, separator, description = content[4:].partition("\n")
    if not separator:
        return title.strip(), ""
    return title.strip(), description.strip()


def _extract_thumbnail_url(components: list[dict[str, Any]]) -> str | None:
    for component in _walk_component_payloads(components):
        if component.get("type") != 11:
            continue
        media = component.get("media") or {}
        url = media.get("url")
        if url:
            return url
    return None


def _saved_channel_name(description: str, url: str) -> str | None:
    # Full messages keep the name in code; active messages keep it in the link
    # label so a deleted room remains identifiable after a restart.
    full_name = re.search(r'`([^`\n]+)`[ \t]+\[[^\]\n]*\]\(' + re.escape(url) + r'\)', description)
    if full_name:
        return full_name.group(1) if full_name.group(1) != '未知频道' else None
    link_name = re.search(r'\[((?:\\.|[^\]\\\n])+)\]\(' + re.escape(url) + r'\)', description)
    if link_name:
        return re.sub(r'\\(.)', r'\1', link_name.group(1))
    return None


async def _build_full_description(bot: Any, description: str, *, voice_channel: Any = None) -> str:
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

    channel_id = int(voice_channel_id)
    if getattr(voice_channel, 'id', None) != channel_id:
        voice_channel = bot.get_channel(channel_id)
    saved_name = _saved_channel_name(description, url)
    fallback_key = 'invitation.channel_unavailable'
    if voice_channel is None:
        try:
            voice_channel = await bot.fetch_channel(channel_id)
        except discord.NotFound:
            fallback_key = 'invitation.channel_deleted'
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            if not saved_name:
                raise  # Keep transient failures eligible for durable retry.
    channel_name = voice_channel.name if voice_channel else saved_name
    if not channel_name:
        channel_name = t(fallback_key).format(channel_id=channel_id)
    channel_name = discord.utils.escape_mentions(channel_name.replace('`', 'ˋ'))

    return t('invitation.invite_embed_content_edited').format(
        name=channel_name,
        url=url,
        mention=mention,
        time=time,
    )
