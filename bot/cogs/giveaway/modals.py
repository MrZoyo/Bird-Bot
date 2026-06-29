import datetime
import logging
import random
import re
import string
from dataclasses import dataclass

import discord
from discord import ui

from bot.utils import fmt_user
from bot.utils.i18n import t
from bot.utils.modal_helpers import add_labeled_file_upload, add_labeled_text_input

from .views import GiveawayPanelView, add_lead_and_three_stat_fields


@dataclass
class GiveawayDraftState:
    creator_id: int
    giveaway_channel_id: int
    default_provider: str
    duration_text: str = ""
    duration_minutes: int = 0
    winner_number: int = 1
    prizes: str = ""
    description: str = ""
    provider: str = ""
    reaction_limit: int = 0
    message_limit: int = 0
    timespent_limit_minutes: int = 0
    image_file: discord.File | None = None
    image_filename: str | None = None
    published: bool = False

    @property
    def provider_or_default(self) -> str:
        return self.provider or self.default_provider

    @property
    def timespent_limit_seconds(self) -> int:
        return self.timespent_limit_minutes * 60


class GiveawayModal(ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        logging.error(
            "Giveaway modal %s failed for %s",
            self.__class__.__name__,
            fmt_user(getattr(interaction, 'user', None)),
            exc_info=(type(error), error, error.__traceback__),
        )
        message = t('giveaway.giveaway_modal_error_message')
        if not interaction.response.is_done():
            await interaction.response.send_message(message)
            return
        await interaction.followup.send(message)


class GiveawayCreateModal(GiveawayModal):
    def __init__(self, bot, db, state: GiveawayDraftState, draft_view=None):
        super().__init__(title=t('giveaway.giveaway_create_modal_title'))
        self.bot = bot
        self.db = db
        self.state = state
        self.draft_view = draft_view

        self.duration = add_labeled_text_input(
            self,
            t('giveaway.giveaway_duration_label'),
            placeholder=t('giveaway.giveaway_duration_placeholder'),
            required=True,
            min_length=2,
            default=state.duration_text or None,
        )
        self.winners = add_labeled_text_input(
            self,
            t('giveaway.giveaway_winners_label'),
            placeholder=t('giveaway.giveaway_winners_placeholder'),
            required=True,
            min_length=1,
            max_length=2,
            default=str(state.winner_number or 1),
        )
        self.prizes = add_labeled_text_input(
            self,
            t('giveaway.giveaway_prizes_label'),
            placeholder=t('giveaway.giveaway_prizes_placeholder'),
            required=True,
            max_length=100,
            default=state.prizes or None,
        )
        self.description = add_labeled_text_input(
            self,
            t('giveaway.giveaway_description_label'),
            placeholder=t('giveaway.giveaway_description_placeholder'),
            required=False,
            default=state.description or t('giveaway.giveaway_description_default'),
            max_length=500,
        )
        self.providers = add_labeled_text_input(
            self,
            t('giveaway.giveaway_provider_label'),
            placeholder=t('giveaway.giveaway_provider_placeholder'),
            required=False,
            default=state.provider or None,
        )

    async def on_submit(self, interaction: discord.Interaction):
        duration_minutes = parse_duration_to_minutes(self.duration.value)
        if duration_minutes <= 0:
            await interaction.response.send_message(
                t('giveaway.giveaway_duration_invalid_message'),
            )
            return
        if not self.winners.value.isdigit() or int(self.winners.value) < 1:
            await interaction.response.send_message(
                t('giveaway.giveaway_winners_invalid_message'),
            )
            return

        self.state.duration_text = self.duration.value
        self.state.duration_minutes = duration_minutes
        self.state.winner_number = int(self.winners.value)
        self.state.prizes = self.prizes.value
        self.state.description = self.description.value
        self.state.provider = self.providers.value

        if self.draft_view is None:
            draft_view = GiveawayDraftView(self.bot, self.db, self.state)
            await interaction.response.send_message(
                embed=draft_view.format_embed(),
                view=draft_view,
            )
        else:
            await refresh_draft_message(interaction, self.draft_view)


class GiveawayLimitsModal(GiveawayModal):
    def __init__(self, draft_view):
        super().__init__(title=t('giveaway.giveaway_limits_modal_title'))
        self.draft_view = draft_view
        self.state = draft_view.state

        self.reaction_limit = add_labeled_text_input(
            self,
            t('giveaway.giveaway_reaction_limit_label'),
            placeholder=t('giveaway.giveaway_limit_placeholder'),
            required=True,
            default=str(self.state.reaction_limit),
            max_length=8,
        )
        self.message_limit = add_labeled_text_input(
            self,
            t('giveaway.giveaway_message_limit_label'),
            placeholder=t('giveaway.giveaway_limit_placeholder'),
            required=True,
            default=str(self.state.message_limit),
            max_length=8,
        )
        self.timespent_limit = add_labeled_text_input(
            self,
            t('giveaway.giveaway_timespent_limit_label'),
            placeholder=t('giveaway.giveaway_limit_placeholder'),
            required=True,
            default=str(self.state.timespent_limit_minutes),
            max_length=8,
        )

    async def on_submit(self, interaction: discord.Interaction):
        values = [
            self.reaction_limit.value,
            self.message_limit.value,
            self.timespent_limit.value,
        ]
        if any(not value.isdigit() for value in values):
            await interaction.response.send_message(
                t('giveaway.giveaway_limit_invalid_message'),
            )
            return

        self.state.reaction_limit = int(self.reaction_limit.value)
        self.state.message_limit = int(self.message_limit.value)
        self.state.timespent_limit_minutes = int(self.timespent_limit.value)

        await refresh_draft_message(interaction, self.draft_view)


class GiveawayImageModal(GiveawayModal):
    def __init__(self, draft_view):
        super().__init__(title=t('giveaway.giveaway_image_modal_title'))
        self.draft_view = draft_view
        self.state = draft_view.state
        self.image = add_labeled_file_upload(
            self,
            t('giveaway.giveaway_image_label'),
            required=False,
            min_values=0,
            max_values=1,
        )

    async def on_submit(self, interaction: discord.Interaction):
        if not self.image.values:
            self._close_existing_image()
            self.state.image_file = None
            self.state.image_filename = None
            await refresh_draft_message(interaction, self.draft_view)
            return

        attachment = self.image.values[0]
        if attachment.content_type and not attachment.content_type.startswith('image/'):
            await interaction.response.send_message(
                t('giveaway.giveaway_image_invalid_message'),
            )
            return

        filename = sanitize_image_filename(attachment.filename)
        image_file = await attachment.to_file(
            filename=filename,
            description=t('giveaway.giveaway_image_description'),
        )
        self._close_existing_image()
        self.state.image_file = image_file
        self.state.image_filename = filename

        await refresh_draft_message(interaction, self.draft_view)

    def _close_existing_image(self):
        if self.state.image_file is not None:
            self.state.image_file.close()


class GiveawayDraftView(ui.View):
    def __init__(self, bot, db, state: GiveawayDraftState):
        super().__init__(timeout=900)
        self.bot = bot
        self.db = db
        self.state = state
        self.published_giveaway_id: str | None = None

        self.edit_button = ui.Button(
            label=t('giveaway.giveaway_draft_edit_button'),
            style=discord.ButtonStyle.secondary,
        )
        self.limits_button = ui.Button(
            label=t('giveaway.giveaway_draft_limits_button'),
            style=discord.ButtonStyle.secondary,
        )
        self.image_button = ui.Button(
            label=t('giveaway.giveaway_draft_image_button'),
            style=discord.ButtonStyle.secondary,
        )
        self.publish_button = ui.Button(
            label=t('giveaway.giveaway_draft_publish_button'),
            style=discord.ButtonStyle.success,
        )

        self.edit_button.callback = self.edit_basic_info
        self.limits_button.callback = self.edit_limits
        self.image_button.callback = self.edit_image
        self.publish_button.callback = self.publish

        self.populate_panel()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.state.creator_id:
            return True
        await interaction.response.send_message(
            t('giveaway.giveaway_draft_owner_only_message'),
        )
        return False

    def populate_panel(self, *, published_giveaway_id: str | None = None) -> None:
        self.clear_items()
        self.published_giveaway_id = published_giveaway_id
        if published_giveaway_id:
            return

        self.add_item(self.edit_button)
        self.add_item(self.limits_button)
        self.add_item(self.image_button)
        self.add_item(self.publish_button)

    def format_embed(self) -> discord.Embed:
        if self.published_giveaway_id:
            return discord.Embed(
                title=t('giveaway.giveaway_published_title'),
                description=t(
                    'giveaway.giveaway_published_message',
                    giveaway_id=self.published_giveaway_id,
                ),
                color=discord.Color.green(),
            )

        image_text = (
            self.state.image_filename
            if self.state.image_filename
            else t('giveaway.giveaway_draft_no_image')
        )

        embed = discord.Embed(
            title=t('giveaway.giveaway_draft_title'),
            color=discord.Color.blurple(),
        )
        add_lead_and_three_stat_fields(
            embed,
            t('giveaway.giveaway_draft_prizes_title'),
            self.state.prizes or t('giveaway.giveaway_draft_missing_value'),
            t('giveaway.giveaway_duration_label'),
            self.state.duration_text or t('giveaway.giveaway_draft_missing_value'),
            t('giveaway.giveaway_provider_label'),
            self.state.provider_or_default,
            t('giveaway.giveaway_winners_label'),
            str(self.state.winner_number),
        )
        embed.add_field(
            name=t('giveaway.giveaway_requirement_title'),
            value=t(
                'giveaway.giveaway_requirement_text',
                reaction_req=self.state.reaction_limit,
                message_req=self.state.message_limit,
                timespent_req=self.state.timespent_limit_minutes,
            ),
            inline=False,
        )
        embed.add_field(
            name=t('giveaway.giveaway_embed_description_title'),
            value=self.state.description or t('giveaway.giveaway_description_default'),
            inline=False,
        )
        embed.add_field(
            name=t('giveaway.giveaway_draft_image_title'),
            value=image_text,
            inline=False,
        )
        return embed

    async def edit_basic_info(self, interaction: discord.Interaction):
        await self._send_modal(
            interaction,
            GiveawayCreateModal(self.bot, self.db, self.state, draft_view=self),
        )

    async def edit_limits(self, interaction: discord.Interaction):
        await self._send_modal(interaction, GiveawayLimitsModal(self))

    async def edit_image(self, interaction: discord.Interaction):
        await self._send_modal(interaction, GiveawayImageModal(self))

    async def _send_modal(self, interaction: discord.Interaction, modal: ui.Modal):
        try:
            await interaction.response.send_modal(modal)
        except discord.HTTPException as error:
            logging.error(
                "Failed to open giveaway modal %s for %s",
                modal.__class__.__name__,
                fmt_user(interaction.user),
                exc_info=(type(error), error, error.__traceback__),
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    t('giveaway.giveaway_modal_open_failed_message'),
                )

    async def publish(self, interaction: discord.Interaction):
        if self.state.published:
            await interaction.response.send_message(
                t('giveaway.giveaway_already_published_message'),
            )
            return
        if not self.state.prizes or self.state.duration_minutes <= 0:
            await interaction.response.send_message(
                t('giveaway.giveaway_draft_missing_basic_message'),
            )
            return

        await interaction.response.defer()
        giveaway_channel = self.bot.get_channel(self.state.giveaway_channel_id)
        if giveaway_channel is None:
            await interaction.followup.send(
                t('giveaway.giveaway_channel_missing_message'),
            )
            return

        giveaway_id = await self.generate_giveaway_id()
        starttime = datetime.datetime.now().isoformat()
        record = self._build_record(giveaway_id, starttime, image_url=None)

        files = []
        if self.state.image_file is not None:
            files.append(self.state.image_file)
            record['image_url'] = self.state.image_file.uri

        panel_view = GiveawayPanelView(
            self.bot,
            giveaway_id,
            self.state.giveaway_channel_id,
            record=record,
            participant_count=0,
        )
        send_kwargs = {
            'embed': panel_view.format_embed(),
            'view': panel_view,
        }
        if files:
            send_kwargs['files'] = files
        message = await giveaway_channel.send(**send_kwargs)

        image_url = None
        if self.state.image_file is not None and message.attachments:
            image_url = message.attachments[0].url
            record['image_url'] = image_url
            panel_view = GiveawayPanelView(
                self.bot,
                giveaway_id,
                self.state.giveaway_channel_id,
                record=record,
                participant_count=0,
            )
            await message.edit(embed=panel_view.format_embed(), view=panel_view)

        await self.db.insert_giveaway(
            giveaway_id,
            message.id,
            starttime,
            self.state.duration_minutes,
            self.state.winner_number,
            self.state.prizes,
            self.state.description,
            interaction.user.id,
            None,
            self.state.reaction_limit,
            self.state.message_limit,
            self.state.timespent_limit_seconds,
            provider=self.state.provider_or_default,
            image_url=image_url,
            image_filename=self.state.image_filename,
            ui_version=2,
        )

        panel_view.message_id = message.id
        giveaway_cog = self.bot.get_cog('GiveawayCog')
        if giveaway_cog:
            giveaway_cog.giveaways[giveaway_id] = panel_view
            await giveaway_cog.save_giveaways(giveaway_id, panel_view)

        self.state.published = True
        self.disable_all_items()
        self.populate_panel(published_giveaway_id=giveaway_id)
        await interaction.edit_original_response(
            content=None,
            embed=self.format_embed(),
            view=self,
        )

    def _build_record(self, giveaway_id, starttime, image_url):
        return {
            'giveaway_id': giveaway_id,
            'message_id': None,
            'starttime': starttime,
            'duration': self.state.duration_minutes,
            'winner_number': self.state.winner_number,
            'prizes': self.state.prizes,
            'description': self.state.description,
            'creator_id': self.state.creator_id,
            'reaction_req': self.state.reaction_limit,
            'message_req': self.state.message_limit,
            'timespent_req': self.state.timespent_limit_seconds,
            'participant_ids': None,
            'winner_ids': None,
            'is_end': 0,
            'provider': self.state.provider_or_default,
            'image_url': image_url,
            'image_filename': self.state.image_filename,
            'ui_version': 2,
        }

    def disable_all_items(self):
        for item in self.walk_children():
            if hasattr(item, 'disabled'):
                item.disabled = True

    async def generate_giveaway_id(self):
        existing_ids = {str(giveaway_id) for giveaway_id in await self.db.fetch_all_giveaway_ids()}
        while True:
            giveaway_id = ''.join(random.choices(string.digits, k=10))
            if giveaway_id not in existing_ids:
                return giveaway_id


def parse_duration_to_minutes(duration_text: str) -> int:
    matches = re.findall(
        r'(\d+)(w|week|weeks|d|day|days|h|hour|hours|m|min|mins|minute|minutes)',
        duration_text,
    )
    duration_in_minutes = 0
    for duration_value, duration_unit in matches:
        value = int(duration_value)
        if duration_unit.startswith('w'):
            duration_in_minutes += value * 7 * 24 * 60
        elif duration_unit.startswith('d'):
            duration_in_minutes += value * 24 * 60
        elif duration_unit.startswith('h'):
            duration_in_minutes += value * 60
        else:
            duration_in_minutes += value
    return duration_in_minutes


def sanitize_image_filename(filename: str) -> str:
    base = re.sub(r'[^A-Za-z0-9_.-]+', '_', filename).strip('._')
    if not base:
        return 'giveaway_image.png'
    if '.' not in base:
        return f'{base}.png'
    return base[:80]


async def refresh_draft_message(
    interaction: discord.Interaction,
    draft_view: GiveawayDraftView,
) -> None:
    draft_view.populate_panel()
    try:
        await interaction.response.edit_message(
            content=None,
            embed=draft_view.format_embed(),
            view=draft_view,
        )
    except discord.HTTPException as error:
        logging.error(
            "Failed to refresh giveaway draft message for %s",
            fmt_user(interaction.user),
            exc_info=(type(error), error, error.__traceback__),
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(
                t('giveaway.giveaway_draft_refresh_failed_message'),
            )
            return
        await interaction.followup.send(
            t('giveaway.giveaway_draft_refresh_failed_message'),
        )
