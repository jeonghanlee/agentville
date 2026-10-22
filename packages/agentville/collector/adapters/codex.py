"""Codex adapter.

Live state comes from the app-server daemon of one Codex home (one shift per
loaded thread); turn and tool detail come from the thread's rollout file.
Loaded subagent threads are Contractors of the shift of their parent thread.
A recently written rollout of a thread the daemon does not know (e.g. ``codex
exec``) is a rollout-only shift, observed from that file alone.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from agentville import version
from agentville.collector.appserver import AppServerClient, AppServerError, RpcConnection, RpcError
from agentville.collector.jsonl import JsonlTail
from agentville.common.observations import Kind, Observation, RawLocation, SessionStatus, ShiftKey, Source

PROVIDER = "codex"

_TOOL_CALLS = {"function_call", "custom_tool_call", "local_shell_call"}
_TOOL_OUTPUTS = {"function_call_output", "custom_tool_call_output", "local_shell_call_output"}
# task_complete.error kinds after which the turn just ends.
_TRANSIENT_ERRORS = {"server_overloaded"}
# A rollout-only shift lasts while its rollout was written within this window.
ROLLOUT_WINDOW = timedelta(minutes=30)
_ROLLOUT_NAME = re.compile(r"rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-(.+)\.jsonl")
# session_meta is the first record; a rollout without it in this many lines has none.
_META_LINES = 5


def socket_path(home: str) -> str:
    return os.path.join(home, "app-server-control", "app-server-control.sock")


def is_subagent_thread(thread: dict[str, Any]) -> bool:
    source = thread.get("source")
    return bool(thread.get("parentThreadId")) or (isinstance(source, dict) and "subAgent" in source)


def is_employee_thread(thread: dict[str, Any]) -> bool:
    """Subagent threads (Contractors) and internal system threads are not Employees."""
    return not is_subagent_thread(thread) and thread.get("threadSource") != "system"


def is_employee_rollout(meta: dict[str, Any]) -> bool:
    """The rollout ``session_meta`` counterpart of ``is_employee_thread``."""
    source = meta.get("source")
    subagent = isinstance(source, dict) and any(str(k).lower() == "subagent" for k in source)
    return not subagent and not meta.get("parent_thread_id") and meta.get("thread_source") != "system"


def read_session_meta(path: str) -> dict[str, Any] | None:
    """The rollout's ``session_meta`` payload; ``{}`` when it has none, None while its first lines are incomplete."""
    with open(path, "rb") as fh:
        for _ in range(_META_LINES):
            line = fh.readline()
            if not line.endswith(b"\n"):
                return None
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("type") == "session_meta":
                payload = record.get("payload")
                return payload if isinstance(payload, dict) else {}
    return {}


def _mtime(path: str) -> float | None:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def contractor_status(status: dict[str, Any]) -> str | None:
    """Contractor status for a thread status; None when the thread is not loaded."""
    kind = status.get("type")
    if kind == "notLoaded":
        return None
    if kind == "active":
        return "waiting" if status.get("activeFlags") else "active"
    return {"idle": "idle", "systemError": "error"}.get(kind, "unknown")


