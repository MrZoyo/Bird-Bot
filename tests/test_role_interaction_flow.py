import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import discord

from bot.cogs.role import cog as role_cog_module
from bot.cogs.role import modals as role_modals
from bot.cogs.role import views as role_views
from bot.cogs.role.cog import RoleCog
from bot.cogs.role.modals import SignatureModal
from bot.cogs.role.views import AchievementRoleView, GenderView, SignatureView


ROLE_TEXT = {
    "role.role_no_progress_message": "no progress",
    "role.role_no_column_name_message": "no column",
    "role.role_no_achievement_message": "no achievement",
    "role.role_success_message": "awarded {name}",
    "role.role_remove_message": "removed {name}",
    "role.role_pickup_title": "Pick achievement",
    "role.role_pickup_footer": "Pickup footer",
    "role.gender_pickup_title": "Pick gender",
    "role.gender_tree_title": "Tree title",
    "role.gender_tree_description": "- Tree description",
    "role.gender_sakura_title": "Sakura title",
    "role.gender_sakura_description": "- Sakura description",
    "role.gender_ninja_title": "Ninja title",
    "role.gender_ninja_description": "- Ninja description",
    "role.gender_pickup_footer": "Gender footer",
    "role.gender_success_message": "gender awarded {name}",
    "role.gender_remove_message": "gender removed {name}",
    "role.signature.button_label": "Set signature",
    "role.signature.view_button_label": "View signature",
    "role.signature.modal_title": "Signature",
    "role.signature.modal_label": "Signature",
    "role.signature.modal_placeholder": "Write signature",
    "role.signature.pickup_title": "Signature panel",
    "role.signature.pickup_description": "max {max_length}; changes {max_changes}; days {cooldown_days}",
    "role.signature.pickup_footer": "Signature footer",
    "role.signature.no_permission_message": "need {required_time}, have {current_time}",
    "role.signature.disabled_message": "disabled",
    "role.signature.cooldown_message": "cooldown {signature}",
    "role.signature.success_message": "saved {signature}; remaining {remaining_times}",
    "role.signature.update_failed_message": "update failed",
}


class FakeResponse:
    def __init__(self, events):
        self.events = events
        self.deferred = []
        self.messages = []
        self.modals = []

    async def defer(self, *, ephemeral=False, **kwargs):
        self.events.append(("defer", ephemeral))
        self.deferred.append({"ephemeral": ephemeral, **kwargs})

    async def send_message(self, content=None, *, ephemeral=False, **kwargs):
        self.events.append(("response", content))
        self.messages.append({
            "content": content,
            "ephemeral": ephemeral,
            **kwargs,
        })

    async def send_modal(self, modal):
        self.events.append(("modal", type(modal).__name__))
        self.modals.append(modal)


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


class FakeInteraction:
    def __init__(self, *, user, guild=None, data=None, events):
        self.user = user
        self.guild = guild
        self.data = data or {}
        self.response = FakeResponse(events)
        self.followup = FakeFollowup(events)


@dataclass
class FakeRole:
    id: int
    name: str
    position: int

    def __ge__(self, other):
        return self.position >= other.position


class FakeGuild:
    def __init__(self, roles):
        self.roles = roles
        self.me = SimpleNamespace(top_role=FakeRole(999, "Bot", 100))

    def get_role(self, role_id):
        return next((role for role in self.roles if role.id == role_id), None)


@dataclass
class FakeMember:
    id: int
    display_name: str
    name: str
    mention: str
    guild: FakeGuild
    events: list
    roles: list = field(default_factory=list)

    async def add_roles(self, *roles, reason=None):
        self.events.append(("add_roles", [role.id for role in roles], reason))
        for role in roles:
            if role not in self.roles:
                self.roles.append(role)

    async def remove_roles(self, *roles, reason=None):
        self.events.append(("remove_roles", [role.id for role in roles], reason))
        self.roles = [role for role in self.roles if role not in roles]


class FakeRoleDB:
    def __init__(self, events, *, progress=0):
        self.events = events
        self.progress = progress

    async def get_user_achievement_progress(self, user_id, achievement_type):
        self.events.append(("db_progress", user_id, achievement_type))
        return self.progress


class FakeSignatureDB:
    def __init__(self, events):
        self.events = events
        self.signatures = []

    async def get_user_signature(self, user_id):
        self.events.append(("db_get_signature", user_id))
        return None

    async def find_available_time_slot(self, user_id, **kwargs):
        self.events.append(("db_find_slot", user_id, kwargs))
        return 1

    async def update_user_signature(self, user_id, signature, available_slot):
        self.events.append(("db_update_signature", user_id, signature, available_slot))
        self.signatures.append((user_id, signature, available_slot))
        return True

    async def get_signature_remaining_changes(self, user_id, **kwargs):
        self.events.append(("db_remaining", user_id, kwargs))
        return 2


