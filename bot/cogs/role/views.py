import logging

import discord
from discord import components
from discord.ui import Button, View

from bot.utils import config, safe_member_role_edit
from bot.utils.i18n import t
from bot.utils.role_db import RoleDatabaseManager

from .modals import SignatureModal


async def ensure_optional_role(member: discord.Member, role_id: int | None, reason: str) -> None:
    """Add an optional starter role when configured and present in the guild.

    Silently swallows discord.Forbidden (role hierarchy issue) so the
    caller's primary action isn't blocked by a starter-role side effect;
    failure is still logged for diagnostics.
    """
    if not role_id:
        return

    if discord.utils.get(member.roles, id=role_id) is not None:
        return

    role = discord.utils.get(member.guild.roles, id=role_id)
    if role is None:
        logging.warning("Configured starter role %s not found in guild %s", role_id, member.guild.id)
        return

    try:
        await member.add_roles(role, reason=reason)
    except discord.Forbidden:
        logging.error(
            "Cannot add starter role %r (pos=%d) to %s (%s); bot top_role=%r (pos=%d). "
            "Check role hierarchy.",
            role.name, role.position, member.id, member.display_name,
            member.guild.me.top_role.name, member.guild.me.top_role.position,
        )
    except discord.HTTPException as exc:
        logging.error(
            "HTTPException adding starter role %r to %s (%s): %s",
            role.name, member.id, member.display_name, exc,
        )


class AchievementRoleView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # No interaction time limit
        self.bot = bot

        self.main_config = config.get_config('main')
        self.role_db = RoleDatabaseManager(self.main_config['db_path'])

        self.achievement_config = config.get_config('achievements')

        self.role_config = config.get_config('role')
        self.achievements = self.achievement_config['achievements']
        self.role_type_name = self.role_config['role_type_name']
        self.achievement_start_role_id = self.role_config['achievement_start_role_id']
        self.role_no_column_name_message = t('role.role_no_column_name_message')
        self.role_no_progress_message = t('role.role_no_progress_message')
        self.role_no_achievement_message = t('role.role_no_achievement_message')
        self.role_success_message = t('role.role_success_message')
        self.role_remove_message = t('role.role_remove_message')

        for index, role in enumerate(self.role_type_name):
            row = index // 3  # Calculate row: 0, 1, 2 go to row 0; 3, 4, 5 go to row 1
            button = Button(style=components.ButtonStyle.green,
                            label=role['name'],
                            custom_id=role['type'],
                            row=row)
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        # Defer the interaction to avoid timeouts
        await interaction.response.defer()
        # Get the type from the button's custom_id
        achievement_type = interaction.data['custom_id']

        # Get the user's id
        user_id = interaction.user.id

        await ensure_optional_role(
            interaction.user,
            self.achievement_start_role_id,
            "Adding achievement start role"
        )

        # Get the user's progress for the achievement type
        user_progress = await self.role_db.get_user_achievement_progress(user_id, achievement_type)
        
        # If the user has no progress for this achievement type, do nothing
        if user_progress is None:
            await interaction.followup.send(self.role_no_progress_message, ephemeral=True)
            return

        # Filter the achievements to only include those of the same type
        same_type_achievements = [a for a in self.achievements if a['type'] == achievement_type]
        # Sort achievements by threshold in descending order
        same_type_achievements.sort(key=lambda x: x['threshold'], reverse=True)

        # Find the highest achievement the user is eligible for
        highest_eligible_achievement = next(
            (a for a in same_type_achievements if user_progress >= a['threshold']), None)

        if highest_eligible_achievement is None:
            await interaction.followup.send(self.role_no_achievement_message, ephemeral=True)
            return

        # Get the role for the highest eligible achievement
        highest_eligible_role = discord.utils.get(interaction.guild.roles, id=highest_eligible_achievement['role_id'])

        # Get the user's current achievement role for this type, if any
        current_achievement_role = None
        for achievement in same_type_achievements:
            role = discord.utils.get(interaction.user.roles, id=achievement['role_id'])
            if role:
                current_achievement_role = role
                break

        # If user has their highest eligible role, they can remove it
        if current_achievement_role and current_achievement_role.id == highest_eligible_role.id:
            # Remove all achievement roles of this type
            achievement_roles = [discord.utils.get(interaction.guild.roles, id=a['role_id']) for a in
                                 same_type_achievements]
            if not await safe_member_role_edit(
                interaction,
                remove=achievement_roles,
                reason="Removing achievement roles",
                context="achievement",
            ):
                return
            await interaction.followup.send(
                self.role_remove_message.format(name=current_achievement_role.name),
                ephemeral=True
            )
            logging.info(f"User {user_id} has removed their {current_achievement_role.name} role")
            return

        # If user has a role lower than their highest eligible role
        if current_achievement_role:
            # Remove the current role and give them their highest eligible role
            other_roles = [discord.utils.get(interaction.guild.roles, id=a['role_id']) for a in same_type_achievements]
            if not await safe_member_role_edit(
                interaction,
                remove=other_roles,
                add=[highest_eligible_role],
                reason="Upgrading achievement role",
                context="achievement",
            ):
                return
            await interaction.followup.send(
                self.role_success_message.format(name=highest_eligible_role.name),
                ephemeral=True
            )
            logging.info(
                f"User {user_id} upgraded from {current_achievement_role.name} to {highest_eligible_role.name}")
            return

        # If user has no role yet, give them their highest eligible role
        if not await safe_member_role_edit(
            interaction,
            add=[highest_eligible_role],
            reason="Adding achievement role",
            context="achievement",
        ):
            return
        await interaction.followup.send(
            self.role_success_message.format(name=highest_eligible_role.name),
            ephemeral=True
        )
        logging.info(f"User {user_id} has been awarded the {highest_eligible_role.name} role")


