# bot/cogs/game_dnd_cog.py
from ..utils import config

import discord
from discord.ext import commands
import random
import re


class DnDCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="dnd_roll")
    @discord.app_commands.describe(expression="Expression to roll, e.g., '3+4d6' or '2d04' for 0-4 range.",
                                   x="Number of times to repeat the roll.")
    async def dnd_roll(self, interaction: discord.Interaction, expression: str, x: int = 1):
        """Rolls dice based on DnD notation. Supports 0-based dice with '0' prefix (e.g., d04)."""
        if '#' in expression:
            parts = expression.split('#', 1)
            if parts[0].isdigit():
                x = int(parts[0])
                expression = parts[1]
            else:
                expression = expression.replace('#', '')

        results = []
        for _ in range(x):
            try:
                result, detailed = self.parse_and_roll(expression)
                if result is None:
                    await interaction.response.send_message("Invalid dice notation.", ephemeral=True)
                    return
                results.append((result, detailed))
            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

        # Create a table string
        table = "Roll|Result|Details\n----|------|-------\n"
        for i, (result, detailed) in enumerate(results, 1):
            table += f"{i:3} |{result:5} |{detailed}\n"

        await interaction.response.send_message(f"**Results**:\n```\n{table}\n```")

    def parse_and_roll(self, expression):
        """
        Parses and evaluates a dice rolling expression.
        Supports standard dice (d6) and zero-based dice (d04).
        """
        # Pattern for dice with optional zero prefix
        pattern = r"([+-]?\d*d0?\d+)|([+-]?\d+)"
        matches = re.findall(pattern, expression)

        if not matches:
            raise ValueError("Invalid expression format.")

        total = 0
        details = []

        for match in matches:
            if match[0]:  # Dice roll found
                dice_str = match[0]
                sign = -1 if dice_str.startswith('-') else 1
                parts = dice_str.lstrip('+-').split('d')

                # Handle number of dice
                num_dice = int(parts[0]) if parts[0] else 1
                if num_dice < 1:
                    raise ValueError("Number of dice must be positive.")
                if num_dice > 100:
                    raise ValueError("Maximum 100 dice allowed per roll.")

                # Handle dice sides
                dice_sides_str = parts[1]
                zero_based = dice_sides_str.startswith('0')
                dice_sides = int(dice_sides_str)

                # Validate dice sides
                if dice_sides == 0:
                    raise ValueError("Dice cannot have 0 sides.")
                if dice_sides > 1000:
                    raise ValueError("Maximum 1000 sides per die.")

                # Adjust for zero-based dice
                min_value = 0 if zero_based else 1
                max_value = dice_sides if zero_based else dice_sides

                if max_value < min_value:
                    raise ValueError("Invalid dice range.")

                # Roll the dice
                rolls = [random.randint(min_value, max_value) for _ in range(num_dice)]
                roll_sum = sum(rolls) * sign

                total += roll_sum
                details.append(f"{'+' if sign > 0 else '-'}{num_dice}d{dice_sides_str}:" +
                               "+".join(map(str, [x * sign for x in rolls])) +
                               f"={roll_sum},")

            elif match[1]:  # Modifier found
                modifier = int(match[1])
                total += modifier
                details.append(f"{match[1]},")

        detailed_result = "".join(details)
        return total, detailed_result