import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from bot.utils import NotebookDatabaseManager, check_channel_validity, config

from .views import ConfirmationView, EventPaginationView


class NotebookCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.conf = config.get_config()
        self.db_path = self.conf['db_path']
        self.db = NotebookDatabaseManager(self.db_path)

    async def cog_load(self):
        await self.db.initialize_database()

    @app_commands.command(
        name="notebook_log",
        description=locale_str(
            "Log an event for a specific member",
            key="notebook.notebook_log.description",
        ),
    )
    @app_commands.describe(
        event_object=locale_str(
            "The member to log",
            key="notebook.notebook_log.params.event_object",
        ),
        event_description=locale_str(
            "The description of the event",
            key="notebook.notebook_log.params.event_description",
        ),
    )
    async def log_event(self, interaction: discord.Interaction, event_object: discord.Member, event_description: str):
        await interaction.response.defer()

        if not await check_channel_validity(interaction):
            return

        view = ConfirmationView(self.bot, interaction.user.id, event_object.id, 0, event_description)
        embed = discord.Embed(title="Log Event",
                              description=f"You will log an event.",
                              color=discord.Color.blue())
        embed.add_field(name="Event Object", value=event_object.mention, inline=False)
        embed.add_field(name="Event Description", value=event_description, inline=False)
        await interaction.edit_original_response(embed=embed, view=view)

    async def add_event_to_db(self, user_id, event_object, event_description):
        await self.db.insert_event_and_ensure_admin(user_id, event_object, event_description)

    @app_commands.command(
        name="notebook_member",
        description=locale_str(
            "List all event logs for a specific member",
            key="notebook.notebook_member.description",
        ),
    )
    @app_commands.describe(
        member=locale_str(
            "The member to fetch event logs for",
            key="notebook.notebook_member.params.member",
        ),
    )
    async def check_member_event(self, interaction: discord.Interaction, member: discord.Member):
        """Lists all event logs for the specified member."""
        await interaction.response.defer()
        try:
            # Check if the user is in the admins table
            if not await self.is_user_admin(interaction.user.id):
                await interaction.followup.send("Only Admin can use this command.", ephemeral=True)
                return

            records = await self.fetch_events_for_user(member.id)
            if not records:
                await interaction.followup.send("No logs found for this user.", ephemeral=True)
                return
            view = EventPaginationView(self.bot, records, interaction.user.id,
                                       EventPaginationView.format_page_check_member_event)
            message = await interaction.followup.send(content=f"Logs for <@{member.id}>",
                                                      embed=view.format_page_check_member_event(),
                                                      view=view)
            view.message = message
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    async def is_user_admin(self, user_id):
        return await self.db.is_admin(user_id)

    async def fetch_events_for_user(self, event_member):
        return await self.db.fetch_events_for_member(event_member)

    @app_commands.command(
        name="notebook_all",
        description=locale_str(
            "List event logs for all members",
            key="notebook.notebook_all.description",
        ),
    )
    async def check_all_event(self, interaction: discord.Interaction):
        """Lists all event logs."""
        await interaction.response.defer()
        try:
            # Check if the user is in the admins table
            if not await self.is_user_admin(interaction.user.id):
                await interaction.followup.send("Only Admin can use this command.", ephemeral=True)
                return

            records = await self.fetch_all_events()
            if not records:
                await interaction.followup.send("No logs found.", ephemeral=True)
                return
            view = EventPaginationView(self.bot, records, interaction.user.id,
                                       EventPaginationView.format_page_check_all_event)
            message = await interaction.followup.send(content=f"All Logs",
                                                      embed=view.format_page_check_all_event(),
                                                      view=view)
            view.message = message
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    async def fetch_all_events(self):
        return await self.db.fetch_event_summary_all()

    @app_commands.command(
        name="notebook_delete",
        description=locale_str(
            "Delete a specific event from a member's log",
            key="notebook.notebook_delete.description",
        ),
    )
    @app_commands.describe(
        member=locale_str(
            "The member whose event is to be deleted",
            key="notebook.notebook_delete.params.member",
        ),
        event_serial_number=locale_str(
            "The serial number of the event to be deleted",
            key="notebook.notebook_delete.params.event_serial_number",
        ),
    )
    async def delete_event(self, interaction: discord.Interaction, member: discord.Member, event_serial_number: int):
        """Deletes an event log for the specified member."""
        await interaction.response.defer()
        try:
            # Check if the command is used in the specific channel
            if not await check_channel_validity(interaction):
                return

            # Fetch the event details from the database
            event_details = await self.fetch_event_details(member.id, event_serial_number)
            if not event_details:
                await interaction.followup.send("No event found with the provided details.", ephemeral=True)
                return

            # Create an embed and add the event details to it
            embed = discord.Embed(title=f"Event {event_serial_number} for {member.display_name}",
                                  description=f"**Add Time:** {event_details[0]}\n"
                                              f"**Operator:** {self.bot.get_user(int(event_details[1])).mention if self.bot.get_user(int(event_details[1])) else f'User ID: {event_details[1]}'}\n"
                                              f"**Logged Member:**{member.mention}\n"
                                              f"**Event Description:**\n {event_details[3]}",
                                  color=discord.Color.red())

            view = ConfirmationView(self.bot, interaction.user.id, member.id, event_serial_number)
            await interaction.edit_original_response(content=f"Are you sure you want to delete this event?",
                                                     embed=embed, view=view)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    async def fetch_event_details(self, event_member, event_serial_number):
        return await self.db.fetch_event_details(event_member, event_serial_number)

    async def delete_event_from_db(self, event_member, event_serial_number):
        await self.db.delete_event(event_member, event_serial_number)
