"""Delivers message batches to HQ over HTTP(S)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class Delivery:
    ok: bool
    need_snapshot: bool = False
    error: str | None = None


class HttpSender:
    def __init__(self, url: str, token: str | None = None, timeout: float = 5.0) -> None:
        self.endpoint = url.rstrip("/") + "/api/v1/ingest/messages"
        self.token = token
        self.timeout = timeout

    def __call__(self, messages: list[dict[str, Any]]) -> Delivery:
        body = json.dumps({"messages": messages}, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return Delivery(False, error=f"HTTP {exc.code}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return Delivery(False, error=str(exc))
        return Delivery(True, need_snapshot=bool(isinstance(result, dict) and result.get("need_snapshot")))
