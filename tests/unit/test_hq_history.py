import os
import sqlite3
import threading
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agentville.common.protocol import Envelope, iso
from agentville.hq.app import create_app
from agentville.hq.store import Store

T0 = datetime(2026, 1, 1, tzinfo=UTC)
BRANCH = {"alias": "b", "country": "", "time": "UTC", "location": "", "thresholds": {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}}


def s(seconds):
    return T0 + timedelta(seconds=seconds)


def agent(agent_id, on_duty=True, seat=1):
    return {"agent_id": agent_id, "project_id": "p", "project_alias": "p", "provider": "claude", "seat": seat,
            "presence": "on_duty" if on_duty else "off_duty", "presence_since": iso(T0),
            "instance": {"instance_id": "i-" + agent_id, "started_at": iso(T0), "runtime": {}} if on_duty else None}


def activity(agent_id, state="idle", since=0, workload=0):
    return {"agent_id": agent_id, "instance_id": "i-" + agent_id, "state": state, "state_since": iso(s(since)),
            "source": "session_file", "confidence": "high", "workload": workload}


def snapshot(agents, activities):
    return {"branch": BRANCH, "agents": agents, "activities": activities, "contractors": []}


class Branch:
    """A Branch that sends one message per call, received when it is sent."""

    def __init__(self, store, branch_id="b1"):
        self.store, self.env, self.branch_id = store, Envelope(branch_id), branch_id

    def send(self, seconds, kind, payload, event=None):
        at = s(seconds)
        message = self.env.wrap(kind, s(event) if event is not None else at, payload, at)
        return self.store.ingest(self.branch_id, [message], at)

    def beats(self, first, last, interval=10):
        for second in range(first, last + 1, interval):
            self.send(second, "heartbeat", {"interval": interval})


def _store(tmp_path):
    return Store(str(tmp_path / "hq.sqlite3"))


def _states(state):
    return {a["agent_id"]: a["state"] for a in state["activities"]}


def test_state_at_reproduces_earlier_state(tmp_path):
    store = _store(tmp_path)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1"), agent("a2")], [activity("a1"), activity("a2")]))
    branch.send(60, "activity", activity("a1", "working", 60))
    branch.send(120, "agent", agent("a1", on_duty=False))
    assert _states(store.state_at(s(30))) == {"a1": "idle", "a2": "idle"}
    assert _states(store.state_at(s(90))) == {"a1": "working", "a2": "idle"}
    later = store.state_at(s(150))
    assert _states(later) == {"a2": "idle"}
    assert {a["agent_id"]: a["presence"] for a in later["agents"]} == {"a1": "off_duty", "a2": "on_duty"}
    current = store.state(s(150))
    for key in ("agents", "activities", "contractors"):
        assert sorted(current[key], key=str) == sorted(later[key], key=str)
    assert later["branches"][0]["branch"] == BRANCH and later["branches"][0]["last_seq"] == 3


def test_snapshot_records_only_the_keys_it_changes(tmp_path):
    store = _store(tmp_path)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1"), agent("a2")], [activity("a1"), activity("a2")]))
    db = sqlite3.connect(str(tmp_path / "hq.sqlite3"))
    before = db.execute("SELECT COUNT(*) FROM changes").fetchone()[0]
    assert before == 7
    branch.send(10, "snapshot", snapshot([agent("a1")], [activity("a1", "working", 10)]))
    rows = db.execute("SELECT kind, key, payload IS NULL FROM changes ORDER BY id").fetchall()[before:]
    assert sorted(rows) == [("activity", "a1", 0), ("activity", "a2", 1), ("agent", "a2", 1)]


def test_change_times_of_one_key_never_go_backwards(tmp_path):
    store = _store(tmp_path)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1")], [activity("a1")]))
    branch.send(60, "activity", activity("a1", "working", 60))
    # An older fact applied later is placed at the time of the previous change of that key.
    branch.send(70, "activity", activity("a1", "waiting", 30), event=30)
    assert _states(store.state_at(s(45))) == {"a1": "idle"}
    assert _states(store.state_at(s(60))) == {"a1": "waiting"}
    # A fact ahead of HQ's clock is placed at its receipt.
    branch.send(80, "activity", activity("a1", "idle", 80), event=3600)
    db = sqlite3.connect(str(tmp_path / "hq.sqlite3"))
    assert db.execute("SELECT MAX(at) FROM changes").fetchone()[0] == iso(s(80))


