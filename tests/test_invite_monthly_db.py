import asyncio
from datetime import datetime, timezone

import pytest

from bot.utils.db_connect import connect_database
from bot.utils.invite_guard_db import InviteGuardDatabaseManager
from bot.utils.invite_monthly_db import InviteMonthlyDatabaseManager
from bot.utils.invite_months import month_bounds, month_key, shift_month
from bot.utils.shop_db import ShopDatabaseManager


UTC = timezone.utc
SEPTEMBER = datetime(2026, 9, 12, 12, tzinfo=UTC)
BERLIN = 'Europe/Berlin'


@pytest.mark.parametrize('key,start,end', [
    ('2026-01', '2025-12-31T23:00:00+00:00', '2026-01-31T23:00:00+00:00'),
    ('2026-03', '2026-02-28T23:00:00+00:00', '2026-03-31T22:00:00+00:00'),
    ('2026-09', '2026-08-31T22:00:00+00:00', '2026-09-30T22:00:00+00:00'),
    ('2026-10', '2026-09-30T22:00:00+00:00', '2026-10-31T23:00:00+00:00'),
    ('2026-12', '2026-11-30T23:00:00+00:00', '2026-12-31T23:00:00+00:00'),
])
def test_berlin_month_boundaries_handle_dst_and_year_rollover(key, start, end):
    assert tuple(value.isoformat() for value in month_bounds(key, BERLIN)) == (start, end)
    assert month_key(datetime.fromisoformat(start), BERLIN) == key
    assert month_key(datetime.fromisoformat(end), BERLIN) == shift_month(key, 1)


def test_opening_balance_imported_once_and_october_only_contains_new_credits(tmp_path):
    async def scenario():
        path = str(tmp_path / 'invite.db')
        db = InviteGuardDatabaseManager(path)
        monthly = InviteMonthlyDatabaseManager(path)
        await db.initialize_database()
        old = '2026-07-01T12:00:00+00:00'
        for member_id in [200, 201, 202]:
            await db.record_member_join(123, member_id, old)
        await db.attribute_member(123, 200, 100, 'a', old)
        await db.pool_attribute_members(123, [201, 202], [(100, 'b', 2)], old)

        await asyncio.gather(*(monthly.ensure_tracking(123, SEPTEMBER, BERLIN) for _ in range(2)))
        assert await monthly.get_leaderboard(123, '2026-09', BERLIN) == [{'user_id': 100, 'total_count': 3}]
        assert await monthly.get_leaderboard(123, '2026-07', BERLIN) == []
        assert await monthly.get_leaderboard(999, '2026-09', BERLIN) == []

        last_second = '2026-09-30T21:59:59+00:00'
        october = '2026-09-30T22:00:00+00:00'
        await db.record_member_join(123, 203, last_second)
        assert await db.attribute_member(123, 203, 100, 'a', last_second)
        assert not await db.attribute_member(123, 203, 100, 'a', october)
        for member_id in [204, 205]:
            await db.record_member_join(123, member_id, october)
        assert await db.pool_attribute_members(123, [204, 205], [(101, 'c', 2)], october)
        assert not await db.pool_attribute_members(123, [204, 205], [(101, 'c', 2)], october)
        await monthly.ensure_tracking(123, datetime.fromisoformat(october), BERLIN)
        assert await monthly.get_leaderboard(123, '2026-09', BERLIN) == [{'user_id': 100, 'total_count': 4}]
        assert await monthly.get_leaderboard(123, '2026-10', BERLIN) == [{'user_id': 101, 'total_count': 2}]
        assert await monthly.next_unsettled_month(123) == '2026-09'
        with pytest.raises(ValueError, match='timezone'):
            await monthly.ensure_tracking(123, SEPTEMBER, 'UTC')

    asyncio.run(scenario())


def test_monthly_ledger_failure_rolls_back_lifetime_attribution(tmp_path, monkeypatch):
    async def scenario():
        from bot.utils import invite_guard_db
        path = str(tmp_path / 'invite.db')
        db = InviteGuardDatabaseManager(path)
        monthly = InviteMonthlyDatabaseManager(path)
        await db.initialize_database()
        await monthly.ensure_tracking(123, SEPTEMBER, BERLIN)
        await db.record_member_join(123, 200, SEPTEMBER.isoformat())

        async def fail(*args):
            raise RuntimeError('ledger unavailable')

        monkeypatch.setattr(invite_guard_db, 'record_monthly_credit', fail)
        with pytest.raises(RuntimeError):
            await db.attribute_member(123, 200, 100, 'a', SEPTEMBER.isoformat())
        assert (await db.get_user(123, 200))['attribution_locked'] == 0
        assert await db.get_user(123, 100) is None
        assert await monthly.get_leaderboard(123, '2026-09', BERLIN) == []

    asyncio.run(scenario())


