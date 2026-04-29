import asyncio
import logging
from types import SimpleNamespace

import discord

from bot.cogs.create_invitation import full_message
from bot.cogs.create_invitation.cog import log_keyword_detection


class FakeBot:
    def get_channel(self, channel_id):
        if channel_id == 456:
            return SimpleNamespace(id=456, name="Alpha Room")
        return None


class FakeMessage:
    id = 999
    channel = SimpleNamespace(id=111, name="teamup")

    def __init__(self, embed):
        self.embeds = [embed]
        self.edited_embed = None
        self.edited_view = "not-updated"

    async def edit(self, *, embed, view):
        self.edited_embed = embed
        self.edited_view = view


def test_update_invitation_message_to_full_uses_shared_locale_style(monkeypatch):
    translations = {
        "invitation.roomfull_title": "[FULL]",
        "invitation.invite_embed_content_edited": (
            "voice={name}; url={url}; user={mention}; time={time}"
        ),
    }
    monkeypatch.setattr(full_message, "t", lambda key: translations[key])

    embed = discord.Embed(
        title="Need one",
        description=(
            "join https://discord.com/channels/123/456 "
            "from <@789> posted <t:1700000000:R>"
        ),
        color=discord.Color.blue(),
    )
    embed.add_field(name="note", value="keep me", inline=False)
    embed.set_thumbnail(url="https://example.com/avatar.png")
    embed.set_footer(text="old footer")
    embed.timestamp = discord.utils.utcnow()

    message = FakeMessage(embed)

    asyncio.run(full_message.update_invitation_message_to_full(FakeBot(), message))

    assert message.edited_view is None
    assert message.edited_embed.title == "[FULL] ~~Need one~~"
    assert message.edited_embed.description == (
        "voice=Alpha Room; "
        "url=https://discord.com/channels/123/456; "
        "user=<@789>; "
        "time=<t:1700000000:R>"
    )
    assert message.edited_embed.color == discord.Color.red()
    assert message.edited_embed.fields[0].name == "note"
    assert message.edited_embed.fields[0].value == "keep me"
    assert message.edited_embed.footer.text is None
    assert message.edited_embed.timestamp is None


def test_keyword_detection_log_uses_name_and_id(caplog):
    logger = logging.getLogger("keyword_detection")
    old_propagate = logger.propagate
    logger.propagate = True
    try:
        message = SimpleNamespace(
            author=SimpleNamespace(id=123, display_name="Alice", name="alice_raw"),
            channel=SimpleNamespace(id=456, name="teamup"),
            content="缺1",
        )

        with caplog.at_level(logging.INFO, logger="keyword_detection"):
            log_keyword_detection(message, [("缺", "1", "")])

        assert "Alice / alice_raw (123)" in caplog.text
        assert "teamup (456)" in caplog.text
    finally:
        logger.propagate = old_propagate