class FakeBot:
    def __init__(self, role_cog):
        self.role_cog = role_cog
        self.guilds = []

    def get_cog(self, name):
        if name == "RoleCog":
            return self.role_cog
        return None


class FakeStoredRoleDB:
    async def get_all_role_views(self, table):
        return [(111, 222)]

    async def remove_role_view(self, message_id, channel_id, table):
        raise AssertionError("stored signature view should not be removed")


class FakeStoredMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeStoredChannel:
    id = 222
    name = "role-panels"

    def __init__(self, message):
        self.message = message

    async def fetch_message(self, message_id):
        assert message_id == 111
        return self.message


def _translate(key, **kwargs):
    text = ROLE_TEXT[key]
    return text.format(**kwargs) if kwargs else text


def _install_role_config(monkeypatch, role_db):
    monkeypatch.setattr(role_views, "t", _translate)
    monkeypatch.setattr(role_modals, "t", _translate)
    monkeypatch.setattr(role_views, "RoleDatabaseManager", lambda db_path: role_db)
    monkeypatch.setattr(
        role_views.config,
        "get_config",
        lambda name=None: {
            "main": {"db_path": "unused"},
            "achievements": {
                "achievements": [
                    {"type": "message", "threshold": 10, "name": "Chatter", "role_id": 10},
                    {"type": "message", "threshold": 50, "name": "Veteran", "role_id": 20},
                    {"type": "checkin_sum", "threshold": 1, "name": "Checkin", "role_id": 50},
                    {"type": "checkin_combo", "threshold": 1, "name": "Streak", "role_id": 60},
                ],
            },
            "role": {
                "role_type_name": [
                    {"name": "Messages", "type": "message"},
                    {"name": "Checkin", "type": "checkin_sum"},
                    {"name": "Streak", "type": "checkin_combo"},
                ],
                "achievement_start_role_id": 30,
                "social_start_role_id": None,
                "starsign_name": [],
                "mbti_name": [],
                "gender_name": [],
                "signature": {
                    "time_requirement": 60,
                    "helper_role_id": 40,
                    "max_length": 20,
                    "cooldown_days": 7,
                },
            },
        }[name],
    )
    monkeypatch.setattr(
        role_views.config,
        "is_feature_enabled",
        lambda feature_name, default=True: feature_name != "shop",
    )


def test_achievement_role_button_adds_start_role_then_highest_eligible_role(monkeypatch):
    async def scenario():
        events = []
        role_db = FakeRoleDB(events, progress=60)
        _install_role_config(monkeypatch, role_db)
        roles = [
            FakeRole(10, "Chatter", 10),
            FakeRole(20, "Veteran", 20),
            FakeRole(30, "Starter", 5),
        ]
        guild = FakeGuild(roles)
        member = FakeMember(123, "User", "user", "<@123>", guild, events)
        bot = FakeBot(role_cog=None)
        view = AchievementRoleView(bot)
        interaction = FakeInteraction(
            user=member,
            guild=guild,
            data={"custom_id": "message"},
            events=events,
        )

        await view.on_button_click(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "defer",
            "add_roles",
            "db_progress",
            "add_roles",
            "followup",
        ]
        assert events[1] == ("add_roles", [30], "Adding achievement start role")
        assert events[3] == ("add_roles", [20], "Adding achievement role")
        assert [role.id for role in member.roles] == [30, 20]
        assert interaction.followup.messages[0] == {
            "content": "awarded Veteran",
            "ephemeral": True,
        }

    asyncio.run(scenario())


def test_achievement_role_view_hides_disabled_feature_role_types(monkeypatch):
    events = []
    role_db = FakeRoleDB(events, progress=60)
    _install_role_config(monkeypatch, role_db)

    view = AchievementRoleView(FakeBot(role_cog=None))

    assert [
        child.custom_id
        for child in view.walk_children()
        if getattr(child, "custom_id", None) is not None
    ] == ["message"]
    assert [achievement["type"] for achievement in view.achievements] == [
        "message",
        "message",
    ]
    assert view.has_components_v2() is True
    container = view.to_components()[0]
    assert [component["type"] for component in container["components"]] == [10, 14, 9, 10]
    assert container["components"][0]["content"] == "### Pick achievement"
    assert container["components"][1]["divider"] is True
    sections = [component for component in container["components"] if component["type"] == 9]
    assert len(sections) == 1
    assert sections[0]["components"][0]["content"] == (
        "**Messages**\n- **Chatter** : `10`\n- **Veteran** : `50`"
    )
    assert sections[0]["accessory"]["label"] == "Messages"
    assert sections[0]["accessory"]["custom_id"] == "message"
    assert container["components"][-1]["content"] == "-# Pickup footer"


