"""Shared fixture replay assertions for provider integration tests."""

import json
from pathlib import Path

import jsonschema

from agentville.common.protocol import load_schema
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = load_schema()


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
    if "contractors_ended" in exp:
        ended = [m for m in replay.messages if m["kind"] == "contractor" and m["payload"]["status"] == "ended"]
        assert len(ended) == exp["contractors_ended"], where
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
    if "contractors" in exp:
        contractors = agent.instance.contractors.values() if agent.instance else []
        assert [{"state": c.state, "tool": c.tool} for c in contractors] == exp["contractors"], where
    if "reset_at" in exp:
        assert judge.activity_payload(agent, replay.now)["reset_at"] == exp["reset_at"], where
    if "workload" in exp:
        assert judge.activity_payload(agent, replay.now)["workload"] == exp["workload"], where
    if "states_since_start" in exp:
        assert state_history(replay.messages, agent.agent_id) == exp["states_since_start"], where
    if "ref" in exp:
        refs[exp["ref"]] = agent.agent_id
    if "same_as" in exp:
        assert agent.agent_id == refs[exp["same_as"]], where


# Placeholders for prompts, tool input, and provider identifiers that must stay on the Branch.
PRIVATE = ("<text>", "<tool-input>", "<tool-output>", "/home/user", "toolu_")


def check_messages(messages):
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for msg in messages:
        validator.validate(msg)
        text = json.dumps(msg)
        assert not any(p in text for p in PRIVATE), text
    assert [m["seq"] for m in messages] == list(range(1, len(messages) + 1))
    event_times = [m["event_at"] for m in messages]
    assert event_times == sorted(event_times), "event_at must not decrease"
