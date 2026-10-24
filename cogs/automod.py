import re
import time
from collections import defaultdict, deque
import discord
from discord.ext import commands

import permissions
from common import Colors, parseDuration, truncateMessage
from logutils import userEmbed

INVITE = re.compile(r"(?:discord(?:app)?\.com/invite|discord\.gg|discord\.me|dsc\.gg)/([\w-]+)", re.IGNORECASE)
LINK = re.compile(r"https?://([^\s/<>:]+)", re.IGNORECASE)

RULE_NAMES = {
    "words": "Blocked word",
    "invites": "Invite link",
    "links": "Link",
    "mentions": "Mass mentions",
    "spam": "Spam",
    "caps": "Too many caps",
}

def wordPattern(words: tuple):
    # "bad*" = anything starting with bad, otherwise whole words only
    parts = [re.escape(w.lower()).replace(r"\*", r"\S*") for w in words if w.strip()]
    if not parts:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)

class Automod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.patterns = {}                       # guild_id -> (words tuple, compiled)
        self.recent = defaultdict(deque)         # (guild_id, user_id) -> message timestamps
        self.cooldown = {}                       # (guild_id, user_id) -> until, so a burst doesn't get punished 6 times
        self.invites = {}                        # invite code -> guild id (or None if invalid)

    def exempt(self, message: discord.Message, config: dict):
        member = message.author
        if not isinstance(member, discord.Member):
            return True
        if member.guild_permissions.manage_messages or permissions.isMod(member, config):
            return True
        automod = config["automod"]
        if {str(r.id) for r in member.roles} & set(automod["ignored_roles"]):
            return True
        if permissions.channelIds(message.channel) & set(automod["ignored_channels"]):
            return True
        honeypot = config["honeypot"]
        if honeypot["enabled"] and honeypot["channel"] == str(message.channel.id):
            return True # honeypot cog deals with that channel
        return False

    async def inviteGuild(self, code: str):
        if code not in self.invites:
            try:
                invite = await self.bot.fetch_invite(code, with_counts=False)
                self.invites[code] = invite.guild.id if invite.guild else None
            except discord.HTTPException:
                self.invites[code] = None
        return self.invites[code]

    async def check(self, message: discord.Message, rules: dict, guild_id: int):
        """Returns (rule name, detail) for the first rule broken, or None."""
        content = message.content
        if rules["words"]["enabled"] and rules["words"]["list"]:
            words = tuple(rules["words"]["list"])
            cached = self.patterns.get(guild_id)
            if cached is None or cached[0] != words:
                cached = (words, wordPattern(words))
                self.patterns[guild_id] = cached
            if cached[1] and (match := cached[1].search(content)):
                return "words", f"said `{match.group(0)}`"
        if rules["invites"]["enabled"]:
            for code in INVITE.findall(content):
                target = await self.inviteGuild(code)
                if target != guild_id and str(target) not in rules["invites"]["allow_guilds"]:
                    return "invites", f"posted discord.gg/{code}"
        if rules["links"]["enabled"]:
            allowed = rules["links"]["allow_domains"]
            for domain in LINK.findall(content):
                domain = domain.lower().removeprefix("www.")
                if not any(domain == d or domain.endswith("." + d) for d in allowed):
                    return "links", f"linked {domain}"
        if rules["mentions"]["enabled"]:
            count = len(set(message.raw_mentions)) + len(set(message.raw_role_mentions))
            if count > rules["mentions"]["max"]:
                return "mentions", f"{count} mentions"
        if rules["spam"]["enabled"]:
            key = (guild_id, message.author.id)
            now = time.monotonic()
            stamps = self.recent[key]
            stamps.append(now)
            while stamps and now - stamps[0] > rules["spam"]["seconds"]:
                stamps.popleft()
            if len(stamps) >= rules["spam"]["messages"]:
                stamps.clear()
                return "spam", f"{rules['spam']['messages']}+ messages in {rules['spam']['seconds']}s"
        if rules["caps"]["enabled"]:
            letters = [c for c in content if c.isalpha()]
            if len(letters) >= rules["caps"]["min_length"]:
                percent = sum(c.isupper() for c in letters) * 100 // len(letters)
                if percent >= rules["caps"]["percent"]:
                    return "caps", f"{percent}% caps"
        return None

    async def handle(self, message: discord.Message):
        if message.guild is None or message.author.bot or message.webhook_id:
            return
        config = await self.bot.db.getConfig(message.guild.id)
        automod = config["automod"]
        if not automod["enabled"] or self.exempt(message, config):
            return
        result = await self.check(message, automod["rules"], message.guild.id)
        if result is None:
            return
        rule_name, detail = result
        rule = automod["rules"][rule_name]
        action = rule["action"]
        key = (message.guild.id, message.author.id)

        if action != "log":
            try:
                await message.delete()
            except discord.HTTPException:
                pass

        punished = None
        if action in ("warn", "timeout", "mute", "kick", "ban") and self.cooldown.get(key, 0) < time.monotonic():
            self.cooldown[key] = time.monotonic() + 10
            moderation = self.bot.get_cog("Moderation")
            seconds = parseDuration(rule["duration"]) if action in ("timeout", "mute", "ban") else None
            try:
                case_no, _ = await moderation.punish(message.guild, message.author, message.guild.me, action, f"Automod: {RULE_NAMES[rule_name]} ({detail})", seconds)
                punished = f"{action} (case #{case_no})"
            except discord.HTTPException as e:
                punished = f"couldn't {action}: {e.text}"

        if action != "log":
            try:
                await message.channel.send(content=f"{message.author.mention}, your message was removed: **{RULE_NAMES[rule_name]}**.", delete_after=6, allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass

        # log it
        embed = userEmbed(f"Automod: {RULE_NAMES[rule_name]}", message.author, Colors.edit, f"{message.author.mention} in {message.channel.mention} - {detail}")
        if message.content:
            embed.add_field(name="Message", value=truncateMessage(message.content, 1024), inline=False)
        embed.add_field(name="Action", value=punished or ("logged only" if action == "log" else "message deleted"))
        channel_id = automod["log_channel"] or config["logging"]["channels"]["moderation"]
        channel = message.guild.get_channel_or_thread(int(channel_id)) if channel_id else None
        if channel:
            self.bot.webhooks.log(channel, embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.handle(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content != after.content:
            await self.handle(after)

async def setup(bot):
    await bot.add_cog(Automod(bot))
