import asyncio
import re
from types import SimpleNamespace

from bot.cogs.teamup_display.cog import TeamupDisplayCog
from bot.cogs.teamup_display.rendering import fit_sections, text_length
from bot.utils.db_connect import connect_database
from bot.utils.invitation_db import InvitationDatabaseManager
from bot.utils.teamup_display_manager import TeamupDisplayManager


async def publish(db, room, *, age_seconds=0, content='缺1', game_type=None):
    row = await db.prepare(user_id=1, channel_id=20, voice_channel_id=room,
                           content=content, game_type=game_type)
    await db.activate(row['id'], row['id'] + 100)
    async with connect_database(db.db_path) as conn:
        await conn.execute("UPDATE teamup_invitations SET created_at=datetime('now', ?) WHERE id=?",
                           (f'-{age_seconds} seconds', row['id']))
        await conn.commit()
    return row


def test_display_expiry_boundary_is_read_only_and_survives_restart(tmp_path):
    async def scenario():
        path = str(tmp_path / 'invites.db')
        db = InvitationDatabaseManager(path)
        await db.initialize()
        fresh = await publish(db, 10, age_seconds=240)
        boundary = await publish(db, 11, age_seconds=300)
        old = await publish(db, 12, age_seconds=8 * 86400)
        ended = await publish(db, 13)
        await db.end(ended['id'])
        pending = await db.prepare(user_id=1, channel_id=20, voice_channel_id=14, content='pending')
        before = [await db.get(r['id']) for r in [fresh, boundary, old, ended, pending]]

        board = TeamupDisplayManager(path)
        await board.init_tables()
        await board.cleanup_expired_invitations()
        assert [r['id'] for r in await board.get_active_invitations()] == [fresh['id']]
        assert [r['id'] for r in await board.get_active_invitations(6)] == [boundary['id'], fresh['id']]
        assert [await db.get(r['id']) for r in [fresh, boundary, old, ended, pending]] == before
        restarted = TeamupDisplayManager(path)
        assert [r['id'] for r in await restarted.get_active_invitations()] == [fresh['id']]
        assert await db.end(old['id'])  # Hidden invitations remain operable.
    asyncio.run(scenario())


def test_same_room_republish_restarts_display_window(tmp_path):
    async def scenario():
        path = str(tmp_path / 'invites.db')
        db = InvitationDatabaseManager(path)
        await db.initialize()
        old = await publish(db, 10, age_seconds=600)
        board = TeamupDisplayManager(path)
        assert await board.get_active_invitations() == []
        new = await publish(db, 10)
        assert [r['id'] for r in await board.get_active_invitations()] == [new['id']]
        assert (await db.get(old['id']))['end_reason'] == 'superseded'
        assert not await db.end(old['id'])
        assert (await db.current(10))['id'] == new['id']
    asyncio.run(scenario())


def test_overflow_keeps_complete_entries_links_and_counts_omissions():
    lines = [f'🔍 `招募{i}😀`\n🏠 2 人 | ⏳ <t:1790880000:R>\n📍https://discord.com/channels/123456789012345678/{i:018}'
             for i in range(60)]
    description = fit_sections([('游戏一', lines[:40]), ('游戏二', lines[40:])])
    shown = re.findall(r'https://discord.com/channels/\d+/(\d+)', description)
    assert 0 < len(shown) < 60
    assert text_length(description) <= 4096
    assert len(description) <= 4096
    assert shown == [f'{i:018}' for i in range(len(shown))]
    assert f'另有 {60 - len(shown)} 条' in description
    assert description.count('`') == 2 * len(shown)
    assert all(line in description for line in lines[:len(shown)])
    assert '游戏二' not in description or lines[40] in description


def test_fitting_entries_keep_existing_layout_and_oversized_single_entry_is_safe():
    assert fit_sections([('游戏一', ['first', 'second']), ('游戏二', ['third'])]) == (
        '\n**游戏一**\nfirst\n\nsecond\n\n**游戏二**\nthird'
    )
    description = fit_sections([('游戏', ['😀' * 2500])])
    assert '另有 1 条' in description
    assert text_length(description) <= 4096
    assert '**游戏**' not in description


def test_real_board_render_hides_old_rows_and_bounds_busy_board(tmp_path):
    async def scenario():
        path = str(tmp_path / 'invites.db')
        manager = TeamupDisplayManager(path)
        await manager.init_tables()
        db = InvitationDatabaseManager(path)
        old = await publish(db, 999, age_seconds=900, content='OLD_SENTINEL')
        for room in range(60):
            await publish(db, 1000 + room, content='😀' * 50)
        cog = object.__new__(TeamupDisplayCog)
        cog.bot = SimpleNamespace(
            user=SimpleNamespace(avatar=None), get_user=lambda _: None,
            get_channel=lambda cid: SimpleNamespace(id=cid, guild=SimpleNamespace(id=123456789012345678), members=[1, 2]),
        )
        cog.db_manager = manager
        cog.invitation_expire_minutes = 5
        cog.max_content_length = 50
        cog.embed_color = 10039500
        cog.emojis = dict(search='🔍', players='🏠', time='⏳', link='📍')
        embed = await cog.create_display_embed()
        assert 'OLD_SENTINEL' not in embed.description
        assert text_length(embed.description) <= 4096
        assert text_length(embed.title + embed.description + embed.footer.text) <= 6000
        assert '暂未展示' in embed.description
        assert (await db.get(old['id']))['status'] == 'active'
    asyncio.run(scenario())
