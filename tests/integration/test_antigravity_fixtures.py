import io
import json
import copy
import select
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from agentville.collector.adapters.antigravity import AntigravityAdapter, TAIL_WINDOW
from agentville.collector.config import parse
from agentville.collector.main import Collector, SeqStore, jsonl_deliver
from agentville.collector.project import GitProjectResolver
from agentville.common.protocol import load_schema

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "antigravity"


@pytest.mark.parametrize("history_at_attach,large_history", [(False, False), (True, False), (True, True)],
                         ids=["fresh-history", "existing-history", "history-beyond-tail"])
def test_real_presence_lock_and_shipped_transcript(tmp_path, history_at_attach, large_history):
    home = tmp_path / "gemini"
    app = home / "antigravity-cli"
    presence = app / "presence"
    presence.mkdir(parents=True)
    (presence / "stale.lock").touch()
    lock = presence / "11111111-1111-4111-8111-111111111111.lock"
    transcript = app / "brain" / lock.stem / ".system_generated/logs/transcript.jsonl"
    transcript.parent.mkdir(parents=True)
    lines = (FIXTURES / "1.4.5/S01/transcript.jsonl").read_text().splitlines(keepends=True)
    if history_at_attach:
        padding = lines[-1] * (TAIL_WINDOW // len(lines[-1]) + 1) if large_history else ""
        transcript.write_text("".join(lines) + padding)
        if large_history:
            assert transcript.stat().st_size > TAIL_WINDOW
    worker = subprocess.Popen([sys.executable, str(FIXTURES / "worker.py"), str(lock)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=tmp_path)
    try:
        assert select.select([worker.stdout], [], [], 10)[0]
        assert worker.stdout.readline().strip() == "locked"
        stream = io.StringIO()
        now = datetime(2026, 1, 1, tzinfo=UTC)
        adapter = AntigravityAdapter(str(home), clock=lambda: now)
        collector = Collector(parse({"host": {"id": "branch-agy"}}), jsonl_deliver(stream), [adapter],
                              GitProjectResolver("branch-agy"), SeqStore(str(tmp_path / "seq")), clock=lambda: now)
        collector.tick()
        assert len(collector.judge.agents) == 1
        assert collector.judge.agents[0].provider == "antigravity"
        expected = [("working", None), ("working", "run_command"), ("working", None), ("idle", None), ("error", None)]
        if not history_at_attach:
            for line, (state, tool) in zip(lines, expected, strict=True):
                with transcript.open("a") as fh:
                    fh.write(line)
                now = datetime.fromisoformat(json.loads(line)["created_at"].replace("Z", "+00:00"))
                collector.tick()
                inst = collector.judge.agents[0].instance
                assert (inst.state, inst.tool) == (state, tool)
        inst = collector.judge.agents[0].instance
        assert (inst.state, inst.tool) == ("error", None)
        count = 0 if history_at_attach else 1
        assert collector.judge.activity_payload(collector.judge.agents[0], now)["workload"] == count
        transcript.rename(transcript.with_name("transcript.1.jsonl"))
        transcript.write_text("".join(lines))
        collector.tick()
        assert (inst.state, inst.tool) == ("error", None)
        assert collector.judge.activity_payload(collector.judge.agents[0], now)["workload"] == count
        transcript.write_text(lines[0])
        collector.tick()
        assert (inst.state, inst.tool) == ("error", None)
        assert collector.judge.activity_payload(collector.judge.agents[0], now)["workload"] == count
        for source, state, tool in [(1, "working", "run_command"), (2, "working", None), (3, "idle", None)]:
            row = copy.deepcopy(json.loads(lines[source]))
            row["step_index"] += 10
            row["created_at"] = f"2026-01-01T00:00:{source + 10:02d}Z"
            now = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            with transcript.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            collector.tick()
            assert (inst.state, inst.tool) == (state, tool)
        assert collector.judge.activity_payload(collector.judge.agents[0], now)["workload"] == count + 1
        collector.tick()
        assert (inst.state, inst.tool) == ("idle", None)
        worker.stdin.write("exit\n")
        worker.stdin.flush()
        worker.wait(timeout=10)
        collector.tick()
        assert collector.judge.agents[0].instance is None
        assert len(collector.judge.agents) == 1
        validator = jsonschema.Draft202012Validator(load_schema(), format_checker=jsonschema.FormatChecker())
        for line in stream.getvalue().splitlines():
            validator.validate(json.loads(line))
        assert all(value not in stream.getvalue() for value in (str(tmp_path), "<text>", "<error>", "CommandLine", "<tool-output>"))
    finally:
        if worker.poll() is None:
            worker.stdin.write("exit\n")
            worker.stdin.flush()
            worker.wait(timeout=10)
        assert worker.returncode == 0
