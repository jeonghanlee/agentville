"""An outer HTTP boundary serving preserved MET Norway input to the real client."""

import copy
import json
import threading
from datetime import datetime
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CAPTURE = Path(__file__).parent / "fixtures/weather/met-locationforecast.json"


class MetServer:
    def __init__(self):
        self.document = json.loads(CAPTURE.read_bytes())
        self.now = [datetime.fromisoformat(self.document["properties"]["timeseries"][0]["time"].replace("Z", "+00:00"))
                    .timestamp() + 300]
        self.code = 200
        self.body = None
        self.headers = {}
        self.calls = []
        self.received = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def __enter__(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.calls.append({"path": self.path, "headers": dict(self.headers)})
                owner.received.set()
                owner.release.wait(15)
                self.send_response(owner.code)
                headers = {"Content-Type": "application/json", "Expires": formatdate(owner.now[0] + 600, usegmt=True),
                           "Last-Modified": formatdate(owner.now[0] - 60, usegmt=True), **owner.headers}
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                try:
                    self.wfile.write(owner.body if owner.body is not None else json.dumps(owner.document).encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/compact"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def symbols(self, symbol):
        self.document = copy.deepcopy(self.document)
        for item in self.document["properties"]["timeseries"]:
            item["data"]["next_1_hours"] = {"summary": {"symbol_code": symbol}}