def test_state_at_now_equals_state_with_a_branch_clock_ahead(tmp_path):
    store = _store(tmp_path)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1")], [activity("a1", "working", 0)]))
    # The Branch clock is 20 s ahead of HQ's.
    branch.send(100, "activity", activity("a1", "waiting", 120), event=120)
    assert _states(store.state(s(100))) == _states(store.state_at(s(100))) == {"a1": "waiting"}
    # Later changes of the key are still placed after it.
    branch.send(101, "activity", activity("a1", "working", 121), event=121)
    assert _states(store.state_at(s(100))) == {"a1": "waiting"} and _states(store.state_at(s(101))) == {"a1": "working"}


def test_reachability_at_a_past_time_follows_received_messages(tmp_path):
    store = _store(tmp_path)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([], []))
    branch.beats(0, 10)
    branch.beats(100, 120)
    reachable = lambda seconds: store.state_at(s(seconds))["branches"][0]["reachable"]  # noqa: E731
    assert reachable(40) and not reachable(41) and not reachable(99) and reachable(100)
    assert store.state_at(s(50))["branches"][0]["last_seen_at"] == iso(s(10))


def test_existing_database_seeds_the_baseline_from_current_state(tmp_path):
    path = str(tmp_path / "hq.sqlite3")
    old = Store(path)
    Branch(old).send(0, "snapshot", snapshot([agent("a1")], [activity("a1", "working")]))
    old.close()
    db = sqlite3.connect(path)
    db.executescript("DROP TABLE changes; DROP TABLE baseline; DROP TABLE meta;")
    db.close()
    upgraded = Store(path, now=s(500))
    assert upgraded.history_range(s(600)) == (s(500), s(600))
    assert _states(upgraded.state_at(s(500))) == {"a1": "working"}
    assert upgraded.state_at(s(500))["branches"][0]["branch"] == BRANCH
    upgraded.close()
    assert Store(path, now=s(900)).history_range(s(900))[0] == s(500)


def test_empty_database_starts_history_at_first_message(tmp_path):
    store = _store(tmp_path)
    assert store.history_range(s(0)) == (None, s(0))
    Branch(store).send(40, "snapshot", snapshot([], []))
    assert store.history_range(s(50))[0] == s(40)


def test_prune_folds_old_changes_into_the_baseline(tmp_path):
    store = _store(tmp_path)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1"), agent("a2")], [activity("a1"), activity("a2")]))
    branch.send(60, "activity", activity("a1", "working", 60))
    branch.send(70, "agent", agent("a2", on_duty=False))
    branch.send(200, "activity", activity("a1", "waiting", 200))
    expected = store.state_at(s(100))
    assert store.prune(s(100)) == 3
    assert store.history_range(s(300))[0] == s(100)
    assert store.state_at(s(100))["activities"] == expected["activities"]
    assert store.state_at(s(100))["agents"] == expected["agents"]
    assert _states(store.state_at(s(250))) == {"a1": "waiting"}
    db = sqlite3.connect(str(tmp_path / "hq.sqlite3"))
    assert db.execute("SELECT COUNT(*) FROM changes WHERE at < ?", (iso(s(100)),)).fetchone()[0] == 0
    # A second prune with an earlier cutoff changes nothing.
    store.prune(s(50))
    assert store.history_range(s(300))[0] == s(100)


def _day(store):
    """One colleague: idle, working, waiting twice, an error, a limit; the Branch is silent from 200 to 300 s."""
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1"), agent("a2", on_duty=False, seat=2)], [activity("a1")]))
    branch.beats(0, 160)
    branch.send(100, "activity", activity("a1", "working", 100))
    branch.send(130, "activity", activity("a1", "working", 100, workload=3))
    branch.send(150, "activity", activity("a1", "waiting", 150))
    branch.beats(300, 400)
    branch.send(300, "activity", activity("a1", "waiting", 150, workload=1))
    branch.send(320, "activity", activity("a1", "idle", 320))
    branch.send(330, "activity", activity("a1", "waiting", 330))
    branch.send(340, "activity", activity("a1", "error", 340))
    branch.send(350, "activity", activity("a1", "limited", 350))
    branch.send(380, "agent", agent("a1", on_duty=False))
    return branch


