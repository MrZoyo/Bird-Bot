import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from bot.cogs.create_invitation import lifecycle as lifecycle_module
from bot.cogs.create_invitation.lifecycle import InvitationLifecycle
from bot.cogs.create_invitation.views import InvitationFullButton, LegacyInvitationFullButton
from bot.cogs.voice_channel.views import RoomControlPanelView
from bot.utils.db_connect import connect_database
from bot.utils.invitation_db import InvitationDatabaseManager
from bot.utils.teamup_display_manager import TeamupDisplayManager


async def prepare(db, *, user_id=1, room=10):
    return await db.prepare(user_id=user_id, channel_id=20, voice_channel_id=room, content='缺1')


def test_lifecycle_survives_expiry_restart_and_stale_end(tmp_path):
    async def scenario():
        path = str(tmp_path / 'invites.db')
        db = InvitationDatabaseManager(path)
        await db.initialize()
        a = await prepare(db)
        assert await db.activate(a['id'], 101)
        # Both the old five-minute expiry and 600-second view lifetime have elapsed.
        async with connect_database(path) as conn:
            await conn.execute("UPDATE teamup_invitations SET created_at=datetime('now','-2 hours'), expires_at=datetime('now','-1 hour')")
            await conn.commit()
        restarted = InvitationDatabaseManager(path)
        await restarted.initialize()
        board = TeamupDisplayManager(path)
        await board.init_tables()
        await board.cleanup_expired_invitations()
        assert [row['id'] for row in await board.get_active_invitations()] == [a['id']]
        b = await prepare(restarted, user_id=2)
        assert await restarted.activate(b['id'], 102)
        assert not await restarted.end(a['id'])
        assert (await restarted.current(10))['id'] == b['id']
        assert (await restarted.get(a['id']))['end_reason'] == 'superseded'
        assert [row['id'] for row in await restarted.pending_sync()] == [a['id']]
        assert await restarted.end(b['id'])
        assert await restarted.current(10) is None
    asyncio.run(scenario())


def test_concurrent_publish_and_end_never_delete_another_generation(tmp_path):
    async def scenario():
        db = InvitationDatabaseManager(str(tmp_path / 'invites.db'))
        await db.initialize()
        a, b = await prepare(db), await prepare(db)
        await asyncio.gather(db.activate(b['id'], 102), db.activate(a['id'], 101))
        assert [row['id'] for row in await db.active()] == [b['id']]
        assert not await db.end(a['id'])
        assert sorted(await asyncio.gather(db.end(b['id']), db.end(b['id']))) == [False, True]
        c = await prepare(db)
        await db.activate(c['id'], 103)
        assert not await db.activate(a['id'], 101)
        assert (await db.current(10))['id'] == c['id']
    asyncio.run(scenario())


def test_legacy_migration_keeps_only_identifiable_latest_live_invite(tmp_path):
    async def scenario():
        path = str(tmp_path / 'legacy.db')
        async with connect_database(path) as conn:
            await conn.execute('''CREATE TABLE teamup_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, channel_id INTEGER,
                voice_channel_id INTEGER, message_content TEXT, player_count INTEGER,
                game_type TEXT, created_at TEXT, expires_at TEXT,
                invitation_message_id INTEGER, invitation_channel_id INTEGER)''')
            for room, msg, expiry in [(10, 101, '+5 minutes'), (10, 102, '+5 minutes'),
                                      (11, 103, '-1 minute'), (12, None, '+5 minutes'),
                                      (13, 104, '+5 minutes')]:
                await conn.execute('''INSERT INTO teamup_invitations VALUES
                    (NULL,1,20,?,'old',1,NULL,datetime('now','localtime'),
                    datetime('now','localtime',?),?,20)''', (room, expiry, msg))
            await conn.execute('UPDATE teamup_invitations SET invitation_channel_id=NULL WHERE voice_channel_id=13')
            await conn.commit()
        db = InvitationDatabaseManager(path)
        await db.initialize()
        assert [r['invitation_message_id'] for r in await db.active()] == [102]
        assert {r['invitation_message_id'] for r in await db.pending_sync()} == {101, 103}
        assert (await db.get(5))['message_sync'] == 'blocked'
        # Running either manager's initialization again must not revive ended rows.
        await db.end(2)
        await TeamupDisplayManager(path).init_tables()
        assert await db.active() == []
    asyncio.run(scenario())


