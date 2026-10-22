"""Delivers message batches to HQ over HTTP(S)."""

from __future__ import annotations

import http.client
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class Delivery:
    ok: bool
    need_snapshot: bool = False
    error: str | None = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class HttpSender:
    def __init__(self, url: str, token: str | None = None, timeout: float = 5.0) -> None:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"unsupported HQ URL scheme: {parsed.scheme!r}")
        if token and parsed.scheme == "http" and not _is_loopback_host(parsed.hostname):
            raise ValueError("refusing to send a token over plain HTTP to a non-loopback HQ; use https")
        self.endpoint = url.rstrip("/") + "/api/v1/ingest/messages"
        self.token = token
        self.timeout = timeout
        # A loopback HQ is never reached through an environment proxy, which would see the token.
        no_proxy = [urllib.request.ProxyHandler({})] if _is_loopback_host(parsed.hostname) else []
        self._opener = urllib.request.build_opener(_NoRedirect, *no_proxy)

    def __call__(self, messages: list[dict[str, Any]]) -> Delivery:
        body = json.dumps({"messages": messages}, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                result = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read() or b"{}").get("detail", "")
            except (ValueError, AttributeError, OSError):
                pass
            return Delivery(False, error=f"HTTP {exc.code} {detail}".strip())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # OSError covers ssl.SSLError and connection resets.
            return Delivery(False, error=str(exc))
        except http.client.HTTPException as exc:
            # A response cut short or malformed, e.g. IncompleteRead or BadStatusLine.
            return Delivery(False, error=f"{type(exc).__name__}: {exc}")
        return Delivery(True, need_snapshot=bool(isinstance(result, dict) and result.get("need_snapshot")))
