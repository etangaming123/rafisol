"""
Webhook handling for logs and /post. Rafisol keeps one webhook per channel
(created on first use, stored in the database, never exported), and log
embeds are queued per channel and sent in bundles of up to 10, so a raid or
a big purge doesn't run straight into webhook rate limits.
"""

import io
import asyncio
import discord

WEBHOOK_NAME = "Rafisol"
LOG_USERNAME = "Rafisol Logs"
FLUSH_DELAY = 1.5 # seconds to wait for more embeds before sending a bundle

class WebhookUnavailable(Exception):
    pass

def embedSize(embed: discord.Embed):
    return len(embed)

class WebhookManager:
    def __init__(self, bot):
        self.bot = bot
        self.cache = {}   # channel_id -> discord.Webhook
        self.queues = {}  # channel_id -> list of (embed, file)
        self.flushers = {}
        self.locks = {}

    def baseChannel(self, channel):
        # threads don't have their own webhooks, they go through the parent
        if isinstance(channel, discord.Thread):
            return channel.parent, channel
        return channel, None

    async def get(self, channel, create: bool = True):
        base, _ = self.baseChannel(channel)
        if base is None or not hasattr(base, "create_webhook"):
            return None
        if base.id in self.cache:
            return self.cache[base.id]
        lock = self.locks.setdefault(base.id, asyncio.Lock())
        async with lock: # two logs at once shouldn't make two webhooks
            if base.id in self.cache:
                return self.cache[base.id]
            row = await self.bot.db.getWebhook(base.id)
            if row:
                webhook = discord.Webhook.partial(row["webhook_id"], row["token"], client=self.bot)
                self.cache[base.id] = webhook
                return webhook
            if not create or not base.permissions_for(base.guild.me).manage_webhooks:
                return None
            try:
                webhook = None
                for existing in await base.webhooks():
                    if existing.user and existing.user.id == self.bot.user.id and existing.token:
                        webhook = existing
                        break
                if webhook is None:
                    avatar = await self.bot.user.display_avatar.read()
                    webhook = await base.create_webhook(name=WEBHOOK_NAME, avatar=avatar, reason="Rafisol logging / posts")
            except discord.HTTPException as e:
                print(f"Couldn't get a webhook for channel {base.id}: {e}")
                return None
            await self.bot.db.setWebhook(base.guild.id, base.id, webhook.id, webhook.token)
            self.cache[base.id] = webhook
            return webhook

    async def forget(self, channel_id: int):
        self.cache.pop(channel_id, None)
        await self.bot.db.deleteWebhook(channel_id)

    async def send(self, channel, username: str = None, avatar_url: str = None, retry: bool = True, **kwargs):
        """Send through the channel's webhook. Returns the WebhookMessage, or raises if that's impossible."""
        base, thread = self.baseChannel(channel)
        webhook = await self.get(channel)
        if webhook is None:
            raise WebhookUnavailable("Rafisol needs the Manage Webhooks permission in that channel.")
        if thread is not None:
            kwargs["thread"] = thread
        try:
            return await webhook.send(
                username=username or self.bot.user.display_name,
                avatar_url=avatar_url or self.bot.user.display_avatar.url,
                wait=True,
                allowed_mentions=kwargs.pop("allowed_mentions", discord.AllowedMentions.none()),
                **kwargs,
            )
        except discord.NotFound:
            # someone deleted the webhook, make a new one and try once more
            await self.forget(base.id)
            if retry:
                return await self.send(channel, username=username, avatar_url=avatar_url, retry=False, **kwargs)
            raise

    async def edit(self, channel, message_id: int, **kwargs):
        base, thread = self.baseChannel(channel)
        webhook = await self.get(channel, create=False)
        if webhook is None:
            raise WebhookUnavailable("The webhook that posted that message is gone.")
        if thread is not None:
            kwargs["thread"] = thread
        return await webhook.edit_message(message_id, allowed_mentions=discord.AllowedMentions.none(), **kwargs)

    # ---- log queue

    def log(self, channel, embed: discord.Embed, file: discord.File = None):
        """Queue a log embed for a channel. Fire and forget."""
        if channel is None:
            return
        queue = self.queues.setdefault(channel.id, [])
        queue.append((embed, file))
        if channel.id not in self.flushers or self.flushers[channel.id].done():
            self.flushers[channel.id] = asyncio.create_task(self.flush(channel))

    async def flush(self, channel):
        await asyncio.sleep(FLUSH_DELAY)
        while self.queues.get(channel.id):
            queue = self.queues[channel.id]
            batch, files, size = [], [], 0
            # bundle up to 10 embeds / 6000 chars / 10 files into one message
            while queue and len(batch) < 10:
                embed, file = queue[0]
                if batch and (size + embedSize(embed) > 6000 or (file and len(files) >= 10)):
                    break
                queue.pop(0)
                batch.append(embed)
                size += embedSize(embed)
                if file:
                    files.append(file)
            try:
                await self.send(channel, username=LOG_USERNAME, embeds=batch, files=files)
            except (WebhookUnavailable, discord.Forbidden):
                # no manage webhooks, fall back to a normal message
                try:
                    await channel.send(embeds=batch, files=[rewind(f) for f in files], allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException as e:
                    print(f"Couldn't send logs to channel {channel.id}: {e}")
            except discord.HTTPException as e:
                print(f"Couldn't send logs to channel {channel.id}: {e}")
            await asyncio.sleep(0.5)
        self.queues.pop(channel.id, None)

def rewind(file: discord.File):
    try:
        file.reset()
    except Exception:
        pass
    return file

def textFile(text: str, filename: str = "message.txt"):
    return discord.File(io.BytesIO(text.encode("utf-8")), filename=filename)