class StarSignView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # No interaction time limit
        self.bot = bot
        self.buttons_per_row = 4

        self.main_config = config.get_config('main')
        self.role_db = RoleDatabaseManager(self.main_config['db_path'])

        self.role_config = config.get_config('role')
        self.starsign_name = self.role_config['starsign_name']
        self.social_start_role_id = self.role_config['social_start_role_id']
        self.starsign_success_message = t('role.starsign_success_message')
        self.starsign_remove_message = t('role.starsign_remove_message')

        for index, star_sign in enumerate(self.starsign_name):
            row = index % self.buttons_per_row  # Calculate the row for the button
            button = Button(style=components.ButtonStyle.primary,
                            label=star_sign['emoji'],
                            custom_id=star_sign['name'],
                            row=row)
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        await interaction.response.defer()

        star_sign_name = interaction.data['custom_id']

        # Get the role for the clicked star sign
        star_sign_role_id = next(
            (star_sign['role_id'] for star_sign in self.starsign_name if star_sign['name'] == star_sign_name), None)
        star_sign_role = discord.utils.get(interaction.guild.roles, id=star_sign_role_id)

        # Check if user already has this role
        if star_sign_role in interaction.user.roles:
            # Remove the role and send removal message
            if not await safe_member_role_edit(
                interaction,
                remove=[star_sign_role],
                reason="User removed star sign role",
                context="starsign",
            ):
                return
            await interaction.followup.send(self.starsign_remove_message.format(name=star_sign_role.name),
                                            ephemeral=True)
            logging.info(f"User {interaction.user.id} has removed the {star_sign_role.name} role")
            return

        await ensure_optional_role(
            interaction.user,
            self.social_start_role_id,
            "Adding social start role"
        )

        # Remove other star sign roles from the user + add the new one
        other_roles = [discord.utils.get(interaction.guild.roles, id=star_sign['role_id']) for star_sign in
                       self.starsign_name if star_sign['name'] != star_sign_name]
        if not await safe_member_role_edit(
            interaction,
            remove=other_roles,
            add=[star_sign_role],
            reason="Switching star sign role",
            context="starsign",
        ):
            return

        # Notify the user after successfully adding the role
        await interaction.followup.send(self.starsign_success_message.format(name=star_sign_role.name), ephemeral=True)
        logging.info(f"User {interaction.user.id} has been awarded the {star_sign_role.name} role")


