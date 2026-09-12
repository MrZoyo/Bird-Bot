"""Monthly invite settlement and winner notifications."""
import hashlib
import logging

import discord

from bot.utils import fmt_guild, fmt_user
from bot.utils.i18n import t
from bot.utils.invite_months import month_key


def build_reward_view(cog, reward, settings, *, guild_name: str, with_image: bool, preview: bool = False):
    year, month = map(int, reward['month'].split('-'))
    rank = reward['rank']
    placement = t(f'invite_guard.monthly.rank_{rank}') if rank <= 3 else t('invite_guard.monthly.rank_other', rank=rank)
    body = t('invite_guard.monthly.notification_body', guild=guild_name, month=month,
             placement=placement, count=reward['total_count'], points=reward['points'])
    if preview:
        body = t('invite_guard.monthly.preview') + '\n\n' + body
    return cog._build_reward_notification_view(
        title=t('invite_guard.monthly.notification_title', month=month),
        body=body,
        footer=t('invite_guard.monthly.notification_footer', year=year, month=month),
        guild_id=settings.guild_id,
        channel_id=cog._runtime_leaderboard_channel_id or settings.channel_id,
        message_id=cog._runtime_leaderboard_message_id or settings.message_id,
        with_image=with_image,
    )


async def send_reward_notification(cog, reward, settings, *, preview: bool = False) -> int | None:
    user = cog.bot.get_user(reward['user_id']) or await cog.bot.fetch_user(reward['user_id'])
    if user.bot:
        return None
    guild = cog.bot.get_guild(settings.guild_id)
    if guild is None:
        guild = await cog.bot.fetch_guild(settings.guild_id)
    file = cog._build_reward_notification_file(settings)
    try:
        view = build_reward_view(cog, reward, settings, guild_name=guild.name,
                                 with_image=file is not None, preview=preview)
        identity = f"invite-monthly:{reward['guild_id']}:{reward['month']}:{reward['user_id']}"
        if preview:
            identity += ':preview'
        nonce = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], 'big')
        kwargs = dict(view=view, nonce=nonce, allowed_mentions=discord.AllowedMentions.none())
        if file is not None:
            kwargs['file'] = file
        message = await user.send(**kwargs)
        logging.info('[InviteMonthly] Sent reward DM to %s for %s, month=%s.',
                     fmt_user(user), fmt_guild(guild), reward['month'])
        return message.id
    finally:
        if file is not None:
            file.close()


async def settle_months(cog, settings, now=None):
    if not settings.monthly_enabled or not settings.enabled:
        return
    now = now or discord.utils.utcnow()
    async with cog._monthly_settlement_lock:
        await cog.monthly_db.ensure_tracking(settings.guild_id, now, settings.monthly_timezone)
        current = month_key(now, settings.monthly_timezone)
        key = await cog.monthly_db.next_unsettled_month(settings.guild_id)
        while key and key < current:
            # Serialize the closing snapshot with attribution. No old-month
            # credit can be appended after the winners have been frozen.
            async with cog._invite_cache_lock:
                candidates = await cog.monthly_db.get_leaderboard(settings.guild_id, key, settings.monthly_timezone)
                winners = await cog._filter_human_leaderboard_rows(candidates, 10, strict=True)
                if await cog.monthly_db.freeze_results(settings.guild_id, key, winners, now):
                    logging.info('[InviteMonthly] Settled month=%s for %s, winners=%s.',
                                 key, fmt_guild(settings.guild_id), len(winners))
            key = await cog.monthly_db.next_unsettled_month(settings.guild_id)

        for reward in await cog.monthly_db.get_rewards(settings.guild_id, pending_only=True):
            if not reward['paid_at']:
                try:
                    await cog.shop_db.update_user_balance_with_record(
                        reward['user_id'], reward['points'], 'invite_monthly_reward', cog.bot.user.id,
                        f"Monthly invite leaderboard {reward['month']}: rank {reward['rank']}, {reward['total_count']} invites",
                        idempotency_key=f"invite-monthly:{settings.guild_id}:{reward['month']}:{reward['user_id']}",
                    )
                    await cog.monthly_db.mark_paid(reward, now)
                except Exception:
                    logging.exception('[InviteMonthly] Reward payment failed for %s, month=%s; will retry.',
                                      fmt_user(reward['user_id']), reward['month'])
                    continue
            panel_ready = (cog._runtime_leaderboard_channel_id or settings.channel_id) and (
                cog._runtime_leaderboard_message_id or settings.message_id
            )
            if not panel_ready or not settings.reward_notification_enabled:
                continue
            if not await cog.monthly_db.claim_notification(reward):
                continue
            try:
                message_id = await send_reward_notification(cog, reward, settings)
                await cog.monthly_db.finish_notification(reward, 'sent' if message_id else 'failed', message_id)
            except Exception:
                await cog.monthly_db.finish_notification(reward, 'failed')
                logging.exception('[InviteMonthly] Reward DM failed for %s, month=%s; payment is preserved.',
                                  fmt_user(reward['user_id']), reward['month'])
