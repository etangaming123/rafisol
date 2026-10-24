import asyncio

import config_schema
from database import Database, HISTORY_KEEP

def run(coro):
    return asyncio.run(coro)

def test_config_history_cases_and_schedule(tmp_path):
    async def go():
        db = Database(str(tmp_path / "test.db"))
        await db.connect()

        config = await db.editConfig(1)
        assert config == config_schema.defaults()
        config["automod"]["enabled"] = True
        await db.saveConfig(1, config, author_id=5, note="import")
        db.configs.clear() # make sure it really comes back from disk
        assert (await db.getConfig(1))["automod"]["enabled"] is True

        for i in range(HISTORY_KEEP + 3):
            await db.saveConfig(1, config, author_id=5, note=f"change {i}")
        history = await db.configHistory(1)
        assert len(history) == HISTORY_KEEP
        oldest_kept = await db.historyEntry(1, history[-1]["id"])
        assert oldest_kept["automod"]["enabled"] is True

        cases = await asyncio.gather(*(db.addCase(1, "warn", 10, 5, "spam") for _ in range(5)))
        assert sorted(cases) == [1, 2, 3, 4, 5]
        assert await db.addCase(2, "ban", 10, 5) == 1 # numbering is per guild
        assert await db.activeWarnCount(1, 10) == 5
        assert await db.deactivateCase(1, 3)
        assert await db.activeWarnCount(1, 10) == 4
        assert await db.clearWarns(1, 10) == 4

        await db.schedule(1, 10, "unban", 100)
        await db.schedule(1, 10, "unban", 200) # replaces the first
        due = await db.dueActions(150)
        assert due == []
        due = await db.dueActions(250)
        assert len(due) == 1 and due[0]["run_at"] == 200

        await db.saveRoles(1, 10, ["123", "456"])
        assert await db.popRoles(1, 10) == ["123", "456"]
        assert await db.popRoles(1, 10) == []

        await db.saveLockdown(1, 77, {"send_messages": None})
        assert await db.lockedChannels(1) == [77]
        assert await db.popLockdown(1, 77) == (True, {"send_messages": None})
        assert await db.popLockdown(1, 77) == (False, None)
        await db.close()
    run(go())

def test_delete_guild_removes_everything(tmp_path):
    async def go():
        db = Database(str(tmp_path / "test.db"))
        await db.connect()
        config = await db.editConfig(1)
        await db.saveConfig(1, config, author_id=5)
        await db.addCase(1, "warn", 10, 5, "spam")
        await db.addCase(2, "warn", 10, 5, "spam")
        await db.schedule(1, 10, "unban", 100)
        await db.saveRoles(1, 10, ["123"])

        await db.deleteGuild(1)

        assert await db.userCases(1, 10) == []
        assert await db.configHistory(1) == []
        assert await db.dueActions(10**12) == []
        assert await db.popRoles(1, 10) == []
        assert len(await db.userCases(2, 10)) == 1 # other guilds untouched
        await db.close()
    run(go())
