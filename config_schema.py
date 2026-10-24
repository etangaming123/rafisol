"""
Server settings schema for Rafisol. Everything a server can configure lives in
one JSON blob per guild (see database.py), which is also exactly what
/config export hands out and /config import takes back.

The static editor (editor.html) gets its defaults from siteresources/defaults.js,
which generate_editor_defaults.py builds from DEFAULT_CONFIG below - rerun it
whenever you touch the defaults, events or command list.

All snowflakes are stored as strings, since javascript can't hold them as
numbers without losing precision.
"""

import re
import copy
import json
import time

from common import parseDuration

SCHEMA_VERSION = 1
MAX_IMPORT_BYTES = 256 * 1024

# id -> (category, readable label). categories match logging.channels
LOG_EVENTS = {
    "message_delete":      ("messages", "Message deleted"),
    "message_bulk_delete": ("messages", "Messages bulk deleted"),
    "message_edit":        ("messages", "Message edited"),
    "member_join":         ("members", "Member joined"),
    "member_leave":        ("members", "Member left"),
    "member_nickname":     ("members", "Nickname changed"),
    "member_roles":        ("members", "Member roles changed"),
    "member_user_update":  ("members", "Username / avatar changed"),
    "voice_join":          ("voice", "Joined voice channel"),
    "voice_leave":         ("voice", "Left voice channel"),
    "voice_move":          ("voice", "Moved voice channel"),
    "voice_server_mute":   ("voice", "Server muted / deafened"),
    "voice_self_mute":     ("voice", "Self muted / deafened"),
    "voice_stream":        ("voice", "Started / stopped streaming or video"),
    "channel_create":      ("server", "Channel created"),
    "channel_delete":      ("server", "Channel deleted"),
    "channel_update":      ("server", "Channel edited (incl. permissions)"),
    "role_create":         ("server", "Role created"),
    "role_delete":         ("server", "Role deleted"),
    "role_update":         ("server", "Role edited"),
    "guild_update":        ("server", "Server settings edited"),
    "emoji_update":        ("server", "Emojis / stickers changed"),
    "invite_update":       ("server", "Invites created / deleted"),
    "webhook_update":      ("server", "Webhooks changed"),
    "thread_update":       ("server", "Threads created / deleted / edited"),
    "integration_update":  ("server", "Integrations / bots changed"),
    "automod_rule_update": ("server", "Discord AutoMod rules changed"),
    "event_update":        ("server", "Scheduled events changed"),
    "mod_ban":             ("moderation", "Member banned (outside Rafisol)"),
    "mod_unban":           ("moderation", "Member unbanned (outside Rafisol)"),
    "mod_kick":            ("moderation", "Member kicked (outside Rafisol)"),
    "mod_timeout":         ("moderation", "Member timed out (outside Rafisol)"),
    "mod_prune":           ("moderation", "Members pruned"),
}
LOG_CATEGORIES = ["messages", "members", "voice", "server", "moderation"]

MOD_ACTIONS = ["warn", "timeout", "mute", "kick", "ban"]
AUTOMOD_ACTIONS = ["log", "delete", "warn", "timeout", "mute", "kick", "ban"]
HONEYPOT_ACTIONS = ["softban", "ban", "kick", "timeout"]
HONEYPOT_DELETE = [3600, 86400, 259200, 604800] # discord caps ban message deletion at 7 days
ROLEMENU_MODES = ["normal", "unique", "verify", "remove"]
ROLEMENU_TYPES = ["buttons", "select"]
BUTTON_STYLES = ["primary", "secondary", "success", "danger"]

# what channel types can be picked where
POSTABLE_CHANNELS = ("text", "news", "voice", "stage_voice")
LOCKABLE_CHANNELS = ("text", "news", "voice", "stage_voice", "forum", "media")

ID_SLUG = re.compile(r"^[a-z0-9_-]{1,32}$")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
COMMAND_NAME = re.compile(r"^[a-z0-9_-]{1,32}( [a-z0-9_-]{1,32}){0,2}$")

EMBED_DEFAULT = {
    "title": "",
    "description": "",
    "url": "",
    "color": "",
    "author_name": "",
    "author_icon": "",
    "fields": [],
    "image": "",
    "thumbnail": "",
    "footer": "",
    "footer_icon": "",
    "timestamp": False,
}

