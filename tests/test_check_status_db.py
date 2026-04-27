import asyncio

from bot.utils.check_status_db import CheckStatusDatabaseManager


def run(coro):
    return asyncio.run(coro)


def test_record_status_and_fetch_by_date_prefix(tmp_path):
    db = CheckStatusDatabaseManager(str(tmp_path / "status.db"))

    run(db.initialize_database())
    run(db.record_status("2026-04-27 10:00:00", people=5, channels=2))
    run(db.record_status("2026-04-27 10:10:00", people=7, channels=3))
    run(db.record_status("2026-04-28 10:00:00", people=1, channels=1))

    rows = run(db.fetch_status_by_date_prefix("2026-04-27"))

    assert rows == [
        ("2026-04-27 10:00:00", 5, 2),
        ("2026-04-27 10:10:00", 7, 3),
    ]
    assert run(db.fetch_status_by_date_prefix("2026-04-29")) == []
