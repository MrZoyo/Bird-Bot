import asyncio
import datetime
import io
from pathlib import Path
from types import SimpleNamespace

import discord
import pytest
from ruamel.yaml import YAML

from bot.cogs.giveaway import cog as cog_module, editing, modals, views
from bot.cogs.giveaway.cog import GiveawayCog
from bot.cogs.giveaway.editing import GiveawayEditView
from bot.utils.giveaway_db import GiveawayDatabaseManager
from test_giveaway_interaction_flow import FakeBot, FakeChannel, FakeInteraction, FakeMessage, FakeUser


def interaction(user_id=10):
    return FakeInteraction(FakeUser(user_id, 'Admin', 'admin', f'<@{user_id}>'), [])


async def setup_edit(tmp_path, monkeypatch, *, image=True, ui_version=2):
    text = YAML(typ='safe').load(Path('bot/locales/zh_CN/giveaway.yaml'))

    def translate(key, **kwargs):
        value = text[key.split('.', 1)[1]]
        return value.format_map(kwargs) if kwargs else value

    for module in (editing, modals, views, cog_module):
        monkeypatch.setattr(module, 't', translate)

    async def permitted(*args, **kwargs):
        return True

    monkeypatch.setattr(editing, 'check_channel_validity', permitted)
    monkeypatch.setattr(cog_module, 'check_channel_validity', permitted)
    db = GiveawayDatabaseManager(str(tmp_path / 'edit.db'))
    await db.initialize_database()
    await db.insert_giveaway(
        1, '900', (datetime.datetime.now() - datetime.timedelta(minutes=10)).isoformat(),
        60, 2, 'August prize', 'Description', 99, None, 0, 0, 0,
        provider='Provider', image_url='https://cdn.discordapp.com/attachments/10/123/old.png' if image else None,
        image_filename='old.png' if image else None, ui_version=ui_version,
    )
    await db.add_participant(1, 101)
    await db.add_participant(1, 202)
    cog = object.__new__(GiveawayCog)
    cog._giveaway_locks = {}
    cog.giveaways = {}
    cog.db = db
    cog.giveaway_channel_id = 10
    message = FakeMessage(900, [])
    message.flags = discord.MessageFlags()
    message.attachments = [SimpleNamespace(filename='old.png', id=1)] if image else []
    channel = FakeChannel(10, message, [])
    cog.bot = FakeBot(channel=channel, cog=cog)
    record = await db.fetch_giveaway(1)
    return cog, message, GiveawayEditView(cog, record, 10)


def test_command_opens_private_draft_without_changing_activity(tmp_path, monkeypatch):
    async def scenario():
        cog, message, view = await setup_edit(tmp_path, monkeypatch)
        before = await cog.db.fetch_giveaway(1)
        request = interaction()
        await GiveawayCog.ga_change.callback(cog, request, '1')
        assert request.response.events[0][0:2] == ('defer', True)
        response = request.followup.messages[0]
        assert response['ephemeral'] is True
        assert isinstance(response['view'], GiveawayEditView)
        assert len(response['view'].children) == 5
        view.state.prizes = 'September prize'
        assert await cog.db.fetch_giveaway(1) == before
        await view.cancel(interaction())
        assert await cog.db.fetch_giveaway(1) == before
        assert not message.edits

    asyncio.run(scenario())


