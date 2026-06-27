import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from bot.utils import check_channel_validity, config, fmt_channel
from bot.utils.achievement_visibility import (
    filter_visible_achievements,
    filter_visible_role_types,
    resolve_hidden_achievement_types,
)
from bot.utils.i18n import t
from bot.utils.role_db import RoleDatabaseManager

from .views import AchievementRoleView, GenderView, MBTIView, SignatureView, StarSignView


def _escape_markdown_table_cell(value: object) -> str:
    """Keep markdown tables readable when names contain special characters."""
    return str(value).replace("|", "\\|").replace("\n", " ")


class RoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.main_config = config.get_config('main')
        self.role_db = RoleDatabaseManager(self.main_config['db_path'])

        self.achievement_config = config.get_config('achievements')

        self.role_config = config.get_config('role')
        # Existing config loads
        hidden_achievement_types = resolve_hidden_achievement_types()
        self.achievements = filter_visible_achievements(
            self.achievement_config['achievements'],
            hidden_achievement_types,
        )
        self.role_type_name = filter_visible_role_types(
            self.role_config['role_type_name'],
            hidden_achievement_types,
        )

        self.role_pickup_title = t('role.role_pickup_title')
        self.role_pickup_footer = t('role.role_pickup_footer')

        # StarSign configs
        self.starsign_name = self.role_config['starsign_name']
        self.starsign_pickup_title = t('role.starsign_pickup_title')
        self.starsign_pickup_footer = t('role.starsign_pickup_footer')
        self.starsign_fire_title = t('role.starsign_fire_title')
        self.starsign_fire_description = t('role.starsign_fire_description')
        self.starsign_earth_title = t('role.starsign_earth_title')
        self.starsign_earth_description = t('role.starsign_earth_description')
        self.starsign_air_title = t('role.starsign_air_title')
        self.starsign_air_description = t('role.starsign_air_description')
        self.starsign_water_title = t('role.starsign_water_title')
        self.starsign_water_description = t('role.starsign_water_description')

        # MBTI configs
        self.mbti_name = self.role_config['mbti_name']
        self.mbti_pickup_title = t('role.mbti_pickup_title')
        self.mbti_pickup_footer = t('role.mbti_pickup_footer')
        self.mbti_first_field_title = t('role.mbti_first_field_title')
        self.mbti_first_field_description = t('role.mbti_first_field_description')
        self.mbti_SP_title = t('role.mbti_SP_title')
        self.mbti_SP_description = t('role.mbti_SP_description')
        self.mbti_SJ_title = t('role.mbti_SJ_title')
        self.mbti_SJ_description = t('role.mbti_SJ_description')
        self.mbti_NF_title = t('role.mbti_NF_title')
        self.mbti_NF_description = t('role.mbti_NF_description')
        self.mbti_NT_title = t('role.mbti_NT_title')
        self.mbti_NT_description = t('role.mbti_NT_description')

        # Gender configs - new additions
        self.gender_name = self.role_config['gender_name']
        self.gender_pickup_title = t('role.gender_pickup_title')
        self.gender_pickup_footer = t('role.gender_pickup_footer')
        self.gender_success_message = t('role.gender_success_message')
        self.gender_remove_message = t('role.gender_remove_message')
        self.gender_tree_title = t('role.gender_tree_title')
        self.gender_tree_description = t('role.gender_tree_description')
        self.gender_sakura_title = t('role.gender_sakura_title')
        self.gender_sakura_description = t('role.gender_sakura_description')
        self.gender_ninja_title = t('role.gender_ninja_title')
        self.gender_ninja_description = t('role.gender_ninja_description')

    def _get_panel_role_targets(self, panel_type: str) -> list[dict[str, object]]:
        if panel_type == 'role':
            enabled_types = {role_type['type'] for role_type in self.role_type_name}
            return [
                {
                    'label': achievement['name'],
                    'role_id': achievement.get('role_id'),
                }
                for achievement in self.achievements
                if achievement.get('type') in enabled_types
            ]

        if panel_type == 'starsign':
            return [
                {
                    'label': star_sign['name'],
                    'role_id': star_sign.get('role_id'),
                }
                for star_sign in self.starsign_name
            ]

        if panel_type == 'mbti':
            return [
                {
                    'label': mbti['name'],
                    'role_id': mbti.get('role_id'),
                }
                for mbti in self.mbti_name
            ]

        if panel_type == 'gender':
            return [
                {
                    'label': gender['name'],
                    'role_id': gender.get('role_id'),
                }
                for gender in self.gender_name
            ]

        return []

    def _build_role_check_report(self, guild: discord.Guild, panel_name: str, panel_type: str) -> tuple[bool, str]:
        targets = self._get_panel_role_targets(panel_type)
        passed_count = 0
        lines = [
            f"**{panel_name} 关联身份组校验**",
        ]

        if not targets:
            lines.append("")
            lines.append("没有找到任何可校验的 `role_id`，未创建领取面板。")
            return False, "\n".join(lines)

        table_lines = [
            "| 项目 | Role ID | 结果 | 服务器身份组 |",
            "| --- | --- | --- | --- |",
        ]

        all_passed = True
        for target in targets:
            label = _escape_markdown_table_cell(target.get('label', '未命名'))
            role_id = target.get('role_id')

            if not isinstance(role_id, int) or role_id <= 0:
                status = "未配置"
                role_name = "-"
                role_id_display = "未配置"
                all_passed = False
            else:
                role = guild.get_role(role_id)
                role_id_display = str(role_id)
                if role is None:
                    status = "未找到"
                    role_name = "-"
                    all_passed = False
                else:
                    status = "通过"
                    role_name = _escape_markdown_table_cell(role.name)
                    passed_count += 1

            table_lines.append(
                f"| {label} | {role_id_display} | {status} | {role_name} |"
            )

        lines.append(f"通过：**{passed_count}/{len(targets)}**")
        lines.append("")
        lines.append("```md")
        lines.extend(table_lines)
        lines.append("```")

        if not all_passed:
            lines.append("")
            lines.append("校验未全部通过，已阻止创建该领取面板。")

        return all_passed, "\n".join(lines)

    @app_commands.command(
        name="create_role_pickup",
        description=locale_str(
            "Creates a message on a specific channel for role pickup.",
            key="role.create_role_pickup.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "The channel where the message will be created.",
            key="role.create_role_pickup.params.channel",
        ),
    )
    async def create_role_pickup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        all_passed, report = self._build_role_check_report(interaction.guild, "成就面板", "role")
        if not all_passed:
            await interaction.followup.send(report, ephemeral=True)
            return

        # Create the role pickup message with the AchievementRoleView as its view
        view = AchievementRoleView(self.bot)

        # Create an Embed for each type in the achievement
        embed = discord.Embed(title=self.role_pickup_title, color=discord.Color.blue())
        for role in self.role_type_name:
            achievement_info = "\n".join([f"- **{a['name']}** : `{a['threshold']}`" for a in self.achievements if
                                          a['type'] == role['type']])
            embed.add_field(name=role['name'], value=achievement_info, inline=False)

        embed.set_footer(text=self.role_pickup_footer)

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        message = await channel.send(embed=embed, view=view)

        # Save the view to the database
        await self.role_db.save_role_view(message.id, channel.id, table='role_views')

        await interaction.followup.send(
            f"{report}\n\n校验通过，已在 {channel.mention} 创建成就领取面板。",
            ephemeral=True
        )

    @app_commands.command(
        name="create_starsign_pickup",
        description=locale_str(
            "Creates a message on a specific channel for star sign pickup.",
            key="role.create_starsign_pickup.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "The channel where the message will be created.",
            key="role.create_starsign_pickup.params.channel",
        ),
    )
    async def create_starsign_pickup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        all_passed, report = self._build_role_check_report(interaction.guild, "星座面板", "starsign")
        if not all_passed:
            await interaction.followup.send(report, ephemeral=True)
            return

        # Create the role pickup message with the AchievementRoleView as its view
        view = StarSignView(self.bot)

        # Create an Embed for each type in the achievement
        embed = discord.Embed(title=self.starsign_pickup_title, color=discord.Color.purple())
        embed.add_field(name=self.starsign_fire_title, value=self.starsign_fire_description, inline=False)
        embed.add_field(name=self.starsign_earth_title, value=self.starsign_earth_description, inline=False)
        embed.add_field(name=self.starsign_air_title, value=self.starsign_air_description, inline=False)
        embed.add_field(name=self.starsign_water_title, value=self.starsign_water_description, inline=False)

        embed.set_footer(text=self.starsign_pickup_footer)

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        message = await channel.send(embed=embed, view=view)

        # Save the view to the database
        await self.role_db.save_role_view(message.id, channel.id, table='starsign_views')

        await interaction.followup.send(
            f"{report}\n\n校验通过，已在 {channel.mention} 创建星座领取面板。",
            ephemeral=True
        )

    @app_commands.command(
        name="create_mbti_pickup",
        description=locale_str(
            "Creates a message on a specific channel for MBTI pickup.",
            key="role.create_mbti_pickup.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "The channel where the message will be created.",
            key="role.create_mbti_pickup.params.channel",
        ),
    )
    async def create_mbti_pickup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        all_passed, report = self._build_role_check_report(interaction.guild, "MBTI 面板", "mbti")
        if not all_passed:
            await interaction.followup.send(report, ephemeral=True)
            return

        # Create the role pickup message with the AchievementRoleView as its view
        view = MBTIView(self.bot)

        # Create an Embed for each type in the achievement
        embed = discord.Embed(title=self.mbti_pickup_title, color=discord.Color.gold())

        embed.add_field(name=self.mbti_first_field_title, value=self.mbti_first_field_description, inline=False)
        embed.add_field(name=self.mbti_SP_title, value=self.mbti_SP_description, inline=False)
        embed.add_field(name=self.mbti_SJ_title, value=self.mbti_SJ_description, inline=False)
        embed.add_field(name=self.mbti_NF_title, value=self.mbti_NF_description, inline=False)
        embed.add_field(name=self.mbti_NT_title, value=self.mbti_NT_description, inline=False)

        embed.set_footer(text=self.mbti_pickup_footer)

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        message = await channel.send(embed=embed, view=view)

        # Save the view to the database
        await self.role_db.save_role_view(message.id, channel.id, table='mbti_views')

        await interaction.followup.send(
            f"{report}\n\n校验通过，已在 {channel.mention} 创建 MBTI 领取面板。",
            ephemeral=True
        )

    @app_commands.command(
        name="create_gender_pickup",
        description=locale_str(
            "Creates a message on a specific channel for gender pickup.",
            key="role.create_gender_pickup.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "The channel where the message will be created.",
            key="role.create_gender_pickup.params.channel",
        ),
    )
    async def create_gender_pickup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        all_passed, report = self._build_role_check_report(interaction.guild, "性别面板", "gender")
        if not all_passed:
            await interaction.followup.send(report, ephemeral=True)
            return

        view = GenderView(self.bot)

        embed = discord.Embed(title=self.gender_pickup_title, color=discord.Color.purple())
        embed.add_field(name=self.gender_tree_title, value=self.gender_tree_description, inline=False)
        embed.add_field(name=self.gender_sakura_title, value=self.gender_sakura_description, inline=False)
        embed.add_field(name=self.gender_ninja_title, value=self.gender_ninja_description, inline=False)

        embed.set_footer(text=self.gender_pickup_footer)

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        message = await channel.send(embed=embed, view=view)

        # Save the view to the database
        await self.role_db.save_role_view(message.id, channel.id, table='gender_views')

        await interaction.followup.send(
            f"{report}\n\n校验通过，已在 {channel.mention} 创建性别领取面板。",
            ephemeral=True
        )

    @app_commands.command(
        name="create_signature_pickup",
        description=locale_str(
            "Creates a message for signature settings.",
            key="role.create_signature_pickup.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "The channel where the message will be created.",
            key="role.create_signature_pickup.params.channel",
        ),
    )
    async def create_signature_pickup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        view = SignatureView(self.bot)
        embed = discord.Embed(
            title=t('role.signature.pickup_title'),
            description=t('role.signature.pickup_description'),
            color=discord.Color.brand_green()
        )
        embed.set_footer(text=t('role.signature.pickup_footer'))

        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        message = await channel.send(embed=embed, view=view)
        await self.role_db.save_role_view(message.id, channel.id, table='signature_views')
        await interaction.followup.send(f"Signature pickup message created in {channel.mention}.")

    @app_commands.command(
        name="signature_permission_toggle",
        description=locale_str(
            "Toggle a user's ability to set signature",
            key="role.signature_permission_toggle.description",
        ),
    )
    @app_commands.describe(
        user_id=locale_str(
            "The user ID to toggle",
            key="role.signature_permission_toggle.params.user_id",
        ),
        disable=locale_str(
            "True to disable, False to enable",
            key="role.signature_permission_toggle.params.disable",
        ),
    )
    async def toggle_signature(self, interaction: discord.Interaction, user_id: str, disable: bool):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        user = await self.bot.fetch_user(int(user_id))
        if not user:
            await interaction.followup.send("User not found.", ephemeral=True)
            return

        await self.role_db.toggle_signature_permission(int(user_id), disable)

        message_key = 'admin_disable_message' if disable else 'admin_enable_message'
        await interaction.followup.send(
            t(f'role.signature.{message_key}',
              user_mention=user.mention,
              user_id=user_id)
        )

    @app_commands.command(
        name="signature_clear",
        description=locale_str(
            "Clear a user's signature and change history",
            key="role.signature_clear.description",
        ),
    )
    @app_commands.describe(
        user_id=locale_str(
            "The user ID to clear signature for",
            key="role.signature_clear.params.user_id",
        ),
    )
    async def clear_signature(self, interaction: discord.Interaction, user_id: str):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        user = await self.bot.fetch_user(int(user_id))
        if not user:
            await interaction.followup.send("User not found.", ephemeral=True)
            return

        await self.role_db.clear_user_signature(int(user_id))

        await interaction.followup.send(
            t('role.signature.admin_clear_success',
              user_mention=user.mention,
              user_id=user_id)
        )


    async def load_role_views(self, table='role_views'):
        records = await self.role_db.get_all_role_views(table)

        for message_id, channel_id in records:
            channel = self.bot.get_channel(int(channel_id))
            if channel is None:
                logging.error(
                    "Channel %s from %s not found, removing from database",
                    fmt_channel(channel_id),
                    table,
                )
                await self.role_db.remove_role_view(message_id, channel_id, table=table)
                continue

            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                logging.error(
                    "Message %s from %s not found in %s, removing from database",
                    message_id,
                    table,
                    fmt_channel(channel),
                )
                await self.role_db.remove_role_view(message_id, channel_id, table=table)
                continue

            # Recreate the View and add it to the message
            if table == 'role_views':
                view = AchievementRoleView(self.bot)
            elif table == 'starsign_views':
                view = StarSignView(self.bot)
            elif table == 'mbti_views':
                view = MBTIView(self.bot)
            elif table == 'gender_views':
                view = GenderView(self.bot)
            elif table == 'signature_views':
                view = SignatureView(self.bot)

            logging.info("Recreating %s for message %s in %s", table, message_id, fmt_channel(channel))

            await message.edit(view=view)


    @app_commands.command(
        name="signature_set_requirement",
        description=locale_str(
            "Set the voice time requirement for signature feature",
            key="role.signature_set_requirement.description",
        ),
    )
    @app_commands.describe(
        minutes=locale_str(
            "Required voice time in minutes",
            key="role.signature_set_requirement.params.minutes",
        ),
    )
    async def set_signature_requirement(self, interaction: discord.Interaction, minutes: int):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        # Update the config
        self.role_config['signature']['time_requirement'] = minutes

        # Save the updated config through the unified async writer (P2-3).
        # Pre-refactor the call was `config.save_config(...)` (sync),
        # which never existed on Config and raised AttributeError silently
        # through discord.py's error handler — /signature_set_requirement
        # appeared to work but never persisted anything.
        await config.save_config('role', self.role_config)

        await interaction.followup.send(
            f"Signature requirement has been updated to {minutes} minutes of voice time.",
            ephemeral=True
        )

    @app_commands.command(
        name="signature_check",
        description=locale_str(
            "Check a user's signature information",
            key="role.signature_check.description",
        ),
    )
    @app_commands.describe(
        user_id=locale_str(
            "The user ID to check signature for",
            key="role.signature_check.params.user_id",
        ),
    )
    async def check_signature(self, interaction: discord.Interaction, user_id: str):
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer()

        user = await self.bot.fetch_user(int(user_id))
        if not user:
            await interaction.followup.send("User not found.", ephemeral=True)
            return

        signature_data = await self.role_db.get_user_signature(int(user_id))

        if not signature_data:
            await interaction.followup.send(
                t('role.signature.admin_check_no_record_message',
                  user_mention=user.mention,
                  user_id=user_id)
            )
            return

        current_time = datetime.now(timezone.utc)

        # 计算每个时间槽距今多少天 (loop var renamed from `t` to `ts`
        # to avoid shadowing the i18n helper).
        times = []
        for ts in [signature_data['change_time1'], signature_data['change_time2'], signature_data['change_time3']]:
            try:
                if ts:
                    time_obj = datetime.fromisoformat(ts)
                    days = (current_time - time_obj).days
                    times.append(t('role.signature.admin_check_time_format',
                                   timestamp=int(time_obj.timestamp()),
                                   days=days))
                else:
                    times.append(t('role.signature.admin_check_time_unused'))
            except (ValueError, TypeError):
                times.append(t('role.signature.admin_check_time_unused'))

        status = (t('role.signature.admin_check_status_disabled')
                  if signature_data['is_disabled']
                  else t('role.signature.admin_check_status_normal'))

        embed = discord.Embed(
            title=t('role.signature.admin_check_title'),
            color=discord.Color.blue() if not signature_data['is_disabled'] else discord.Color.red()
        )

        embed.add_field(
            name=t('role.signature.admin_check_user_info_title'),
            value=f"{user.mention} ({user_id})",
            inline=False
        )
        embed.add_field(
            name=t('role.signature.admin_check_status_title'),
            value=status,
            inline=False
        )
        embed.add_field(
            name=t('role.signature.admin_check_signature_title'),
            value=signature_data['signature'] or t('role.signature.admin_check_no_signature'),
            inline=False
        )
        embed.add_field(
            name=t('role.signature.admin_check_history_title'),
            value=t('role.signature.admin_check_history_format',
                    time1=times[0],
                    time2=times[1],
                    time3=times[2]),
            inline=False
        )

        await interaction.followup.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.role_db.initialize_database()

        for table in ['role_views', 'starsign_views', 'mbti_views', 'gender_views', 'signature_views']:
            await self.load_role_views(table=table)
