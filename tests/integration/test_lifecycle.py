import io
import json
import os
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from websockets.sync.client import connect

from agentville.collector.adapters.claude import ClaudeAdapter
from agentville.collector.config import parse
from agentville.collector.main import Collector, SeqStore
from agentville.collector.project import GitProjectResolver
from agentville.collector.sender import HttpSender
from agentville.common.protocol import iso
from agentville.common.protocol import Envelope
from agentville.hq.notify import Notifier, NotifyConfig, Outbox, http_post
from tests.lifecycle_support import ADMIN, BRANCH_TOKEN, PROJECT, VIEWER, HQ, activity, agent, snapshot
from tests.unit.test_claude_proc import _write_stat

ROOT = Path(__file__).resolve().parents[2]
OLD = "2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf"


def test_malformed_origin_is_rejected_without_mutation_or_server_failure(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq:
        hq.send()
        before = hq.life()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for origin in ("http://[", "http://[::1", "https://untrusted.example"):
            request = urllib.request.Request(
                hq.url + "/api/v1/lifecycle/close", method="POST",
                data=json.dumps({"kind": "branch", "id": "b1"}).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + ADMIN, "Origin": origin},
            )
            with pytest.raises(urllib.error.HTTPError) as error:
                opener.open(request, timeout=5)
            assert error.value.code == 403
            assert json.loads(error.value.read()) == {"detail": "invalid origin"}
            assert hq.life() == before
        status, value = hq.request("/api/v1/lifecycle/close", {"kind": "branch", "id": "b1"}, ADMIN,
                                   headers={"Origin": hq.url})
        assert status == 200 and value["closed"] and value["revision"] == before["revision"] + 1


def test_administrator_authority_is_separate_and_fail_closed(tmp_path):
    with HQ(tmp_path / "hq.sqlite3", viewer_token=VIEWER, tokens={"b1": BRANCH_TOKEN}, trust_loopback=False) as hq:
        hq.send()
        for token in (None, VIEWER, BRANCH_TOKEN, "wrong-credential"):
            assert hq.request("/api/v1/lifecycle/close", {"kind": "branch", "id": "b1"}, token)[0] == 401
            assert not hq.life()["closed"]
        assert hq.request("/api/v1/state", token=ADMIN)[0] == 401
        assert hq.request("/api/v1/lifecycle/close", {"kind": "branch", "id": "b1"}, ADMIN,
                          headers={"Origin": "https://untrusted.example"})[0] == 403
        for body in ({}, {"kind": [], "id": "b1"}, {"kind": "branch", "id": []}):
            assert hq.request("/api/v1/lifecycle/close", body, ADMIN)[0] == 400
        assert hq.request("/api/v1/lifecycle/close", {"kind": "project", "id": "missing"}, ADMIN)[0] == 404
        assert hq.close()["closed"]
        assert hq.close()["revision"] == 1
    with HQ(tmp_path / "disabled.sqlite3", admin_token=None) as hq:
        hq.send()
        assert hq.request("/api/v1/lifecycle/close", {"kind": "branch", "id": "b1"}, ADMIN)[0] == 503


