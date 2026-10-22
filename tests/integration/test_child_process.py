import io
import json
import os
import select
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import jsonschema

from agentville.collector.adapters.claude import ClaudeAdapter
from agentville.collector.adapters.codex import CodexAdapter
from agentville.collector.config import parse
from agentville.collector.main import Collector, SeqStore, jsonl_deliver
from agentville.collector.process import ProcessTable
from agentville.collector.project import GitProjectResolver
from agentville.collector.roster import Roster
from agentville.common.protocol import load_schema
from tests.unit.test_process import write_process

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "process"


def receipt(worker):
    assert select.select([worker.stdout], [], [], 10)[0], "worker did not become ready"
    line = worker.stdout.readline()
    assert line, "worker exited before its readiness receipt"
    return line


@pytest.mark.parametrize("private", [False, True], ids=["open-fds", "non-dumpable"])
def test_s05_real_processes_through_collector(tmp_path, private):
    fixture = json.loads((FIXTURES / "S05/scenario.json").read_text())
    home = tmp_path / "codex"
    path = home / "sessions/2026/01/01" / f"rollout-2026-01-01T00-00-00-{fixture['thread_id']}.jsonl"
    path.parent.mkdir(parents=True)
    worker = subprocess.Popen([sys.executable, str(FIXTURES / "worker.py"), str(path),
                               "private" if private else "public"], cwd=tmp_path,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    collector = None
    try:
        identities = json.loads(receipt(worker))
        table = ProcessTable()
        table.refresh()
        child = table.processes[identities["child"]]
        assert child.started_at is not None
        if private:
            with pytest.raises(PermissionError):
                list(Path(f"/proc/{child.pid}/fd").iterdir())
        at = datetime.fromtimestamp(child.started_at + 0.1, tz=UTC).isoformat()
        records = fixture["rollout_records"]
        for record in records:
            record["timestamp"] = at
        records[0]["payload"].update({"timestamp": at, "cwd": str(tmp_path)})
        path.write_text(json.dumps(records[0]) + "\n")
        claude = tmp_path / "claude"
        (claude / "sessions").mkdir(parents=True)
        session = {**fixture["parent"], "pid": identities["parent"],
                   "procStart": identities["parent_start"], "cwd": str(tmp_path)}
        (claude / "sessions" / f"{identities['parent']}.json").write_text(json.dumps(session))
        stream = io.StringIO()
        collector = Collector(parse({"host": {"id": "branch-s05", "alias": "S05"}}),
                              jsonl_deliver(stream), [CodexAdapter(str(home)), ClaudeAdapter(str(claude))],
                              GitProjectResolver("branch-s05"), SeqStore(str(tmp_path / "seq")),
                              roster=Roster(str(tmp_path / "roster.json")))
        collector.tick()
        agents, _, contractors = collector.judge.snapshot(datetime.now(UTC))
        assert len(agents) == len(contractors) == 1
        assert agents[0]["provider"] == "claude"
        assert contractors[0]["origin"] == "child_process" and contractors[0]["provider"] == "codex"
        assert contractors[0]["parent_instance_id"] == agents[0]["instance"]["instance_id"]
        with path.open("a") as fh:
            fh.write("\n".join(json.dumps(record) for record in records[1:3]) + "\n")
        collector.tick()
        assert collector.judge.snapshot(datetime.now(UTC))[2][0]["tool"] == "exec_command"
        with path.open("a") as fh:
            fh.write(json.dumps(records[3]) + "\n")
        collector.tick()
        assert collector.judge.snapshot(datetime.now(UTC))[2][0]["tool"] is None
        assert collector.judge.snapshot(datetime.now(UTC))[2][0]["state"] == "working"
        with path.open("a") as fh:
            fh.write(json.dumps(records[4]) + "\n")
        collector.tick()
        worker.stdin.write("stop-child\n")
        worker.stdin.flush()
        assert receipt(worker).strip() == "child-stopped"
        collector.tick()
        assert collector.judge.snapshot(datetime.now(UTC))[2] == []
        collector.tick()
        assert len(collector.judge.agents) == 1
        collector.close()
        collector = None
        restarted_stream = io.StringIO()
        restarted = Collector(parse({"host": {"id": "branch-s05", "alias": "S05"}}),
                              jsonl_deliver(restarted_stream), [CodexAdapter(str(home)), ClaudeAdapter(str(claude))],
                              GitProjectResolver("branch-s05"), SeqStore(str(tmp_path / "seq")),
                              roster=Roster(str(tmp_path / "roster.json")))
        try:
            restarted.tick()
            assert len(restarted.judge.agents) == 1
            assert restarted.judge.agents[0].agent_id == agents[0]["agent_id"]
            assert restarted.judge.agents[0].instance is not None
            assert restarted.judge.snapshot(datetime.now(UTC))[2] == []
            with path.open("a") as fh:
                fh.write(json.dumps(records[1]) + "\n")
            restarted.tick()
            assert len(restarted.judge.agents) == 2
            codex_agent = next(agent for agent in restarted.judge.agents if agent.provider == "codex")
            assert codex_agent.instance.state == "working"
        finally:
            restarted.close()
        messages = [json.loads(line) for line in stream.getvalue().splitlines()]
        validator = jsonschema.Draft202012Validator(load_schema(), format_checker=jsonschema.FormatChecker())
        for message in messages:
            validator.validate(message)
        assert [message["seq"] for message in messages] == list(range(1, len(messages) + 1))
        assert fixture["thread_id"] not in stream.getvalue()
        assert str(tmp_path) not in stream.getvalue()
        assert "arguments" not in stream.getvalue()
    finally:
        if collector is not None:
            collector.close()
        if worker.poll() is None:
            worker.stdin.write("exit\n")
            worker.stdin.flush()
        worker.wait(timeout=10)
        assert worker.returncode == 0


@pytest.mark.parametrize("late_parent", [False, True], ids=["known-parent", "late-parent"])
def test_s05_reused_parent_pid_does_not_keep_child_hired(tmp_path, late_parent):
    fixture = json.loads((FIXTURES / "S05/scenario.json").read_text())
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "stat").write_text(f"btime {fixture['boot_epoch']}\n")
    for row in fixture["processes"]:
        write_process(proc, row, tmp_path)
    claude, codex = tmp_path / "claude", tmp_path / "codex"
    (claude / "sessions").mkdir(parents=True)
    session = {**fixture["parent"], "pid": 1001, "procStart": "1000000", "cwd": str(tmp_path)}
    if not late_parent:
        (claude / "sessions/1001.json").write_text(json.dumps(session))
    table = ProcessTable(str(proc))
    table.refresh()
    now = datetime.fromtimestamp(table.processes[2001].started_at + 1, tz=UTC)
    path = codex / "sessions/2026/01/01" / f"rollout-2026-01-01T00-00-00-{fixture['thread_id']}.jsonl"
    path.parent.mkdir(parents=True)
    meta = fixture["rollout_records"][0]
    meta["payload"].update({"timestamp": now.isoformat(), "cwd": str(tmp_path)})
    path.write_text(json.dumps(meta) + "\n")
    os.utime(path, (now.timestamp(), now.timestamp()))
    fd = proc / "2001/fd"
    fd.mkdir()
    (fd / "7").symlink_to(path)
    stream = io.StringIO()
    collector = Collector(parse({"host": {"id": "fixture-branch"}}), jsonl_deliver(stream),
                          [CodexAdapter(str(codex), clock=lambda: now, proc_root=str(proc)),
                           ClaudeAdapter(str(claude), clock=lambda: now, proc_root=str(proc))],
                          GitProjectResolver("fixture-branch"), SeqStore(str(tmp_path / "seq")),
                          clock=lambda: now, proc_root=str(proc))
    try:
        collector.tick()
        assert len(collector.judge.agents) == 1
        assert len(collector.judge.snapshot(now)[2]) == (0 if late_parent else 1)
        nested = fixture["nested_process"]
        write_process(proc, nested, tmp_path)
        nested_session = {**fixture["parent"], "sessionId": "66666666-6666-4666-8666-666666666666",
                          "pid": nested["pid"], "procStart": str(nested["start"]), "cwd": str(tmp_path)}
        (claude / "sessions/3001.json").write_text(json.dumps(nested_session))
        collector.tick()
        previous_contractors = collector.judge.snapshot(now)[2]
        if late_parent:
            assert len(previous_contractors) == 1
            previous_id = collector.judge.agents[0].agent_id
            (claude / "sessions/1001.json").write_text(json.dumps(session))
            collector.tick()
            previous = next(agent for agent in collector.judge.agents if agent.agent_id == previous_id)
            assert previous.instance is None
        agents, _, contractors = collector.judge.snapshot(now)
        on_duty = [agent for agent in agents if agent["presence"] == "on_duty"]
        assert len(on_duty) == 1 and len(contractors) == 2
        assert {contractor["provider"] for contractor in contractors} == {"claude", "codex"}
        assert all(contractor["origin"] == "child_process" and
                   contractor["parent_instance_id"] == on_duty[0]["instance"]["instance_id"] for contractor in contractors)
        if late_parent:
            messages = [json.loads(line) for line in stream.getvalue().splitlines()]
            ended = [message["payload"]["contractor_id"] for message in messages
                     if message["kind"] == "contractor" and message["payload"]["status"] == "ended"]
            assert previous_contractors[0]["contractor_id"] in ended
            assert previous_contractors[0]["contractor_id"] not in {row["contractor_id"] for row in contractors}
        write_process(proc, {**fixture["processes"][0], "start": 1000030}, tmp_path)
        collector.tick()
        assert all(agent.instance is None for agent in collector.judge.agents)
        assert collector.judge.snapshot(now)[2] == []
        with path.open("a") as fh:
            fh.write(json.dumps(fixture["rollout_records"][2]) + "\n")
        collector.tick()
        assert len(collector.judge.agents) == (2 if late_parent else 1)
        assert collector.judge.snapshot(now)[2] == []
        validator = jsonschema.Draft202012Validator(load_schema(), format_checker=jsonschema.FormatChecker())
        for line in stream.getvalue().splitlines():
            validator.validate(json.loads(line))
    finally:
        collector.close()


