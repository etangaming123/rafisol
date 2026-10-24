import discord
from discord import app_commands
from discord.ext import commands

import common
from common import Colors, ConfirmView, formatUsername, plainUsername, timestamp

def readColor(text: str):
    if not text:
        return None, None
    try:
        return discord.Color.from_str(text if text.startswith(("#", "0x", "rgb")) else f"#{text}"), None
    except ValueError:
        return None, f"Couldn't read `{text}` as a colour. Use a hex code like `#8649d7`."

def roleProblem(interaction: discord.Interaction, role: discord.Role):
    """Can the person running this hand out / edit this role? None if fine."""
    guild = interaction.guild
    if role.is_default():
        return "That's @everyone."
    if role.managed:
        return "That role is managed by Discord or an integration (bot roles, booster role etc)."
    if role >= guild.me.top_role:
        return "That role is above (or is) my highest role, so I can't touch it. Move my role up!"
    if interaction.user.id != guild.owner_id and role >= interaction.user.top_role:
        return "That role is the same as or above your highest role."
    return None

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    role = app_commands.Group(name="role", description="Manage roles.")
    customrole = app_commands.Group(name="customrole", description="Your own personal role (if the server allows it).")

    @role.command(name="add", description="Give a member a role.")
    @app_commands.describe(member="The member.", role="The role to give.")
    async def role_add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        problem = roleProblem(interaction, role)
        if problem:
            await interaction.response.send_message(content=problem, ephemeral=True)
            return
        if role in member.roles:
            await interaction.response.send_message(content=f"{member.mention} already has {role.mention}.", ephemeral=True)
            return
        await member.add_roles(role, reason=f"/role add by {plainUsername(interaction.user)}")
        await interaction.response.send_message(content=f"Gave {role.mention} to **{formatUsername(member)}**.", ephemeral=True)

    @role.command(name="remove", description="Take a role from a member.")
    @app_commands.describe(member="The member.", role="The role to remove.")
    async def role_remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        problem = roleProblem(interaction, role)
        if problem:
            await interaction.response.send_message(content=problem, ephemeral=True)
            return
        if role not in member.roles:
            await interaction.response.send_message(content=f"{member.mention} doesn't have {role.mention}.", ephemeral=True)
            return
        await member.remove_roles(role, reason=f"/role remove by {plainUsername(interaction.user)}")
        await interaction.response.send_message(content=f"Removed {role.mention} from **{formatUsername(member)}**.", ephemeral=True)

    @role.command(name="create", description="Create a new role.")
    @app_commands.describe(name="The role's name.", color="Hex colour, e.g. #8649d7.", hoist="Show members separately in the member list.", mentionable="Let anyone @mention it.")
    async def role_create(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100], color: str = None, hoist: bool = False, mentionable: bool = False):
        colour, error = readColor(color)
        if error:
            await interaction.response.send_message(content=error, ephemeral=True)
            return
        role = await interaction.guild.create_role(name=name, color=colour or discord.Color.default(), hoist=hoist, mentionable=mentionable, reason=f"/role create by {plainUsername(interaction.user)}")
        await interaction.response.send_message(content=f"Created {role.mention}!", ephemeral=True)

    @role.command(name="delete", description="Delete a role.")
    @app_commands.describe(role="The role to delete.")
    async def role_delete(self, interaction: discord.Interaction, role: discord.Role):
        problem = roleProblem(interaction, role)
        if problem:
            await interaction.response.send_message(content=problem, ephemeral=True)
            return
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(content=f"Delete {role.mention}? {len(role.members)} member{'s' if len(role.members) != 1 else ''} have it.", view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            await interaction.edit_original_response(content="Cancelled.", view=None)
            return
        name = role.name
        await role.delete(reason=f"/role delete by {plainUsername(interaction.user)}")
        await interaction.edit_original_response(content=f"Deleted **{common.removeFormatting(name)}**.", view=None)

    @role.command(name="edit", description="Edit a role.")
    @app_commands.describe(role="The role to edit.", name="New name.", color="New hex colour (or 'none').", hoist="Show members separately.", mentionable="Let anyone @mention it.")
    async def role_edit(self, interaction: discord.Interaction, role: discord.Role, name: app_commands.Range[str, 1, 100] = None, color: str = None, hoist: bool = None, mentionable: bool = None):
        problem = roleProblem(interaction, role)
        if problem:
            await interaction.response.send_message(content=problem, ephemeral=True)
            return
        changes = {}
        if name is not None:
            changes["name"] = name
        if color is not None:
            if color.lower() == "none":
                changes["color"] = discord.Color.default()
            else:
                colour, error = readColor(color)
                if error:
                    await interaction.response.send_message(content=error, ephemeral=True)
                    return
                changes["color"] = colour
        if hoist is not None:
            changes["hoist"] = hoist
        if mentionable is not None:
            changes["mentionable"] = mentionable
        if not changes:
            await interaction.response.send_message(content="You didn't change anything!", ephemeral=True)
            return
        await role.edit(reason=f"/role edit by {plainUsername(interaction.user)}", **changes)
        await interaction.response.send_message(content=f"Updated {role.mention}.", ephemeral=True)

    @role.command(name="info", description="Show info about a role.")
    @app_commands.describe(role="The role.")
    async def role_info(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(title=role.name, color=role.color if role.color.value else Colors.neutral)
        embed.add_field(name="ID", value=str(role.id))
        embed.add_field(name="Members", value=str(len(role.members)))
        embed.add_field(name="Colour", value=str(role.color) if role.color.value else "default")
        embed.add_field(name="Position", value=str(role.position))
        embed.add_field(name="Hoisted", value="yes" if role.hoist else "no")
        embed.add_field(name="Mentionable", value="yes" if role.mentionable else "no")
        embed.add_field(name="Created", value=timestamp(role.created_at, "D"))
        key = [name.replace("_", " ").capitalize() for name, value in role.permissions if value]
        if key:
            embed.add_field(name="Permissions", value=common.truncateMessage(", ".join(key), 1024), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---- custom roles

    def eligible(self, member: discord.Member, config: dict):
        custom = config["roles"]["custom_roles"]
        if not custom["enabled"]:
            return False
        if custom["allow_boosters"] and member.premium_since is not None:
            return True
        return bool({str(r.id) for r in member.roles} & set(custom["allowed_roles"]))

    async def ownedRole(self, member: discord.Member):
        role_id = await self.bot.db.getCustomRole(member.guild.id, member.id)
        role = member.guild.get_role(role_id) if role_id else None
        if role_id and role is None:
            await self.bot.db.deleteCustomRole(member.guild.id, member.id) # deleted by hand
        return role

    @customrole.command(name="create", description="Create your own custom role.")
    @app_commands.describe(name="Your role's name.", color="Hex colour, e.g. #ff77aa.")
    async def customrole_create(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100], color: str = None):
        config = await self.bot.db.getConfig(interaction.guild.id)
        if not self.eligible(interaction.user, config):
            await interaction.response.send_message(content="You can't have a custom role here." if config["roles"]["custom_roles"]["enabled"] else "Custom roles are turned off in this server.", ephemeral=True)
            return
        if await self.ownedRole(interaction.user):
            await interaction.response.send_message(content="You already have a custom role! Use `/customrole edit` instead.", ephemeral=True)
            return
        colour, error = readColor(color)
        if error:
            await interaction.response.send_message(content=error, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        anchor = guild.get_role(common.toInt(config["roles"]["custom_roles"]["anchor_role"]) or 0)
        position = (anchor.position - 1) if anchor and anchor < guild.me.top_role else guild.me.top_role.position - 1
        role = await guild.create_role(name=name, color=colour or discord.Color.default(), reason=f"Custom role for {plainUsername(interaction.user)}")
        try:
            await role.edit(position=max(1, position))
        except discord.HTTPException:
            pass # stays at the bottom, colour may be hidden by other roles but it works
        await interaction.user.add_roles(role, reason="Custom role")
        await self.bot.db.setCustomRole(guild.id, interaction.user.id, role.id)
        await interaction.followup.send(content=f"Made you {role.mention}!", ephemeral=True)

    @customrole.command(name="edit", description="Edit your custom role.")
    @app_commands.describe(name="New name.", color="New hex colour.")
    async def customrole_edit(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100] = None, color: str = None):
        role = await self.ownedRole(interaction.user)
        if role is None:
            await interaction.response.send_message(content="You don't have a custom role. Make one with `/customrole create`!", ephemeral=True)
            return
        changes = {}
        if name:
            changes["name"] = name
        if color:
            colour, error = readColor(color)
            if error:
                await interaction.response.send_message(content=error, ephemeral=True)
                return
            changes["color"] = colour
        if not changes:
            await interaction.response.send_message(content="You didn't change anything!", ephemeral=True)
            return
        await role.edit(reason=f"Custom role edit by {plainUsername(interaction.user)}", **changes)
        await interaction.response.send_message(content=f"Updated {role.mention}!", ephemeral=True)

    @customrole.command(name="delete", description="Delete your custom role.")
    async def customrole_delete(self, interaction: discord.Interaction):
        role = await self.ownedRole(interaction.user)
        if role is None:
            await interaction.response.send_message(content="You don't have a custom role.", ephemeral=True)
            return
        await role.delete(reason=f"Custom role deleted by {plainUsername(interaction.user)}")
        await self.bot.db.deleteCustomRole(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(content="Deleted your custom role.", ephemeral=True)

    async def removeCustomRole(self, guild: discord.Guild, user_id: int, reason: str):
        role_id = await self.bot.db.getCustomRole(guild.id, user_id)
        if role_id is None:
            return
        role = guild.get_role(role_id)
        await self.bot.db.deleteCustomRole(guild.id, user_id)
        if role:
            try:
                await role.delete(reason=reason)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # stopped boosting / lost the role that allowed it
        if before.premium_since == after.premium_since and before.roles == after.roles:
            return
        config = await self.bot.db.getConfig(after.guild.id)
        if config["roles"]["custom_roles"]["enabled"] and not self.eligible(after, config):
            await self.removeCustomRole(after.guild, after.id, "No longer eligible for a custom role")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self.removeCustomRole(member.guild, member.id, "Custom role owner left")

async def setup(bot):
    await bot.add_cog(Roles(bot))
