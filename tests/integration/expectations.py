"""Shared fixture replay assertions for provider integration tests."""

import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schemas" / "protocol-v1.schema.json").read_text())


def load_scenario(scenario: Path):
    meta = yaml.safe_load((scenario / "meta.yaml").read_text())
    ops = [json.loads(line) for line in (scenario / "timeline.jsonl").read_text().splitlines()]
    expectations = {}
    for exp in meta["expect"]:
        expectations.setdefault(exp["after"], []).append(exp)
    return ops, expectations


def state_history(messages, agent_id):
    history = []
    for msg in messages:
        if msg["kind"] == "activity" and msg["payload"]["agent_id"] == agent_id:
            state = msg["payload"]["state"]
            if not history or history[-1] != state:
                history.append(state)
    return history


def check(replay, step, exp, refs, select):
    judge = replay.judge
    where = f"step {step}: {exp}"
    if "agent_count" in exp:
        assert len(judge.agents) == exp["agent_count"], where
    agent = select(exp)
    if agent is None:
        return
    if "seat" in exp:
        assert agent.seat == exp["seat"], where
    if "presence" in exp:
        assert agent.presence(replay.now, judge._leave_after) == exp["presence"], where
    if "state" in exp:
        assert agent.instance is not None and agent.instance.state == exp["state"], where
    if "tool" in exp:
        assert agent.instance.tool == exp["tool"], where
    if "workload" in exp:
        assert judge.activity_payload(agent, replay.now)["workload"] == exp["workload"], where
    if "states_since_start" in exp:
        assert state_history(replay.messages, agent.agent_id) == exp["states_since_start"], where
    if "ref" in exp:
        refs[exp["ref"]] = agent.agent_id
    if "same_as" in exp:
        assert agent.agent_id == refs[exp["same_as"]], where


def check_messages(messages):
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for msg in messages:
        validator.validate(msg)
    assert [m["seq"] for m in messages] == list(range(1, len(messages) + 1))
    event_times = [m["event_at"] for m in messages]
    assert event_times == sorted(event_times), "event_at must not decrease"