ROLEMENU_DEFAULT = {
    "id": "",
    "channel": None,
    "message_id": None,
    "mode": "normal",
    "type": "buttons",
    "placeholder": "Pick your roles",
    "content": "",
    "embed": copy.deepcopy(EMBED_DEFAULT),
    "options": [],
}

ROLEMENU_OPTION_DEFAULT = {"role": None, "label": "", "emoji": "", "style": "secondary", "description": ""}

POST_DEFAULT = {
    "id": "",
    "channel": None,
    "username": "",
    "avatar_url": "",
    "content": "",
    "embeds": [],
    "message_id": None,
    "posted_channel": None,
}

OVERRIDE_DEFAULT = {"allow_roles": [], "deny_roles": [], "allow_channels": [], "deny_channels": [], "disabled": False}

DEFAULT_CONFIG = {
    "schema": SCHEMA_VERSION,
    "general": {
        "embed_color": "#8649d7",
    },
    "permissions": {
        "admin_roles": [],
        "mod_roles": [],
        "overrides": {},
    },
    "moderation": {
        "mute_role": None,
        "dm_on_action": True,
        "dm_extra": "",
        "require_reason": False,
        "protect_mods": True,
        "lockdown_channels": [],
        "lockdown_message": "This channel has been locked by a moderator.",
        "warn_thresholds": [],
    },
    "automod": {
        "enabled": False,
        "log_channel": None,
        "ignored_roles": [],
        "ignored_channels": [],
        "rules": {
            "words":    {"enabled": False, "list": [], "action": "delete", "duration": "10m"},
            "invites":  {"enabled": False, "allow_guilds": [], "action": "delete", "duration": "10m"},
            "links":    {"enabled": False, "allow_domains": [], "action": "delete", "duration": "10m"},
            "mentions": {"enabled": False, "max": 5, "action": "timeout", "duration": "10m"},
            "spam":     {"enabled": False, "messages": 6, "seconds": 5, "action": "timeout", "duration": "5m"},
            "caps":     {"enabled": False, "percent": 70, "min_length": 12, "action": "delete", "duration": "10m"},
        },
    },
    "honeypot": {
        "enabled": False,
        "channel": None,
        "action": "softban",
        "delete_seconds": 604800,
        "duration": "1d",
        "dm": True,
        "warning": "**DO NOT TYPE HERE.** This channel is a trap for hacked accounts and spam bots - anyone who sends a message here is automatically removed from the server and their recent messages are deleted.",
    },
    "logging": {
        "channels": {category: None for category in LOG_CATEGORIES},
        "events": {event: True for event in LOG_EVENTS},
        "ignored_channels": [],
        "ignored_roles": [],
        "ignore_bots": True,
        "new_account_days": 7,
    },
    "welcome": {
        "join": {"enabled": False, "channel": None, "message": "Welcome {user.mention} to **{server}**! You're our {membercount.ordinal} member.", "embed": copy.deepcopy(EMBED_DEFAULT)},
        "leave": {"enabled": False, "channel": None, "message": "{user} has left the server.", "embed": copy.deepcopy(EMBED_DEFAULT)},
        "dm": {"enabled": False, "message": "", "embed": copy.deepcopy(EMBED_DEFAULT)},
        "autoroles": [],
        "bot_autoroles": [],
        "role_persist": False,
    },
    "roles": {
        "custom_roles": {"enabled": False, "allow_boosters": True, "allowed_roles": [], "anchor_role": None},
        "self_assignable": [],
    },
    "reaction_roles": [],
    "posts": [],
}

def defaults():
    return copy.deepcopy(DEFAULT_CONFIG)

def fillDefaults(data: dict, template: dict = None):
    """Deep-merge stored data onto the defaults so older configs pick up new keys. Lists/values from data win."""
    template = DEFAULT_CONFIG if template is None else template
    out = copy.deepcopy(template)
    if not isinstance(data, dict):
        return out
    for key, value in data.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict) and key not in ("overrides",):
            # events/channels have fixed keys, overrides is free-form
            out[key] = fillDefaults(value, out[key])
        else:
            out[key] = copy.deepcopy(value)
    return out


