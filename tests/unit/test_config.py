import os
import stat

import pytest
import yaml

from agentville.collector.config import load_or_create, parse


def test_first_start_creates_private_config_with_stable_id(tmp_path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex-work").mkdir()
    path = tmp_path / "cfg" / "config.yaml"
    first = load_or_create(str(path), str(home))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert first.host_id
    assert [c.account_alias for c in first.codex_homes] == ["personal", "work"]
    assert first.claude_home == str(home / ".claude")
    second = load_or_create(str(path), str(home))
    assert second.host_id == first.host_id


def test_existing_config_is_not_rewritten(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"host": {"id": "branch-1", "alias": "Minas Tirith", "time": "Third Age"}}))
    before = path.read_text()
    config = load_or_create(str(path), str(tmp_path))
    assert (config.host_id, config.alias, config.time) == ("branch-1", "Minas Tirith", "Third Age")
    assert path.read_text() == before


def test_missing_host_id_is_rejected():
    with pytest.raises(ValueError):
        parse({"host": {"alias": "x"}})


def test_thresholds_override_defaults():
    config = parse({"host": {"id": "b"}, "thresholds": {"leave": 60, "unknown": 1}})
    assert config.thresholds == {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 60}


@pytest.mark.parametrize("document", [
    {"collector": {"heartbeat_interval": 0}},
    {"thresholds": {"phone": -1}},
    {"thresholds": {"phone": 600, "doze": 300}},
    {"thresholds": {"lounge": 1000}},
])
def test_invalid_values_are_rejected(document):
    with pytest.raises(ValueError):
        parse({"host": {"id": "b"}, **document})


def test_token_in_group_readable_config_is_refused(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"host": {"id": "b"}, "hq": {"token": "secret"}}))
    path.chmod(0o640)
    with pytest.raises(SystemExit, match="chmod 600"):
        load_or_create(str(path), str(tmp_path))
    path.chmod(0o600)
    assert load_or_create(str(path), str(tmp_path)).hq_token == "secret"


def test_condition_rules_first_match_wins():
    config = parse({
        "host": {"id": "b"},
        "conditions": [
            {"provider": "claude", "model": "model-a*", "effort": "high", "condition": "study-mode"},
            {"provider": "*", "effort": "low", "condition": "lazy"},
        ],
    })
    assert config.condition_for("claude", "model-a-1", {"effort": "high"}) == "study-mode"
    assert config.condition_for("codex", "model-a-1", {"effort": "high"}) == "normal"
    assert config.condition_for("codex", None, {"effort": "low"}) == "lazy"
    assert config.condition_for("claude", None, {}) == "normal"


def test_empty_conditions_disable_mapping():
    config = parse({"host": {"id": "b"}, "conditions": []})
    assert config.condition_for("codex", None, {"effort": "high"}) == "normal"


def test_posix_tz_is_not_used_as_zone_name(monkeypatch):
    from agentville.collector import config as cfg
    monkeypatch.setenv("TZ", "UTC0")
    assert cfg.local_timezone() != "UTC0"
    monkeypatch.setenv("TZ", ":Asia/Seoul")
    assert cfg.local_timezone() == "Asia/Seoul"
