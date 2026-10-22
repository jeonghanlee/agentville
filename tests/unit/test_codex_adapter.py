import json
import os
from datetime import UTC, datetime

import pytest

from agentville.collector.adapters.codex import CodexAdapter, is_employee_thread
from agentville.collector.appserver import AppServerError, RpcError
from agentville.collector.judge import Judge
from agentville.collector.project import COMMON_OFFICE
from agentville.common.observations import Kind, Source

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class OneThread:
    def __init__(self, thread):
        self.thread = thread

    def request(self, method, params):
        if method == "thread/loaded/list":
            return {"data": [self.thread["id"]], "nextCursor": None}
        return {"thread": self.thread}

    def drain(self):
        return []

    def close(self):
        pass


def _record(ptype):
    return json.dumps({"timestamp": "2026-01-01T00:00:00Z", "type": "event_msg", "payload": {"type": ptype}}) + "\n"


def test_existing_rollout_history_is_not_replayed(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(_record("task_started") + _record("task_complete"))
    thread = {"id": "t1", "cwd": "/r", "path": str(rollout), "status": {"type": "idle"}, "threadSource": "user"}
    adapter = CodexAdapter(str(tmp_path), connect=lambda: OneThread(thread), clock=lambda: NOW)
    kinds = [o.kind for o in adapter.poll()]
    assert Kind.PROCESS_STARTED in kinds and Kind.TURN_STARTED not in kinds
    with open(rollout, "a") as fh:
        fh.write(_record("task_started"))
    assert [o.kind for o in adapter.poll()] == [Kind.TURN_STARTED]


def test_rollout_located_by_thread_id_when_path_missing(tmp_path):
    day = tmp_path / "sessions" / "2026" / "01" / "01"
    day.mkdir(parents=True)
    thread = {"id": "t2", "cwd": "/r", "path": None, "status": {"type": "idle"}, "threadSource": "user"}
    adapter = CodexAdapter(str(tmp_path), connect=lambda: OneThread(thread), clock=lambda: NOW)
    (day / "rollout-2026-01-01T00-00-00-t2.jsonl").write_text("")
    adapter.poll()
    with open(day / "rollout-2026-01-01T00-00-00-t2.jsonl", "a") as fh:
        fh.write(_record("task_started"))
    assert Kind.TURN_STARTED in [o.kind for o in adapter.poll()]


def test_employee_thread_classification():
    assert is_employee_thread({"threadSource": "user"})
    assert not is_employee_thread({"threadSource": "system"})
    assert not is_employee_thread({"parentThreadId": "p"})
    assert not is_employee_thread({"source": {"subAgent": "review"}})


class Scripted:
    """Connection whose loaded list and notifications are set by the test."""

    def __init__(self, threads, loaded):
        self.threads, self.loaded, self.pending, self.reads = threads, loaded, [], []

    def request(self, method, params):
        if method == "thread/loaded/list":
            return {"data": list(self.loaded), "nextCursor": None}
        self.reads.append(params["threadId"])
        return {"thread": self.threads[params["threadId"]]}

    def drain(self):
        out, self.pending = self.pending, []
        return out

    def close(self):
        pass


def test_status_for_unknown_unloaded_thread_is_not_read(tmp_path):
    conn = Scripted({"t9": {"id": "t9", "status": {"type": "idle"}}}, loaded=[])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    adapter.poll()
    conn.pending = [{"method": "thread/status/changed", "params": {"threadId": "t9", "status": {"type": "idle"}}}]
    assert adapter.poll() == []
    assert conn.reads == []


def test_malformed_messages_are_ignored(tmp_path):
    conn = Scripted({}, loaded=[])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    adapter.poll()
    conn.pending = [{"method": "thread/status/changed", "params": None}, "junk",
                    {"method": "thread/status/changed", "params": {"threadId": "x", "status": None}}]
    assert adapter.poll() == []


def test_turn_completion_precedes_idle_status_in_one_poll(tmp_path):
    rollout = tmp_path / "r.jsonl"
    thread = {"id": "t1", "cwd": "/r", "path": str(rollout), "status": {"type": "active", "activeFlags": []}, "threadSource": "user"}
    conn = Scripted({"t1": thread}, loaded=["t1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    adapter.poll()
    rollout.write_text(_record("task_complete"))
    conn.pending = [{"method": "thread/status/changed", "params": {"threadId": "t1", "status": {"type": "idle"}}}]
    kinds = [o.kind for o in adapter.poll()]
    assert kinds.index(Kind.TURN_COMPLETED) < kinds.index(Kind.SESSION_STATUS)


def test_unreadable_rollout_does_not_drop_other_shifts(tmp_path):
    rollout = tmp_path / "good.jsonl"
    rollout.write_text("")
    conn = Scripted({
        "t1": {"id": "t1", "cwd": "/r", "path": str(tmp_path / "bad.jsonl"), "status": {"type": "idle"}},
        "t2": {"id": "t2", "cwd": "/r", "path": str(rollout), "status": {"type": "idle"}},
    }, loaded=["t1", "t2"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    adapter.poll()
    (tmp_path / "bad.jsonl" / "x").mkdir(parents=True)
    rollout.write_text(_record("task_started"))
    assert [(o.kind, o.shift.native_id) for o in adapter.poll()] == [(Kind.TURN_STARTED, "t2")]


def test_thread_started_after_attach_reads_rollout_from_start(tmp_path):
    rollout = tmp_path / "r.jsonl"
    rollout.write_text(_record("task_started"))
    conn = Scripted({}, loaded=[])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    adapter.poll()
    thread = {"id": "t1", "cwd": "/r", "path": str(rollout), "createdAt": int(NOW.timestamp()),
              "status": {"type": "active", "activeFlags": []}}
    conn.pending = [{"method": "thread/started", "params": {"thread": thread}}]
    assert Kind.TURN_STARTED in [o.kind for o in adapter.poll()]


def test_resumed_thread_after_attach_does_not_replay_history(tmp_path):
    rollout = tmp_path / "r.jsonl"
    rollout.write_text(_record("task_started"))
    conn = Scripted({}, loaded=[])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    adapter.poll()
    thread = {"id": "t1", "cwd": "/r", "path": str(rollout), "createdAt": int(NOW.timestamp()) - 86400,
              "status": {"type": "active", "activeFlags": []}}
    conn.pending = [{"method": "thread/started", "params": {"thread": thread}}]
    assert Kind.TURN_STARTED not in [o.kind for o in adapter.poll()]


class _Resolver:
    def resolve(self, cwd):
        return COMMON_OFFICE


def test_task_error_stays_in_error_until_activity_resumes(tmp_path):
    rollout = tmp_path / "r.jsonl"
    rollout.write_text("")
    thread = {"id": "t1", "cwd": "/r", "path": str(rollout), "status": {"type": "active", "activeFlags": []}}
    conn = Scripted({"t1": thread}, loaded=["t1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    judge = Judge(_Resolver(), lambda kind, at, payload: None)

    def step():
        for obs in adapter.poll():
            judge.apply(obs)
        return judge.agents[0].instance.state

    step()
    with open(rollout, "a") as fh:
        fh.write(json.dumps({"timestamp": "2026-01-01T00:00:01Z", "type": "event_msg",
                             "payload": {"type": "task_complete", "error": {"message": "x"}}}) + "\n")
    conn.pending = [{"method": "thread/status/changed", "params": {"threadId": "t1", "status": {"type": "idle"}}}]
    assert step() == "error"
    with open(rollout, "a") as fh:
        fh.write(_record("task_started"))
    assert step() == "working"


class _FailingRead(Scripted):
    closed = False

    def request(self, method, params):
        if method == "thread/read" and params["threadId"] == "t2":
            raise RpcError("thread/read: {'code': -32600, 'message': 'thread not loaded'}")
        return super().request(method, params)

    def close(self):
        self.closed = True


def test_rpc_error_on_one_thread_keeps_connection_and_other_shifts(tmp_path):
    conn = _FailingRead({"t1": {"id": "t1", "cwd": "/r", "path": None, "status": {"type": "idle"}}}, loaded=["t1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    adapter.poll()
    conn.loaded.append("t2")
    conn.pending = [{"method": "thread/status/changed", "params": {"threadId": "t2", "status": {"type": "active", "activeFlags": []}}}]
    assert adapter.poll() == []
    assert not conn.closed


def _sub(observations):
    return [(o.kind, o.shift.native_id, o.data) for o in observations
            if o.kind in (Kind.SUBAGENT_STARTED, Kind.SUBAGENT_STATUS, Kind.SUBAGENT_ENDED)]


def _sub_obs(observations):
    return [o for o in observations if o.kind in (Kind.SUBAGENT_STARTED, Kind.SUBAGENT_STATUS)]


def _status(thread_id, status):
    return {"method": "thread/status/changed", "params": {"threadId": thread_id, "status": status}}


def _parent_and_child(tmp_path, child_status=None):
    parent = {"id": "p1", "cwd": "/r", "path": None, "status": {"type": "idle"}}
    child = {"id": "c1", "cwd": "/r", "path": str(tmp_path / "c1.jsonl"), "parentThreadId": "p1",
             "source": {"subAgent": "review"}, "createdAt": int(NOW.timestamp()),
             "status": child_status or {"type": "active", "activeFlags": []}}
    return parent, child


def test_subagent_thread_is_contractor_of_parent_shift(tmp_path):
    parent, child = _parent_and_child(tmp_path)
    conn = Scripted({"p1": parent, "c1": child}, loaded=["c1", "p1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    observations = adapter.poll()
    assert [o.shift.native_id for o in observations if o.kind is Kind.PROCESS_STARTED] == ["p1"]
    assert _sub(observations) == [(Kind.SUBAGENT_STARTED, "p1", {"subagent_id": "c1", "provider": "codex",
                                                                 "status": "active", "tool": None})]
    conn.pending = [_status("c1", {"type": "active", "activeFlags": ["waitingOnApproval"]}),
                    _status("c1", {"type": "systemError"}), _status("c1", {"type": "idle"})]
    assert [o.data["status"] for o in adapter.poll()] == ["waiting", "error", "idle"]
    conn.loaded.remove("c1")
    conn.pending = [_status("c1", {"type": "notLoaded"})]
    assert _sub(adapter.poll()) == [(Kind.SUBAGENT_ENDED, "p1", {"subagent_id": "c1"})]


def test_nested_subagent_is_found_at_seed_whatever_the_order(tmp_path):
    parent, child = _parent_and_child(tmp_path)
    grandchild = dict(child, id="g1", parentThreadId="c1", path=None)
    conn = Scripted({"p1": parent, "c1": child, "g1": grandchild}, loaded=["g1", "c1", "p1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    started = [(shift, data["subagent_id"]) for kind, shift, data in _sub(adapter.poll()) if kind is Kind.SUBAGENT_STARTED]
    assert started == [("p1", "c1"), ("p1", "g1")]


def test_subagent_tool_comes_from_its_rollout(tmp_path):
    parent, child = _parent_and_child(tmp_path)
    conn = Scripted({"p1": parent}, loaded=["p1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    adapter.poll()
    (tmp_path / "c1.jsonl").write_text(json.dumps({"timestamp": "2026-01-01T00:00:01Z", "type": "response_item",
        "payload": {"type": "function_call", "name": "exec_command", "arguments": "<tool-input>", "call_id": "x"}}) + "\n")
    conn.threads["c1"] = child
    conn.loaded.append("c1")
    conn.pending = [{"method": "thread/started", "params": {"thread": child}}]
    assert [o.data["tool"] for o in _sub_obs(adapter.poll())] == [None, "exec_command"]
    with open(tmp_path / "c1.jsonl", "a") as fh:
        fh.write(json.dumps({"timestamp": "2026-01-01T00:00:02Z", "type": "response_item",
                             "payload": {"type": "function_call_output", "call_id": "x", "output": "<tool-output>"}}) + "\n")
    assert [o.data["tool"] for o in adapter.poll()] == [None]


def test_subagent_ends_on_close_and_with_parent(tmp_path):
    parent, child = _parent_and_child(tmp_path)
    conn = Scripted({"p1": parent, "c1": child}, loaded=["p1", "c1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    adapter.poll()
    conn.pending = [{"method": "thread/closed", "params": {"threadId": "c1"}}]
    assert _sub(adapter.poll()) == [(Kind.SUBAGENT_ENDED, "p1", {"subagent_id": "c1"})]

    conn2 = Scripted({"p1": parent, "c1": child}, loaded=["p1", "c1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn2, clock=lambda: NOW)
    messages = []
    judge = Judge(_Resolver(), lambda kind, at, payload: messages.append((kind, payload)))
    for obs in adapter.poll():
        judge.apply(obs)
    conn2.pending = [_status("p1", {"type": "notLoaded"})]
    for obs in adapter.poll():
        judge.apply(obs)
    assert [(k, p.get("status")) for k, p in messages[-2:]] == [("contractor", "ended"), ("agent", None)]
    conn2.pending = [_status("c1", {"type": "idle"})]
    assert _sub(adapter.poll()) == []


def test_subagent_missing_after_reconnect_is_ended(tmp_path):
    parent, child = _parent_and_child(tmp_path)
    conns = [Scripted({"p1": parent, "c1": child}, loaded=["p1", "c1"]), Scripted({"p1": parent}, loaded=["p1"])]
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conns.pop(0), clock=lambda: NOW)
    adapter.poll()
    adapter._conn = None
    assert _sub(adapter.poll()) == [(Kind.SUBAGENT_ENDED, "p1", {"subagent_id": "c1"})]


def _token_count(*used, resets=(1767243600, 1767830400)):
    windows = {name: {"used_percent": u, "window_minutes": 300, "resets_at": r}
               for name, u, r in zip(("primary", "secondary"), used, resets)}
    return json.dumps({"timestamp": "2026-01-01T00:00:00Z", "type": "event_msg",
                       "payload": {"type": "token_count", "info": {}, "rate_limits": windows}}) + "\n"


def test_token_count_at_full_window_reports_limit_with_reset(tmp_path):
    rollout = tmp_path / "r.jsonl"
    rollout.write_text("")
    thread = {"id": "t1", "cwd": "/r", "path": str(rollout), "status": {"type": "active", "activeFlags": []}}
    conn = Scripted({"t1": thread}, loaded=["t1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    judge = Judge(_Resolver(), lambda kind, at, payload: None)

    def step(line):
        with open(rollout, "a") as fh:
            fh.write(line)
        observations = adapter.poll()
        for obs in observations:
            judge.apply(obs)
        return [(o.kind, o.data) for o in observations]

    step("")
    assert step(_token_count(50.0)) == []
    assert step(_token_count(100.0, 100.0)) == [(Kind.LIMIT_REACHED, {"reset_at": datetime(2026, 1, 8, tzinfo=UTC)})]
    assert step(_token_count(100.0, 100.0)) == []
    payload = judge.activity_payload(judge.agents[0], NOW)
    assert (payload["state"], payload["reset_at"]) == ("limited", "2026-01-08T00:00:00.000Z")
    conn.pending = [{"method": "thread/status/changed", "params": {"threadId": "t1", "status": {"type": "idle"}}}]
    step(_record("task_complete"))
    assert judge.agents[0].instance.state == "limited"
    assert step(_token_count(20.0, 40.0)) == [(Kind.LIMIT_CLEARED, {})]
    assert judge.agents[0].instance.state == "idle"
    assert judge.activity_payload(judge.agents[0], NOW)["reset_at"] is None


def _task_complete(error):
    return json.dumps({"timestamp": "2026-01-01T00:00:01Z", "type": "event_msg",
                       "payload": {"type": "task_complete", "error": error}}) + "\n"


def _limited_stepper(tmp_path):
    rollout = tmp_path / "r.jsonl"
    rollout.write_text("")
    thread = {"id": "t1", "cwd": "/r", "path": str(rollout), "status": {"type": "active", "activeFlags": []}}
    conn = Scripted({"t1": thread}, loaded=["t1"])
    adapter = CodexAdapter(str(tmp_path), connect=lambda: conn, clock=lambda: NOW)
    judge = Judge(_Resolver(), lambda kind, at, payload: None)

    def step(line):
        with open(rollout, "a") as fh:
            fh.write(line)
        observations = adapter.poll()
        for obs in observations:
            judge.apply(obs)
        return [(o.kind, o.data) for o in observations]

    step("")
    return step, judge


def test_usage_limit_error_keeps_the_employee_limited(tmp_path):
    step, judge = _limited_stepper(tmp_path)
    step(_token_count(100.0, 40.0))
    error = {"codex_error_info": "usage_limit_exceeded", "message": "<text>"}
    assert [k for k, _ in step(_task_complete(error))] == [Kind.TURN_COMPLETED]
    payload = judge.activity_payload(judge.agents[0], NOW)
    assert (payload["state"], payload["reset_at"]) == ("limited", "2026-01-01T05:00:00.000Z")


def test_usage_limit_error_without_full_window_reports_limit(tmp_path):
    step, judge = _limited_stepper(tmp_path)
    step(_token_count(97.0, 40.0))
    error = {"codex_error_info": "usage_limit_exceeded", "message": "<text>"}
    assert step(_task_complete(error)) == [(Kind.LIMIT_REACHED, {"reset_at": datetime(2026, 1, 1, 5, tzinfo=UTC)}),
                                           (Kind.TURN_COMPLETED, {"duration_ms": None})]
    assert judge.agents[0].instance.state == "limited"


def test_usage_limit_error_before_any_token_count_has_no_reset(tmp_path):
    step, judge = _limited_stepper(tmp_path)
    error = {"codex_error_info": "usage_limit_exceeded", "message": "<text>"}
    assert step(_task_complete(error))[0] == (Kind.LIMIT_REACHED, {"reset_at": None})
    assert judge.agents[0].instance.state == "limited"


def test_server_overloaded_is_transient_and_other_errors_remain(tmp_path):
    step, judge = _limited_stepper(tmp_path)
    overloaded = {"codex_error_info": "server_overloaded", "message": "<text>"}
    assert [k for k, _ in step(_task_complete(overloaded))] == [Kind.TURN_COMPLETED]
    assert judge.agents[0].instance.state == "idle"
    step(_record("task_started"))
    assert [k for k, _ in step(_task_complete({"codex_error_info": "<other>", "message": "<text>"}))] == [
        Kind.AGENT_ERROR, Kind.TURN_COMPLETED]
    step(_record("task_started"))
    assert [k for k, _ in step(_task_complete("<text>"))] == [Kind.AGENT_ERROR, Kind.TURN_COMPLETED]


def _no_daemon():
    raise AppServerError("no daemon")


def _rollout(home, thread_id, meta=None, *lines, age=60):
    day = home / "sessions" / "2026" / "01" / "01"
    day.mkdir(parents=True, exist_ok=True)
    path = day / f"rollout-2026-01-01T00-00-00-{thread_id}.jsonl"
    payload = {"id": thread_id, "timestamp": "2025-12-31T23:59:00Z", "cwd": "/w", "source": "exec",
               "thread_source": "user", **(meta or {})}
    record = {"timestamp": payload["timestamp"], "type": "session_meta", "payload": payload}
    path.write_text(json.dumps(record) + "\n" + "".join(lines))
    _touch(path, age)
    return path


def _touch(path, age):
    os.utime(path, (NOW.timestamp() - age, NOW.timestamp() - age))


def _append(path, *lines, age=0):
    with open(path, "a") as fh:
        fh.writelines(lines)
    _touch(path, age)


def _tool(name="exec_command", call_id="x"):
    payload = {"type": "function_call", "name": name, "arguments": "<tool-input>", "call_id": call_id}
    return json.dumps({"timestamp": "2026-01-01T00:00:01Z", "type": "response_item", "payload": payload}) + "\n"


def test_rollout_without_daemon_is_a_low_confidence_shift(tmp_path):
    path = _rollout(tmp_path, "r1", None, _record("task_started"))
    _rollout(tmp_path, "r0", None, _record("task_started"), age=31 * 60)
    adapter = CodexAdapter(str(tmp_path), connect=_no_daemon, clock=lambda: NOW, account_alias="codex-account-1")
    judge = Judge(_Resolver(), lambda kind, at, payload: None)
    observations = adapter.poll()
    assert [(o.kind, o.shift.native_id) for o in observations] == [
        (Kind.PROCESS_STARTED, "rollout:r1"), (Kind.SESSION_STARTED, "rollout:r1")]
    started = observations[0]
    assert started.source is Source.SESSION_LOG
    assert started.data == {"cwd": "/w", "session_id": "r1", "runtime": {"type": "rollout"},
                            "account_alias": "codex-account-1", "max_confidence": "low"}
    for obs in observations:
        judge.apply(obs)
    _append(path, _record("task_started"), _tool())
    for obs in adapter.poll():
        judge.apply(obs)
    payload = judge.activity_payload(judge.agents[0], NOW)
    assert (payload["state"], payload["tool"], payload["source"], payload["confidence"]) == (
        "working", "exec_command", "session_log", "low")
    _append(path, _task_complete({"codex_error_info": "usage_limit_exceeded", "message": "<text>"}))
    for obs in adapter.poll():
        judge.apply(obs)
    assert judge.agents[0].instance.state == "limited"


def test_rollout_created_after_attach_is_read_from_start(tmp_path):
    adapter = CodexAdapter(str(tmp_path), connect=_no_daemon, clock=lambda: NOW)
    assert adapter.poll() == []
    _rollout(tmp_path, "r1", {"timestamp": "2026-01-01T00:00:00Z"}, _record("task_started"), _tool(), age=0)
    kinds = [o.kind for o in adapter.poll()]
    assert kinds == [Kind.PROCESS_STARTED, Kind.SESSION_STARTED, Kind.TURN_STARTED, Kind.TOOL_STARTED]


def test_rollout_shift_ends_after_thirty_minutes_without_writes(tmp_path):
    path = _rollout(tmp_path, "r1")
    adapter = CodexAdapter(str(tmp_path), connect=_no_daemon, clock=lambda: NOW)
    adapter.poll()
    _touch(path, 29 * 60)
    assert adapter.poll() == []
    _touch(path, 31 * 60)
    assert [(o.kind, o.shift.native_id) for o in adapter.poll()] == [(Kind.PROCESS_EXITED, "rollout:r1")]
    assert adapter.poll() == []
    _append(path, _record("task_started"))
    assert [o.kind for o in adapter.poll()] == [Kind.PROCESS_STARTED, Kind.SESSION_STARTED, Kind.TURN_STARTED]


def test_daemon_thread_takes_over_a_rollout_shift(tmp_path):
    path = _rollout(tmp_path, "r1")
    daemon = Scripted({"r1": {"id": "r1", "cwd": "/w", "path": str(path), "status": {"type": "idle"}}}, loaded=["r1"])
    connect = [_no_daemon]
    adapter = CodexAdapter(str(tmp_path), connect=lambda: connect[0](), clock=lambda: NOW)
    messages = []
    judge = Judge(_Resolver(), lambda kind, at, payload: messages.append((kind, payload)))

    def step():
        observations = adapter.poll()
        for obs in observations:
            judge.apply(obs)
        return [(o.kind, o.shift.native_id) for o in observations]

    step()
    _append(path, _record("task_started"))
    connect[0] = lambda: daemon
    assert step()[:4] == [(Kind.TURN_STARTED, "rollout:r1"), (Kind.PROCESS_EXITED, "rollout:r1"),
                          (Kind.PROCESS_STARTED, "r1"), (Kind.SESSION_STARTED, "r1")]
    assert len(judge.agents) == 1 and judge.agents[0].instance.shift.native_id == "r1"
    _append(path, _tool())
    assert step() == [(Kind.TOOL_STARTED, "r1")]
    daemon.pending = [{"method": "thread/closed", "params": {"threadId": "r1"}}]
    assert step() == [(Kind.PROCESS_EXITED, "r1")]
    assert step() == []


@pytest.mark.parametrize("meta", [
    {"source": {"subagent": {"thread_spawn": {"parent_thread_id": "p1"}}}},
    {"source": {"subAgent": "review"}},
    {"parent_thread_id": "p1"},
    {"thread_source": "system"},
])
def test_subagent_and_system_rollouts_are_not_shifts(tmp_path, meta):
    path = _rollout(tmp_path, "r1", meta, _record("task_started"))
    adapter = CodexAdapter(str(tmp_path), connect=_no_daemon, clock=lambda: NOW)
    assert adapter.poll() == []
    _append(path, _record("task_started"))
    assert adapter.poll() == []


def test_rollout_without_complete_session_meta_waits(tmp_path):
    day = tmp_path / "sessions" / "2026" / "01" / "01"
    day.mkdir(parents=True)
    path = day / "rollout-2026-01-01T00-00-00-r1.jsonl"
    path.write_text('{"type": "session_meta", "payload": {"id": "r1"')
    _touch(path, 0)
    adapter = CodexAdapter(str(tmp_path), connect=_no_daemon, clock=lambda: NOW)
    assert adapter.poll() == []
    _append(path, ', "cwd": "/w"}}\n')
    assert [o.kind for o in adapter.poll()] == [Kind.PROCESS_STARTED, Kind.SESSION_STARTED]
