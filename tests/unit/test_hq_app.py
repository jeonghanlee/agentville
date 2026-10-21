import json
import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agentville.common.protocol import Envelope
from agentville.hq.app import create_app
from agentville.hq.store import Store

T0 = datetime(2026, 1, 1, tzinfo=UTC)
HOSTS = frozenset({"testserver"})
BRANCH = {"alias": "b", "country": "", "time": "UTC", "location": "", "thresholds": {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}}


def _client(tmp_path, tokens=None, loopback=frozenset({"testclient"}), hosts=HOSTS, **options):
    app = create_app(Store(str(tmp_path / "hq.sqlite3")), tokens, clock=lambda: T0, loopback=loopback, hosts=hosts, **options)
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
                                    loopback=frozenset({"testclient"}), hosts=HOSTS, viewer_token="v"))
    assert guarded.get("/api/v1/state").status_code == 401
    assert guarded.get("/api/v1/state", headers={"Authorization": "Bearer v"}).status_code == 200
    assert client.get("/api/v1/stats").json()["ingest"]["accepted"] == 1


def test_untrusted_loopback_requires_token(tmp_path):
    client = _client(tmp_path)
    app = create_app(Store(str(tmp_path / "other.sqlite3")), clock=lambda: T0, loopback=frozenset({"testclient"}), hosts=HOSTS, trust_loopback=False)
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
    with TestClient(create_app(store, loopback=frozenset({"testclient"}), hosts=HOSTS)) as client:
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
    with _client(tmp_path) as client, client.websocket_connect("/ws/v1/live") as ws:
        assert ws.receive_json() == {"type": "state", "state": {"branches": [], "agents": [], "activities": [], "contractors": []}}
        client.post("/api/v1/ingest/messages", json={"messages": [_snapshot()]})
        update = ws.receive_json()
        assert update["state"]["branches"][0]["branch_id"] == "b1"


def test_live_socket_requires_viewer_token_when_set(tmp_path):
    app = create_app(Store(str(tmp_path / "hq.sqlite3")), clock=lambda: T0, loopback=frozenset({"testclient"}), hosts=HOSTS, viewer_token="v")
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/v1/live") as ws:
            ws.receive_json()
    with client.websocket_connect("/ws/v1/live?token=v") as ws:
        assert ws.receive_json()["type"] == "state"


def test_dashboard_is_served(tmp_path):
    client = _client(tmp_path)
    page = client.get("/")
    assert page.status_code == 200 and "AgentVille" in page.text
    assert client.get("/app.js").status_code == 200
    assert client.get("/i18n.js").status_code == 200


def test_ingest_rejects_browser_requests(tmp_path):
    client = _client(tmp_path)
    body = json.dumps({"messages": [_snapshot()]})
    cross_site = client.post("/api/v1/ingest/messages", content=body,
                             headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
    assert cross_site.status_code == 403
    simple = client.post("/api/v1/ingest/messages", content=body, headers={"Content-Type": "text/plain"})
    assert simple.status_code == 415
    assert client.get("/api/v1/state").json()["branches"] == []


def test_foreign_host_is_rejected(tmp_path):
    client = _client(tmp_path)
    assert client.get("/api/v1/state", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/v1/state", headers={"Host": "testserver:8470"}).status_code == 200
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/v1/live", headers={"Host": "evil.example"}) as ws:
            ws.receive_json()
    open_app = TestClient(create_app(Store(str(tmp_path / "other.sqlite3")), clock=lambda: T0, hosts=None))
    assert open_app.get("/api/v1/state", headers={"Host": "evil.example"}).status_code == 200


def test_live_socket_accepts_same_origin_only(tmp_path):
    client = _client(tmp_path)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/v1/live", headers={"Origin": "https://evil.example"}) as ws:
            ws.receive_json()
    with client.websocket_connect("/ws/v1/live", headers={"Origin": "http://testserver"}) as ws:
        assert ws.receive_json()["type"] == "state"


def test_body_limit_applies_without_content_length(tmp_path):
    client = _client(tmp_path)

    def chunks():
        for _ in range(5):
            yield b" " * (1024 * 1024)

    response = client.post("/api/v1/ingest/messages", content=chunks(), headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_non_finite_numbers_and_deep_nesting_are_rejected(tmp_path):
    client = _client(tmp_path)
    for number in ("NaN", "Infinity", "1e999"):
        message = _snapshot()
        message["payload"]["agents"] = [{"agent_id": "a", "project_id": "p", "project_alias": "p", "provider": "claude",
                                         "seat": 1, "presence": "off_duty", "presence_since": "2026-01-01T00:00:00.000Z",
                                         "settings": {"effort": 0.5}}]
        body = json.dumps({"messages": [message]}).replace("0.5", number)
        response = client.post("/api/v1/ingest/messages", content=body, headers={"Content-Type": "application/json"})
        assert response.status_code == 400
    deep = client.post("/api/v1/ingest/messages", content=b"[" * 200000, headers={"Content-Type": "application/json"})
    assert deep.status_code == 400


def test_malformed_timestamp_is_rejected_before_storage(tmp_path):
    client = _client(tmp_path)
    bad = _snapshot()
    bad["sent_at"] = "garbageZ"
    assert client.post("/api/v1/ingest/messages", json={"messages": [bad]}).status_code == 422
    assert client.post("/api/v1/ingest/messages", json={"messages": [_snapshot()]}).status_code == 200


def test_untrusted_caller_without_a_known_token_is_rejected_before_parsing(tmp_path):
    client = _client(tmp_path, tokens={"b1": "s" * 16}, loopback=frozenset())
    response = client.post("/api/v1/ingest/messages", content=b"not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 401


def test_server_names_extend_host_and_origin(tmp_path):
    client = _client(tmp_path, server_names=frozenset({"hq.example"}))
    assert client.get("/api/v1/state", headers={"Host": "hq.example"}).status_code == 200
    with client.websocket_connect("/ws/v1/live", headers={"Origin": "https://hq.example"}) as ws:
        assert ws.receive_json()["type"] == "state"


def test_token_file_values_must_be_strong_strings(tmp_path):
    from agentville.hq.main import load_tokens

    path = tmp_path / "tokens.yaml"
    for content in ("b1:\n", "b1: yes\n", "b1: short\n", "- b1\n"):
        path.write_text(content)
        path.chmod(0o600)
        with pytest.raises(SystemExit):
            load_tokens(str(path))
    path.write_text("b1: " + "t" * 16 + "\n")
    assert load_tokens(str(path)) == {"b1": "t" * 16}


def test_server_name_requires_token_protection(tmp_path):
    from agentville.hq.main import main

    with pytest.raises(SystemExit):
        main(["--server-name", "hq.example", "--db", str(tmp_path / "hq.sqlite3")])