def test_reopening_uses_accepted_reports_current_instances_and_global_project(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq:
        initial = hq.send()
        hq.send(branch="b2")
        hq.advance()
        hq.close(); hq.close("project", PROJECT)
        assert hq.life("project", PROJECT)["closed"]
        hq.advance()
        hq.send("heartbeat", {"interval": 30})
        assert hq.life()["closed"]
        assert HttpSender(hq.url)([initial]).ok
        assert hq.life()["closed"]
        gap = dict(initial, kind="heartbeat", payload={"interval": 30}, seq=6)
        assert HttpSender(hq.url)([gap]).ok
        hq.envelopes["b1"].seq = 6
        stale = dict(initial, kind="agent", payload=agent(), seq=5)
        code, result = hq.request("/api/v1/ingest/messages", {"messages": [stale]})
        assert code == 200 and result["stale"] == 1
        assert hq.life()["closed"]
        hq.send("activity", {**activity(), "instance_id": "previous-shift"})
        assert hq.life()["closed"]
        hq.send("agent", agent(duty=False))
        assert hq.life()["closed"]
        hq.send("snapshot", {"branch": snapshot()["branch"], "agents": [], "activities": [], "contractors": []})
        assert hq.life()["closed"] and hq.life("project", PROJECT)["closed"]
        hq.advance()
        hq.send("snapshot", snapshot("b2"), branch="b2", event=hq.clock[0] - timedelta(days=1), sent=hq.clock[0] - timedelta(hours=1))
        assert not hq.life("project", PROJECT)["closed"]
        assert hq.life()["closed"]
        hq.send("agent", agent(), event=hq.clock[0] - timedelta(days=1))
        assert not hq.life()["closed"]
        assert hq.life()["reopen_count"] == 1
        assert hq.life("project", PROJECT)["reopen_count"] == 1


def test_history_checkpoints_retention_restart_and_work_log_preservation(tmp_path):
    path = tmp_path / "hq.sqlite3"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = [start]
    with HQ(path, clock) as hq:
        hq.send(); hq.send(branch="b2")
        clock[0] += timedelta(hours=1)
        before = hq.clock[0]
        hq.send("heartbeat", {"interval": 3600})
        params = {"from": iso(start), "to": iso(before)}
        original = hq.get("/api/v1/worklog", **params)
        hq.close(); hq.close("project", PROJECT)
        hq.advance(30)
        closed = clock[0]
        assert hq.get("/api/v1/state", at=iso(closed))["lifecycles"] == hq.get()["lifecycles"]
        assert hq.get("/api/v1/worklog", **params) == original
        hq.advance(30)
        reopened = clock[0]
        hq.send("activity", activity(), event=start)
        hq.send("heartbeat", {"interval": 3600}, branch="b2")
        hq.advance(3600)
        hq.send("heartbeat", {"interval": 3600})
        hq.store.prune(before - timedelta(seconds=1))
        events = hq.get("/api/v1/changes", **{"from": iso(before - timedelta(seconds=1)), "to": iso(clock[0]), "branch_id": "b2"})["changes"]
        project_events = [v for v in events if v["kind"] == "lifecycle" and v["target_kind"] == "project"]
        assert [v["closed"] for v in project_events] == [True, False]
        assert [v["at"] for v in project_events] == [iso(before), iso(reopened)]
        state = hq.get("/api/v1/state", at=iso(closed))
        assert all(v["closed"] for v in state["lifecycles"] if v["id"] in ("b1", PROJECT))
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] > 0
    with HQ(path, clock) as hq:
        assert not hq.life()["closed"] and not hq.life("project", PROJECT)["closed"]
        assert hq.life()["reopen_count"] == 1
        assert hq.get("/api/v1/state", at=iso(closed)) == state


def test_actual_collector_idle_polls_and_newly_discovered_idle_agent(tmp_path):
    home = tmp_path / "home"; (home / "sessions").mkdir(parents=True)
    proc = tmp_path / "proc"
    _write_stat(proc, 1001, "claude", "1000000")
    clock = [datetime(2026, 1, 1, tzinfo=UTC)]
    with HQ(tmp_path / "hq.sqlite3", clock) as hq:
        adapter = ClaudeAdapter(str(home), clock=lambda: clock[0], proc_root=str(proc))
        collector = Collector(parse({"host": {"id": "b1"}}), HttpSender(hq.url), [adapter],
                              GitProjectResolver("b1"), SeqStore(str(tmp_path / "seq")), clock=lambda: clock[0], proc_root=str(proc))
        try:
            collector.tick(); hq.close()
            hq.advance(31); collector.tick()
            assert hq.life()["closed"]
            shutil.copyfile(ROOT / "tests/fixtures/claude/2.1.303/S01/sessions/001-1001.json", home / "sessions/1001.json")
            hq.advance(31); collector.tick()
            assert not hq.life()["closed"]
            hq.close(); hq.advance(31); collector.tick()
            assert hq.life()["closed"]
        finally:
            collector.close()


def test_real_ntfy_transport_and_live_socket_report_reopening_once(tmp_path):
    delivered = []
    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            delivered.append((self.headers.get("Title"), self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200); self.end_headers()
        def log_message(self, *args):
            pass
    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=receiver.serve_forever, daemon=True); thread.start()
    config = NotifyConfig(f"http://127.0.0.1:{receiver.server_port}/alerts", events=frozenset({"reopened"}))
    outbox = Outbox(http_post(config))
    try:
        with HQ(tmp_path / "hq.sqlite3", notifier=Notifier(config, outbox.put), notify_interval=0.02, live_refresh=0.02) as hq:
            hq.send(); hq.advance(); hq.close(); hq.close("project", PROJECT)
            with connect(hq.url.replace("http:", "ws:") + "/ws/v1/live") as live:
                assert any(v["closed"] for v in json.loads(live.recv(timeout=3))["state"]["lifecycles"])
                hq.advance(); report = hq.send()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    state = json.loads(live.recv(timeout=3))["state"]
                    if any(v["reopen_count"] for v in state["lifecycles"]):
                        break
                assert all(not v["closed"] for v in state["lifecycles"])
                assert HttpSender(hq.url)([report]).ok
                deadline = time.monotonic() + 3
                while len(delivered) < 2 and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert len(delivered) == 2
                assert {title for title, _ in delivered} == {"Branch Office reopened", "Project Shared reopened"}
                hq.close(); hq.advance(); hq.send()
                assert len(delivered) == 2
                hq.advance(31); hq.send("heartbeat", {"interval": 30})
                deadline = time.monotonic() + 3
                while len(delivered) < 3 and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert len(delivered) == 3
                hq.advance(); hq.close(); hq.advance(); hq.send()
                hq.advance(); hq.close()
                hq.advance(31); hq.send("heartbeat", {"interval": 30})
    finally:
        outbox.close(); receiver.shutdown(); receiver.server_close(); thread.join(timeout=3)
    assert len(delivered) == 3


