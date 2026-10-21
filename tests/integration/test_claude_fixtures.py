import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from agentville.collector.adapters.claude import ClaudeAdapter, encode_cwd
from agentville.collector.judge import Judge
from agentville.collector.project import Project
from agentville.common.protocol import Envelope
from tests.integration.expectations import check, check_messages, load_scenario

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "claude"
PROJECT = Project("github.com/example/repo", "repo")


class FixedResolver:
    def resolve(self, cwd):
        return PROJECT


def _scenarios():
    return sorted(p for p in FIXTURES.glob("*/*") if (p / "meta.yaml").exists())


class Replay:
    def __init__(self, scenario: Path, home: Path):
        self.scenario = scenario
        self.home = home
        self.now = None
        self.messages = []
        envelope = Envelope("branch-test")
        self.adapter = ClaudeAdapter(str(home), clock=lambda: self.now, is_alive=lambda pid, start: True)
        self.judge = Judge(
            FixedResolver(),
            lambda kind, at, payload: self.messages.append(envelope.wrap(kind, at, payload, self.now)),
        )
        (home / "sessions").mkdir(parents=True)

    def apply(self, op):
        self.now = datetime.fromisoformat(op["at"].replace("Z", "+00:00"))
        if op["op"] == "session_write":
            shutil.copy(self.scenario / op["file"], self.home / "sessions" / f"{op['pid']}.json")
        elif op["op"] == "session_remove":
            os.remove(self.home / "sessions" / f"{op['pid']}.json")
        elif op["op"] == "file_write":
            target = self.home / op["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.scenario / op["file"], target)
        elif op["op"] == "log_append":
            lines = (self.scenario / op["file"]).read_text().splitlines(keepends=True)
            if "path" in op:
                target = self.home / op["path"]
            else:
                target = self.home / "projects" / encode_cwd(op["cwd"]) / f"{op['session']}.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            start, end = op["lines"]
            with open(target, "a") as fh:
                fh.writelines(lines[start:end])
        for obs in self.adapter.poll():
            self.judge.apply(obs)

    def agent(self, exp):
        if "pid" in exp:
            prefix = f"{exp['pid']}:"
            return next(a for a in self.judge.agents if a.instance and a.instance.shift.native_id.startswith(prefix))
        return next(a for a in self.judge.agents if a.seat == exp.get("seat", 1))



@pytest.mark.parametrize("scenario", _scenarios(), ids=lambda p: f"{p.parent.name}-{p.name}")
def test_scenario(scenario, tmp_path):
    ops, expectations = load_scenario(scenario)
    replay = Replay(scenario, tmp_path / "home")
    refs = {}
    for step, op in enumerate(ops, start=1):
        replay.apply(op)
        for exp in expectations.get(step, []):
            check(replay, step, exp, refs, replay.agent)
    check_messages(replay.messages)
