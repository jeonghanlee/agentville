import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import jsonschema
import pytest
import yaml

from agentville.collector.adapters.claude import ClaudeAdapter, encode_cwd
from agentville.collector.judge import Judge
from agentville.collector.project import Project
from agentville.common.protocol import Envelope

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "claude"
SCHEMA = json.loads((ROOT / "schemas" / "protocol-v1.schema.json").read_text())
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
        elif op["op"] == "log_append":
            lines = (self.scenario / op["file"]).read_text().splitlines(keepends=True)
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

    def states(self, agent_id):
        history = []
        for msg in self.messages:
            if msg["kind"] == "activity" and msg["payload"]["agent_id"] == agent_id:
                state = msg["payload"]["state"]
                if not history or history[-1] != state:
                    history.append(state)
        return history


@pytest.mark.parametrize("scenario", _scenarios(), ids=lambda p: f"{p.parent.name}-{p.name}")
def test_scenario(scenario, tmp_path):
    meta = yaml.safe_load((scenario / "meta.yaml").read_text())
    ops = [json.loads(line) for line in (scenario / "timeline.jsonl").read_text().splitlines()]
    expectations = {}
    for exp in meta["expect"]:
        expectations.setdefault(exp["after"], []).append(exp)
    replay = Replay(scenario, tmp_path / "home")
    refs = {}
    for step, op in enumerate(ops, start=1):
        replay.apply(op)
        for exp in expectations.get(step, []):
            agent = replay.agent(exp)
            where = f"step {step}: {exp}"
            if "seat" in exp:
                assert agent.seat == exp["seat"], where
            if "presence" in exp:
                assert agent.presence(replay.now, replay.judge._leave_after) == exp["presence"], where
            if "state" in exp:
                assert agent.instance is not None and agent.instance.state == exp["state"], where
            if "tool" in exp:
                assert agent.instance.tool == exp["tool"], where
            if "workload" in exp:
                assert replay.judge.activity_payload(agent, replay.now)["workload"] == exp["workload"], where
            if "states_since_start" in exp:
                assert replay.states(agent.agent_id) == exp["states_since_start"], where
            if "ref" in exp:
                refs[exp["ref"]] = agent.agent_id
            if "same_as" in exp:
                assert agent.agent_id == refs[exp["same_as"]], where
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for msg in replay.messages:
        validator.validate(msg)
    assert [m["seq"] for m in replay.messages] == list(range(1, len(replay.messages) + 1))
    event_times = [m["event_at"] for m in replay.messages]
    assert event_times == sorted(event_times), "event_at must not decrease"