@pytest.mark.parametrize('ui_version', [1, 2])
def test_save_preserves_participants_and_new_joins_use_new_limits(tmp_path, monkeypatch, ui_version):
    async def scenario():
        cog, message, view = await setup_edit(tmp_path, monkeypatch, ui_version=ui_version)
        original = await cog.db.fetch_giveaway(1)
        await cog.db.add_participant(1, 303)  # Arrived after the draft opened.
        view.state.prizes = 'September prize'
        view.state.description = 'New description'
        view.state.provider = 'New provider'
        view.state.duration_minutes = 120
        view.state.winner_number = 7
        view.state.reaction_limit = 100
        view.state.message_limit = 200
        view.state.timespent_limit_minutes = 30
        view.state.timespent_seconds_override = None
        await view.save(interaction())
        saved = await cog.db.fetch_giveaway(1)
        assert saved['prizes'] == 'September prize'
        assert saved['description'] == 'New description'
        assert saved['provider'] == 'New provider'
        assert saved['winner_number'] == 7
        assert saved['ui_version'] == 2
        assert saved['duration'] == 120
        assert (saved['reaction_req'], saved['message_req'], saved['timespent_req']) == (100, 200, 1800)
        for key in ('giveaway_id', 'message_id', 'starttime', 'creator_id', 'image_url', 'image_filename'):
            assert saved[key] == original[key]
        assert set(await cog.draw_winners(1, 7)) == {'101', '202', '303'}
        assert 'attachments' not in message.edits[0]
        assert message.edits[0]['embed'].image.url == 'attachment://old.png'
        assert 'September prize' in message.edits[0]['embed'].title
        assert message.edits[0]['view'].participate_button.custom_id == 'participate_1'

        checked = []

        async def achievements(user_id):
            checked.append(user_id)
            return (user_id, 0, 0, 0, 0)

        cog.db.fetch_user_achievements = achievements
        panel = cog.giveaways[1]
        old = interaction(101)
        await panel.participate(old)
        assert checked == []
        assert old.response.messages[0]['ephemeral'] is True
        await panel.participate(interaction(404))
        assert checked == [404]
        assert not await cog.db.is_participant(1, 404)
        await panel.exit(interaction(101))
        await panel.participate(interaction(101))
        assert checked == [404, 101]
        assert not await cog.db.is_participant(1, 101)
        assert set(await cog.db.fetch_participant_ids(1)) == {'202', '303'}
        assert all(edit['embed'].image.url == 'attachment://old.png' for edit in message.edits)
        edits = len(message.edits)
        await view.save(interaction())
        assert len(message.edits) == edits  # No duplicate save.

    asyncio.run(scenario())


@pytest.mark.parametrize('reason', ['ended', 'expired', 'stale', 'bad_deadline'])
def test_closed_or_stale_drafts_cannot_overwrite_activity(tmp_path, monkeypatch, reason):
    async def scenario():
        cog, message, view = await setup_edit(tmp_path, monkeypatch)
        if reason == 'ended':
            await cog.db.mark_giveaway_as_ended(1)
        elif reason == 'expired':
            await cog.db.update_giveaway_duration(1, 1)
        elif reason == 'stale':
            await cog.db.update_giveaway_description(1, 'Another administrator saved this')
        else:
            view.state.duration_minutes = 1
        current = await cog.db.fetch_giveaway(1)
        view.state.prizes = 'Must not be saved'
        response = interaction()
        await view.save(response)
        assert await cog.db.fetch_giveaway(1) == current
        assert not message.edits
        assert response.followup.messages[0]['ephemeral'] is True

    asyncio.run(scenario())


@pytest.mark.parametrize('image_action', ['replace', 'remove'])
def test_edit_image_payload_and_persisted_reference(tmp_path, monkeypatch, image_action):
    async def scenario():
        cog, message, view = await setup_edit(tmp_path, monkeypatch)
        view.state.image_changed = True
        view.state.image_filename = 'new.png' if image_action == 'replace' else None
        if image_action == 'replace':
            view.state.image_file = discord.File(io.BytesIO(b'new image'), filename='new.png')
        await view.save(interaction())
        saved = await cog.db.fetch_giveaway(1)
        attachments = message.edits[0]['attachments']
        if image_action == 'replace':
            assert saved['image_url'] == 'attachment://new.png'
            assert saved['image_filename'] == 'new.png'
            assert len(attachments) == 1 and attachments[0].filename == 'new.png'
            assert message.edits[0]['embed'].image.url == 'attachment://new.png'
        else:
            assert saved['image_url'] is None and saved['image_filename'] is None
            assert attachments == []
            assert not message.edits[0]['embed'].image.url
        assert await cog.db.fetch_participant_ids(1) == ['101', '202']

    asyncio.run(scenario())


