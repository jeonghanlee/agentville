import json
import os
import stat
from datetime import UTC, datetime, timedelta

import jsonschema

from agentville.common.protocol import load_schema

from agentville.collector.config import parse
from agentville.collector.main import Collector, SeqStore, main
from agentville.collector.sender import Delivery
from agentville.collector.project import Project
from agentville.common.observations import Kind, Observation, ShiftKey, Source

SCHEMA = load_schema()
T0 = datetime(2026, 1, 1, tzinfo=UTC)


class Resolver:
    def resolve(self, cwd):
        return Project("github.com/example/repo", "repo")


class ScriptedAdapter:
    def __init__(self):
        self.batches = []

    def poll(self):
        return self.batches.pop(0) if self.batches else []


def into(out):
    def deliver(messages):
        out.extend(messages)
        return Delivery(True)

    return deliver


def _obs(kind, at, **data):
    return Observation(kind, ShiftKey("claude", "1:1"), at, at, Source.SESSION_FILE, data)


def _collector(tmp_path, adapter, clock):
    config = parse({"host": {"id": "branch-1"}, "collector": {"heartbeat_interval": 30},
                    "conditions": [{"provider": "*", "effort": "high", "condition": "study-mode"}]})
    out = []
    collector = Collector(config, into(out), [adapter], Resolver(), SeqStore(str(tmp_path / "seq")), clock=clock)
    return collector, out


def test_first_tick_sends_snapshot_then_changes(tmp_path):
    now = [T0]
    adapter = ScriptedAdapter()
    adapter.batches = [
        [_obs(Kind.PROCESS_STARTED, T0, cwd="/r", session_id="s1", runtime={"type": "shell"}),
         _obs(Kind.SESSION_STATUS, T0, status="idle")],
        [_obs(Kind.MODEL_CHANGED, T0 + timedelta(seconds=1), model="m", settings={"effort": "high"})],
    ]
    collector, out = _collector(tmp_path, adapter, lambda: now[0])
    collector.tick()
    assert [m["kind"] for m in out] == ["snapshot", "heartbeat"]
    snapshot = out[0]["payload"]
    assert len(snapshot["agents"]) == 1 and snapshot["activities"][0]["state"] == "idle"
    now[0] = T0 + timedelta(seconds=1)
    collector.tick()
    assert out[-1]["kind"] == "agent" and out[-1]["payload"]["condition"] == "study-mode"
    now[0] = T0 + timedelta(seconds=31)
    collector.tick()
    assert out[-1]["kind"] == "heartbeat"
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for message in out:
        validator.validate(message)
    assert [m["seq"] for m in out] == list(range(1, len(out) + 1))


def test_sequence_resumes_after_restart(tmp_path):
    collector, out = _collector(tmp_path, ScriptedAdapter(), lambda: T0)
    collector.tick()
    last = out[-1]["seq"]
    collector2, out2 = _collector(tmp_path, ScriptedAdapter(), lambda: T0)
    collector2.tick()
    assert out2[0]["seq"] == 1001 and out2[0]["seq"] > last


def test_seq_reservation_fsyncs_directory(tmp_path, monkeypatch):
    synced = []
    fsync = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (synced.append(stat.S_ISDIR(os.fstat(fd).st_mode)), fsync(fd)))
    SeqStore(str(tmp_path / "state" / "seq")).save(5)
    assert synced[-1] is True


def test_cli_once_writes_valid_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    output = tmp_path / "messages.jsonl"
    assert main(["--once", "--output", str(output)]) == 0
    messages = [json.loads(line) for line in output.read_text().splitlines()]
    assert [m["kind"] for m in messages] == ["snapshot", "heartbeat"]
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for message in messages:
        validator.validate(message)
    assert (tmp_path / "config" / "agentville" / "config.yaml").exists()
    assert not (tmp_path / "state" / "agentville" / "seq").exists()


class FailingAdapter:
    def poll(self):
        raise RuntimeError("boom")


def test_failing_adapter_does_not_stop_others(tmp_path, capsys):
    good = ScriptedAdapter()
    good.batches = [[_obs(Kind.PROCESS_STARTED, T0, cwd="/r", session_id="s1", runtime={"type": "shell"})]]
    config = parse({"host": {"id": "b"}})
    out = []
    collector = Collector(config, into(out), [FailingAdapter(), good], Resolver(), SeqStore(str(tmp_path / "seq")), clock=lambda: T0)
    collector.tick()
    assert len(out[0]["payload"]["agents"]) == 1
    assert "RuntimeError" in capsys.readouterr().err


