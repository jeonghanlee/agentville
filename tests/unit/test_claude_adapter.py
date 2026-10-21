import json
from datetime import UTC, datetime

from agentville.collector.adapters.claude import ClaudeAdapter, _default_is_alive, encode_cwd
from agentville.common.observations import Kind

NOW = datetime(2026, 1, 1, tzinfo=UTC)
CWD = "/home/user/repo"
SID = "11111111-1111-4111-8111-111111111111"


def _session(home, pid=1001, sid=SID, status="idle", cwd=CWD):
    path = home / "sessions" / f"{pid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "sessionId": sid, "cwd": cwd, "status": "idle" if status is None else status,
                                "procStart": "1", "startedAt": 0, "statusUpdatedAt": 0}))
    return path


def _transcript(home, records, sid=SID, cwd=CWD, mode="a"):
    path = home / "projects" / encode_cwd(cwd) / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode) as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return path


def _adapter(home):
    return ClaudeAdapter(str(home), clock=lambda: NOW, is_alive=lambda pid, start: True)


def _kinds(observations):
    return [o.kind for o in observations]


def _tool_use(name="Bash", tid="t1"):
    return {"type": "assistant", "timestamp": "2026-01-01T00:00:00Z",
            "message": {"content": [{"type": "tool_use", "id": tid, "name": name}]}}


def test_unreadable_session_file_keeps_shift(tmp_path):
    path = _session(tmp_path)
    adapter = _adapter(tmp_path)
    assert Kind.PROCESS_STARTED in _kinds(adapter.poll())
    path.write_text('{"pid": 10')
    assert Kind.PROCESS_EXITED not in _kinds(adapter.poll())
    _session(tmp_path)
    assert _kinds(adapter.poll()) == []


def test_existing_transcript_history_is_not_replayed(tmp_path):
    _transcript(tmp_path, [_tool_use("Read", "old")])
    _session(tmp_path)
    adapter = _adapter(tmp_path)
    assert Kind.TOOL_STARTED not in _kinds(adapter.poll())
    _transcript(tmp_path, [_tool_use("Bash", "new")])
    started = [o for o in adapter.poll() if o.kind is Kind.TOOL_STARTED]
    assert [o.data["tool"] for o in started] == ["Bash"]


def test_transcript_created_after_attach_is_read_from_start(tmp_path):
    _session(tmp_path)
    adapter = _adapter(tmp_path)
    adapter.poll()
    _transcript(tmp_path, [_tool_use()])
    assert Kind.TOOL_STARTED in _kinds(adapter.poll())


def test_session_switch_flushes_old_transcript(tmp_path):
    _session(tmp_path)
    adapter = _adapter(tmp_path)
    adapter.poll()
    _transcript(tmp_path, [{"type": "system", "subtype": "turn_duration", "timestamp": "2026-01-01T00:00:00Z"}])
    _session(tmp_path, sid="22222222-2222-4222-8222-222222222222")
    kinds = _kinds(adapter.poll())
    assert kinds.index(Kind.TURN_COMPLETED) < kinds.index(Kind.SESSION_STARTED)


def test_error_record_does_not_change_model(tmp_path):
    _session(tmp_path)
    adapter = _adapter(tmp_path)
    adapter.poll()
    _transcript(tmp_path, [
        {"type": "assistant", "requestedModel": "model-a", "message": {"model": "model-a", "content": []}},
        {"type": "assistant", "isApiErrorMessage": True, "message": {"model": "<synthetic>", "content": []}},
    ])
    observations = adapter.poll()
    assert [o.data["model"] for o in observations if o.kind is Kind.MODEL_CHANGED] == ["model-a"]
    assert Kind.AGENT_ERROR in _kinds(observations)


def test_transcript_found_by_session_id_when_encoding_differs(tmp_path):
    _session(tmp_path, cwd="/home/user/my repo_x")
    adapter = _adapter(tmp_path)
    adapter.poll()
    path = tmp_path / "projects" / "-home-user-other-encoding" / f"{SID}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_tool_use()) + "\n")
    assert Kind.TOOL_STARTED in _kinds(adapter.poll())


def test_zombie_is_not_alive(tmp_path):
    fields = ["Z"] + ["0"] * 18 + ["555"] + ["0"] * 30
    (tmp_path / "77").mkdir()
    (tmp_path / "77" / "stat").write_text("77 (claude) " + " ".join(fields))
    assert not _default_is_alive(77, "555", str(tmp_path))
    fields[0] = "S"
    (tmp_path / "77" / "stat").write_text("77 (claude) " + " ".join(fields))
    assert _default_is_alive(77, "555", str(tmp_path))


def test_model_is_seeded_from_existing_transcript_at_attach(tmp_path):
    _transcript(tmp_path, [
        {"type": "assistant", "requestedModel": "model-a", "effort": "high", "message": {"model": "model-a", "content": []}},
        {"type": "assistant", "isApiErrorMessage": True, "message": {"model": "<synthetic>", "content": []}},
        {"type": "user", "message": {"content": "x"}},
    ])
    _session(tmp_path)
    observations = _adapter(tmp_path).poll()
    changed = [o.data for o in observations if o.kind is Kind.MODEL_CHANGED]
    assert changed == [{"model": "model-a", "settings": {"effort": "high"}}]
    assert Kind.TOOL_STARTED not in _kinds(observations)


def test_unreadable_transcript_does_not_drop_other_shifts(tmp_path):
    other = "22222222-2222-4222-8222-222222222222"
    _session(tmp_path, pid=1001)
    _session(tmp_path, pid=1002, sid=other)
    adapter = _adapter(tmp_path)
    adapter.poll()
    (tmp_path / "projects" / encode_cwd(CWD) / f"{SID}.jsonl" / "x").mkdir(parents=True)
    _transcript(tmp_path, [_tool_use()], sid=other)
    started = [o for o in adapter.poll() if o.kind is Kind.TOOL_STARTED]
    assert [o.shift.native_id for o in started] == ["1002:1"]


def test_shift_discovered_after_attach_reads_transcript_from_start(tmp_path):
    adapter = _adapter(tmp_path)
    adapter.poll()
    _transcript(tmp_path, [_tool_use()])
    _session(tmp_path)
    assert Kind.TOOL_STARTED in _kinds(adapter.poll())


def test_resumed_session_after_attach_does_not_replay_history(tmp_path):
    adapter = _adapter(tmp_path)
    adapter.poll()
    old = _tool_use()
    old["timestamp"] = "2025-12-31T00:00:00Z"
    _transcript(tmp_path, [old])
    _session(tmp_path)
    assert Kind.TOOL_STARTED not in _kinds(adapter.poll())
