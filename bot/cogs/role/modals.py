import discord

from bot.utils.i18n import t
from bot.utils.role_db import RoleDatabaseManager


class SignatureModal(discord.ui.Modal):
    def __init__(self, bot, max_length):
        super().__init__(title=t('role.signature.modal_title'))
        self.bot = bot
        self.signature = discord.ui.TextInput(
            label=t('role.signature.modal_label'),
            placeholder=t('role.signature.modal_placeholder'),
            max_length=max_length,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.signature)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        role_db = RoleDatabaseManager(self.bot.get_cog('RoleCog').main_config['db_path'])

        # Check if user is disabled
        signature_data = await role_db.get_user_signature(interaction.user.id)
        if signature_data and signature_data['is_disabled']:
            await interaction.followup.send(t('role.signature.disabled_message'), ephemeral=True)
            return

        # Find available time slot
        available_slot = await role_db.find_available_time_slot(interaction.user.id)
        if available_slot is None:
            # Cannot change signature yet
            current_sig = signature_data['signature'] if signature_data else "无"
            await interaction.followup.send(
                t('role.signature.cooldown_message', signature=current_sig),
                ephemeral=True
            )
            return

        # Update signature
        if await role_db.update_user_signature(interaction.user.id, str(self.signature), available_slot):
            # Calculate remaining changes
            remaining_times = await role_db.get_signature_remaining_changes(interaction.user.id)

            await interaction.followup.send(
                t('role.signature.success_message',
                  signature=str(self.signature),
                  remaining_times=remaining_times),
                ephemeral=True
            )
        else:
            await interaction.followup.send(t('role.signature.update_failed_message'), ephemeral=True)


