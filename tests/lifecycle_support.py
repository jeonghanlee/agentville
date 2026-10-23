"""Real HTTP HQ servers and protocol input shared by lifecycle checks."""

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

import uvicorn

from agentville.collector.sender import HttpSender
from agentville.common.protocol import Envelope, iso
from agentville.hq.app import create_app
from agentville.hq.store import Store

ADMIN = "test-admin-credential-040"
VIEWER = "test-viewer-credential-040"
BRANCH_TOKEN = "test-branch-credential-040"
PROJECT = "example.test/team/shared"
BRANCH = {"alias": "Office", "country": "", "time": "UTC", "location": "",
          "thresholds": {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}}


def agent(branch="b1", duty=True):
    at = "2026-01-01T00:00:00.000Z"
    return {"agent_id": "agent-" + branch, "project_id": PROJECT, "project_alias": "Shared",
            "provider": "claude", "seat": 1, "presence": "on_duty" if duty else "off_duty", "presence_since": at,
            "instance": {"instance_id": "shift-" + branch, "started_at": at, "runtime": {"type": "shell"}} if duty else None}


def activity(branch="b1", state="idle"):
    return {"agent_id": "agent-" + branch, "instance_id": "shift-" + branch,
            "state": state, "state_since": "2026-01-01T00:00:00.000Z", "source": "session_file", "confidence": "high"}


def snapshot(branch="b1", duty=True):
    return {"branch": BRANCH, "agents": [agent(branch, duty)],
            "activities": [activity(branch)] if duty else [], "contractors": []}


class HQ:
    def __init__(self, path, clock=None, **options):
        self.path = path
        self.clock = clock or [datetime.now(UTC) - timedelta(seconds=30)]
        self.options = {"admin_token": ADMIN, **options}
        self.envelopes = {}

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}"
        self.store = Store(str(self.path), now=self.clock[0])
        self.app = create_app(self.store, clock=lambda: self.clock[0], **self.options)
        self.server = uvicorn.Server(uvicorn.Config(self.app, log_level="error"))
        self.thread = threading.Thread(target=lambda: self.server.run(sockets=[self.sock]), daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert self.server.started
        return self

    def __exit__(self, *args):
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.sock.close()
        assert not self.thread.is_alive()

    def advance(self, seconds=1):
        self.clock[0] += timedelta(seconds=seconds)

    def request(self, path, body=None, token=None, headers=None, params=None):
        if params:
            path += "?" + urllib.parse.urlencode(params)
        hdr = {"Content-Type": "application/json", **(headers or {})}
        if token is not None:
            hdr["Authorization"] = "Bearer " + token
        request = urllib.request.Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers=hdr)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            response = opener.open(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.code, json.loads(response.read())

    def get(self, path="/api/v1/state", **params):
        code, value = self.request(path, token=self.options.get("viewer_token"), params=params)
        assert code == 200, value
        return value

    def close(self, kind="branch", identity="b1"):
        code, value = self.request("/api/v1/lifecycle/close", {"kind": kind, "id": identity}, ADMIN)
        assert code == 200, value
        return value

    def send(self, kind="snapshot", payload=None, branch="b1", event=None, sent=None):
        env = self.envelopes.setdefault(branch, Envelope(branch))
        message = env.wrap(kind, event or self.clock[0], payload if payload is not None else snapshot(branch), sent or self.clock[0])
        tokens = self.options.get("tokens") or {}
        result = HttpSender(self.url, tokens.get(branch))([message])
        assert result.ok, result.error
        return message

    def life(self, kind="branch", identity="b1"):
        return next(v for v in self.get()["lifecycles"] if (v["kind"], v["id"]) == (kind, identity))