class MBTIView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.buttons_per_row = 4

        self.main_config = config.get_config('main')
        self.role_db = RoleDatabaseManager(self.main_config['db_path'])

        self.role_config = config.get_config('role')
        self.mbti_name = self.role_config['mbti_name']
        self.social_start_role_id = self.role_config['social_start_role_id']
        self.mbti_success_message = t('role.mbti_success_message')
        self.mbti_remove_message = t('role.mbti_remove_message')

        for index, mbti in enumerate(self.mbti_name):
            row = index % self.buttons_per_row
            button = Button(style=components.ButtonStyle.primary,
                            label=mbti['name'],
                            custom_id=mbti['name'],
                            row=row)
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        await interaction.response.defer()

        mbti_name = interaction.data['custom_id']

        # Get the role for the clicked MBTI type
        mbti_role_id = next(
            (mbti['role_id'] for mbti in self.mbti_name if mbti['name'] == mbti_name), None)
        mbti_role = discord.utils.get(interaction.guild.roles, id=mbti_role_id)

        # Check if user already has this role
        if mbti_role in interaction.user.roles:
            # Remove the role and send removal message
            if not await safe_member_role_edit(
                interaction,
                remove=[mbti_role],
                reason="User removed MBTI role",
                context="mbti",
            ):
                return
            await interaction.followup.send(self.mbti_remove_message.format(name=mbti_role.name), ephemeral=True)
            logging.info(f"User {interaction.user.id} has removed the {mbti_role.name} role")
            return

        await ensure_optional_role(
            interaction.user,
            self.social_start_role_id,
            "Adding social start role"
        )

        # Remove other MBTI roles from the user + add the new one
        other_roles = [discord.utils.get(interaction.guild.roles, id=mbti['role_id']) for mbti in
                       self.mbti_name if mbti['name'] != mbti_name]
        if not await safe_member_role_edit(
            interaction,
            remove=other_roles,
            add=[mbti_role],
            reason="Switching MBTI role",
            context="mbti",
        ):
            return

        await interaction.followup.send(self.mbti_success_message.format(name=mbti_role.name), ephemeral=True)
        logging.info(f"User {interaction.user.id} has been awarded the {mbti_role.name} role")


class GenderView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.buttons_per_row = 3  # Since we have 3 options

        self.main_config = config.get_config('main')
        self.role_db = RoleDatabaseManager(self.main_config['db_path'])

        self.role_config = config.get_config('role')
        self.gender_name = self.role_config['gender_name']
        self.gender_success_message = t('role.gender_success_message')
        self.gender_remove_message = t('role.gender_remove_message')

        for index, gender in enumerate(self.gender_name):
            button = Button(
                style=components.ButtonStyle.primary,
                label=gender['emoji'],
                custom_id=gender['name'],
                row=0  # All buttons in one row since we only have 3
            )
            button.callback = self.on_button_click
            self.add_item(button)

    async def on_button_click(self, interaction: discord.Interaction):
        await interaction.response.defer()

        gender_name = interaction.data['custom_id']

        # Get the role for the clicked gender
        gender_role_id = next(
            (gender['role_id'] for gender in self.gender_name if gender['name'] == gender_name), None)
        gender_role = discord.utils.get(interaction.guild.roles, id=gender_role_id)

        # Check if user already has this role
        if gender_role in interaction.user.roles:
            # Remove the role and send removal message
            if not await safe_member_role_edit(
                interaction,
                remove=[gender_role],
                reason="User removed gender role",
                context="gender",
            ):
                return
            await interaction.followup.send(self.gender_remove_message.format(name=gender_role.name), ephemeral=True)
            logging.info(f"User {interaction.user.id} has removed the {gender_role.name} role")
            return

        # Remove other gender roles from the user + add the new one
        other_roles = [discord.utils.get(interaction.guild.roles, id=gender['role_id']) for gender in
                       self.gender_name if gender['name'] != gender_name]
        if not await safe_member_role_edit(
            interaction,
            remove=other_roles,
            add=[gender_role],
            reason="Switching gender role",
            context="gender",
        ):
            return

        # Notify the user after successfully adding the role
        await interaction.followup.send(self.gender_success_message.format(name=gender_role.name), ephemeral=True)
        logging.info(f"User {interaction.user.id} has been awarded the {gender_role.name} role")




