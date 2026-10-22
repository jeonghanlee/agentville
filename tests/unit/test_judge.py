from datetime import UTC, datetime, timedelta

import jsonschema

from agentville.collector.config import parse
from agentville.collector.judge import Judge
from agentville.collector.main import Collector, SeqStore
from agentville.collector.project import Project
from agentville.collector.sender import Delivery
from agentville.common.observations import Kind, Observation, ShiftKey, Source
from agentville.common.protocol import Envelope, load_schema

T0 = datetime(2026, 1, 1, tzinfo=UTC)
KEY = ShiftKey("claude", "1:1")
VALIDATOR = jsonschema.Draft202012Validator(load_schema())


class Resolver:
    def resolve(self, cwd):
        return Project("github.com/example/repo", "repo")


def _obs(kind, seconds=0, **data):
    at = T0 + timedelta(seconds=seconds)
    return Observation(kind, KEY, at, at, Source.SESSION_LOG, data)


def _judge():
    messages = []
    envelope = Envelope("b")
    judge = Judge(Resolver(), lambda kind, at, payload: messages.append(envelope.wrap(kind, at, payload, at)))
    judge.apply(_obs(Kind.PROCESS_STARTED, cwd="/r", runtime={"type": "shell"}))
    return judge, messages


def _of(messages, kind):
    for message in messages:
        VALIDATOR.validate(message)
    return [m["payload"] for m in messages if m["kind"] == kind]


def test_contractor_lifecycle_and_state():
    judge, messages = _judge()
    judge.apply(_obs(Kind.SUBAGENT_STARTED, 1, subagent_id="toolu_1", provider="claude", status="active", tool=None))
    judge.apply(_obs(Kind.SUBAGENT_STATUS, 2, subagent_id="toolu_1", status="active", tool="Read"))
    judge.apply(_obs(Kind.SUBAGENT_STATUS, 3, subagent_id="toolu_1", status="active", tool="Read"))
    judge.apply(_obs(Kind.SUBAGENT_STATUS, 4, subagent_id="toolu_1", status="idle", tool="Read"))
    judge.apply(_obs(Kind.SUBAGENT_ENDED, 5, subagent_id="toolu_1"))
    contractors = _of(messages, "contractor")
    assert [(c["status"], c["state"], c["tool"]) for c in contractors] == [
        ("hired", "working", None), ("hired", "working", "Read"), ("hired", "idle", None), ("ended", "idle", None)]
    instance_id = judge.agents[0].instance.instance_id
    assert {c["parent_instance_id"] for c in contractors} == {instance_id}
    assert len({c["contractor_id"] for c in contractors}) == 1
    assert "toolu_1" not in contractors[0]["contractor_id"]
    assert contractors[0]["origin"] == "in_process" and contractors[0]["provider"] == "claude"
    assert contractors[1]["state_since"] == contractors[0]["state_since"]
    assert judge.agents[0].instance.contractors == {}


def test_status_for_unknown_subagent_is_ignored():
    judge, messages = _judge()
    judge.apply(_obs(Kind.SUBAGENT_STATUS, 1, subagent_id="x", status="active", tool="Bash"))
    judge.apply(_obs(Kind.SUBAGENT_ENDED, 1, subagent_id="x"))
    assert _of(messages, "contractor") == []


def test_parent_exit_ends_contractors():
    judge, messages = _judge()
    judge.apply(_obs(Kind.SUBAGENT_STARTED, 1, subagent_id="a"))
    judge.apply(_obs(Kind.SUBAGENT_STARTED, 1, subagent_id="b", status="waiting"))
    judge.apply(_obs(Kind.PROCESS_EXITED, 2))
    kinds = [m["kind"] for m in messages]
    assert kinds[-3:] == ["contractor", "contractor", "agent"]
    ended = _of(messages, "contractor")[-2:]
    assert [(c["status"], c["state"]) for c in ended] == [("ended", "working"), ("ended", "waiting")]


def test_limit_sets_reset_at_until_activity_resumes():
    judge, messages = _judge()
    reset = T0 + timedelta(hours=5)
    judge.apply(_obs(Kind.LIMIT_REACHED, 1, reset_at=reset))
    judge.apply(_obs(Kind.TURN_COMPLETED, 2))
    judge.apply(_obs(Kind.SESSION_STATUS, 3, status="idle"))
    activities = _of(messages, "activity")
    assert (activities[-1]["state"], activities[-1]["reset_at"]) == ("limited", "2026-01-01T05:00:00.000Z")
    judge.apply(_obs(Kind.TURN_STARTED, 4))
    assert (_of(messages, "activity")[-1]["state"], _of(messages, "activity")[-1]["reset_at"]) == ("working", None)


def test_limit_cleared_returns_to_idle():
    judge, messages = _judge()
    judge.apply(_obs(Kind.LIMIT_REACHED, 1, reset_at=None))
    assert _of(messages, "activity")[-1]["reset_at"] is None
    judge.apply(_obs(Kind.LIMIT_CLEARED, 2))
    assert _of(messages, "activity")[-1]["state"] == "idle"
    count = len(messages)
    judge.apply(_obs(Kind.LIMIT_CLEARED, 3))
    assert len(messages) == count


