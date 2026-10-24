"""Shared bits for the logging cogs: where a log goes and whether it should be sent at all."""

import discord

import config_schema
from common import plainUsername, avatarUrl
from permissions import channelIds

def logChannel(guild: discord.Guild, config: dict, category: str):
    channel_id = config["logging"]["channels"].get(category)
    return guild.get_channel_or_thread(int(channel_id)) if channel_id else None

def shouldLog(config: dict, event: str, channel=None, member=None):
    logging = config["logging"]
    if not logging["events"].get(event, True):
        return False
    category = config_schema.LOG_EVENTS[event][0]
    if not logging["channels"].get(category):
        return False
    if channel is not None and channelIds(channel) & set(logging["ignored_channels"]):
        return False
    if member is not None:
        if logging["ignore_bots"] and member.bot:
            return False
        if isinstance(member, discord.Member) and {str(r.id) for r in member.roles} & set(logging["ignored_roles"]):
            return False
    return True

async def sendLog(bot, guild: discord.Guild, event: str, embed: discord.Embed, file: discord.File = None, channel=None, member=None):
    """Check the event is wanted, then queue it for the right log channel."""
    config = await bot.db.getConfig(guild.id)
    if not shouldLog(config, event, channel, member):
        return
    target = logChannel(guild, config, config_schema.LOG_EVENTS[event][0])
    if target is None:
        return
    if channel is not None and target.id == channel.id and event.startswith("message"):
        return # don't log deletes/edits of the log channel itself, that way lies loops
    bot.webhooks.log(target, embed, file)

def userEmbed(title: str, user: discord.abc.User, color, description: str = None):
    embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    embed.set_author(name=plainUsername(user), icon_url=avatarUrl(user))
    embed.set_footer(text=f"User ID: {user.id}")
    return embed