def test_work_log_sums_states_gaps_and_entries(tmp_path):
    store = _store(tmp_path)
    _day(store)
    log = store.worklog(s(0), s(400), s(400))
    assert [r["agent_id"] for r in log["rows"]] == ["a1"]
    row = log["rows"][0]
    seconds = row["seconds"]
    # The Branch is observed until 190 s (three 10 s intervals after 160 s) and again from 300 s.
    assert seconds["unobserved"] == 110
    assert seconds["on_duty"] == 270
    assert (seconds["idle"], seconds["working"], seconds["waiting"], seconds["error"], seconds["limited"]) == (110, 50, 70, 10, 30)
    assert (row["waits"], row["longest_wait"], row["errors"], row["limits"]) == (2, 60, 1, 1)
    assert (row["project_id"], row["provider"], row["seat"], row["alias"]) == ("p", "claude", 1, None)
    assert log["branches"] == [{"branch_id": "b1", "branch": BRANCH}]


def test_work_log_is_clipped_to_the_period(tmp_path):
    store = _store(tmp_path)
    _day(store)
    row = store.worklog(s(120), s(160), s(400))["rows"][0]
    assert row["seconds"]["working"] == 30 and row["seconds"]["waiting"] == 10 and row["waits"] == 1
    # A period ending after now ends at now; one starting before the kept history starts with it.
    log = store.worklog(s(-3600), s(9999), s(120))
    assert (log["from"], log["to"]) == (iso(s(0)), iso(s(120)))
    assert log["rows"][0]["seconds"]["on_duty"] == 120


def test_changes_list_transitions_in_time_order(tmp_path):
    store = _store(tmp_path)
    _day(store)
    result = store.changes(s(0), s(400), s(400))
    kinds = [(c["at"], c["kind"], c.get("state") or c.get("presence") or c.get("reachable")) for c in result["changes"]]
    assert kinds == [
        (iso(s(100)), "activity", "working"), (iso(s(150)), "activity", "waiting"),
        (iso(s(190)), "reachability", False), (iso(s(300)), "reachability", True),
        (iso(s(320)), "activity", "idle"), (iso(s(330)), "activity", "waiting"), (iso(s(340)), "activity", "error"),
        (iso(s(350)), "activity", "limited"), (iso(s(380)), "presence", "off_duty"),
    ]
    assert [a["agent_id"] for a in result["agents"]] == ["a1"] and not result["truncated"]
    assert set(result["changes"][0]) == {"at", "kind", "branch_id", "agent_id", "state", "state_since"}
    limited = store.changes(s(0), s(400), s(400), limit=2)
    assert limited["truncated"] and [c["kind"] for c in limited["changes"]] == ["activity", "presence"]
    assert store.changes(s(0), s(400), s(400), branch_id="other")["changes"] == []


def _client(store, now, **options):
    return TestClient(create_app(store, clock=lambda: now, loopback=frozenset({"testclient"}),
                                 hosts=frozenset({"testserver"}), **options))


def test_history_endpoints(tmp_path):
    store = _store(tmp_path)
    _day(store)
    client = _client(store, s(400), viewer_token="v")
    auth = {"Authorization": "Bearer v"}
    for path in ("/api/v1/history", "/api/v1/state?at=" + iso(s(10)),
                 f"/api/v1/changes?from={iso(s(0))}&to={iso(s(400))}", f"/api/v1/worklog?from={iso(s(0))}&to={iso(s(400))}"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=auth).status_code == 200
    assert client.get("/api/v1/history", headers=auth).json() == {"from": iso(s(0)), "to": iso(s(400))}
    state = client.get("/api/v1/state", params={"at": iso(s(110))}, headers=auth).json()
    assert _states(state) == {"a1": "working"} and state["branches"][0]["reachable"]
    assert client.get("/api/v1/state", params={"at": "2026-01-01T00:03:20+00:00"}, headers=auth).json()["branches"][0]["reachable"] is False
    worklog = client.get("/api/v1/worklog", params={"from": iso(s(0)), "to": iso(s(400)), "branch_id": "b1"}, headers=auth).json()
    assert worklog["rows"][0]["seconds"]["working"] == 50
    changes = client.get("/api/v1/changes", params={"from": iso(s(0)), "to": iso(s(400))}, headers=auth).json()
    assert len(changes["changes"]) == 9


