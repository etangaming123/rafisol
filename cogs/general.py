import discord
from discord import app_commands
from discord.ext import commands

import common
import permissions
from common import Colors, formatUsername, timestamp

# which /help section each command shows up in
SECTIONS = {
    "General": ["help", "ping", "rank", "userinfo", "serverinfo", "role info", "config editor"],
    "Moderation": ["ban", "unban", "softban", "kick", "timeout", "untimeout", "mute", "unmute", "warn", "clearwarns", "purge", "lockdown", "unlock", "slowmode", "nick", "honeypot setup"],
    "Cases": ["cases", "case", "reason", "delcase"],
    "Roles": ["role add", "role remove", "role create", "role delete", "role edit", "customrole create", "customrole edit", "customrole delete", "rolemenu post", "rolemenu list"],
    "Posts & Logs": ["post send", "post update", "post list", "logs channel", "logs ignore", "logs status"],
    "Settings": ["config export", "config import", "config history", "config rollback", "config reset"],
}

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show the Rafisol commands you can use here.")
    async def help(self, interaction: discord.Interaction):
        config = await self.bot.db.getConfig(interaction.guild.id)
        embed = discord.Embed(
            title="Rafisol",
            description=f"Multipurpose server bot. Most settings live in the [web editor]({self.bot.editorUrl}) - grab your settings with `/config export`, edit them there, then `/config import`.",
            color=common.parseColor(config["general"]["embed_color"]),
        )
        for section, names in SECTIONS.items():
            lines = []
            for name in names:
                allowed, _ = permissions.evaluate(interaction.user, interaction.channel, name, config)
                if allowed:
                    lines.append(f"`/{name}` - {permissions.COMMANDS[name][2]}")
            if lines:
                embed.add_field(name=section, value="\n".join(lines), inline=False)
        embed.set_footer(text=f"Rafisol v{common.version} • {common.githuburl.removeprefix('https://')}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Check Rafisol's latency.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(content=f"Pong! `{round(self.bot.latency * 1000)}ms`", ephemeral=True)

    @app_commands.command(name="userinfo", description="Show info about a member.")
    @app_commands.describe(user="The member to look up (defaults to you).")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        embed = discord.Embed(title=formatUsername(user), color=user.color if user.color.value else Colors.brand)
        embed.set_thumbnail(url=common.avatarUrl(user))
        embed.add_field(name="ID", value=str(user.id))
        embed.add_field(name="Account created", value=f"{timestamp(user.created_at, 'D')} ({timestamp(user.created_at)})")
        if user.joined_at:
            embed.add_field(name="Joined server", value=f"{timestamp(user.joined_at, 'D')} ({timestamp(user.joined_at)})")
        roles = [role.mention for role in reversed(user.roles) if not role.is_default()]
        embed.add_field(name=f"Roles ({len(roles)})", value=common.truncateMessage(" ".join(roles), 1024) if roles else "None", inline=False)
        if user.is_timed_out():
            embed.add_field(name="Timed out until", value=timestamp(user.timed_out_until, "F"))
        if user.premium_since:
            embed.add_field(name="Boosting since", value=timestamp(user.premium_since, "D"))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="serverinfo", description="Show info about this server.")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=guild.name, description=guild.description, color=Colors.brand)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>")
        embed.add_field(name="Created", value=timestamp(guild.created_at, "D"))
        embed.add_field(name="Members", value=str(guild.member_count))
        embed.add_field(name="Channels", value=f"{len(guild.text_channels)} text, {len(guild.voice_channels)} voice")
        embed.add_field(name="Roles", value=str(len(guild.roles) - 1))
        embed.add_field(name="Boosts", value=f"{guild.premium_subscription_count} (level {guild.premium_tier})")
        embed.set_footer(text=f"Server ID: {guild.id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="rank", description="Give yourself (or remove) a self-assignable role.")
    @app_commands.describe(role="The role to toggle.")
    async def rank(self, interaction: discord.Interaction, role: str):
        config = await self.bot.db.getConfig(interaction.guild.id)
        allowed = config["roles"]["self_assignable"]
        target = interaction.guild.get_role(common.toInt(role) or 0)
        if target is None or str(target.id) not in allowed:
            await interaction.response.send_message(content="That role isn't self-assignable here.", ephemeral=True)
            return
        if target >= interaction.guild.me.top_role:
            await interaction.response.send_message(content="That role is above mine, so I can't give it out. Ask an admin to move my role up!", ephemeral=True)
            return
        if target in interaction.user.roles:
            await interaction.user.remove_roles(target, reason="Self-assignable role (/rank)")
            await interaction.response.send_message(content=f"Removed {target.mention}.", ephemeral=True)
        else:
            await interaction.user.add_roles(target, reason="Self-assignable role (/rank)")
            await interaction.response.send_message(content=f"Gave you {target.mention}!", ephemeral=True)

    @rank.autocomplete("role")
    async def rank_autocomplete(self, interaction: discord.Interaction, current: str):
        config = await self.bot.db.getConfig(interaction.guild.id)
        choices = []
        for role_id in config["roles"]["self_assignable"]:
            role = interaction.guild.get_role(int(role_id))
            if role and current.lower() in role.name.lower():
                have = "✓ " if role in interaction.user.roles else ""
                choices.append(app_commands.Choice(name=f"{have}{role.name}"[:100], value=str(role.id)))
        return choices[:25]

async def setup(bot):
    await bot.add_cog(General(bot))