def _from_iso(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@dataclass
class _Shift:
    key: ShiftKey
    thread_id: str
    tail: JsonlTail | None
    status: tuple[str, tuple[str, ...]] | None = None
    model: tuple[str | None, str | None] = (None, None)
    open_tools: dict[str, str] = field(default_factory=dict)
    limited: bool = False
    limit_reset: datetime | None = None
    # Reset of the most used window in the latest token_count, for a limit reported only as an error.
    last_reset: datetime | None = None
    source: Source = Source.APP_SERVER


@dataclass
class _Contractor:
    thread_id: str
    parent: _Shift
    tail: JsonlTail | None
    status: str
    tool: str | None = None
    open_tools: dict[str, str] = field(default_factory=dict)
    reported: tuple[str, str | None] | None = None


class CodexAdapter:
    def __init__(
        self,
        home: str,
        connect: Callable[[], RpcConnection] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        account_alias: str | None = None,
    ) -> None:
        self.home = home
        self.account_alias = account_alias
        self._connect = connect or self._default_connect
        self._clock = clock
        self._conn: RpcConnection | None = None
        self._shifts: dict[str, _Shift] = {}
        self._contractors: dict[str, _Contractor] = {}
        self._ignored: set[str] = set()
        self._attached_at: datetime | None = None
        self._followed: set[str] = set()
        # Rollout-only shifts by thread id, and the tails they followed, by path.
        self._rollouts: dict[str, _Shift] = {}
        self._rollout_tails: dict[str, JsonlTail] = {}
        self._scanned_at: datetime | None = None
        self._not_employees: set[str] = set()
        # Rollout mtime when a daemon shift ended; a later write is a run outside the daemon.
        self._daemon_ended: dict[str, float] = {}

    def _default_connect(self) -> RpcConnection:
        client = AppServerClient(socket_path(self.home), client_version=version())
        client.connect()
        return client

    def poll(self) -> list[Observation]:
        now = self._clock()
        out: list[Observation] = []
        try:
            if self._conn is None:
                self._conn = self._connect()
                self._seed(now, out)
            messages = self._conn.drain()
            # Rollout first, so a turn's completion precedes the status that ends it.
            self._read_rollouts(now, out)
            for message in messages:
                if isinstance(message, dict):
                    self._notification(message, now, out)
        except AppServerError:
            self._disconnect(now, out)
        self._scan_rollouts(now, out)
        self._read_rollouts(now, out)
        self._expire_rollouts(now, out)
        return out

    def _read_rollouts(self, now: datetime, out: list[Observation]) -> None:
        for shift in [*self._shifts.values(), *self._rollouts.values()]:
            self._read_rollout(shift, now, out)
        for contractor in list(self._contractors.values()):
            self._read_contractor_rollout(contractor, now, out)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _disconnect(self, now: datetime, out: list[Observation]) -> None:
        if self._conn is not None:
            self._conn.close()
        self._conn = None
        for shift in self._shifts.values():
            if shift.status != ("unknown", ()):
                shift.status = ("unknown", ())
                out.append(self._obs(Kind.SESSION_STATUS, shift, now, now, {"status": SessionStatus.UNKNOWN.value, "native": None}))
        for contractor in self._contractors.values():
            contractor.status = "unknown"
            self._report(contractor, now, now, out)

    def _loaded(self) -> list[str]:
        assert self._conn is not None
        loaded: list[str] = []
        cursor = None
        while True:
            result = self._conn.request("thread/loaded/list", {"cursor": cursor} if cursor else {})
            if not isinstance(result, dict):
                raise AppServerError("invalid thread/loaded/list result")
            loaded.extend(i for i in result.get("data") or [] if isinstance(i, str))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return loaded

    def _seed(self, now: datetime, out: list[Observation]) -> None:
        loaded = self._loaded()
        self._ignored &= set(loaded)
        for thread_id in list(self._contractors):
            if thread_id not in loaded:
                self._end_contractor(self._contractors[thread_id], now, out)
        for thread_id in list(self._shifts):
            if thread_id not in loaded:
                self._end(self._shifts[thread_id], now, out)
        threads = [t for t in (self._read_thread(i) for i in loaded if i not in self._ignored) if t is not None]
        parents = {t.get("id"): t.get("parentThreadId") for t in threads}

        def depth(thread: dict[str, Any]) -> int:
            n, parent, seen = int(is_subagent_thread(thread)), thread.get("parentThreadId"), set()
            while parent in parents and parent not in seen:
                seen.add(parent)
                n, parent = n + 1, parents[parent]
            return n

        # Parents first, nested subagents after their own parents, so each finds its parent shift.
        for thread in sorted(threads, key=depth):
            self._observe_thread(thread, now, out)
        if self._attached_at is None:
            self._attached_at = now

    def _read_thread(self, thread_id: str) -> dict[str, Any] | None:
        assert self._conn is not None
        try:
            result = self._conn.request("thread/read", {"threadId": thread_id, "includeTurns": False})
        except RpcError:
            # Skip this thread for now; its shift keeps its previous state.
            return None
        thread = result.get("thread") if isinstance(result, dict) else None
        return thread if isinstance(thread, dict) else None

    def _observe_thread(self, thread: dict[str, Any], now: datetime, out: list[Observation]) -> None:
        thread_id = thread.get("id")
        if not isinstance(thread_id, str):
            return
        if is_subagent_thread(thread):
            self._observe_contractor(thread, now, out)
            return
        if not is_employee_thread(thread):
            self._ignored.add(thread_id)
            return
        status = thread.get("status") or {}
        if status.get("type") == "notLoaded":
            return
        shift = self._shifts.get(thread_id)
        if shift is None:
            shift = self._start(thread, now, out)
        self._status(shift, status, now, out)

    def _observe_contractor(self, thread: dict[str, Any], now: datetime, out: list[Observation]) -> None:
        thread_id = thread["id"]
        status = contractor_status(thread.get("status") or {})
        contractor = self._contractors.get(thread_id)
        if contractor is not None:
            self._contractor_status(contractor, status, now, out)
            return
        parent = self._parent_shift(thread.get("parentThreadId"))
        if status is None or parent is None:
            return
        contractor = _Contractor(thread_id, parent, self._tail(thread), status)
        self._contractors[thread_id] = contractor
        contractor.reported = (status, None)
        out.append(
            self._obs(Kind.SUBAGENT_STARTED, parent, now, now, {"subagent_id": thread_id, "provider": PROVIDER, "status": status, "tool": None})
        )

    def _parent_shift(self, parent_id: Any) -> _Shift | None:
        if parent_id in self._shifts:
            return self._shifts[parent_id]
        # A nested subagent works for the Employee of its root thread.
        contractor = self._contractors.get(parent_id)
        return contractor.parent if contractor is not None else None

    def _contractor_status(self, contractor: _Contractor, status: str | None, now: datetime, out: list[Observation]) -> None:
        if status is None:
            self._end_contractor(contractor, now, out)
            return
        contractor.status = status
        self._report(contractor, now, now, out)

    def _report(self, contractor: _Contractor, at: datetime, now: datetime, out: list[Observation]) -> None:
        tool = contractor.tool if contractor.status == "active" else None
        if (contractor.status, tool) == contractor.reported:
            return
        contractor.reported = (contractor.status, tool)
        data = {"subagent_id": contractor.thread_id, "status": contractor.status, "tool": tool}
        out.append(self._obs(Kind.SUBAGENT_STATUS, contractor.parent, at, now, data))

    def _end_contractor(self, contractor: _Contractor, now: datetime, out: list[Observation]) -> None:
        self._contractors.pop(contractor.thread_id, None)
        self._ended_by_daemon(contractor.thread_id, contractor.tail)
        if contractor.parent.thread_id in self._shifts:
            out.append(self._obs(Kind.SUBAGENT_ENDED, contractor.parent, now, now, {"subagent_id": contractor.thread_id}))

    def _tail(self, thread: dict[str, Any]) -> JsonlTail | None:
        path = self._rollout_path(thread)
        if not path:
            return None
        tail = JsonlTail(path)
        created = thread.get("createdAt")
        resumed = path in self._followed
        self._followed.add(path)
        if self._attached_at is None or resumed or not isinstance(created, (int, float)) or (
            datetime.fromtimestamp(created, tz=UTC) < self._attached_at
        ):
            # History written before attach, or of a thread resumed before or during this
            # run, is not replayed; live state comes from the app-server.
            tail.seek_end()
        return tail

    def _start(self, thread: dict[str, Any], now: datetime, out: list[Observation]) -> _Shift:
        thread_id = thread["id"]
        rollout = self._rollouts.get(thread_id)
        if rollout is not None:
            # The daemon takes over; its shift continues the rollout from where the rollout-only shift stopped.
            self._end(rollout, now, out)
        shift = _Shift(ShiftKey(PROVIDER, thread_id), thread_id, rollout.tail if rollout else self._tail(thread))
        self._shifts[thread_id] = shift
        out.append(
            self._obs(
                Kind.PROCESS_STARTED,
                shift,
                now,
                now,
                {
                    "cwd": thread.get("cwd", ""),
                    "session_id": thread_id,
                    "runtime": {"type": "app_server"},
                    "account_alias": self.account_alias,
                },
            )
        )
        out.append(self._obs(Kind.SESSION_STARTED, shift, now, now, {"session_id": thread_id}))
        model = (thread.get("model"), thread.get("reasoningEffort"))
        if any(model):
            shift.model = model
            out.append(self._obs(Kind.MODEL_CHANGED, shift, now, now, self._model_data(model)))
        return shift

    def _scan_rollouts(self, now: datetime, out: list[Observation]) -> None:
        """Start a rollout-only shift for each recent rollout of a thread the daemon does not know."""
        known = self._shifts.keys() | self._contractors.keys() | self._ignored | self._rollouts.keys() | self._not_employees
        pattern = os.path.join(glob.escape(self.home), "sessions", "*", "*", "*", "rollout-*.jsonl")
        for path in glob.glob(pattern):
            match = _ROLLOUT_NAME.fullmatch(os.path.basename(path))
            if match is None or match.group(1) in known:
                continue
            thread_id = match.group(1)
            mtime = _mtime(path)
            if mtime is None or now.timestamp() - mtime > ROLLOUT_WINDOW.total_seconds():
                continue
            if thread_id in self._daemon_ended and mtime <= self._daemon_ended[thread_id]:
                continue
            try:
                meta = read_session_meta(path)
            except OSError:
                continue
            if meta and is_employee_rollout(meta):
                self._start_rollout(thread_id, path, meta, now, out)
            elif meta is not None:
                self._not_employees.add(thread_id)
        if self._scanned_at is None:
            self._scanned_at = now

    def _start_rollout(self, thread_id: str, path: str, meta: dict[str, Any], now: datetime, out: list[Observation]) -> None:
        tail = self._rollout_tails.get(path)
        if tail is None:
            tail = self._rollout_tails[path] = JsonlTail(path)
            created = _from_iso(meta.get("timestamp"))
            # The same rules as for daemon threads: history before attach, or of a resumed rollout, is not replayed.
            if self._scanned_at is None or path in self._followed or created is None or created < self._scanned_at:
                tail.seek_end()
            self._followed.add(path)
        shift = _Shift(ShiftKey(PROVIDER, f"rollout:{thread_id}"), thread_id, tail, source=Source.SESSION_LOG)
        self._rollouts[thread_id] = shift
        data = {"cwd": str(meta.get("cwd") or ""), "session_id": thread_id, "runtime": {"type": "rollout"},
                "account_alias": self.account_alias, "max_confidence": "low"}
        out.append(self._obs(Kind.PROCESS_STARTED, shift, now, now, data))
        out.append(self._obs(Kind.SESSION_STARTED, shift, now, now, {"session_id": thread_id}))

    def _expire_rollouts(self, now: datetime, out: list[Observation]) -> None:
        for shift in list(self._rollouts.values()):
            mtime = _mtime(shift.tail.path) if shift.tail else None
            if mtime is None or now.timestamp() - mtime > ROLLOUT_WINDOW.total_seconds():
                self._end(shift, now, out)

    def _rollout_path(self, thread: dict[str, Any]) -> str | None:
        path = thread.get("path")
        if isinstance(path, str) and path:
            return path
        return self._find_rollout(thread["id"])

    def _find_rollout(self, thread_id: str) -> str | None:
        name = f"rollout-*-{glob.escape(thread_id)}.jsonl"
        matches = glob.glob(os.path.join(glob.escape(self.home), "sessions", "*", "*", "*", name))
        return matches[0] if matches else None

    def _status(self, shift: _Shift, status: dict[str, Any], now: datetime, out: list[Observation]) -> None:
        kind = status.get("type")
        flags = tuple(sorted(status.get("activeFlags") or ()))
        current = (kind, flags)
        if current == shift.status:
            return
        previous = shift.status
        shift.status = current
        if kind == "systemError":
            out.append(self._obs(Kind.AGENT_ERROR, shift, now, now, {"status": kind}))
            return
        waiting = kind == "active" and bool(flags)
        if kind == "active" and not waiting:
            shift.limited = False
        was_waiting = previous is not None and previous[0] == "active" and bool(previous[1])
        if waiting and not was_waiting:
            out.append(self._obs(Kind.INPUT_REQUESTED, shift, now, now, {"reason": flags[0]}))
        elif was_waiting and not waiting:
            out.append(self._obs(Kind.INPUT_RESOLVED, shift, now, now, {}))
        normalized = (
            SessionStatus.WAITING
            if waiting
            else SessionStatus.ACTIVE
            if kind == "active"
            else SessionStatus.IDLE
            if kind == "idle"
            else SessionStatus.UNKNOWN
        )
        out.append(self._obs(Kind.SESSION_STATUS, shift, now, now, {"status": normalized.value, "native": kind}))

    def _notification(self, message: dict[str, Any], now: datetime, out: list[Observation]) -> None:
        method = message.get("method")
        params = message.get("params")
        if not isinstance(params, dict):
            return
        thread_id = params.get("threadId")
        if method == "thread/started" and isinstance(params.get("thread"), dict):
            self._observe_thread(params["thread"], now, out)
        elif method == "thread/closed" and thread_id in self._contractors:
            self._end_contractor(self._contractors[thread_id], now, out)
        elif method == "thread/closed" and thread_id in self._shifts:
            self._end(self._shifts[thread_id], now, out)
        elif method == "thread/status/changed" and isinstance(thread_id, str):
            status = params.get("status")
            if not isinstance(status, dict) or thread_id in self._ignored:
                return
            if thread_id in self._contractors:
                self._contractor_status(self._contractors[thread_id], contractor_status(status), now, out)
                return
            shift = self._shifts.get(thread_id)
            if status.get("type") == "notLoaded":
                if shift is not None:
                    self._end(shift, now, out)
            elif shift is not None:
                self._status(shift, status, now, out)
            elif thread_id in self._loaded():
                thread = self._read_thread(thread_id)
                if thread is not None:
                    self._observe_thread(thread, now, out)

    def _read_rollout(self, shift: _Shift, now: datetime, out: list[Observation]) -> None:
        if shift.tail is None:
            return
        try:
            for offset, record in shift.tail.read():
                at = _from_iso(record.get("timestamp")) or now
                raw = RawLocation(shift.tail.path, offset)
                for kind, data in self._interpret(shift, record):
                    out.append(Observation(kind, shift.key, at, now, Source.SESSION_LOG, data, raw))
        except OSError as exc:
            # One unreadable rollout must not discard observations of the other shifts.
            print(f"agentville-collector: {shift.tail.path}: {exc}", file=sys.stderr, flush=True)

    def _read_contractor_rollout(self, contractor: _Contractor, now: datetime, out: list[Observation]) -> None:
        if contractor.tail is None:
            return
        try:
            for _, record in contractor.tail.read():
                payload = record.get("payload")
                if record.get("type") != "response_item" or not isinstance(payload, dict):
                    continue
                call_id = payload.get("call_id")
                if payload.get("type") in _TOOL_CALLS:
                    contractor.open_tools[call_id] = contractor.tool = payload.get("name") or payload["type"]
                elif payload.get("type") in _TOOL_OUTPUTS:
                    contractor.open_tools.pop(call_id, None)
                    contractor.tool = next(reversed(contractor.open_tools.values()), None)
                else:
                    continue
                self._report(contractor, _from_iso(record.get("timestamp")) or now, now, out)
        except OSError as exc:
            print(f"agentville-collector: {contractor.tail.path}: {exc}", file=sys.stderr, flush=True)

    def _interpret(self, shift: _Shift, record: dict[str, Any]) -> list[tuple[Kind, dict[str, Any]]]:
        rtype = record.get("type")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return []
        ptype = payload.get("type")
        if rtype == "event_msg":
            if ptype == "task_started":
                shift.limited = False
                return [(Kind.TURN_STARTED, {})]
            if ptype == "token_count":
                return self._limit(shift, payload.get("rate_limits"))
            if ptype == "task_complete":
                return self._task_error(shift, payload.get("error")) + [
                    (Kind.TURN_COMPLETED, {"duration_ms": payload.get("duration_ms")})
                ]
            if ptype == "turn_aborted":
                return [(Kind.TURN_COMPLETED, {"aborted": payload.get("reason")})]
            if ptype == "thread_settings_applied":
                settings = payload.get("thread_settings") if isinstance(payload.get("thread_settings"), dict) else payload
                return self._model(shift, settings.get("model"), settings.get("reasoning_effort"))
            return []
        if rtype == "turn_context":
            return self._model(shift, payload.get("model"), payload.get("effort"))
        if rtype == "response_item":
            call_id = payload.get("call_id")
            if ptype in _TOOL_CALLS:
                name = payload.get("name") or ptype
                shift.open_tools[call_id] = name
                shift.limited = False
                return [(Kind.TOOL_STARTED, {"tool_id": call_id, "tool": name})]
            if ptype in _TOOL_OUTPUTS:
                return [(Kind.TOOL_FINISHED, {"tool_id": call_id, "tool": shift.open_tools.pop(call_id, None), "success": None})]
        return []

    @staticmethod
    def _task_error(shift: _Shift, error: Any) -> list[tuple[Kind, dict[str, Any]]]:
        kind = error.get("codex_error_info") if isinstance(error, dict) else None
        if not error or kind in _TRANSIENT_ERRORS:
            return []
        if kind == "usage_limit_exceeded":
            if shift.limited:
                return []
            shift.limited, shift.limit_reset = True, shift.last_reset
            return [(Kind.LIMIT_REACHED, {"reset_at": shift.last_reset})]
        return [(Kind.AGENT_ERROR, {"status": "task_error"})]

    @staticmethod
    def _limit(shift: _Shift, rate_limits: Any) -> list[tuple[Kind, dict[str, Any]]]:
        if not isinstance(rate_limits, dict):
            return []
        windows = [w for w in (rate_limits.get("primary"), rate_limits.get("secondary")) if isinstance(w, dict)]
        known = [w for w in windows if isinstance(w.get("used_percent"), (int, float)) and isinstance(w.get("resets_at"), (int, float))]
        if known:
            busiest = max(known, key=lambda w: (w["used_percent"], w["resets_at"]))
            shift.last_reset = datetime.fromtimestamp(busiest["resets_at"], tz=UTC)
        full = [w for w in windows if isinstance(w.get("used_percent"), (int, float)) and w["used_percent"] >= 100]
        if full:
            resets = [w["resets_at"] for w in full if isinstance(w.get("resets_at"), (int, float))]
            reset = datetime.fromtimestamp(max(resets), tz=UTC) if resets else None
            if shift.limited and shift.limit_reset == reset:
                return []
            shift.limited, shift.limit_reset = True, reset
            return [(Kind.LIMIT_REACHED, {"reset_at": reset})]
        if shift.limited and windows:
            shift.limited, shift.limit_reset = False, None
            return [(Kind.LIMIT_CLEARED, {})]
        return []

    def _model(self, shift: _Shift, model: Any, effort: Any) -> list[tuple[Kind, dict[str, Any]]]:
        current = (model if isinstance(model, str) else None, effort if isinstance(effort, str) else None)
        if not any(current) or current == shift.model:
            return []
        shift.model = current
        return [(Kind.MODEL_CHANGED, self._model_data(current))]

    @staticmethod
    def _model_data(model: tuple[str | None, str | None]) -> dict[str, Any]:
        return {"model": model[0], "settings": {"effort": model[1]} if model[1] else {}}

    def _end(self, shift: _Shift, now: datetime, out: list[Observation]) -> None:
        self._read_rollout(shift, now, out)
        if self._rollouts.get(shift.thread_id) is shift:
            del self._rollouts[shift.thread_id]
        else:
            self._shifts.pop(shift.thread_id, None)
            self._ended_by_daemon(shift.thread_id, shift.tail)
        # The Judge ends the shift's Contractors with it.
        for thread_id in [i for i, c in self._contractors.items() if c.parent is shift]:
            self._ended_by_daemon(thread_id, self._contractors.pop(thread_id).tail)
        out.append(self._obs(Kind.PROCESS_EXITED, shift, now, now, {"thread_id": shift.thread_id}))

    def _ended_by_daemon(self, thread_id: str, tail: JsonlTail | None) -> None:
        path = tail.path if tail else self._find_rollout(thread_id)
        self._daemon_ended[thread_id] = (_mtime(path) if path else None) or 0.0

    @staticmethod
    def _obs(kind: Kind, shift: _Shift, at: datetime, now: datetime, data: dict[str, Any]) -> Observation:
        return Observation(kind, shift.key, at, now, shift.source, data)