OLD_PREPARE = '''
import json, sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from agentville.common.protocol import Envelope, iso
from agentville.hq.app import create_app
from agentville.hq.store import Store
import agentville.hq.store as implementation

base = Path.cwd()
assert str(Path(implementation.__file__).resolve()).startswith(str(base / "old" / "packages"))
now = [datetime(2026, 1, 1, tzinfo=UTC)]
start = now[0]
store = Store(str(base / "original.sqlite3"), now=now[0])
branch = {"alias":"Office","country":"","time":"UTC","location":"","thresholds":{"phone":300,"doze":1800,"lounge":3600,"leave":604800}}
envs = {b:Envelope(b) for b in ("b1","b2")}
with TestClient(create_app(store, clock=lambda:now[0], retention=timedelta(hours=2), loopback=frozenset({"testclient"}), hosts=frozenset({"testserver"}))) as client:
    def send(b, kind, payload):
        result = client.post("/api/v1/ingest/messages", json={"messages":[envs[b].wrap(kind,now[0],payload,now[0])]})
        assert result.status_code == 200 and result.json()["accepted"] == 1
    for b in envs:
        a = {"agent_id":"agent-"+b,"project_id":"example.test/team/shared","project_alias":"Shared","provider":"claude","seat":1,"presence":"on_duty" if b=="b1" else "off_duty","presence_since":iso(start)}
        activities = []
        if b=="b1":
            a["instance"]={"instance_id":"shift-b1","started_at":iso(start),"runtime":{"type":"shell"}}
            activities=[{"agent_id":"agent-b1","instance_id":"shift-b1","state":"idle","state_since":iso(start),"source":"session_file","confidence":"high"}]
        send(b,"snapshot",{"branch":branch,"agents":[a],"activities":activities,"contractors":[]})
    for hour in (1,2,3):
        now[0]=start+timedelta(hours=hour)
        send("b1","activity",{"agent_id":"agent-b1","instance_id":"shift-b1","state":"waiting" if hour==2 else "working","state_since":iso(now[0]),"source":"session_file","confidence":"high"})
        send("b2","heartbeat",{"interval":30})
    now[0]+=timedelta(seconds=60)
    for b in envs: send(b,"heartbeat",{"interval":30})
    period={"from":iso(start+timedelta(hours=1)),"to":iso(now[0])}
    queries={"state":("/api/v1/state",{}),"past":("/api/v1/state",{"at":iso(start+timedelta(hours=1,minutes=30))}),"history":("/api/v1/history",{}),"changes":("/api/v1/changes",period),"worklog":("/api/v1/worklog",period)}
    result={name:{"path":path,"params":params,"value":client.get(path,params=params).json()} for name,(path,params) in queries.items()}
    (base/"expected.json").write_text(json.dumps({"now":iso(now[0]),"queries":result,"source":implementation.__file__},indent=2))
with sqlite3.connect(base/"original.sqlite3") as db:
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    assert db.execute("SELECT COUNT(*) FROM baseline").fetchone()[0]>0
    assert db.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]>0
'''


