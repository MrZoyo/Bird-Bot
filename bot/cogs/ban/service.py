import re
from datetime import datetime, timedelta
from typing import Optional

import discord

from bot.utils.i18n import t


DISCORD_INVITE_PREFIXES = (
    'https://discord.gg/',
    'https://discord.com/invite/',
)


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """Parse a compact duration string like ``1d`` or ``30m``."""
    match = re.fullmatch(r'(\d+)([mhdw])', duration_str.strip().lower())
    if not match:
        return None

    amount, unit = match.groups()
    amount = int(amount)
    if amount == 0:
        return None

    if unit == 'm':
        return timedelta(minutes=amount)
    if unit == 'h':
        return timedelta(hours=amount)
    if unit == 'd':
        return timedelta(days=amount)
    if unit == 'w':
        return timedelta(weeks=amount)

    return None


def member_has_ban_permission(member: discord.Member, ban_config: dict) -> bool:
    if member.guild_permissions.administrator:
        return True

    admin_roles = ban_config.get('admin_roles', [])
    if any(role.id in admin_roles for role in member.roles):
        return True

    admin_users = ban_config.get('admin_users', [])
    return member.id in admin_users


def is_admin_channel(channel_id: int | None, admin_channel_id: int | None) -> bool:
    return bool(admin_channel_id) and channel_id == admin_channel_id


def is_valid_discord_invite_link(invite_link: str) -> bool:
    return invite_link.startswith(DISCORD_INVITE_PREFIXES)


def build_ban_notification_embed(
    bot_user: discord.ClientUser,
    user: discord.User,
    reason: str,
    duration: Optional[str] = None,
    unban_time: Optional[datetime] = None,
) -> discord.Embed:
    if duration:
        title = t('ban.tempban_notification_title')
        description = t('ban.tempban_notification_description')
    else:
        title = t('ban.ban_notification_title')
        description = t('ban.ban_notification_description')

    embed = discord.Embed(
        title=title,
        description=description.format(user=user.mention),
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    )
    _set_bot_thumbnail(embed, bot_user)
    _set_user_footer(embed, user)

    embed.add_field(
        name=t('ban.reason_field'),
        value=reason or t('ban.no_reason'),
        inline=False,
    )

    if duration:
        embed.add_field(
            name=t('ban.duration_field'),
            value=duration,
            inline=True,
        )
        if unban_time:
            embed.add_field(
                name=t('ban.unban_time_field'),
                value=_discord_timestamp(unban_time),
                inline=True,
            )
    else:
        embed.add_field(
            name=t('ban.duration_field'),
            value=t('ban.permanent'),
            inline=True,
        )

    return embed


def build_mute_notification_embed(
    bot_user: discord.ClientUser,
    user: discord.User,
    reason: str,
    duration: str,
    unmute_time: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title=t('ban.mute_notification_title'),
        description=t('ban.mute_notification_description').format(user=user.mention),
        color=discord.Color.yellow(),
        timestamp=discord.utils.utcnow(),
    )
    _set_bot_thumbnail(embed, bot_user)
    _set_user_footer(embed, user)

    embed.add_field(
        name=t('ban.mute_reason_field'),
        value=reason or t('ban.no_reason'),
        inline=False,
    )
    embed.add_field(
        name=t('ban.mute_duration_field'),
        value=duration,
        inline=True,
    )
    embed.add_field(
        name=t('ban.mute_end_time_field'),
        value=_discord_timestamp(unmute_time),
        inline=True,
    )

    return embed


def build_tempban_dm_embed(
    user: discord.User,
    guild: discord.Guild,
    reason: str,
    duration: str,
    unban_time: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title=t('ban.tempban_dm_title'),
        description=t('ban.tempban_dm_description').format(guild_name=guild.name),
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow(),
    )
    _set_guild_thumbnail(embed, guild)

    embed.add_field(
        name=t('ban.tempban_dm_reason_field'),
        value=reason,
        inline=False,
    )
    embed.add_field(
        name=t('ban.tempban_dm_duration_field'),
        value=duration,
        inline=True,
    )
    embed.add_field(
        name=t('ban.tempban_dm_unban_time_field'),
        value=_discord_timestamp(unban_time),
        inline=True,
    )
    embed.set_footer(
        text=t('ban.tempban_dm_footer'),
        icon_url=user.display_avatar.url,
    )

    return embed


def build_mute_dm_embed(
    user: discord.User,
    guild: discord.Guild,
    reason: str,
    duration: str,
    unmute_time: datetime,
) -> discord.Embed:
    embed = discord.Embed(
        title=t('ban.mute_dm_title'),
        description=t('ban.mute_dm_description').format(guild_name=guild.name),
        color=discord.Color.yellow(),
        timestamp=discord.utils.utcnow(),
    )
    _set_guild_thumbnail(embed, guild)

    embed.add_field(
        name=t('ban.mute_dm_reason_field'),
        value=reason,
        inline=False,
    )
    embed.add_field(
        name=t('ban.mute_dm_duration_field'),
        value=duration,
        inline=True,
    )
    embed.add_field(
        name=t('ban.mute_dm_unmute_time_field'),
        value=_discord_timestamp(unmute_time),
        inline=True,
    )
    embed.set_footer(
        text=t('ban.mute_dm_footer'),
        icon_url=user.display_avatar.url,
    )

    return embed


def _discord_timestamp(value: datetime) -> str:
    return f"<t:{int(value.timestamp())}:F>"


def _set_bot_thumbnail(embed: discord.Embed, bot_user: discord.ClientUser) -> None:
    if bot_user.avatar:
        embed.set_thumbnail(url=bot_user.avatar.url)


def _set_guild_thumbnail(embed: discord.Embed, guild: discord.Guild) -> None:
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)


def _set_user_footer(embed: discord.Embed, user: discord.User) -> None:
    embed.set_footer(
        text=f"User: {user.display_name}",
        icon_url=user.display_avatar.url,
    )
