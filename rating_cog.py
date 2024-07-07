# Author: MrZoyo
# Version: 0.7.8
# Date: 2024-07-06
# ========================================
import discord
from discord import app_commands, ui, components, Interaction
from discord.ext import commands, tasks
from discord.ui import Button, View, Select
import random
import string
import aiosqlite
import re
import tempfile
import logging
import matplotlib.pyplot as plt
import io

from illegal_team_act_cog import IllegalTeamActCog


class RatingConfirmationView(ui.View):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']

    def create_embed(self, rating_id, description):
        # Create the embed
        embed = discord.Embed(title='Rating', color=discord.Color.blue())

        embed.add_field(name="Description", value=description, inline=False)
        embed.add_field(name="Rating count", value="NaN", inline=False)

        embed.set_footer(text=f"Rating ID: {rating_id}")

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        return embed


class RatingOptionsView(ui.View):
    def __init__(self, bot, rating_id, user_id):
        super().__init__()
        self.bot = bot
        self.rating_id = rating_id
        self.user_id = user_id

        number_to_emoji = {
            1: "1️⃣",
            2: "2️⃣",
            3: "3️⃣",
            4: "4️⃣",
            5: "5️⃣",
            6: "6️⃣",
            7: "7️⃣",
            8: "8️⃣",
            9: "9️⃣",
            10: "🔟"
        }

        # Create a list of options for the select menu
        options = [
            discord.SelectOption(
                label=f"Point:{i}",
                value=str(i),
                emoji=number_to_emoji[i],
                description=f"You rate {i} Point"
            ) for i in range(1, 11)
        ]

        # Debugging: Print or log the options list
        # print(f"Options: {options}")

        # Add the select component to the view
        select = ui.Select(
            placeholder='Choose your rating...',
            min_values=1,
            max_values=1,
            options=options,
            custom_id='rating_select'
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        # Convert the selected option value to an integer
        score = int(interaction.data['values'][0])
        # Proceed with updating the rating
        await self.bot.get_cog('RatingCog').update_rating(interaction, score, self.rating_id)
        await interaction.delete_original_response()


class RatingView(ui.View):
    def __init__(self, bot, rating_id, rating_channel_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.rating_id = rating_id
        self.rating_channel_id = int(rating_channel_id)
        self.message_id = None

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']

        # buttons definition
        self.participate_button = Button(label="Rate",
                                         style=components.ButtonStyle.primary,
                                         custom_id=f"rate_{str(self.rating_id)}")

        self.participate_button.callback = self.participate

        self.add_item(self.participate_button)

    def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

    def to_dict(self):
        return {
            'rating_id': self.rating_id,
            'rating_channel_id': self.rating_channel_id,
            'message_id': self.message_id,
        }

    async def participate(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            # The interaction has already been responded to
            return

        # Show a selection of 10 options on a scale of 1 to 10
        await interaction.response.send_message(
            "Please select your rating:",
            view=RatingOptionsView(self.bot, self.rating_id, interaction.user.id),
            ephemeral=True
        )


class RatingForm(ui.Modal, title='Create Rating'):
    description = ui.TextInput(label='Description', placeholder='Enter the description here...', required=True,
                               max_length=500)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.result = None

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']
        self.rating_channel_id = config['rating_channel_id']

    async def on_submit(self, interaction: discord.Interaction):
        # Generate a rating id
        rating_id = await self.generate_rating_id()

        # Create the rating confirmation view
        rating_confirmation_view = RatingConfirmationView(self.bot)
        embed = rating_confirmation_view.create_embed(
            rating_id=rating_id,
            description=self.description.value
        )
        await interaction.response.send_message(content=f"Successfully created the rating {rating_id}!",
                                                embed=embed,
                                                ephemeral=False)

        rating_view = RatingView(self.bot, rating_id, self.rating_channel_id)
        rating_channel = self.bot.get_channel(self.rating_channel_id)
        message = await rating_channel.send(embed=embed, view=rating_view)

        # Insert the rating into the database
        await self.insert_rating(
            rating_id,
            message.id,
            self.description.value,
            interaction.user.id,
        )

        # Store the message id in the view
        rating_view.message_id = message.id
        # Store the RatingView instance in the RatingCog
        self.bot.get_cog('RatingCog').ratings[rating_id] = rating_view
        # Save the state of the RatingView instance
        await self.bot.get_cog('RatingCog').save_rating(rating_id, rating_view)

    async def generate_rating_id(self):
        # fetch all rating ids
        existing_rating_ids = await self.fetch_all_rating_ids()

        # Generate an unique rating id
        while True:
            rating_id = ''.join(random.choices(string.digits, k=10))
            if rating_id not in existing_rating_ids:
                return rating_id

    async def fetch_rating(self, rating_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT * FROM rating WHERE rating_id = ?', (rating_id,))
            record = await cursor.fetchone()
            await cursor.close()
            return record

    async def fetch_all_rating_ids(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT rating_id FROM rating')
            rows = await cursor.fetchall()
            await cursor.close()
            return [row[0] for row in rows]

    async def insert_rating(self, rating_id, message_id, description, creator_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO rating (rating_id, message_id, description, creator_id)
                VALUES (?, ?, ?, ?)
            ''', (rating_id, message_id, description, creator_id))
            await db.commit()


def parse_person_with_point(data_str):
    # Matches patterns like (123456:1)
    pattern = re.compile(r'\((\d+):(\d+)\)')
    return {int(match.group(1)): int(match.group(2)) for match in pattern.finditer(data_str)}


def dict_to_person_with_point(data_dict):
    return ','.join(f'({user_id}:{score})' for user_id, score in data_dict.items())


class RatingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ratings = {}
        self.illegal_act_cog = IllegalTeamActCog(bot)

        self.config = self.bot.get_cog('ConfigCog').config
        self.db_path = self.config['db_path']
        self.rating_channel_id = self.config['rating_channel_id']

    async def count_participants(self, rating_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT person_with_point FROM rating WHERE rating_id = ?', (rating_id,))
            record = await cursor.fetchone()
            if record and record[0]:
                person_with_point = parse_person_with_point(record[0])
                return len(person_with_point)
            return 0

    async def update_rating_embed(self, rating_id, channel_id, message_id):
        count = await self.count_participants(rating_id)
        channel = self.bot.get_channel(channel_id)
        if channel:
            try:
                message = await channel.fetch_message(message_id)
                embed = message.embeds[0]  # Assuming there's at least one embed
                # Find and update the "Rating count" field
                for i, field in enumerate(embed.fields):
                    if field.name == "Rating count":
                        embed.set_field_at(i, name="Rating count", value=str(count), inline=False)
                        break
                else:
                    # If the "Rating count" field doesn't exist, add it
                    embed.add_field(name="Rating count", value=str(count), inline=False)
                await message.edit(embed=embed)
            except Exception as e:
                logging.error(f"Failed to update rating embed: {e}")
        else:
            logging.error(f"Rating Channel {channel_id} not found")

    async def update_rating(self, interaction: discord.Interaction, score, rating_id):
        user_id = interaction.user.id

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Check if the rating has ended
            await cursor.execute('SELECT is_end FROM rating WHERE rating_id = ?', (rating_id,))
            is_end_record = await cursor.fetchone()

            if is_end_record and is_end_record[0]:
                # If the rating has ended, inform the user and return
                await interaction.followup.send("This rating period has ended. You cannot rate anymore.",
                                                ephemeral=True)
                return

            # Fetch the current person_with_point data for the rating
            await cursor.execute('SELECT person_with_point FROM rating WHERE rating_id = ?', (rating_id,))
            record = await cursor.fetchone()

            if record and record[0]:
                person_with_point = parse_person_with_point(record[0])
            else:
                person_with_point = {}

            # Update or insert the user's score
            person_with_point[user_id] = score

            # Convert the dictionary back to the string format
            person_with_point_str = dict_to_person_with_point(person_with_point)

            # Update the database
            await cursor.execute('UPDATE rating SET person_with_point = ? WHERE rating_id = ?',
                                 (person_with_point_str, rating_id))
            await db.commit()
            await cursor.close()

            # After updating the rating in the database, update the rating count in the embed
            rating_view = self.ratings.get(rating_id)
            if rating_view:
                await self.update_rating_embed(rating_id, rating_view.rating_channel_id, rating_view.message_id)

            try:
                await interaction.channel.send(f"{interaction.user.mention}, your rating has been saved.",
                                               delete_after=10)
            except discord.errors.NotFound:
                await interaction.channel.send(f"{interaction.user.mention}, your rating has been saved.",
                                               delete_after=10)

    async def load_rating(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT rating_id, rating_channel_id, message_id FROM rating_views')
            records = await cursor.fetchall()

            for rating_id, rating_channel_id, message_id in records:
                # Check if the rating has ended
                await cursor.execute('SELECT is_end FROM rating WHERE rating_id = ?', (rating_id,))
                is_end_record = await cursor.fetchone()

                if is_end_record and is_end_record[0]:
                    # If the rating has ended, delete the record from rating_views
                    await cursor.execute('DELETE FROM rating_views WHERE rating_id = ?', (rating_id,))
                    await db.commit()
                    logging.info(f"Rating {rating_id} has ended. Deleting from rating_views.")
                    continue

                # Attempt to fetch the message from Discord
                channel = self.bot.get_channel(int(rating_channel_id))
                if channel:
                    try:
                        message = await channel.fetch_message(int(message_id))
                        # If message exists, load the rating normally
                        view = RatingView(self.bot, rating_id, rating_channel_id)
                        view.message_id = message_id
                        self.ratings[rating_id] = view
                        await message.edit(view=view)
                        logging.info(f"Rating {rating_id} loaded in channel {rating_channel_id}")
                    except discord.NotFound:
                        # If message does not exist, mark the rating as ended and delete from rating_views
                        await cursor.execute('UPDATE rating SET is_end = 1 WHERE rating_id = ?', (rating_id,))
                        await cursor.execute('DELETE FROM rating_views WHERE rating_id = ?', (rating_id,))
                        logging.error(f"Message {message_id} not found. Rating {rating_id} marked as ended.")
                        await db.commit()
                else:
                    logging.error(f"Channel {rating_channel_id} not found")

            await cursor.close()

    async def save_rating(self, rating_id, view):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'REPLACE INTO rating_views (rating_id, rating_channel_id, message_id) VALUES (?, ?, ?)',
                (rating_id, view.rating_channel_id, view.message_id))
            await db.commit()
            await cursor.close()

    @app_commands.command(name="rt_create", description="Create a rating")
    async def create_rating(self, interaction: discord.Interaction):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        form = RatingForm(self.bot)
        await interaction.response.send_modal(form)

    @app_commands.command(name="rt_end", description="End a rating")
    @app_commands.describe(rating_id="The ID of the rating to end")
    async def end_rating(self, interaction: discord.Interaction, rating_id: str):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        await interaction.response.defer()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT message_id, person_with_point FROM rating WHERE rating_id = ?', (rating_id,))
            record = await cursor.fetchone()

            if not record:
                await interaction.followup.send(f"Rating {rating_id} not found.")
                return

            # If the rating has already ended, just give the average score
            await cursor.execute('SELECT is_end, average_score FROM rating WHERE rating_id = ?', (rating_id,))
            is_end, average_score = await cursor.fetchone()
            if is_end:
                await interaction.followup.send(f"The rating {rating_id} has already ended."
                                                f"The average score for rating {rating_id} is {average_score}.")
                return

            # Update the rating to end
            message_id, person_with_point = record
            await cursor.execute('UPDATE rating SET is_end = 1 WHERE rating_id = ?', (rating_id,))
            await db.commit()

            scores = parse_person_with_point(person_with_point)
            average_score = sum(scores.values()) / len(scores) if scores else 0

            # Generate bar chart for voting distribution
            score_counts = {i: 0 for i in range(1, 11)}
            for score in scores.values():
                score_counts[score] += 1

            fig, ax = plt.subplots()
            ax.bar(score_counts.keys(), score_counts.values())
            ax.set_xticks(list(score_counts.keys()))  # Ensure all labels from 1 to 10 are shown
            ax.set_xlabel('Scores')
            ax.set_xlabel('Scores')
            ax.set_ylabel('Votes')
            ax.set_title('Voting Distribution')

            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            file = discord.File(buf, 'voting_distribution.png')

            # Fetch and edit the original message
            channel = self.bot.get_channel(self.rating_channel_id)
            message = await channel.fetch_message(int(message_id))
            embed = message.embeds[0]
            embed.title = "[END] " + embed.title
            embed.color = discord.Color.red()
            embed.add_field(name="Average Score", value=str(average_score), inline=False)
            embed.set_image(url="attachment://voting_distribution.png")

            # Disable all buttons
            view = RatingView(self.bot, rating_id, self.rating_channel_id)
            view.disable_all_buttons()

            await message.edit(embed=embed, view=view, attachments=[file])

            buf.close()

            await interaction.followup.send(f"Rating {rating_id} has ended. The average score is {average_score}.")

    @app_commands.command(name="rt_cancel", description="Cancel a rating")
    @app_commands.describe(rating_id="The ID of the rating to cancel")
    async def cancel_rating(self, interaction: discord.Interaction, rating_id: str):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        await interaction.response.defer()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT message_id FROM rating WHERE rating_id = ?', (rating_id,))
            record = await cursor.fetchone()

            if not record:
                await interaction.followup.send(f"Rating {rating_id} not found.")
                return

            # If the rating has already ended, inform the user
            await cursor.execute('SELECT is_end FROM rating WHERE rating_id = ?', (rating_id,))
            is_end = await cursor.fetchone()
            if is_end and is_end[0]:
                await interaction.followup.send(f"The rating {rating_id} has already ended.")
                return

            # Update the rating to end and set it as cancelled
            message_id = record[0]
            await cursor.execute('UPDATE rating SET is_end = 1 WHERE rating_id = ?', (rating_id,))
            await db.commit()

            # Fetch and edit the original message
            channel = self.bot.get_channel(self.rating_channel_id)
            message = await channel.fetch_message(int(message_id))
            embed = message.embeds[0]
            embed.title = "[CANCEL] " + embed.title
            embed.color = discord.Color.orange()

            # Disable all buttons
            view = RatingView(self.bot, rating_id, self.rating_channel_id)
            view.disable_all_buttons()

            await message.edit(embed=embed, view=view)

            await interaction.followup.send(f"Rating {rating_id} has been cancelled.")

    @app_commands.command(name="rt_description", description="Change the description of an unended rating")
    @app_commands.describe(rating_id="The ID of the rating to change", new_description="The new description")
    async def change_description(self, interaction: discord.Interaction, rating_id: str, new_description: str):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        await interaction.response.defer()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT message_id, is_end FROM rating WHERE rating_id = ?', (rating_id,))
            record = await cursor.fetchone()

            if not record:
                await interaction.followup.send(f"Rating {rating_id} not found.")
                return

            message_id, is_end = record
            if is_end:
                await interaction.followup.send(
                    f"The rating {rating_id} has already ended. You cannot change its description.")
                return

            # Update the description in the database
            await cursor.execute('UPDATE rating SET description = ? WHERE rating_id = ?', (new_description, rating_id))
            await db.commit()

            # Fetch and edit the original message
            channel = self.bot.get_channel(self.rating_channel_id)
            message = await channel.fetch_message(int(message_id))
            embed = message.embeds[0]
            for i, field in enumerate(embed.fields):
                if field.name == "Description":
                    embed.set_field_at(i, name="Description", value=new_description, inline=False)
                    break
            else:
                embed.add_field(name="Description", value=new_description, inline=False)

            await message.edit(embed=embed)

            await interaction.followup.send(f"The description for rating {rating_id} "
                                            f"has been updated to:\n{new_description}")

    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure the table exists
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS rating (
                    rating_id INTEGER NOT NULL,
                    message_id TEXT NOT NULL,
                    description TEXT,
                    creator_id TEXT NOT NULL,
                    person_with_point TEXT,
                    average_score REAL DEFAULT 0,
                    is_end BOOLEAN DEFAULT 0
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS rating_views (
                    rating_id TEXT PRIMARY KEY,
                    rating_channel_id TEXT,
                    message_id TEXT
                )
            ''')
            await db.commit()

            await self.load_rating()
