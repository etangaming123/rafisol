import discord
from discord.ext import commands

from common import Colors, truncateMessage, timestamp
from logutils import sendLog, userEmbed
from webhooks import textFile

def describeAttachments(message: discord.Message):
    lines = [f"[{a.filename}]({a.proxy_url})" for a in message.attachments]
    lines += [f"Sticker: {s.name}" for s in message.stickers]
    return "\n".join(lines)

class MessageLog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel_or_thread(payload.channel_id) if guild else None
        if channel is None:
            return
        message = payload.cached_message
        if message is None:
            embed = discord.Embed(title="Message Deleted", description=f"A message was deleted in {channel.mention}.\n-# content not cached (sent before Rafisol last restarted, or too old).", color=Colors.delete, timestamp=discord.utils.utcnow())
            embed.set_footer(text=f"Message ID: {payload.message_id}")
            await sendLog(self.bot, guild, "message_delete", embed, channel=channel)
            return
        if message.type not in (discord.MessageType.default, discord.MessageType.reply) and not message.content:
            return # joins, pins, boosts etc
        embed = userEmbed("Message Deleted", message.author, Colors.delete, f"**Sent by {message.author.mention} in {channel.mention}** {timestamp(message.created_at)}")
        file = None
        if message.content:
            if len(message.content) > 3800:
                file = textFile(message.content)
            embed.description += "\n\n" + truncateMessage(message.content, 3800)
        attachments = describeAttachments(message)
        if attachments:
            embed.add_field(name="Attachments", value=truncateMessage(attachments, 1024), inline=False)
        if message.reference and message.reference.message_id:
            embed.add_field(name="Replying to", value=f"[Jump](https://discord.com/channels/{guild.id}/{message.reference.channel_id}/{message.reference.message_id})")
        embed.set_footer(text=f"User ID: {message.author.id} • Message ID: {message.id}")
        await sendLog(self.bot, guild, "message_delete", embed, file, channel=channel, member=message.author)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel_or_thread(payload.channel_id) if guild else None
        if channel is None:
            return
        cached = sorted(payload.cached_messages, key=lambda m: m.created_at)
        lines = []
        for message in cached:
            line = f"[{message.created_at:%Y-%m-%d %H:%M:%S}] {message.author} ({message.author.id}): {message.content}"
            for attachment in message.attachments:
                line += f"\n    attachment: {attachment.url}"
            lines.append(line)
        missing = len(payload.message_ids) - len(cached)
        if missing:
            lines.append(f"\n{missing} message(s) weren't cached, so their content isn't available.")
        embed = discord.Embed(title="Messages Bulk Deleted", description=f"**{len(payload.message_ids)} messages** deleted in {channel.mention}.", color=Colors.delete, timestamp=discord.utils.utcnow())
        if cached:
            authors = {}
            for message in cached:
                authors[message.author.mention] = authors.get(message.author.mention, 0) + 1
            embed.add_field(name="Authors", value=truncateMessage(", ".join(f"{a} ({n})" for a, n in authors.items()), 1024), inline=False)
        await sendLog(self.bot, guild, "message_bulk_delete", embed, textFile("\n".join(lines), f"deleted-{channel.id}.txt"), channel=channel)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild is None or before.content == after.content:
            return # embeds loading in also fire edits
        embed = userEmbed("Message Edited", after.author, Colors.edit, f"**{after.author.mention} edited a message in {after.channel.mention}** [Jump to message]({after.jump_url})")
        file = None
        if len(before.content) > 1024 or len(after.content) > 1024:
            file = textFile(f"--- before ---\n{before.content}\n\n--- after ---\n{after.content}", "edit.txt")
        embed.add_field(name="Before", value=truncateMessage(before.content, 1024) or "*empty*", inline=False)
        embed.add_field(name="After", value=truncateMessage(after.content, 1024) or "*empty*", inline=False)
        embed.set_footer(text=f"User ID: {after.author.id} • Message ID: {after.id}")
        await sendLog(self.bot, after.guild, "message_edit", embed, file, channel=after.channel, member=after.author)

async def setup(bot):
    await bot.add_cog(MessageLog(bot))