class SignatureView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

        # 设置签名按钮
        set_button = Button(
            style=components.ButtonStyle.primary,
            label=t('role.signature.button_label'),
            custom_id="signature_button",
            row=0
        )
        set_button.callback = self.on_button_click
        self.add_item(set_button)

        # 查看签名按钮
        view_button = Button(
            style=components.ButtonStyle.secondary,
            label=t('role.signature.view_button_label'),
            custom_id="view_signature_button",
            row=0
        )
        view_button.callback = self.on_view_button_click
        self.add_item(view_button)

    async def check_voice_time_requirement(self, user_id):
        sig_cfg = self.bot.get_cog('RoleCog').role_config['signature']
        required_time = sig_cfg['time_requirement']
        helper_role_id = sig_cfg['helper_role_id']

        # 检查是否是服务器助力成员
        for guild in self.bot.guilds:
            member = guild.get_member(user_id)
            if member and any(role.id == helper_role_id for role in member.roles):
                return True, 0  # 如果是助力成员，直接返回True

        # 如果不是助力成员，检查语音时长
        role_db = RoleDatabaseManager(self.bot.get_cog('RoleCog').main_config['db_path'])
        return await role_db.check_voice_time_requirement(user_id, required_time)

    async def on_button_click(self, interaction: discord.Interaction):
        sig_cfg = self.bot.get_cog('RoleCog').role_config['signature']

        # Check voice time requirement
        meets_requirement, current_time = await self.check_voice_time_requirement(interaction.user.id)
        if not meets_requirement:
            await interaction.response.send_message(
                t('role.signature.no_permission_message',
                  required_time=sig_cfg['time_requirement'],
                  current_time=int(current_time)),
                ephemeral=True
            )
            return

        modal = SignatureModal(self.bot, sig_cfg['max_length'])
        await interaction.response.send_modal(modal)

    async def on_view_button_click(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        sig_cfg = self.bot.get_cog('RoleCog').role_config['signature']

        # Check voice time requirement
        meets_requirement, current_time = await self.check_voice_time_requirement(interaction.user.id)
        if not meets_requirement:
            await interaction.followup.send(
                t('role.signature.no_permission_message',
                  required_time=sig_cfg['time_requirement'],
                  current_time=int(current_time)),
                ephemeral=True
            )
            return

        role_db = RoleDatabaseManager(self.bot.get_cog('RoleCog').main_config['db_path'])
        signature_data = await role_db.get_user_signature(interaction.user.id)

        if not signature_data:
            await interaction.followup.send(t('role.signature.no_signature_message'), ephemeral=True)
            return

        if signature_data['is_disabled']:
            await interaction.followup.send(t('role.signature.disabled_message'), ephemeral=True)
            return

        if not signature_data['signature']:
            await interaction.followup.send(t('role.signature.no_signature_message'), ephemeral=True)
            return

        await interaction.followup.send(
            t('role.signature.view_message', signature=signature_data['signature']),
            ephemeral=True
        )