@pytest.mark.parametrize("parent_first", [False, True], ids=["child-adapter-first", "parent-adapter-first"])
def test_s05_late_parent_session_reclassifies_the_child(tmp_path, parent_first):
    fixture = json.loads((FIXTURES / "S05/scenario.json").read_text())
    claude, codex = tmp_path / "claude", tmp_path / "codex"
    (claude / "sessions").mkdir(parents=True)
    rollout = codex / "sessions/2026/01/01" / f"rollout-2026-01-01T00-00-00-{fixture['thread_id']}.jsonl"
    rollout.parent.mkdir(parents=True)
    worker = subprocess.Popen([sys.executable, str(FIXTURES / "worker.py"), str(rollout), "public"],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=tmp_path)
    collector = None
    try:
        identities = json.loads(receipt(worker))
        table = ProcessTable()
        table.refresh()
        child = table.processes[identities["child"]]
        record = fixture["rollout_records"][0]
        record["payload"].update({"timestamp": datetime.fromtimestamp(child.started_at + 0.1, tz=UTC).isoformat(),
                                  "cwd": str(tmp_path)})
        rollout.write_text(json.dumps(record) + "\n")
        stream = io.StringIO()
        adapters = [CodexAdapter(str(codex)), ClaudeAdapter(str(claude))]
        if parent_first:
            adapters.reverse()
        collector = Collector(parse({"host": {"id": "late-parent"}}), jsonl_deliver(stream), adapters,
                              GitProjectResolver("late-parent"), SeqStore(str(tmp_path / "seq")),
                              roster=Roster(str(tmp_path / "roster.json")))
        collector.tick()
        assert [agent.provider for agent in collector.judge.agents if agent.instance] == ["codex"]
        previous = collector.judge.agents[0]
        previous_id, previous_sessions = previous.agent_id, list(previous.sessions)
        with rollout.open("a") as fh:
            fh.write("\n".join(json.dumps(row) for row in fixture["rollout_records"][1:3]) + "\n")
        collector.tick()
        assert previous.instance.state == "working" and previous.instance.tool == "exec_command"
        document = {**fixture["parent"], "pid": identities["parent"],
                    "procStart": identities["parent_start"], "cwd": str(tmp_path)}
        (claude / "sessions" / f"{identities['parent']}.json").write_text(json.dumps(document))
        collector.tick()
        agents, _, contractors = collector.judge.snapshot(datetime.now(UTC))
        assert [agent["provider"] for agent in agents if agent["presence"] == "on_duty"] == ["claude"]
        assert len(contractors) == 1 and contractors[0]["origin"] == "child_process"
        assert contractors[0]["state"] == "working" and contractors[0]["tool"] == "exec_command"
        assert previous.agent_id == previous_id and previous.instance is None
        assert previous.sessions == previous_sessions
        saved = next(row for row in Roster(str(tmp_path / "roster.json")).load() if row["agent_id"] == previous_id)
        assert not saved["on_duty"] and saved["sessions"] == previous_sessions
        messages = [json.loads(line) for line in stream.getvalue().splitlines()]
        off_duty = [row for row in messages if row["kind"] == "agent"
                    and row["payload"]["agent_id"] == previous_id and row["payload"]["presence"] == "off_duty"]
        assert len(off_duty) == 1
        assert off_duty[0]["payload"]["instance"] is None
        hired = next(row for row in messages if row["kind"] == "contractor")
        assert off_duty[0]["seq"] < hired["seq"]
        collector.tick()
        assert collector.judge.snapshot(datetime.now(UTC))[2] == contractors
        with rollout.open("a") as fh:
            fh.write(json.dumps(fixture["rollout_records"][3]) + "\n")
        collector.tick()
        assert collector.judge.snapshot(datetime.now(UTC))[2][0]["tool"] is None
        collector.close()
        collector = Collector(parse({"host": {"id": "late-parent"}}), jsonl_deliver(stream),
                              [CodexAdapter(str(codex)), ClaudeAdapter(str(claude))],
                              GitProjectResolver("late-parent"), SeqStore(str(tmp_path / "seq")),
                              roster=Roster(str(tmp_path / "roster.json")))
        collector.tick()
        restored = next(agent for agent in collector.judge.agents if agent.agent_id == previous_id)
        assert restored.instance is None and restored.sessions == previous_sessions
        assert len(collector.judge.snapshot(datetime.now(UTC))[2]) == 1
        worker.stdin.write("stop-child\n")
        worker.stdin.flush()
        assert receipt(worker).strip() == "child-stopped"
        collector.tick()
        assert collector.judge.snapshot(datetime.now(UTC))[2] == []
        validator = jsonschema.Draft202012Validator(load_schema(), format_checker=jsonschema.FormatChecker())
        for line in stream.getvalue().splitlines():
            validator.validate(json.loads(line))
    finally:
        if collector is not None:
            collector.close()
        if worker.poll() is None:
            worker.stdin.write("exit\n")
            worker.stdin.flush()
        worker.wait(timeout=10)
        assert worker.returncode == 0
