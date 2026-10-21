"""Read-only JSON-RPC client for the Codex app-server control socket.

Transport: WebSocket (RFC 6455) over a Unix stream socket, JSON-RPC in text frames.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import select
import socket
import struct
from collections import deque
from typing import Any, Protocol

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class AppServerError(Exception):
    pass


class RpcConnection(Protocol):
    def request(self, method: str, params: dict[str, Any]) -> Any: ...

    def drain(self) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


def _mask(payload: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % 4] for i, b in enumerate(payload))


def encode_frame(opcode: int, payload: bytes) -> bytes:
    """Encode one final, client-masked frame."""
    n = len(payload)
    if n < 126:
        header = struct.pack(">BB", 0x80 | opcode, 0x80 | n)
    elif n < 1 << 16:
        header = struct.pack(">BBH", 0x80 | opcode, 0x80 | 126, n)
    else:
        header = struct.pack(">BBQ", 0x80 | opcode, 0x80 | 127, n)
    key = os.urandom(4)
    return header + key + _mask(payload, key)


def decode_frame(buf: bytes) -> tuple[bool, int, bytes, int] | None:
    """Return (fin, opcode, payload, consumed) for one complete frame in buf, or None."""
    if len(buf) < 2:
        return None
    fin = bool(buf[0] & 0x80)
    opcode = buf[0] & 0x0F
    masked = bool(buf[1] & 0x80)
    n = buf[1] & 0x7F
    i = 2
    if n == 126:
        if len(buf) < 4:
            return None
        n = struct.unpack(">H", buf[2:4])[0]
        i = 4
    elif n == 127:
        if len(buf) < 10:
            return None
        n = struct.unpack(">Q", buf[2:10])[0]
        i = 10
    key = b""
    if masked:
        if len(buf) < i + 4:
            return None
        key = buf[i : i + 4]
        i += 4
    if len(buf) < i + n:
        return None
    payload = buf[i : i + n]
    return fin, opcode, _mask(payload, key) if masked else payload, i + n


class AppServerClient:
    def __init__(self, socket_path: str, client_name: str = "agentville", client_version: str = "0", timeout: float = 5.0) -> None:
        self.socket_path = socket_path
        self.client_name = client_name
        self.client_version = client_version
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buf = b""
        self._fragments: list[bytes] = []
        self._next_id = 0
        self._notifications: deque[dict[str, Any]] = deque()

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.socket_path)
            key = base64.b64encode(os.urandom(16)).decode()
            sock.sendall(
                (
                    "GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                    f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
                ).encode()
            )
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    raise AppServerError("connection closed during handshake")
                data += chunk
        except OSError as exc:
            sock.close()
            raise AppServerError(str(exc)) from exc
        head, self._buf = data.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        headers = {k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in lines[1:])}
        expected = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
        if " 101 " not in f"{lines[0]} " or headers.get("sec-websocket-accept") != expected:
            sock.close()
            raise AppServerError(f"unexpected handshake response: {lines[0]}")
        self._sock = sock
        result = self.request(
            "initialize",
            {"clientInfo": {"name": self.client_name, "version": self.client_version}, "capabilities": {"experimentalApi": False}},
        )
        if not isinstance(result, dict):
            raise AppServerError("invalid initialize result")
        self._send({"jsonrpc": "2.0", "method": "initialized"})

    def request(self, method: str, params: dict[str, Any]) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = self._receive(self.timeout)
            if message is None:
                raise AppServerError(f"timeout waiting for {method}")
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise AppServerError(f"{method}: {message['error']}")
                return message.get("result")
            self._queue(message)

    def drain(self) -> list[dict[str, Any]]:
        while (message := self._receive(0)) is not None:
            self._queue(message)
        out = list(self._notifications)
        self._notifications.clear()
        return out

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.sendall(encode_frame(OP_CLOSE, b""))
            except OSError:
                pass
            self._sock.close()
            self._sock = None

    def _queue(self, message: dict[str, Any]) -> None:
        # Server-to-client requests (approvals) are never answered; only notifications are kept.
        if "method" in message and "id" not in message:
            self._notifications.append(message)

    def _send(self, message: dict[str, Any]) -> None:
        self._write(encode_frame(OP_TEXT, json.dumps(message).encode()))

    def _write(self, data: bytes) -> None:
        if self._sock is None:
            raise AppServerError("not connected")
        try:
            self._sock.sendall(data)
        except OSError as exc:
            self.close()
            raise AppServerError(str(exc)) from exc

    def _receive(self, timeout: float) -> dict[str, Any] | None:
        while True:
            frame = decode_frame(self._buf)
            if frame is not None:
                fin, opcode, payload, consumed = frame
                self._buf = self._buf[consumed:]
                if opcode == OP_PING:
                    self._write(encode_frame(OP_PONG, payload))
                    continue
                if opcode == OP_PONG:
                    continue
                if opcode == OP_CLOSE:
                    self.close()
                    raise AppServerError("closed by server")
                self._fragments.append(payload)
                if not fin:
                    continue
                text = b"".join(self._fragments)
                self._fragments.clear()
                try:
                    message = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict):
                    return message
                continue
            if self._sock is None:
                raise AppServerError("not connected")
            ready, _, _ = select.select([self._sock], [], [], timeout)
            if not ready:
                return None
            try:
                chunk = self._sock.recv(65536)
            except OSError as exc:
                self.close()
                raise AppServerError(str(exc)) from exc
            if not chunk:
                self.close()
                raise AppServerError("connection closed")
            self._buf += chunk
