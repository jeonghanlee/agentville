import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from agentville.collector.adapters.codex import CodexAdapter
from agentville.collector.appserver import AppServerError
from agentville.collector.config import account_alias
from agentville.collector.judge import Judge
from agentville.common.protocol import Envelope
from tests.integration.expectations import (
    CONDITION_FOR,
    FixtureResolver,
    check,
    check_messages,
    find_agent,
    load_scenario,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "codex"
FIXTURE_HOME = "/home/user/.codex"


def fixture_home(number):
    """Fixture path of Codex home ``number``, as written by the generator."""
    return FIXTURE_HOME if number == 1 else f"{FIXTURE_HOME}-{number}"


class FakeDaemon:
    """In-memory app-server state; connections see notifications queued after they connect."""

    def __init__(self):
        self.threads = {}
        self.loaded = []
        self.pending = []
        self.connection = None

    def connect(self):
        self.connection = FakeConnection(self)
        self.pending.clear()
        return self.connection

    def apply(self, method, params):
        thread_id = params.get("threadId")
        if method == "thread/started":
            thread = params["thread"]
            self.threads[thread["id"]] = thread
            self._load(thread["id"])
        elif method == "thread/closed":
            self._unload(thread_id)
        elif method == "thread/status/changed":
            if params["status"]["type"] == "notLoaded":
                self._unload(thread_id)
            else:
                self.threads[thread_id]["status"] = params["status"]
                self._load(thread_id)
        self.pending.append({"method": method, "params": params})

    def _load(self, thread_id):
        if thread_id not in self.loaded:
            self.loaded.append(thread_id)

    def _unload(self, thread_id):
        if thread_id in self.loaded:
            self.loaded.remove(thread_id)
        if thread_id in self.threads:
            self.threads[thread_id]["status"] = {"type": "notLoaded"}


class FakeConnection:
    def __init__(self, daemon):
        self.daemon = daemon
        self.broken = False

    def request(self, method, params):
        if self.broken:
            raise AppServerError("broken")
        if method == "thread/loaded/list":
            return {"data": list(self.daemon.loaded), "nextCursor": None}
        if method == "thread/read":
            return {"thread": json.loads(json.dumps(self.daemon.threads[params["threadId"]]))}
        raise AssertionError(f"unexpected method {method}")

    def drain(self):
        if self.broken:
            raise AppServerError("broken")
        out = list(self.daemon.pending)
        self.daemon.pending.clear()
        return out

    def close(self):
        pass


class Replay:
    """Replays a scenario against one Codex home per ``home`` number used in the timeline (default 1).

    Each home has its own daemon and Adapter with the account alias a new configuration gives it.
    """

    def __init__(self, scenario: Path, root: Path, homes: int = 1):
        self.scenario = scenario
        self.now = None
        self.messages = []
        self.homes = {n: root / ("home" if n == 1 else f"home-{n}") for n in range(1, homes + 1)}
        self.daemons = {n: FakeDaemon() for n in self.homes}
        self.adapters = [
            CodexAdapter(str(home), connect=self.daemons[n].connect, clock=lambda: self.now,
                         account_alias=account_alias("codex", n))
            for n, home in self.homes.items()
        ]
        envelope = Envelope("branch-test")
        self.judge = Judge(
            FixtureResolver(),
            lambda kind, at, payload: self.messages.append(envelope.wrap(kind, at, payload, self.now)),
            condition_for=CONDITION_FOR,
        )

    def _thread(self, data, number):
        prefix = fixture_home(number) + "/"
        if (data.get("path") or "").startswith(prefix):
            data["path"] = f"{self.homes[number]}/{data['path'][len(prefix):]}"
        return data

    def apply(self, op):
        self.now = datetime.fromisoformat(op["at"].replace("Z", "+00:00"))
        kind = op["op"]
        number = op.get("home", 1)
        daemon = self.daemons[number]
        if kind == "appserver_thread":
            thread = self._thread(json.loads((self.scenario / op["file"]).read_text()), number)
            daemon.threads[thread["id"]] = thread
            daemon._load(thread["id"])
        elif kind == "appserver_notify":
            message = json.loads((self.scenario / op["file"]).read_text())
            if "thread" in message["params"]:
                self._thread(message["params"]["thread"], number)
            daemon.apply(message["method"], message["params"])
        elif kind == "appserver_disconnect":
            if daemon.connection is not None:
                daemon.connection.broken = True
        elif kind == "log_append":
            lines = (self.scenario / op["file"]).read_text().splitlines(keepends=True)
            target = self.homes[number] / op["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            start, end = op["lines"]
            with open(target, "a") as fh:
                fh.writelines(lines[start:end])
        for adapter in self.adapters:
            for obs in adapter.poll():
                self.judge.apply(obs)

    def agent(self, exp):
        return find_agent(self.judge.agents, exp)


def _scenarios():
    return sorted(p for p in FIXTURES.glob("*/*") if (p / "meta.yaml").exists())


@pytest.mark.parametrize("scenario", _scenarios(), ids=lambda p: f"{p.parent.name}-{p.name}")
def test_scenario(scenario, tmp_path):
    ops, expectations = load_scenario(scenario)
    replay = Replay(scenario, tmp_path, homes=max(op.get("home", 1) for op in ops))
    refs = {}
    for step, op in enumerate(ops, start=1):
        replay.apply(op)
        for exp in expectations.get(step, []):
            check(replay, step, exp, refs, replay.agent)
    check_messages(replay.messages)
