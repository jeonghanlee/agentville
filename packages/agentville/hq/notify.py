"""External notifications: HQ posts the browser notification rules' messages to an ntfy topic.

Messages carry only what browser notifications carry: colleague names, provider initials, Project and Branch
aliases. Sending runs in one background thread with a bounded queue, so a slow or failing server never delays
ingest.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import queue
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib import resources
from typing import Any

EVENTS = ("waiting", "error", "branch", "reopened")
LANGUAGES = ("en", "ko")
ALERT_STATES = ("waiting", "error")
SUBJECT_INTERVAL = timedelta(seconds=30)
SUMMARY_AFTER = 3
QUEUE_SIZE = 100
SEND_TIMEOUT = 10.0
LOG_INTERVAL = 60.0
# Dictionary keys used for notifications; the texts are those of the Web UI (web/i18n.js).
KEYS = ("notify.waiting", "notify.error", "notify.branch.unreachable", "notify.branch.unreachableBody",
        "notify.branch.reachable", "notify.branch.reachableBody", "notify.summary", "notify.summaryMixed",
        "branch.unnamed", "project.unnamed", "notify.reopened.branch", "notify.reopened.project", "notify.reopenedBody")


@dataclass(frozen=True)
class NotifyConfig:
    url: str
    token_file: str | None = None
    events: frozenset[str] = frozenset(EVENTS)
    language: str = "en"
    token: str | None = None


def is_loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def parse_config(document: Any) -> NotifyConfig:
    """Validate the notification configuration; the token file is read by the caller."""
    if not isinstance(document, dict):
        raise ValueError("must be a mapping with url, and optionally token_file, events, and language")
    unknown = sorted(str(key) for key in document if key not in ("url", "token_file", "events", "language"))
    if unknown:
        raise ValueError(f"unknown key {unknown[0]}")
    url = document.get("url")
    parts = urllib.parse.urlsplit(url) if isinstance(url, str) else None
    if parts is None or not parts.hostname or parts.scheme not in ("http", "https"):
        raise ValueError("url must be the URL of an ntfy topic, e.g. https://ntfy.example.org/<topic>")
    if parts.scheme == "http" and not is_loopback(parts.hostname):
        raise ValueError("url must use https unless its host is loopback")
    if parts.path.strip("/") == "":
        raise ValueError("url must name a topic, e.g. https://ntfy.example.org/<topic>")
    token_file = document.get("token_file")
    if token_file is not None and (not isinstance(token_file, str) or not token_file):
        raise ValueError("token_file must be a path")
    events = document.get("events", list(EVENTS))
    if not isinstance(events, list) or not events or not all(e in EVENTS for e in events):
        raise ValueError("events must be a list of " + ", ".join(EVENTS))
    language = document.get("language", "en")
    if language not in LANGUAGES:
        raise ValueError("language must be " + " or ".join(LANGUAGES))
    return NotifyConfig(url, token_file, frozenset(events), language)


_SECTION = re.compile(r"^  (\w+): \{$")
_ENTRY = re.compile(r'^\s+"([^"]+)":\s*"((?:[^"\\]|\\.)*)",?\s*$')


def load_strings(language: str) -> dict[str, str]:
    """Notification texts of one language from the Web UI dictionary, with English for missing keys."""
    text = resources.files("agentville.hq").joinpath("web/i18n.js").read_text(encoding="utf-8")
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in text.splitlines():
        section = _SECTION.match(line)
        if section:
            current = sections.setdefault(section.group(1), {})
            continue
        entry = _ENTRY.match(line)
        if entry and current is not None and entry.group(1) in KEYS:
            current[entry.group(1)] = json.loads(f'"{entry.group(2)}"')
    english = sections.get("en", {})
    missing = [key for key in KEYS if key not in english]
    if missing:
        raise ValueError(f"web/i18n.js has no {missing[0]}")
    return {**english, **sections.get(language, {})}


def _provider_name(provider: str) -> str:
    return {"claude": "Claude", "codex": "Codex"}.get(provider, str(provider))


def _initials(provider: str) -> str:
    return {"claude": "CL", "codex": "CX"}.get(provider, str(provider)[:2].upper())


@dataclass
class Subject:
    """A colleague or a Branch, with only the fields a notification shows."""

    id: str
    kind: str
    branch_id: str
    state: str = ""
    since: str = ""
    reachable: bool = False
    name: str = ""
    provider: str = ""
    project: str = ""
    branch: str = ""
    target_kind: str = ""

    @property
    def marker(self) -> str:
        if self.kind == "reopened":
            return self.state + "@" + self.since
        if self.kind == "branch":
            return "reachable" if self.reachable else "unreachable"
        return f"{self.state}@{self.since}" if self.state in ALERT_STATES else self.state


@dataclass
class Message:
    title: str
    body: str
    tags: str
    priority: str


def _header(value: str) -> str:
    """A header value without line breaks; non-ASCII text is sent as an RFC 2047 encoded word."""
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
    if value.isascii():
        return value
    return "=?UTF-8?B?" + base64.b64encode(value.encode()).decode() + "?="


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def http_post(config: NotifyConfig, timeout: float = SEND_TIMEOUT) -> Callable[[Message], None]:
    """POST a message to the ntfy topic URL; raises on any failure."""
    host = urllib.parse.urlsplit(config.url).hostname
    # A loopback server is never reached through an environment proxy, which would see the token.
    no_proxy = [urllib.request.ProxyHandler({})] if is_loopback(host) else []
    opener = urllib.request.build_opener(_NoRedirect, *no_proxy)

    def post(message: Message) -> None:
        headers = {"Title": _header(message.title), "Tags": message.tags, "Priority": message.priority,
                   "Content-Type": "text/plain; charset=utf-8"}
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        request = urllib.request.Request(config.url, data=message.body.encode(), headers=headers, method="POST")
        with opener.open(request, timeout=timeout) as response:
            response.read()

    return post


def _log(text: str) -> None:
    print(f"agentville-hq: {text}", file=sys.stderr, flush=True)


class Outbox:
    """One sending thread with a bounded queue; failures are logged at most once per ``log_interval``."""

    def __init__(self, post: Callable[[Message], None], size: int = QUEUE_SIZE, log: Callable[[str], None] = _log,
                 log_interval: float = LOG_INTERVAL, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._post = post
        self._queue: queue.Queue[Message | None] = queue.Queue(size)
        self._log = log
        self._log_interval = log_interval
        self._monotonic = monotonic
        self._logged_at: float | None = None
        self._log_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="agentville-notify", daemon=True)
        self._thread.start()

    def put(self, message: Message) -> None:
        try:
            self._queue.put_nowait(message)
        except queue.Full:
            self._failed("queue full, notification dropped")

    def close(self, timeout: float = 2.0) -> None:
        try:
            self._queue.put(None, timeout=timeout)
        except queue.Full:
            return
        self._thread.join(timeout)

    def _run(self) -> None:
        while (message := self._queue.get()) is not None:
            try:
                self._post(message)
            except Exception as exc:  # noqa: BLE001 - any failure is logged and the next message is tried
                self._failed(f"{type(exc).__name__}: {exc}")

    def _failed(self, reason: str) -> None:
        with self._log_lock:
            now = self._monotonic()
            if self._logged_at is not None and now - self._logged_at < self._log_interval:
                return
            self._logged_at = now
        self._log(f"notification failed: {reason}")


class Notifier:
    """Applies the browser notification rules (architecture Section 6.4) to HQ state and hands out the messages.

    The first evaluation after start is a baseline. A colleague or Branch seen for the first time is recorded,
    never announced, and so are colleagues of a Branch whose snapshot was just applied. A Branch counts only
    once it has been heard since HQ started.
    """

    def __init__(self, config: NotifyConfig, send: Callable[[Message], None], strings: dict[str, str] | None = None) -> None:
        self.config = config
        self.send = send
        self.strings = strings or load_strings(config.language)
        # seen: last marker per subject; sent: time and marker of the last message; pending: held by the rate limit.
        self._seen: dict[str, str] = {}
        self._sent: dict[str, tuple[datetime, str]] = {}
        self._pending: dict[str, tuple[Subject, datetime]] = {}
        self._started = False
        self._lock = threading.Lock()

    def t(self, key: str, **params: Any) -> str:
        return re.sub(r"\{(\w+)\}", lambda m: str(params.get(m.group(1), m.group(0))), self.strings[key])

    def subjects(self, state: dict[str, Any], heard: frozenset[str]) -> list[Subject]:
        branches = {b["branch_id"]: b for b in state["branches"]}
        activities = {(a["branch_id"], a["agent_id"]): a for a in state["activities"]}

        def branch_name(branch_id: str) -> str:
            return ((branches.get(branch_id) or {}).get("branch") or {}).get("alias") or self.t("branch.unnamed")

        out = []
        for agent in state["agents"]:
            activity = activities.get((agent["branch_id"], agent["agent_id"]))
            on_duty = agent.get("presence") == "on_duty"
            state_name = (activity or {}).get("state") or "unknown" if on_duty else "idle"
            out.append(Subject(
                id="colleague:" + json.dumps([agent["branch_id"], agent["agent_id"]]), kind="colleague",
                branch_id=agent["branch_id"], state=state_name, since=(activity or {}).get("state_since") or "",
                name=agent.get("alias") or f"{_provider_name(agent.get('provider'))} {agent.get('seat')}",
                provider=_initials(agent.get("provider")), project=agent.get("project_alias") or self.t("project.unnamed"),
                branch=branch_name(agent["branch_id"])))
        for branch_id, branch in branches.items():
            if branch_id in heard:
                out.append(Subject(id="branch:" + branch_id, kind="branch", branch_id=branch_id,
                                   reachable=bool(branch.get("reachable")), branch=branch_name(branch_id)))
        for value in state.get("lifecycles", []):
            out.append(Subject(id="lifecycle:" + value["kind"] + ":" + value["id"], kind="reopened",
                               branch_id=value["branch_id"], since=str(value["reopen_count"]), name=value["alias"],
                               target_kind=value["kind"], state="closed" if value["closed"] else "open"))
        return out

    def wanted(self, subject: Subject) -> bool:
        if subject.kind == "reopened":
            return "reopened" in self.config.events and subject.since != "0" and subject.state == "open"
        if subject.kind == "branch":
            return "branch" in self.config.events
        return subject.state in ALERT_STATES and subject.state in self.config.events

    def observe(self, state: dict[str, Any], heard: frozenset[str], now: datetime,
                resynced: frozenset[str] = frozenset()) -> None:
        """Evaluate one state: record markers, send held messages that are due, and announce transitions."""
        with self._lock:
            baseline, self._started = not self._started, True
            changes, present = [], set()
            for subject in self.subjects(state, heard):
                present.add(subject.id)
                previous = self._seen.get(subject.id)
                self._seen[subject.id] = subject.marker
                if baseline or previous is None or previous == subject.marker:
                    continue
                if subject.kind == "colleague" and subject.branch_id in resynced:
                    continue
                if self.wanted(subject):
                    changes.append(subject)
            for gone in set(self._seen) - present:
                del self._seen[gone]
                self._pending.pop(gone, None)
            for subject_id, (subject, due) in list(self._pending.items()):
                if now >= due:
                    del self._pending[subject_id]
                    # A held change is sent only if it still holds and differs from what was last sent.
                    if self._seen.get(subject_id) == subject.marker and self._sent.get(subject_id, (now, ""))[1] != subject.marker:
                        self._deliver([subject], now)
            if changes:
                self._deliver(changes, now)

    def _deliver(self, changes: list[Subject], now: datetime) -> None:
        due = []
        for subject in changes:
            last = self._sent.get(subject.id)
            if last is not None and now < last[0] + SUBJECT_INTERVAL:
                self._pending[subject.id] = (subject, last[0] + SUBJECT_INTERVAL)
            else:
                due.append(subject)
        for subject in due:
            self._pending.pop(subject.id, None)
            self._sent[subject.id] = (now, subject.marker)
        if len(due) > SUMMARY_AFTER:
            colleagues = [s for s in due if s.kind == "colleague"]
            names = [s.branch if s.kind == "branch" else s.name for s in due[:SUMMARY_AFTER]]
            more = f" +{len(due) - len(names)}" if len(due) > len(names) else ""
            high = any(self._priority(s) == "high" for s in due)
            self.send(Message(self.t("notify.summary" if len(colleagues) == len(due) else "notify.summaryMixed", n=len(due)),
                              ", ".join(names) + more, "agentville,summary", "high" if high else "default"))
            return
        for subject in due:
            self.send(self.message(subject))

    @staticmethod
    def _priority(subject: Subject) -> str:
        if subject.kind == "branch":
            return "default" if subject.reachable else "high"
        return "high" if subject.state == "error" else "default"

    def message(self, subject: Subject) -> Message:
        if subject.kind == "reopened":
            return Message(self.t("notify.reopened." + subject.target_kind, name=subject.name),
                           self.t("notify.reopenedBody"), "agentville,reopened", "default")
        if subject.kind == "branch":
            key = "reachable" if subject.reachable else "unreachable"
            return Message(self.t("notify.branch." + key, branch=subject.branch), self.t(f"notify.branch.{key}Body"),
                           "agentville," + key, self._priority(subject))
        return Message(self.t("notify." + subject.state, name=subject.name),
                       " \u00b7 ".join([subject.provider, subject.project, subject.branch]),
                       "agentville," + subject.state, self._priority(subject))
