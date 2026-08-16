import asyncio
from types import SimpleNamespace

from bot.cogs.create_invitation import cog as invitation_cog
from bot.cogs.create_invitation.cog import (
    CreateInvitationCog,
    find_teamup_keyword_matches,
    is_single_person_waiting,
)


class FakeMessage:
    def __init__(self, content):
        self.content = content
        self.author = SimpleNamespace(
            id=123,
            bot=False,
            voice=None,
            mention="<@123>",
        )
        self.channel = SimpleNamespace(id=456)
        self.guild = SimpleNamespace(id=789)
        self.replies = []

    async def reply(self, content, **kwargs):
        self.replies.append({"content": content, **kwargs})


def test_single_person_waiting_requires_a_basic_teamup_match():
    cases = {
        "一等全世界": True,
        "1q4": True,
        "１Q五": True,
        "缺1": False,
        "等2": False,
        "21q4": False,
        "稍微一等": False,
        "1等": False,
        "一q": False,
    }

    for content, expected in cases.items():
        matches = find_teamup_keyword_matches(content)
        assert is_single_person_waiting(content, matches) is expected

    assert find_teamup_keyword_matches("稍微一等") == []
    assert find_teamup_keyword_matches("1等") == []
    assert find_teamup_keyword_matches("一q") == []


def test_messages_outside_voice_use_contextual_room_prompt(monkeypatch):
    async def scenario():
        monkeypatch.setattr(invitation_cog, "log_keyword_detection", lambda *args: None)
        monkeypatch.setattr(
            invitation_cog,
            "DefaultRoomView",
            lambda bot, url: SimpleNamespace(bot=bot, url=url),
        )

        bot = SimpleNamespace(user=SimpleNamespace(id=999))
        cog = object.__new__(CreateInvitationCog)
        cog.bot = bot
        cog.conf = {"ignore_channel_ids": []}
        cog.ignore_user_ids = []
        cog.ignore_channel_message = "ignored"
        cog.default_create_room_channel_id = 321
        cog.single_person_waiting_response = "{mention}，不如你先来发车~"
        cog.illegal_team_response = "{mention}，本频道不允许私拉，先创个房间吧~"

        cases = {
            "一等全世界": "<@123>，不如你先来发车~",
            "1q4": "<@123>，不如你先来发车~",
            "hks-q4": "<@123>，本频道不允许私拉，先创个房间吧~",
            "HKS-q4": "<@123>，本频道不允许私拉，先创个房间吧~",
            "缺1": "<@123>，本频道不允许私拉，先创个房间吧~",
            "等2": "<@123>，本频道不允许私拉，先创个房间吧~",
        }
        for content, expected in cases.items():
            message = FakeMessage(content)
            await cog.on_message(message)

            assert len(message.replies) == 1
            assert message.replies[0]["content"] == expected
            assert message.replies[0]["view"].url.endswith("/789/321")

        for content in ("稍微一等", "1等", "一q", "abc-q4"):
            message = FakeMessage(content)
            await cog.on_message(message)
            assert message.replies == []

    asyncio.run(scenario())
