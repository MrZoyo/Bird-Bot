"""Calendar-month boundaries for invitation accounting."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def month_key(now: datetime, timezone_name: str) -> str:
    if now.tzinfo is None:
        raise ValueError('Monthly invite accounting requires an aware datetime')
    return now.astimezone(ZoneInfo(timezone_name)).strftime('%Y-%m')


def shift_month(key: str, months: int) -> str:
    year, month = map(int, key.split('-'))
    if not 1 <= month <= 12:
        raise ValueError('Invalid calendar month')
    year, index = divmod(year * 12 + month - 1 + months, 12)
    return f'{year:04d}-{index + 1:02d}'


def month_bounds(key: str, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    year, month = map(int, key.split('-'))
    next_year, next_month = map(int, shift_month(key, 1).split('-'))
    return (
        datetime(year, month, 1, tzinfo=zone).astimezone(timezone.utc),
        datetime(next_year, next_month, 1, tzinfo=zone).astimezone(timezone.utc),
    )
