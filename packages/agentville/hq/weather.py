"""Opt-in regional forecasts, shared expiry-aware cache, and display-only results."""

from __future__ import annotations

import asyncio
import json
import math
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from agentville import version

PROVIDER_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
SOURCE_URL = "https://www.met.no/en"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
USER_AGENT = f"AgentVille/{version()} https://github.com/jeonghanlee/agentville"
TIMEOUT = 5
MAX_BODY = 1024 * 1024
MAX_BRANCHES = 128
MIN_REFRESH = 60
MAX_BACKOFF = 3600
POLL_SECONDS = 5
HOUR = 3600


@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float

    @property
    def key(self) -> str:
        return f"{self.latitude:.4f},{self.longitude:.4f}"

    @property
    def hemisphere(self) -> str:
        return "north" if self.latitude > 0 else "south" if self.latitude < 0 else ""


def parse_config(document: Any) -> dict[str, Location]:
    """Require explicit coordinates indexed by stable Branch identity."""
    if not isinstance(document, dict) or set(document) != {"branches"}:
        raise ValueError("weather configuration must contain only a branches mapping")
    branches = document["branches"]
    if not isinstance(branches, dict) or len(branches) > MAX_BRANCHES:
        raise ValueError(f"weather branches must be a mapping with at most {MAX_BRANCHES} entries")
    result = {}
    for identity, item in branches.items():
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 256:
            raise ValueError("weather Branch IDs must be nonempty strings of at most 256 characters")
        if not isinstance(item, dict) or set(item) != {"latitude", "longitude"}:
            raise ValueError("each weather Branch requires only latitude and longitude")
        values = []
        for name, bound in (("latitude", 90), ("longitude", 180)):
            value = item[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or abs(value) > bound or not math.isfinite(value):
                raise ValueError(f"weather {name} must be a finite number between {-bound} and {bound}")
            values.append(round(float(value), 4))
        result[identity] = Location(*values)
    return result


def _stamp(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("forecast timestamps require a time zone")
    return parsed.timestamp()


def _iso(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat().replace("+00:00", "Z")


def _header_time(value: str | None, fallback: float) -> float:
    try:
        stamp = parsedate_to_datetime(value).timestamp() if value else fallback
        return stamp if math.isfinite(stamp) else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback


def condition(symbol: Any) -> str:
    if not isinstance(symbol, str):
        return "unknown"
    name = symbol.split("_")[0]
    if "thunder" in name:
        return "thunder"
    for part in ("sleet", "snow", "rain", "fog"):
        if part in name:
            return part
    if name in {"clearsky", "fair"}:
        return "clear"
    if name in {"partlycloudy", "cloudy"}:
        return "cloud"
    return "unknown"


def forecasts(document: Any) -> tuple[str, list[dict[str, Any]]]:
    """Normalize real provider intervals without turning future samples into observations."""
    try:
        properties = document["properties"]
        if properties["meta"]["units"]["air_temperature"] != "celsius":
            raise ValueError("forecast temperature must use Celsius")
        updated = properties["meta"]["updated_at"]
        _stamp(updated)
        series = properties["timeseries"]
        if not isinstance(series, list) or not 1 <= len(series) <= 512:
            raise ValueError("invalid forecast series")
        result = []
        for item in series:
            start = _stamp(item["time"])
            data = item["data"]
            temperature = data["instant"]["details"].get("air_temperature")
            if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not math.isfinite(temperature):
                raise ValueError("invalid forecast temperature")
            summary = data.get("next_1_hours", {}).get("summary", {})
            result.append({"start": start, "end": start + HOUR, "temperature": temperature,
                           "condition": condition(summary.get("symbol_code"))})
        if any(a["start"] >= b["start"] for a, b in zip(result, result[1:])):
            raise ValueError("forecast times must increase")
        return updated, result
    except (KeyError, TypeError, AttributeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid MET Norway forecast") from exc


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Weather:
    """One persistent cache per HQ; a dedicated worker owns network refreshes."""

    def __init__(self, locations: dict[str, Location], path: str, clock: Callable[[], float] = time.time):
        self.locations, self.clock = locations, clock
        self.lock = threading.RLock()
        self.refresh_lock = threading.Lock()
        self.stopping = threading.Event()
        self.cells = {location.key: location for location in locations.values()}
        self.entries: dict[str, dict[str, Any]] = {}
        self.opener = urllib.request.build_opener(_NoRedirect)
        self.db = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        self.db.execute("CREATE TABLE IF NOT EXISTS weather_cache (cell TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.commit()
        for cell, payload in self.db.execute("SELECT cell, payload FROM weather_cache"):
            if cell not in self.cells:
                continue
            try:
                entry = json.loads(payload)
                if not isinstance(entry, dict):
                    continue
                for name in ("expires", "retry", "failures", "fetched"):
                    if not isinstance(entry[name], (int, float)) or not math.isfinite(entry[name]):
                        raise ValueError("invalid cached timestamp")
                if entry["data"] is not None:
                    forecasts(entry["data"])
                self.entries[cell] = entry
            except (KeyError, TypeError, ValueError):
                continue

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def _request(self, location: Location, modified: str) -> tuple[int, Any, bytes]:
        query = urllib.parse.urlencode({"lat": f"{location.latitude:.4f}", "lon": f"{location.longitude:.4f}"})
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if modified:
            headers["If-Modified-Since"] = modified
        request = urllib.request.Request(PROVIDER_URL + "?" + query, headers=headers)
        try:
            response = self.opener.open(request, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            body = response.read(MAX_BODY + 1)
            return response.code, response.headers, body

    def refresh(self) -> None:
        """At most one refresh runs, independently of cache readers."""
        if not self.refresh_lock.acquire(blocking=False):
            return
        try:
            self._refresh()
        finally:
            self.refresh_lock.release()

    def _refresh(self) -> None:
        for cell, location in self.cells.items():
            if self.stopping.is_set():
                break
            now = self.clock()
            with self.lock:
                old = self.entries.get(cell, {"data": None, "expires": 0, "retry": 0,
                                              "failures": 0, "fetched": 0, "modified": ""})
                if now < max(old["expires"], old["retry"]):
                    continue
            entry = dict(old)
            retry_after = now + MIN_REFRESH
            try:
                code, headers, body = self._request(location, old.get("modified", ""))
                hint = headers.get("Retry-After")
                retry_after = max(retry_after, now + int(hint) if hint and hint.isdigit()
                                  else _header_time(hint, retry_after))
                if len(body) > MAX_BODY:
                    raise ValueError("weather response exceeds the size limit")
                if code == 304 and old["data"] is not None:
                    data = old["data"]
                elif code in {200, 203}:
                    data = json.loads(body)
                    forecasts(data)
                else:
                    raise ValueError("weather provider returned an unsuccessful status")
                entry.update(data=data, fetched=now, expires=max(now, _header_time(headers.get("Expires"), now)),
                             retry=now + MIN_REFRESH, failures=0,
                             modified=headers.get("Last-Modified", old.get("modified", "")), deprecated=code == 203)
            except (OSError, ValueError, TypeError, urllib.error.URLError):
                failures = min(old["failures"] + 1, 10)
                entry.update(failures=failures, retry=max(retry_after, now + min(MAX_BACKOFF, MIN_REFRESH * 2 ** (failures - 1))))
            with self.lock:
                self.entries[cell] = entry
                self.db.execute("INSERT OR REPLACE INTO weather_cache VALUES (?, ?)", (cell, json.dumps(entry)))
                self.db.commit()

    async def run(self) -> None:
        while True:
            task = asyncio.create_task(asyncio.to_thread(self.refresh))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                self.stopping.set()
                await task
                raise
            await asyncio.sleep(POLL_SECONDS)

    def display(self, identity: str) -> dict[str, Any]:
        location = self.locations.get(identity)
        result: dict[str, Any] = {"status": "unconfigured", "hemisphere": location.hemisphere if location else "",
                                  "source": "MET Norway", "source_url": SOURCE_URL, "license_url": LICENSE_URL,
                                  "temperature": None, "condition": "unknown", "valid_from": None,
                                  "valid_to": None, "updated_at": None, "fetched_at": None, "expires_at": None,
                                  "deprecated": False}
        if location is None:
            return result
        with self.lock:
            entry = dict(self.entries.get(location.key, {}))
        if not entry:
            return {**result, "status": "loading"}
        if entry["data"] is None:
            return {**result, "status": "unavailable"}
        updated, rows = forecasts(entry["data"])
        now = self.clock()
        row = next((row for row in rows if row["start"] <= now < row["end"]), None)
        result.update(updated_at=updated, fetched_at=_iso(entry["fetched"]), expires_at=_iso(entry["expires"]),
                      deprecated=entry.get("deprecated", False))
        if row is None:
            return {**result, "status": "unavailable"}
        result.update(temperature=row["temperature"], condition=row["condition"],
                      valid_from=_iso(row["start"]), valid_to=_iso(row["end"]))
        result["status"] = "stale" if now >= entry["expires"] or entry["failures"] else "available"
        return result