def test_history_endpoints_reject_bad_times(tmp_path):
    store = _store(tmp_path)
    Branch(store).send(0, "snapshot", snapshot([], []))
    client = _client(store, s(100))
    for at in (iso(s(-1)), iso(s(101)), "2026-01-01T00:00:10", "yesterday"):
        assert client.get("/api/v1/state", params={"at": at}).status_code == 400, at
    for params in ({"from": iso(s(10))}, {"from": iso(s(10)), "to": iso(s(10))},
                   {"from": iso(s(0)), "to": iso(s(0) + timedelta(days=32))}, {"from": "x", "to": iso(s(10))}):
        assert client.get("/api/v1/worklog", params=params).status_code == 400, params
        assert client.get("/api/v1/changes", params=params).status_code == 400, params
    empty = _client(Store(str(tmp_path / "empty.sqlite3")), s(100))
    assert empty.get("/api/v1/history").json() == {"from": None, "to": iso(s(100))}
    assert empty.get("/api/v1/state", params={"at": iso(s(50))}).status_code == 400
    assert empty.get("/api/v1/worklog", params={"from": iso(s(0)), "to": iso(s(50))}).json()["rows"] == []


def _ingest_hours(store, hours=5):
    """A colleague changing state every 7 minutes for some hours, received when sent; the live state after each."""
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1"), agent("a2", seat=2)], [activity("a1"), activity("a2")]))
    live = {0: store.state(s(0))}
    states = ["working", "waiting", "idle", "error"]
    for n, second in enumerate(range(420, hours * 3600, 420)):
        if n % 9 == 4:
            branch.send(second, "agent", agent("a2", on_duty=n % 2 == 0, seat=2))
        else:
            branch.send(second, "activity", activity("a1", states[n % 4], second))
        live[second] = store.state(s(second))
    return branch, live


def _without(state):
    return {key: sorted(state[key], key=str) for key in ("agents", "activities", "contractors")}


def test_checkpoints_reproduce_the_live_state(tmp_path):
    store = _store(tmp_path)
    _branch, live = _ingest_hours(store)
    db = sqlite3.connect(str(tmp_path / "hq.sqlite3"))
    assert [row[0] for row in db.execute("SELECT at FROM checkpoints ORDER BY at")] == [iso(s(h * 3600)) for h in (1, 2, 3, 4)]
    for second, state in live.items():
        assert _without(store.state_at(s(second))) == _without(state), second
    # The same answers without checkpoints: they only shorten the work.
    expected = {second: store.state_at(s(second)) for second in live}
    log = store.worklog(s(0), s(5 * 3600), s(5 * 3600))
    db.execute("DELETE FROM checkpoints")
    db.commit()
    assert all(store.state_at(s(second)) == state for second, state in expected.items())
    assert store.worklog(s(0), s(5 * 3600), s(5 * 3600)) == log


def test_a_late_change_updates_the_checkpoints_after_it(tmp_path):
    store = _store(tmp_path)
    branch, _live = _ingest_hours(store)
    # Received at 5 h, a new colleague of 30 min earlier; and a new Contractor of 3.5 h earlier.
    branch.send(5 * 3600, "agent", agent("a3", seat=3), event=5 * 3600 - 1800)
    contractor = {"contractor_id": "c1", "parent_agent_id": "a1", "provider": "claude", "status": "hired", "state": "working",
                  "state_since": iso(s(5400))}
    branch.send(5 * 3600 + 1, "contractor", contractor, event=5400)
    times = [s(5400 - 1), s(5400), s(3 * 3600), s(4 * 3600), s(5 * 3600 - 1800), s(5 * 3600 + 1)]
    with_checkpoints = [store.state_at(t) for t in times]
    assert ["a3" in {a["agent_id"] for a in state["agents"]} for state in with_checkpoints] == [False] * 4 + [True] * 2
    assert [len(state["contractors"]) for state in with_checkpoints] == [0, 1, 1, 1, 1, 1]
    db = sqlite3.connect(str(tmp_path / "hq.sqlite3"))
    db.execute("DELETE FROM checkpoints")
    db.commit()
    assert [store.state_at(t) for t in times] == with_checkpoints


def test_prune_keeps_checkpoints_consistent(tmp_path):
    store = _store(tmp_path)
    _branch, live = _ingest_hours(store)
    cutoff = s(2 * 3600 + 600)
    expected = {second: store.state_at(s(second)) for second in live if s(second) >= cutoff}
    store.prune(cutoff)
    db = sqlite3.connect(str(tmp_path / "hq.sqlite3"))
    assert db.execute("SELECT MIN(at) FROM checkpoints").fetchone()[0] == iso(s(3 * 3600))
    # Keys whose change was folded now take the baseline payload.
    assert db.execute("SELECT COUNT(*) FROM checkpoint_keys WHERE change_id IS NULL").fetchone()[0] > 0
    assert all(store.state_at(s(second)) == state for second, state in expected.items())
    db.execute("DELETE FROM checkpoints")
    db.commit()
    assert all(store.state_at(s(second)) == state for second, state in expected.items())


