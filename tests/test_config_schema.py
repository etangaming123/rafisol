import copy
import json
import pathlib

import pytest

import config_schema as cs

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample_export.json"

def sampleExport():
    return json.loads(FIXTURE.read_text())

def guildFromMeta(meta, bot_top=9):
    channels = {c["id"]: c["type"] for c in meta["channels"]}
    roles = {r["id"]: {"position": r["position"], "managed": r["managed"] and r["name"] != "@everyone", "default": r["name"] == "@everyone"} for r in meta["roles"]}
    return cs.GuildInfo(channels, roles, bot_top, meta["guild_id"])

def test_defaults_validate_cleanly():
    clean, warnings = cs.validateConfig(cs.defaults())
    assert warnings == []
    assert clean == cs.defaults()

def test_sample_export_round_trips():
    raw = sampleExport()
    clean, warnings = cs.validateConfig(raw, guildFromMeta(raw["_meta"]))
    assert warnings == []
    expected = {k: v for k, v in raw.items() if k != "_meta"}
    assert clean == expected

def test_bytes_input_and_size_limit():
    raw = json.dumps(sampleExport()).encode()
    clean, _ = cs.validateConfig(raw)
    assert clean["posts"][0]["id"] == "rules"
    with pytest.raises(ValueError):
        cs.validateConfig(b" " * (cs.MAX_IMPORT_BYTES + 1))

def test_garbage_is_rejected():
    for bad in (b"not json", b"[1, 2]", b"\xff\xfe"):
        with pytest.raises(ValueError):
            cs.validateConfig(bad)
    with pytest.raises(ValueError):
        cs.validateConfig({"schema": cs.SCHEMA_VERSION + 1})

def test_unknown_keys_dropped_with_warning():
    raw = cs.defaults()
    raw["sneaky"] = True
    raw["general"]["extra"] = 1
    clean, warnings = cs.validateConfig(raw)
    assert "sneaky" not in clean and "extra" not in clean["general"]
    assert any("sneaky" in w for w in warnings)

def test_missing_channels_and_roles_removed():
    raw = sampleExport()
    raw["logging"]["channels"]["messages"] = "1399999999999999999"
    raw["permissions"]["mod_roles"].append("1399999999999999998")
    clean, warnings = cs.validateConfig(raw, guildFromMeta(raw["_meta"]))
    assert clean["logging"]["channels"]["messages"] is None
    assert "1399999999999999998" not in clean["permissions"]["mod_roles"]
    assert len(warnings) == 2

def test_wrong_channel_type_removed():
    raw = sampleExport()
    raw["welcome"]["join"]["channel"] = raw["_meta"]["channels"][-1]["id"] # a category
    clean, warnings = cs.validateConfig(raw, guildFromMeta(raw["_meta"]))
    assert clean["welcome"]["join"]["channel"] is None
    assert warnings

def test_managed_roles_cant_be_given_out():
    raw = sampleExport()
    booster = next(r["id"] for r in raw["_meta"]["roles"] if r["name"] == "Server Booster")
    raw["welcome"]["autoroles"].append(booster)
    clean, warnings = cs.validateConfig(raw, guildFromMeta(raw["_meta"]))
    assert booster not in clean["welcome"]["autoroles"]

def test_numeric_snowflakes_accepted_but_warned():
    raw = cs.defaults()
    raw["logging"]["channels"]["messages"] = 1300000000000000007
    clean, warnings = cs.validateConfig(raw)
    assert clean["logging"]["channels"]["messages"] == "1300000000000000007"
    assert warnings

def test_values_clamped_and_types_fixed():
    raw = cs.defaults()
    raw["automod"]["rules"]["mentions"]["max"] = 9999
    raw["automod"]["rules"]["spam"]["seconds"] = "five"
    raw["general"]["embed_color"] = "purple"
    raw["moderation"]["warn_thresholds"] = [{"count": 3, "action": "explode", "duration": "forever"}, {"count": 3, "action": "ban"}]
    clean, warnings = cs.validateConfig(raw)
    assert clean["automod"]["rules"]["mentions"]["max"] == 50
    assert clean["automod"]["rules"]["spam"]["seconds"] == cs.DEFAULT_CONFIG["automod"]["rules"]["spam"]["seconds"]
    assert clean["general"]["embed_color"] == cs.DEFAULT_CONFIG["general"]["embed_color"]
    assert clean["moderation"]["warn_thresholds"] == [{"count": 3, "action": "timeout", "duration": "1h"}]
    assert len(warnings) >= 5

def test_embed_limits():
    raw = sampleExport()
    embed = raw["posts"][0]["embeds"][0]
    embed["fields"] = [{"name": f"f{i}", "value": "v", "inline": True} for i in range(30)]
    embed["title"] = "x" * 500
    embed["image"] = "javascript:alert(1)"
    clean, warnings = cs.validateConfig(raw)
    out = clean["posts"][0]["embeds"][0]
    assert len(out["fields"]) == 25
    assert len(out["title"]) == 256
    assert out["image"] == ""

def test_duplicate_ids_and_bad_slugs():
    raw = sampleExport()
    raw["posts"].append(copy.deepcopy(raw["posts"][0]))
    raw["posts"].append({**copy.deepcopy(raw["posts"][0]), "id": "Bad Id!"})
    clean, warnings = cs.validateConfig(raw)
    assert [p["id"] for p in clean["posts"]] == ["rules"]
    assert len(warnings) == 2

def test_webhook_username_rules():
    raw = sampleExport()
    raw["posts"][0]["username"] = "Discord Staff"
    clean, warnings = cs.validateConfig(raw)
    assert clean["posts"][0]["username"] == ""

def test_message_ids_carried_over_from_current():
    raw = sampleExport()
    current, _ = cs.validateConfig(raw)
    current["posts"][0]["message_id"] = "1311111111111111111"
    current["posts"][0]["posted_channel"] = current["posts"][0]["channel"]
    current["reaction_roles"][0]["message_id"] = "1322222222222222222"
    clean, _ = cs.validateConfig(raw, current=current)
    assert clean["posts"][0]["message_id"] == "1311111111111111111"
    assert clean["posts"][0]["posted_channel"] == current["posts"][0]["channel"]
    assert clean["reaction_roles"][0]["message_id"] == "1322222222222222222"

def test_honeypot_section():
    raw = cs.defaults()
    raw["honeypot"].update({"enabled": True, "action": "nuke", "delete_seconds": 5, "duration": "60d"})
    clean, warnings = cs.validateConfig(raw)
    assert clean["honeypot"]["action"] == "softban"
    assert clean["honeypot"]["delete_seconds"] == 604800
    assert clean["honeypot"]["duration"] == "1d"
    assert len(warnings) == 3

def test_fill_defaults_adds_new_keys():
    old = cs.defaults()
    del old["honeypot"]
    del old["logging"]["events"]["voice_stream"]
    filled = cs.fillDefaults(old)
    assert filled["honeypot"] == cs.DEFAULT_CONFIG["honeypot"]
    assert filled["logging"]["events"]["voice_stream"] is True

def test_changed_sections():
    a = cs.defaults()
    b = cs.defaults()
    b["automod"]["enabled"] = True
    assert cs.changedSections(a, b) == ["automod"]
