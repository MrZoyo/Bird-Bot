from datetime import datetime

from bot.cogs.privateroom.cog import PrivateRoomCog


def _build_cog() -> PrivateRoomCog:
    cog = object.__new__(PrivateRoomCog)
    cog.conf = {
        "renewal_extend_days": 31,
        "check_time_hour": 8,
    }
    return cog


def test_renewal_end_date_extends_future_room_from_current_end_date():
    cog = _build_cog()
    now = datetime(2026, 4, 23, 11, 44, 5)
    current_end_date = datetime(2026, 4, 25, 8, 0, 0)

    assert cog._calculate_renewal_end_date(
        current_end_date,
        now,
    ) == datetime(2026, 5, 26, 8, 0, 0)


def test_renewal_end_date_extends_stale_room_from_now():
    cog = _build_cog()
    now = datetime(2026, 4, 23, 11, 44, 5)
    current_end_date = datetime(2026, 3, 2, 8, 0, 0)

    assert cog._calculate_renewal_end_date(
        current_end_date,
        now,
    ) == datetime(2026, 5, 24, 8, 0, 0)


def test_renewal_days_remaining_never_displays_negative_days():
    cog = _build_cog()
    now = datetime(2026, 4, 23, 11, 44, 5)

    assert cog._renewal_days_remaining(datetime(2026, 4, 23, 8, 0, 0), now) == 0
