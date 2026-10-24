"""
Honeypot channel: a "DO NOT TYPE HERE" channel that hacked accounts and spam
bots blast along with every other channel. Anyone who talks in it gets
softbanned (ban to wipe their recent messages everywhere, then unban) or
whatever action the server picked.
"""

import time
import discord
from discord import app_commands
from discord.ext import commands

import common
import permissions
from common import Colors, parseDuration, plainUsername

class Honeypot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.handled = {} # (guild_id, user_id) -> when, spam bots send a few at once and we only want to action them once

    honeypot = app_commands.Group(name="honeypot", description="Trap channel for hacked accounts / spam bots.")

    def warningEmbed(self, config: dict):
        embed = discord.Embed(title="⚠️ DO NOT TYPE HERE", description=config["honeypot"]["warning"], color=Colors.delete)
        embed.set_footer(text="Anyone who sends a message here is removed automatically.")
        return embed

    @honeypot.command(name="setup", description="Create a honeypot channel (or repost the warning in the current one).")
    @app_commands.describe(name="Channel name (defaults to do-not-type-here).", action="What happens to anyone who types there.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Softban (ban + unban, wipes their messages)", value="softban"),
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Kick", value="kick"),
        app_commands.Choice(name="Timeout", value="timeout"),
    ])
    async def setup_honeypot(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100] = "do-not-type-here", action: str = None):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        me = guild.me.guild_permissions
        if not (me.manage_channels and me.ban_members and me.manage_messages):
            await interaction.followup.send(content="I need **Manage Channels**, **Ban Members** and **Manage Messages** for the honeypot to work.", ephemeral=True)
            return
        config = await self.bot.db.editConfig(guild.id)
        honeypot = config["honeypot"]
        channel = guild.get_channel(common.toInt(honeypot["channel"]) or 0)
        created = False
        if channel is None:
            # put it at the very top, that's where spam bots start
            channel = await guild.create_text_channel(
                name=name,
                position=0,
                topic="DO NOT TYPE HERE - anyone who sends a message here is removed automatically.",
                overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)},
                reason=f"Honeypot set up by {plainUsername(interaction.user)}",
            )
            created = True
        honeypot["enabled"] = True
        honeypot["channel"] = str(channel.id)
        if action:
            honeypot["action"] = action
        await self.bot.db.saveConfig(guild.id, config, interaction.user.id, note="honeypot setup")
        try:
            await channel.send(embed=self.warningEmbed(config))
        except discord.HTTPException:
            pass
        await interaction.followup.send(content=f"{'Created' if created else 'Using'} {channel.mention} as the honeypot. Anyone (except mods) who types there gets **{honeypot['action']}**{' and their last ' + common.formatDuration(honeypot['delete_seconds']) + ' of messages wiped' if honeypot['action'] in ('softban', 'ban') else ''}.\n-# turn it off or tweak it in the editor's Honeypot tab.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot or message.webhook_id or not isinstance(message.author, discord.Member):
            return
        config = await self.bot.db.getConfig(message.guild.id)
        honeypot = config["honeypot"]
        if not honeypot["enabled"] or honeypot["channel"] != str(message.channel.id):
            return
        member = message.author
        if member.guild_permissions.manage_messages or permissions.isMod(member, config):
            return # mods testing it shouldn't get yeeted
        key = (message.guild.id, member.id)
        now = time.monotonic()
        if now - self.handled.get(key, 0) < 60:
            return
        self.handled = {k: t for k, t in self.handled.items() if now - t < 60}
        self.handled[key] = now
        try:
            if member.top_role >= message.guild.me.top_role:
                print(f"Honeypot in {message.guild.id}: {member.id} is above me, can't action them")
                return
            action = honeypot["action"]
            seconds = parseDuration(honeypot["duration"]) if action == "timeout" else None
            reason = f"Honeypot: sent a message in #{message.channel.name}"
            if action in ("kick", "timeout"):
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
            moderation = self.bot.get_cog("Moderation")
            await moderation.punish(message.guild, member, message.guild.me, action, reason, seconds, dm=honeypot["dm"], delete_seconds=honeypot["delete_seconds"])
        except discord.HTTPException as e:
            print(f"Honeypot action failed in {message.guild.id}: {e}")

async def setup(bot):
    await bot.add_cog(Honeypot(bot))
