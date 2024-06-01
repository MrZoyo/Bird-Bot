import discord
from discord.ext import commands
import random
import re


class DnDCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="dnd_roll")
    @discord.app_commands.describe(expression="Expression to roll, e.g., '3+4d6'.",
                                   x="Number of times to repeat the roll.")
    async def dnd_roll(self, interaction: discord.Interaction, expression: str, x: int = 1):
        """Rolls dice based on DnD notation."""
        if '#' in expression:
            parts = expression.split('#', 1)
            if parts[0].isdigit():
                x = int(parts[0])
                expression = parts[1]
            else:
                expression = expression.replace('#', '')
        results = []
        for _ in range(x):
            result, detailed = self.parse_and_roll(expression)
            if result is None:
                await interaction.response.send_message("Invalid dice notation.")
                return
            results.append((result, detailed))

        # Create a table string
        table = "Roll|Result|Details\n----|------|-------\n"
        for i, (result, detailed) in enumerate(results, 1):
            table += f"{i:3} |{result:5} |{detailed}\n"

        await interaction.response.send_message(f"**Results**:\n```\n{table}\n```")

    def parse_and_roll(self, expression):
        pattern = r"([+-]?\d*d\d+)|([+-]?\d+)"
        matches = re.findall(pattern, expression)
        total = 0
        details = []

        for match in matches:
            if 'd' in match[0]:  # Dice roll found
                sign = -1 if match[0].startswith('-') else 1
                parts = match[0].lstrip('+-').split('d')
                num_dice = int(parts[0]) if parts[0] else 1
                dice_sides = int(parts[1])
                rolls = [random.randint(1, dice_sides) for _ in range(num_dice)]
                roll_sum = sum(rolls) * sign
                total += roll_sum
                details.append(f"{'+' if sign > 0 else '-'}{num_dice}d{dice_sides}:" + "+".join(
                    map(str, [x * sign for x in rolls])) + f"={roll_sum},")
            elif match[1]:  # Modifier found
                total += int(match[1])
                details.append(f"{match[1]},")

        detailed_result = "".join(details)
        return total, detailed_result