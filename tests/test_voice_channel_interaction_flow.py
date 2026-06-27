import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import discord

from bot.cogs.create_invitation import full_message
from bot.cogs.voice_channel import views as voice_views
from bot.cogs.voice_channel.views import RoomControlPanelView


VOICE_TEXT = {
    "voicechannel.control_panel.title": "Room Control",
    "voicechannel.control_panel.footer": "Use buttons",
    "voicechannel.control_panel.description_template": (
        "owner={owner_mention}; soundboard={soundboard_status}"
    ),
    "voicechannel.control_panel.buttons.unlock_label": "Unlock",
    "voicechannel.control_panel.buttons.lock_label": "Lock",
    "voicechannel.control_panel.buttons.full_label": "Full",
    "voicechannel.control_panel.buttons.soundboard_label": "Soundboard",
    "voicechannel.control_panel.messages.unlock_success": "unlocked",
    "voicechannel.control_panel.messages.lock_success": "locked",
    "voicechannel.control_panel.messages.full_success": "full ok",
    "voicechannel.control_panel.messages.full_no_invitation": "no invitation",
    "voicechannel.control_panel.messages.full_channel_not_found": "channel not found",
    "voicechannel.control_panel.messages.full_message_deleted": "message deleted",
    "voicechannel.control_panel.messages.full_no_permission": "no permission",
    "voicechannel.control_panel.messages.full_error": "full error",
    "voicechannel.control_panel.messages.soundboard_enabled": "soundboard enabled",
    "voicechannel.control_panel.messages.soundboard_disabled": "soundboard disabled",
    "voicechannel.control_panel.messages.not_in_voice": "not in voice",
    "voicechannel.control_panel.messages.not_room_owner": "not owner",
    "voicechannel.control_panel.messages.permission_error": "permission error",
    "voicechannel.control_panel.messages.channel_not_found": "voice not found",
    "voicechannel.control_panel.messages.http_error": "http error",
    "voicechannel.control_panel.messages.unknown_error": "unknown error",
}

INVITATION_TEXT = {
    "invitation.roomfull_title": "[FULL]",
    "invitation.invite_embed_content_edited": (
        "voice={name}; url={url}; user={mention}; time={time}"
    ),
}


class FakeResponse:
    def __init__(self, events):
        self.events = events
        self.deferred = []

    async def defer(self, *, ephemeral=False, **kwargs):
        self.events.append(("defer", ephemeral))
        self.deferred.append({"ephemeral": ephemeral, **kwargs})


