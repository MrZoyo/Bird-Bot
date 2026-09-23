import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.cogs.privateroom.cog import PrivateRoomCog
from bot.cogs.privateroom.views import PrivateRoomShopView
from bot.utils.i18n import t


@pytest.mark.parametrize(('configured', 'booster', 'bonus', 'cost'), [
    (None, True, 30, 480),
    (30, True, 30, 480),
    (0, True, 0, 600),
    (20, True, 20, 520),
    (None, False, 0, 600),
])
def test_booster_bonus_matches_shop_text_and_discount(configured, booster, bonus, cost):
    async def scenario():
        cog = object.__new__(PrivateRoomCog)
        cog.bot = SimpleNamespace(user=SimpleNamespace(avatar=None))
        cog.conf = dict(points_cost=600, voice_hours_threshold=150, room_duration_days=31, max_rooms=40)
        if configured is not None:
            cog.conf['booster_discount_hours'] = configured
        cog.get_last_month_voice_hours = AsyncMock(return_value=0)
        cog.is_booster = AsyncMock(return_value=booster)
        result = await cog.calculate_discount(123)
        assert result[3] == cost
        assert result[5] == bonus
        display_bonus = configured if configured is not None else 30
        expected = t('privateroom.messages.shop_description').format(
            points_cost=600, duration=31, hours_threshold=150, booster_hours=display_bonus,
            available_rooms=40, max_rooms=40,
        )
        panel = PrivateRoomShopView(cog).to_components()
        assert expected in panel[0]['components'][0]['content']

    asyncio.run(scenario())
