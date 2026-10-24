"""
Who can run what. Every slash command is listed in COMMANDS with a level and
(optionally) the Discord permission that also counts as access for it. The
check runs once for every command in RafisolTree.interaction_check (main.py),
so cogs don't need to repeat it.

Access, in order:
  1. Server owner / Administrator - always allowed.
  2. Command disabled by an override - nobody else.
  3. Override channel deny/allow lists.
  4. Override deny roles, then allow roles (allow roles skip the level check).
  5. Level: everyone / mod (mod or admin role, or the native perm) /
     admin (admin role, Manage Server, or the native perm).

tests/test_permissions.py makes sure every registered command is listed here.
"""

import discord

# qualified command name -> (level, native permission or None, description shown in the editor)
COMMANDS = {
    "help":              ("everyone", None, "Show Rafisol's commands"),
    "ping":              ("everyone", None, "Check the bot's latency"),
    "rank":              ("everyone", None, "Toggle a self-assignable role"),
    "userinfo":          ("everyone", None, "Show info about a member"),
    "serverinfo":        ("everyone", None, "Show info about the server"),

    "ban":               ("mod", "ban_members", "Ban a user"),
    "unban":             ("mod", "ban_members", "Unban a user"),
    "softban":           ("mod", "ban_members", "Ban + unban to clear messages"),
    "kick":              ("mod", "kick_members", "Kick a member"),
    "timeout":           ("mod", "moderate_members", "Time out a member"),
    "untimeout":         ("mod", "moderate_members", "Remove a timeout"),
    "mute":              ("mod", "moderate_members", "Give the mute role"),
    "unmute":            ("mod", "moderate_members", "Remove the mute role"),
    "warn":              ("mod", "moderate_members", "Warn a member"),
    "clearwarns":        ("mod", "moderate_members", "Clear a member's warnings"),
    "purge":             ("mod", "manage_messages", "Bulk delete messages"),
    "lockdown":          ("mod", "manage_channels", "Lock a channel or the server"),
    "unlock":            ("mod", "manage_channels", "Unlock a channel or the server"),
    "slowmode":          ("mod", "manage_channels", "Set a channel's slowmode"),
    "nick":              ("mod", "manage_nicknames", "Change a member's nickname"),
    "cases":             ("mod", "moderate_members", "List a user's cases"),
    "case":              ("mod", "moderate_members", "Show a case"),
    "reason":            ("mod", "moderate_members", "Edit a case's reason"),
    "delcase":           ("mod", "moderate_members", "Void a case"),

    "role add":          ("mod", "manage_roles", "Give a member a role"),
    "role remove":       ("mod", "manage_roles", "Take a role from a member"),
    "role create":       ("admin", "manage_roles", "Create a role"),
    "role delete":       ("admin", "manage_roles", "Delete a role"),
    "role edit":         ("admin", "manage_roles", "Edit a role's name/colour/settings"),
    "role info":         ("everyone", None, "Show info about a role"),
    "customrole create": ("everyone", None, "Create your own custom role"),
    "customrole edit":   ("everyone", None, "Edit your custom role"),
    "customrole delete": ("everyone", None, "Delete your custom role"),

    "rolemenu post":     ("admin", "manage_roles", "Post or refresh a role menu"),
    "rolemenu list":     ("admin", "manage_roles", "List role menus"),
    "post send":         ("admin", "manage_webhooks", "Post a saved webhook message"),
    "post update":       ("admin", "manage_webhooks", "Edit a posted webhook message in place"),
    "post list":         ("admin", "manage_webhooks", "List saved webhook posts"),

    "honeypot setup":    ("admin", "manage_channels", "Create a honeypot channel"),
    "logs channel":      ("admin", None, "Set a log channel"),
    "logs ignore":       ("admin", None, "Toggle ignoring a channel in logs"),
    "logs status":       ("admin", None, "Show the logging setup"),
    "config export":     ("admin", None, "Download this server's settings"),
    "config import":     ("admin", None, "Upload edited settings"),
    "config history":    ("admin", None, "List previous settings versions"),
    "config rollback":   ("admin", None, "Restore previous settings"),
    "config reset":      ("admin", None, "Reset all settings"),
    "config editor":     ("everyone", None, "Link to the settings editor"),
}

LEVELS = {"everyone": 0, "mod": 1, "admin": 2}

def roleIds(member: discord.Member):
    return {str(role.id) for role in member.roles}

def isAdmin(member: discord.Member, config: dict):
    if member.guild.owner_id == member.id or member.guild_permissions.administrator:
        return True
    if member.guild_permissions.manage_guild:
        return True
    return bool(roleIds(member) & set(config["permissions"]["admin_roles"]))

def isMod(member: discord.Member, config: dict):
    if isAdmin(member, config):
        return True
    return bool(roleIds(member) & set(config["permissions"]["mod_roles"]))

def channelIds(channel):
    # thread -> parent -> category, so overrides on a category cover everything in it
    ids = set()
    while channel is not None:
        ids.add(str(channel.id))
        channel = getattr(channel, "parent", None) or getattr(channel, "category", None)
    return ids

def evaluate(member: discord.Member, channel, command: str, config: dict):
    """Returns (allowed, reason shown when denied)."""
    if member.guild.owner_id == member.id or member.guild_permissions.administrator:
        return True, None
    level, native, _ = COMMANDS.get(command, ("admin", None, ""))
    override = config["permissions"]["overrides"].get(command) or config["permissions"]["overrides"].get(command.split(" ")[0])
    if override:
        if override.get("disabled"):
            return False, "That command is disabled in this server."
        here = channelIds(channel)
        if here & set(override.get("deny_channels", [])):
            return False, "That command can't be used in this channel."
        if override.get("allow_channels") and not (here & set(override["allow_channels"])):
            return False, "That command can't be used in this channel."
        mine = roleIds(member)
        if mine & set(override.get("deny_roles", [])):
            return False, "You don't have permission to use this command!"
        if mine & set(override.get("allow_roles", [])):
            return True, None

    if level == "everyone":
        return True, None
    if native and getattr(member.guild_permissions, native, False):
        return True, None
    if level == "mod" and isMod(member, config):
        return True, None
    if level == "admin" and isAdmin(member, config):
        return True, None
    return False, "You don't have permission to use this command!"

def canTarget(moderator: discord.Member, target: discord.Member, config: dict):
    """Stop mods from actioning people at/above them (or other mods, if protect_mods is on)."""
    guild = moderator.guild
    if target.id == guild.owner_id:
        return False, "You can't do that to the server owner."
    if target.id == moderator.id:
        return False, "You can't do that to yourself."
    if moderator.id != guild.owner_id and target.top_role >= moderator.top_role:
        return False, "That member's highest role is the same as or above yours."
    if config["moderation"]["protect_mods"] and moderator.id != guild.owner_id and isMod(target, config) and not isAdmin(moderator, config):
        return False, "No. (that member is a moderator)"
    if target.top_role >= guild.me.top_role:
        return False, "That member's highest role is above mine, so I can't touch them. Move my role up!"
    return True, None