def test_active_status_and_tool_clear_limited():
    for obs in (_obs(Kind.SESSION_STATUS, 2, status="active"), _obs(Kind.TOOL_STARTED, 2, tool="Bash")):
        judge, messages = _judge()
        judge.apply(_obs(Kind.LIMIT_REACHED, 1, reset_at=T0))
        judge.apply(obs)
        assert _of(messages, "activity")[-1]["state"] == "working"


class Scripted:
    def __init__(self, batches):
        self.batches = batches

    def poll(self):
        return self.batches.pop(0) if self.batches else []


def test_snapshot_includes_active_contractors(tmp_path):
    out = []

    def deliver(messages):
        out.extend(messages)
        return Delivery(True)

    adapter = Scripted([[_obs(Kind.PROCESS_STARTED, cwd="/r", runtime={"type": "shell"}),
                         _obs(Kind.SUBAGENT_STARTED, subagent_id="a"),
                         _obs(Kind.SUBAGENT_STARTED, subagent_id="b"),
                         _obs(Kind.SUBAGENT_ENDED, subagent_id="b")]])
    collector = Collector(parse({"host": {"id": "b"}}), deliver, [adapter], Resolver(), SeqStore(str(tmp_path / "seq")),
                          clock=lambda: T0)
    collector.tick()
    snapshot = _of(out, "snapshot")[0]
    instance_id = snapshot["agents"][0]["instance"]["instance_id"]
    assert [(c["parent_instance_id"], c["status"], c["state"]) for c in snapshot["contractors"]] == [
        (instance_id, "hired", "working")]


class Repositories:
    def resolve(self, cwd):
        return Project("github.com/example/" + cwd.strip("/"), cwd.strip("/"))


def _started(judge, shift, cwd, seconds=0):
    at = T0 + timedelta(seconds=seconds)
    judge.apply(Observation(Kind.PROCESS_STARTED, shift, at, at, Source.SESSION_LOG,
                            {"cwd": cwd, "session_id": shift.native_id, "runtime": {"type": "rollout"}}))


def test_seats_are_unique_per_provider_on_the_branch():
    judge = Judge(Repositories(), lambda kind, at, payload: None)
    # Rollout-only Codex shifts in different repositories, and a Claude shift beside them.
    _started(judge, ShiftKey("codex", "rollout:1"), "/alpha")
    _started(judge, ShiftKey("codex", "rollout:2"), "/beta")
    _started(judge, ShiftKey("codex", "rollout:3"), "/gamma")
    _started(judge, ShiftKey("claude", "1:1"), "/beta")
    seats = [(a.provider, a.project.alias, a.seat) for a in judge.agents]
    assert seats == [("codex", "alpha", 1), ("codex", "beta", 2), ("codex", "gamma", 3), ("claude", "beta", 1)]
    judge.apply(Observation(Kind.PROCESS_EXITED, ShiftKey("codex", "rollout:2"), T0, T0, Source.SESSION_LOG, {}))
    # A later shift in the same repository returns to its Employee; a new repository takes the next free seat.
    _started(judge, ShiftKey("codex", "rollout:4"), "/beta", 5)
    _started(judge, ShiftKey("codex", "rollout:5"), "/delta", 6)
    assert [(a.project.alias, a.seat) for a in judge.agents if a.provider == "codex"] == [
        ("alpha", 1), ("beta", 2), ("gamma", 3), ("delta", 4)]


def test_restored_duplicate_seats_are_renumbered():
    judge = Judge(Resolver(), lambda kind, at, payload: None)
    record = {"project_alias": "p", "presence_since": "2026-01-01T00:00:00.000Z"}
    judge.restore([{**record, "agent_id": "a", "project_id": "p1", "provider": "codex", "seat": 1},
                   {**record, "agent_id": "b", "project_id": "p2", "provider": "codex", "seat": 1},
                   {**record, "agent_id": "c", "project_id": "p2", "provider": "codex", "seat": 2},
                   {**record, "agent_id": "d", "project_id": "p2", "provider": "claude", "seat": 1}], T0)
    assert [(a.agent_id, a.seat) for a in judge.agents] == [("a", 1), ("b", 3), ("c", 2), ("d", 1)]


def test_alias_from_configuration_is_sent():
    messages = []
    envelope = Envelope("b")
    judge = Judge(Resolver(), lambda kind, at, payload: messages.append(envelope.wrap(kind, at, payload, at)),
                  new_id=lambda: "agent-1", alias_for={"agent-1": "Reviewer"}.get)
    judge.apply(_obs(Kind.PROCESS_STARTED, cwd="/r", runtime={"type": "shell"}))
    assert _of(messages, "agent")[0]["alias"] == "Reviewer"
    assert judge.snapshot(T0)[0][0]["alias"] == "Reviewer"
