import asyncio
import discord
from discord.ext import commands

import main
import permissions

def loadTree():
    async def build():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default(), tree_cls=main.RafisolTree)
        for cog in main.cogs:
            await bot.load_extension(f"cogs.{cog}")
        return bot
    return asyncio.run(build())

def test_every_command_has_a_permission_entry():
    bot = loadTree()
    names = {c.qualified_name for c in bot.tree.walk_commands() if not isinstance(c, discord.app_commands.Group)}
    missing = names - set(permissions.COMMANDS)
    stale = set(permissions.COMMANDS) - names
    assert not missing, f"commands missing from permissions.COMMANDS: {missing}"
    assert not stale, f"permissions.COMMANDS lists commands that don't exist: {stale}"

def test_command_count_under_discord_limit():
    bot = loadTree()
    assert len(bot.tree.get_commands()) <= 100

def test_levels_are_valid():
    for name, (level, native, description) in permissions.COMMANDS.items():
        assert level in permissions.LEVELS, name
        assert native is None or hasattr(discord.Permissions, native), name
        assert description
