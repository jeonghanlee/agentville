from datetime import UTC, datetime, timedelta

from agentville.common.protocol import Envelope
from agentville.hq.store import Store

T0 = datetime(2026, 1, 1, tzinfo=UTC)
BRANCH = {"alias": "b", "country": "", "time": "UTC", "location": "", "thresholds": {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}}


def agent(agent_id, on_duty=True):
    return {"agent_id": agent_id, "project_id": "p", "project_alias": "p", "provider": "claude", "seat": 1,
            "presence": "on_duty" if on_duty else "off_duty", "presence_since": "2026-01-01T00:00:00.000Z",
            "instance": {"instance_id": "i", "started_at": "2026-01-01T00:00:00.000Z", "runtime": {}} if on_duty else None}


def activity(agent_id, state="idle"):
    return {"agent_id": agent_id, "instance_id": "i", "state": state, "state_since": "2026-01-01T00:00:00.000Z",
            "source": "session_file", "confidence": "high"}


def snapshot(agents, activities):
    return {"branch": BRANCH, "agents": agents, "activities": activities, "contractors": []}


def store(tmp_path):
    return Store(str(tmp_path / "hq.sqlite3"))


def test_snapshot_replaces_branch_state_and_changes_apply(tmp_path):
    s, env = store(tmp_path), Envelope("b1")
    r = s.ingest("b1", [env.wrap("snapshot", T0, snapshot([agent("a1"), agent("a2")], [activity("a1")]), T0)], T0)
    assert (r.accepted, r.need_snapshot) == (1, False)
    s.ingest("b1", [env.wrap("activity", T0, activity("a1", "working"), T0)], T0)
    state = s.state(T0)
    assert {a["agent_id"] for a in state["agents"]} == {"a1", "a2"}
    assert state["activities"][0]["state"] == "working"
    s.ingest("b1", [env.wrap("snapshot", T0, snapshot([agent("a3")], []), T0)], T0)
    state = s.state(T0)
    assert [a["agent_id"] for a in state["agents"]] == ["a3"] and state["activities"] == []


def test_duplicates_stale_and_gaps(tmp_path):
    s, env = store(tmp_path), Envelope("b1")
    s.ingest("b1", [env.wrap("snapshot", T0, snapshot([], []), T0)], T0)
    beat = env.wrap("heartbeat", T0, {"interval": 30}, T0)
    assert s.ingest("b1", [beat], T0).accepted == 1
    assert s.ingest("b1", [beat], T0).duplicates == 1
    env.seq = 5
    gap = s.ingest("b1", [env.wrap("heartbeat", T0, {"interval": 30}, T0)], T0)
    assert gap.need_snapshot and gap.accepted == 1
    env.seq = 2
    assert s.ingest("b1", [env.wrap("heartbeat", T0, {"interval": 30}, T0)], T0).stale == 1


def test_unknown_branch_without_snapshot_requests_one(tmp_path):
    s = store(tmp_path)
    assert s.ingest("b2", [Envelope("b2").wrap("heartbeat", T0, {"interval": 30}, T0)], T0).need_snapshot


def test_off_duty_agent_drops_activity(tmp_path):
    s, env = store(tmp_path), Envelope("b1")
    s.ingest("b1", [env.wrap("snapshot", T0, snapshot([agent("a1")], [activity("a1")]), T0)], T0)
    s.ingest("b1", [env.wrap("agent", T0, agent("a1", on_duty=False), T0)], T0)
    state = s.state(T0)
    assert state["agents"][0]["presence"] == "off_duty" and state["activities"] == []


def test_branch_unreachable_after_three_heartbeats(tmp_path):
    s, env = store(tmp_path), Envelope("b1")
    s.ingest("b1", [env.wrap("snapshot", T0, snapshot([], []), T0), env.wrap("heartbeat", T0, {"interval": 10}, T0)], T0)
    assert s.state(T0 + timedelta(seconds=30))["branches"][0]["reachable"]
    assert not s.state(T0 + timedelta(seconds=31))["branches"][0]["reachable"]


def test_prune_removes_old_messages_only(tmp_path):
    s, env = store(tmp_path), Envelope("b1")
    s.ingest("b1", [env.wrap("snapshot", T0, snapshot([agent("a1")], []), T0)], T0)
    assert s.prune(T0 + timedelta(days=1)) == 1
    assert len(s.state(T0)["agents"]) == 1


def test_branch_that_lost_its_sequence_is_reset_by_snapshot(tmp_path):
    s, env = store(tmp_path), Envelope("b1")
    s.ingest("b1", [env.wrap("snapshot", T0, snapshot([agent("old")], []), T0),
                    env.wrap("heartbeat", T0, {"interval": 30}, T0), env.wrap("heartbeat", T0, {"interval": 30}, T0)], T0)
    fresh = Envelope("b1")
    result = s.ingest("b1", [fresh.wrap("snapshot", T0, snapshot([agent("new")], []), T0),
                             fresh.wrap("heartbeat", T0, {"interval": 30}, T0)], T0)
    assert (result.accepted, result.duplicates, result.need_snapshot) == (2, 0, False)
    assert [a["agent_id"] for a in s.state(T0)["agents"]] == ["new"]


def test_same_agent_id_on_two_branches_is_kept_apart(tmp_path):
    s = store(tmp_path)
    s.ingest("b1", [Envelope("b1").wrap("snapshot", T0, snapshot([agent("a1")], []), T0)], T0)
    s.ingest("b2", [Envelope("b2").wrap("snapshot", T0, snapshot([agent("a1")], []), T0)], T0)
    assert sorted(a["branch_id"] for a in s.state(T0)["agents"]) == ["b1", "b2"]


def test_branch_without_heartbeat_uses_default_interval(tmp_path):
    s = store(tmp_path)
    s.ingest("b1", [Envelope("b1").wrap("snapshot", T0, snapshot([], []), T0)], T0)
    assert s.state(T0 + timedelta(seconds=90))["branches"][0]["reachable"]
    assert not s.state(T0 + timedelta(seconds=91))["branches"][0]["reachable"]


def test_delayed_snapshot_does_not_replace_newer_state(tmp_path):
    s, env = store(tmp_path), Envelope("b1")
    late = env.wrap("snapshot", T0, snapshot([agent("old")], []), T0)
    s.ingest("b1", [env.wrap("snapshot", T0, snapshot([agent("new")], []), T0 + timedelta(seconds=6))], T0)
    result = s.ingest("b1", [late], T0)
    assert (result.accepted, result.stale) == (0, 1)
    assert [a["agent_id"] for a in s.state(T0)["agents"]] == ["new"]


def test_existing_database_gains_last_sent_column(tmp_path):
    import sqlite3

    path = str(tmp_path / "hq.sqlite3")
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE branches (branch_id TEXT PRIMARY KEY, payload TEXT, last_seq INTEGER, "
               "last_seen_at TEXT NOT NULL, heartbeat_interval INTEGER)")
    db.commit()
    db.close()
    s, env = Store(path), Envelope("b1")
    assert s.ingest("b1", [env.wrap("snapshot", T0, snapshot([], []), T0)], T0).accepted == 1
