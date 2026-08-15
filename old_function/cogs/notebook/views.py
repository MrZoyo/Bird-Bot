import discord
from discord.ui import Button, View


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
        self.item_each_page = 5
        self.total_pages = (len(records) - 1) // self.item_each_page + 1
        self.total_records = len(records)
        self.message = None
        self.format_page_method = format_page_method

        self.previous_button = Button(label="Previous", style=discord.ButtonStyle.blurple, disabled=True)
        self.next_button = Button(label="Next", style=discord.ButtonStyle.green, disabled=len(records) <= self.item_each_page)
        self.previous_button.callback = self.previous_button_callback
        self.next_button.callback = self.next_button_callback
        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def update_buttons(self):
        self.previous_button.disabled = self.page == 0
        self.next_button.disabled = (self.page + 1) * self.item_each_page >= len(self.records)
        if self.message:
            await self.message.edit(view=self)

    async def previous_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page -= 1
        await self.update_buttons()
        await interaction.edit_original_response(embed=self.format_page_method(self), view=self)

    async def next_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page += 1
        await self.update_buttons()
        await interaction.edit_original_response(embed=self.format_page_method(self), view=self)

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
