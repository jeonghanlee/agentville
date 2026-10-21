import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agentville.common.protocol import Envelope
from agentville.hq.app import create_app
from agentville.hq.store import Store

T0 = datetime(2026, 1, 1, tzinfo=UTC)
BRANCH = {"alias": "b", "country": "", "time": "UTC", "location": "", "thresholds": {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}}


def _client(tmp_path, tokens=None, loopback=frozenset({"testclient"})):
    app = create_app(Store(str(tmp_path / "hq.sqlite3")), tokens, clock=lambda: T0, loopback=loopback)
    return TestClient(app)


def _snapshot(branch_id="b1"):
    return Envelope(branch_id).wrap("snapshot", T0, {"branch": BRANCH, "agents": [], "activities": [], "contractors": []}, T0)


def test_loopback_ingest_and_state(tmp_path):
    client = _client(tmp_path)
    assert client.get("/health").json() == {"status": "ok"}
    response = client.post("/api/v1/ingest/messages", json={"messages": [_snapshot()]})
    assert response.status_code == 200 and response.json()["accepted"] == 1
    state = client.get("/api/v1/state").json()
    assert state["branches"][0]["branch_id"] == "b1" and state["branches"][0]["branch"]["alias"] == "b"


def test_remote_branch_requires_its_token(tmp_path):
    client = _client(tmp_path, tokens={"b1": "secret"}, loopback=frozenset())
    body = {"messages": [_snapshot()]}
    assert client.post("/api/v1/ingest/messages", json=body).status_code == 401
    assert client.post("/api/v1/ingest/messages", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/v1/ingest/messages", json=body, headers={"Authorization": "Bearer secret"}).status_code == 200
    other = {"messages": [_snapshot("b2")]}
    assert client.post("/api/v1/ingest/messages", json=other, headers={"Authorization": "Bearer secret"}).status_code == 401


def test_rejects_invalid_batches(tmp_path):
    client = _client(tmp_path)
    assert client.post("/api/v1/ingest/messages", json={"messages": []}).status_code == 400
    assert client.post("/api/v1/ingest/messages", json={"messages": [_snapshot("b1"), _snapshot("b2")]}).status_code == 400
    bad = _snapshot()
    bad["kind"] = "nonsense"
    assert client.post("/api/v1/ingest/messages", json={"messages": [bad]}).status_code == 422
    assert client.post("/api/v1/ingest/messages", content=b"not json", headers={"Content-Type": "application/json"}).status_code == 400


def test_viewer_token_guards_reads_and_stats(tmp_path):
    client = _client(tmp_path)
    client.post("/api/v1/ingest/messages", json={"messages": [_snapshot()]})
    guarded = TestClient(create_app(Store(str(tmp_path / "hq.sqlite3")), clock=lambda: T0,
                                    loopback=frozenset({"testclient"}), viewer_token="v"))
    assert guarded.get("/api/v1/state").status_code == 401
    assert guarded.get("/api/v1/state", headers={"Authorization": "Bearer v"}).status_code == 200
    assert client.get("/api/v1/stats").json()["ingest"]["accepted"] == 1


def test_untrusted_loopback_requires_token(tmp_path):
    client = _client(tmp_path)
    app = create_app(Store(str(tmp_path / "other.sqlite3")), clock=lambda: T0, loopback=frozenset({"testclient"}), trust_loopback=False)
    assert TestClient(app).post("/api/v1/ingest/messages", json={"messages": [_snapshot()]}).status_code == 401
    assert client.post("/api/v1/ingest/messages", json={"messages": [_snapshot()]}).status_code == 200


def test_malformed_branch_ids_and_large_bodies(tmp_path):
    client = _client(tmp_path)
    bad = _snapshot()
    bad["branch_id"] = ["x"]
    assert client.post("/api/v1/ingest/messages", json={"messages": [bad]}).status_code == 400
    big = b'{"messages": [' + b" " * (4 * 1024 * 1024 + 1) + b"]}"
    assert client.post("/api/v1/ingest/messages", content=big, headers={"Content-Type": "application/json"}).status_code == 413


def test_store_closed_on_shutdown(tmp_path):
    store = Store(str(tmp_path / "hq.sqlite3"))
    with TestClient(create_app(store, loopback=frozenset({"testclient"}))) as client:
        client.post("/api/v1/ingest/messages", json={"messages": [_snapshot()]})
    with pytest.raises(sqlite3.ProgrammingError):
        store.state(T0)
    assert not (tmp_path / "hq.sqlite3-wal").exists() or (tmp_path / "hq.sqlite3-wal").stat().st_size == 0


def test_hq_refuses_remote_bind_without_viewer_token(tmp_path):
    from agentville.hq.main import main

    with pytest.raises(SystemExit):
        main(["--host", "0.0.0.0", "--db", str(tmp_path / "hq.sqlite3")])
    with pytest.raises(SystemExit):
        main(["--host", "0.0.0.0", "--allow-remote", "--db", str(tmp_path / "hq.sqlite3")])


def test_live_socket_sends_state_on_connect_and_after_ingest(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/v1/live") as ws:
        assert ws.receive_json() == {"type": "state", "state": {"branches": [], "agents": [], "activities": [], "contractors": []}}
        client.post("/api/v1/ingest/messages", json={"messages": [_snapshot()]})
        update = ws.receive_json()
        assert update["state"]["branches"][0]["branch_id"] == "b1"


def test_live_socket_requires_viewer_token_when_set(tmp_path):
    app = create_app(Store(str(tmp_path / "hq.sqlite3")), clock=lambda: T0, loopback=frozenset({"testclient"}), viewer_token="v")
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/v1/live") as ws:
            ws.receive_json()
    with client.websocket_connect("/ws/v1/live?token=v") as ws:
        assert ws.receive_json()["type"] == "state"


def test_dashboard_is_served(tmp_path):
    client = _client(tmp_path)
    page = client.get("/")
    assert page.status_code == 200 and "AGENTVILLE" in page.text
    assert client.get("/app.js").status_code == 200
