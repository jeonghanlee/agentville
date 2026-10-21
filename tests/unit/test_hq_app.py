from datetime import UTC, datetime

from fastapi.testclient import TestClient

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
