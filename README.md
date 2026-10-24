# Rafisol
A multipurpose Discord server bot, built for moderation, logging, etc. 

[Terms](https://rafisol.etangaming.xyz/termsofservice.html) • [Privacy](https://rafisol.etangaming.xyz/privacypolicy.html)

[Website](https://rafisol.etangaming.xyz/) • [Settings Editor](https://rafisol.etangaming.xyz/editor.html) • [Add to Server](https://discord.com/oauth2/authorize?client_id=1563324610106236938)

> [!NOTE]
> Uptime is flaky. 

## Features
### Moderation
* `/ban` `/unban` `/softban` `/kick` `/timeout` `/untimeout` `/mute` `/unmute` `/warn` `/purge` `/lockdown` `/unlock` `/slowmode` `/nick`
* Temporary bans, mutes and lockdowns (`2d1h30m` style durations) that undo themselves
* Numbered cases for every action - `/cases` `/case` `/reason` `/delcase` `/clearwarns`
* Warnings that escalate automatically (e.g. 3 warnings = 1h timeout)
* Bans/kicks/timeouts done through Discord itself (or other bots) get cases too
* Mutes stick even if someone leaves and rejoins

### Logging
* Messages - deletes (with attachments), bulk deletes (as a .txt transcript), edits
* Members - joins (with new account warnings), leaves (with their roles), nickname, role, username and avatar changes
* Voice - joins, leaves, moves, server/self mute and deafen, streaming and camera
* Server - audit-log style logs of channel, permission, role, server, emoji, sticker, invite, webhook, thread, integration, AutoMod rule and event changes, showing who did it and why
* Every event can be toggled, with ignored channels/categories/roles

### Automod + Honeypot
* Blocked words (with wildcards), invite links, links (with an allowlist), mass mentions, spam and caps filters
* Each rule can log, delete, warn, timeout, mute, kick or ban
* **Honeypot channel** - a "DO NOT TYPE HERE" channel. Hacked accounts and spam bots post in every channel they can see, so anyone who talks there gets softbanned (banned and instantly unbanned, which wipes their recent messages everywhere). The action is configurable (softban, ban, kick or timeout). `/honeypot setup` makes the channel for you.

### Roles
* Button and dropdown role menus (normal, unique, verify-only and remove-only modes) that keep working after restarts
* `/rank` self-assignable roles
* `/customrole` - boosters (or chosen roles) can make their own role
* Autoroles (separate ones for bots), role persist
* `/role add` `/role remove` `/role create` `/role delete` `/role edit` `/role info`
* Per-command permissions: mod/admin roles, allow/deny roles, channel restrictions, disabling commands

### Join / Leave
* Welcome and leave messages with embeds and placeholders (`{user.mention}`, `{server}`, `{membercount.ordinal}`...)
* Welcome DMs

### Webhook posts
* Write rules/info/FAQ posts in the editor, `/post send` them with a custom name and avatar, then `/post update` to edit them in place

## Settings Editor
All of Rafisol's settings live in one file per server:

1. Run `/config export` - Rafisol sends you `rafisol-<server id>.json`
2. Open the [Settings Editor](https://rafisol.etangaming.xyz/editor.html) and import it
3. Edit, export, and run `/config import` with the file attached
4. Rafisol checks the file, shows what changed and anything it had to fix, and asks you to confirm

`/config rollback` undoes an import, and `/config history` lists the last 10 versions. The editor runs entirely in your browser, and exports never include webhook URLs.

> [!WARNING]
> Rafisol can only give out roles below its own highest role, and only action members below it. Drag its role near the top in Server Settings --> Roles.

## Selfhosting
1. Make an application in the [Discord Developer Portal](https://discord.com/developers/applications), add a bot, and copy its token.
2. Under **Bot**, turn on the **Server Members** and **Message Content** privileged intents.
3. Invite it with the `bot` and `applications.commands` scopes. The easiest permission set is **Administrator**; otherwise it needs at least: View Audit Log, Manage Server (for invite logs), Manage Roles, Manage Channels, Manage Webhooks, Manage Messages, Manage Nicknames, Kick Members, Ban Members, Moderate Members, View Channels, Send Messages, Embed Links, Attach Files, Read Message History.
4. Clone and install:
```
git clone https://github.com/etangaming123/rafisol
cd rafisol
pip install -r requirements.txt
```
5. Run `python main.py` once. It creates `config.json` - put your token in and press enter:
```json
{
    "token": "PUT YOUR BOT TOKEN HERE",
    "editor_url": "https://rafisol.etangaming.xyz/editor.html",
    "database_path": "rafisol.db"
}
```
The token is encrypted in place the first time the bot starts. Set `editor_url` to your own GitHub Pages URL if you host the editor yourself (recommended if you're running a modified instance).

Requires Python 3.10 or above.

### Encryption keys (recommended)
By default the token's encryption key is stored in `bot_token.key` next to `config.json`. To keep the key off disk, put it in the `RAFISOL_BOT_TOKEN_ENCRYPTION_KEY` environment variable instead:
* Windows: `python generate_env_keys.py --apply`, then open a new terminal
* macOS/Linux: `python3 generate_env_keys.py` and add the printed `export` line to your shell profile

If the env var shows up later, the stored token is moved over to it automatically.

### Hosting the editor
The editor and website are plain HTML at the repo root - turn on GitHub Pages for `main` / root (Settings --> Pages) and it just works. After changing `config_schema.py` or `permissions.py`, run `python generate_editor_defaults.py` to rebuild `siteresources/defaults.js` so the editor matches the bot.

### Development
```
pip install -r requirements-dev.txt
pytest
```
`python -m http.server` in the repo root serves the editor locally.

## License
MIT - see [LICENSE](LICENSE).