def test_failed_discord_edit_restores_settings_and_keeps_late_join(tmp_path, monkeypatch):
    async def scenario():
        cog, message, view = await setup_edit(tmp_path, monkeypatch)
        view.state.prizes = 'Changed'
        view.state.image_changed = True
        view.state.image_filename = 'retry.png'
        view.state.image_file = discord.File(io.BytesIO(b'retry'), filename='retry.png')
        before = await cog.db.fetch_giveaway(1)
        normal_edit = message.edit

        async def forbidden(**kwargs):
            await cog.db.add_participant(1, 303)
            raise discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'no permission')

        message.edit = forbidden
        response = interaction()
        await view.save(response)
        restored = await cog.db.fetch_giveaway(1)
        assert {k: v for k, v in restored.items() if k != 'participant_ids'} == {
            k: v for k, v in before.items() if k != 'participant_ids'
        }
        assert set(await cog.db.fetch_participant_ids(1)) == {'101', '202', '303'}
        assert not view.state.published
        assert not view.saving
        assert response.followup.messages
        message.edit = normal_edit
        await view.save(interaction())
        assert (await cog.db.fetch_giveaway(1))['prizes'] == 'Changed'
        assert view.state.published

    asyncio.run(scenario())


def test_edit_owner_and_modal_validation(tmp_path, monkeypatch):
    async def scenario():
        cog, message, view = await setup_edit(tmp_path, monkeypatch)
        await view.save(interaction(999))
        assert not message.edits
        form = modals.GiveawayCreateModal(cog.bot, cog.db, view.state, draft_view=view)
        form.duration._value = '0m'
        form.winners._value = '7'
        form.prizes._value = 'Invalid duration'
        await form.on_submit(interaction())
        assert view.state.prizes == 'August prize'
        form.duration._value = '2h'
        form.description._value = 'Edited in the modal'
        form.providers._value = 'Someone'
        await form.on_submit(interaction())
        assert view.state.duration_minutes == 120
        assert view.state.prizes == 'Invalid duration'
        assert view.state.description == 'Edited in the modal'
        assert len(view.children) == 5
        assert (await cog.db.fetch_giveaway(1))['prizes'] == 'August prize'
        limits = modals.GiveawayLimitsModal(view)
        limits.reaction_limit._value = '5'
        limits.message_limit._value = '6'
        limits.timespent_limit._value = '7'
        await limits.on_submit(interaction())
        assert view.state.timespent_limit_seconds == 420

    asyncio.run(scenario())


def test_db_compare_and_save_protects_results_and_concurrent_edits(tmp_path, monkeypatch):
    async def scenario():
        cog, _, _ = await setup_edit(tmp_path, monkeypatch)
        db = cog.db
        before = await db.fetch_giveaway(1)
        with pytest.raises(ValueError):
            await db.update_giveaway_settings(before, {'participant_ids': ''})
        assert await db.update_giveaway_settings(before, {'prizes': 'First admin'})
        assert not await db.update_giveaway_settings(before, {'prizes': 'Stale admin'})
        current = await db.fetch_giveaway(1)
        await db.update_giveaway_winners(1, [202])
        assert not await db.update_giveaway_settings(current, {'prizes': 'Too late'})
        assert await db.fetch_winner_ids(1) == [202]
        assert await db.fetch_participant_ids(1) == ['101', '202']

    asyncio.run(scenario())