def test_gender_role_view_pairs_each_type_with_right_side_button(monkeypatch):
    events = []
    role_db = FakeRoleDB(events)
    _install_role_config(monkeypatch, role_db)
    original_get_config = role_views.config.get_config

    def get_config(name=None):
        base = original_get_config(name)
        if name == "role":
            return {
                **base,
                "gender_name": [
                    {"name": "Tree", "emoji": "🌳", "role_id": 1},
                    {"name": "Sakura", "emoji": "🌸", "role_id": 2},
                    {"name": "Ninja", "emoji": "🥷", "role_id": 3},
                ],
            }
        return base

    monkeypatch.setattr(role_views.config, "get_config", get_config)

    view = GenderView(FakeBot(role_cog=None))
    container = view.to_components()[0]
    sections = [component for component in container["components"] if component["type"] == 9]

    assert view.has_components_v2() is True
    assert [component["type"] for component in container["components"]] == [10, 14, 9, 14, 9, 14, 9, 10]
    assert container["components"][0]["content"] == "### Pick gender"
    assert container["components"][1]["divider"] is True
    assert [section["accessory"]["label"] for section in sections] == ["🌳", "🌸", "🥷"]
    assert [section["accessory"]["custom_id"] for section in sections] == ["Tree", "Sakura", "Ninja"]
    assert sections[0]["components"][0]["content"] == "**Tree title**\nTree description"
    assert container["components"][-1]["content"] == "-# Gender footer"


def test_signature_button_rejects_user_without_voice_time_before_modal(monkeypatch):
    async def scenario():
        events = []
        role_db = FakeRoleDB(events)
        _install_role_config(monkeypatch, role_db)
        role_cog = SimpleNamespace(
            role_config={
                "signature": {
                    "time_requirement": 60,
                    "helper_role_id": 40,
                    "max_length": 20,
                    "cooldown_days": 7,
                },
            },
            main_config={"db_path": "unused"},
        )
        view = SignatureView(FakeBot(role_cog))

        async def check_voice_time_requirement(user_id):
            events.append(("check_voice_time", user_id))
            return False, 12

        view.check_voice_time_requirement = check_voice_time_requirement
        interaction = FakeInteraction(
            user=SimpleNamespace(id=123),
            events=events,
        )

        await view.on_button_click(interaction)

        assert events == [
            ("check_voice_time", 123),
            ("response", "need 60, have 12"),
        ]
        assert interaction.response.messages[0]["ephemeral"] is True
        assert interaction.response.modals == []

    asyncio.run(scenario())


def test_signature_modal_updates_signature_before_success_followup(monkeypatch):
    async def scenario():
        events = []
        signature_db = FakeSignatureDB(events)
        monkeypatch.setattr(role_modals, "t", _translate)
        monkeypatch.setattr(role_modals, "RoleDatabaseManager", lambda db_path: signature_db)
        role_cog = SimpleNamespace(
            main_config={"db_path": "unused"},
            role_config={
                "signature": {
                    "cooldown_days": 14,
                },
            },
        )
        bot = FakeBot(role_cog)
        modal = SignatureModal(bot, max_length=20)
        modal.signature._value = "hello"
        interaction = FakeInteraction(
            user=SimpleNamespace(id=123),
            events=events,
        )

        await modal.on_submit(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "defer",
            "db_get_signature",
            "db_find_slot",
            "db_update_signature",
            "db_remaining",
            "followup",
        ]
        assert events[2] == ("db_find_slot", 123, {"cooldown_days": 14})
        assert events[4] == ("db_remaining", 123, {"cooldown_days": 14})
        assert signature_db.signatures == [(123, "hello", 1)]
        assert interaction.followup.messages[0] == {
            "content": "saved hello; remaining 2",
            "ephemeral": True,
        }

    asyncio.run(scenario())


def test_signature_view_restore_refreshes_embed_with_configured_cooldown(monkeypatch):
    async def scenario():
        monkeypatch.setattr(role_cog_module, "t", _translate)
        monkeypatch.setattr(role_views, "t", _translate)
        stored_message = FakeStoredMessage()
        stored_channel = FakeStoredChannel(stored_message)
        role_cog = SimpleNamespace(
            role_config={
                "signature": {
                    "max_length": 24,
                    "cooldown_days": 14,
                },
            },
            role_db=FakeStoredRoleDB(),
            bot=SimpleNamespace(
                user=SimpleNamespace(avatar=None),
                get_channel=lambda channel_id: stored_channel if channel_id == 222 else None,
            ),
        )
        role_cog._build_signature_pickup_embed = lambda: RoleCog._build_signature_pickup_embed(role_cog)

        await RoleCog.load_role_views(role_cog, table="signature_views")

        assert len(stored_message.edits) == 1
        edit = stored_message.edits[0]
        assert isinstance(edit["embed"], discord.Embed)
        assert edit["embed"].title == "Signature panel"
        assert edit["embed"].description == "max 24; changes 3; days 14"
        assert isinstance(edit["view"], SignatureView)

    asyncio.run(scenario())
