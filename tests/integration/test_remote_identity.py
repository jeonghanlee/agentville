import json
import socket
import threading
import time
from datetime import UTC, datetime

import uvicorn

from agentville.collector.config import parse
from agentville.collector.main import Collector, SeqStore
from agentville.collector.project import GitProjectResolver
from agentville.collector.sender import HttpSender, SHARED_HOST_WARNING
from agentville.hq.app import create_app
from agentville.hq.store import Store

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_copied_identity_warning_exact_retries_tokens_and_proxy(tmp_path, capsys, monkeypatch):
    store = Store(str(tmp_path / "hq.sqlite3"))
    token = "synthetic-branch-token-030"
    app = create_app(store, tokens={"shared": token}, trust_loopback=False)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("NO_PROXY", "")
        url = f"http://127.0.0.1:{port}"
        sender = HttpSender(url, token)
        for alias in ("First", "Second"):
            config = parse({"host": {"id": "shared", "alias": alias}})
            collector = Collector(config, sender, [], GitProjectResolver("shared"),
                                  SeqStore(str(tmp_path / alias / "seq")), clock=lambda: NOW)
            collector.tick()
            collector.close()
        assert "agentville-collector: " + SHARED_HOST_WARNING in capsys.readouterr().err
        with store._lock:
            rows = store._db.execute("SELECT branch_id, seq, kind, event_at, sent_at, payload FROM messages ORDER BY seq").fetchall()
        messages = [{"schema_version": 1, "branch_id": r[0], "seq": r[1], "kind": r[2],
                     "event_at": r[3], "sent_at": r[4], "payload": json.loads(r[5])} for r in rows]
        assert messages
        assert sender(messages).ok and not sender(messages).shared_host_id
        assert not HttpSender(url)(messages).ok
        assert not HttpSender(url, "wrong-token")(messages).ok
        heartbeat = next(message for message in messages if message["kind"] == "heartbeat")
        heartbeat["payload"]["interval"] += 1
        assert sender([heartbeat]).shared_host_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()
