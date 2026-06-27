# bot/utils/role_helpers.py
import logging
from typing import Iterable, Sequence

import discord

from .log_helpers import fmt_role, fmt_user


_HIERARCHY_ERROR_MESSAGE = (
    "❌ Bot 角色层级不足：有目标角色的层级等于或高于 Bot 自身角色。\n"
    "请联系管理员到 **服务器设置 → 角色** 里，把 Bot 的角色拖到所有功能性角色（星座 / MBTI / 性别 / 成就等）之上。\n"
    "（提示：即使 Bot 有 Administrator 权限，Discord 的角色层级规则仍然独立生效。）"
)

_GENERIC_ERROR_MESSAGE = "❌ 角色操作失败，请稍后重试或联系管理员。"


async def safe_member_role_edit(
    interaction: discord.Interaction,
    *,
    remove: Iterable[discord.Role | None] = (),
    add: Iterable[discord.Role | None] = (),
    reason: str,
    context: str,
) -> bool:
    """Apply remove+add on ``interaction.user`` with hierarchy-aware diagnostics.

    Discord's role hierarchy requires the bot's top_role to be strictly higher
    than any role it touches; Administrator permission does NOT override this.
    On ``discord.Forbidden`` this logs exactly which roles are at or above
    bot.top_role (name + position) so operators can pinpoint what to reorder,
    then sends the user a readable ephemeral followup.

    Returns True on success, False on any failure (caller should early-return).
    ``None`` entries in ``remove``/``add`` are silently skipped (covers the
    case where a configured role id no longer exists in the guild).
    """
    remove_list: Sequence[discord.Role] = [r for r in remove if r is not None]
    add_list: Sequence[discord.Role] = [r for r in add if r is not None]

    member = interaction.user
    try:
        if remove_list:
            await member.remove_roles(*remove_list, reason=reason)
        if add_list:
            await member.add_roles(*add_list, reason=reason)
        return True
    except discord.Forbidden:
        bot_top = interaction.guild.me.top_role
        blockers_remove = [(r.name, r.position) for r in remove_list if r >= bot_top]
        blockers_add = [(r.name, r.position) for r in add_list if r >= bot_top]
        logging.error(
            "[%s] Role hierarchy block for %s: "
            "bot top_role=%s (pos=%d); remove blocked=%s; add blocked=%s",
            context,
            fmt_user(member),
            fmt_role(bot_top),
            bot_top.position,
            blockers_remove,
            blockers_add,
        )
        try:
            await interaction.followup.send(_HIERARCHY_ERROR_MESSAGE, ephemeral=True)
        except discord.HTTPException:
            pass
        return False
    except discord.HTTPException as exc:
        logging.error(
            "[%s] HTTPException updating roles for %s: %s",
            context,
            fmt_user(member),
            exc,
        )
        try:
            await interaction.followup.send(_GENERIC_ERROR_MESSAGE, ephemeral=True)
        except discord.HTTPException:
            pass
        return False
