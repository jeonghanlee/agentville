import json
from datetime import UTC, datetime

from agentville.collector.adapters.codex import CodexAdapter, is_employee_thread
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