def test_off_duty_becomes_on_leave_without_new_events(tmp_path):
    now = [T0]
    adapter = ScriptedAdapter()
    adapter.batches = [
        [_obs(Kind.PROCESS_STARTED, T0, cwd="/r", session_id="s1", runtime={"type": "shell"})],
        [_obs(Kind.PROCESS_EXITED, T0 + timedelta(seconds=1))],
    ]
    config = parse({"host": {"id": "b"}, "thresholds": {"leave": 60}})
    out = []
    collector = Collector(config, into(out), [adapter], Resolver(), SeqStore(str(tmp_path / "seq")), clock=lambda: now[0])
    collector.tick()
    now[0] = T0 + timedelta(seconds=1)
    collector.tick()
    assert out[-1]["payload"]["presence"] == "off_duty"
    now[0] = T0 + timedelta(seconds=120)
    collector.tick()
    presences = [m["payload"]["presence"] for m in out if m["kind"] == "agent"]
    assert presences[-1] == "on_leave"
    count = len(out)
    collector.tick()
    assert all(m["kind"] == "heartbeat" for m in out[count:])


class FlakyHq:
    def __init__(self):
        self.up = True
        self.need_snapshot = False
        self.received = []

    def __call__(self, messages):
        if not self.up:
            return Delivery(False, error="down")
        self.received.append([m["kind"] for m in messages])
        need, self.need_snapshot = self.need_snapshot, False
        return Delivery(True, need_snapshot=need)


def test_hq_outage_resyncs_with_snapshot_and_backs_off(tmp_path, capsys):
    now = [T0]
    adapter = ScriptedAdapter()
    hq = FlakyHq()
    config = parse({"host": {"id": "b"}})
    collector = Collector(config, hq, [adapter], Resolver(), SeqStore(str(tmp_path / "seq")), clock=lambda: now[0])
    collector.tick()
    assert hq.received == [["snapshot", "heartbeat"]]
    hq.up = False
    adapter.batches = [[_obs(Kind.PROCESS_STARTED, T0, cwd="/r", session_id="s1", runtime={"type": "shell"})]]
    now[0] = T0 + timedelta(seconds=1)
    collector.tick()
    assert "delivery failed" in capsys.readouterr().err
    hq.up = True
    now[0] = T0 + timedelta(milliseconds=1500)
    collector.tick()
    assert len(hq.received) == 1, "retry waits for backoff"
    now[0] = T0 + timedelta(seconds=3)
    collector.tick()
    assert len(hq.received) == 2 and hq.received[-1][0] == "snapshot"


def test_hq_gap_report_triggers_snapshot(tmp_path):
    now = [T0]
    hq = FlakyHq()
    adapter = ScriptedAdapter()
    collector = Collector(parse({"host": {"id": "b"}}), hq, [adapter], Resolver(), SeqStore(str(tmp_path / "seq")), clock=lambda: now[0])
    collector.tick()
    hq.need_snapshot = True
    adapter.batches = [[_obs(Kind.PROCESS_STARTED, T0, cwd="/r", session_id="s1", runtime={"type": "shell"})]]
    now[0] = T0 + timedelta(seconds=1)
    collector.tick()
    now[0] = T0 + timedelta(seconds=2)
    adapter.batches = [[_obs(Kind.SESSION_STATUS, T0 + timedelta(seconds=2), status="idle")]]
    collector.tick()
    assert hq.received[-1] == ["snapshot"]


def _rostered(tmp_path, adapter, now):
    from agentville.collector.roster import Roster

    config = parse({"host": {"id": "branch-1"}})
    out = []
    collector = Collector(config, into(out), [adapter], Resolver(), SeqStore(str(tmp_path / "seq")),
                          clock=lambda: now[0], roster=Roster(str(tmp_path / "roster.json")))
    return collector, out


def _snapshot_agents(out):
    return [m for m in out if m["kind"] == "snapshot"][-1]["payload"]["agents"]


def test_roster_keeps_employees_across_restart(tmp_path):
    now = [T0]
    adapter = ScriptedAdapter()
    adapter.batches = [[_obs(Kind.PROCESS_STARTED, T0, cwd="/r", session_id="s1", runtime={"type": "shell"}),
                        _obs(Kind.SESSION_STARTED, T0, session_id="s1")],
                       [_obs(Kind.PROCESS_EXITED, T0 + timedelta(minutes=1))]]
    first, out = _rostered(tmp_path, adapter, now)
    first.tick()
    now[0] = T0 + timedelta(minutes=1)
    first.tick()
    agent_id = _snapshot_agents(out)[0]["agent_id"]
    assert stat.S_IMODE(os.stat(tmp_path / "roster.json").st_mode) == 0o600

    now[0] = T0 + timedelta(minutes=5)
    resumed = ScriptedAdapter()
    resumed.batches = [[_obs(Kind.PROCESS_STARTED, now[0], cwd="/r", session_id="s1", runtime={"type": "shell"})]]
    second, out = _rostered(tmp_path, ScriptedAdapter(), now)
    second.tick()
    restored = _snapshot_agents(out)
    assert [(a["agent_id"], a["presence"], a["presence_since"]) for a in restored] == [
        (agent_id, "off_duty", "2026-01-01T00:01:00.000Z")]
    second.adapters = [resumed]
    second.tick()
    assert [a.agent_id for a in second.judge.agents] == [agent_id]
    assert second.judge.agents[0].instance is not None


