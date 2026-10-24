"""
Button / select menu role menus. The components are DynamicItems, so the
custom_id carries everything we need (menu id + role id) and the menus keep
working after a restart without storing any views.
"""

import discord
from discord import app_commands
from discord.ext import commands

import common
from common import buildEmbed

STYLES = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}

def findMenu(config: dict, menu_id: str):
    return next((m for m in config["reaction_roles"] if m["id"] == menu_id), None)

def emojiOrNone(text: str):
    if not text:
        return None
    try:
        return discord.PartialEmoji.from_str(text)
    except Exception:
        return None

async def applyRoles(interaction: discord.Interaction, menu_id: str, picked: list[int], from_select: bool):
    bot = interaction.client
    config = await bot.db.getConfig(interaction.guild.id)
    menu = findMenu(config, menu_id)
    if menu is None:
        await interaction.response.send_message(content="This role menu doesn't exist anymore.", ephemeral=True)
        return
    guild = interaction.guild
    member = interaction.user
    menu_roles = [r for r in (guild.get_role(int(o["role"])) for o in menu["options"]) if r]
    picked_roles = [r for r in menu_roles if r.id in picked]
    if not picked_roles and not from_select:
        await interaction.response.send_message(content="That role isn't part of this menu anymore.", ephemeral=True)
        return
    usable = [r for r in menu_roles if r < guild.me.top_role and not r.managed]
    if any(r not in usable for r in picked_roles):
        await interaction.response.send_message(content="I can't give out that role (it's above mine). Let an admin know!", ephemeral=True)
        return

    have = set(r for r in menu_roles if r in member.roles)
    add, remove = set(), set()
    mode = menu["mode"]
    if from_select:
        chosen = set(picked_roles)
        if mode in ("normal", "unique"):
            add, remove = chosen - have, have - chosen
        elif mode == "verify":
            add = chosen - have
        elif mode == "remove":
            remove = chosen & have
    else:
        role = picked_roles[0]
        if mode == "normal":
            (remove if role in have else add).add(role)
        elif mode == "unique":
            if role in have:
                remove.add(role)
            else:
                add.add(role)
                remove = have - {role}
        elif mode == "verify":
            if role not in have:
                add.add(role)
        elif mode == "remove":
            if role in have:
                remove.add(role)

    reason = f"Role menu {menu_id}"
    if add:
        await member.add_roles(*add, reason=reason)
    if remove:
        await member.remove_roles(*[r for r in remove if r in usable], reason=reason)
    lines = [f"Added {r.mention}" for r in add] + [f"Removed {r.mention}" for r in remove]
    await interaction.response.send_message(content="\n".join(lines) or "Nothing changed.", ephemeral=True)


class RoleButton(discord.ui.DynamicItem[discord.ui.Button], template=r"rafisol:rr:(?P<menu>[a-z0-9_-]{1,32}):(?P<role>[0-9]{15,21})"):
    def __init__(self, menu_id: str, role_id: int, label: str = None, emoji=None, style=discord.ButtonStyle.secondary):
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"rafisol:rr:{menu_id}:{role_id}"))
        self.menu_id = menu_id
        self.role_id = role_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(match["menu"], int(match["role"]))

    async def callback(self, interaction: discord.Interaction):
        await applyRoles(interaction, self.menu_id, [self.role_id], from_select=False)


class RoleSelect(discord.ui.DynamicItem[discord.ui.Select], template=r"rafisol:rs:(?P<menu>[a-z0-9_-]{1,32})"):
    def __init__(self, menu_id: str, select: discord.ui.Select = None):
        super().__init__(select or discord.ui.Select(custom_id=f"rafisol:rs:{menu_id}"))
        self.menu_id = menu_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match):
        return cls(match["menu"], item)

    async def callback(self, interaction: discord.Interaction):
        values = interaction.data.get("values", [])
        await applyRoles(interaction, self.menu_id, [int(v) for v in values if v.isdigit()], from_select=True)


