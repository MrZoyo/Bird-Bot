import asyncio
from types import SimpleNamespace

from bot.cogs.achievement import views as achievement_views
from bot.cogs.achievement.views import ConfirmationView, RankView


ACHIEVEMENT_TEXT = {
    "achievements.rank.all_button_label": "All",
    "achievements.achievements_ranking_title": "Rankings",
    "achievements.rank.embed_title_single": "Rank: {type_name}",
    "achievements.rank.embed_title_date_format": "{title} ({year}-{month})",
    "achievements.rank.no_data_message": "No data",
    "achievements.rank.rank_prefix": "#{rank}",
    "achievements.rank.pagination_field_name": "{start}-{end}",
}


class FakeResponse:
    def __init__(self, events):
        self.events = events
        self.deferred = []
        self.edits = []

    async def defer(self, *, ephemeral=False, **kwargs):
        self.events.append(("defer", ephemeral))
        self.deferred.append({"ephemeral": ephemeral, **kwargs})

    async def edit_message(self, *, content=None, view=None, **kwargs):
        self.events.append(("response_edit", content, type(view).__name__ if view else None))
        self.edits.append({
            "content": content,
            "view": view,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, *, user=None, data=None, events):
        self.user = user or SimpleNamespace(id=1)
        self.data = data or {}
        self.response = FakeResponse(events)
        self.events = events
        self.original_edits = []

    async def edit_original_response(self, *, content=None, embed=None, view=None, **kwargs):
        self.events.append(("edit_original", content or (embed.title if embed else None)))
        self.original_edits.append({
            "content": content,
            "embed": embed,
            "view": view,
            **kwargs,
        })


class FakeAchievementCog:
    def __init__(self, *, hidden_types=None):
        self.hidden_types = hidden_types or set()

    def is_achievement_type_visible(self, achievement_type):
        return achievement_type not in self.hidden_types

    def get_visible_achievement_rankings(self):
        return [
            ranking
            for ranking in [
                {"type": "message", "name": "Messages"},
                {"type": "time_spent", "name": "Voice Time"},
                {"type": "checkin_sum", "name": "Checkins"},
                {"type": "checkin_combo", "name": "Checkin Streak"},
            ]
            if self.is_achievement_type_visible(ranking["type"])
        ]

    def get_visible_achievement_type_names(self):
        return {
            achievement_type: label
            for achievement_type, label in {
                "message": "Messages",
                "time_spent": "Voice Time",
                "checkin_sum": "Checkins",
                "checkin_combo": "Checkin Streak",
            }.items()
            if self.is_achievement_type_visible(achievement_type)
        }


class FakeBot:
    def __init__(self, achievement_cog):
        self.achievement_cog = achievement_cog
        self.users = {
            101: SimpleNamespace(id=101, mention="<@101>"),
            102: SimpleNamespace(id=102, mention="<@102>"),
        }

    def get_cog(self, name):
        if name == "AchievementCog":
            return self.achievement_cog
        return None

    def get_user(self, user_id):
        return self.users.get(user_id)


class FakeAchievementDB:
    def __init__(self, events, *, apply_success=True):
        self.events = events
        self.apply_success = apply_success
        self.applied = []
        self.logged = []

    async def apply_manual_changes(self, member_id, changes, operation):
        self.events.append(("db_apply", member_id, changes, operation))
        self.applied.append((member_id, changes, operation))
        return self.apply_success

    async def log_manual_operation(self, operator_id, member_id, operation, changes):
        self.events.append(("db_log", operator_id, member_id, operation, changes))
        self.logged.append((operator_id, member_id, operation, changes))


def _install_achievement_config(monkeypatch):
    def translate(key, **kwargs):
        text = ACHIEVEMENT_TEXT[key]
        return text.format(**kwargs) if kwargs else text

    monkeypatch.setattr(achievement_views, "t", translate)
    monkeypatch.setattr(
        achievement_views,
        "rank_type_button_labels",
        lambda: {
            "message": "Messages",
            "time_spent": "Time",
        },
    )
    monkeypatch.setattr(
        achievement_views.config,
        "get_config",
        lambda name=None: {
            "achievements_ranking_emoji": ["1.", "2.", "3."],
        },
    )


def test_confirmation_button_applies_changes_logs_then_edits_original(monkeypatch):
    async def scenario():
        _install_achievement_config(monkeypatch)
        events = []
        db = FakeAchievementDB(events)
        bot = FakeBot(FakeAchievementCog())
        view = ConfirmationView(
            bot,
            member_id=555,
            reactions=2,
            messages=3,
            time_spent=120,
            operation="increase",
            db_manager=db,
        )
        interaction = FakeInteraction(user=SimpleNamespace(id=999), events=events)

        await view.children[0].callback(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "response_edit",
            "db_apply",
            "db_log",
            "edit_original",
        ]
        expected_changes = {
            "message_count": 3,
            "reaction_count": 2,
            "time_spent": 120,
        }
        assert db.applied == [(555, expected_changes, "increase")]
        assert db.logged == [(999, 555, "increase", expected_changes)]
        assert interaction.original_edits[0]["content"] == "**Operation increase complete!**"

    asyncio.run(scenario())


def test_rank_type_button_keeps_underscored_time_spent_type(monkeypatch):
    async def scenario():
        _install_achievement_config(monkeypatch)
        events = []
        bot = FakeBot(FakeAchievementCog())
        view = RankView(
            bot,
            all_rankings={
                "message": [(101, 12)],
                "time_spent": [(101, 900), (102, 120)],
            },
        )
        interaction = FakeInteraction(
            data={"custom_id": "type_time_spent"},
            events=events,
        )

        await view.type_button_callback(interaction)

        assert events == [
            ("defer", False),
            ("edit_original", "Rank: Voice Time"),
        ]
        embed = interaction.original_edits[0]["embed"]
        assert embed.title == "Rank: Voice Time"
        assert embed.fields[0].name == "1-2"
        assert "<@101> - 15" in embed.fields[0].value
        assert "<@102> - 2" in embed.fields[0].value

    asyncio.run(scenario())


def test_rank_view_hides_shop_types_when_shop_feature_is_disabled(monkeypatch):
    _install_achievement_config(monkeypatch)
    bot = FakeBot(FakeAchievementCog(
        hidden_types={"checkin_sum", "checkin_combo"},
    ))

    view = RankView(bot, all_rankings={})

    assert [button.custom_id for button in view.type_buttons] == [
        "type_message",
        "type_time_spent",
    ]
    assert [str(button.emoji) for button in view.type_buttons] == ["🟡", "🔵"]