def test_an_existing_history_gets_checkpoints_when_opened(tmp_path):
    path = str(tmp_path / "hq.sqlite3")
    store = _store(tmp_path)
    _branch, live = _ingest_hours(store, hours=3)
    store.close()
    db = sqlite3.connect(path)
    db.execute("DELETE FROM checkpoints")
    db.execute("DELETE FROM checkpoint_keys")
    db.commit()
    reopened = Store(path, now=s(3 * 3600 + 5))
    assert [row[0] for row in db.execute("SELECT at FROM checkpoints ORDER BY at")] == [iso(s(h * 3600)) for h in (1, 2, 3)]
    assert all(_without(reopened.state_at(s(second))) == _without(state) for second, state in live.items())


def test_history_reads_take_neither_the_lock_nor_the_writer(tmp_path):
    store = _store(tmp_path)
    branch, _live = _ingest_hours(store, hours=2)
    results = []

    def read():
        results.append(store.state_at(s(3000)))
        results.append(store.worklog(s(0), s(7200), s(7200)))
        results.append(store.changes(s(0), s(7200), s(7200)))

    # An ingest in progress holds the lock; history reads still finish.
    with store._lock:
        reader = threading.Thread(target=read)
        reader.start()
        reader.join(5)
    assert len(results) == 3
    # A read in progress does not hold up ingest.
    with store._reading():
        assert branch.send(7300, "activity", activity("a1", "working", 7300)).accepted == 1
    assert _states(store.state(s(7300)))["a1"] == "working"


def test_an_activity_removed_and_restored_is_not_a_new_entry(tmp_path):
    store = _store(tmp_path)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1")], [activity("a1", "waiting", 0)]))
    branch.send(10, "activity", activity("a1", "waiting", 10))
    branch.send(20, "snapshot", snapshot([agent("a1")], []))
    branch.send(30, "snapshot", snapshot([agent("a1")], [activity("a1", "waiting", 10)]))
    row = store.worklog(s(0), s(40), s(40))["rows"][0]
    assert (row["waits"], row["seconds"]["waiting"], row["longest_wait"], row["seconds"]["unknown"]) == (1, 30, 20, 10)
    changes = store.changes(s(0), s(40), s(40))["changes"]
    assert [(c["at"], c["state_since"]) for c in changes] == [(iso(s(10)), iso(s(10)))]
    # A new state_since after the removal is a new entry.
    branch.send(50, "snapshot", snapshot([agent("a1")], []))
    branch.send(60, "snapshot", snapshot([agent("a1")], [activity("a1", "waiting", 55)]))
    assert store.worklog(s(0), s(70), s(70))["rows"][0]["waits"] == 2


def test_a_period_outside_the_kept_history_is_empty(tmp_path):
    store = _store(tmp_path)
    Branch(store).send(100, "snapshot", snapshot([agent("a1")], [activity("a1", "working", 100)]))
    assert store.worklog(s(0), s(50), s(200)) == {"from": None, "to": None, "rows": [], "branches": []}
    assert store.changes(s(300), s(400), s(200)) == {"from": None, "to": None, "changes": [], "truncated": False,
                                                     "agents": [], "branches": []}
    client = _client(store, s(200))
    assert client.get("/api/v1/worklog", params={"from": iso(s(0)), "to": iso(s(50))}).json()["from"] is None
    empty = _client(Store(str(tmp_path / "empty.sqlite3")), s(100))
    assert empty.get("/api/v1/changes", params={"from": iso(s(0)), "to": iso(s(50))}).json()["to"] is None


