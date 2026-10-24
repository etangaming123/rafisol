import time
import discord
from discord.ext import commands

from common import Colors, formatDuration
from logutils import sendLog, userEmbed

class VoiceLog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.joined = {} # (guild_id, member_id) -> when they joined their current channel

    def spent(self, member: discord.Member):
        started = self.joined.pop((member.guild.id, member.id), None)
        if not started:
            return ""
        seconds = int(time.time() - started)
        return f"\n-# was there for {formatDuration(seconds) if seconds else '0s'}"

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        key = (guild.id, member.id)

        if before.channel is None and after.channel is not None:
            self.joined[key] = time.time()
            embed = userEmbed("Joined Voice Channel", member, Colors.undo, f"{member.mention} joined {after.channel.mention}")
            await sendLog(self.bot, guild, "voice_join", embed, channel=after.channel, member=member)
            return
        if before.channel is not None and after.channel is None:
            embed = userEmbed("Left Voice Channel", member, Colors.delete, f"{member.mention} left {before.channel.mention}{self.spent(member)}")
            await sendLog(self.bot, guild, "voice_leave", embed, channel=before.channel, member=member)
            return
        if before.channel != after.channel:
            embed = userEmbed("Moved Voice Channel", member, Colors.info, f"{member.mention} moved from {before.channel.mention} to {after.channel.mention}{self.spent(member)}")
            self.joined[key] = time.time()
            await sendLog(self.bot, guild, "voice_move", embed, channel=after.channel, member=member)
            return

        channel = after.channel
        changes = []
        if before.mute != after.mute:
            changes.append(("voice_server_mute", "Server muted" if after.mute else "Server unmuted"))
        if before.deaf != after.deaf:
            changes.append(("voice_server_mute", "Server deafened" if after.deaf else "Server undeafened"))
        if before.self_mute != after.self_mute:
            changes.append(("voice_self_mute", "Muted themselves" if after.self_mute else "Unmuted themselves"))
        if before.self_deaf != after.self_deaf:
            changes.append(("voice_self_mute", "Deafened themselves" if after.self_deaf else "Undeafened themselves"))
        if before.self_stream != after.self_stream:
            changes.append(("voice_stream", "Started streaming" if after.self_stream else "Stopped streaming"))
        if before.self_video != after.self_video:
            changes.append(("voice_stream", "Turned their camera on" if after.self_video else "Turned their camera off"))
        for event, text in changes:
            server_side = event == "voice_server_mute"
            embed = userEmbed("Voice State Changed", member, Colors.edit if server_side else Colors.info, f"{member.mention}: **{text}** in {channel.mention}")
            await sendLog(self.bot, guild, event, embed, channel=channel, member=member)

async def setup(bot):
    await bot.add_cog(VoiceLog(bot))
