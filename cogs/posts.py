import discord
from discord import app_commands
from discord.ext import commands

import common
from common import buildEmbed
from webhooks import WebhookUnavailable

def findPost(config: dict, post_id: str):
    return next((p for p in config["posts"] if p["id"] == post_id), None)

class Posts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    post = app_commands.Group(name="post", description="Webhook posts like rules and info (write them in the editor).")

    def render(self, data: dict, guild: discord.Guild, color: int):
        embeds = [e for e in (buildEmbed(e, guild=guild, color=color) for e in data["embeds"]) if e]
        content = common.renderTemplate(data["content"], guild=guild) or None
        return content, embeds

    async def load(self, interaction: discord.Interaction, post_id: str):
        config = await self.bot.db.editConfig(interaction.guild.id)
        data = findPost(config, post_id)
        if data is None:
            await interaction.followup.send(content=f"There's no post called `{post_id}`. Write one in the editor first!", ephemeral=True)
            return None, None
        return config, data

    @post.command(name="send", description="Post a saved message through a webhook.")
    @app_commands.describe(post="The post's id (from the editor).")
    async def post_send(self, interaction: discord.Interaction, post: str):
        await interaction.response.defer(ephemeral=True)
        config, data = await self.load(interaction, post)
        if data is None:
            return
        channel = interaction.guild.get_channel_or_thread(int(data["channel"])) if data["channel"] else None
        if channel is None:
            await interaction.followup.send(content="That post doesn't have a (valid) channel set.", ephemeral=True)
            return
        content, embeds = self.render(data, interaction.guild, common.parseColor(config["general"]["embed_color"]))
        if content is None and not embeds:
            await interaction.followup.send(content="That post is empty!", ephemeral=True)
            return
        try:
            message = await self.bot.webhooks.send(channel, username=data["username"] or interaction.guild.name, avatar_url=data["avatar_url"] or (interaction.guild.icon.url if interaction.guild.icon else None), content=content, embeds=embeds)
        except WebhookUnavailable as e:
            await interaction.followup.send(content=str(e), ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(content=f"Discord didn't like that post: {e.text}", ephemeral=True)
            return
        data["message_id"] = str(message.id)
        data["posted_channel"] = str(channel.id)
        await self.bot.db.saveConfig(interaction.guild.id, config, history=False)
        await interaction.followup.send(content=f"Posted `{post}` in {channel.mention}! [Jump]({message.jump_url})\n-# edit it in the editor and use `/post update` to change it in place.", ephemeral=True)

    @post.command(name="update", description="Edit an already posted message to match the saved version.")
    @app_commands.describe(post="The post's id (from the editor).")
    async def post_update(self, interaction: discord.Interaction, post: str):
        await interaction.response.defer(ephemeral=True)
        config, data = await self.load(interaction, post)
        if data is None:
            return
        if not data["message_id"] or not data["posted_channel"]:
            await interaction.followup.send(content="That post hasn't been sent yet. Use `/post send` first!", ephemeral=True)
            return
        channel = interaction.guild.get_channel_or_thread(int(data["posted_channel"]))
        if channel is None:
            await interaction.followup.send(content="The channel it was posted in is gone. Use `/post send` to post it again.", ephemeral=True)
            return
        content, embeds = self.render(data, interaction.guild, common.parseColor(config["general"]["embed_color"]))
        try:
            await self.bot.webhooks.edit(channel, int(data["message_id"]), content=content, embeds=embeds)
        except (WebhookUnavailable, discord.NotFound):
            await interaction.followup.send(content="Couldn't find that message anymore (deleted, or the webhook was removed). Use `/post send` to post it again.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(content=f"Discord didn't like that post: {e.text}", ephemeral=True)
            return
        note = f"\n-# heads up: the post's channel is now <#{data['channel']}>, but this edited the copy in {channel.mention}. Use `/post send` to post it in the new channel." if data["channel"] and data["channel"] != data["posted_channel"] else ""
        await interaction.followup.send(content=f"Updated `{post}` in {channel.mention}!{note}", ephemeral=True)

    @post_send.autocomplete("post")
    @post_update.autocomplete("post")
    async def post_autocomplete(self, interaction: discord.Interaction, current: str):
        config = await self.bot.db.getConfig(interaction.guild.id)
        return [app_commands.Choice(name=p["id"], value=p["id"]) for p in config["posts"] if current.lower() in p["id"]][:25]

    @post.command(name="list", description="List saved webhook posts.")
    async def post_list(self, interaction: discord.Interaction):
        config = await self.bot.db.getConfig(interaction.guild.id)
        if not config["posts"]:
            await interaction.response.send_message(content="No posts yet. Write some in the editor!", ephemeral=True)
            return
        lines = []
        for p in config["posts"]:
            where = f"<#{p['channel']}>" if p["channel"] else "no channel"
            posted = f"[posted](https://discord.com/channels/{interaction.guild.id}/{p['posted_channel']}/{p['message_id']})" if p["message_id"] and p["posted_channel"] else "not posted"
            lines.append(f"`{p['id']}` - {where}, {len(p['embeds'])} embed{'s' if len(p['embeds']) != 1 else ''} ({posted})")
        embed = discord.Embed(title="Webhook posts", description="\n".join(lines)[:4096], color=common.Colors.info)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Posts(bot))