class Message:
    def __init__(self, message_id, channel, bot_user):
        self.id = message_id
        self.channel = channel
        self.author = bot_user
        self.embeds = [discord.Embed(title='缺1', description='join https://discord.com/channels/30/10 from <@1>')]
        self.components = []
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        if kwargs.get('embed'):
            self.embeds = [kwargs['embed']]
        self.view = kwargs.get('view')


async def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle_module, 't', lambda key: key)
    db = InvitationDatabaseManager(str(tmp_path / 'invites.db'))
    await db.initialize()
    guild = SimpleNamespace(id=30)
    room = SimpleNamespace(id=10, name='Room', guild=guild, members=[])
    text_channel = SimpleNamespace(id=20, name='Teamup')
    bot_user = SimpleNamespace(id=99)
    author = SimpleNamespace(id=1, name='Poster', display_name='Poster', voice=SimpleNamespace(channel=room))
    other = SimpleNamespace(id=2, name='Member', display_name='Member', voice=SimpleNamespace(channel=room))
    board = SimpleNamespace(refresh_all_boards=AsyncMock())
    bot = SimpleNamespace(user=bot_user, get_channel=lambda cid: room if cid == 10 else text_channel)
    lifecycle = InvitationLifecycle(bot, db, None)
    cog = SimpleNamespace(lifecycle=lifecycle)
    bot.get_cog = lambda name: cog if name == 'CreateInvitationCog' else board if name == 'TeamupDisplayCog' else None
    row = await prepare(db)
    message = Message(101, text_channel, bot_user)
    text_channel.fetch_message = AsyncMock(return_value=message)
    await db.activate(row['id'], message.id)

    def interaction(user=author, target=message):
        return SimpleNamespace(
            id=500, user=user, channel=text_channel, message=target, client=bot,
            created_at=discord.utils.utcnow(), response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
    return SimpleNamespace(db=db, lifecycle=lifecycle, bot=bot, row=row, message=message,
                           room=room, author=author, other=other, interaction=interaction, board=board)


@pytest.mark.parametrize('source', ['invitation', 'room', 'legacy'])
def test_both_buttons_end_same_invitation_and_remove_components(tmp_path, monkeypatch, source):
    async def scenario():
        env = await setup(tmp_path, monkeypatch)
        interaction = env.interaction(env.other if source == 'room' else env.author)
        if source == 'room':
            # Exercise the actual room-panel entry, with a member who is not the poster.
            view = object.__new__(RoomControlPanelView)
            view.bot = env.bot
            view.voice_channel_id = env.room.id
            await view.full_callback(interaction)
        else:
            button = InvitationFullButton(env.row['id']) if source == 'invitation' else LegacyInvitationFullButton()
            await button.callback(interaction)
        interaction.response.defer.assert_awaited_once()
        assert await env.db.active() == []
        assert env.message.edits[-1]['view'] is None
        assert (await env.db.get(env.row['id']))['message_sync'] == 'done'
        assert interaction.followup.send.await_args.args[0] == 'invitation.roomfull_set_message'
        env.board.refresh_all_boards.assert_awaited_once()
    asyncio.run(scenario())


def test_stale_dynamic_button_and_other_user_cannot_end_new_invitation(tmp_path, monkeypatch):
    async def scenario():
        env = await setup(tmp_path, monkeypatch)
        unauthorized = env.interaction(env.other)
        await InvitationFullButton(env.row['id']).callback(unauthorized)
        assert (await env.db.current(10))['id'] == env.row['id']
        newer = await prepare(env.db)
        await env.db.activate(newer['id'], 102)
        stale = env.interaction()
        await InvitationFullButton(env.row['id']).callback(stale)
        assert stale.followup.send.await_args.args[0] == 'invitation.already_ended'
        assert (await env.db.current(10))['id'] == newer['id']
    asyncio.run(scenario())


def test_unknown_interaction_aborts_before_any_state_change(tmp_path, monkeypatch):
    async def scenario():
        env = await setup(tmp_path, monkeypatch)
        interaction = env.interaction()
        interaction.created_at -= timedelta(seconds=8)
        interaction.response.defer.side_effect = discord.NotFound(
            SimpleNamespace(status=404, reason='Not Found'), {'code': 10062, 'message': 'Unknown interaction'})
        await InvitationFullButton(env.row['id']).callback(interaction)
        assert (await env.db.current(10))['id'] == env.row['id']
        assert env.message.edits == []
        interaction.followup.send.assert_not_awaited()
    asyncio.run(scenario())


def test_edit_failure_retains_end_and_restart_retries_once(tmp_path, monkeypatch):
    async def scenario():
        env = await setup(tmp_path, monkeypatch)
        original_edit = env.message.edit
        env.message.edit = AsyncMock(side_effect=discord.HTTPException(
            SimpleNamespace(status=503, reason='Unavailable'), 'unavailable'))
        interaction = env.interaction()
        await InvitationFullButton(env.row['id']).callback(interaction)
        assert await env.db.active() == []
        assert (await env.db.get(env.row['id']))['message_sync'] == 'pending'
        assert interaction.followup.send.await_args.args[0] == 'invitation.ended_sync_pending'
        env.message.edit = original_edit
        async with connect_database(env.db.db_path) as conn:
            await conn.execute('UPDATE teamup_invitations SET next_sync_at=NULL')
            await conn.commit()
        restarted = InvitationLifecycle(env.bot, InvitationDatabaseManager(env.db.db_path), None)
        await restarted.reconcile()
        assert (await env.db.get(env.row['id']))['message_sync'] == 'done'
        assert len(env.message.edits) == 1
        await restarted.reconcile()
        assert len(env.message.edits) == 1
    asyncio.run(scenario())


def test_room_deletion_ends_active_invitation(tmp_path, monkeypatch):
    async def scenario():
        env = await setup(tmp_path, monkeypatch)
        await env.lifecycle.room_deleted(10)
        assert await env.db.active() == []
        assert (await env.db.get(env.row['id']))['end_reason'] == 'room_deleted'
        assert env.message.edits[-1]['view'] is None
    asyncio.run(scenario())


def test_room_full_without_active_invitation_returns_clear_feedback(tmp_path, monkeypatch):
    async def scenario():
        env = await setup(tmp_path, monkeypatch)
        await env.db.end(env.row['id'])
        interaction = env.interaction(env.other)
        await env.lifecycle.finish(interaction, source='room', voice_channel_id=10)
        assert interaction.followup.send.await_args.args[0] == 'invitation.no_active_invitation'
        assert env.message.edits == []
    asyncio.run(scenario())


def test_sync_retries_are_bounded_and_history_cleanup_preserves_active(tmp_path):
    async def scenario():
        db = InvitationDatabaseManager(str(tmp_path / 'invites.db'))
        await db.initialize()
        row = await prepare(db)
        await db.activate(row['id'], 101)
        await db.end(row['id'])
        for _ in range(3):
            await db.record_sync(row['id'], 'retry')
        assert (await db.get(row['id']))['message_sync'] == 'blocked'
        assert await db.pending_sync() == []
        another = await prepare(db)
        await db.activate(another['id'], 102)
        await db.cleanup_history()
        assert (await db.current(10))['id'] == another['id']
    asyncio.run(scenario())


def test_unconfirmed_publication_recovery_is_bounded(tmp_path):
    async def scenario():
        db = InvitationDatabaseManager(str(tmp_path / 'invites.db'))
        await db.initialize()
        old = await prepare(db)
        await db.activate(old['id'], 101)
        pending = await prepare(db)
        for _ in range(3):
            await db.record_recovery_failure(pending['id'])
        row = await db.get(pending['id'])
        assert row['status'] == 'ended'
        assert row['end_reason'] == 'publish_unconfirmed'
        assert (await db.current(10))['id'] == old['id']
    asyncio.run(scenario())


def test_board_edit_failure_does_not_report_complete_success(tmp_path, monkeypatch):
    async def scenario():
        env = await setup(tmp_path, monkeypatch)
        env.board.refresh_all_boards.return_value = False
        interaction = env.interaction()
        await InvitationFullButton(env.row['id']).callback(interaction)
        assert await env.db.active() == []
        assert interaction.followup.send.await_args.args[0] == 'invitation.ended_sync_pending'
    asyncio.run(scenario())


def test_failed_new_publish_keeps_old_invitation_active(tmp_path, monkeypatch):
    async def scenario():
        env = await setup(tmp_path, monkeypatch)
        monkeypatch.setattr('bot.cogs.create_invitation.views.TeamInvitationView.populate_panel', AsyncMock())
        env.board.db_manager = SimpleNamespace(get_game_type_by_channel=AsyncMock(return_value=None))
        obj = SimpleNamespace(author=env.author, channel=env.message.channel, content='缺2',
                              reply=AsyncMock(side_effect=discord.Forbidden(
                                  SimpleNamespace(status=403, reason='Forbidden'), 'forbidden')))
        with pytest.raises(discord.Forbidden):
            await env.lifecycle.publish(obj, env.room)
        assert (await env.db.current(10))['id'] == env.row['id']
        assert env.message.edits == []
    asyncio.run(scenario())


def test_recovery_attaches_successful_send_without_sending_again(tmp_path, monkeypatch):
    async def scenario():
        from discord.components import _component_factory
        env = await setup(tmp_path, monkeypatch)
        pending = await prepare(env.db)
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(discord.ui.Container(discord.ui.ActionRow(InvitationFullButton(pending['id']))))
        message = SimpleNamespace(id=102, author=env.bot.user,
            flags=discord.MessageFlags._from_value(32768),
            components=[_component_factory(c) for c in view.to_components()])
        async def history(**kwargs):
            assert kwargs['limit'] == 100
            yield message
        env.message.channel.history = history
        await env.lifecycle._recover_publication(pending)
        assert (await env.db.current(10))['invitation_message_id'] == 102
        assert (await env.db.get(env.row['id']))['status'] == 'ended'
    asyncio.run(scenario())


def test_new_publish_saves_exact_message_and_marks_previous_full(tmp_path, monkeypatch):
    async def scenario():
        env = await setup(tmp_path, monkeypatch)
        monkeypatch.setattr('bot.cogs.create_invitation.views.TeamInvitationView.populate_panel', AsyncMock())
        env.board.db_manager = SimpleNamespace(get_game_type_by_channel=AsyncMock(return_value=None))
        sent = SimpleNamespace(id=102)
        obj = SimpleNamespace(author=env.other, channel=env.message.channel, content='缺2', reply=AsyncMock(return_value=sent))
        await env.lifecycle.publish(obj, env.room)
        current = await env.db.current(10)
        assert current['invitation_message_id'] == 102
        assert current['user_id'] == env.other.id
        assert env.message.edits[-1]['view'] is None
        assert obj.reply.await_args.kwargs['view'].invitation_id == current['id']
    asyncio.run(scenario())


def test_persistent_dynamic_dispatch_reconstructs_after_restart(monkeypatch):
    async def scenario():
        from discord.ui.view import ViewStore

        # Store contains no original per-message View: this is the restart path.
        store = ViewStore(SimpleNamespace())
        store.add_dynamic_items(InvitationFullButton)
        button = InvitationFullButton(123)
        original = discord.ui.LayoutView(timeout=None)
        original.add_item(discord.ui.Container(discord.ui.ActionRow(button)))
        from discord.components import _component_factory
        message = SimpleNamespace(id=888, flags=discord.MessageFlags._from_value(32768),
                                  components=[_component_factory(c) for c in original.to_components()])
        finish = AsyncMock()
        bot = SimpleNamespace(get_cog=lambda name: SimpleNamespace(lifecycle=SimpleNamespace(finish=finish)))
        interaction = SimpleNamespace(message=message, client=bot, data={'custom_id': button.custom_id, 'component_type': 2})
        store.dispatch_view(2, button.custom_id, interaction)
        for _ in range(20):
            if finish.await_count:
                break
            await asyncio.sleep(0)
        finish.assert_awaited_once_with(interaction, invitation_id=123)
        store._ViewStore__tasks.clear()
    asyncio.run(scenario())