def test_employee_on_duty_at_last_save_is_restored_off_duty_from_restart(tmp_path):
    now = [T0]
    adapter = ScriptedAdapter()
    adapter.batches = [[_obs(Kind.PROCESS_STARTED, T0, cwd="/r", session_id="s1", runtime={"type": "shell"})]]
    _rostered(tmp_path, adapter, now)[0].tick()
    now[0] = T0 + timedelta(hours=2)
    second, out = _rostered(tmp_path, ScriptedAdapter(), now)
    second.tick()
    assert [(a["presence"], a["presence_since"]) for a in _snapshot_agents(out)] == [("off_duty", "2026-01-01T02:00:00.000Z")]


def test_unreadable_roster_starts_empty(tmp_path, capsys):
    (tmp_path / "roster.json").write_text("{not json")
    (tmp_path / "roster.json.bad").write_text("older")
    adapter = ScriptedAdapter()
    adapter.batches = [[], [_obs(Kind.PROCESS_STARTED, T0, cwd="/r", session_id="s1", runtime={"type": "shell"})]]
    collector, out = _rostered(tmp_path, adapter, [T0])
    collector.tick()
    assert _snapshot_agents(out) == []
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1 and str(tmp_path / "roster.json") in lines[0] and "Expecting" in lines[0]
    assert (tmp_path / "roster.json").read_text() == "{not json"
    collector.tick()
    assert (tmp_path / "roster.json.bad").read_text() == "{not json"
    assert len(json.loads((tmp_path / "roster.json").read_text())) == 1


def test_roster_that_is_not_a_list_is_kept_aside(tmp_path, capsys):
    from agentville.collector.roster import Roster

    (tmp_path / "roster.json").write_text("{}")
    roster = Roster(str(tmp_path / "roster.json"))
    assert roster.load() == []
    assert "not a list" in capsys.readouterr().err
    roster.save([])
    assert (tmp_path / "roster.json.bad").read_text() == "{}"
    assert (tmp_path / "roster.json").read_text() == "[]\n"


def test_missing_roster_starts_empty_quietly(tmp_path, capsys):
    from agentville.collector.roster import Roster

    roster = Roster(str(tmp_path / "roster.json"))
    assert roster.load() == []
    roster.save([])
    assert capsys.readouterr().err == "" and not (tmp_path / "roster.json.bad").exists()


def test_resumed_session_returns_to_the_colleague_who_last_worked_on_it(tmp_path):
    a, b = ShiftKey("claude", "1:1"), ShiftKey("claude", "2:2")

    def obs(kind, shift, **data):
        return Observation(kind, shift, T0, T0, Source.SESSION_FILE, data)

    adapter = ScriptedAdapter()
    adapter.batches = [
        [obs(Kind.PROCESS_STARTED, a, cwd="/r", session_id="s", runtime={"type": "shell"}), obs(Kind.SESSION_STARTED, a, session_id="s"),
         obs(Kind.PROCESS_STARTED, b, cwd="/r", session_id="s", runtime={"type": "shell"}), obs(Kind.SESSION_STARTED, b, session_id="s"),
         obs(Kind.PROCESS_EXITED, a), obs(Kind.PROCESS_EXITED, b)],
        [obs(Kind.PROCESS_STARTED, ShiftKey("claude", "3:3"), cwd="/r", session_id="s", runtime={"type": "shell"})],
    ]
    collector, _ = _collector(tmp_path, adapter, lambda: T0)
    collector.tick()
    collector.tick()
    assert [(x.seat, x.instance is not None) for x in collector.judge.agents] == [(1, False), (2, True)]


def test_diagnostic_output_does_not_write_state(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    config = tmp_path / "config.yaml"
    config.write_text("host: {id: b}\nproviders: {claude: [], codex: []}\n")
    config.chmod(0o600)
    assert main(["--config", str(config), "--once", "--output", str(tmp_path / "out.jsonl")]) == 0
    assert (tmp_path / "out.jsonl").read_text()
    assert not (tmp_path / "state").exists()