class GuildInfo:
    """What the validator needs to know about a server. Built from a discord.Guild, or by hand in tests."""
    def __init__(self, channels: dict, roles: dict, bot_top: int, guild_id: str = None):
        self.channels = channels # "id" -> type string
        self.roles = roles       # "id" -> {"position": int, "managed": bool, "default": bool}
        self.bot_top = bot_top   # position of the bot's highest role
        self.guild_id = guild_id

    @classmethod
    def fromGuild(cls, guild):
        channels = {str(c.id): str(c.type) for c in guild.channels}
        for thread in guild.threads:
            channels[str(thread.id)] = "thread"
        roles = {str(r.id): {"position": r.position, "managed": r.managed, "default": r.is_default()} for r in guild.roles}
        return cls(channels, roles, guild.me.top_role.position, str(guild.id))


class Validator:
    def __init__(self, guild: GuildInfo = None):
        self.guild = guild
        self.warnings = []

    def warn(self, path, message):
        self.warnings.append(f"`{path}`: {message}")

    # ---- primitives

    def boolean(self, value, default, path):
        if isinstance(value, bool):
            return value
        if value is not None:
            self.warn(path, "expected true/false, using default")
        return default

    def integer(self, value, default, low, high, path):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            if value is not None:
                self.warn(path, "expected a number, using default")
            return default
        clamped = max(low, min(high, int(value)))
        if clamped != value:
            self.warn(path, f"clamped to {clamped} (allowed {low}-{high})")
        return clamped

    def string(self, value, default, maxlen, path):
        if value is None:
            return default
        if not isinstance(value, str):
            self.warn(path, "expected text, using default")
            return default
        if len(value) > maxlen:
            self.warn(path, f"cut down to {maxlen} characters")
            return value[:maxlen]
        return value

    def choice(self, value, options, default, path):
        if value in options:
            return value
        if value is not None:
            self.warn(path, f"must be one of {', '.join(map(str, options))}, using {default}")
        return default

    def color(self, value, default, path, allow_empty=False):
        if allow_empty and value in ("", None):
            return ""
        if isinstance(value, str) and HEX_COLOR.match(value):
            return value.lower()
        if value is not None:
            self.warn(path, "expected a hex colour like #8649d7, using default")
        return default

    def duration(self, value, default, path, max_seconds=None):
        if value in (None, ""):
            return default
        seconds = parseDuration(value)
        if seconds is None:
            self.warn(path, f"couldn't read duration {value!r}, using {default}")
            return default
        if max_seconds and seconds > max_seconds:
            self.warn(path, f"longer than allowed, using {default}")
            return default
        return str(value).strip().lower().replace(" ", "")

    def url(self, value, path):
        value = self.string(value, "", 2048, path)
        if value and not (value.startswith("https://") or value.startswith("http://") or value.startswith("{")):
            self.warn(path, "links must start with https://, removed")
            return ""
        return value

    def snowflake(self, value, path):
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            value = str(value) # an int that survived JSON is fine, but warn since JS may have mangled it
            self.warn(path, "IDs should be strings (javascript can mangle big numbers)")
        if isinstance(value, str) and value.isdigit() and 15 <= len(value) <= 21:
            return value
        self.warn(path, f"{value!r} isn't a valid ID, removed")
        return None

    def channel(self, value, path, types=POSTABLE_CHANNELS):
        cid = self.snowflake(value, path)
        if cid is None or self.guild is None:
            return cid
        ctype = self.guild.channels.get(cid)
        if ctype is None:
            self.warn(path, f"channel {cid} doesn't exist in this server, removed")
            return None
        if types and ctype not in types:
            self.warn(path, f"channel {cid} is a {ctype} channel, which can't be used here, removed")
            return None
        return cid

    def channels(self, value, path, types=None, limit=100):
        if not isinstance(value, list):
            if value is not None:
                self.warn(path, "expected a list")
            return []
        out = []
        for i, item in enumerate(value[:limit]):
            cid = self.channel(item, f"{path}[{i}]", types)
            if cid and cid not in out:
                out.append(cid)
        return out

    def role(self, value, path, assignable=False):
        rid = self.snowflake(value, path)
        if rid is None or self.guild is None:
            return rid
        info = self.guild.roles.get(rid)
        if info is None:
            self.warn(path, f"role {rid} doesn't exist in this server, removed")
            return None
        if assignable:
            if info["default"] or info["managed"]:
                self.warn(path, f"role {rid} is managed by Discord/an integration and can't be given out, removed")
                return None
            if info["position"] >= self.guild.bot_top:
                self.warn(path, f"role {rid} is above Rafisol's highest role, so it can't be given out - move Rafisol's role up (kept anyway)")
        return rid

    def roles(self, value, path, assignable=False, limit=100):
        if not isinstance(value, list):
            if value is not None:
                self.warn(path, "expected a list")
            return []
        out = []
        for i, item in enumerate(value[:limit]):
            rid = self.role(item, f"{path}[{i}]", assignable)
            if rid and rid not in out:
                out.append(rid)
        if len(value) > limit:
            self.warn(path, f"only the first {limit} kept")
        return out

    def strings(self, value, path, maxlen, limit):
        if not isinstance(value, list):
            if value is not None:
                self.warn(path, "expected a list")
            return []
        out = []
        for i, item in enumerate(value[:limit]):
            item = self.string(item, "", maxlen, f"{path}[{i}]").strip()
            if item and item not in out:
                out.append(item)
        if len(value) > limit:
            self.warn(path, f"only the first {limit} kept")
        return out

    def section(self, value, path):
        if isinstance(value, dict):
            return value
        if value is not None:
            self.warn(path, "expected an object, using defaults")
        return {}

    # ---- shared shapes

    def embed(self, value, path):
        value = self.section(value, path)
        out = copy.deepcopy(EMBED_DEFAULT)
        out["title"] = self.string(value.get("title"), "", 256, f"{path}.title")
        out["description"] = self.string(value.get("description"), "", 4096, f"{path}.description")
        out["url"] = self.url(value.get("url"), f"{path}.url")
        out["color"] = self.color(value.get("color"), "", f"{path}.color", allow_empty=True)
        out["author_name"] = self.string(value.get("author_name"), "", 256, f"{path}.author_name")
        out["author_icon"] = self.url(value.get("author_icon"), f"{path}.author_icon")
        out["image"] = self.url(value.get("image"), f"{path}.image")
        out["thumbnail"] = self.url(value.get("thumbnail"), f"{path}.thumbnail")
        out["footer"] = self.string(value.get("footer"), "", 2048, f"{path}.footer")
        out["footer_icon"] = self.url(value.get("footer_icon"), f"{path}.footer_icon")
        out["timestamp"] = self.boolean(value.get("timestamp"), False, f"{path}.timestamp")
        fields = value.get("fields") if isinstance(value.get("fields"), list) else []
        if len(fields) > 25:
            self.warn(f"{path}.fields", "embeds can only have 25 fields, extra removed")
        for i, field in enumerate(fields[:25]):
            field = self.section(field, f"{path}.fields[{i}]")
            name = self.string(field.get("name"), "", 256, f"{path}.fields[{i}].name")
            text = self.string(field.get("value"), "", 1024, f"{path}.fields[{i}].value")
            if name.strip() and text.strip():
                out["fields"].append({"name": name, "value": text, "inline": self.boolean(field.get("inline"), False, f"{path}.fields[{i}].inline")})
            elif name or text:
                self.warn(f"{path}.fields[{i}]", "fields need both a name and a value, removed")
        if embedLength(out) > 6000:
            self.warn(path, "embed is over Discord's 6000 character limit - Discord will reject it")
        return out

    def message(self, value, path, default_message):
        # join/leave/dm style: text + optional embed
        value = self.section(value, path)
        return {
            "enabled": self.boolean(value.get("enabled"), False, f"{path}.enabled"),
            "message": self.string(value.get("message"), default_message, 2000, f"{path}.message"),
            "embed": self.embed(value.get("embed"), f"{path}.embed"),
        }

    # ---- sections

    def general(self, value):
        value = self.section(value, "general")
        return {"embed_color": self.color(value.get("embed_color"), DEFAULT_CONFIG["general"]["embed_color"], "general.embed_color")}

    def permissions(self, value):
        value = self.section(value, "permissions")
        out = {
            "admin_roles": self.roles(value.get("admin_roles"), "permissions.admin_roles", limit=25),
            "mod_roles": self.roles(value.get("mod_roles"), "permissions.mod_roles", limit=25),
            "overrides": {},
        }
        overrides = self.section(value.get("overrides"), "permissions.overrides")
        for name, override in list(overrides.items())[:150]:
            path = f"permissions.overrides.{name}"
            if not isinstance(name, str) or not COMMAND_NAME.match(name):
                self.warn(path, "not a valid command name, removed")
                continue
            override = self.section(override, path)
            clean = {
                "allow_roles": self.roles(override.get("allow_roles"), f"{path}.allow_roles", limit=25),
                "deny_roles": self.roles(override.get("deny_roles"), f"{path}.deny_roles", limit=25),
                "allow_channels": self.channels(override.get("allow_channels"), f"{path}.allow_channels", limit=50),
                "deny_channels": self.channels(override.get("deny_channels"), f"{path}.deny_channels", limit=50),
                "disabled": self.boolean(override.get("disabled"), False, f"{path}.disabled"),
            }
            if clean != OVERRIDE_DEFAULT: # don't keep empty overrides around
                out["overrides"][name] = clean
        return out

    def moderation(self, value):
        value = self.section(value, "moderation")
        d = DEFAULT_CONFIG["moderation"]
        out = {
            "mute_role": self.role(value.get("mute_role"), "moderation.mute_role", assignable=True),
            "dm_on_action": self.boolean(value.get("dm_on_action"), d["dm_on_action"], "moderation.dm_on_action"),
            "dm_extra": self.string(value.get("dm_extra"), d["dm_extra"], 500, "moderation.dm_extra"),
            "require_reason": self.boolean(value.get("require_reason"), d["require_reason"], "moderation.require_reason"),
            "protect_mods": self.boolean(value.get("protect_mods"), d["protect_mods"], "moderation.protect_mods"),
            "lockdown_channels": self.channels(value.get("lockdown_channels"), "moderation.lockdown_channels", LOCKABLE_CHANNELS, limit=100),
            "lockdown_message": self.string(value.get("lockdown_message"), d["lockdown_message"], 1000, "moderation.lockdown_message"),
            "warn_thresholds": [],
        }
        thresholds = value.get("warn_thresholds") if isinstance(value.get("warn_thresholds"), list) else []
        seen = set()
        for i, item in enumerate(thresholds[:10]):
            path = f"moderation.warn_thresholds[{i}]"
            item = self.section(item, path)
            count = self.integer(item.get("count"), None, 1, 100, f"{path}.count")
            if count is None or count in seen:
                self.warn(path, "needs a unique warning count, removed")
                continue
            seen.add(count)
            out["warn_thresholds"].append({
                "count": count,
                "action": self.choice(item.get("action"), ["timeout", "mute", "kick", "ban"], "timeout", f"{path}.action"),
                "duration": self.duration(item.get("duration"), "1h", f"{path}.duration"),
            })
        out["warn_thresholds"].sort(key=lambda t: t["count"])
        return out

    def automod(self, value):
        value = self.section(value, "automod")
        d = DEFAULT_CONFIG["automod"]
        rules = self.section(value.get("rules"), "automod.rules")
        out = {
            "enabled": self.boolean(value.get("enabled"), d["enabled"], "automod.enabled"),
            "log_channel": self.channel(value.get("log_channel"), "automod.log_channel"),
            "ignored_roles": self.roles(value.get("ignored_roles"), "automod.ignored_roles", limit=50),
            "ignored_channels": self.channels(value.get("ignored_channels"), "automod.ignored_channels", limit=100),
            "rules": {},
        }
        for name, rule_default in d["rules"].items():
            path = f"automod.rules.{name}"
            rule = self.section(rules.get(name), path)
            clean = {
                "enabled": self.boolean(rule.get("enabled"), False, f"{path}.enabled"),
                "action": self.choice(rule.get("action"), AUTOMOD_ACTIONS, rule_default["action"], f"{path}.action"),
                "duration": self.duration(rule.get("duration"), rule_default["duration"], f"{path}.duration"),
            }
            if name == "words":
                clean["list"] = self.strings(rule.get("list"), f"{path}.list", 100, 500)
            elif name == "invites":
                guilds = rule.get("allow_guilds") if isinstance(rule.get("allow_guilds"), list) else []
                clean["allow_guilds"] = [g for g in (self.snowflake(x, f"{path}.allow_guilds[{i}]") for i, x in enumerate(guilds[:50])) if g]
            elif name == "links":
                clean["allow_domains"] = [x.lower() for x in self.strings(rule.get("allow_domains"), f"{path}.allow_domains", 253, 200)]
            elif name == "mentions":
                clean["max"] = self.integer(rule.get("max"), rule_default["max"], 1, 50, f"{path}.max")
            elif name == "spam":
                clean["messages"] = self.integer(rule.get("messages"), rule_default["messages"], 2, 30, f"{path}.messages")
                clean["seconds"] = self.integer(rule.get("seconds"), rule_default["seconds"], 1, 60, f"{path}.seconds")
            elif name == "caps":
                clean["percent"] = self.integer(rule.get("percent"), rule_default["percent"], 10, 100, f"{path}.percent")
                clean["min_length"] = self.integer(rule.get("min_length"), rule_default["min_length"], 1, 2000, f"{path}.min_length")
            out["rules"][name] = {key: clean[key] for key in rule_default} # keep key order same as defaults
        return out

    def honeypot(self, value):
        value = self.section(value, "honeypot")
        d = DEFAULT_CONFIG["honeypot"]
        return {
            "enabled": self.boolean(value.get("enabled"), d["enabled"], "honeypot.enabled"),
            "channel": self.channel(value.get("channel"), "honeypot.channel", ("text", "news", "voice", "stage_voice", "forum", "media")),
            "action": self.choice(value.get("action"), HONEYPOT_ACTIONS, d["action"], "honeypot.action"),
            "delete_seconds": self.choice(value.get("delete_seconds"), HONEYPOT_DELETE, d["delete_seconds"], "honeypot.delete_seconds"),
            "duration": self.duration(value.get("duration"), d["duration"], "honeypot.duration", max_seconds=28 * 86400),
            "dm": self.boolean(value.get("dm"), d["dm"], "honeypot.dm"),
            "warning": self.string(value.get("warning"), d["warning"], 2000, "honeypot.warning"),
        }

    def logging(self, value):
        value = self.section(value, "logging")
        d = DEFAULT_CONFIG["logging"]
        channels = self.section(value.get("channels"), "logging.channels")
        events = self.section(value.get("events"), "logging.events")
        return {
            "channels": {c: self.channel(channels.get(c), f"logging.channels.{c}") for c in LOG_CATEGORIES},
            "events": {e: self.boolean(events.get(e), True, f"logging.events.{e}") for e in LOG_EVENTS},
            "ignored_channels": self.channels(value.get("ignored_channels"), "logging.ignored_channels", limit=200),
            "ignored_roles": self.roles(value.get("ignored_roles"), "logging.ignored_roles", limit=50),
            "ignore_bots": self.boolean(value.get("ignore_bots"), d["ignore_bots"], "logging.ignore_bots"),
            "new_account_days": self.integer(value.get("new_account_days"), d["new_account_days"], 0, 365, "logging.new_account_days"),
        }

    def welcome(self, value):
        value = self.section(value, "welcome")
        d = DEFAULT_CONFIG["welcome"]
        join = self.message(value.get("join"), "welcome.join", d["join"]["message"])
        join["channel"] = self.channel(self.section(value.get("join"), "welcome.join").get("channel"), "welcome.join.channel")
        leave = self.message(value.get("leave"), "welcome.leave", d["leave"]["message"])
        leave["channel"] = self.channel(self.section(value.get("leave"), "welcome.leave").get("channel"), "welcome.leave.channel")
        return {
            "join": {key: join[key] for key in d["join"]},
            "leave": {key: leave[key] for key in d["leave"]},
            "dm": self.message(value.get("dm"), "welcome.dm", d["dm"]["message"]),
            "autoroles": self.roles(value.get("autoroles"), "welcome.autoroles", assignable=True, limit=10),
            "bot_autoroles": self.roles(value.get("bot_autoroles"), "welcome.bot_autoroles", assignable=True, limit=10),
            "role_persist": self.boolean(value.get("role_persist"), d["role_persist"], "welcome.role_persist"),
        }

    def roles_section(self, value):
        value = self.section(value, "roles")
        custom = self.section(value.get("custom_roles"), "roles.custom_roles")
        return {
            "custom_roles": {
                "enabled": self.boolean(custom.get("enabled"), False, "roles.custom_roles.enabled"),
                "allow_boosters": self.boolean(custom.get("allow_boosters"), True, "roles.custom_roles.allow_boosters"),
                "allowed_roles": self.roles(custom.get("allowed_roles"), "roles.custom_roles.allowed_roles", limit=25),
                "anchor_role": self.role(custom.get("anchor_role"), "roles.custom_roles.anchor_role"),
            },
            "self_assignable": self.roles(value.get("self_assignable"), "roles.self_assignable", assignable=True, limit=25),
        }

    def slug(self, value, path, seen):
        if not isinstance(value, str) or not ID_SLUG.match(value):
            self.warn(path, "needs an id of 1-32 lowercase letters, numbers, - or _, removed")
            return None
        if value in seen:
            self.warn(path, f"id {value!r} is used twice, second one removed")
            return None
        seen.add(value)
        return value

    def reaction_roles(self, value):
        if not isinstance(value, list):
            if value is not None:
                self.warn("reaction_roles", "expected a list")
            return []
        out, seen = [], set()
        for i, menu in enumerate(value[:50]):
            path = f"reaction_roles[{i}]"
            menu = self.section(menu, path)
            menu_id = self.slug(menu.get("id"), f"{path}.id", seen)
            if menu_id is None:
                continue
            clean = {
                "id": menu_id,
                "channel": self.channel(menu.get("channel"), f"{path}.channel"),
                "message_id": self.snowflake(menu.get("message_id"), f"{path}.message_id"),
                "mode": self.choice(menu.get("mode"), ROLEMENU_MODES, "normal", f"{path}.mode"),
                "type": self.choice(menu.get("type"), ROLEMENU_TYPES, "buttons", f"{path}.type"),
                "placeholder": self.string(menu.get("placeholder"), ROLEMENU_DEFAULT["placeholder"], 150, f"{path}.placeholder"),
                "content": self.string(menu.get("content"), "", 2000, f"{path}.content"),
                "embed": self.embed(menu.get("embed"), f"{path}.embed"),
                "options": [],
            }
            options = menu.get("options") if isinstance(menu.get("options"), list) else []
            if len(options) > 25:
                self.warn(f"{path}.options", "menus can only have 25 options, extra removed")
            roles_used = set()
            for j, option in enumerate(options[:25]):
                opath = f"{path}.options[{j}]"
                option = self.section(option, opath)
                role = self.role(option.get("role"), f"{opath}.role", assignable=True)
                if role is None or role in roles_used:
                    self.warn(opath, "needs a (unique) role, removed")
                    continue
                roles_used.add(role)
                label = self.string(option.get("label"), "", 80, f"{opath}.label")
                emoji = self.string(option.get("emoji"), "", 64, f"{opath}.emoji")
                if not label and not emoji:
                    self.warn(opath, "has no label or emoji, so the role id will be shown")
                clean["options"].append({
                    "role": role,
                    "label": label,
                    "emoji": emoji,
                    "style": self.choice(option.get("style"), BUTTON_STYLES, "secondary", f"{opath}.style"),
                    "description": self.string(option.get("description"), "", 100, f"{opath}.description"),
                })
            out.append(clean)
        return out

    def posts(self, value):
        if not isinstance(value, list):
            if value is not None:
                self.warn("posts", "expected a list")
            return []
        out, seen = [], set()
        for i, post in enumerate(value[:50]):
            path = f"posts[{i}]"
            post = self.section(post, path)
            post_id = self.slug(post.get("id"), f"{path}.id", seen)
            if post_id is None:
                continue
            username = self.string(post.get("username"), "", 80, f"{path}.username")
            if re.search(r"discord|clyde", username, re.IGNORECASE):
                self.warn(f"{path}.username", "webhook names can't contain 'discord' or 'clyde', cleared")
                username = ""
            embeds = post.get("embeds") if isinstance(post.get("embeds"), list) else []
            if len(embeds) > 10:
                self.warn(f"{path}.embeds", "messages can only have 10 embeds, extra removed")
            clean = {
                "id": post_id,
                "channel": self.channel(post.get("channel"), f"{path}.channel"),
                "username": username,
                "avatar_url": self.url(post.get("avatar_url"), f"{path}.avatar_url"),
                "content": self.string(post.get("content"), "", 2000, f"{path}.content"),
                "embeds": [self.embed(e, f"{path}.embeds[{j}]") for j, e in enumerate(embeds[:10])],
                "message_id": self.snowflake(post.get("message_id"), f"{path}.message_id"),
                "posted_channel": self.snowflake(post.get("posted_channel"), f"{path}.posted_channel"),
            }
            if sum(embedLength(e) for e in clean["embeds"]) > 6000:
                self.warn(path, "embeds add up to more than Discord's 6000 character limit - Discord will reject it")
            out.append(clean)
        return out


