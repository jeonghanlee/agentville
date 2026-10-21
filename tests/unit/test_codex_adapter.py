import json
from datetime import UTC, datetime

from agentville.collector.adapters.codex import CodexAdapter, is_employee_thread
from agentville.collector.appserver import RpcError
from agentville.collector.judge import Judge
from agentville.collector.project import COMMON_OFFICE
from agentville.common.observations import Kind

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