def test_times_outside_the_datetime_range_are_rejected(tmp_path):
    store = _store(tmp_path)
    Branch(store).send(0, "snapshot", snapshot([], []))
    client = _client(store, s(100))
    assert client.get("/api/v1/state", params={"at": "0001-01-01T00:00:00+00:01"}).status_code == 400
    assert client.get("/api/v1/worklog", params={"from": "0001-01-01T00:00:00+01:00", "to": iso(s(10))}).status_code == 400
    assert client.get("/api/v1/changes", params={"from": iso(s(0)), "to": "9999-12-31T23:59:59-01:00"}).status_code == 400
    message = Envelope("b1", seq=10).wrap("heartbeat", s(1), {"interval": 30}, s(1))
    message["event_at"] = "0001-01-01T00:00:00+01:00"
    assert client.post("/api/v1/ingest/messages", json={"messages": [message]}).status_code == 422


def test_identical_history_requests_share_one_computation(tmp_path, monkeypatch):
    store = _store(tmp_path)
    _day(store)
    calls = []
    worklog = store.worklog

    def counted(*args):
        calls.append(args)
        return worklog(*args)

    monkeypatch.setattr(store, "worklog", counted)
    client = _client(store, s(400))
    params = {"from": iso(s(0)), "to": iso(s(400))}
    first = client.get("/api/v1/worklog", params=params).json()
    assert client.get("/api/v1/worklog", params=params).json() == first
    assert len(calls) == 1
    client.get("/api/v1/worklog", params={**params, "branch_id": "b1"})
    assert len(calls) == 2


def test_a_rejected_batch_leaves_no_checkpoint_behind(tmp_path):
    store = _store(tmp_path)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1")], [activity("a1")]))
    message = Envelope("b2").wrap("heartbeat", s(7200), {"interval": 30}, s(7200))
    try:
        store.ingest("b1", [message], s(7200))
    except ValueError:
        pass
    # The checkpoint of the rolled-back batch is written again by the next ingest.
    branch.send(7200, "activity", activity("a1", "working", 7200))
    db = sqlite3.connect(str(tmp_path / "hq.sqlite3"))
    assert [row[0] for row in db.execute("SELECT at FROM checkpoints")] == [iso(s(7200))]
    assert _states(store.state_at(s(3600))) == {"a1": "idle"}


def test_a_removal_across_the_period_start_keeps_the_last_known_activity(tmp_path):
    store = _store(tmp_path)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1")], [activity("a1", "idle", 0)]))
    branch.beats(5, 400)
    branch.send(100, "activity", activity("a1", "waiting", 100))
    branch.send(200, "snapshot", snapshot([agent("a1")], []))
    branch.send(300, "snapshot", snapshot([agent("a1")], [activity("a1", "waiting", 100)]))
    # Removed before the period and restored in it with the same state and state_since: no entry, no transition.
    assert store.worklog(s(250), s(400), s(400))["rows"][0]["waits"] == 0
    assert [c for c in store.changes(s(250), s(400), s(400))["changes"] if c["kind"] == "activity"] == []
    assert store.worklog(s(0), s(400), s(400))["rows"][0]["waits"] == 1
    # Restored with a new state_since, it is an entry.
    branch.send(450, "snapshot", snapshot([agent("a1")], []))
    branch.send(500, "snapshot", snapshot([agent("a1")], [activity("a1", "waiting", 480)]))
    assert store.worklog(s(460), s(520), s(520))["rows"][0]["waits"] == 1


def test_the_log_is_truncated_although_history_reads_overlap(tmp_path):
    path = str(tmp_path / "hq.sqlite3")
    store = Store(path, wal_limit=64 * 1024)
    branch = Branch(store)
    branch.send(0, "snapshot", snapshot([agent("a1")], [activity("a1")]))
    first_open, release, second_done = threading.Event(), threading.Event(), threading.Event()

    def first():
        with store._reading() as db:
            db.execute("SELECT COUNT(*) FROM changes").fetchone()
            first_open.set()
            release.wait(5)

    def second():
        store.state_at(s(1))
        second_done.set()

    reader = threading.Thread(target=first)
    reader.start()
    assert first_open.wait(5)
    # A read transaction pins the log: it grows past the limit while the read stays open.
    for second_ in range(1, 400):
        branch.send(second_, "activity", activity("a1", "working", 0, workload=second_))
    assert os.path.getsize(path + "-wal") > 64 * 1024
    # A new history read waits while the open one finishes and the log is checkpointed.
    later = threading.Thread(target=second)
    later.start()
    assert not second_done.wait(0.3)
    release.set()
    reader.join(5)
    assert second_done.wait(5)
    later.join(5)
    store._shrinker.join(5)
    assert os.path.getsize(path + "-wal") <= 64 * 1024
    assert _states(store.state_at(s(399))) == {"a1": "working"}
