import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord.http import handle_message_parameters

from bot.cogs.create_invitation import cog as invitation_module
from bot.cogs.create_invitation import full_message
from bot.cogs.create_invitation import views as invitation_views
from bot.cogs.create_invitation.cog import CreateInvitationCog
from bot.cogs.create_invitation.lifecycle import InvitationLifecycle
from bot.cogs.create_invitation.views import TeamInvitationView
from bot.cogs.teamup_display import cog as display_module
from bot.cogs.teamup_display.cog import TeamupDisplayCog
from bot.utils.components_v2 import build_panel_container
from bot.utils.i18n import t
from bot.utils.invitation_db import InvitationDatabaseManager
from bot.utils.mentions import strip_discord_mentions


BLOCKED_MENTIONS = '@everyone @here <@222> <@&444>'
INJECTED_MENTIONS = f'{BLOCKED_MENTIONS} <@!333>'


def panel_text(view):
    def walk(components):
        for component in components:
            if component.get('type') == 10:
                yield component['content']
            yield from walk(component.get('components', []))
            if component.get('accessory'):
                yield from walk([component['accessory']])
    return '\n'.join(walk(view.to_components()))


async def publish_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(invitation_module, 'log_keyword_detection', lambda *args: None)
    monkeypatch.setattr(invitation_views.config, 'get_config', lambda _: {})
    guild = SimpleNamespace(id=30)
    room = SimpleNamespace(id=10, name='Room', guild=guild, members=[])
    author = SimpleNamespace(
        id=1, name='Poster', display_name='Poster', bot=False, avatar=None,
        mention='<@1>', voice=SimpleNamespace(channel=room),
    )
    bot = SimpleNamespace(user=SimpleNamespace(id=99, avatar=None), get_cog=lambda _: None)
    db = InvitationDatabaseManager(str(tmp_path / 'mentions.db'))
    await db.initialize()
    lifecycle = InvitationLifecycle(bot, db, SimpleNamespace(get_user_signature=AsyncMock(return_value=None)))
    lifecycle.sync_room = AsyncMock()
    cog = object.__new__(CreateInvitationCog)
    cog.bot, cog.lifecycle = bot, lifecycle
    cog.conf, cog.ignore_user_ids = {'ignore_channel_ids': []}, []
    cog.default_invite_embed_title = t('invitation.default_invite_embed_title')
    cog.failed_invite_responses = 'Failed: '
    message = SimpleNamespace(
        author=author, channel=SimpleNamespace(id=20), guild=guild,
        content=f'缺1 {INJECTED_MENTIONS}', reply=AsyncMock(return_value=SimpleNamespace(id=100)),
    )
    return SimpleNamespace(cog=cog, db=db, message=message, room=room, author=author)


@pytest.mark.parametrize('source', ['automatic', 'slash'])
def test_invitation_publication_removes_injected_mentions_and_restricts_notification_targets(
    tmp_path, monkeypatch, source,
):
    async def scenario():
        env = await publish_environment(tmp_path, monkeypatch)
        if source == 'automatic':
            await env.cog.on_message(env.message)
            send = env.message.reply
        else:
            interaction = SimpleNamespace(
                user=env.author, channel=env.message.channel,
                response=SimpleNamespace(defer=AsyncMock()),
                followup=SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=100))),
            )
            await CreateInvitationCog.invitation.callback(env.cog, interaction, title=env.message.content)
            send = interaction.followup.send
            interaction.response.defer.assert_awaited_once()
        send.assert_awaited_once()
        payload = send.await_args.kwargs
        text = panel_text(payload['view'])
        for token in BLOCKED_MENTIONS.split():
            assert token not in text
        assert '缺1' in text and '<@1>' in text and '<@!333>' in text
        # Serialize through discord.py, including a permissive client default,
        # to verify that retained nickname mentions cannot notify third parties.
        with handle_message_parameters(
            view=payload['view'], allowed_mentions=payload['allowed_mentions'],
            previous_allowed_mentions=discord.AllowedMentions.all(),
        ) as serialized:
            assert serialized.payload['allowed_mentions'] == {'parse': [], 'users': [1]}
        row = await env.db.current(env.room.id)
        assert ' '.join(row['message_content'].split()) == '缺1 <@!333>'
        assert env.message.content == f'缺1 {INJECTED_MENTIONS}'
    asyncio.run(scenario())


@pytest.mark.parametrize('title', [BLOCKED_MENTIONS, ' \n\t '])
def test_empty_sanitized_title_uses_default_in_database_and_panel(tmp_path, monkeypatch, title):
    async def scenario():
        env = await publish_environment(tmp_path, monkeypatch)
        await env.cog.lifecycle.publish(env.message, env.room, title=title)
        expected = t('invitation.default_invite_embed_title')
        assert (await env.db.current(env.room.id))['message_content'] == expected
        assert panel_text(env.message.reply.await_args.kwargs['view']).startswith(f'### {expected}\n')
    asyncio.run(scenario())


def test_cleared_nullable_signature_does_not_prevent_invitation_publication(tmp_path, monkeypatch):
    async def scenario():
        env = await publish_environment(tmp_path, monkeypatch)
        env.cog.lifecycle.role_db.get_user_signature.return_value = {'signature': None, 'is_disabled': False}
        await env.cog.on_message(env.message)
        env.message.reply.assert_awaited_once()
        text = panel_text(env.message.reply.await_args.kwargs['view'])
        assert '缺1' in text and '<@1>' in text
        assert 'None' not in text
        assert (await env.db.current(env.room.id))['status'] == 'active'
    asyncio.run(scenario())


