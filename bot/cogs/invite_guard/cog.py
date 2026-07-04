from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands, tasks

from bot.utils import (
    InviteGuardDatabaseManager,
    ShopDatabaseManager,
    check_channel_validity,
    config,
    fmt_channel,
    fmt_guild,
    fmt_user,
)
from bot.utils.components_v2 import clear_legacy_message_payload
from bot.utils.invite_guard_db import InviteLinkRecord, InviteLinkSyncSummary
from bot.utils.i18n import t
from bot.utils.paths import project_path
from bot.utils.task_helpers import wait_until_ready_or_stop


DEFAULT_MAX_AGE_DAYS = 3
DEFAULT_INTERVAL_HOURS = 24
DEFAULT_AUDIT_REASON = "Auto cleanup: invite older than {max_age_days} days"
DEFAULT_LEADERBOARD_INTERVAL_MINUTES = 5
DEFAULT_LEADERBOARD_TOP_N = 15
DEFAULT_INVITE_REWARD_POINTS = 60
DEFAULT_POOLED_ATTRIBUTION_ENABLED = True
DEFAULT_ATTRIBUTION_BATCH_WINDOW_SECONDS = 2
DEFAULT_REWARD_NOTIFICATION_IMAGE = "invite_reward.png"
REWARD_NOTIFICATION_ATTACHMENT_NAME = "invite_reward.png"
LEADERBOARD_PANEL_COLOR = 0x7C3AED


@dataclass(frozen=True)
class InviteCleanerSettings:
    enabled: bool = True
    guild_id: int | None = None
    max_age_days: int = DEFAULT_MAX_AGE_DAYS
    interval_hours: int = DEFAULT_INTERVAL_HOURS
    dry_run: bool = False
    invite_code_whitelist: frozenset[str] = field(default_factory=frozenset)
    invite_creator_whitelist: frozenset[int] = field(default_factory=frozenset)
    audit_reason: str = DEFAULT_AUDIT_REASON


@dataclass(frozen=True)
class InviteLeaderboardSettings:
    enabled: bool = True
    guild_id: int | None = None
    channel_id: int | None = None
    message_id: int | None = None
    interval_minutes: int = DEFAULT_LEADERBOARD_INTERVAL_MINUTES
    top_n: int = DEFAULT_LEADERBOARD_TOP_N
    ignored_codes: frozenset[str] = field(default_factory=frozenset)
    ignored_inviter_ids: frozenset[int] = field(default_factory=frozenset)
    unknown_allow_reattribution: bool = True
    ambiguous_allow_reattribution: bool = True
    require_single_delta_for_attribution: bool = True
    reward_points_per_invite: int = DEFAULT_INVITE_REWARD_POINTS
    pooled_attribution_enabled: bool = DEFAULT_POOLED_ATTRIBUTION_ENABLED
    attribution_batch_window_seconds: float = DEFAULT_ATTRIBUTION_BATCH_WINDOW_SECONDS
    reward_notification_enabled: bool = True
    reward_notification_image: str = DEFAULT_REWARD_NOTIFICATION_IMAGE


@dataclass(frozen=True)
class InviteSnapshot:
    code: str
    uses: int
    inviter_id: int | None
    ignored: bool


@dataclass
class InviteCleanupSummary:
    dry_run: bool
    scanned: int = 0
    deleted: int = 0
    would_delete: int = 0
    skipped_whitelist: int = 0
    skipped_young: int = 0
    skipped_missing_created_at: int = 0
    failed: int = 0

    @property
    def skipped_total(self) -> int:
        return self.skipped_whitelist + self.skipped_young + self.skipped_missing_created_at


