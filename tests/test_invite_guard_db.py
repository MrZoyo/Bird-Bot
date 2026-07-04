import asyncio

from bot.utils.invite_guard_db import InviteGuardDatabaseManager, InviteLinkRecord


NOW = "2026-07-04T12:00:00+00:00"
LATER = "2026-07-04T12:05:00+00:00"


def test_invite_links_sync_and_mark_inactive(tmp_path):
    async def scenario():
        db = InviteGuardDatabaseManager(str(tmp_path / "invite.db"))
        await db.initialize_database()

        first = InviteLinkRecord(
            guild_id=1,
            code="abc",
            channel_id=10,
            inviter_id=100,
            created_at=NOW,
            max_age=3600,
            max_uses=0,
            uses=1,
            temporary=False,
            ignored=False,
        )
        summary = await db.sync_invite_links(1, [first], NOW)
        assert summary.scanned == 1
        assert summary.inserted == 1
        assert summary.updated == 0
        assert summary.marked_inactive == 0

        second = InviteLinkRecord(
            guild_id=1,
            code="abc",
            channel_id=10,
            inviter_id=100,
            created_at=NOW,
            max_age=3600,
            max_uses=0,
            uses=3,
            temporary=False,
            ignored=True,
        )
        summary = await db.sync_invite_links(1, [second], LATER)
        link = await db.get_invite_link(1, "abc")
        assert summary.updated == 1
        assert link["previous_uses"] == 1
        assert link["uses"] == 3
        assert link["ignored"] == 1

        summary = await db.sync_invite_links(1, [], LATER)
        link = await db.get_invite_link(1, "abc")
        assert summary.marked_inactive == 1
        assert link["active"] == 0
        assert link["deleted_at"] == LATER

    asyncio.run(scenario())


def test_invite_user_attribution_locks_and_counts_once(tmp_path):
    async def scenario():
        db = InviteGuardDatabaseManager(str(tmp_path / "invite.db"))
        await db.initialize_database()

        user = await db.record_member_join(1, 200, NOW)
        assert user["join_count"] == 1
        assert user["attribution_status"] == "unattributed"

        assert await db.attribute_member(1, 200, 100, "abc", NOW) is True
        assert await db.attribute_member(1, 200, 101, "def", LATER) is False

        invited = await db.get_user(1, 200)
        inviter = await db.get_user(1, 100)
        assert invited["invited_by_user_id"] == 100
        assert invited["invited_by_code"] == "abc"
        assert invited["attribution_locked"] == 1
        assert invited["allow_reattribution"] == 0
        assert inviter["invited_count"] == 1

        await db.record_member_leave(1, 200, LATER)
        left = await db.get_user(1, 200)
        assert left["leave_count"] == 1
        assert (await db.get_user(1, 100))["invited_count"] == 1

    asyncio.run(scenario())


def test_ignored_or_unknown_status_can_be_reattributed_later(tmp_path):
    async def scenario():
        db = InviteGuardDatabaseManager(str(tmp_path / "invite.db"))
        await db.initialize_database()

        await db.record_member_join(1, 200, NOW)
        assert await db.set_member_attribution_status(
            1,
            200,
            "ignored",
            code="birdgaming",
            allow_reattribution=True,
            now=NOW,
        ) is True
        ignored = await db.get_user(1, 200)
        assert ignored["attribution_status"] == "ignored"
        assert ignored["attribution_locked"] == 0
        assert ignored["allow_reattribution"] == 1

        assert await db.attribute_member(1, 200, 100, "abc", LATER) is True
        attributed = await db.get_user(1, 200)
        inviter = await db.get_user(1, 100)
        assert attributed["attribution_status"] == "attributed"
        assert attributed["attribution_locked"] == 1
        assert inviter["invited_count"] == 1

    asyncio.run(scenario())