@pytest.mark.parametrize('source', ['message', 'slash_title'])
def test_direct_panel_population_sanitizes_title_and_signature(tmp_path, monkeypatch, source):
    async def scenario():
        env = await publish_environment(tmp_path, monkeypatch)
        role_db = SimpleNamespace(get_user_signature=AsyncMock(return_value={
            'signature': f'打野 {INJECTED_MENTIONS} contact@example.com', 'is_disabled': False,
        }))
        view = TeamInvitationView(env.cog.bot, env.room, env.author, role_db)
        if source == 'message':
            await view.populate_panel(env.message)
        else:
            interaction = SimpleNamespace(user=env.author, data={'name': 'invt'})
            await view.populate_panel(interaction, title=env.message.content)
        text = panel_text(view)
        for token in BLOCKED_MENTIONS.split():
            assert token not in text
        assert text.count('<@!333>') == 2
        assert '打野' in text and 'contact@example.com' in text
        assert '<@1>' in text
    asyncio.run(scenario())


@pytest.mark.parametrize('content', [
    '@eve<@222>ryone', '@he<@&444>re', '@<@222>everyone',
])
def test_removing_embedded_mentions_cannot_create_a_new_broadcast_mention(content):
    cleaned = strip_discord_mentions(content)
    assert '@everyone' not in cleaned and '@here' not in cleaned
    assert '<@222>' not in cleaned and '<@&444>' not in cleaned


def test_sanitizer_preserves_nickname_mentions_ordinary_at_text_and_channel_links():
    text = '缺1 <@!333> contact@example.com @someone <#456> https://example.com/@profile'
    assert strip_discord_mentions(text) == text


@pytest.mark.parametrize('panel', [False, True], ids=['embed', 'components_v2'])
@pytest.mark.parametrize('has_room_url', [False, True], ids=['legacy_without_url', 'room_link'])
def test_full_update_cleans_historical_mentions_without_notifying_anyone(panel, has_room_url):
    async def scenario():
        title = f'缺1 {INJECTED_MENTIONS}'
        description = f'old signature {INJECTED_MENTIONS}'
        if has_room_url:
            description = f'join https://discord.com/channels/30/10 from <@1>\n{description}'
        message = SimpleNamespace(id=100, channel=SimpleNamespace(id=20, name='Teamup'), edit=AsyncMock())
        if panel:
            view = discord.ui.LayoutView()
            view.add_item(build_panel_container(title=title, description=description, buttons=[]))
            message.embeds, message.components = [], view.to_components()
        else:
            message.embeds = [discord.Embed(title=title, description=description)]
        bot = SimpleNamespace(get_channel=lambda _: SimpleNamespace(id=10, name='Room'))
        assert await full_message.update_invitation_message_to_full(bot, message) == 'updated'
        payload = message.edit.await_args.kwargs
        text = panel_text(payload['view']) if panel else (
            f"{payload['embed'].title}\n{payload['embed'].description}"
        )
        for token in BLOCKED_MENTIONS.split():
            assert token not in text
        assert '<@!333>' in text
        assert payload['allowed_mentions'].to_dict() == {'parse': []}
        if has_room_url:
            assert 'https://discord.com/channels/30/10' in text and '<@1>' in text
    asyncio.run(scenario())


def test_historical_board_content_is_sanitized_and_create_and_refresh_disable_mentions(monkeypatch):
    async def scenario():
        monkeypatch.setattr(display_module, 'check_channel_validity', AsyncMock(return_value=True))
        board_message = SimpleNamespace(id=101, edit=AsyncMock())
        text_channel = SimpleNamespace(
            id=20, name='Teamup', mention='<#20>',
            fetch_message=AsyncMock(return_value=board_message),
            send=AsyncMock(return_value=board_message),
            permissions_for=lambda _: SimpleNamespace(send_messages=True),
        )
        room = SimpleNamespace(id=10, guild=SimpleNamespace(id=30), members=[1, 2])
        historical_row = {
            'message_content': f'缺1 {INJECTED_MENTIONS}', 'voice_channel_id': 10,
            'user_id': 1, 'created_at': '2026-10-12 10:00:00',
        }
        cog = object.__new__(TeamupDisplayCog)
        cog.bot = SimpleNamespace(
            user=SimpleNamespace(avatar=None), get_user=lambda _: None,
            get_channel=lambda cid: room if cid == 10 else text_channel,
        )
        cog.db_manager = SimpleNamespace(
            get_active_invitations=AsyncMock(return_value=[historical_row]),
            get_all_game_types=AsyncMock(return_value={}),
            save_display_board=AsyncMock(return_value=True),
        )
        cog.invitation_expire_minutes, cog.max_content_length, cog.embed_color = 5, 256, 10039500
        cog.emojis = dict(search='search', players='players', time='time', link='link')
        interaction = SimpleNamespace(
            guild=SimpleNamespace(me=object()), response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        await TeamupDisplayCog.teamup_init.callback(cog, interaction, text_channel)
        assert await cog.update_display_board(20, 101)
        for send in [text_channel.send, board_message.edit]:
            send.assert_awaited_once()
            payload = send.await_args.kwargs
            text = payload['embed'].description
            for token in BLOCKED_MENTIONS.split():
                assert token not in text
            assert '缺1' in text and '<@!333>' in text
            assert 'https://discord.com/channels/30/10' in text
            assert payload['allowed_mentions'].to_dict() == {'parse': []}
        # Old rows are safely rendered without mutating stored history.
        assert historical_row['message_content'] == f'缺1 {INJECTED_MENTIONS}'
    asyncio.run(scenario())
