import json
import socket
import threading
import time
import urllib.request
from datetime import UTC, datetime

import uvicorn

from agentville.collector.config import parse
from agentville.collector.main import Collector, SeqStore
from agentville.collector.project import Project
from agentville.collector.sender import HttpSender
from agentville.common.observations import Kind, Observation, ShiftKey, Source
from agentville.hq.app import create_app
from agentville.hq.store import Store

T0 = datetime(2026, 1, 1, tzinfo=UTC)


class Resolver:
    def resolve(self, cwd):
        return Project("github.com/example/repo", "repo")


class OneShot:
    def __init__(self, observations):
        self.observations = observations

    def poll(self):
        out, self.observations = self.observations, []
        return out


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_collector_to_hq_over_http(tmp_path):
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(Store(str(tmp_path / "hq.sqlite3"))), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    try:
        key = ShiftKey("claude", "1:1")
        adapter = OneShot([
            Observation(Kind.PROCESS_STARTED, key, T0, T0, Source.SESSION_FILE, {"cwd": "/r", "session_id": "s1", "runtime": {"type": "shell"}}),
            Observation(Kind.SESSION_STATUS, key, T0, T0, Source.SESSION_FILE, {"status": "active"}),
        ])
        url = f"http://127.0.0.1:{port}"
        collector = Collector(parse({"host": {"id": "branch-e2e", "alias": "Home"}}), HttpSender(url), [adapter],
                              Resolver(), SeqStore(str(tmp_path / "seq")), clock=lambda: T0)
        collector.tick()
        with urllib.request.urlopen(f"{url}/api/v1/state", timeout=5) as response:
            state = json.loads(response.read())
        assert state["branches"][0]["branch"]["alias"] == "Home"
        assert state["agents"][0]["project_id"] == "github.com/example/repo"
        assert state["activities"][0]["state"] == "working"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
