import asyncio
import logging
from datetime import datetime, timedelta, timezone
from weakref import WeakValueDictionary

import discord

from bot.utils import fmt_channel, fmt_user
from bot.utils.i18n import t

from .full_message import update_invitation_message_to_full
from .interactions import acknowledge


class InvitationLifecycle:
    """Serialize a room's transitions and reconcile durable Discord updates."""

    def __init__(self, bot, db, role_db):
        self.bot = bot
        self.db = db
        self.role_db = role_db
        self._locks = WeakValueDictionary()

    def room_lock(self, channel_id):
        lock = self._locks.get(channel_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[channel_id] = lock
        return lock

    async def refresh_boards(self):
        cog = self.bot.get_cog('TeamupDisplayCog')
        if cog:
            return await cog.refresh_all_boards()
        return True

    async def publish(self, obj, channel, *, title=None):
        from .views import TeamInvitationView

        author = getattr(obj, 'author', None) or obj.user
        content = title or getattr(obj, 'content', None) or t('invitation.default_invite_embed_title')
        async with self.room_lock(channel.id):
            board = self.bot.get_cog('TeamupDisplayCog')
            game_type = await board.db_manager.get_game_type_by_channel(obj.channel.id) if board else None
            row = await self.db.prepare(
                user_id=author.id, channel_id=obj.channel.id, voice_channel_id=channel.id,
                content=content, player_count=len(channel.members), game_type=game_type,
                voice_channel_name=channel.name,
            )
            view = TeamInvitationView(self.bot, channel, author, self.role_db, invitation_id=row['id'])
            try:
                await view.populate_panel(obj, title=content)
            except Exception:
                await self.db.abandon(row['id'])
                raise
            try:
                if hasattr(obj, 'author'):
                    message = await obj.reply(view=view)
                else:
                    message = await obj.followup.send(view=view, wait=True)
            except discord.HTTPException as exc:
                if exc.status < 500:
                    await self.db.abandon(row['id'])
                # A server/network failure can mean the message was sent. Keep
                # pending for bounded reconciliation; never blindly resend it.
                raise
            await self.db.activate(row['id'], message.id)
            await self.sync_room(channel.id)
        await self.refresh_boards()
        logging.info('Published invitation %s for user %s in room %s', row['id'], fmt_user(author), fmt_channel(channel))
        return message

    async def finish(self, interaction, *, invitation_id=None, voice_channel_id=None, source='invitation'):
        if not await acknowledge(interaction):
            return
        try:
            if source == 'room':
                voice = getattr(interaction.user, 'voice', None)
                if not voice or not voice.channel or voice.channel.id != voice_channel_id:
                    await interaction.followup.send(t('invitation.not_in_vc_message'), ephemeral=True)
                    return
                async with self.room_lock(voice_channel_id):
                    row = await self.db.current(voice_channel_id)
                    if row is None:
                        await interaction.followup.send(t('invitation.no_active_invitation'), ephemeral=True)
                        return
                    result = await self._finish_row(row)
            else:
                message = interaction.message
                row = await self.db.get(invitation_id) if invitation_id is not None else await self.db.get_by_message(message.id)
                if not row or row['invitation_message_id'] != message.id:
                    await interaction.followup.send(t('invitation.legacy_unavailable'), ephemeral=True)
                    return
                if (getattr(message.author, 'id', None) != self.bot.user.id
                        or row['invitation_channel_id'] != interaction.channel.id):
                    await interaction.followup.send(t('invitation.interaction_target_error_message'), ephemeral=True)
                    return
                if interaction.user.id != row['user_id']:
                    await interaction.followup.send(t('invitation.interaction_target_error_message'), ephemeral=True)
                    return
                voice = getattr(interaction.user, 'voice', None)
                if not voice or not voice.channel or voice.channel.id != row['voice_channel_id']:
                    await interaction.followup.send(t('invitation.not_in_vc_message'), ephemeral=True)
                    return
                async with self.room_lock(row['voice_channel_id']):
                    row = await self.db.get(row['id'])
                    result = await self._finish_row(row, message=message)
            if await self.refresh_boards() is False and result == 'roomfull_set_message':
                result = 'ended_sync_pending'
            await interaction.followup.send(t(f'invitation.{result}'), ephemeral=True)
            logging.info('Invitation %s finish result=%s source=%s user=%s room=%s',
                         row['id'], result, source, fmt_user(interaction.user),
                         fmt_channel(self.bot.get_channel(row['voice_channel_id']) or row['voice_channel_id']))
        except Exception:
            logging.exception('Could not finish invitation for user %s in %s',
                              fmt_user(interaction.user), fmt_channel(getattr(interaction, 'channel', None)))
            await interaction.followup.send(t('invitation.finish_failed'), ephemeral=True)

    async def _finish_row(self, row, *, message=None):
        if row['status'] != 'active':
            return 'already_ended'
        changed = await self.db.end(row['id'])
        if not changed:
            return 'already_ended'
        outcome = await self.sync_one(await self.db.get(row['id']), message=message)
        return 'roomfull_set_message' if outcome in ('updated', 'missing') else 'ended_sync_pending'

    async def sync_one(self, row, *, message=None, voice_channel=None):
        if not row['invitation_message_id']:
            await self.db.record_sync(row['id'], 'missing')
            return 'missing'
        try:
            if message is None:
                channel = self.bot.get_channel(row['invitation_channel_id'])
                if channel is None:
                    channel = await self.bot.fetch_channel(row['invitation_channel_id'])
                message = await channel.fetch_message(row['invitation_message_id'])
            outcome = await update_invitation_message_to_full(
                self.bot, message, voice_channel=voice_channel,
                voice_channel_name=row.get('voice_channel_name'),
            )
        except discord.NotFound:
            outcome = 'missing'
        except discord.Forbidden:
            outcome = 'forbidden'
        except (discord.HTTPException, asyncio.TimeoutError, OSError):
            outcome = 'retry'
        await self.db.record_sync(row['id'], outcome)
        if outcome not in ('updated', 'missing'):
            logging.warning('Invitation %s message synchronization=%s channel=%s',
                            row['id'], outcome, fmt_channel(row['invitation_channel_id']))
        return outcome

    async def sync_room(self, channel_id, *, voice_channel=None):
        # Caller holds the room lock. UI work is outside database transactions.
        for row in await self.db.pending_sync(channel_id):
            await self.sync_one(row, voice_channel=voice_channel)

    async def room_deleted(self, channel_id, *, voice_channel=None):
        async with self.room_lock(channel_id):
            if voice_channel is not None:
                await self.db.remember_channel_name(channel_id, voice_channel.name)
            row = await self.db.current(channel_id)
            if row:
                await self.db.end(row['id'], 'room_deleted')
                await self.sync_room(channel_id, voice_channel=voice_channel)
        await self.refresh_boards()

    async def reconcile(self):
        recovered = False
        for row in await self.db.pending_publications():
            async with self.room_lock(row['voice_channel_id']):
                if (await self.db.get(row['id']))['status'] != 'pending':
                    continue
                try:
                    await self._recover_publication(row)
                    recovered = True
                except (discord.HTTPException, asyncio.TimeoutError, OSError):
                    await self.db.record_recovery_failure(row['id'])
                    logging.warning('Invitation %s publication recovery failed in %s',
                                    row['id'], fmt_channel(row['invitation_channel_id']))
        for row in await self.db.pending_sync():
            async with self.room_lock(row['voice_channel_id']):
                current = await self.db.get(row['id'])
                if current and current['message_sync'] == 'pending':
                    await self.sync_one(current)
        for row in await self.db.active():
            if self.bot.get_channel(row['voice_channel_id']) is None:
                try:
                    await self.bot.fetch_channel(row['voice_channel_id'])
                except discord.NotFound:
                    await self.room_deleted(row['voice_channel_id'])
                except discord.HTTPException:
                    pass  # Cache absence / permissions do not prove deletion.
        await self.db.cleanup_history()
        if recovered:
            await self.refresh_boards()

    async def _recover_publication(self, row):
        from .views import invitation_custom_id

        try:
            channel = self.bot.get_channel(row['invitation_channel_id'])
            if channel is None:
                channel = await self.bot.fetch_channel(row['invitation_channel_id'])
            after = datetime.fromisoformat(row['created_at']).replace(tzinfo=timezone.utc) - timedelta(seconds=5)
            expected = invitation_custom_id(row['id'])
            async for message in channel.history(limit=100, after=after, oldest_first=True):
                if message.author.id != self.bot.user.id:
                    continue
                view = discord.ui.LayoutView.from_message(message)
                if any(getattr(item, 'custom_id', None) == expected for item in view.walk_children()):
                    await self.db.activate(row['id'], message.id)
                    return
            await self.db.abandon(row['id'], 'publish_unconfirmed')
            logging.warning('Invitation %s send could not be confirmed within 100 messages in %s; not resending',
                            row['id'], fmt_channel(row['invitation_channel_id']))
        except discord.NotFound:
            await self.db.abandon(row['id'], 'channel_deleted')
        except discord.Forbidden:
            await self.db.abandon(row['id'], 'publish_unconfirmed')
            logging.warning('Invitation %s recovery forbidden in %s', row['id'], fmt_channel(row['invitation_channel_id']))
