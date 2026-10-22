import base64
import json
import os
import socket
import threading
import time
import urllib.request
from datetime import UTC, datetime

import uvicorn
from websockets.sync.client import connect

from agentville.common.protocol import Envelope
from agentville.hq.app import create_app
from agentville.hq.store import Store

T0 = datetime(2026, 1, 1, tzinfo=UTC)
BRANCH = {"alias": "b", "country": "", "time": "UTC", "location": "", "thresholds": {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(tmp_path, **options):
    port = _free_port()
    app = create_app(Store(str(tmp_path / "hq.sqlite3")), **options)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    return server, port


def _ingest(port, agents):
    message = Envelope("b1").wrap("snapshot", T0, {"branch": BRANCH, "agents": agents, "activities": [], "contractors": []}, T0)
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1/ingest/messages",
                                     data=json.dumps({"messages": [message]}).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def _stalled_viewer(port):
    # Completes the WebSocket handshake, then never reads.
    s = socket.create_connection(("127.0.0.1", port))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET /ws/v1/live HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    return s


def test_stalled_viewer_does_not_freeze_other_viewers(tmp_path):
    server, port = _serve(tmp_path, live_refresh=0.2, send_timeout=0.5)
    try:
        agents = [{"agent_id": f"a{i}", "project_id": "p" * 200, "project_alias": "p", "provider": "claude", "seat": 1,
                   "presence": "off_duty", "presence_since": "2026-01-01T00:00:00.000Z"} for i in range(3000)]
        assert _ingest(port, agents)["accepted"] == 1
        stalled = _stalled_viewer(port)
        with connect(f"ws://127.0.0.1:{port}/ws/v1/live", max_size=None) as viewer:
            received, deadline = 0, time.monotonic() + 6
            while time.monotonic() < deadline:
                viewer.recv(timeout=3)
                received += 1
            assert received >= 10
        stalled.close()
    finally:
        server.should_exit = True


def test_rejected_socket_receives_its_close_code(tmp_path):
    server, port = _serve(tmp_path, viewer_token="v" * 16, auth_timeout=0.5)
    try:
        for first in (None, json.dumps({"type": "auth", "token": "w" * 16})):
            with connect(f"ws://127.0.0.1:{port}/ws/v1/live") as viewer:
                if first is not None:
                    viewer.send(first)
                try:
                    viewer.recv(timeout=3)
                except Exception:  # noqa: BLE001 - the close is what is examined
                    pass
                assert viewer.close_code == 4401
        with connect(f"ws://127.0.0.1:{port}/ws/v1/live") as viewer:
            viewer.send(json.dumps({"type": "auth", "token": "v" * 16}))
            assert json.loads(viewer.recv(timeout=3))["type"] == "state"
        with connect(f"ws://127.0.0.1:{port}/ws/v1/live", additional_headers={"Origin": "https://evil.example"}) as viewer:
            try:
                viewer.recv(timeout=3)
            except Exception:  # noqa: BLE001
                pass
            assert viewer.close_code == 4403
    finally:
        server.should_exit = True
