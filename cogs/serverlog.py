"""
Audit-log style server logs. Everything here comes from on_audit_log_entry_create,
so we always know who did it and why (needs View Audit Log).
"""

import datetime
import discord
from discord.ext import commands

import common
from common import Colors, timestamp, truncateMessage, formatUsername
from logutils import sendLog

A = discord.AuditLogAction
EVENTS = {
    A.channel_create: "channel_create",
    A.channel_delete: "channel_delete",
    A.channel_update: "channel_update",
    A.overwrite_create: "channel_update",
    A.overwrite_update: "channel_update",
    A.overwrite_delete: "channel_update",
    A.role_create: "role_create",
    A.role_delete: "role_delete",
    A.role_update: "role_update",
    A.guild_update: "guild_update",
    A.emoji_create: "emoji_update",
    A.emoji_update: "emoji_update",
    A.emoji_delete: "emoji_update",
    A.sticker_create: "emoji_update",
    A.sticker_update: "emoji_update",
    A.sticker_delete: "emoji_update",
    A.invite_create: "invite_update",
    A.invite_delete: "invite_update",
    A.webhook_create: "webhook_update",
    A.webhook_update: "webhook_update",
    A.webhook_delete: "webhook_update",
    A.thread_create: "thread_update",
    A.thread_update: "thread_update",
    A.thread_delete: "thread_update",
    A.integration_create: "integration_update",
    A.integration_update: "integration_update",
    A.integration_delete: "integration_update",
    A.bot_add: "integration_update",
    A.automod_rule_create: "automod_rule_update",
    A.automod_rule_update: "automod_rule_update",
    A.automod_rule_delete: "automod_rule_update",
    A.scheduled_event_create: "event_update",
    A.scheduled_event_update: "event_update",
    A.scheduled_event_delete: "event_update",
    A.member_update: "member_nickname", # or mod_timeout, sorted out below
    A.member_role_update: "member_roles",
    A.ban: "mod_ban",
    A.unban: "mod_unban",
    A.kick: "mod_kick",
    A.member_prune: "mod_prune",
}

# attributes that are noise (or covered elsewhere)
SKIP_ATTRS = {"id", "type", "available", "flags", "system_channel_flags", "position"}

def readable(name: str):
    return name.replace("_", " ").capitalize()

def permNames(perms: discord.Permissions):
    return {name for name, value in perms if value}

def mention(value):
    if isinstance(value, (discord.Role, discord.abc.GuildChannel, discord.Thread, discord.Member, discord.User)):
        return value.mention
    if isinstance(value, discord.Object):
        return f"`{value.id}`"
    return None

def formatValue(value):
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, discord.Colour):
        return str(value) if value.value else "default"
    if isinstance(value, discord.Asset):
        return f"[image]({value.url})"
    if isinstance(value, datetime.datetime):
        return timestamp(value, "f")
    if isinstance(value, discord.Permissions):
        names = permNames(value)
        return ", ".join(readable(n) for n in sorted(names)) or "none"
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], tuple): # channel overwrites on create: [(target, overwrite)]
            return ", ".join(mention(t) or str(t) for t, _ in value) or "none"
        return ", ".join(mention(v) or formatValue(v) for v in value) or "none"
    if hasattr(value, "name") and hasattr(value, "value") and not isinstance(value, (str, int)):
        return readable(str(value.name)) # enums
    m = mention(value)
    if m:
        return m
    if isinstance(value, str):
        return truncateMessage(value, 400) if value else "empty"
    return str(value)

def describeTarget(entry: discord.AuditLogEntry):
    target = entry.target
    m = mention(target) if not isinstance(target, discord.Object) else None
    if m:
        name = getattr(target, "name", None)
        return f"{m} ({common.removeFormatting(name)})" if name and isinstance(target, (discord.Role, discord.abc.GuildChannel)) else m
    if isinstance(target, discord.Invite):
        return f"`discord.gg/{target.code}`"
    if isinstance(target, discord.Guild):
        return target.name
    # deleted things are just Objects now, so dig the name out of the change set
    name = getattr(entry.before, "name", None) or getattr(entry.after, "name", None) or getattr(target, "name", None)
    code = getattr(entry.before, "code", None) or getattr(entry.after, "code", None)
    if code:
        return f"`discord.gg/{code}`"
    target_id = getattr(target, "id", None)
    return f"**{common.removeFormatting(str(name))}**" + (f" (`{target_id}`)" if target_id else "") if name else (f"`{target_id}`" if target_id else "unknown")

def overwriteLines(entry: discord.AuditLogEntry):
    """Show allow / deny / reset per permission for permission overwrite changes."""
    def state(diff):
        allow = getattr(diff, "allow", None) or discord.Permissions.none()
        deny = getattr(diff, "deny", None) or discord.Permissions.none()
        return permNames(allow), permNames(deny)
    before_allow, before_deny = state(entry.before)
    after_allow, after_deny = state(entry.after)
    lines = []
    for perm in sorted(before_allow | before_deny | after_allow | after_deny):
        old = "allow" if perm in before_allow else "deny" if perm in before_deny else "neutral"
        new = "allow" if perm in after_allow else "deny" if perm in after_deny else "neutral"
        if old != new:
            icon = {"allow": "✅", "deny": "❌", "neutral": "➖"}[new]
            lines.append(f"{icon} {readable(perm)}")
    return lines

