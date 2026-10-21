import json
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
    assert (tmp_path / "state" / "agentville" / "seq").read_text().strip() == "1000"


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
