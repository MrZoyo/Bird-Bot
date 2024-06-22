# Author: MrZoyo
# Version: 0.6.7
# Date: 2024-06-17
# ========================================
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
import aiosqlite
from datetime import datetime
from illegal_team_act_cog import IllegalTeamActCog


class ConfirmationView(View):
    def __init__(self, bot, user_id, event_object, event_serial_number, event_description=None):
        super().__init__(timeout=300.0)
        self.bot = bot
        self.user_id = user_id
        self.event_object = event_object
        self.event_serial_number = event_serial_number
        self.event_description = event_description

        self.confirm_button = Button(style=discord.ButtonStyle.green, label="Confirm")
        self.cancel_button = Button(style=discord.ButtonStyle.red, label="Cancel")

        self.confirm_button.callback = self.confirm
        self.cancel_button.callback = self.cancel

        self.add_item(self.confirm_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def confirm(self, interaction: discord.Interaction):
        cog = self.bot.get_cog('NotebookCog')
        if self.event_description is not None:
            await cog.add_event_to_db(self.user_id, self.event_object, self.event_description)
        else:
            await cog.delete_event_from_db(self.event_object, self.event_serial_number)
        self.remove_item(self.confirm_button)
        self.remove_item(self.cancel_button)

        if self.event_description is not None:
            await interaction.message.edit(content="Event logged.", view=self)
        else:
            await interaction.message.edit(content="Event deleted.", view=self)

    async def cancel(self, interaction: discord.Interaction):
        self.remove_item(self.confirm_button)
        self.remove_item(self.cancel_button)
        await interaction.message.edit(content="Cancelled.", view=self)


class EventPaginationView(View):
    def __init__(self, bot, records, user_id, format_page_method):
        super().__init__(timeout=300.0)
        self.bot = bot
        self.records = records
        self.user_id = user_id
        self.page = 0
        self.total_pages = (len(records) - 1) // 5 + 1
        self.total_records = len(records)
        self.message = None
        self.format_page_method = format_page_method

        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.blurple, disabled=True)
        self.next_button = Button(label="Next", style=discord.ButtonStyle.green, disabled=len(records) <= 5)
        self.previous_button.callback = self.previous_button_callback
        self.next_button.callback = self.next_button_callback
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.item_each_page = 5

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def update_buttons(self):
        self.previous_button.disabled = self.page == 0
        self.next_button.disabled = (self.page + 1) * self.item_each_page >= len(self.records)
        if self.message:
            await self.message.edit(view=self)

    async def previous_button_callback(self, interaction: discord.Interaction):
        self.page -= 1
        await self.update_buttons()
        await interaction.response.edit_message(embed=self.format_page_method(self), view=self)

    async def next_button_callback(self, interaction: discord.Interaction):
        self.page += 1
        await self.update_buttons()
        await interaction.response.edit_message(embed=self.format_page_method(self), view=self)

    def format_page_check_member_event(self):
        start = self.page * self.item_each_page
        end = min(start + self.item_each_page, self.total_records)
        page_entries = self.records[start:end]

        embed = discord.Embed(
            title=f"Logs for {self.bot.get_user(int(page_entries[0][2])).display_name if self.bot.get_user(int(page_entries[0][2])) else f'User ID: {page_entries[0][2]}'}",
            color=discord.Color.blue())

        records_str = ""
        for record in page_entries:
            record_str = (f"**Log Number:** {record[4]} \n"
                          f"**Add Time:** {record[0]} \n"
                          f"**Operator:** {self.bot.get_user(int(record[1])).mention if self.bot.get_user(int(record[1])) else f'User ID: {record[1]}'}\n"
                          f"**Event Description:** \n {record[3]}\n"
                          f"{'-' * 20}\n")

            # If adding the next record will exceed the limit,
            # add the current records_str as a field and start a new one
            if len(records_str) + len(record_str) > 1024:
                embed.add_field(name="Records", value=records_str, inline=False)
                records_str = record_str
            else:
                records_str += record_str

        # Add any remaining records
        if records_str:
            embed.add_field(name="Records", value=records_str, inline=False)

        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} - Total Logs: {self.total_records}")
        return embed

    def format_page_check_all_event(self):
        start = self.page * self.item_each_page
        end = min(start + self.item_each_page, self.total_records)
        page_entries = self.records[start:end]

        description = "\n".join([
            f"**Last Event Time::** {record[0]} \n"
            f"**Logged Member:** {self.bot.get_user(int(record[1])).mention if self.bot.get_user(int(record[1])) else f'User ID: {record[1]}'}\n"
            f"**Logged Times:** {record[2]}\n"
            f"{'-' * 20}"
            for record in page_entries
        ])

        embed = discord.Embed(title="All Logged Events",
                              description=description,
                              color=discord.Color.blue())
        embed.set_footer(text=f"Page {self.page + 1}/{self.total_pages} - Total Logs: {self.total_records}")
        return embed


class NotebookCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.illegal_act_cog = IllegalTeamActCog(bot)

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']

    @app_commands.command(name="log_event")
    @app_commands.describe(event_object="The member to log",
                           event_description="The description of the event"
                           )
    async def log_event(self, interaction: discord.Interaction, event_object: discord.Member, event_description: str):
        await interaction.response.defer()

        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        view = ConfirmationView(self.bot, interaction.user.id, event_object.id, 0, event_description)
        embed = discord.Embed(title="Log Event",
                              description=f"You will log an event.",
                              color=discord.Color.blue())
        embed.add_field(name="Event Object", value=event_object.mention, inline=False)
        embed.add_field(name="Event Description", value=event_description, inline=False)
        await interaction.edit_original_response(embed=embed, view=view)

    async def add_event_to_db(self, user_id, event_object, event_description):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            add_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')  # Using microseconds

            # Fetch the maximum count for the given event_member
            await cursor.execute('SELECT MAX(count) FROM event_logs WHERE event_member = ?', (event_object,))
            max_count = await cursor.fetchone()
            if max_count[0] is None:
                # If there are no records for the event_member, set the count to 1
                count = 1
            else:
                # If there are records, increment the maximum count by 1
                count = max_count[0] + 1

            # Insert a new record with the calculated count
            await cursor.execute(
                'INSERT INTO event_logs (add_time, operator, event_member, event_description, count) VALUES (?, ?, ?, ?, ?)',
                (add_time, user_id, event_object, event_description, count))

            # Check if the user is already in the admins table
            await cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
            if await cursor.fetchone() is None:
                # If the user is not in the admins table, insert them
                await cursor.execute('INSERT INTO admins (user_id) VALUES (?)', (user_id,))

            await db.commit()
            await cursor.close()

    @app_commands.command(name="check_member_event")
    @app_commands.describe(member="The member to fetch event logs for")
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
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT * FROM admins WHERE user_id = ?', (user_id,))
            admin = await cursor.fetchone()
            await cursor.close()
            return admin is not None

    async def fetch_events_for_user(self, event_member):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'SELECT add_time, operator, event_member, event_description, count FROM event_logs WHERE event_member = ?',
                (event_member,))
            records = await cursor.fetchall()
            await cursor.close()
            return records

    @app_commands.command(name="check_all_event")
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
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'SELECT MAX(add_time), event_member, COUNT(event_member) FROM event_logs GROUP BY event_member')
            records = await cursor.fetchall()
            await cursor.close()
            return records

    @app_commands.command(name="delete_event")
    @app_commands.describe(member="The member whose event is to be deleted",
                           event_serial_number="The serial number of the event to be deleted"
                           )
    async def delete_event(self, interaction: discord.Interaction, member: discord.Member, event_serial_number: int):
        """Deletes an event log for the specified member."""
        await interaction.response.defer()
        try:
            # Check if the command is used in the specific channel
            if not await self.illegal_act_cog.check_channel_validity(interaction):
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
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'SELECT add_time, operator, event_member, event_description FROM event_logs WHERE event_member = ? AND count = ?',
                (event_member, event_serial_number))
            record = await cursor.fetchone()
            await cursor.close()
            return record

    async def delete_event_from_db(self, event_member, event_serial_number):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'DELETE FROM event_logs WHERE event_member = ? AND count = ?',
                (event_member, event_serial_number))
            await db.commit()
            await cursor.close()

    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure the table exists
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS event_logs (
                    add_time TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    event_member TEXT NOT NULL,
                    event_description TEXT NOT NULL,
                    count INTEGER DEFAULT 1
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id TEXT NOT NULL
                )
            ''')
            await db.commit()
