import json
import time
import copy
import asyncio
import aiosqlite

import config_schema

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS config_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    data TEXT NOT NULL,
    author_id INTEGER,
    note TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS config_history_guild ON config_history (guild_id, id);
CREATE TABLE IF NOT EXISTS cases (
    guild_id INTEGER NOT NULL,
    case_no INTEGER NOT NULL,
    action TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    mod_id INTEGER NOT NULL,
    reason TEXT,
    duration INTEGER,
    created_at INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (guild_id, case_no)
);
CREATE INDEX IF NOT EXISTS cases_user ON cases (guild_id, user_id);
CREATE TABLE IF NOT EXISTS scheduled_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    run_at INTEGER NOT NULL,
    data TEXT
);
CREATE INDEX IF NOT EXISTS scheduled_run_at ON scheduled_actions (run_at);
CREATE TABLE IF NOT EXISTS role_persist (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role_ids TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS webhooks (
    channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    webhook_id INTEGER NOT NULL,
    token TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lockdown_state (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    previous TEXT,
    PRIMARY KEY (guild_id, channel_id)
);
CREATE TABLE IF NOT EXISTS custom_roles (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
"""

HISTORY_KEEP = 10

class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection = None
        self.configs = {} # guild_id -> config dict, treat as read-only (use editConfig to change)
        self.caselock = asyncio.Lock() # case numbers are per guild, so two mods at once can't grab the same one

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        print(f"Connected to database [{self.path}]")

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def fetchone(self, query, params=()):
        async with self.conn.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, query, params=()):
        async with self.conn.execute(query, params) as cursor:
            return await cursor.fetchall()

    async def execute(self, query, params=()):
        cursor = await self.conn.execute(query, params)
        await self.conn.commit()
        return cursor

    # ---- guild config

    async def getConfig(self, guild_id: int):
        """Cached config for a guild. Don't mutate what this returns - use editConfig()."""
        if guild_id in self.configs:
            return self.configs[guild_id]
        row = await self.fetchone("SELECT data FROM guild_config WHERE guild_id = ?", (guild_id,))
        config = config_schema.fillDefaults(json.loads(row["data"])) if row else config_schema.defaults()
        self.configs[guild_id] = config
        return config

    async def editConfig(self, guild_id: int):
        return copy.deepcopy(await self.getConfig(guild_id))

    async def saveConfig(self, guild_id: int, config: dict, author_id: int = None, note: str = None, history: bool = True):
        now = int(time.time())
        if history:
            # snapshot what we're replacing so /config rollback can bring it back
            previous = await self.getConfig(guild_id)
            await self.conn.execute(
                "INSERT INTO config_history (guild_id, data, author_id, note, created_at) VALUES (?, ?, ?, ?, ?)",
                (guild_id, json.dumps(previous), author_id, note, now),
            )
            await self.conn.execute(
                "DELETE FROM config_history WHERE guild_id = ? AND id NOT IN (SELECT id FROM config_history WHERE guild_id = ? ORDER BY id DESC LIMIT ?)",
                (guild_id, guild_id, HISTORY_KEEP),
            )
        await self.conn.execute(
            "INSERT INTO guild_config (guild_id, data, updated_at) VALUES (?, ?, ?) ON CONFLICT(guild_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (guild_id, json.dumps(config), now),
        )
        await self.conn.commit()
        self.configs[guild_id] = config

    async def configHistory(self, guild_id: int):
        return await self.fetchall("SELECT id, author_id, note, created_at FROM config_history WHERE guild_id = ? ORDER BY id DESC", (guild_id,))

    async def historyEntry(self, guild_id: int, entry_id: int):
        row = await self.fetchone("SELECT data FROM config_history WHERE guild_id = ? AND id = ?", (guild_id, entry_id))
        return config_schema.fillDefaults(json.loads(row["data"])) if row else None

    async def deleteGuild(self, guild_id: int):
        for table in ("guild_config", "config_history", "cases", "scheduled_actions", "role_persist", "webhooks", "lockdown_state", "custom_roles"):
            await self.conn.execute(f"DELETE FROM {table} WHERE guild_id = ?", (guild_id,))
        await self.conn.commit()
        self.configs.pop(guild_id, None)

    # ---- cases

    async def addCase(self, guild_id: int, action: str, user_id: int, mod_id: int, reason: str = None, duration: int = None):
        async with self.caselock:
            row = await self.fetchone("SELECT COALESCE(MAX(case_no), 0) + 1 AS next FROM cases WHERE guild_id = ?", (guild_id,))
            case_no = row["next"]
            await self.execute(
                "INSERT INTO cases (guild_id, case_no, action, user_id, mod_id, reason, duration, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (guild_id, case_no, action, user_id, mod_id, reason, duration, int(time.time())),
            )
            return case_no

    async def getCase(self, guild_id: int, case_no: int):
        return await self.fetchone("SELECT * FROM cases WHERE guild_id = ? AND case_no = ?", (guild_id, case_no))

    async def userCases(self, guild_id: int, user_id: int):
        return await self.fetchall("SELECT * FROM cases WHERE guild_id = ? AND user_id = ? ORDER BY case_no DESC", (guild_id, user_id))

    async def recentCases(self, guild_id: int, limit: int = 25):
        return await self.fetchall("SELECT * FROM cases WHERE guild_id = ? ORDER BY case_no DESC LIMIT ?", (guild_id, limit))

    async def activeWarnCount(self, guild_id: int, user_id: int):
        row = await self.fetchone("SELECT COUNT(*) AS n FROM cases WHERE guild_id = ? AND user_id = ? AND action = 'warn' AND active = 1", (guild_id, user_id))
        return row["n"]

    async def updateCaseReason(self, guild_id: int, case_no: int, reason: str):
        cursor = await self.execute("UPDATE cases SET reason = ? WHERE guild_id = ? AND case_no = ?", (reason, guild_id, case_no))
        return cursor.rowcount > 0

    async def deactivateCase(self, guild_id: int, case_no: int):
        cursor = await self.execute("UPDATE cases SET active = 0 WHERE guild_id = ? AND case_no = ? AND active = 1", (guild_id, case_no))
        return cursor.rowcount > 0

    async def clearWarns(self, guild_id: int, user_id: int):
        cursor = await self.execute("UPDATE cases SET active = 0 WHERE guild_id = ? AND user_id = ? AND action = 'warn' AND active = 1", (guild_id, user_id))
        return cursor.rowcount

    # ---- scheduled actions (temp bans, temp mutes, timed lockdowns)

    async def schedule(self, guild_id: int, target_id: int, action: str, run_at: int, data: dict = None):
        # only one pending action of each kind per target, newest wins
        await self.conn.execute("DELETE FROM scheduled_actions WHERE guild_id = ? AND target_id = ? AND action = ?", (guild_id, target_id, action))
        await self.execute(
            "INSERT INTO scheduled_actions (guild_id, target_id, action, run_at, data) VALUES (?, ?, ?, ?, ?)",
            (guild_id, target_id, action, run_at, json.dumps(data or {})),
        )

    async def unschedule(self, guild_id: int, target_id: int, action: str):
        await self.execute("DELETE FROM scheduled_actions WHERE guild_id = ? AND target_id = ? AND action = ?", (guild_id, target_id, action))

    async def dueActions(self, now: int):
        return await self.fetchall("SELECT * FROM scheduled_actions WHERE run_at <= ? ORDER BY run_at", (now,))

    async def deleteScheduled(self, action_id: int):
        await self.execute("DELETE FROM scheduled_actions WHERE id = ?", (action_id,))

    async def scheduledFor(self, guild_id: int, target_id: int, action: str):
        return await self.fetchone("SELECT * FROM scheduled_actions WHERE guild_id = ? AND target_id = ? AND action = ?", (guild_id, target_id, action))

    # ---- role persist

    async def saveRoles(self, guild_id: int, user_id: int, role_ids: list):
        if not role_ids:
            await self.execute("DELETE FROM role_persist WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
            return
        await self.execute(
            "INSERT INTO role_persist (guild_id, user_id, role_ids) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET role_ids = excluded.role_ids",
            (guild_id, user_id, json.dumps(role_ids)),
        )

    async def popRoles(self, guild_id: int, user_id: int):
        row = await self.fetchone("SELECT role_ids FROM role_persist WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        if row is None:
            return []
        await self.execute("DELETE FROM role_persist WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        return json.loads(row["role_ids"])

    # ---- webhooks (never exported, the token is basically a password)

    async def getWebhook(self, channel_id: int):
        return await self.fetchone("SELECT * FROM webhooks WHERE channel_id = ?", (channel_id,))

    async def setWebhook(self, guild_id: int, channel_id: int, webhook_id: int, token: str):
        await self.execute(
            "INSERT INTO webhooks (channel_id, guild_id, webhook_id, token) VALUES (?, ?, ?, ?) ON CONFLICT(channel_id) DO UPDATE SET webhook_id = excluded.webhook_id, token = excluded.token",
            (channel_id, guild_id, webhook_id, token),
        )

    async def deleteWebhook(self, channel_id: int):
        await self.execute("DELETE FROM webhooks WHERE channel_id = ?", (channel_id,))

    # ---- lockdown

    async def saveLockdown(self, guild_id: int, channel_id: int, previous):
        await self.execute(
            "INSERT OR REPLACE INTO lockdown_state (guild_id, channel_id, previous) VALUES (?, ?, ?)",
            (guild_id, channel_id, json.dumps(previous)),
        )

    async def popLockdown(self, guild_id: int, channel_id: int):
        row = await self.fetchone("SELECT previous FROM lockdown_state WHERE guild_id = ? AND channel_id = ?", (guild_id, channel_id))
        if row is None:
            return False, None
        await self.execute("DELETE FROM lockdown_state WHERE guild_id = ? AND channel_id = ?", (guild_id, channel_id))
        return True, json.loads(row["previous"])

    async def lockedChannels(self, guild_id: int):
        rows = await self.fetchall("SELECT channel_id FROM lockdown_state WHERE guild_id = ?", (guild_id,))
        return [row["channel_id"] for row in rows]

    # ---- custom roles

    async def getCustomRole(self, guild_id: int, user_id: int):
        row = await self.fetchone("SELECT role_id FROM custom_roles WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        return row["role_id"] if row else None

    async def setCustomRole(self, guild_id: int, user_id: int, role_id: int):
        await self.execute("INSERT OR REPLACE INTO custom_roles (guild_id, user_id, role_id) VALUES (?, ?, ?)", (guild_id, user_id, role_id))

    async def deleteCustomRole(self, guild_id: int, user_id: int):
        await self.execute("DELETE FROM custom_roles WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))

    async def customRoleOwner(self, guild_id: int, role_id: int):
        row = await self.fetchone("SELECT user_id FROM custom_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
        return row["user_id"] if row else None