def buildView(menu: dict, guild: discord.Guild):
    view = discord.ui.View(timeout=None)
    options = []
    for option in menu["options"]:
        role = guild.get_role(int(option["role"]))
        if role:
            options.append((option, role))
    if not options:
        return None
    if menu["type"] == "select":
        select = discord.ui.Select(
            custom_id=f"rafisol:rs:{menu['id']}",
            placeholder=menu["placeholder"] or None,
            min_values=0,
            max_values=1 if menu["mode"] == "unique" else len(options),
            options=[discord.SelectOption(label=(o["label"] or r.name)[:100], value=str(r.id), emoji=emojiOrNone(o["emoji"]), description=o["description"] or None) for o, r in options],
        )
        view.add_item(RoleSelect(menu["id"], select))
    else:
        for i, (option, role) in enumerate(options):
            emoji = emojiOrNone(option["emoji"])
            label = option["label"] or (None if emoji else role.name)
            item = RoleButton(menu["id"], role.id, label=label, emoji=emoji, style=STYLES[option["style"]])
            item.item.row = i // 5
            view.add_item(item)
    return view


class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    rolemenu = app_commands.Group(name="rolemenu", description="Button / dropdown role menus (set them up in the editor).")

    @rolemenu.command(name="post", description="Post a role menu, or refresh it if it's already posted.")
    @app_commands.describe(menu="The menu's id (from the editor).", new="Post a fresh message instead of editing the old one.")
    async def rolemenu_post(self, interaction: discord.Interaction, menu: str, new: bool = False):
        await interaction.response.defer(ephemeral=True)
        config = await self.bot.db.editConfig(interaction.guild.id)
        data = findMenu(config, menu)
        if data is None:
            await interaction.followup.send(content=f"There's no role menu called `{menu}`. Make one in the editor first!", ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(data["channel"])) if data["channel"] else None
        if channel is None:
            await interaction.followup.send(content="That menu doesn't have a (valid) channel set.", ephemeral=True)
            return
        view = buildView(data, interaction.guild)
        if view is None:
            await interaction.followup.send(content="That menu has no roles in it.", ephemeral=True)
            return
        color = common.parseColor(config["general"]["embed_color"])
        embed = buildEmbed(data["embed"], guild=interaction.guild, color=color)
        content = common.renderTemplate(data["content"], guild=interaction.guild) or None
        if content is None and embed is None:
            embed = discord.Embed(title="Pick your roles", description="\n".join(f"{o['emoji']} <@&{o['role']}> {o['description']}".strip() for o in data["options"]), color=color)
        try:
            message = None
            if data["message_id"] and not new:
                try:
                    message = await channel.fetch_message(int(data["message_id"]))
                    await message.edit(content=content, embed=embed, view=view)
                    action = "Updated"
                except discord.NotFound:
                    message = None
            if message is None:
                message = await channel.send(content=content, embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
                action = "Posted"
        except discord.HTTPException as e:
            await interaction.followup.send(content=f"Discord didn't like that menu: {e.text}\n-# check the emojis are valid and the embed isn't too long.", ephemeral=True)
            return
        if str(message.id) != data["message_id"]:
            data["message_id"] = str(message.id)
            await self.bot.db.saveConfig(interaction.guild.id, config, history=False)
        await interaction.followup.send(content=f"{action} `{menu}` in {channel.mention}! [Jump]({message.jump_url})", ephemeral=True)

    @rolemenu_post.autocomplete("menu")
    async def menu_autocomplete(self, interaction: discord.Interaction, current: str):
        config = await self.bot.db.getConfig(interaction.guild.id)
        return [app_commands.Choice(name=m["id"], value=m["id"]) for m in config["reaction_roles"] if current.lower() in m["id"]][:25]

    @rolemenu.command(name="list", description="List this server's role menus.")
    async def rolemenu_list(self, interaction: discord.Interaction):
        config = await self.bot.db.getConfig(interaction.guild.id)
        menus = config["reaction_roles"]
        if not menus:
            await interaction.response.send_message(content="No role menus yet. Add some in the editor!", ephemeral=True)
            return
        lines = []
        for m in menus:
            where = f"<#{m['channel']}>" if m["channel"] else "no channel"
            posted = f"[posted](https://discord.com/channels/{interaction.guild.id}/{m['channel']}/{m['message_id']})" if m["message_id"] else "not posted"
            lines.append(f"`{m['id']}` - {m['type']}, {m['mode']}, {len(m['options'])} roles in {where} ({posted})")
        embed = discord.Embed(title="Role menus", description="\n".join(lines)[:4096], color=common.Colors.info)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    bot.add_dynamic_items(RoleButton, RoleSelect)
    await bot.add_cog(ReactionRoles(bot))
