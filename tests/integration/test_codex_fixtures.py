import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from agentville.collector.adapters.codex import CodexAdapter
from agentville.collector.appserver import AppServerError
from agentville.collector.judge import Judge
from agentville.collector.project import Project
from agentville.common.protocol import Envelope
from tests.integration.expectations import check, check_messages, load_scenario

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "codex"
FIXTURE_HOME = "/home/user/.codex"
PROJECT = Project("github.com/example/repo", "repo")


class FixedResolver:
    def resolve(self, cwd):
        return PROJECT


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
    def __init__(self, scenario: Path, home: Path):
        self.scenario = scenario
        self.home = home
        self.now = None
        self.messages = []
        self.daemon = FakeDaemon()
        envelope = Envelope("branch-test")
        self.adapter = CodexAdapter(str(home), connect=self.daemon.connect, clock=lambda: self.now)
        self.judge = Judge(
            FixedResolver(), lambda kind, at, payload: self.messages.append(envelope.wrap(kind, at, payload, self.now))
        )

    def _thread(self, data):
        if data.get("path"):
            data["path"] = data["path"].replace(FIXTURE_HOME, str(self.home))
        return data

    def apply(self, op):
        self.now = datetime.fromisoformat(op["at"].replace("Z", "+00:00"))
        kind = op["op"]
        if kind == "appserver_thread":
            thread = self._thread(json.loads((self.scenario / op["file"]).read_text()))
            self.daemon.threads[thread["id"]] = thread
            self.daemon._load(thread["id"])
        elif kind == "appserver_notify":
            message = json.loads((self.scenario / op["file"]).read_text())
            if "thread" in message["params"]:
                self._thread(message["params"]["thread"])
            self.daemon.apply(message["method"], message["params"])
        elif kind == "appserver_disconnect":
            if self.daemon.connection is not None:
                self.daemon.connection.broken = True
        elif kind == "log_append":
            lines = (self.scenario / op["file"]).read_text().splitlines(keepends=True)
            target = self.home / op["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            start, end = op["lines"]
            with open(target, "a") as fh:
                fh.writelines(lines[start:end])
        for obs in self.adapter.poll():
            self.judge.apply(obs)

    def agent(self, exp):
        if "seat" not in exp and not any(k in exp for k in ("state", "presence", "tool", "workload", "states_since_start", "ref", "same_as")):
            return None
        return next(a for a in self.judge.agents if a.seat == exp.get("seat", 1))


def _scenarios():
    return sorted(p for p in FIXTURES.glob("*/*") if (p / "meta.yaml").exists())


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