def test_freeze_results_once_with_top_ten_rewards_and_empty_month(tmp_path):
    async def scenario():
        path = str(tmp_path / 'invite.db')
        await InviteGuardDatabaseManager(path).initialize_database()
        db = InviteMonthlyDatabaseManager(path)
        await db.ensure_tracking(123, SEPTEMBER, BERLIN)
        winners = [dict(user_id=100+index, total_count=20-index) for index in range(10)]
        with pytest.raises(ValueError, match='before it ends'):
            await db.freeze_results(123, '2026-09', winners, SEPTEMBER)
        october = datetime(2026, 9, 30, 22, tzinfo=UTC)
        results = await asyncio.gather(*(db.freeze_results(123, '2026-09', winners, october) for _ in range(2)))
        assert sorted(results) == [False, True]
        rewards = await db.get_rewards(123)
        assert [row['points'] for row in rewards] == [200, 150, 100] + [60]*7
        assert [row['rank'] for row in rewards] == list(range(1, 11))
        assert await db.get_champion(123, '2026-09') == dict(user_id=100, total_count=20)
        assert await db.freeze_results(123, '2026-10', [], datetime(2026, 11, 1, tzinfo=UTC))
        assert await db.get_champion(123, '2026-10') is None
        assert await db.next_unsettled_month(123) == '2026-11'
        assert not await db.claim_notification(rewards[0])
        await db.mark_paid(rewards[0], october)
        assert await db.claim_notification(rewards[0])
        assert not await db.claim_notification(rewards[0])
        await db.finish_notification(rewards[0], 'sent', 12345)
        assert (await db.get_rewards(123))[0]['dm_message_id'] == 12345

    asyncio.run(scenario())


def test_idempotent_shop_payment_across_connections_and_restart(tmp_path):
    async def scenario():
        path = str(tmp_path / 'shop.db')
        first = ShopDatabaseManager(path)
        second = ShopDatabaseManager(path)
        await first.initialize_database()
        await second.initialize_database()
        args = (100, 200, 'invite_monthly_reward', 999)
        try:
            balances = await asyncio.gather(
                first.update_user_balance_with_record(*args, idempotency_key='invite-monthly:123:2026-09:100'),
                second.update_user_balance_with_record(*args, idempotency_key='invite-monthly:123:2026-09:100'),
            )
            assert balances == [200, 200]
            assert await first.get_user_balance(100) == 200
            assert await first.get_transaction_count(100) == 1
            with pytest.raises(ValueError, match='different transaction'):
                await second.update_user_balance_with_record(
                    100, 150, 'invite_monthly_reward', 999, idempotency_key='invite-monthly:123:2026-09:100',
                )
        finally:
            await first.close()
            await second.close()
        restarted = ShopDatabaseManager(path)
        try:
            await restarted.initialize_database()
            assert await restarted.update_user_balance_with_record(*args, idempotency_key='invite-monthly:123:2026-09:100') == 200
            assert await restarted.get_transaction_count(100) == 1
        finally:
            await restarted.close()

    asyncio.run(scenario())


def test_legacy_shop_transaction_migration_preserves_balance_and_history(tmp_path):
    async def scenario():
        path = str(tmp_path / 'legacy.db')
        async with connect_database(path) as db:
            await db.execute('CREATE TABLE shop_user_balance (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)')
            await db.execute('INSERT INTO shop_user_balance VALUES (100, 75)')
            await db.execute('''CREATE TABLE shop_transactions (id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL, timestamp TEXT NOT NULL, operation_type TEXT NOT NULL,
                amount INTEGER NOT NULL, new_balance INTEGER NOT NULL, operator_id INTEGER NOT NULL, note TEXT)''')
            await db.execute("INSERT INTO shop_transactions VALUES (1, 100, '2026-07-01', 'old', 75, 75, 999, 'legacy')")
            await db.commit()
        shop = ShopDatabaseManager(path)
        try:
            await shop.initialize_database()
            assert await shop.get_user_balance(100) == 75
            assert await shop.get_transaction_count(100) == 1
            assert await shop.update_user_balance_with_record(100, 200, 'invite_monthly_reward', 999, idempotency_key='new') == 275
        finally:
            await shop.close()

    asyncio.run(scenario())