def test_end_waits_for_save_then_uses_updated_prize(tmp_path, monkeypatch):
    async def scenario():
        cog, message, view = await setup_edit(tmp_path, monkeypatch)
        reached_discord = asyncio.Event()
        release_discord = asyncio.Event()
        normal_edit = message.edit

        async def slow_edit(**kwargs):
            reached_discord.set()
            await release_discord.wait()
            await normal_edit(**kwargs)

        message.edit = slow_edit
        view.state.prizes = 'September prize'
        save = asyncio.create_task(view.save(interaction()))
        await reached_discord.wait()
        notified = []

        async def notify(winners, prize, giveaway_id):
            notified.append(prize)

        cog.notify_winners = notify
        ending = asyncio.create_task(GiveawayCog.end_giveaway.callback(cog, interaction(), '1'))
        await asyncio.sleep(0)
        assert not ending.done() and notified == []
        release_discord.set()
        await asyncio.gather(save, ending)
        assert notified == ['September prize']
        assert (await cog.db.fetch_giveaway(1))['is_end'] == 1
        assert all(item.disabled for item in message.edits[-1]['view'].children)
        assert message.edits[-1]['embed'].image.url == 'attachment://old.png'

    asyncio.run(scenario())


def test_image_modal_acknowledges_before_downloading_and_clear_is_draft_only(tmp_path, monkeypatch):
    async def scenario():
        cog, message, view = await setup_edit(tmp_path, monkeypatch)
        form = modals.GiveawayImageModal(view)
        request = interaction()

        async def download(**kwargs):
            assert request.response.is_done()
            return discord.File(io.BytesIO(b'picture'), filename=kwargs['filename'])

        form.image._values = [SimpleNamespace(
            content_type='image/png', filename='upload.png', to_file=download,
        )]
        await form.on_submit(request)
        assert view.state.image_filename == 'upload.png'
        assert view.state.image_changed
        assert request.edits[0]['view'] is view
        assert len(view.children) == 5
        assert not message.edits
        assert (await cog.db.fetch_giveaway(1))['image_filename'] == 'old.png'
        clear_form = modals.GiveawayImageModal(view)
        await clear_form.on_submit(interaction())
        assert view.state.image_file is None and view.state.image_filename is None
        assert (await cog.db.fetch_giveaway(1))['image_filename'] == 'old.png'

    asyncio.run(scenario())


def test_scheduler_rereads_settings_after_waiting_for_edit(tmp_path, monkeypatch):
    async def scenario():
        cog, message, _ = await setup_edit(tmp_path, monkeypatch)
        # The scheduler's initial query sees an expired deadline. An edit that
        # already owns the lock extends it before the scheduler can draw.
        await cog.db.update_giveaway_duration(1, 1)
        fetched = asyncio.Event()
        normal_fetch = cog.fetch_all_giveaways

        async def fetch(*args, **kwargs):
            rows = await normal_fetch(*args, **kwargs)
            fetched.set()
            return rows

        cog.fetch_all_giveaways = fetch
        cog.bot.is_closed = lambda: False
        async with cog.giveaway_lock('1'):
            check = asyncio.create_task(GiveawayCog.check_giveaways.coro(cog))
            await fetched.wait()
            await cog.db.update_giveaway_duration(1, 120)
        await check
        assert not message.edits
        assert (await cog.db.fetch_giveaway(1))['is_end'] == 0

    asyncio.run(scenario())


def test_edit_rechecks_admin_channel_and_preserves_legacy_seconds(tmp_path, monkeypatch):
    async def scenario():
        cog, message, view = await setup_edit(tmp_path, monkeypatch)

        async def denied(*args, **kwargs):
            return False

        monkeypatch.setattr(editing, 'check_channel_validity', denied)
        await view.save(interaction())
        assert not message.edits
        before = await cog.db.fetch_giveaway(1)
        assert await cog.db.update_giveaway_settings(before, {'timespent_req': 61})
        record = await cog.db.fetch_giveaway(1)
        reopened = GiveawayEditView(cog, record, 10)
        assert reopened.state.timespent_limit_seconds == 61

    asyncio.run(scenario())