def test_repair_detects_count_mismatch(tmp_path):
    async def scenario():
        db = InviteGuardDatabaseManager(str(tmp_path / "invite.db"))
        await db.initialize_database()

        await db.record_member_join(1, 200, NOW)
        await db.attribute_member(1, 200, 100, "abc", NOW)

        mismatches = await db.find_count_mismatches(1)
        assert mismatches == []

    asyncio.run(scenario())


def test_pool_attribute_members_locks_members_and_credits_inviters(tmp_path):
    async def scenario():
        db = InviteGuardDatabaseManager(str(tmp_path / "invite.db"))
        await db.initialize_database()

        await db.record_member_join(1, 200, NOW)
        await db.record_member_join(1, 201, NOW)

        ok = await db.pool_attribute_members(
            1,
            [200, 201],
            [(100, "abc", 1), (101, "def", 1)],
            NOW,
        )
        assert ok is True

        member_a = await db.get_user(1, 200)
        member_b = await db.get_user(1, 201)
        for member in (member_a, member_b):
            assert member["attribution_status"] == "pooled"
            assert member["attribution_locked"] == 1
            assert member["allow_reattribution"] == 0
            assert member["invited_by_user_id"] is None
            assert member["invited_by_code"] is None

        inviter_a = await db.get_user(1, 100)
        inviter_b = await db.get_user(1, 101)
        assert inviter_a["pooled_count"] == 1
        assert inviter_a["invited_count"] == 0
        assert inviter_b["pooled_count"] == 1

    asyncio.run(scenario())


def test_pool_attribute_members_rolls_back_when_member_already_locked(tmp_path):
    async def scenario():
        db = InviteGuardDatabaseManager(str(tmp_path / "invite.db"))
        await db.initialize_database()

        await db.record_member_join(1, 200, NOW)
        await db.record_member_join(1, 201, NOW)
        # Lock 201 ahead of time (e.g. already attributed by another path).
        assert await db.attribute_member(1, 201, 999, "zzz", NOW) is True

        ok = await db.pool_attribute_members(
            1,
            [200, 201],
            [(100, "abc", 1), (101, "def", 1)],
            NOW,
        )
        assert ok is False

        member_a = await db.get_user(1, 200)
        assert member_a["attribution_status"] == "unattributed"
        assert member_a["attribution_locked"] == 0
        inviter_a = await db.get_user(1, 100)
        assert inviter_a is None

    asyncio.run(scenario())


def test_get_leaderboard_orders_by_invited_plus_pooled_count(tmp_path):
    async def scenario():
        db = InviteGuardDatabaseManager(str(tmp_path / "invite.db"))
        await db.initialize_database()

        await db.record_member_join(1, 200, NOW)
        await db.attribute_member(1, 200, 100, "abc", NOW)  # inviter 100: invited_count=1

        await db.record_member_join(1, 201, NOW)
        await db.record_member_join(1, 202, NOW)
        await db.pool_attribute_members(
            1,
            [201, 202],
            [(101, "def", 2)],
            NOW,
        )  # inviter 101: pooled_count=2

        rows = await db.get_leaderboard(1, 10)
        assert [row["user_id"] for row in rows] == [101, 100]
        assert rows[0]["total_count"] == 2
        assert rows[0]["pooled_count"] == 2
        assert rows[0]["invited_count"] == 0
        assert rows[1]["total_count"] == 1

    asyncio.run(scenario())


def test_get_user_includes_pooled_count_for_invite_check_user(tmp_path):
    async def scenario():
        db = InviteGuardDatabaseManager(str(tmp_path / "invite.db"))
        await db.initialize_database()

        await db.record_member_join(1, 200, NOW)
        await db.record_member_join(1, 201, NOW)
        await db.pool_attribute_members(1, [200, 201], [(100, "abc", 2)], NOW)

        inviter = await db.get_user(1, 100)
        assert inviter["pooled_count"] == 2
        assert inviter["invited_count"] == 0

        member = await db.get_user(1, 200)
        assert member["pooled_count"] == 0
        assert member["attribution_status"] == "pooled"

    asyncio.run(scenario())