class FakeFollowup:
    def __init__(self, events):
        self.events = events
        self.messages = []

    async def send(self, content=None, *, ephemeral=False, **kwargs):
        self.events.append(("followup", content))
        self.messages.append({
            "content": content,
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakePanelMessage:
    def __init__(self, events):
        self.events = events
        self.edits = []

    async def edit(self, *, embed=None, view=None, **kwargs):
        self.events.append(("panel_edit", embed.title if embed else None))
        self.edits.append({
            "embed": embed,
            "view": view,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, *, user, message, events):
        self.user = user
        self.message = message
        self.response = FakeResponse(events)
        self.followup = FakeFollowup(events)


@dataclass
class FakeUser:
    id: int = 123
    display_name: str = "Zoyo"
    name: str = "zoyo_raw"
    mention: str = "<@123>"
    voice: object | None = None


class FakeOverwrite:
    def __init__(self):
        self.values = {}

    def update(self, **kwargs):
        self.values.update(kwargs)


class FakeVoiceChannel:
    def __init__(self, channel_id, events):
        self.id = channel_id
        self.name = "Alpha Room"
        self.events = events
        self.guild = SimpleNamespace(default_role=SimpleNamespace(id=1, name="@everyone"))
        self.permission_calls = []
        self._overwrite = FakeOverwrite()

    def overwrites_for(self, target):
        self.events.append(("overwrites_for", target.id))
        return self._overwrite

    async def set_permissions(self, target, **kwargs):
        self.events.append(("set_permissions", target.id, kwargs))
        self.permission_calls.append({
            "target": target,
            **kwargs,
        })


class FakeVoiceDB:
    def __init__(self, events):
        self.events = events
        self.room_type_updates = []
        self.soundboard_updates = []

    async def set_room_type(self, channel_id, room_type):
        self.events.append(("db_set_room_type", channel_id, room_type))
        self.room_type_updates.append((channel_id, room_type))

    async def set_soundboard(self, channel_id, enabled):
        self.events.append(("db_set_soundboard", channel_id, enabled))
        self.soundboard_updates.append((channel_id, enabled))


class FakeTeamupDB:
    def __init__(self, events, last_invitation):
        self.events = events
        self.last_invitation = last_invitation
        self.removed_invalid = []

    async def get_last_invitation_by_voice_channel(self, voice_channel_id):
        self.events.append(("db_last_invitation", voice_channel_id))
        return self.last_invitation

    async def remove_invalid_invitation(self, voice_channel_id):
        self.events.append(("db_remove_invalid", voice_channel_id))
        self.removed_invalid.append(voice_channel_id)


class FakeTeamupCog:
    def __init__(self, events, last_invitation):
        self.events = events
        self.db_manager = FakeTeamupDB(events, last_invitation)
        self.removed_from_display = []

    async def remove_teamup_from_display(self, user_id, voice_channel_id):
        self.events.append(("remove_display", user_id, voice_channel_id))
        self.removed_from_display.append((user_id, voice_channel_id))


class FakeTextChannel:
    def __init__(self, channel_id, message, events):
        self.id = channel_id
        self.name = "teamup"
        self.message = message
        self.events = events

    async def fetch_message(self, message_id):
        self.events.append(("fetch_message", self.id, message_id))
        return self.message


class FakeInvitationMessage:
    id = 444
    channel = SimpleNamespace(id=333, name="teamup")

    def __init__(self, embed, events):
        self.embeds = [embed]
        self.events = events
        self.edits = []

    async def edit(self, *, embed=None, view=None, **kwargs):
        self.events.append(("invitation_edit", embed.title if embed else None, view))
        self.edits.append({
            "embed": embed,
            "view": view,
            **kwargs,
        })


class FakeBot:
    def __init__(self, *, voice_channel, text_channel=None, teamup_cog=None):
        self.user = SimpleNamespace(avatar=None)
        self.voice_channel = voice_channel
        self.text_channel = text_channel
        self.teamup_cog = teamup_cog

    def get_channel(self, channel_id):
        if channel_id == self.voice_channel.id:
            return self.voice_channel
        if self.text_channel and channel_id == self.text_channel.id:
            return self.text_channel
        return None

    def get_cog(self, name):
        if name == "TeamupDisplayCog":
            return self.teamup_cog
        return None


def _install_translations(monkeypatch):
    monkeypatch.setattr(voice_views, "t", lambda key: VOICE_TEXT[key])
    monkeypatch.setattr(full_message, "t", lambda key: INVITATION_TEXT[key])
    monkeypatch.setattr(
        voice_views.config,
        "get_config",
        lambda name=None: {
            "control_panel": {
                "colors": {
                    "public": 0x00AA00,
                    "private": 0xAA0000,
                },
            },
        },
    )


def _voice_state(channel_id):
    return SimpleNamespace(channel=SimpleNamespace(id=channel_id))


def _build_view(monkeypatch, events, *, soundboard_enabled=True, room_type="public"):
    _install_translations(monkeypatch)
    voice_channel = FakeVoiceChannel(222, events)
    creator = FakeUser(123, "Creator", "creator", "<@123>", voice=_voice_state(222))
    db = FakeVoiceDB(events)
    bot = FakeBot(voice_channel=voice_channel)
    view = RoomControlPanelView(
        bot,
        voice_channel,
        creator,
        db,
        soundboard_enabled=soundboard_enabled,
        room_type=room_type,
    )
    return view, bot, voice_channel, creator, db


def test_lock_button_sets_private_permissions_db_and_refreshes_panel(monkeypatch):
    async def scenario():
        events = []
        view, _, voice_channel, creator, db = _build_view(monkeypatch, events)
        panel_message = FakePanelMessage(events)
        interaction = FakeInteraction(
            user=creator,
            message=panel_message,
            events=events,
        )

        await view.lock_callback(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "defer",
            "set_permissions",
            "db_set_room_type",
            "panel_edit",
            "followup",
        ]
        assert voice_channel.permission_calls[0]["connect"] is False
        assert db.room_type_updates == [(222, "private")]
        assert view.room_type == "private"
        assert panel_message.edits[0]["embed"].color.value == 0xAA0000
        assert interaction.followup.messages[0] == {
            "content": "locked",
            "ephemeral": True,
        }

    asyncio.run(scenario())


def test_unlock_button_sets_public_permissions_db_and_refreshes_panel(monkeypatch):
    async def scenario():
        events = []
        view, _, voice_channel, creator, db = _build_view(
            monkeypatch,
            events,
            room_type="private",
        )
        panel_message = FakePanelMessage(events)
        interaction = FakeInteraction(
            user=creator,
            message=panel_message,
            events=events,
        )

        await view.unlock_callback(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "defer",
            "set_permissions",
            "db_set_room_type",
            "panel_edit",
            "followup",
        ]
        assert voice_channel.permission_calls[0]["connect"] is True
        assert db.room_type_updates == [(222, "public")]
        assert view.room_type == "public"
        assert panel_message.edits[0]["embed"].color.value == 0x00AA00
        assert interaction.followup.messages[0]["content"] == "unlocked"
        assert interaction.followup.messages[0]["ephemeral"] is True

    asyncio.run(scenario())


def test_lock_button_rejects_user_outside_managed_voice_channel(monkeypatch):
    async def scenario():
        events = []
        view, _, voice_channel, _, db = _build_view(monkeypatch, events)
        user = FakeUser(456, "Other", "other", "<@456>", voice=_voice_state(999))
        interaction = FakeInteraction(
            user=user,
            message=FakePanelMessage(events),
            events=events,
        )

        await view.lock_callback(interaction)

        assert events == [
            ("defer", True),
            ("followup", "not in voice"),
        ]
        assert voice_channel.permission_calls == []
        assert db.room_type_updates == []

    asyncio.run(scenario())


def test_soundboard_button_toggles_permissions_db_and_embed_for_owner(monkeypatch):
    async def scenario():
        events = []
        view, _, voice_channel, creator, db = _build_view(
            monkeypatch,
            events,
            soundboard_enabled=True,
        )
        panel_message = FakePanelMessage(events)
        interaction = FakeInteraction(
            user=creator,
            message=panel_message,
            events=events,
        )

        await view.soundboard_callback(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "defer",
            "overwrites_for",
            "set_permissions",
            "db_set_soundboard",
            "panel_edit",
            "followup",
        ]
        assert voice_channel._overwrite.values == {"use_soundboard": False}
        assert voice_channel.permission_calls[0]["overwrite"] is voice_channel._overwrite
        assert db.soundboard_updates == [(222, False)]
        assert view.soundboard_enabled is False
        assert "soundboard=关闭" in panel_message.edits[0]["embed"].description
        assert interaction.followup.messages[0]["content"] == "soundboard disabled"

    asyncio.run(scenario())


def test_soundboard_button_rejects_non_owner_before_channel_lookup(monkeypatch):
    async def scenario():
        events = []
        view, _, voice_channel, _, db = _build_view(monkeypatch, events)
        user = FakeUser(456, "Other", "other", "<@456>", voice=_voice_state(222))
        interaction = FakeInteraction(
            user=user,
            message=FakePanelMessage(events),
            events=events,
        )

        await view.soundboard_callback(interaction)

        assert events == [
            ("defer", True),
            ("followup", "not owner"),
        ]
        assert voice_channel.permission_calls == []
        assert db.soundboard_updates == []

    asyncio.run(scenario())


def test_full_button_updates_invitation_with_shared_full_style_then_removes_display(monkeypatch):
    async def scenario():
        events = []
        view, bot, voice_channel, creator, _ = _build_view(monkeypatch, events)
        invitation_embed = discord.Embed(
            title="Need one",
            description=(
                "join https://discord.com/channels/111/222 "
                "from <@123> posted <t:1700000000:R>"
            ),
            color=discord.Color.blue(),
        )
        invitation_embed.add_field(name="note", value="keep", inline=False)
        invitation_message = FakeInvitationMessage(invitation_embed, events)
        text_channel = FakeTextChannel(333, invitation_message, events)
        last_invitation = {
            "invitation_channel_id": text_channel.id,
            "invitation_message_id": invitation_message.id,
        }
        teamup_cog = FakeTeamupCog(events, last_invitation)
        bot.text_channel = text_channel
        bot.teamup_cog = teamup_cog
        interaction = FakeInteraction(
            user=creator,
            message=FakePanelMessage(events),
            events=events,
        )

        await view.full_callback(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "defer",
            "db_last_invitation",
            "fetch_message",
            "invitation_edit",
            "remove_display",
            "followup",
        ]
        edit = invitation_message.edits[0]
        assert edit["view"] is None
        assert edit["embed"].title == "[FULL] ~~Need one~~"
        assert edit["embed"].description == (
            "voice=Alpha Room; "
            "url=https://discord.com/channels/111/222; "
            "user=<@123>; "
            "time=<t:1700000000:R>"
        )
        assert edit["embed"].fields[0].value == "keep"
        assert teamup_cog.removed_from_display == [(creator.id, voice_channel.id)]
        assert interaction.followup.messages[0]["content"] == "full ok"
        assert interaction.followup.messages[0]["ephemeral"] is True

    asyncio.run(scenario())


def test_full_button_without_invitation_returns_ephemeral_error(monkeypatch):
    async def scenario():
        events = []
        view, bot, _, creator, _ = _build_view(monkeypatch, events)
        bot.teamup_cog = FakeTeamupCog(events, last_invitation=None)
        interaction = FakeInteraction(
            user=creator,
            message=FakePanelMessage(events),
            events=events,
        )

        await view.full_callback(interaction)

        assert events == [
            ("defer", True),
            ("db_last_invitation", 222),
            ("followup", "no invitation"),
        ]
        assert interaction.followup.messages[0]["ephemeral"] is True

    asyncio.run(scenario())
