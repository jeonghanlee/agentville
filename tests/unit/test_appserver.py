import base64
import hashlib
import json
import socket
import struct
import threading
import time

import pytest

from agentville.collector.appserver import (
    OP_CLOSE,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    AppServerClient,
    AppServerError,
    decode_frame,
    encode_frame,
)

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def server_frame(opcode, payload, fin=True):
    n = len(payload)
    first = (0x80 if fin else 0) | opcode
    if n < 126:
        header = struct.pack(">BB", first, n)
    elif n < 1 << 16:
        header = struct.pack(">BBH", first, 126, n)
    else:
        header = struct.pack(">BBQ", first, 127, n)
    return header + payload


class FakeDaemon:
    """Single-connection app-server stand-in driven by a script function."""

    def __init__(self, path, script, accept_override=None):
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(path)
        self.listener.listen(1)
        self.script = script
        self.accept_override = accept_override
        self.received = []
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        conn, _ = self.listener.accept()
        self.conn = conn
        data = b""
        while b"\r\n\r\n" not in data:
            data += conn.recv(4096)
        head, self.buf = data.split(b"\r\n\r\n", 1)
        key = next(l.split(":", 1)[1].strip() for l in head.decode().split("\r\n") if l.lower().startswith("sec-websocket-key"))
        accept = self.accept_override or base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        conn.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n".encode())
        try:
            self.script(self)
        except OSError:
            pass

    def recv(self):
        while True:
            frame = decode_frame(self.buf)
            if frame:
                _, opcode, payload, used = frame
                self.buf = self.buf[used:]
                self.received.append((opcode, payload))
                return opcode, json.loads(payload) if opcode == OP_TEXT else payload
            chunk = self.conn.recv(65536)
            if not chunk:
                raise OSError("closed")
            self.buf += chunk

    def send(self, obj, opcode=OP_TEXT):
        self.conn.sendall(server_frame(opcode, json.dumps(obj).encode()))

    def answer_initialize(self):
        _, msg = self.recv()
        assert msg["method"] == "initialize" and msg["jsonrpc"] == "2.0"
        self.send({"id": msg["id"], "result": {"codexHome": "/home/user/.codex"}})
        _, note = self.recv()
        assert note == {"jsonrpc": "2.0", "method": "initialized"}


def test_frame_round_trip_with_extended_lengths():
    for size in (5, 300, 70000):
        payload = b"x" * size
        fin, opcode, decoded, used = decode_frame(encode_frame(OP_TEXT, payload))
        assert (fin, opcode, decoded) == (True, OP_TEXT, payload)
        assert used == len(encode_frame(OP_TEXT, payload))
    assert decode_frame(encode_frame(OP_TEXT, b"abc")[:-1]) is None


def test_request_buffers_notifications_and_answers_ping(tmp_path):
    path = str(tmp_path / "s.sock")

    def script(d):
        d.answer_initialize()
        _, msg = d.recv()
        assert msg["method"] == "thread/loaded/list"
        d.send({"method": "thread/status/changed", "params": {"threadId": "t1", "status": {"type": "idle"}}})
        d.conn.sendall(server_frame(OP_PING, b"hb"))
        big = json.dumps({"id": msg["id"], "result": {"data": ["t1"], "pad": "y" * 70000}}).encode()
        d.conn.sendall(server_frame(OP_TEXT, big[:10], fin=False) + server_frame(0x0, big[10:]))
        opcode, payload = d.recv()
        assert (opcode, payload) == (OP_PONG, b"hb")
        d.send({"id": 99, "method": "item/commandExecution/requestApproval", "params": {}})
        d.send({"method": "thread/closed", "params": {"threadId": "t1"}})
        d.recv()

    FakeDaemon(path, script)
    client = AppServerClient(path, timeout=2)
    client.connect()
    assert client.request("thread/loaded/list", {})["data"] == ["t1"]
    deadline = time.time() + 2
    notes = []
    while time.time() < deadline and len(notes) < 2:
        notes += client.drain()
    assert [n["method"] for n in notes] == ["thread/status/changed", "thread/closed"]
    assert client.dropped_requests == 1
    client.close()


def test_handshake_rejects_wrong_accept(tmp_path):
    path = str(tmp_path / "s.sock")
    FakeDaemon(path, lambda d: None, accept_override="wrong")
    with pytest.raises(AppServerError):
        AppServerClient(path, timeout=2).connect()


def test_server_close_raises(tmp_path):
    path = str(tmp_path / "s.sock")

    def script(d):
        d.answer_initialize()
        d.conn.sendall(server_frame(OP_CLOSE, b""))

    FakeDaemon(path, script)
    client = AppServerClient(path, timeout=2)
    client.connect()
    with pytest.raises(AppServerError):
        for _ in range(50):
            client.drain()
            time.sleep(0.02)


def test_missing_socket_raises(tmp_path):
    with pytest.raises(AppServerError):
        AppServerClient(str(tmp_path / "absent.sock"), timeout=1).connect()


def test_failed_initialize_closes_socket(tmp_path):
    path = str(tmp_path / "s.sock")

    def script(d):
        _, msg = d.recv()
        d.send({"id": msg["id"], "error": {"code": -1, "message": "no"}})

    FakeDaemon(path, script)
    client = AppServerClient(path, timeout=2)
    with pytest.raises(AppServerError):
        client.connect()
    assert client._sock is None


def test_request_deadline_covers_unrelated_traffic(tmp_path):
    path = str(tmp_path / "s.sock")

    def script(d):
        d.answer_initialize()
        d.recv()
        for _ in range(20):
            d.send({"method": "skills/changed", "params": {}})
            time.sleep(0.05)

    FakeDaemon(path, script)
    client = AppServerClient(path, timeout=0.3)
    client.connect()
    started = time.monotonic()
    with pytest.raises(AppServerError):
        client.request("thread/loaded/list", {})
    assert time.monotonic() - started < 0.8
