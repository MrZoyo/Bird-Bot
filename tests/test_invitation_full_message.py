import asyncio
import logging
from types import SimpleNamespace

import discord

from bot.cogs.create_invitation import full_message
from bot.cogs.create_invitation import views as invitation_views
from bot.cogs.create_invitation.cog import log_keyword_detection
from bot.cogs.create_invitation.views import TeamInvitationView


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


class FakeV2Message:
    id = 1000
    channel = SimpleNamespace(id=111, name="teamup")

    def __init__(self, components):
        self.embeds = []
        self.components = components
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeResponse:
    def __init__(self, events):
        self.events = events

    async def defer(self, *, ephemeral=False, **kwargs):
        self.events.append(("defer", ephemeral, kwargs))


class FakeFollowup:
    def __init__(self, events):
        self.events = events
        self.messages = []

    async def send(self, content=None, *, ephemeral=False, **kwargs):
        self.events.append(("followup", content, ephemeral))
        self.messages.append({
            "content": content,
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, *, user, message, events):
        self.user = user
        self.message = message
        self.response = FakeResponse(events)
        self.followup = FakeFollowup(events)


class FakeRoleDB:
    async def get_user_signature(self, user_id):
        return {"signature": "main jungle", "is_disabled": False}


class FakeInvitationCog:
    def __init__(self, events):
        self.events = events

    async def update_message_to_full(self, message):
        self.events.append(("update_full", message.id))


class FakeTeamupCog:
    def __init__(self, events):
        self.events = events
        self.removed = []

    async def remove_teamup_from_display(self, user_id, voice_channel_id):
        self.events.append(("remove_display", user_id, voice_channel_id))
        self.removed.append((user_id, voice_channel_id))


class FakeViewBot:
    def __init__(self, events=None, invitation_cog=None, teamup_cog=None):
        self.user = SimpleNamespace(avatar=None)
        self.events = events or []
        self.invitation_cog = invitation_cog
        self.teamup_cog = teamup_cog

    def get_cog(self, name):
        if name == "CreateInvitationCog":
            return self.invitation_cog
        if name == "TeamupDisplayCog":
            return self.teamup_cog
        return None


def _install_view_translations(monkeypatch):
    translations = {
        "invitation.roomfull_button_label": "Full",
        "invitation.invite_button_label": "Join",
        "invitation.invite_embed_content": (
            "voice={vc_url}; user={mention}; time={time}"
        ),
        "invitation.interaction_target_error_message": "not yours",
        "invitation.roomfull_set_message": "marked full",
        "invitation.not_in_vc_message": "not in vc",
        "invitation.extract_channel_id_error": "extract failed",
    }
    monkeypatch.setattr(invitation_views, "t", lambda key: translations[key])
    monkeypatch.setattr(
        invitation_views.config,
        "get_config",
        lambda name: {"default_create_room_channel_id": 456},
    )


def _walk_components(components):
    for component in components:
        yield component
        children = component.get("components") or []
        yield from _walk_components(children)
        accessory = component.get("accessory")
        if accessory:
            yield from _walk_components([accessory])


def _first_text_content(components):
    for component in _walk_components(components):
        if component.get("type") == 10:
            return component["content"]
    return ""


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


def test_update_invitation_message_to_full_repaints_components_v2_panel(monkeypatch):
    translations = {
        "invitation.roomfull_title": "[FULL]",
        "invitation.invite_embed_content_edited": (
            "voice={name}; url={url}; user={mention}; time={time}"
        ),
    }
    monkeypatch.setattr(full_message, "t", lambda key: translations[key])

    join_button = discord.ui.Button(
        style=discord.ButtonStyle.link,
        label="Join",
        url="https://discord.com/channels/123/456",
    )
    full_button = discord.ui.Button(
        style=discord.ButtonStyle.danger,
        label="Full",
        custom_id="room_full_button",
    )
    view = discord.ui.LayoutView()
    view.add_item(full_message.build_panel_container(
        title="Need one",
        description=(
            "join https://discord.com/channels/123/456 "
            "from <@789> posted <t:1700000000:R>"
        ),
        footer="Use buttons",
        accent_color=discord.Color.blue(),
        buttons=[join_button, full_button],
    ))
    message = FakeV2Message(view.to_components())

    asyncio.run(full_message.update_invitation_message_to_full(FakeBot(), message))

    edit = message.edits[0]
    assert edit["content"] is None
    assert edit["embed"] is None
    assert edit["attachments"] == []
    assert edit["view"].has_components_v2() is True
    container = edit["view"].to_components()[0]
    text = _first_text_content(container["components"])
    assert text.startswith("### [FULL] ~~Need one~~")
    assert "voice=Alpha Room" in text


def test_team_invitation_view_uses_components_v2_with_separator(monkeypatch):
    async def scenario():
        _install_view_translations(monkeypatch)
        guild = SimpleNamespace(id=123)
        channel = SimpleNamespace(id=456, guild=guild)
        user = SimpleNamespace(
            id=789,
            mention="<@789>",
            guild=guild,
            avatar=None,
            voice=SimpleNamespace(channel=channel),
        )
        message = SimpleNamespace(
            author=user,
            content="缺1 <@999>",
        )
        view = TeamInvitationView(FakeViewBot(), channel, user, FakeRoleDB())

        await view.populate_panel(message)

        assert view.has_components_v2() is True
        container = view.to_components()[0]
        assert container["type"] == 17
        assert _first_text_content(container["components"]).startswith("### 缺1")
        assert "<@999>" not in _first_text_content(container["components"])
        assert not any(component["type"] == 14 for component in container["components"])
        action_row = container["components"][-1]
        assert [button["label"] for button in action_row["components"]] == ["Join", "Full"]

    asyncio.run(scenario())


def test_team_invitation_full_button_uses_view_channel_without_embed(monkeypatch):
    async def scenario():
        _install_view_translations(monkeypatch)
        events = []
        guild = SimpleNamespace(id=123)
        channel = SimpleNamespace(id=456, guild=guild)
        user = SimpleNamespace(
            id=789,
            mention="<@789>",
            guild=guild,
            avatar=None,
            voice=SimpleNamespace(channel=channel),
        )
        invitation_cog = FakeInvitationCog(events)
        teamup_cog = FakeTeamupCog(events)
        bot = FakeViewBot(events, invitation_cog, teamup_cog)
        view = TeamInvitationView(bot, channel, user, FakeRoleDB())
        message = SimpleNamespace(id=1000, embeds=[], components=[])
        interaction = FakeInteraction(user=user, message=message, events=events)

        await view.room_full_button_callback(interaction)

        assert events == [
            ("defer", True, {}),
            ("update_full", 1000),
            ("remove_display", user.id, channel.id),
            ("followup", "marked full", True),
        ]

    asyncio.run(scenario())


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