def test_upgrade_from_actual_published_030_writer_preserves_existing_observations(tmp_path):
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", OLD], check=True, capture_output=True).stdout
    old = tmp_path / "old"; old.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(old, filter="data")
    env = {**os.environ, "PYTHONPATH": str(old / "packages"), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-c", OLD_PREPARE], cwd=tmp_path, env=env, capture_output=True, text=True)
    (tmp_path / "old-writer.stdout").write_text(result.stdout)
    (tmp_path / "old-writer.stderr").write_text(result.stderr)
    assert result.returncode == 0, result.stderr
    original = tmp_path / "original.sqlite3"
    import hashlib
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    expected = json.loads((tmp_path / "expected.json").read_text())
    copy = tmp_path / "upgrade.sqlite3"; shutil.copyfile(original, copy)
    clock = [datetime.fromisoformat(expected["now"].replace("Z", "+00:00"))]
    with HQ(copy, clock) as hq:
        for name, entry in expected["queries"].items():
            actual = hq.get(entry["path"], **entry["params"])
            previous = entry["value"]
            if name in ("state", "past"):
                actual.pop("lifecycles")
            if name == "state":
                assert all(not b["reachable"] for b in actual["branches"])
                for b in previous["branches"]:
                    b["reachable"] = False
            assert actual == previous, name
        assert all(not v["closed"] for v in hq.get()["lifecycles"])
        hq.close(); hq.close("project", PROJECT)
        closed = hq.get()["lifecycles"]
    with HQ(copy, clock) as hq:
        assert hq.get()["lifecycles"] == closed
        last = next(b["last_seq"] for b in hq.get()["branches"] if b["branch_id"] == "b1")
        hq.envelopes["b1"] = Envelope("b1", seq=last)
        hq.advance(); hq.send()
        assert not hq.life()["closed"] and not hq.life("project", PROJECT)["closed"]
    assert hashlib.sha256(original.read_bytes()).hexdigest() == original_hash
    (tmp_path / "upgrade-receipt.json").write_text(json.dumps({"old_commit": OLD, "original_sha256": original_hash,
        "queries_compared": list(expected["queries"]), "copy": str(copy)}, indent=2))
    print("Upgrade evidence:", tmp_path)


def private_file(path, content):
    path.write_text(content)
    path.chmod(0o600)
    return str(path)


def cli_command(tmp_path, admin):
    viewer = private_file(tmp_path / "viewer.token", VIEWER + "\n")
    branch = private_file(tmp_path / "tokens.yaml", "b1: " + BRANCH_TOKEN + "\n")
    return [sys.executable, "-m", "agentville.hq.main", "--port", "0", "--db", str(tmp_path / "cli.sqlite3"),
            "--viewer-token-file", viewer, "--tokens", branch, "--no-trust-loopback", "--admin-token-file", admin]


def test_real_cli_private_credentials_and_http_authority(tmp_path):
    admin = private_file(tmp_path / "admin.token", ADMIN + "\n")
    command = cli_command(tmp_path, admin)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "packages")}
    log = tmp_path / "hq.stderr"
    with log.open("w") as output:
        process = subprocess.Popen(command, stdout=output, stderr=output, env=env)
        try:
            deadline = time.monotonic() + 10
            match = None
            while process.poll() is None and time.monotonic() < deadline:
                match = re.search(r"serving (http://127\.0\.0\.1:\d+)/", log.read_text())
                if match:
                    break
                time.sleep(0.01)
            assert match, log.read_text()
            client = HQ(tmp_path / "cli.sqlite3", viewer_token=VIEWER, tokens={"b1": BRANCH_TOKEN})
            client.url = match[1]
            while time.monotonic() < deadline:
                try:
                    if client.request("/health")[0] == 200:
                        break
                except OSError:
                    time.sleep(0.01)
            client.send()
            for token in (None, VIEWER, BRANCH_TOKEN):
                assert client.request("/api/v1/lifecycle/close", {"kind": "branch", "id": "b1"}, token)[0] == 401
            assert client.close()["closed"]
            assert client.request("/api/v1/state", token=ADMIN)[0] == 401
            assert client.life()["closed"]
        finally:
            process.terminate()
            process.wait(timeout=10)
    (tmp_path / "hq.exit-status").write_text(str(process.returncode))
    assert process.returncode in (0, -signal.SIGTERM), log.read_text()


@pytest.mark.parametrize("content, mode, reason", [
    ("", 0o600, "administrator token must be distinct"),
    ("short", 0o600, "administrator token must be distinct"),
    ("invalid credential with spaces", 0o600, "administrator token must be distinct"),
    ("invalid-credential-" + chr(233), 0o600, "administrator token must be distinct"),
    (VIEWER, 0o600, "administrator token must be distinct"),
    (BRANCH_TOKEN, 0o600, "administrator token must be distinct"),
    (ADMIN, 0o644, "must not be accessible by group or others"),
])
def test_real_cli_rejects_unsafe_admin_before_database_or_listen(tmp_path, content, mode, reason):
    admin = Path(private_file(tmp_path / "admin.token", content))
    admin.chmod(mode)
    result = subprocess.run(cli_command(tmp_path, str(admin)), env={**os.environ, "PYTHONPATH": str(ROOT / "packages")},
                            capture_output=True, text=True, timeout=10)
    (tmp_path / "hq.stderr").write_text(result.stderr)
    assert result.returncode != 0 and reason in result.stderr
    assert "serving " not in result.stderr
    assert not (tmp_path / "cli.sqlite3").exists()