def changeFields(entry: discord.AuditLogEntry):
    fields = []
    before = dict(iter(entry.before))
    after = dict(iter(entry.after))
    for attr in list(dict.fromkeys(list(before) + list(after))):
        if attr in SKIP_ATTRS or attr in ("allow", "deny"):
            continue
        old, new = before.get(attr), after.get(attr)
        if old == new:
            continue
        if isinstance(old, discord.Permissions) or isinstance(new, discord.Permissions):
            old_names = permNames(old or discord.Permissions.none())
            new_names = permNames(new or discord.Permissions.none())
            lines = [f"✅ {readable(p)}" for p in sorted(new_names - old_names)] + [f"❌ {readable(p)}" for p in sorted(old_names - new_names)]
            if lines:
                fields.append((readable(attr), "\n".join(lines)))
            continue
        if entry.action.category == discord.AuditLogActionCategory.create:
            fields.append((readable(attr), formatValue(new)))
        elif entry.action.category == discord.AuditLogActionCategory.delete:
            fields.append((readable(attr), formatValue(old)))
        else:
            fields.append((readable(attr), f"{formatValue(old)} → {formatValue(new)}"))
    return fields

class ServerLog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        event = EVENTS.get(entry.action)
        if event is None:
            return
        guild = entry.guild
        by_me = entry.user_id == self.bot.user.id

        if entry.action == A.member_update:
            timed_out = getattr(entry.after, "timed_out_until", discord.utils.MISSING)
            if timed_out is not discord.utils.MISSING:
                if not by_me:
                    await self.externalCase(entry, "timeout" if timed_out else "untimeout", timed_out)
                return
            if not hasattr(entry.after, "nick"):
                return # mute/deafen in voice etc, voice log has those
        if event.startswith("mod_") and event != "mod_prune":
            if not by_me: # rafisol's own actions already have cases
                await self.externalCase(entry, {"mod_ban": "ban", "mod_unban": "unban", "mod_kick": "kick"}[event])
            return

        verb = {discord.AuditLogActionCategory.create: "Created", discord.AuditLogActionCategory.delete: "Deleted"}.get(entry.action.category, "Updated")
        color = {"Created": Colors.undo, "Deleted": Colors.delete}.get(verb, Colors.edit)
        title = readable(entry.action.name).replace(" update", "").replace(" create", "").replace(" delete", "")
        title = f"{title} {verb}"
        if entry.action == A.member_role_update:
            title = "Member Roles Changed"
        elif entry.action == A.member_update:
            title = "Nickname Changed"
        elif entry.action in (A.overwrite_create, A.overwrite_update, A.overwrite_delete):
            title = "Channel Permissions Changed"
        elif entry.action == A.bot_add:
            title = "Bot Added"
        elif entry.action == A.member_prune:
            title = "Members Pruned"

        description = describeTarget(entry)
        if entry.user:
            description += f"\nby {entry.user.mention} ({formatUsername(entry.user)})"
        embed = discord.Embed(title=title, description=description, color=color, timestamp=entry.created_at)

        if entry.action in (A.overwrite_create, A.overwrite_update, A.overwrite_delete):
            who = entry.extra
            label = mention(who) or getattr(who, "name", None) or "someone"
            lines = overwriteLines(entry)
            if entry.action == A.overwrite_delete:
                lines = ["Overwrite removed"]
            embed.add_field(name="Permissions for", value=label, inline=False)
            if lines:
                embed.add_field(name="Changes", value=truncateMessage("\n".join(lines), 1024), inline=False)
        elif entry.action == A.member_role_update:
            # audit log puts added roles in after.roles and removed ones in before.roles
            added, removed = getattr(entry.after, "roles", []), getattr(entry.before, "roles", [])
            if added:
                embed.add_field(name="Added", value=truncateMessage(formatValue(added), 1024), inline=False)
            if removed:
                embed.add_field(name="Removed", value=truncateMessage(formatValue(removed), 1024), inline=False)
        elif entry.action == A.member_prune:
            embed.add_field(name="Removed", value=str(getattr(entry.extra, "members_removed", "?")))
            embed.add_field(name="Inactive for", value=f"{getattr(entry.extra, 'delete_member_days', '?')} days")
        else:
            for name, value in changeFields(entry)[:24]:
                embed.add_field(name=name, value=truncateMessage(value, 1024) or "none", inline=len(value) < 60)

        if entry.reason:
            embed.add_field(name="Reason", value=truncateMessage(entry.reason, 1024), inline=False)
        embed.set_footer(text=f"Target ID: {getattr(entry.target, 'id', '?')}" + (f" • User ID: {entry.user_id}" if entry.user_id else ""))

        channel = entry.target if isinstance(entry.target, (discord.abc.GuildChannel, discord.Thread)) else None
        member = entry.target if isinstance(entry.target, discord.Member) else None
        if event in ("member_roles", "member_nickname"):
            await sendLog(self.bot, guild, event, embed, member=member)
        else:
            await sendLog(self.bot, guild, event, embed, channel=channel)

    async def externalCase(self, entry: discord.AuditLogEntry, action: str, until: datetime.datetime = None):
        """Bans/kicks/timeouts done through Discord (or another bot) still get a case."""
        event = {"ban": "mod_ban", "unban": "mod_unban", "kick": "mod_kick", "timeout": "mod_timeout", "untimeout": "mod_timeout"}[action]
        config = await self.bot.db.getConfig(entry.guild.id)
        if not config["logging"]["events"][event]:
            return
        moderation = self.bot.get_cog("Moderation")
        target = entry.target
        if target is None or entry.user is None or moderation is None:
            return
        if isinstance(target, discord.Object):
            target = self.bot.get_user(target.id) or await self.bot.fetch_user(target.id)
        duration = int((until - discord.utils.utcnow()).total_seconds()) if until else None
        await moderation.recordCase(entry.guild, action, target, entry.user, entry.reason, duration)

async def setup(bot):
    await bot.add_cog(ServerLog(bot))
