import discord
from discord.ext import commands

import common
from common import Colors, timestamp, buildEmbed, renderTemplate
from logutils import sendLog, userEmbed

MENTIONS = discord.AllowedMentions(users=True, roles=False, everyone=False)

def welcomeKwargs(section: dict, member, guild, color):
    content = renderTemplate(section["message"], member, guild) or None
    embed = buildEmbed(section.get("embed"), member, guild, color)
    if content is None and embed is None:
        return None
    return {"content": content, "embed": embed}

class MemberLog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def assignable(self, guild: discord.Guild, role_ids):
        roles = []
        for role_id in role_ids:
            role = guild.get_role(int(role_id))
            if role and not role.managed and not role.is_default() and role < guild.me.top_role:
                roles.append(role)
        return roles

    async def giveJoinRoles(self, member: discord.Member, config: dict):
        welcome = config["welcome"]
        roles = self.assignable(member.guild, welcome["bot_autoroles"] if member.bot else welcome["autoroles"])
        if welcome["role_persist"]:
            roles += self.assignable(member.guild, await self.bot.db.popRoles(member.guild.id, member.id))
        roles = [r for r in dict.fromkeys(roles) if r not in member.roles]
        if roles:
            try:
                await member.add_roles(*roles, reason="Rafisol autoroles / role persist")
            except discord.HTTPException as e:
                print(f"Couldn't give join roles in {member.guild.id}: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        config = await self.bot.db.getConfig(guild.id)
        color = common.parseColor(config["general"]["embed_color"])

        # log
        age_days = (discord.utils.utcnow() - member.created_at).days
        embed = userEmbed("Member Joined", member, Colors.undo, f"{member.mention} is the {common.ordinal(guild.member_count or 0)} member")
        embed.add_field(name="Account created", value=f"{timestamp(member.created_at, 'D')} ({timestamp(member.created_at)})")
        new_days = config["logging"]["new_account_days"]
        if new_days and age_days < new_days:
            embed.add_field(name="⚠️ New account", value=f"Created less than {new_days} day{'s' if new_days != 1 else ''} ago")
        embed.set_thumbnail(url=common.avatarUrl(member))
        await sendLog(self.bot, guild, "member_join", embed, member=member)

        # welcome message + dm
        join = config["welcome"]["join"]
        if join["enabled"] and join["channel"]:
            channel = guild.get_channel(int(join["channel"]))
            kwargs = welcomeKwargs(join, member, guild, color)
            if channel and kwargs:
                try:
                    await channel.send(allowed_mentions=MENTIONS, **kwargs)
                except discord.HTTPException as e:
                    print(f"Couldn't send welcome message in {guild.id}: {e}")
        dm = config["welcome"]["dm"]
        if dm["enabled"] and not member.bot:
            kwargs = welcomeKwargs(dm, member, guild, color)
            if kwargs:
                await common.dmUser(member, **kwargs)

        # roles - wait for membership screening if the server has it
        if not member.pending:
            await self.giveJoinRoles(member, config)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.pending and not after.pending:
            await self.giveJoinRoles(after, await self.bot.db.getConfig(after.guild.id))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        config = await self.bot.db.getConfig(guild.id)
        color = common.parseColor(config["general"]["embed_color"])

        roles = [r for r in reversed(member.roles) if not r.is_default()]
        embed = userEmbed("Member Left", member, Colors.delete, f"{member.mention} left the server")
        if member.joined_at:
            embed.add_field(name="Joined", value=f"{timestamp(member.joined_at, 'D')} ({timestamp(member.joined_at)})")
        if roles:
            embed.add_field(name=f"Roles ({len(roles)})", value=common.truncateMessage(" ".join(r.mention for r in roles), 1024), inline=False)
        embed.set_thumbnail(url=common.avatarUrl(member))
        await sendLog(self.bot, guild, "member_leave", embed, member=member)

        if config["welcome"]["role_persist"]:
            keep = [str(r.id) for r in roles if not r.managed and not r.is_premium_subscriber()]
            await self.bot.db.saveRoles(guild.id, member.id, keep)

        leave = config["welcome"]["leave"]
        if leave["enabled"] and leave["channel"]:
            channel = guild.get_channel(int(leave["channel"]))
            kwargs = welcomeKwargs(leave, member, guild, color)
            if channel and kwargs:
                try:
                    await channel.send(allowed_mentions=discord.AllowedMentions.none(), **kwargs)
                except discord.HTTPException as e:
                    print(f"Couldn't send leave message in {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        changes = []
        if before.name != after.name:
            changes.append(("Username", f"{before.name} → {after.name}"))
        if before.global_name != after.global_name:
            changes.append(("Display name", f"{before.global_name or 'none'} → {after.global_name or 'none'}"))
        avatar_changed = before.display_avatar.key != after.display_avatar.key
        if not changes and not avatar_changed:
            return
        for guild in after.mutual_guilds:
            member = guild.get_member(after.id)
            embed = userEmbed("User Updated", after, Colors.info, after.mention)
            for name, value in changes:
                embed.add_field(name=name, value=common.removeFormatting(value), inline=False)
            if avatar_changed:
                embed.add_field(name="Avatar", value=f"Changed ([old]({before.display_avatar.url}))", inline=False)
                embed.set_thumbnail(url=after.display_avatar.url)
            await sendLog(self.bot, guild, "member_user_update", embed, member=member)

async def setup(bot):
    await bot.add_cog(MemberLog(bot))
