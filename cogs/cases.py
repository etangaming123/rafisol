import discord
from discord import app_commands
from discord.ext import commands

import common
from common import Colors, formatUsername, timestamp, formatDuration
from cogs.moderation import caseEmbed

class Cases(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="cases", description="List a user's moderation history (or the latest cases in the server).")
    @app_commands.describe(user="The user to look up (leave empty for the latest cases).")
    async def cases(self, interaction: discord.Interaction, user: discord.User = None):
        if user:
            rows = await self.bot.db.userCases(interaction.guild.id, user.id)
            title = f"Cases for {formatUsername(user)}"
        else:
            rows = await self.bot.db.recentCases(interaction.guild.id)
            title = "Latest cases"
        if not rows:
            await interaction.response.send_message(content="No cases found. Squeaky clean!", ephemeral=True)
            return
        lines = []
        for row in rows[:25]:
            line = f"`#{row['case_no']}` **{row['action']}**"
            if not user:
                line += f" <@{row['user_id']}>"
            if row["duration"]:
                line += f" ({formatDuration(row['duration'])})"
            line += f" {timestamp(row['created_at'])} - {common.truncateMessage(row['reason'] or 'No reason provided.', 80)}"
            if not row["active"]:
                line = f"~~{line}~~"
            lines.append(line)
        embed = discord.Embed(title=title, description="\n".join(lines)[:4096], color=Colors.info)
        if user:
            warns = await self.bot.db.activeWarnCount(interaction.guild.id, user.id)
            embed.set_footer(text=f"{len(rows)} case{'s' if len(rows) != 1 else ''} • {warns} active warning{'s' if warns != 1 else ''}" + (" • showing latest 25" if len(rows) > 25 else ""))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="case", description="Show a single case.")
    @app_commands.describe(number="The case number.")
    async def case(self, interaction: discord.Interaction, number: int):
        row = await self.bot.db.getCase(interaction.guild.id, number)
        if row is None:
            await interaction.response.send_message(content=f"There's no case #{number}.", ephemeral=True)
            return
        user = self.bot.get_user(row["user_id"]) or row["user_id"]
        moderator = self.bot.get_user(row["mod_id"]) or row["mod_id"]
        embed = caseEmbed(interaction.guild, row["case_no"], row["action"], user, moderator, row["reason"], row["duration"], row["created_at"], bool(row["active"]))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="reason", description="Change the reason on a case.")
    @app_commands.describe(number="The case number.", reason="The new reason.")
    async def reason(self, interaction: discord.Interaction, number: int, reason: app_commands.Range[str, 1, 1000]):
        if not await self.bot.db.updateCaseReason(interaction.guild.id, number, reason):
            await interaction.response.send_message(content=f"There's no case #{number}.", ephemeral=True)
            return
        await interaction.response.send_message(content=f"Updated the reason for case #{number}.", ephemeral=True)
        row = await self.bot.db.getCase(interaction.guild.id, number)
        embed = caseEmbed(interaction.guild, number, row["action"], self.bot.get_user(row["user_id"]) or row["user_id"], interaction.user, reason, row["duration"], row["created_at"])
        embed.title += " (reason updated)"
        await self.bot.get_cog("Moderation").logCase(interaction.guild, embed)

    @app_commands.command(name="delcase", description="Void a case (it stays in history, crossed out, and stops counting as a warning).")
    @app_commands.describe(number="The case number.")
    async def delcase(self, interaction: discord.Interaction, number: int):
        if not await self.bot.db.deactivateCase(interaction.guild.id, number):
            await interaction.response.send_message(content=f"Case #{number} doesn't exist or is already voided.", ephemeral=True)
            return
        await interaction.response.send_message(content=f"Voided case #{number}.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Cases(bot))
