from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands, tasks

from bot.utils import check_channel_validity, config, fmt_channel, fmt_guild, fmt_user
from bot.utils.i18n import t
from bot.utils.task_helpers import wait_until_ready_or_stop


DEFAULT_MAX_AGE_DAYS = 3
DEFAULT_INTERVAL_HOURS = 24
DEFAULT_AUDIT_REASON = "Auto cleanup: invite older than {max_age_days} days"


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
    def __init__(self, bot):
        self.bot = bot
        self.settings = self._load_settings()

    async def cog_load(self):
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

    def cog_unload(self):
        if self.invite_cleanup_task.is_running():
            self.invite_cleanup_task.cancel()

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

    @app_commands.command(
        name="invite_cleanup",
        description=locale_str(
            "Run invite cleanup once and return a short summary",
            key="invite_guard.invite_cleanup.description",
        ),
    )
    @app_commands.describe(
        dry_run=locale_str(
            "Only report invites that would be deleted; do not delete them.",
            key="invite_guard.invite_cleanup.params.dry_run",
        ),
    )
    async def invite_cleanup(
        self,
        interaction: discord.Interaction,
        dry_run: bool | None = None,
    ):
        if not await self._can_run_manual_cleanup(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        summary = await self.run_cleanup(
            dry_run=dry_run,
            source="manual",
            respect_enabled=False,
        )
        await interaction.followup.send(self._format_summary(summary), ephemeral=True)

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

        try:
            invites = await guild.invites()
        except discord.Forbidden:
            summary.failed += 1
            logging.error(
                "[InviteCleaner] Cannot list invites for %s. The bot needs permission to view server "
                "invites before it can clean them; usually Manage Guild / Manage Server is required.",
                fmt_guild(guild),
            )
            self._log_summary(summary, source)
            return summary
        except discord.HTTPException as e:
            summary.failed += 1
            logging.error(
                "[InviteCleaner] Failed to list invites for %s: %s",
                fmt_guild(guild),
                e,
            )
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

    async def _can_run_manual_cleanup(self, interaction: discord.Interaction) -> bool:
        return await check_channel_validity(interaction)

    def _get_target_guild(self, settings: InviteCleanerSettings) -> discord.Guild | None:
        if settings.guild_id is None:
            logging.warning("[InviteCleaner] No target guild configured; set invite_guard.guild_id or main.guild_id.")
            return None

        guild = self.bot.get_guild(settings.guild_id)
        if guild is None:
            logging.warning(
                "[InviteCleaner] Target guild %s was not found in bot cache; cleanup skipped.",
                fmt_guild(settings.guild_id),
            )
            return None
        return guild

    def _load_settings(self) -> InviteCleanerSettings:
        main_config = config.get_config('main')
        raw = config.get_config('invite_guard', silent=True)
        if not isinstance(raw, dict):
            raw = {}

        guild_id = _coerce_int(
            _setting_value(raw, 'guild_id', 'INVITE_CLEANER_GUILD_ID', default=main_config.get('guild_id')),
            default=None,
        )
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

    def _apply_loop_interval(self, settings: InviteCleanerSettings) -> None:
        if self.invite_cleanup_task.hours != settings.interval_hours:
            self.invite_cleanup_task.change_interval(hours=settings.interval_hours)

    def _audit_reason(self, settings: InviteCleanerSettings) -> str:
        try:
            return settings.audit_reason.format(max_age_days=settings.max_age_days)
        except (KeyError, IndexError, ValueError):
            return settings.audit_reason

    def _format_summary(self, summary: InviteCleanupSummary) -> str:
        return t(
            'invite_guard.messages.summary',
            dry_run=str(summary.dry_run).lower(),
            scanned=summary.scanned,
            deleted=summary.deleted,
            would_delete=summary.would_delete,
            skipped_whitelist=summary.skipped_whitelist,
            skipped_young=summary.skipped_young,
            skipped_missing_created_at=summary.skipped_missing_created_at,
            failed=summary.failed,
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