class InviteGuardCog(commands.Cog):
    # Class-level default so the missing-image warning is logged only once per
    # process even across settlement batches.
    _reward_image_warned = False

    def __init__(self, bot):
        self.bot = bot
        self.settings = self._load_settings()
        self.leaderboard_settings = self._load_leaderboard_settings()
        self.db_path = config.get_config('main')['db_path']
        self.db = InviteGuardDatabaseManager(self.db_path)
        shop_config = config.get_config('shop', silent=True)
        self.shop_db = ShopDatabaseManager(self.db_path, shop_config if isinstance(shop_config, dict) else {})
        self.invite_cache: dict[str, InviteSnapshot] = {}
        self._invite_cache_initialized = False
        self._invite_cache_lock = asyncio.Lock()
        self._runtime_leaderboard_channel_id = self.leaderboard_settings.channel_id
        self._runtime_leaderboard_message_id = self.leaderboard_settings.message_id
        self._pending_joins: list[discord.Member] = []
        self._settle_task: asyncio.Task | None = None

    async def cog_load(self):
        await self.db.initialize_database()
        if self.leaderboard_settings.reward_points_per_invite > 0:
            await self.shop_db.initialize_database()

        self._apply_loop_interval(self.settings)
        if self.settings.enabled and not self.invite_cleanup_task.is_running():
            self.invite_cleanup_task.start()
            logging.info(
                "[InviteCleaner] Scheduled cleanup every %s hour(s) for %s.",
                self.settings.interval_hours,
                fmt_guild(self.settings.guild_id),
            )
        else:
            logging.info("[InviteCleaner] Scheduled cleanup is disabled by config.")

        self._apply_leaderboard_loop_interval(self.leaderboard_settings)
        if self.leaderboard_settings.enabled and not self.invite_leaderboard_task.is_running():
            self.invite_leaderboard_task.start()
            logging.info(
                "[InviteLeaderboard] Scheduled sync every %s minute(s) for %s.",
                self.leaderboard_settings.interval_minutes,
                fmt_guild(self.leaderboard_settings.guild_id),
            )
        else:
            logging.info("[InviteLeaderboard] Scheduled leaderboard sync is disabled by config.")

    def cog_unload(self):
        if self.invite_cleanup_task.is_running():
            self.invite_cleanup_task.cancel()
        if self.invite_leaderboard_task.is_running():
            self.invite_leaderboard_task.cancel()
        if self._settle_task is not None and not self._settle_task.done():
            self._settle_task.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.leaderboard_settings.enabled or self._invite_cache_initialized:
            return
        await self.initialize_invite_cache(source="ready")

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        settings = self._load_leaderboard_settings()
        if not settings.enabled:
            return

        guild = getattr(invite, "guild", None)
        if guild is None or guild.id != settings.guild_id:
            return

        now = _now_iso()
        record = self._invite_to_record(guild.id, invite, settings)
        if record is None:
            return

        try:
            await self.db.upsert_invite_link(guild.id, record, now)
            self.invite_cache[record.code] = _record_to_snapshot(record)
            logging.info(
                "[InviteLeaderboard] Recorded new invite %s for %s by %s.",
                record.code,
                fmt_guild(guild),
                _fmt_user_id(record.inviter_id),
            )
        except Exception as e:
            logging.error(
                "[InviteLeaderboard] Failed to persist invite create %s in %s: %s",
                record.code,
                fmt_guild(guild),
                e,
                exc_info=True,
            )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        settings = self._load_leaderboard_settings()
        if not settings.enabled:
            return

        guild = getattr(invite, "guild", None)
        if guild is None or guild.id != settings.guild_id:
            return

        code = _normalize_invite_code(getattr(invite, "code", ""))
        if not code:
            return

        try:
            await self.db.mark_invite_inactive(guild.id, code, _now_iso())
            self.invite_cache.pop(code, None)
            logging.info("[InviteLeaderboard] Marked invite %s inactive in %s.", code, fmt_guild(guild))
        except Exception as e:
            logging.error(
                "[InviteLeaderboard] Failed to mark deleted invite %s in %s: %s",
                code,
                fmt_guild(guild),
                e,
                exc_info=True,
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = self._load_leaderboard_settings()
        if not settings.enabled or member.guild.id != settings.guild_id:
            return

        now = _now_iso()
        try:
            user_record = await self.db.record_member_join(member.guild.id, member.id, now)
        except Exception as e:
            logging.error(
                "[InviteLeaderboard] Failed to record join for %s in %s: %s",
                fmt_user(member),
                fmt_guild(member.guild),
                e,
                exc_info=True,
            )
            return

        if int(user_record.get('attribution_locked') or 0):
            logging.info(
                "[InviteLeaderboard] %s rejoined %s but attribution is already locked.",
                fmt_user(member),
                fmt_guild(member.guild),
            )
            return

        if not self._invite_cache_initialized:
            await self.initialize_invite_cache(source="join-before-cache")

        self._enqueue_pending_join(member, settings)

    def _enqueue_pending_join(self, member: discord.Member, settings: InviteLeaderboardSettings) -> None:
        if member.id not in {existing.id for existing in self._pending_joins}:
            self._pending_joins.append(member)

        if self._settle_task is None or self._settle_task.done():
            self._settle_task = asyncio.create_task(
                self._run_settlement_after_window(settings.attribution_batch_window_seconds)
            )

    async def _run_settlement_after_window(self, window_seconds: float) -> None:
        try:
            while True:
                if window_seconds > 0:
                    await asyncio.sleep(window_seconds)
                await self._settle_pending_joins()
                # Members enqueued while _settle_pending_joins was awaiting (invite
                # fetch / DB I/O) land in _pending_joins without spawning a new task,
                # because _enqueue_pending_join sees this task as not done yet. Loop
                # until the queue is empty so they get settled too. Invariant: there
                # must be NO await between this emptiness check and the coroutine
                # returning — on the single-threaded event loop that guarantees no
                # other coroutine can enqueue between "queue observed empty" and
                # "task marked done", closing the stranded-member race window.
                if not self._pending_joins:
                    break
        except Exception as e:
            logging.error(
                "[InviteLeaderboard] Pending join settlement task failed: %s",
                e,
                exc_info=True,
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = self._load_leaderboard_settings()
        if not settings.enabled or member.guild.id != settings.guild_id:
            return

        try:
            await self.db.record_member_leave(member.guild.id, member.id, _now_iso())
        except Exception as e:
            logging.error(
                "[InviteLeaderboard] Failed to record leave for %s in %s: %s",
                fmt_user(member),
                fmt_guild(member.guild),
                e,
                exc_info=True,
            )

    @tasks.loop(hours=DEFAULT_INTERVAL_HOURS)
    async def invite_cleanup_task(self):
        await self.run_cleanup(source="scheduled")

    @invite_cleanup_task.before_loop
    async def before_invite_cleanup_task(self):
        await wait_until_ready_or_stop(
            self.bot,
            self.invite_cleanup_task,
            'InviteGuardCog.invite_cleanup_task',
        )

    @tasks.loop(minutes=DEFAULT_LEADERBOARD_INTERVAL_MINUTES)
    async def invite_leaderboard_task(self):
        settings = self._load_leaderboard_settings()
        self.leaderboard_settings = settings
        self._apply_leaderboard_loop_interval(settings)
        if not settings.enabled:
            return

        await self.sync_invite_links(settings=settings, source="scheduled")
        await self.update_leaderboard_message(settings=settings)

    @invite_leaderboard_task.before_loop
    async def before_invite_leaderboard_task(self):
        await wait_until_ready_or_stop(
            self.bot,
            self.invite_leaderboard_task,
            'InviteGuardCog.invite_leaderboard_task',
        )
        if self.leaderboard_settings.enabled and not self._invite_cache_initialized:
            await self.initialize_invite_cache(source="task-before-loop")

    @app_commands.command(
        name="invite_sync",
        description=locale_str(
            "Sync current Discord invite links and refresh the leaderboard",
            key="invite_guard.invite_sync.description",
        ),
    )
    async def invite_sync(self, interaction: discord.Interaction):
        if not await self._can_run_admin_command(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = self._load_leaderboard_settings()
        summary = await self.sync_invite_links(settings=settings, source="manual")
        if summary is None:
            await interaction.followup.send(t('invite_guard.messages.sync_failed'), ephemeral=True)
            return
        message_id = await self.update_leaderboard_message(settings=settings)
        await interaction.followup.send(
            t(
                'invite_guard.messages.sync_summary',
                scanned=summary.scanned,
                inserted=summary.inserted,
                updated=summary.updated,
                marked_inactive=summary.marked_inactive,
                message_id=message_id or t('invite_guard.labels.none'),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="invite_check_user",
        description=locale_str(
            "Show invite attribution and leaderboard stats for a member",
            key="invite_guard.invite_check_user.description",
        ),
    )
    @app_commands.describe(
        member=locale_str(
            "Member to inspect.",
            key="invite_guard.invite_check_user.params.member",
        ),
    )
    async def invite_check_user(self, interaction: discord.Interaction, member: discord.Member):
        if not await self._can_run_admin_command(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = self._load_leaderboard_settings()
        record = await self.db.get_user(settings.guild_id, member.id)
        if record is None:
            await interaction.followup.send(t('invite_guard.messages.user_not_found'), ephemeral=True)
            return
        await interaction.followup.send(self._format_user_record(record), ephemeral=True)

    @app_commands.command(
        name="invite_create_embed",
        description=locale_str(
            "Create a new invite leaderboard panel in a channel",
            key="invite_guard.invite_create_embed.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "Channel where the invite leaderboard panel should be created.",
            key="invite_guard.invite_create_embed.params.channel",
        ),
    )
    async def invite_create_embed(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self._can_run_admin_command(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = self._load_leaderboard_settings()
        if channel.guild.id != settings.guild_id:
            await interaction.followup.send(t('invite_guard.messages.channel_wrong_guild'), ephemeral=True)
            return

        summary = await self.sync_invite_links(settings=settings, source="manual-create-panel")
        message_id = await self.update_leaderboard_message(
            settings=settings,
            channel_id=channel.id,
            create_new=True,
        )
        await interaction.followup.send(
            t(
                'invite_guard.messages.create_panel',
                scanned=summary.scanned if summary else 0,
                channel=channel.mention,
                message_id=message_id or t('invite_guard.labels.none'),
            ),
            ephemeral=True,
        )

    async def run_cleanup(
        self,
        *,
        dry_run: bool | None = None,
        source: str = "manual",
        respect_enabled: bool = True,
        now: datetime | None = None,
        settings: InviteCleanerSettings | None = None,
    ) -> InviteCleanupSummary:
        settings = settings or self._load_settings()
        self.settings = settings
        self._apply_loop_interval(settings)

        effective_dry_run = settings.dry_run if dry_run is None else bool(dry_run)
        summary = InviteCleanupSummary(dry_run=effective_dry_run)

        if respect_enabled and not settings.enabled:
            logging.info("[InviteCleaner] Cleanup skipped because invite_guard.enabled is false.")
            return summary

        guild = self._get_target_guild(settings)
        if guild is None:
            summary.failed += 1
            self._log_summary(summary, source)
            return summary

        invites = await self._fetch_guild_invites(guild, log_prefix="[InviteCleaner]")
        if invites is None:
            summary.failed += 1
            self._log_summary(summary, source)
            return summary

        summary.scanned = len(invites)
        current_time = _as_aware_utc(now or discord.utils.utcnow())

        for invite in invites:
            try:
                await self._process_invite(invite, guild, settings, summary, current_time)
            except Exception as e:
                summary.failed += 1
                logging.error(
                    "[InviteCleaner] Unexpected error while processing invite %s in %s: %s",
                    getattr(invite, "code", "unknown"),
                    fmt_guild(guild),
                    e,
                    exc_info=True,
                )

        self._log_summary(summary, source)
        return summary

    async def initialize_invite_cache(self, *, source: str) -> InviteLinkSyncSummary | None:
        async with self._invite_cache_lock:
            if self._invite_cache_initialized:
                return None

            settings = self._load_leaderboard_settings()
            if not settings.enabled:
                return None

            summary = await self._sync_invite_links_locked(settings=settings, source=source)
            if summary is not None:
                self._invite_cache_initialized = True
            return summary

    async def sync_invite_links(
        self,
        *,
        settings: InviteLeaderboardSettings | None = None,
        source: str,
    ) -> InviteLinkSyncSummary | None:
        async with self._invite_cache_lock:
            return await self._sync_invite_links_locked(settings=settings, source=source)

    async def _sync_invite_links_locked(
        self,
        *,
        settings: InviteLeaderboardSettings | None = None,
        source: str,
    ) -> InviteLinkSyncSummary | None:
        """Fetch/diff/persist invites. Caller must already hold _invite_cache_lock."""
        settings = settings or self._load_leaderboard_settings()
        guild = self._get_target_guild(settings)
        if guild is None:
            return None

        invites = await self._fetch_guild_invites(guild, log_prefix="[InviteLeaderboard]")
        if invites is None:
            return None

        records = self._invites_to_records(guild.id, invites, settings)
        summary = await self._persist_invite_snapshot(guild.id, records, _now_iso(), source=source)
        logging.info(
            "[InviteLeaderboard] source=%s scanned=%s inserted=%s updated=%s marked_inactive=%s",
            source,
            summary.scanned,
            summary.inserted,
            summary.updated,
            summary.marked_inactive,
        )
        return summary

    async def update_leaderboard_message(
        self,
        *,
        settings: InviteLeaderboardSettings | None = None,
        channel_id: int | None = None,
        create_new: bool = False,
    ) -> int | None:
        settings = settings or self._load_leaderboard_settings()
        if not settings.enabled:
            return None
        effective_channel_id = channel_id or self._runtime_leaderboard_channel_id or settings.channel_id
        if not effective_channel_id:
            logging.warning("[InviteLeaderboard] No leaderboard channel configured.")
            return None
        if settings.message_id and not self._runtime_leaderboard_message_id and not create_new:
            self._runtime_leaderboard_message_id = settings.message_id

        channel = await self._get_message_channel(effective_channel_id)
        if channel is None:
            return None

        view = await self._build_leaderboard_view(settings)
        message_id = None if create_new else (self._runtime_leaderboard_message_id or settings.message_id)

        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(view=view, **clear_legacy_message_payload())
                self._runtime_leaderboard_channel_id = channel.id
                self._runtime_leaderboard_message_id = message.id
                return message.id
            except discord.NotFound:
                logging.warning(
                    "[InviteLeaderboard] Configured message %s was not found in %s; creating a new one.",
                    message_id,
                    fmt_channel(channel),
                )
            except discord.Forbidden:
                logging.error(
                    "[InviteLeaderboard] No permission to edit leaderboard message %s in %s.",
                    message_id,
                    fmt_channel(channel),
                )
                return None
            except discord.HTTPException as e:
                logging.error(
                    "[InviteLeaderboard] Failed to edit leaderboard message %s in %s: %s",
                    message_id,
                    fmt_channel(channel),
                    e,
                )
                return None

        try:
            message = await channel.send(view=view)
            self._runtime_leaderboard_channel_id = channel.id
            self._runtime_leaderboard_message_id = message.id
            logging.warning(
                "[InviteLeaderboard] Created leaderboard message %s in %s. Save it as invite_guard.leaderboard_message_id.",
                message.id,
                fmt_channel(channel),
            )
            return message.id
        except discord.Forbidden:
            logging.error("[InviteLeaderboard] No permission to send leaderboard message in %s.", fmt_channel(channel))
        except discord.HTTPException as e:
            logging.error("[InviteLeaderboard] Failed to send leaderboard message in %s: %s", fmt_channel(channel), e)
        return None

    async def _persist_invite_snapshot(
        self,
        guild_id: int,
        records: list[InviteLinkRecord],
        now: str,
        *,
        source: str,
    ) -> InviteLinkSyncSummary:
        try:
            summary = await self.db.sync_invite_links(guild_id, records, now)
            self.invite_cache = {
                record.code: _record_to_snapshot(record)
                for record in records
            }
            return summary
        except Exception as e:
            logging.error(
                "[InviteLeaderboard] Failed to persist invite snapshot from %s for %s: %s",
                source,
                fmt_guild(guild_id),
                e,
                exc_info=True,
            )
            return InviteLinkSyncSummary(scanned=len(records))

    async def _settle_pending_joins(self) -> None:
        batch = list(self._pending_joins)
        self._pending_joins.clear()
        if not batch:
            return

        settings = self._load_leaderboard_settings()
        now = _now_iso()
        guild = batch[0].guild

        # Rewards collected while the lock is held, paid out after release so Shop
        # DB I/O never blocks invite fetch/diff/persist for the next settlement or
        # the background invite_leaderboard_task sync.
        single_invite_rewards: list[tuple[discord.Member, InviteLinkRecord]] = []
        pooled_rewards: list[tuple[int, str, int]] = []

        async with self._invite_cache_lock:
            previous_cache = dict(self.invite_cache)
            invites = await self._fetch_guild_invites(guild)
            if invites is None:
                for member in batch:
                    await self._mark_join_status(
                        member,
                        status='unknown',
                        code=None,
                        inviter_id=None,
                        allow_reattribution=settings.unknown_allow_reattribution,
                        now=now,
                    )
                return

            records = self._invites_to_records(guild.id, invites, settings)
            deltas = self._find_invite_deltas(records, previous_cache)
            await self._persist_invite_snapshot(guild.id, records, now, source="member_join_settlement")

            total_delta = sum(delta for _, delta in deltas)

            if len(batch) == 1 and len(deltas) == 1 and (
                not settings.require_single_delta_for_attribution or total_delta == 1
            ):
                record, delta = deltas[0]
                await self._attribute_member_from_single_invite(batch[0], record, delta, settings, now)
                return

            batch_ids = {member.id for member in batch}
            pooled_ok = (
                settings.pooled_attribution_enabled
                and bool(deltas)
                and total_delta == len(batch)
                and all(
                    not record.ignored
                    and record.inviter_id is not None
                    and record.inviter_id not in batch_ids
                    for record, _delta in deltas
                )
            )

            if pooled_ok and len(deltas) == 1:
                record, delta = deltas[0]
                for member in batch:
                    try:
                        counted = await self.db.attribute_member(
                            guild.id,
                            member.id,
                            record.inviter_id,
                            record.code,
                            now,
                        )
                    except Exception as e:
                        logging.error(
                            "[InviteLeaderboard] Failed to attribute %s in %s via %s: %s",
                            fmt_user(member),
                            fmt_guild(guild),
                            record.code,
                            e,
                            exc_info=True,
                        )
                        continue
                    if counted:
                        single_invite_rewards.append((member, record))
                        logging.info(
                            "[InviteLeaderboard] Attributed %s in %s to %s via %s (single-invite multi-join) delta=%s.",
                            fmt_user(member),
                            fmt_guild(guild),
                            _fmt_user_id(record.inviter_id),
                            record.code,
                            delta,
                        )
            elif pooled_ok:
                member_ids = [member.id for member in batch]
                awards = [(record.inviter_id, record.code, delta) for record, delta in deltas]
                try:
                    pooled = await self.db.pool_attribute_members(guild.id, member_ids, awards, now)
                except Exception as e:
                    logging.error(
                        "[InviteLeaderboard] Failed to pool-attribute batch in %s: %s",
                        fmt_guild(guild),
                        e,
                        exc_info=True,
                    )
                    pooled = False

                if pooled:
                    codes = ", ".join(f"{record.code}(+{delta})" for record, delta in deltas)
                    logging.info(
                        "[InviteLeaderboard] Pooled attribution settled for %s member(s) %s in %s via %s.",
                        len(batch),
                        [fmt_user(member) for member in batch],
                        fmt_guild(guild),
                        codes,
                    )
                    pooled_rewards.extend(awards)
                else:
                    logging.warning(
                        "[InviteLeaderboard] Pooled attribution rejected (locked member in batch) for %s in %s; "
                        "falling back to ambiguous.",
                        [fmt_user(member) for member in batch],
                        fmt_guild(guild),
                    )
                    for member in batch:
                        await self._mark_join_status(
                            member,
                            status='ambiguous',
                            code=None,
                            inviter_id=None,
                            allow_reattribution=settings.ambiguous_allow_reattribution,
                            now=now,
                        )
            elif deltas:
                codes = ", ".join(f"{record.code}(+{delta})" for record, delta in deltas)
                logging.warning(
                    "[InviteLeaderboard] Ambiguous attribution for batch %s in %s; invite deltas: %s.",
                    [fmt_user(member) for member in batch],
                    fmt_guild(guild),
                    codes,
                )
                for member in batch:
                    await self._mark_join_status(
                        member,
                        status='ambiguous',
                        code=None,
                        inviter_id=None,
                        allow_reattribution=settings.ambiguous_allow_reattribution,
                        now=now,
                    )
            else:
                logging.info(
                    "[InviteLeaderboard] Unknown invite source for batch %s in %s; no invite uses increased.",
                    [fmt_user(member) for member in batch],
                    fmt_guild(guild),
                )
                for member in batch:
                    await self._mark_join_status(
                        member,
                        status='unknown',
                        code=None,
                        inviter_id=None,
                        allow_reattribution=settings.unknown_allow_reattribution,
                        now=now,
                    )

        for member, record in single_invite_rewards:
            await self._award_invite_reward(member, record, settings)

        batch_member_ids = [member.id for member in batch]
        for inviter_id, code, delta in pooled_rewards:
            await self._award_pooled_invite_reward(
                inviter_id=inviter_id,
                code=code,
                delta=delta,
                batch_member_ids=batch_member_ids,
                settings=settings,
                guild=guild,
            )

    async def _attribute_member_from_single_invite(
        self,
        member: discord.Member,
        record: InviteLinkRecord,
        delta: int,
        settings: InviteLeaderboardSettings,
        now: str,
    ) -> None:
        if record.ignored:
            logging.info(
                "[InviteLeaderboard] %s joined %s via ignored invite %s.",
                fmt_user(member),
                fmt_guild(member.guild),
                record.code,
            )
            await self._mark_join_status(
                member,
                status='ignored',
                code=record.code,
                inviter_id=None,
                allow_reattribution=True,
                now=now,
            )
            return

        if record.inviter_id is None:
            logging.info(
                "[InviteLeaderboard] %s joined %s via invite %s without an inviter.",
                fmt_user(member),
                fmt_guild(member.guild),
                record.code,
            )
            await self._mark_join_status(
                member,
                status='unknown',
                code=record.code,
                inviter_id=None,
                allow_reattribution=settings.unknown_allow_reattribution,
                now=now,
            )
            return

        if record.inviter_id == member.id:
            logging.info(
                "[InviteLeaderboard] %s joined %s via self-owned invite %s; not counting it.",
                fmt_user(member),
                fmt_guild(member.guild),
                record.code,
            )
            await self._mark_join_status(
                member,
                status='unknown',
                code=record.code,
                inviter_id=record.inviter_id,
                allow_reattribution=settings.unknown_allow_reattribution,
                now=now,
            )
            return

        try:
            counted = await self.db.attribute_member(
                member.guild.id,
                member.id,
                record.inviter_id,
                record.code,
                now,
            )
        except Exception as e:
            logging.error(
                "[InviteLeaderboard] Failed to attribute %s in %s via %s: %s",
                fmt_user(member),
                fmt_guild(member.guild),
                record.code,
                e,
                exc_info=True,
            )
            return

        if counted:
            await self._award_invite_reward(member, record, settings)
            logging.info(
                "[InviteLeaderboard] Attributed %s in %s to %s via %s delta=%s.",
                fmt_user(member),
                fmt_guild(member.guild),
                _fmt_user_id(record.inviter_id),
                record.code,
                delta,
            )
        else:
            logging.info(
                "[InviteLeaderboard] Did not count %s in %s via %s because attribution is locked or disabled.",
                fmt_user(member),
                fmt_guild(member.guild),
                record.code,
            )

    async def _award_invite_reward(
        self,
        member: discord.Member,
        record: InviteLinkRecord,
        settings: InviteLeaderboardSettings,
    ) -> None:
        reward_points = settings.reward_points_per_invite
        if reward_points <= 0:
            return

        awarded = await self._award_invite_points(
            inviter_id=record.inviter_id,
            points=reward_points,
            note=f"Invite reward: {member.id} via {record.code}",
            log_target=fmt_user(member),
            code=record.code,
        )
        if awarded:
            await self._send_reward_notification(
                inviter_id=record.inviter_id,
                guild=member.guild,
                settings=settings,
                body=t(
                    'invite_guard.notification.body',
                    member=f"<@{member.id}>",
                    guild=member.guild.name,
                    points=reward_points,
                ),
            )

    async def _award_pooled_invite_reward(
        self,
        *,
        inviter_id: int,
        code: str,
        delta: int,
        batch_member_ids: list[int],
        settings: InviteLeaderboardSettings,
        guild: discord.Guild,
    ) -> None:
        reward_points = settings.reward_points_per_invite
        if reward_points <= 0 or delta <= 0:
            return

        total_points = reward_points * delta
        member_ids_text = ", ".join(str(member_id) for member_id in batch_member_ids)
        awarded = await self._award_invite_points(
            inviter_id=inviter_id,
            points=total_points,
            note=(
                f"Pooled invite reward: {delta} join(s) via {code} "
                f"among batch members [{member_ids_text}]"
            ),
            log_target=f"pooled batch of {len(batch_member_ids)} member(s)",
            code=code,
        )
        if awarded:
            await self._send_reward_notification(
                inviter_id=inviter_id,
                guild=guild,
                settings=settings,
                body=t(
                    'invite_guard.notification.body_pooled',
                    count=delta,
                    guild=guild.name,
                    points=total_points,
                ),
            )

    async def _award_invite_points(
        self,
        *,
        inviter_id: int,
        points: int,
        note: str,
        log_target: str,
        code: str,
    ) -> bool:
        operator_id = _get_bot_user_id(self.bot)
        try:
            new_balance = await self.shop_db.update_user_balance_with_record(
                inviter_id,
                points,
                "invite_reward",
                operator_id,
                note,
            )
            logging.info(
                "[InviteReward] Awarded %s point(s) to %s for inviting %s via %s. new_balance=%s",
                points,
                _fmt_user_id(inviter_id),
                log_target,
                code,
                new_balance,
            )
            return True
        except Exception as e:
            logging.error(
                "[InviteReward] Failed to award %s point(s) to %s for inviting %s via %s: %s",
                points,
                _fmt_user_id(inviter_id),
                log_target,
                code,
                e,
                exc_info=True,
            )
            return False

    async def _send_reward_notification(
        self,
        *,
        inviter_id: int,
        guild: discord.Guild,
        settings: InviteLeaderboardSettings,
        body: str,
    ) -> None:
        """DM the inviter after reward points have actually been credited.

        Notification is strictly best-effort: it runs after attribution and Shop
        credit, and any failure here must never affect either of them.
        """
        if not settings.reward_notification_enabled:
            return

        # Same resolution order as update_leaderboard_message: runtime panel ids
        # first, config fallback second. Without a valid panel there is nothing
        # for the link button to point at, so the notification is disabled.
        channel_id = self._runtime_leaderboard_channel_id or settings.channel_id
        message_id = self._runtime_leaderboard_message_id or settings.message_id
        if not channel_id or not message_id:
            logging.debug(
                "[InviteReward] Skipping reward DM to %s: no active leaderboard panel "
                "(channel_id=%s, message_id=%s).",
                _fmt_user_id(inviter_id),
                channel_id,
                message_id,
            )
            return

        user = self.bot.get_user(inviter_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(inviter_id)
            except discord.NotFound:
                logging.warning(
                    "[InviteReward] Cannot send reward DM: user %s was not found.",
                    _fmt_user_id(inviter_id),
                )
                return
            except discord.HTTPException as e:
                logging.error(
                    "[InviteReward] Failed to fetch user %s for reward DM: %s",
                    _fmt_user_id(inviter_id),
                    e,
                )
                return

        try:
            file = self._build_reward_notification_file(settings)
            view = self._build_reward_notification_view(
                body=body,
                guild_id=guild.id,
                channel_id=channel_id,
                message_id=message_id,
                with_image=file is not None,
            )
            if file is not None:
                await user.send(view=view, file=file)
            else:
                await user.send(view=view)
            logging.info(
                "[InviteReward] Sent reward notification DM to %s for %s.",
                fmt_user(user),
                fmt_guild(guild),
            )
        except discord.Forbidden:
            logging.info(
                "[InviteReward] Cannot send reward DM to %s (DMs disabled).",
                fmt_user(user),
            )
        except discord.HTTPException as e:
            logging.error(
                "[InviteReward] Failed to send reward DM to %s: %s",
                fmt_user(user),
                e,
            )
        except Exception as e:
            logging.error(
                "[InviteReward] Unexpected error while sending reward DM to %s: %s",
                fmt_user(user),
                e,
                exc_info=True,
            )

    def _build_reward_notification_file(
        self,
        settings: InviteLeaderboardSettings,
    ) -> discord.File | None:
        image_path = str(
            project_path("resources", "images", Path(settings.reward_notification_image).name)
        )
        if os.path.exists(image_path):
            return discord.File(image_path, filename=REWARD_NOTIFICATION_ATTACHMENT_NAME)

        if not InviteGuardCog._reward_image_warned:
            InviteGuardCog._reward_image_warned = True
            logging.warning(
                "[InviteReward] Reward notification image %s is missing; sending text-only DMs.",
                image_path,
            )
        return None

    def _build_reward_notification_view(
        self,
        *,
        body: str,
        guild_id: int,
        channel_id: int,
        message_id: int,
        with_image: bool,
    ) -> discord.ui.LayoutView:
        container_items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(
                f"### {t('invite_guard.notification.title')}\n{body}"
            ),
        ]
        if with_image:
            gallery = discord.ui.MediaGallery()
            gallery.add_item(media=f"attachment://{REWARD_NOTIFICATION_ATTACHMENT_NAME}")
            container_items.append(gallery)

        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            discord.ui.Container(
                *container_items,
                accent_color=LEADERBOARD_PANEL_COLOR,
            )
        )
        view.add_item(
            discord.ui.ActionRow(
                discord.ui.Button(
                    label=t('invite_guard.notification.leaderboard_button'),
                    style=discord.ButtonStyle.link,
                    url=f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}",
                )
            )
        )
        return view

    async def _mark_join_status(
        self,
        member: discord.Member,
        *,
        status: str,
        code: str | None,
        inviter_id: int | None,
        allow_reattribution: bool,
        now: str,
    ) -> None:
        try:
            await self.db.set_member_attribution_status(
                member.guild.id,
                member.id,
                status,
                code=code,
                inviter_id=inviter_id,
                allow_reattribution=allow_reattribution,
                now=now,
            )
        except Exception as e:
            logging.error(
                "[InviteLeaderboard] Failed to mark %s as %s in %s: %s",
                fmt_user(member),
                status,
                fmt_guild(member.guild),
                e,
                exc_info=True,
            )

    def _find_invite_deltas(
        self,
        records: list[InviteLinkRecord],
        previous_cache: dict[str, InviteSnapshot],
    ) -> list[tuple[InviteLinkRecord, int]]:
        deltas = []
        for record in records:
            previous = previous_cache.get(record.code)
            if previous is None:
                continue
            delta = record.uses - previous.uses
            if delta > 0:
                deltas.append((record, delta))
        return deltas

    async def _build_leaderboard_view(self, settings: InviteLeaderboardSettings) -> discord.ui.LayoutView:
        rows = await self.db.get_leaderboard(settings.guild_id, settings.top_n)
        updated_at = discord.utils.format_dt(discord.utils.utcnow(), style='R')
        if not rows:
            leaderboard_body = t('invite_guard.leaderboard.empty')
        else:
            leaderboard_body = "\n".join(
                t(
                    'invite_guard.leaderboard.entry',
                    badge=_leaderboard_badge(index),
                    user=f"<@{row['user_id']}>",
                    count=row['total_count'],
                )
                for index, row in enumerate(rows, start=1)
            )

        bot_avatar_url = _get_bot_avatar_url(self.bot)
        leaderboard_item = (
            discord.ui.Section(
                leaderboard_body,
                accessory=discord.ui.Thumbnail(bot_avatar_url),
            )
            if bot_avatar_url
            else discord.ui.TextDisplay(leaderboard_body)
        )

        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"### {t('invite_guard.leaderboard.title')}\n"
                    f"{t('invite_guard.leaderboard.updated_at', time=updated_at)}"
                ),
                discord.ui.Separator(),
                leaderboard_item,
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# {t('invite_guard.leaderboard.footer')}"),
                accent_color=LEADERBOARD_PANEL_COLOR,
            )
        )
        return view

    async def _get_message_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            return channel
        try:
            return await self.bot.fetch_channel(channel_id)
        except discord.NotFound:
            logging.warning("[InviteLeaderboard] Leaderboard channel %s was not found.", fmt_channel(channel_id))
        except discord.Forbidden:
            logging.error("[InviteLeaderboard] No permission to fetch leaderboard channel %s.", fmt_channel(channel_id))
        except discord.HTTPException as e:
            logging.error("[InviteLeaderboard] Failed to fetch leaderboard channel %s: %s", fmt_channel(channel_id), e)
        return None

    async def _fetch_guild_invites(
        self,
        guild: discord.Guild,
        *,
        log_prefix: str = "[InviteLeaderboard]",
    ) -> list[discord.Invite] | None:
        try:
            return await guild.invites()
        except discord.Forbidden:
            logging.error(
                "%s Cannot list invites for %s. The bot needs permission to view server invites; "
                "usually Manage Guild / Manage Server is required.",
                log_prefix,
                fmt_guild(guild),
            )
        except discord.HTTPException as e:
            logging.error("%s Failed to list invites for %s: %s", log_prefix, fmt_guild(guild), e)
        return None

    def _invites_to_records(
        self,
        guild_id: int,
        invites: list[discord.Invite],
        settings: InviteLeaderboardSettings,
    ) -> list[InviteLinkRecord]:
        records = []
        for invite in invites:
            record = self._invite_to_record(guild_id, invite, settings)
            if record is not None:
                records.append(record)
        return records

    def _invite_to_record(
        self,
        guild_id: int,
        invite: discord.Invite,
        settings: InviteLeaderboardSettings,
    ) -> InviteLinkRecord | None:
        code = _normalize_invite_code(getattr(invite, "code", ""))
        if not code:
            return None

        inviter = getattr(invite, "inviter", None)
        inviter_id = getattr(inviter, "id", None)
        ignored = code in settings.ignored_codes or inviter_id in settings.ignored_inviter_ids
        channel = getattr(invite, "channel", None)

        return InviteLinkRecord(
            guild_id=guild_id,
            code=code,
            channel_id=getattr(channel, "id", None),
            inviter_id=inviter_id,
            created_at=_datetime_to_iso(getattr(invite, "created_at", None)),
            max_age=_coerce_int(getattr(invite, "max_age", None), default=None),
            max_uses=_coerce_int(getattr(invite, "max_uses", None), default=None),
            uses=max(0, _coerce_int(getattr(invite, "uses", 0), default=0) or 0),
            temporary=bool(getattr(invite, "temporary", False)),
            ignored=ignored,
        )

    async def _process_invite(
        self,
        invite: discord.Invite,
        guild: discord.Guild,
        settings: InviteCleanerSettings,
        summary: InviteCleanupSummary,
        current_time: datetime,
    ) -> None:
        created_at = getattr(invite, "created_at", None)
        if created_at is None:
            summary.skipped_missing_created_at += 1
            logging.debug(
                "[InviteCleaner] Skipping invite %s because created_at is missing.",
                getattr(invite, "code", "unknown"),
            )
            return

        code = _normalize_invite_code(getattr(invite, "code", ""))
        if code in settings.invite_code_whitelist:
            summary.skipped_whitelist += 1
            logging.debug("[InviteCleaner] Skipping whitelisted invite %s.", code)
            return

        inviter = getattr(invite, "inviter", None)
        if await self._is_whitelisted_creator(inviter, guild, settings):
            summary.skipped_whitelist += 1
            logging.debug(
                "[InviteCleaner] Skipping invite %s from whitelisted creator %s.",
                code,
                fmt_user(inviter),
            )
            return

        created_time = _as_aware_utc(created_at)
        age = current_time - created_time
        if age <= timedelta(days=settings.max_age_days):
            summary.skipped_young += 1
            return

        await self._delete_or_report_invite(invite, settings, summary, age)

    async def _delete_or_report_invite(
        self,
        invite: discord.Invite,
        settings: InviteCleanerSettings,
        summary: InviteCleanupSummary,
        age: timedelta,
    ) -> None:
        code = _normalize_invite_code(getattr(invite, "code", ""))
        inviter = getattr(invite, "inviter", None)
        uses = getattr(invite, "uses", None)
        max_age = getattr(invite, "max_age", None)
        age_days = age.total_seconds() / 86400

        if summary.dry_run:
            summary.would_delete += 1
            logging.info(
                "[InviteCleaner] DRY RUN: would delete invite %s created_by=%s age_days=%.2f "
                "uses=%s max_age=%s",
                code,
                fmt_user(inviter),
                age_days,
                uses,
                max_age,
            )
            return

        try:
            await invite.delete(reason=self._audit_reason(settings))
            summary.deleted += 1
            logging.info(
                "[InviteCleaner] Deleted invite %s created_by=%s age_days=%.2f uses=%s max_age=%s",
                code,
                fmt_user(inviter),
                age_days,
                uses,
                max_age,
            )
        except discord.Forbidden:
            summary.failed += 1
            logging.error(
                "[InviteCleaner] Cannot delete invite %s. The bot needs permission to delete invites; "
                "usually Manage Guild / Manage Server or the relevant channel Manage Channels permission is required.",
                code,
            )
        except discord.NotFound:
            logging.debug("[InviteCleaner] Invite %s was already gone before deletion.", code)
        except discord.HTTPException as e:
            summary.failed += 1
            logging.error("[InviteCleaner] Failed to delete invite %s: %s", code, e)

    async def _is_whitelisted_creator(
        self,
        inviter: discord.User | discord.Member | None,
        guild: discord.Guild,
        settings: InviteCleanerSettings,
    ) -> bool:
        if inviter is None:
            return False

        inviter_id = getattr(inviter, "id", None)
        if inviter_id in settings.invite_creator_whitelist:
            return True

        try:
            if await self.bot.is_owner(inviter):
                return True
        except Exception as e:
            logging.debug("[InviteCleaner] Could not check bot owner for %s: %s", fmt_user(inviter), e)

        member = inviter if isinstance(inviter, discord.Member) else guild.get_member(inviter_id)
        if member is None and inviter_id is not None:
            try:
                member = await guild.fetch_member(inviter_id)
            except discord.NotFound:
                return False
            except discord.Forbidden:
                logging.debug(
                    "[InviteCleaner] Cannot fetch invite creator %s for admin whitelist check.",
                    fmt_user(inviter),
                )
                return False
            except discord.HTTPException as e:
                logging.debug(
                    "[InviteCleaner] Failed to fetch invite creator %s for admin whitelist check: %s",
                    fmt_user(inviter),
                    e,
                )
                return False

        if member is None:
            return False

        permissions = getattr(member, "guild_permissions", None)
        if getattr(permissions, "administrator", False):
            return True

        return self._member_has_admin_channel_access(member)

    def _member_has_admin_channel_access(self, member: discord.Member) -> bool:
        admin_channel_id = config.get_config('main').get('admin_channel_id')
        if not admin_channel_id:
            return False

        channel = self.bot.get_channel(admin_channel_id)
        if channel is None:
            logging.debug(
                "[InviteCleaner] Admin channel %s is not cached; invite creator admin-channel whitelist skipped.",
                fmt_channel(admin_channel_id),
            )
            return False

        permissions_for = getattr(channel, "permissions_for", None)
        if permissions_for is None:
            return False

        return bool(getattr(permissions_for(member), "view_channel", False))

    async def _can_run_admin_command(self, interaction: discord.Interaction) -> bool:
        return await check_channel_validity(interaction)

    def _get_target_guild(self, settings: InviteCleanerSettings | InviteLeaderboardSettings) -> discord.Guild | None:
        if settings.guild_id is None:
            logging.warning("[InviteGuard] No target guild configured; set main.guild_id.")
            return None

        guild = self.bot.get_guild(settings.guild_id)
        if guild is None:
            logging.warning(
                "[InviteGuard] Target guild %s was not found in bot cache; operation skipped.",
                fmt_guild(settings.guild_id),
            )
            return None
        return guild

    def _load_settings(self) -> InviteCleanerSettings:
        main_config = config.get_config('main')
        raw = config.get_config('invite_guard', silent=True)
        if not isinstance(raw, dict):
            raw = {}

        guild_id = _coerce_int(main_config.get('guild_id'), default=None)
        max_age_days = max(
            1,
            _coerce_int(
                _setting_value(raw, 'max_age_days', 'INVITE_CLEANER_MAX_AGE_DAYS', default=DEFAULT_MAX_AGE_DAYS),
                default=DEFAULT_MAX_AGE_DAYS,
            ),
        )
        interval_hours = max(
            1,
            _coerce_int(
                _setting_value(raw, 'interval_hours', 'INVITE_CLEANER_INTERVAL_HOURS', default=DEFAULT_INTERVAL_HOURS),
                default=DEFAULT_INTERVAL_HOURS,
            ),
        )

        return InviteCleanerSettings(
            enabled=_coerce_bool(
                _setting_value(raw, 'enabled', 'INVITE_CLEANER_ENABLED', default=True),
                default=True,
            ),
            guild_id=guild_id,
            max_age_days=max_age_days,
            interval_hours=interval_hours,
            dry_run=_coerce_bool(
                _setting_value(raw, 'dry_run', 'INVITE_CLEANER_DRY_RUN', default=False),
                default=False,
            ),
            invite_code_whitelist=_coerce_code_set(
                _setting_value(raw, 'invite_code_whitelist', 'INVITE_CODE_WHITELIST', default=[]),
            ),
            invite_creator_whitelist=_coerce_int_set(
                _setting_value(raw, 'invite_creator_whitelist', 'INVITE_CREATOR_WHITELIST', default=[]),
            ),
            audit_reason=str(
                _setting_value(raw, 'audit_reason', 'INVITE_CLEANER_AUDIT_REASON', default=DEFAULT_AUDIT_REASON)
                or DEFAULT_AUDIT_REASON
            ),
        )

    def _load_leaderboard_settings(self) -> InviteLeaderboardSettings:
        raw = config.get_config('invite_guard', silent=True)
        if not isinstance(raw, dict):
            raw = {}

        cleaner_settings = self._load_settings()
        ignored_codes = set(cleaner_settings.invite_code_whitelist)
        ignored_codes.update(
            _coerce_code_set(
                _setting_value(raw, 'ignored_codes', 'INVITE_IGNORED_CODES', default=[]),
            )
        )
        ignored_inviter_ids = _coerce_int_set(
            _setting_value(raw, 'ignored_inviter_ids', 'INVITE_IGNORED_INVITER_IDS', default=[]),
        )

        guild_id = cleaner_settings.guild_id
        interval_minutes = max(
            1,
            _coerce_int(
                _setting_value(
                    raw,
                    'leaderboard_interval_minutes',
                    'INVITE_LEADERBOARD_INTERVAL_MINUTES',
                    default=DEFAULT_LEADERBOARD_INTERVAL_MINUTES,
                ),
                default=DEFAULT_LEADERBOARD_INTERVAL_MINUTES,
            ),
        )
        top_n = max(
            1,
            _coerce_int(
                _setting_value(raw, 'leaderboard_top_n', 'INVITE_LEADERBOARD_TOP_N', default=DEFAULT_LEADERBOARD_TOP_N),
                default=DEFAULT_LEADERBOARD_TOP_N,
            ),
        )
        reward_points_per_invite = max(
            0,
            _coerce_int(
                _setting_value(
                    raw,
                    'reward_points_per_invite',
                    'INVITE_REWARD_POINTS_PER_INVITE',
                    default=DEFAULT_INVITE_REWARD_POINTS,
                ),
                default=DEFAULT_INVITE_REWARD_POINTS,
            ),
        )
        attribution_batch_window_seconds = max(
            0.0,
            _coerce_float(
                _setting_value(
                    raw,
                    'attribution_batch_window_seconds',
                    'INVITE_ATTRIBUTION_BATCH_WINDOW_SECONDS',
                    default=DEFAULT_ATTRIBUTION_BATCH_WINDOW_SECONDS,
                ),
                default=DEFAULT_ATTRIBUTION_BATCH_WINDOW_SECONDS,
            ),
        )

        return InviteLeaderboardSettings(
            enabled=_coerce_bool(
                _setting_value(raw, 'leaderboard_enabled', 'INVITE_LEADERBOARD_ENABLED', default=True),
                default=True,
            ),
            guild_id=guild_id,
            channel_id=_coerce_int(
                _setting_value(raw, 'leaderboard_channel_id', 'INVITE_LEADERBOARD_CHANNEL_ID', default=None),
                default=None,
            ),
            message_id=_coerce_int(
                _setting_value(raw, 'leaderboard_message_id', 'INVITE_LEADERBOARD_MESSAGE_ID', default=None),
                default=None,
            ),
            interval_minutes=interval_minutes,
            top_n=top_n,
            ignored_codes=frozenset(ignored_codes),
            ignored_inviter_ids=ignored_inviter_ids,
            unknown_allow_reattribution=_coerce_bool(
                _setting_value(
                    raw,
                    'unknown_allow_reattribution',
                    'INVITE_UNKNOWN_ALLOW_REATTRIBUTION',
                    default=True,
                ),
                default=True,
            ),
            ambiguous_allow_reattribution=_coerce_bool(
                _setting_value(
                    raw,
                    'ambiguous_allow_reattribution',
                    'INVITE_AMBIGUOUS_ALLOW_REATTRIBUTION',
                    default=True,
                ),
                default=True,
            ),
            require_single_delta_for_attribution=_coerce_bool(
                _setting_value(
                    raw,
                    'require_single_delta_for_attribution',
                    'INVITE_REQUIRE_SINGLE_DELTA_FOR_ATTRIBUTION',
                    default=True,
                ),
                default=True,
            ),
            reward_points_per_invite=reward_points_per_invite,
            pooled_attribution_enabled=_coerce_bool(
                _setting_value(
                    raw,
                    'pooled_attribution_enabled',
                    'INVITE_POOLED_ATTRIBUTION_ENABLED',
                    default=DEFAULT_POOLED_ATTRIBUTION_ENABLED,
                ),
                default=DEFAULT_POOLED_ATTRIBUTION_ENABLED,
            ),
            attribution_batch_window_seconds=attribution_batch_window_seconds,
            reward_notification_enabled=_coerce_bool(
                _setting_value(
                    raw,
                    'reward_notification_enabled',
                    'INVITE_REWARD_NOTIFICATION_ENABLED',
                    default=True,
                ),
                default=True,
            ),
            reward_notification_image=str(
                _setting_value(
                    raw,
                    'reward_notification_image',
                    'INVITE_REWARD_NOTIFICATION_IMAGE',
                    default=DEFAULT_REWARD_NOTIFICATION_IMAGE,
                )
                or DEFAULT_REWARD_NOTIFICATION_IMAGE
            ),
        )

    def _apply_loop_interval(self, settings: InviteCleanerSettings) -> None:
        if self.invite_cleanup_task.hours != settings.interval_hours:
            self.invite_cleanup_task.change_interval(hours=settings.interval_hours)

    def _apply_leaderboard_loop_interval(self, settings: InviteLeaderboardSettings) -> None:
        if self.invite_leaderboard_task.minutes != settings.interval_minutes:
            self.invite_leaderboard_task.change_interval(minutes=settings.interval_minutes)

    def _audit_reason(self, settings: InviteCleanerSettings) -> str:
        try:
            return settings.audit_reason.format(max_age_days=settings.max_age_days)
        except (KeyError, IndexError, ValueError):
            return settings.audit_reason

    def _format_user_record(self, record: dict[str, Any]) -> str:
        return t(
            'invite_guard.messages.user_summary',
            user=f"<@{record['user_id']}>",
            invited_count=record['invited_count'],
            pooled_count=record['pooled_count'],
            invited_by=_fmt_user_id(record['invited_by_user_id']),
            invited_by_code=record['invited_by_code'] or t('invite_guard.labels.none'),
            attribution_status=record['attribution_status'],
            attribution_locked=record['attribution_locked'],
            allow_reattribution=record['allow_reattribution'],
            join_count=record['join_count'],
            leave_count=record['leave_count'],
            last_joined_at=record['last_joined_at'] or t('invite_guard.labels.none'),
            last_left_at=record['last_left_at'] or t('invite_guard.labels.none'),
        )

    def _log_summary(self, summary: InviteCleanupSummary, source: str) -> None:
        logging.info(
            "[InviteCleaner] source=%s scanned=%s deleted=%s would_delete=%s skipped=%s failed=%s dry_run=%s",
            source,
            summary.scanned,
            summary.deleted,
            summary.would_delete,
            summary.skipped_total,
            summary.failed,
            str(summary.dry_run).lower(),
        )


def _setting_value(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    for key in keys:
        if key in os.environ:
            return os.environ[key]
    return default


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _coerce_int(value: Any, *, default: int | None) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, *, default: float) -> float:
    if isinstance(value, bool) or value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_code_set(value: Any) -> frozenset[str]:
    return frozenset(
        code
        for code in (_normalize_invite_code(item) for item in _iter_config_values(value))
        if code
    )


def _coerce_int_set(value: Any) -> frozenset[int]:
    ids = set()
    for item in _iter_config_values(value):
        user_id = _coerce_int(item, default=None)
        if user_id is not None:
            ids.add(user_id)
    return frozenset(ids)


def _iter_config_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(',')]
    if isinstance(value, list | tuple | set | frozenset):
        return list(value)
    return [value]


def _normalize_invite_code(value: Any) -> str:
    code = str(value or "").strip()
    if not code:
        return ""
    code = code.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if "/" in code:
        code = code.rsplit("/", 1)[-1]
    return code.strip()


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _as_aware_utc(value).isoformat()


def _now_iso() -> str:
    return discord.utils.utcnow().isoformat()


def _record_to_snapshot(record: InviteLinkRecord) -> InviteSnapshot:
    return InviteSnapshot(
        code=record.code,
        uses=record.uses,
        inviter_id=record.inviter_id,
        ignored=record.ignored,
    )


def _fmt_user_id(user_id: int | None) -> str:
    if user_id is None:
        return "unknown"
    return f"<@{user_id}> ({user_id})"


def _leaderboard_badge(rank: int) -> str:
    return {
        1: "🥇",
        2: "🥈",
        3: "🥉",
    }.get(rank, f"🔹 #{rank:02d}")


def _get_bot_avatar_url(bot: commands.Bot) -> str | None:
    user = getattr(bot, "user", None)
    avatar = getattr(user, "display_avatar", None)
    url = getattr(avatar, "url", None)
    return str(url) if url else None


def _get_bot_user_id(bot: commands.Bot) -> int:
    user = getattr(bot, "user", None)
    user_id = getattr(user, "id", None)
    return int(user_id) if user_id else 0
