import http.server
import json
import threading

import pytest

from agentville.collector.sender import HttpSender


def test_refuses_token_over_plain_http_to_remote_host():
    with pytest.raises(ValueError):
        HttpSender("http://hq.example:8470", token="t")
    HttpSender("http://127.0.0.1:8470", token="t")
    HttpSender("https://hq.example:8470", token="t")
    with pytest.raises(ValueError):
        HttpSender("ftp://hq.example")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.server.mode == "ok":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")
            return
        if self.server.mode == "redirect":
            self.send_response(307)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.end_headers()
            return
        self.send_response(422)
        body = json.dumps({"detail": "schema: bad kind"}).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.mark.parametrize("mode,expected", [("redirect", "HTTP 307"), ("reject", "HTTP 422 schema: bad kind")])
def test_redirects_not_followed_and_error_detail_reported(mode, expected):
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.mode = mode
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = HttpSender(f"http://127.0.0.1:{server.server_port}", token="t")([{"kind": "heartbeat"}])
        assert not result.ok and result.error == expected
    finally:
        server.shutdown()


def test_loopback_hq_bypasses_environment_proxy(monkeypatch):
    servers = []
    for mode in ("ok", "reject"):
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        server.mode = mode
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
    hq, proxy = servers
    for name in ("no_proxy", "NO_PROXY", "all_proxy", "ALL_PROXY", "https_proxy", "HTTPS_PROXY", "HTTP_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{proxy.server_port}")
    try:
        assert HttpSender(f"http://127.0.0.1:{hq.server_port}", token="t")([{"kind": "heartbeat"}]).ok
    finally:
        for server in servers:
            server.shutdown()
