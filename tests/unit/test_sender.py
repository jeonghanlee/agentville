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
