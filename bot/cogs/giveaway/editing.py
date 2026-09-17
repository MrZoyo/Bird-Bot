"""An unpublished edit draft for an existing giveaway."""
import datetime
import io
import logging

import discord
from discord.utils import format_dt

from bot.utils import check_channel_validity, fmt_user
from bot.utils.giveaway_db import GIVEAWAY_EDITABLE_COLUMNS
from bot.utils.i18n import t

from .modals import GiveawayDraftState, GiveawayDraftView
from .views import GiveawayPanelView


def giveaway_deadline(record):
    return datetime.datetime.fromisoformat(record['starttime']) + datetime.timedelta(
        minutes=record['duration'],
    )


def giveaway_is_closed(record):
    if not record or record['is_end']:
        return True
    deadline = giveaway_deadline(record)
    return deadline <= datetime.datetime.now(tz=deadline.tzinfo)


class GiveawayEditView(GiveawayDraftView):
    editing = True

    def __init__(self, cog, record, editor_id):
        self.cog = cog
        self.original = dict(record)
        self.saving = False
        state = GiveawayDraftState(
            creator_id=editor_id,
            giveaway_channel_id=cog.giveaway_channel_id,
            default_provider=t('giveaway.giveaway_default_provider'),
            duration_text=f"{record['duration']}m",
            duration_minutes=record['duration'],
            winner_number=record['winner_number'],
            prizes=record['prizes'],
            description=record.get('description') or '',
            provider=record.get('provider') or '',
            reaction_limit=record['reaction_req'],
            message_limit=record['message_req'],
            timespent_limit_minutes=record['timespent_req'] // 60,
            timespent_seconds_override=record['timespent_req'],
            image_filename=record.get('image_filename') or record.get('image_url'),
        )
        super().__init__(cog.bot, cog.db, state)
        self.publish_button.label = t('giveaway.giveaway_edit_save_button')
        self.publish_button.callback = self.save
        self.image_button.label = t('giveaway.giveaway_edit_image_button')
        self.cancel_button = discord.ui.Button(
            label=t('giveaway.giveaway_edit_cancel_button'),
            style=discord.ButtonStyle.secondary,
        )
        self.cancel_button.callback = self.cancel
        self.add_item(self.cancel_button)

    def populate_panel(self, **kwargs):
        super().populate_panel(**kwargs)
        if hasattr(self, 'cancel_button'):
            self.add_item(self.cancel_button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.state.creator_id:
            await interaction.response.send_message(
                t('giveaway.giveaway_edit_owner_only_message'), ephemeral=True,
            )
            return False
        if self.state.published or self.saving or self.is_finished():
            await interaction.response.send_message(
                t('giveaway.giveaway_edit_inactive_message'), ephemeral=True,
            )
            return False
        return await check_channel_validity(interaction, ephemeral=True)

    def format_embed(self):
        embed = super().format_embed()
        embed.title = t('giveaway.giveaway_edit_title', giveaway_id=self.original['giveaway_id'])
        embed.description = t('giveaway.giveaway_edit_rules')
        embed.set_field_at(
            1, name=t('giveaway.giveaway_edit_duration_label'),
            value=self.state.duration_text, inline=True,
        )
        deadline = giveaway_deadline({**self.original, 'duration': self.state.duration_minutes})
        embed.add_field(
            name=t('giveaway.giveaway_embed_timeend_title'),
            value=format_dt(deadline, style='F'), inline=False,
        )
        return embed

    async def cancel(self, interaction):
        if not await self.interaction_check(interaction):
            return
        self.stop()
        self._close_image()
        await interaction.response.edit_message(
            content=t('giveaway.giveaway_edit_cancelled_message'), embed=None, view=None,
        )

    async def on_timeout(self):
        self._close_image()

    def _close_image(self):
        if self.state.image_file is not None:
            self.state.image_file.close()

    def _changes(self):
        changes = {
            'duration': self.state.duration_minutes,
            'winner_number': self.state.winner_number,
            'prizes': self.state.prizes,
            'description': self.state.description,
            'provider': self.state.provider_or_default,
            'reaction_req': self.state.reaction_limit,
            'message_req': self.state.message_limit,
            'timespent_req': self.state.timespent_limit_seconds,
            'ui_version': 2,
        }
        if self.state.image_changed:
            changes['image_filename'] = self.state.image_filename
            changes['image_url'] = (
                self.state.image_file.uri if self.state.image_file is not None else None
            )
        # Preserve legacy NULLs/defaults when opening a draft without editing them.
        if not self.state.description and not self.original.get('description'):
            changes['description'] = self.original.get('description')
        if not self.state.provider and not self.original.get('provider'):
            changes['provider'] = self.original.get('provider')
        return changes

    async def save(self, interaction):
        if not await self.interaction_check(interaction):
            return
        self.saving = True
        try:
            await interaction.response.defer()
            async with self.cog.giveaway_lock(self.original['giveaway_id']):
                await self._save_locked(interaction)
        finally:
            self.saving = False

    async def _save_locked(self, interaction):
        current = await self.db.fetch_giveaway(self.original['giveaway_id'])
        if giveaway_is_closed(current):
            await interaction.followup.send(t('giveaway.giveaway_edit_closed_message'), ephemeral=True)
            return
        compared = (*GIVEAWAY_EDITABLE_COLUMNS, 'starttime', 'message_id')
        if any(current.get(key) != self.original.get(key) for key in compared):
            await interaction.followup.send(t('giveaway.giveaway_edit_stale_message'), ephemeral=True)
            return
        changes = self._changes()
        proposed = {**current, **changes}
        if giveaway_is_closed(proposed):
            await interaction.followup.send(t('giveaway.giveaway_edit_deadline_message'), ephemeral=True)
            return
        channel = self.bot.get_channel(self.state.giveaway_channel_id)
        if channel is None:
            await interaction.followup.send(t('giveaway.giveaway_channel_missing_message'), ephemeral=True)
            return
        try:
            message = await channel.fetch_message(int(current['message_id']))
        except discord.HTTPException:
            await interaction.followup.send(t('giveaway.giveaway_edit_fetch_failed_message'), ephemeral=True)
            return
        # Actual Components v2 messages cannot be converted in place to embeds.
        if message.flags.components_v2:
            await interaction.followup.send(t('giveaway.giveaway_edit_legacy_message'), ephemeral=True)
            return
        if giveaway_is_closed(current):
            await interaction.followup.send(t('giveaway.giveaway_edit_closed_message'), ephemeral=True)
            return
        panel = GiveawayPanelView(
            self.bot, current['giveaway_id'], self.state.giveaway_channel_id,
            record=proposed,
            participant_count=await self.cog.get_participant_count(current['giveaway_id']),
        )
        panel.message_id = message.id
        embed = panel.format_embed()
        attachments = {}
        upload = None
        if self.state.image_changed:
            if self.state.image_file is not None:
                # discord.py closes sent Files. Keep the draft file usable after an HTTP failure.
                self.state.image_file.reset()
                upload = discord.File(
                    io.BytesIO(self.state.image_file.fp.read()),
                    filename=self.state.image_filename,
                    description=t('giveaway.giveaway_image_description'),
                )
            attachments['attachments'] = [upload] if upload else []
        try:
            if not await self.db.update_giveaway_settings(current, changes):
                await interaction.followup.send(t('giveaway.giveaway_edit_stale_message'), ephemeral=True)
                return
            try:
                await message.edit(embed=embed, view=panel, **attachments)
            except (discord.HTTPException, OSError):
                # Restore only settings; any concurrent joins/leaves remain intact.
                restored = await self.db.update_giveaway_settings(
                    proposed, {key: current.get(key) for key in changes},
                )
                logging.exception('Giveaway %s message edit failed; settings restored=%s',
                                  current['giveaway_id'], restored)
                await interaction.followup.send(t('giveaway.giveaway_edit_save_failed_message'), ephemeral=True)
                return
        finally:
            if upload is not None:
                upload.close()
        self.cog.giveaways[current['giveaway_id']] = panel
        self.state.published = True
        self.stop()
        self._close_image()
        logging.info('Giveaway %s settings updated by %s', current['giveaway_id'], fmt_user(interaction.user))
        await interaction.edit_original_response(
            content=t('giveaway.giveaway_edit_saved_message', giveaway_id=current['giveaway_id']),
            embed=None, view=None,
        )

    async def on_error(self, interaction, error, item):
        logging.error('Giveaway %s editor failed for %s', self.original['giveaway_id'],
                      fmt_user(interaction.user), exc_info=(type(error), error, error.__traceback__))
        send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await send(t('giveaway.giveaway_edit_error_message'), ephemeral=True)
