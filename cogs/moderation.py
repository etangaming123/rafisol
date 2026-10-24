import time
import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks

import common
import permissions
from common import Colors, formatUsername, plainUsername, timestamp, parseDuration, formatDuration

MAX_TIMEOUT = 28 * 86400

ACTIONS = {
    # action: (past tense for dms/messages, colour)
    "warn":      ("warned", Colors.edit),
    "timeout":   ("timed out", Colors.edit),
    "untimeout": ("un-timed out", Colors.undo),
    "mute":      ("muted", Colors.edit),
    "unmute":    ("unmuted", Colors.undo),
    "kick":      ("kicked", Colors.edit),
    "softban":   ("softbanned", Colors.delete),
    "ban":       ("banned", Colors.delete),
    "unban":     ("unbanned", Colors.undo),
}
DM_ACTIONS = {"warn", "timeout", "mute", "kick", "softban", "ban"}

def caseEmbed(guild: discord.Guild, case_no: int, action: str, user: discord.abc.User | int, moderator: discord.abc.User | int, reason: str = None, duration: int = None, created_at: int = None, active: bool = True):
    past, color = ACTIONS.get(action, (action, Colors.neutral))
    embed = discord.Embed(title=f"Case #{case_no} | {action.capitalize()}", color=color if active else Colors.neutral, timestamp=datetime.datetime.fromtimestamp(created_at or time.time(), datetime.timezone.utc))
    if isinstance(user, int):
        embed.add_field(name="User", value=f"<@{user}> ({user})")
    else:
        embed.add_field(name="User", value=f"{user.mention} ({formatUsername(user)})")
        embed.set_thumbnail(url=common.avatarUrl(user))
    if isinstance(moderator, int):
        embed.add_field(name="Moderator", value=f"<@{moderator}>")
    else:
        embed.add_field(name="Moderator", value=f"{moderator.mention} ({formatUsername(moderator)})")
    if duration:
        expires = (created_at or int(time.time())) + duration
        embed.add_field(name="Duration", value=f"{formatDuration(duration)} (ends {timestamp(expires)})")
    embed.add_field(name="Reason", value=common.truncateMessage(reason or "No reason provided.", 1024), inline=False)
    user_id = user if isinstance(user, int) else user.id
    embed.set_footer(text=f"User ID: {user_id}" + ("" if active else " • voided"))
    return embed

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        self.scheduler.cancel()

    # ---- core, also used by automod / cases / serverlog

    async def logCase(self, guild: discord.Guild, embed: discord.Embed):
        config = await self.bot.db.getConfig(guild.id)
        channel_id = config["logging"]["channels"]["moderation"]
        channel = guild.get_channel_or_thread(int(channel_id)) if channel_id else None
        if channel:
            self.bot.webhooks.log(channel, embed)

    async def recordCase(self, guild, action, user, moderator, reason=None, duration=None):
        case_no = await self.bot.db.addCase(guild.id, action, user.id, moderator.id, reason, duration)
        await self.logCase(guild, caseEmbed(guild, case_no, action, user, moderator, reason, duration))
        return case_no

    async def getMuteRole(self, guild: discord.Guild, create: bool = True):
        config = await self.bot.db.getConfig(guild.id)
        role = guild.get_role(common.toInt(config["moderation"]["mute_role"]) or 0)
        if role or not create:
            return role
        # no mute role yet, make one and deny talking everywhere
        role = await guild.create_role(name="Muted", color=discord.Color.dark_grey(), reason="Rafisol mute role")
        overwrite = discord.PermissionOverwrite(send_messages=False, send_messages_in_threads=False, create_public_threads=False, create_private_threads=False, add_reactions=False, speak=False, stream=False)
        for channel in guild.channels:
            if isinstance(channel, discord.CategoryChannel) or channel.category is None or not channel.permissions_synced:
                try:
                    await channel.set_permissions(role, overwrite=overwrite, reason="Rafisol mute role")
                except discord.HTTPException:
                    pass
        config = await self.bot.db.editConfig(guild.id)
        config["moderation"]["mute_role"] = str(role.id)
        await self.bot.db.saveConfig(guild.id, config, history=False)
        return role

    async def punish(self, guild: discord.Guild, user: discord.abc.User, moderator: discord.abc.User, action: str, reason: str = None, duration: int = None, dm: bool = None, delete_seconds: int = 0):
        """Do a moderation action, DM the user, open a case and log it. Returns (case_no, extra info for the reply)."""
        config = await self.bot.db.getConfig(guild.id)
        member = user if isinstance(user, discord.Member) else guild.get_member(user.id)
        dm = config["moderation"]["dm_on_action"] if dm is None else dm
        audit_reason = f"{plainUsername(moderator)}: {reason or 'No reason provided.'}"[:512]
        notes = []

        dmed = False
        if dm and action in DM_ACTIONS and member is not None:
            past = ACTIONS[action][0]
            embed = discord.Embed(title=f"You were {past} in {guild.name}", color=ACTIONS[action][1], timestamp=discord.utils.utcnow())
            embed.add_field(name="Reason", value=common.truncateMessage(reason or "No reason provided.", 1024), inline=False)
            if duration:
                embed.add_field(name="Duration", value=f"{formatDuration(duration)} (ends {timestamp(int(time.time()) + duration)})", inline=False)
            if config["moderation"]["dm_extra"]:
                embed.description = config["moderation"]["dm_extra"]
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            dmed = await common.dmUser(member, embed=embed)
            if not dmed:
                notes.append("couldn't DM them")

        if action == "timeout":
            duration = min(duration or 3600, MAX_TIMEOUT)
            await member.timeout(datetime.timedelta(seconds=duration), reason=audit_reason)
        elif action == "untimeout":
            await member.timeout(None, reason=audit_reason)
        elif action == "mute":
            role = await self.getMuteRole(guild)
            await member.add_roles(role, reason=audit_reason)
            if duration:
                await self.bot.db.schedule(guild.id, user.id, "unmute", int(time.time()) + duration)
            else:
                await self.bot.db.unschedule(guild.id, user.id, "unmute")
        elif action == "unmute":
            role = await self.getMuteRole(guild, create=False)
            if role and member and role in member.roles:
                await member.remove_roles(role, reason=audit_reason)
            await self.bot.db.unschedule(guild.id, user.id, "unmute")
        elif action == "kick":
            await member.kick(reason=audit_reason)
        elif action == "ban":
            await guild.ban(user, reason=audit_reason, delete_message_seconds=delete_seconds)
            if duration:
                await self.bot.db.schedule(guild.id, user.id, "unban", int(time.time()) + duration)
            else:
                await self.bot.db.unschedule(guild.id, user.id, "unban")
        elif action == "softban":
            await guild.ban(user, reason=audit_reason, delete_message_seconds=delete_seconds or 86400)
            await guild.unban(user, reason=f"{audit_reason} (softban)"[:512])
        elif action == "unban":
            await guild.unban(user, reason=audit_reason)
            await self.bot.db.unschedule(guild.id, user.id, "unban")

        case_no = await self.recordCase(guild, action, user, moderator, reason, duration if action in ("timeout", "mute", "ban") else None)

        if action == "warn":
            count = await self.bot.db.activeWarnCount(guild.id, user.id)
            notes.append(f"they now have {count} warning{'s' if count != 1 else ''}")
            for threshold in config["moderation"]["warn_thresholds"]:
                if threshold["count"] == count and member is not None:
                    escalate = threshold["action"]
                    seconds = parseDuration(threshold["duration"]) if escalate in ("timeout", "mute", "ban") else None
                    try:
                        extra_case, _ = await self.punish(guild, member, guild.me, escalate, f"Reached {count} warnings", seconds, dm=dm)
                        notes.append(f"auto-{ACTIONS[escalate][0]} (case #{extra_case})")
                    except discord.HTTPException as e:
                        notes.append(f"couldn't auto-{escalate}: {e.text}")
                    break
        return case_no, notes

    async def checkTarget(self, interaction: discord.Interaction, user: discord.abc.User, reason: str):
        """Shared checks before an action. Returns an error message, or None if it's fine to go ahead."""
        config = await self.bot.db.getConfig(interaction.guild.id)
        if config["moderation"]["require_reason"] and not reason:
            return "A reason is required for moderation actions in this server."
        if user.id == self.bot.user.id:
            return "Nice try."
        member = user if isinstance(user, discord.Member) else interaction.guild.get_member(user.id)
        if member is not None:
            ok, why = permissions.canTarget(interaction.user, member, config)
            if not ok:
                return why
        return None

    async def run(self, interaction: discord.Interaction, user, action: str, reason: str = None, duration: int = None, dm: bool = None, delete_seconds: int = 0, needs_member: bool = True):
        await interaction.response.defer(ephemeral=True)
        if needs_member and not isinstance(user, discord.Member):
            await interaction.followup.send(content="That user isn't in this server.", ephemeral=True)
            return
        error = await self.checkTarget(interaction, user, reason)
        if error:
            await interaction.followup.send(content=error, ephemeral=True)
            return
        try:
            case_no, notes = await self.punish(interaction.guild, user, interaction.user, action, reason, duration, dm, delete_seconds)
        except discord.Forbidden:
            await interaction.followup.send(content="I don't have permission to do that! Check my role is above theirs and has the right permissions.", ephemeral=True)
            return
        except discord.NotFound:
            await interaction.followup.send(content="Discord couldn't find that user (or they aren't banned).", ephemeral=True)
            return
        text = f"**{formatUsername(user)}** was {ACTIONS[action][0]}"
        if duration and action in ("timeout", "mute", "ban"):
            text += f" for {formatDuration(min(duration, MAX_TIMEOUT) if action == 'timeout' else duration)}"
        text += f". (case #{case_no})"
        if notes:
            text += f"\n-# {', '.join(notes)}"
        await interaction.followup.send(content=text, ephemeral=True)

    def readDuration(self, text):
        if text in (None, ""):
            return None, None
        seconds = parseDuration(text)
        if seconds is None:
            return None, f"Couldn't read `{text}` as a duration. Try something like `30m`, `2h`, `1d12h` or `1w`."
        return seconds, None

    # ---- commands

    @app_commands.command(name="ban", description="Ban a user (works on people who aren't in the server too).")
    @app_commands.describe(user="The user to ban.", reason="Why (shows in their DM and the case).", duration="How long, e.g. 7d (leave empty for permanent).", delete_messages="How much of their recent message history to delete.", dm="DM them about it (defaults to the server setting).")
    @app_commands.choices(delete_messages=[
        app_commands.Choice(name="Don't delete any", value=0),
        app_commands.Choice(name="Last hour", value=3600),
        app_commands.Choice(name="Last 24 hours", value=86400),
        app_commands.Choice(name="Last 3 days", value=259200),
        app_commands.Choice(name="Last 7 days", value=604800),
    ])
    async def ban(self, interaction: discord.Interaction, user: discord.User, reason: str = None, duration: str = None, delete_messages: int = 0, dm: bool = None):
        seconds, error = self.readDuration(duration)
        if error:
            await interaction.response.send_message(content=error, ephemeral=True)
            return
        await self.run(interaction, user, "ban", reason, seconds, dm, delete_messages, needs_member=False)

    @app_commands.command(name="unban", description="Unban a user.")
    @app_commands.describe(user="The user (or their ID) to unban.", reason="Why.")
    async def unban(self, interaction: discord.Interaction, user: discord.User, reason: str = None):
        await self.run(interaction, user, "unban", reason, needs_member=False)

    @app_commands.command(name="softban", description="Ban then instantly unban someone to wipe their recent messages.")
    @app_commands.describe(user="The member to softban.", reason="Why.", dm="DM them about it.")
    async def softban(self, interaction: discord.Interaction, user: discord.User, reason: str = None, dm: bool = None):
        await self.run(interaction, user, "softban", reason, dm=dm, delete_seconds=86400, needs_member=False)

    @app_commands.command(name="kick", description="Kick a member.")
    @app_commands.describe(user="The member to kick.", reason="Why.", dm="DM them about it.")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = None, dm: bool = None):
        await self.run(interaction, user, "kick", reason, dm=dm)

    @app_commands.command(name="timeout", description="Time out a member (max 28 days).")
    @app_commands.describe(user="The member to time out.", duration="How long, e.g. 10m, 1h, 1d.", reason="Why.", dm="DM them about it.")
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str = None, dm: bool = None):
        seconds, error = self.readDuration(duration)
        if error or seconds is None:
            await interaction.response.send_message(content=error or "You need a duration!", ephemeral=True)
            return
        await self.run(interaction, user, "timeout", reason, seconds, dm)

    @app_commands.command(name="untimeout", description="Remove a member's timeout.")
    @app_commands.describe(user="The member.", reason="Why.")
    async def untimeout(self, interaction: discord.Interaction, user: discord.Member, reason: str = None):
        if not user.is_timed_out():
            await interaction.response.send_message(content="They aren't timed out.", ephemeral=True)
            return
        await self.run(interaction, user, "untimeout", reason)

    @app_commands.command(name="mute", description="Give a member the mute role (unlike timeouts, this can be permanent).")
    @app_commands.describe(user="The member to mute.", duration="How long (leave empty for permanent).", reason="Why.", dm="DM them about it.")
    async def mute(self, interaction: discord.Interaction, user: discord.Member, duration: str = None, reason: str = None, dm: bool = None):
        seconds, error = self.readDuration(duration)
        if error:
            await interaction.response.send_message(content=error, ephemeral=True)
            return
        await self.run(interaction, user, "mute", reason, seconds, dm)

    @app_commands.command(name="unmute", description="Remove the mute role from a member.")
    @app_commands.describe(user="The member.", reason="Why.")
    async def unmute(self, interaction: discord.Interaction, user: discord.Member, reason: str = None):
        await self.run(interaction, user, "unmute", reason)

    @app_commands.command(name="warn", description="Warn a member. Warnings can trigger automatic punishments (set in the editor).")
    @app_commands.describe(user="The member to warn.", reason="Why.", dm="DM them about it.")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = None, dm: bool = None):
        await self.run(interaction, user, "warn", reason, dm=dm)

    @app_commands.command(name="clearwarns", description="Clear all of a member's active warnings.")
    @app_commands.describe(user="The member.")
    async def clearwarns(self, interaction: discord.Interaction, user: discord.User):
        count = await self.bot.db.clearWarns(interaction.guild.id, user.id)
        await interaction.response.send_message(content=f"Cleared {count} warning{'s' if count != 1 else ''} from **{formatUsername(user)}**.", ephemeral=True)

    @app_commands.command(name="purge", description="Bulk delete recent messages in this channel.")
    @app_commands.describe(amount="How many messages to look through (1-1000).", user="Only delete messages from this user.", contains="Only delete messages containing this text.", bots="Only delete messages from bots.")
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000], user: discord.User = None, contains: str = None, bots: bool = False):
        await interaction.response.defer(ephemeral=True)
        def check(message: discord.Message):
            if message.pinned:
                return False
            if user and message.author.id != user.id:
                return False
            if contains and contains.lower() not in message.content.lower():
                return False
            if bots and not message.author.bot:
                return False
            return True
        # skip the "thinking" message we just made
        deleted = await interaction.channel.purge(limit=amount, check=check, before=discord.Object(id=interaction.id), reason=f"/purge by {plainUsername(interaction.user)}")
        await interaction.followup.send(content=f"Deleted {len(deleted)} message{'s' if len(deleted) != 1 else ''}." + ("\n-# messages older than 14 days can't be bulk deleted." if len(deleted) < amount and not (user or contains or bots) else ""), ephemeral=True)

    # ---- lockdown

    LOCK_PERMS = ("send_messages", "send_messages_in_threads", "create_public_threads", "create_private_threads", "add_reactions", "connect")

    async def lockChannel(self, channel, reason: str):
        everyone = channel.guild.default_role
        overwrite = channel.overwrites_for(everyone)
        if channel.id in await self.bot.db.lockedChannels(channel.guild.id):
            return False # already locked, keep the original state we saved
        previous = {perm: getattr(overwrite, perm) for perm in self.LOCK_PERMS}
        for perm in self.LOCK_PERMS:
            if perm == "connect" and not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                continue
            setattr(overwrite, perm, False)
        await channel.set_permissions(everyone, overwrite=overwrite, reason=reason)
        await self.bot.db.saveLockdown(channel.guild.id, channel.id, previous)
        return True

    async def unlockChannel(self, channel, reason: str):
        locked, previous = await self.bot.db.popLockdown(channel.guild.id, channel.id)
        if not locked:
            return False
        everyone = channel.guild.default_role
        overwrite = channel.overwrites_for(everyone)
        for perm, value in previous.items():
            setattr(overwrite, perm, value)
        await channel.set_permissions(everyone, overwrite=None if overwrite.is_empty() else overwrite, reason=reason)
        return True

    async def lockTargets(self, guild: discord.Guild, config: dict):
        ids = config["moderation"]["lockdown_channels"]
        if ids:
            return [c for c in (guild.get_channel(int(i)) for i in ids) if c]
        # nothing configured, lock every text channel @everyone can currently talk in
        everyone = guild.default_role
        return [c for c in guild.text_channels if c.permissions_for(everyone).send_messages and c.permissions_for(everyone).view_channel]

    @app_commands.command(name="lockdown", description="Stop @everyone from talking in a channel (or the whole server).")
    @app_commands.describe(channel="The channel to lock (defaults to this one).", server="Lock every lockdown channel instead (set in the editor).", duration="Unlock automatically after this long.", reason="Why (shown in the channel).")
    async def lockdown(self, interaction: discord.Interaction, channel: discord.TextChannel = None, server: bool = False, duration: str = None, reason: str = None):
        seconds, error = self.readDuration(duration)
        if error:
            await interaction.response.send_message(content=error, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        config = await self.bot.db.getConfig(interaction.guild.id)
        targets = await self.lockTargets(interaction.guild, config) if server else [channel or interaction.channel]
        audit = f"Lockdown by {plainUsername(interaction.user)}: {reason or 'No reason provided.'}"[:512]
        embed = discord.Embed(title="🔒 Channel locked", description=config["moderation"]["lockdown_message"], color=Colors.delete)
        if reason:
            embed.add_field(name="Reason", value=reason[:1024])
        if seconds:
            embed.add_field(name="Unlocks", value=timestamp(int(time.time()) + seconds))
        done, skipped = [], 0
        for target in targets:
            try:
                if await self.lockChannel(target, audit):
                    done.append(target)
                    if hasattr(target, "send"):
                        await target.send(embed=embed)
                    if seconds:
                        await self.bot.db.schedule(interaction.guild.id, target.id, "unlock", int(time.time()) + seconds)
                else:
                    skipped += 1
            except discord.HTTPException:
                skipped += 1
        log = discord.Embed(title="Lockdown", description=" ".join(c.mention for c in done)[:4000] or "nothing", color=Colors.delete, timestamp=discord.utils.utcnow())
        log.add_field(name="Moderator", value=f"{interaction.user.mention} ({formatUsername(interaction.user)})")
        log.add_field(name="Reason", value=reason or "No reason provided.")
        if seconds:
            log.add_field(name="Duration", value=formatDuration(seconds))
        await self.logCase(interaction.guild, log)
        text = f"Locked {len(done)} channel{'s' if len(done) != 1 else ''}."
        if skipped:
            text += f" ({skipped} skipped - already locked or missing permissions)"
        if server and not config["moderation"]["lockdown_channels"]:
            text += "\n-# No lockdown channels are set, so every public text channel was locked. Pick specific ones in the editor."
        await interaction.followup.send(content=text, ephemeral=True)

    @app_commands.command(name="unlock", description="Undo a lockdown.")
    @app_commands.describe(channel="The channel to unlock (defaults to this one).", server="Unlock every channel Rafisol locked.", reason="Why.")
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None, server: bool = False, reason: str = None):
        await interaction.response.defer(ephemeral=True)
        if server:
            ids = await self.bot.db.lockedChannels(interaction.guild.id)
            targets = [c for c in (interaction.guild.get_channel(i) for i in ids) if c]
        else:
            targets = [channel or interaction.channel]
        audit = f"Unlock by {plainUsername(interaction.user)}: {reason or 'No reason provided.'}"[:512]
        done = []
        for target in targets:
            try:
                if await self.unlockChannel(target, audit):
                    done.append(target)
                    await self.bot.db.unschedule(interaction.guild.id, target.id, "unlock")
                    if hasattr(target, "send"):
                        await target.send(embed=discord.Embed(title="🔓 Channel unlocked", color=Colors.undo))
            except discord.HTTPException:
                pass
        if not done:
            await interaction.followup.send(content="Nothing to unlock (Rafisol only unlocks channels it locked).", ephemeral=True)
            return
        log = discord.Embed(title="Unlock", description=" ".join(c.mention for c in done)[:4000], color=Colors.undo, timestamp=discord.utils.utcnow())
        log.add_field(name="Moderator", value=f"{interaction.user.mention} ({formatUsername(interaction.user)})")
        await self.logCase(interaction.guild, log)
        await interaction.followup.send(content=f"Unlocked {len(done)} channel{'s' if len(done) != 1 else ''}.", ephemeral=True)

    @app_commands.command(name="slowmode", description="Set this channel's slowmode.")
    @app_commands.describe(duration="e.g. 5s, 1m, 2h (0 or off to disable, max 6h).", channel="The channel (defaults to this one).")
    async def slowmode(self, interaction: discord.Interaction, duration: str, channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        if duration.lower() in ("0", "off", "none"):
            seconds = 0
        else:
            seconds = parseDuration(duration if not duration.isdigit() else f"{duration}s")
            if seconds is None or seconds > 21600:
                await interaction.response.send_message(content="Slowmode has to be between 1 second and 6 hours (e.g. `10s`, `5m`).", ephemeral=True)
                return
        await channel.edit(slowmode_delay=seconds, reason=f"/slowmode by {plainUsername(interaction.user)}")
        await interaction.response.send_message(content=f"Slowmode in {channel.mention} is now {formatDuration(seconds) if seconds else 'off'}.", ephemeral=True)

    @app_commands.command(name="nick", description="Change (or reset) a member's nickname.")
    @app_commands.describe(user="The member.", nickname="The new nickname (leave empty to reset).")
    async def nick(self, interaction: discord.Interaction, user: discord.Member, nickname: app_commands.Range[str, 1, 32] = None):
        config = await self.bot.db.getConfig(interaction.guild.id)
        if user.id != interaction.user.id:
            ok, why = permissions.canTarget(interaction.user, user, config)
            if not ok:
                await interaction.response.send_message(content=why, ephemeral=True)
                return
        await user.edit(nick=nickname, reason=f"/nick by {plainUsername(interaction.user)}")
        await interaction.response.send_message(content=f"{'Changed' if nickname else 'Reset'} **{formatUsername(user)}**'s nickname.", ephemeral=True)

    # ---- temp actions

    @tasks.loop(seconds=30)
    async def scheduler(self):
        for row in await self.bot.db.dueActions(int(time.time())):
            guild = self.bot.get_guild(row["guild_id"])
            await self.bot.db.deleteScheduled(row["id"])
            if guild is None:
                continue
            try:
                if row["action"] == "unban":
                    user = discord.Object(id=row["target_id"])
                    await guild.unban(user, reason="Temporary ban expired")
                    case_no = await self.bot.db.addCase(guild.id, "unban", row["target_id"], self.bot.user.id, "Temporary ban expired")
                    await self.logCase(guild, caseEmbed(guild, case_no, "unban", row["target_id"], self.bot.user, "Temporary ban expired"))
                elif row["action"] == "unmute":
                    member = guild.get_member(row["target_id"])
                    role = await self.getMuteRole(guild, create=False)
                    if member and role and role in member.roles:
                        await member.remove_roles(role, reason="Temporary mute expired")
                        case_no = await self.bot.db.addCase(guild.id, "unmute", member.id, self.bot.user.id, "Temporary mute expired")
                        await self.logCase(guild, caseEmbed(guild, case_no, "unmute", member, self.bot.user, "Temporary mute expired"))
                elif row["action"] == "unlock":
                    channel = guild.get_channel(row["target_id"])
                    if channel and await self.unlockChannel(channel, "Timed lockdown ended"):
                        await channel.send(embed=discord.Embed(title="🔓 Channel unlocked", description="The lockdown timer ran out.", color=Colors.undo))
            except discord.HTTPException as e:
                print(f"Scheduled {row['action']} for {row['target_id']} in {guild.id} failed: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.scheduler.is_running():
            self.scheduler.start()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # rejoining doesn't get you out of a mute
        last = await self.bot.db.fetchone(
            "SELECT action, duration, created_at FROM cases WHERE guild_id = ? AND user_id = ? AND action IN ('mute', 'unmute') AND active = 1 ORDER BY case_no DESC LIMIT 1",
            (member.guild.id, member.id),
        )
        if last is None or last["action"] != "mute":
            return
        if last["duration"] and last["created_at"] + last["duration"] <= time.time():
            return # temp mute ran out while they were gone
        role = await self.getMuteRole(member.guild, create=False)
        if role and role < member.guild.me.top_role:
            try:
                await member.add_roles(role, reason="Still muted (rejoined)")
            except discord.HTTPException:
                pass

async def setup(bot):
    await bot.add_cog(Moderation(bot))
