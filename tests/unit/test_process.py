import json
from datetime import UTC, datetime
from pathlib import Path

from agentville.collector.process import ProcessTable
from agentville.collector.judge import Judge
from agentville.collector.project import Project
from agentville.common.observations import Kind, Observation, ShiftKey, Source

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/process/S05/scenario.json"


def write_process(root, row, cwd):
    directory = root / str(row["pid"])
    directory.mkdir(exist_ok=True)
    fields = ["S", str(row["parent"])] + ["0"] * 17 + [str(row["start"])]
    (directory / "stat").write_text(f"{row['pid']} ({row['name']}) " + " ".join(fields))
    if not (directory / "cwd").is_symlink():
        (directory / "cwd").symlink_to(cwd)


def test_ancestry_start_time_and_ambiguous_rollout_matching(tmp_path):
    fixture = json.loads(FIXTURE.read_text())
    (tmp_path / "stat").write_text(f"btime {fixture['boot_epoch']}\n")
    for row in fixture["processes"]:
        write_process(tmp_path, row, tmp_path)
    table = ProcessTable(str(tmp_path))
    table.refresh()
    child = table.processes[2001]
    assert [process.pid for process in table.ancestors(child)] == [1501, 1001]
    created = datetime.fromtimestamp(child.started_at + 0.1, tz=UTC)
    assert table.match_rollout(str(tmp_path / "rollout.jsonl"), created, str(tmp_path)) == child
    write_process(tmp_path, {**fixture["processes"][-1], "pid": 2002}, tmp_path)
    table.refresh()
    assert table.match_rollout(str(tmp_path / "rollout.jsonl"), created, str(tmp_path)) is None
    fd = tmp_path / "2001/fd"
    fd.mkdir()
    (fd / "7").symlink_to(tmp_path / "rollout.jsonl")
    assert table.match_rollout(str(tmp_path / "rollout.jsonl"), created, str(tmp_path)).pid == 2001
    write_process(tmp_path, {**fixture["processes"][0], "start": child.start + "0"}, tmp_path)
    table.refresh()
    assert [process.pid for process in table.ancestors(table.processes[2001])] == [1501]


def test_truncated_multibyte_process_name_does_not_abort_scan(tmp_path):
    directory = tmp_path / "42"
    directory.mkdir()
    fields = b"S 1 " + b"0 " * 17 + b"100"
    (directory / "stat").write_bytes(b"42 (worker-\xf0\x9f) " + fields)
    table = ProcessTable(str(tmp_path))
    table.refresh()
    assert table.processes[42].identity == (42, "100")


def test_late_parent_moves_in_process_contractors_and_keeps_updates(tmp_path):
    fixture = json.loads(FIXTURE.read_text())
    (tmp_path / "stat").write_text(f"btime {fixture['boot_epoch']}\n")
    for row in fixture["processes"]:
        write_process(tmp_path, row, tmp_path)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    child = ShiftKey("codex", "fixture-child")
    parent = ShiftKey("claude", "fixture-parent")
    messages = []

    class Resolver:
        def resolve(self, cwd):
            return Project("fixture-project", "Fixture")

    judge = Judge(Resolver(), lambda kind, when, payload: messages.append((kind, payload)), proc_root=str(tmp_path))

    def observe(kind, shift, **data):
        return Observation(kind, shift, at, at, Source.PROCESS, data)

    judge.apply_batch([observe(Kind.PROCESS_STARTED, child, pid=2001, proc_start="1000020")])
    judge.apply_batch([observe(Kind.SUBAGENT_STARTED, child, subagent_id="fixture-subagent",
                              provider="claude", status="active", tool="Read")])
    old_contractor = judge.snapshot(at)[2][0]
    judge.apply_batch([observe(Kind.PROCESS_STARTED, parent, pid=1001, proc_start="1000000")])
    agents, _, contractors = judge.snapshot(at)
    root = next(agent for agent in agents if agent["presence"] == "on_duty")
    assert root["provider"] == "claude" and len(contractors) == 2
    moved = next(row for row in contractors if row["origin"] == "in_process")
    assert moved["tool"] == "Read" and moved["state"] == "working"
    assert moved["contractor_id"] != old_contractor["contractor_id"]
    assert moved["parent_instance_id"] == root["instance"]["instance_id"]
    assert any(kind == "contractor" and payload["status"] == "ended"
               and payload["contractor_id"] == old_contractor["contractor_id"] for kind, payload in messages)
    judge.apply_batch([observe(Kind.SUBAGENT_STATUS, child, subagent_id="fixture-subagent", status="idle")])
    current = next(row for row in judge.snapshot(at)[2] if row["contractor_id"] == moved["contractor_id"])
    assert current["state"] == "idle" and current["tool"] is None
    judge.apply_batch([observe(Kind.PROCESS_EXITED, child)])
    assert judge.snapshot(at)[2] == []
    judge.apply_batch([observe(Kind.PROCESS_EXITED, parent)])
    assert all(agent["presence"] == "off_duty" for agent in judge.snapshot(at)[0])
