import random
import traceback
import discord
from discord import app_commands
from discord.ext import commands, tasks

import common
import permissions
import secure_token
from database import Database
from webhooks import WebhookManager

cogs = [
    "general",
    "configuration",
    "moderation",
    "cases",
    "automod",
    "honeypot",
    "messagelog",
    "voicelog",
    "serverlog",
    "memberlog",
    "roles",
    "reactionroles",
    "posts",
]

class RafisolTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # one place for every command's permission check (see permissions.py)
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            if interaction.type == discord.InteractionType.application_command:
                await interaction.response.send_message(content="Rafisol's commands only work in servers.", ephemeral=True)
            return False
        command = interaction.command
        if command is None:
            return True
        config = await self.client.db.getConfig(interaction.guild.id)
        allowed, reason = permissions.evaluate(interaction.user, interaction.channel, command.qualified_name, config)
        if not allowed and interaction.type == discord.InteractionType.application_command:
            await interaction.response.send_message(content=reason, ephemeral=True)
        return allowed

class Rafisol(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True          # privileged - join/leave, role persist, member logs
        intents.message_content = True  # privileged - message logs, automod
        intents.moderation = True
        intents.voice_states = True
        intents.invites = True
        intents.webhooks = True
        intents.emojis_and_stickers = True
        super().__init__(
            command_prefix=commands.when_mentioned, # no prefix commands, slash only
            intents=intents,
            tree_cls=RafisolTree,
            max_messages=10000, # bigger cache = more deleted/edited messages we can show the content of
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=False),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=False),
            allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
        )
        self.config = common.loadBotConfig()
        self.db = Database(self.config["database_path"])
        self.webhooks = WebhookManager(self)
        self.synced = False

    @property
    def editorUrl(self):
        return self.config.get("editor_url") or common.defaulteditorurl

    async def setup_hook(self):
        await self.db.connect()
        for item in cogs:
            try:
                await self.load_extension(f"cogs.{item}")
                print(f"Loaded cog {item}")
            except Exception as e:
                print(f"Failed to load cog {item}: {e}")
                traceback.print_exc()
        self.tree.on_error = self.onTreeError

    async def close(self):
        await super().close()
        await self.db.close()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id}) in {len(self.guilds)} servers")
        if not self.synced:
            try:
                synced = await self.tree.sync()
                print(f"Synced {len(synced)} commands")
                self.synced = True
            except Exception as e:
                print(f"Failed to sync commands: {e}")
        if not self.cycleStatus.is_running():
            self.cycleStatus.start()

    async def on_guild_remove(self, guild: discord.Guild):
        await self.db.deleteGuild(guild.id) # privacy policy: nothing is kept once Rafisol has left
        print(f"Removed from {guild.name} ({guild.id}), deleted its data")

    @tasks.loop(minutes=10)
    async def cycleStatus(self):
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=random.choice(common.statuses)))

    async def onTreeError(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = getattr(error, "original", error)
        if isinstance(error, app_commands.CheckFailure):
            return # permission checks already replied
        if isinstance(original, discord.Forbidden):
            message = "I don't have permission to do that! Check my role is high enough and has the right permissions."
        else:
            message = f"An error occurred: {original}"
            print(f"Error in /{interaction.command.qualified_name if interaction.command else '?'}:")
            traceback.print_exception(type(original), original, original.__traceback__)
        try:
            await common.reply(interaction, message)
        except discord.HTTPException:
            pass

if __name__ == "__main__":
    bot = Rafisol()
    bot.run(secure_token.secure_token("config.json", "token"))