def embedLength(embed: dict):
    total = sum(len(embed.get(key) or "") for key in ("title", "description", "author_name", "footer"))
    for field in embed.get("fields", []):
        total += len(field.get("name", "")) + len(field.get("value", ""))
    return total

def validateConfig(raw, guild: GuildInfo = None, current: dict = None):
    """
    Rebuild a config from raw JSON (bytes/str/dict), keeping only known keys
    with the right types. Returns (clean_config, warnings). Raises ValueError
    if it can't be read at all. Pass current to carry posted message ids over
    when the import doesn't have them.
    """
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > MAX_IMPORT_BYTES:
            raise ValueError(f"That file is too big (max {MAX_IMPORT_BYTES // 1024} KB).")
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("That file isn't valid UTF-8 text.")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"That file isn't valid JSON ({e.msg} at line {e.lineno}).")
    if not isinstance(raw, dict):
        raise ValueError("That file doesn't look like a Rafisol config (expected a JSON object).")
    schema = raw.get("schema")
    if schema is not None and (not isinstance(schema, int) or schema > SCHEMA_VERSION):
        raise ValueError(f"That config was made for a newer version of Rafisol (schema {schema}).")

    v = Validator(guild)
    meta = raw.get("_meta")
    if guild is not None and isinstance(meta, dict) and meta.get("guild_id") not in (None, guild.guild_id):
        v.warn("_meta.guild_id", "this config was exported from a different server - channels and roles from there were dropped")

    clean = {
        "schema": SCHEMA_VERSION,
        "general": v.general(raw.get("general")),
        "permissions": v.permissions(raw.get("permissions")),
        "moderation": v.moderation(raw.get("moderation")),
        "automod": v.automod(raw.get("automod")),
        "honeypot": v.honeypot(raw.get("honeypot")),
        "logging": v.logging(raw.get("logging")),
        "welcome": v.welcome(raw.get("welcome")),
        "roles": v.roles_section(raw.get("roles")),
        "reaction_roles": v.reaction_roles(raw.get("reaction_roles")),
        "posts": v.posts(raw.get("posts")),
    }

    known = set(clean) | {"_meta"}
    for key in raw:
        if key not in known:
            v.warn(key, "unknown setting, ignored")

    if current:
        # if /rolemenu post or /post send ran after the export, don't lose track of those messages
        for section in ("reaction_roles", "posts"):
            existing = {item["id"]: item for item in current.get(section, [])}
            for item in clean[section]:
                old = existing.get(item["id"])
                if old and item["message_id"] is None and old.get("message_id") and old.get("channel") == item["channel"]:
                    item["message_id"] = old["message_id"]
                    if section == "posts":
                        item["posted_channel"] = old.get("posted_channel")
    return clean, v.warnings

def changedSections(old: dict, new: dict):
    return [key for key in new if key != "schema" and old.get(key) != new.get(key)]

def buildExport(config: dict, guild):
    """Config + a snapshot of the server's channels/roles so the editor can show names instead of IDs."""
    channels = []
    for c in sorted(guild.channels, key=lambda c: (c.category.position if c.category else -1, c.position)):
        channels.append({
            "id": str(c.id),
            "name": c.name,
            "type": str(c.type),
            "category": c.category.name if c.category else None,
        })
    roles = []
    for r in sorted(guild.roles, key=lambda r: -r.position):
        roles.append({
            "id": str(r.id),
            "name": r.name,
            "color": str(r.color) if r.color.value else None,
            "position": r.position,
            "managed": r.managed or r.is_default(),
            "assignable": not r.managed and not r.is_default() and r.position < guild.me.top_role.position,
        })
    out = {
        "schema": SCHEMA_VERSION,
        "_meta": {
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "guild_icon": guild.icon.url if guild.icon else None,
            "exported_at": int(time.time()),
            "channels": channels,
            "roles": roles,
        },
    }
    out.update({key: value for key, value in config.items() if key != "schema"})
    return out
