# Rafisol Privacy Policy

**Effective Date**: 2026-10-24
**Bot Name**: Rafisol (Rafisol#2146)
**Developer**: etangaming123
**Contact**:
email: me [at] etangaming [dot] xyz
discord: @etangaming123

## 1. Information we process

### Stored long term (in the Bot's database)
* **Server settings** - each server's configuration (log channels, automod rules, welcome messages, role menus, permissions, etc.), plus a short history of previous versions (the last 10) with the ID of the user who made the change and an optional note.
* **Moderation cases** - for each moderation action: server ID, case number, action type, the target user's ID, the moderator's ID, the reason (as typed by the moderator), duration, active/inactive status and timestamp. This includes warnings.
* **Scheduled actions** - target IDs and timing for temporary bans, mutes and lockdowns, so they undo themselves after restarts.
* **Role persistence** - when enabled by a server, the IDs of a member's roles are saved when they leave, so they can be restored if they rejoin.
* **Custom roles** - the ID of the custom role a member created, if the server enables the feature.
* **Webhooks** - IDs and tokens of webhooks the Bot creates to send posts in a server, and lockdown state (channel IDs). Webhook tokens are never included in settings exports.

The database stores Discord IDs and text that server staff enter. It does not store message history.

### Processed temporarily
* **Message events** - to provide logging and automod, the Bot receives message content, edits, deletions and attachments' links. Recent messages are held in the Bot's memory only (Discord library cache), so a deleted or edited message can be logged. This cache is lost whenever the Bot restarts and is not written to the database.
* **Member, voice and server events** - joins, leaves, nickname/role/username/avatar changes, voice state changes and server changes (channels, roles, emoji, invites, etc.), including usernames, avatars, user IDs and account age.
* **Command inputs** - arguments and files you give to commands (e.g. a settings file in `/config import`).

To receive these events, Rafisol uses Discord's privileged **Message Content** and **Server Members** intents.

### Messages the Bot sends
The Bot may send direct messages to users, such as welcome DMs (if a server enables them) and notices when a moderation action is taken against them.

### Automated actions
Automod, the honeypot and warning escalation act automatically on the data above, based on settings chosen by each server's staff.

### Logs sent to Discord
If a server turns on logging, information from the events above is posted by the Bot into channels chosen by that server, including deleted message content, transcripts of bulk-deleted messages, and the information shown above. This content then lives on Discord and is controlled by that server.

### Technical logs
The Bot prints console output (such as startup messages and command errors) for debugging. It does not track command usage. Console output is not used for advertising or profiling.

## 2. Why we process it
To operate the Bot's features: moderation, logging, automod, roles, welcome messages and webhook posts, to keep it secure, to fix problems, and to comply with the law. We do not sell data, show ads, or build profiles of users. Each server's staff decide what is logged in their server; we host the data.

## 3. Sharing
We do not sell or rent data. Data may be shared:
* **With Discord**, since the Bot operates on its platform. See [Discord's Privacy Policy](https://discord.com/privacy).
* **With the server itself** (staff can see cases, logs and settings for their server).
* **If required by law**, or to protect rights, safety and the Bot.

## 4. The website and Settings Editor
The Settings Editor runs in your browser. The settings file you import or edit is processed locally and is not sent to us. Exported files never include webhook URLs. The website is hosted on GitHub Pages, so GitHub may collect standard web logs (such as IP address) under [GitHub's Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement). We do not run analytics or tracking cookies on the site.

## 5. Retention
* Server settings, cases and the other database records above are kept while the Bot is in your server. When the Bot is removed from a server (kicked, banned, or otherwise), that server's records are deleted automatically.
* Config history keeps only the latest 10 versions.
* Scheduled actions are removed once they run or are cancelled. Role-persist records are removed when the member rejoins and the roles are restored; if the member never rejoins, the record stays until the Bot leaves the server or deletion is requested.
* If the Bot is offline when it is removed from a server, the automatic deletion may not run. In that case, contact us and we will delete the records.
* The message cache is in memory and cleared on restart or as it fills.
* Content posted to Discord channels (logs) is kept according to the server and Discord.

## 6. Your choices and rights
* **Server owners/admins** can change or disable logging, automod, role persist and other features in the Settings Editor, and remove the Bot at any time.
* **Access and deletion requests:** to see, or have deleted, a server's data or your own user ID's records, contact us (section 10). Server staff may still keep their own copies of logs posted in Discord - we have no control over those.

## 7. Security
We take reasonable steps to protect data, such as encrypting the Bot token at rest. No system is perfectly secure, and we cannot guarantee absolute security.

## 8. Children
The Bot is not directed at children under 13 (or the minimum age in your country to use Discord). If you believe a child's data was collected in violation of this policy, contact us and we will delete it.

## 9. Changes to This Privacy Policy
We reserve the right to modify or replace the Privacy Policy at any time. Updates to the Privacy Policy will be posted on the website and the GitHub repository, and the Effective Date will be updated. By continuing to use the Bot after those revisions become effective, you accept the revised policy. If you do not agree, stop using the Bot.

## 10. Contact Us
If you have any questions about this Privacy Policy, please contact us at the given contact information at the top of this page.
