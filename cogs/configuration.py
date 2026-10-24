import io
import json
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

import config_schema
from common import Colors, ConfirmView, timestamp

SECTION_NAMES = {
    "general": "General",
    "permissions": "Permissions",
    "moderation": "Moderation",
    "automod": "Automod",
    "honeypot": "Honeypot",
    "logging": "Logging",
    "welcome": "Join / leave",
    "roles": "Roles",
    "reaction_roles": "Reaction roles",
    "posts": "Webhook posts",
}

def editorButton(url: str):
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Open Settings Editor ↗", style=discord.ButtonStyle.link, url=url))
    return view

def warningsText(warnings: list, limit: int = 1000):
    if not warnings:
        return None
    text = ""
    for i, warning in enumerate(warnings):
        line = f"- {warning}\n"
        if len(text) + len(line) > limit:
            text += f"-# ...and {len(warnings) - i} more"
            break
        text += line
    return text

class Configuration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    config = app_commands.Group(name="config", description="Export, import and manage Rafisol's settings for this server.")
    logs = app_commands.Group(name="logs", description="Quick logging setup (everything else is in the editor).")

    @config.command(name="export", description="Download this server's Rafisol settings as a .json file.")
    async def export(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = await self.bot.db.getConfig(interaction.guild.id)
        data = config_schema.buildExport(config, interaction.guild)
        file = discord.File(io.BytesIO(json.dumps(data, indent=2).encode()), filename=f"rafisol-{interaction.guild.id}.json")
        await interaction.followup.send(
            content="Here are this server's settings! Open the editor, hit **Import…** and pick this file. When you're done, **Export** and upload it with `/config import`.\n-# The file includes your channel and role names so the editor can show them. No webhook URLs or tokens are included.",
            file=file,
            view=editorButton(self.bot.editorUrl),
            ephemeral=True,
        )

    @config.command(name="import", description="Upload edited settings from the editor.")
    @app_commands.describe(file="The .json file exported from the settings editor.")
    async def import_(self, interaction: discord.Interaction, file: discord.Attachment):
        await interaction.response.defer(ephemeral=True)
        if not file.filename.lower().endswith(".json"):
            await interaction.followup.send(content="That's not a .json file!", ephemeral=True)
            return
        if file.size > config_schema.MAX_IMPORT_BYTES:
            await interaction.followup.send(content=f"That file is too big (max {config_schema.MAX_IMPORT_BYTES // 1024} KB).", ephemeral=True)
            return
        raw = await file.read()
        current = await self.bot.db.getConfig(interaction.guild.id)
        guild = config_schema.GuildInfo.fromGuild(interaction.guild)
        try:
            clean, warnings = await asyncio.to_thread(config_schema.validateConfig, raw, guild, current)
        except ValueError as e:
            await interaction.followup.send(content=f"Nothing was changed.\n{e}", ephemeral=True)
            return

        changed = config_schema.changedSections(current, clean)
        if not changed:
            await interaction.followup.send(content="That file is the same as your current settings, nothing to change!" + (f"\n\n**Warnings:**\n{warningsText(warnings)}" if warnings else ""), ephemeral=True)
            return
        embed = discord.Embed(title="Import settings?", color=Colors.edit)
        embed.add_field(name="Sections that will change", value="\n".join(f"- {SECTION_NAMES.get(s, s)}" for s in changed), inline=False)
        if warnings:
            embed.add_field(name=f"Warnings ({len(warnings)})", value=warningsText(warnings), inline=False)
        embed.set_footer(text="You can undo this with /config rollback.")
        view = ConfirmView(interaction.user.id)
        message = await interaction.followup.send(embed=embed, view=view, ephemeral=True, wait=True)
        await view.wait()
        if not view.value:
            await message.edit(content="Cancelled, nothing was changed.", embed=None, view=None)
            return
        await self.bot.db.saveConfig(interaction.guild.id, clean, interaction.user.id, note="import")
        await message.edit(content=f"Done! Updated {len(changed)} section{'s' if len(changed) != 1 else ''}.\n-# If you changed any role menus or posts, run `/rolemenu post` or `/post update` to refresh them.", embed=None, view=None)
        print(f"Imported settings for guild {interaction.guild.id} ({', '.join(changed)})")

    @config.command(name="history", description="List previous versions of this server's settings.")
    async def history(self, interaction: discord.Interaction):
        rows = await self.bot.db.configHistory(interaction.guild.id)
        if not rows:
            await interaction.response.send_message(content="No previous versions saved yet.", ephemeral=True)
            return
        lines = [f"`#{row['id']}` - before {row['note'] or 'change'} by <@{row['author_id']}> {timestamp(row['created_at'])}" for row in rows]
        embed = discord.Embed(title="Settings history", description="\n".join(lines), color=Colors.info)
        embed.set_footer(text="Restore one with /config rollback")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config.command(name="rollback", description="Restore a previous version of this server's settings.")
    @app_commands.describe(version="The version to restore (defaults to the most recent).")
    async def rollback(self, interaction: discord.Interaction, version: int = None):
        rows = await self.bot.db.configHistory(interaction.guild.id)
        if not rows:
            await interaction.response.send_message(content="No previous versions saved yet.", ephemeral=True)
            return
        version = version or rows[0]["id"]
        old = await self.bot.db.historyEntry(interaction.guild.id, version)
        if old is None:
            await interaction.response.send_message(content=f"Couldn't find version #{version}.", ephemeral=True)
            return
        # re-validate, channels/roles may have been deleted since
        clean, warnings = config_schema.validateConfig(old, config_schema.GuildInfo.fromGuild(interaction.guild))
        current = await self.bot.db.getConfig(interaction.guild.id)
        changed = config_schema.changedSections(current, clean)
        view = ConfirmView(interaction.user.id)
        text = f"Restore version #{version}? This changes: {', '.join(SECTION_NAMES.get(s, s) for s in changed) or 'nothing'}."
        if warnings:
            text += f"\n\n**Warnings:**\n{warningsText(warnings)}"
        await interaction.response.send_message(content=text, view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            await interaction.edit_original_response(content="Cancelled.", view=None)
            return
        await self.bot.db.saveConfig(interaction.guild.id, clean, interaction.user.id, note=f"rollback to #{version}")
        await interaction.edit_original_response(content=f"Restored version #{version}!", view=None)

    @rollback.autocomplete("version")
    async def rollback_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = await self.bot.db.configHistory(interaction.guild.id)
        return [app_commands.Choice(name=f"#{row['id']} - before {row['note'] or 'change'}"[:100], value=row["id"]) for row in rows if current in str(row["id"])][:25]

    @config.command(name="reset", description="Reset ALL of Rafisol's settings for this server.")
    async def reset(self, interaction: discord.Interaction):
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(content="Are you sure? This resets **every** Rafisol setting in this server (cases and warnings are kept). You can undo it with `/config rollback`.", view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            await interaction.edit_original_response(content="Cancelled.", view=None)
            return
        await self.bot.db.saveConfig(interaction.guild.id, config_schema.defaults(), interaction.user.id, note="reset")
        await interaction.edit_original_response(content="Done! Everything's back to default.", view=None)

    @config.command(name="editor", description="Get a link to the settings editor.")
    async def editor(self, interaction: discord.Interaction):
        await interaction.response.send_message(content="Export your settings with `/config export`, edit them here, then upload them with `/config import`.", view=editorButton(self.bot.editorUrl), ephemeral=True)

    # ---- logs

    @logs.command(name="channel", description="Set (or clear) where a type of log goes.")
    @app_commands.describe(category="Which logs.", channel="The channel to send them to (leave empty to turn them off).")
    @app_commands.choices(category=[app_commands.Choice(name=c.capitalize(), value=c) for c in config_schema.LOG_CATEGORIES] + [app_commands.Choice(name="All of them", value="all")])
    async def logs_channel(self, interaction: discord.Interaction, category: str, channel: discord.TextChannel = None):
        if channel is not None and not channel.permissions_for(interaction.guild.me).manage_webhooks:
            await interaction.response.send_message(content=f"I need the **Manage Webhooks** permission in {channel.mention} to post logs there.", ephemeral=True)
            return
        config = await self.bot.db.editConfig(interaction.guild.id)
        categories = config_schema.LOG_CATEGORIES if category == "all" else [category]
        for c in categories:
            config["logging"]["channels"][c] = str(channel.id) if channel else None
        await self.bot.db.saveConfig(interaction.guild.id, config, history=False)
        what = "All logs" if category == "all" else f"{category.capitalize()} logs"
        await interaction.response.send_message(content=f"{what} will now go to {channel.mention}!" if channel else f"{what} turned off.", ephemeral=True)

    @logs.command(name="ignore", description="Toggle ignoring a channel (or category) in message/voice logs.")
    @app_commands.describe(channel="The channel or category.")
    async def logs_ignore(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel):
        config = await self.bot.db.editConfig(interaction.guild.id)
        ignored = config["logging"]["ignored_channels"]
        if str(channel.id) in ignored:
            ignored.remove(str(channel.id))
            text = f"{channel.mention} will be logged again."
        else:
            ignored.append(str(channel.id))
            text = f"{channel.mention} will be ignored in logs."
        await self.bot.db.saveConfig(interaction.guild.id, config, history=False)
        await interaction.response.send_message(content=text, ephemeral=True)

    @logs.command(name="status", description="Show how logging is set up here.")
    async def logs_status(self, interaction: discord.Interaction):
        config = await self.bot.db.getConfig(interaction.guild.id)
        logging = config["logging"]
        embed = discord.Embed(title="Logging", color=Colors.info)
        for category in config_schema.LOG_CATEGORIES:
            channel_id = logging["channels"][category]
            channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
            if channel is None:
                value = "Off"
            else:
                perms = channel.permissions_for(interaction.guild.me)
                value = channel.mention + ("" if perms.manage_webhooks else " ⚠️ missing Manage Webhooks")
            events = [e for e, (c, _) in config_schema.LOG_EVENTS.items() if c == category]
            off = [e for e in events if not logging["events"][e]]
            if off and channel:
                value += f"\n-# {len(off)}/{len(events)} events turned off"
            embed.add_field(name=category.capitalize(), value=value)
        if not interaction.guild.me.guild_permissions.view_audit_log:
            embed.add_field(name="⚠️ Missing View Audit Log", value="Server logs and who-did-what need it.", inline=False)
        if logging["ignored_channels"]:
            embed.add_field(name="Ignored channels", value=" ".join(f"<#{c}>" for c in logging["ignored_channels"])[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Configuration(bot))
