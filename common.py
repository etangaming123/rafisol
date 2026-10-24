import os
import re
import json
import discord

# change these if you need
version = "1.0.0"
githuburl = "https://github.com/etangaming123/rafisol"
defaulteditorurl = "https://rafisol.etangaming.xyz/editor.html"
defaultinviteurl = "https://discord.com/oauth2/authorize?client_id=1563324610106236938"
statuses = [
    "your server",
    "the audit log",
    "/help",
    "for rule breakers",
]

# embed colours // semantic so logs are readable at a glance
class Colors:
    brand = 0x8649D7
    delete = discord.Color.red()       # deletes, bans, lockdowns
    edit = discord.Color.orange()      # edits, kicks, timeouts, warns
    undo = discord.Color.green()       # unbans, untimeouts, unlocks, joins
    info = discord.Color.blue()        # misc info, voice
    neutral = discord.Color.light_grey()

defaultavatar = "https://cdn.discordapp.com/embed/avatars/0.png"

configpath = "config.json"
sampleconfig = {
    "token": "PUT YOUR BOT TOKEN HERE",
    "editor_url": defaulteditorurl,
    "database_path": "rafisol.db",
}

def loadBotConfig():
    if not os.path.exists(configpath):
        with open(configpath, "w") as f:
            json.dump(sampleconfig, f, indent=4)
        input(f"Created {configpath} with default values. Please edit it (at least the token), then press enter to continue...")
    with open(configpath, "r") as f:
        data = json.load(f)
    # fill in anything missing from older configs
    for key, value in sampleconfig.items():
        data.setdefault(key, value)
    return data

def removeFormatting(string: str): # escape discord formatting characters
    for char in ['\\', '*', '_', '~', '`', '>', '|']:
        string = string.replace(char, f'\\{char}')
    return string

def formatUsername(user: discord.abc.User): # Fancy formatting for usernames // displayname (@username)
    if user.display_name == user.name:
        return removeFormatting(user.name)
    return f"{removeFormatting(user.display_name)} (@{removeFormatting(user.name)})"

def plainUsername(user: discord.abc.User): # same as formatUsername but unescaped, for embed authors/footers where markdown doesn't render
    if user.display_name == user.name:
        return user.name
    return f"{user.display_name} (@{user.name})"

def avatarUrl(user: discord.abc.User):
    return user.display_avatar.url if user.display_avatar else defaultavatar

def truncateMessage(message: str, length: int):
    if message is None:
        return ""
    if len(message) <= length:
        return message
    return message[:length-30] + f"... [{len(message)-length+30} more characters]"

def timestamp(dt, style: str = "R"): # discord timestamp from datetime or unix int
    if dt is None:
        return "unknown"
    seconds = dt if isinstance(dt, (int, float)) else dt.timestamp()
    return f"<t:{int(seconds)}:{style}>"

def ordinal(n: int):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

durationunits = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}

def parseDuration(text: str):
    """Turn "2d1h30m" / "45m" / "1w" into seconds. Returns None if it can't be parsed or is zero."""
    if text is None:
        return None
    text = str(text).strip().lower().replace(" ", "")
    if text == "":
        return None
    if text.isdigit(): # bare number = minutes, same as hvlbot's timeout-custom
        return int(text) * 60 or None
    parts = re.findall(r"(\d+)([wdhms])", text)
    if not parts or "".join(n + u for n, u in parts) != text:
        return None
    total = sum(int(n) * durationunits[u] for n, u in parts)
    return total or None

def formatDuration(seconds: int):
    if not seconds:
        return "permanent"
    out = []
    for unit, size in durationunits.items():
        if seconds >= size:
            amount, seconds = divmod(seconds, size)
            out.append(f"{amount}{unit}")
    return "".join(out)

def toInt(value):
    """Snowflakes are stored as strings in the config (javascript can't hold them as numbers). None if invalid."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def parseColor(value, fallback=Colors.brand):
    if isinstance(value, int):
        return value
    try:
        return discord.Color.from_str(value).value
    except Exception:
        return fallback if isinstance(fallback, int) else fallback.value

def placeholders(member: discord.abc.User | None, guild: discord.Guild | None):
    values = {}
    if member is not None:
        values.update({
            "{user}": formatUsername(member),
            "{user.mention}": member.mention,
            "{user.name}": member.name,
            "{user.display}": member.display_name,
            "{user.id}": str(member.id),
            "{user.avatar}": avatarUrl(member),
            "{user.created}": timestamp(member.created_at, "D"),
        })
    if guild is not None:
        count = guild.member_count or 0
        values.update({
            "{server}": guild.name,
            "{server.id}": str(guild.id),
            "{server.icon}": guild.icon.url if guild.icon else "",
            "{membercount}": str(count),
            "{membercount.ordinal}": ordinal(count),
        })
    return values

def renderTemplate(text: str, member=None, guild=None):
    if not text:
        return text
    for key, value in placeholders(member, guild).items():
        text = text.replace(key, value)
    return text

def embedIsEmpty(data: dict | None):
    if not data:
        return True
    return not any(data.get(key) for key in ("title", "description", "author_name", "footer", "image", "thumbnail", "fields"))

def buildEmbed(data: dict | None, member=None, guild=None, color=Colors.brand):
    """Build a discord.Embed from the config's shared embed format (see config_schema.EMBED_DEFAULT)."""
    if embedIsEmpty(data):
        return None
    r = lambda text: renderTemplate(text, member, guild) or None
    embed = discord.Embed(
        title=r(data.get("title")),
        description=r(data.get("description")),
        url=data.get("url") or None,
        color=parseColor(data.get("color"), color) if data.get("color") else color,
    )
    if data.get("author_name"):
        embed.set_author(name=r(data["author_name"]), icon_url=r(data.get("author_icon")))
    for field in data.get("fields", []):
        if field.get("name") and field.get("value"):
            embed.add_field(name=r(field["name"]), value=r(field["value"]), inline=bool(field.get("inline")))
    if data.get("image"):
        embed.set_image(url=r(data["image"]))
    if data.get("thumbnail"):
        embed.set_thumbnail(url=r(data["thumbnail"]))
    if data.get("footer"):
        embed.set_footer(text=r(data["footer"]), icon_url=r(data.get("footer_icon")))
    if data.get("timestamp"):
        embed.timestamp = discord.utils.utcnow()
    return embed

class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(content="This confirmation isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()

async def reply(interaction: discord.Interaction, content: str = None, ephemeral: bool = True, **kwargs):
    """Respond whether or not the interaction has been deferred yet."""
    if interaction.response.is_done():
        return await interaction.followup.send(content=content, ephemeral=ephemeral, **kwargs)
    return await interaction.response.send_message(content=content, ephemeral=ephemeral, **kwargs)

async def dmUser(user: discord.abc.User, content: str = None, embed: discord.Embed = None):
    """DM a user, returns True if it went through. Closed DMs are normal so we don't complain about them."""
    try:
        await user.send(content=content, embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False
