"""Codex adapter.

Live state comes from the app-server daemon of one Codex home (one shift per
loaded thread); turn and tool detail come from the thread's rollout file.
"""

from __future__ import annotations

import glob
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentville.collector.appserver import AppServerClient, AppServerError, RpcConnection
from agentville.collector.jsonl import JsonlTail
from agentville.common.observations import Kind, Observation, RawLocation, SessionStatus, ShiftKey, Source

PROVIDER = "codex"

_TOOL_CALLS = {"function_call", "custom_tool_call", "local_shell_call"}
_TOOL_OUTPUTS = {"function_call_output", "custom_tool_call_output", "local_shell_call_output"}


def socket_path(home: str) -> str:
    return os.path.join(home, "app-server-control", "app-server-control.sock")


def is_employee_thread(thread: dict[str, Any]) -> bool:
    """Subagent threads (future Contractors) and internal system threads are not Employees."""
    source = thread.get("source")
    if thread.get("parentThreadId") or (isinstance(source, dict) and "subAgent" in source):
        return False
    return thread.get("threadSource") != "system"


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
        self._ignored: set[str] = set()

    def _default_connect(self) -> RpcConnection:
        client = AppServerClient(socket_path(self.home))
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
            for shift in list(self._shifts.values()):
                self._read_rollout(shift, now, out)
            for message in messages:
                if isinstance(message, dict):
                    self._notification(message, now, out)
        except AppServerError:
            self._disconnect(now, out)
        for shift in list(self._shifts.values()):
            self._read_rollout(shift, now, out)
        return out

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
        for thread_id in list(self._shifts):
            if thread_id not in loaded:
                self._end(self._shifts[thread_id], now, out)
        for thread_id in loaded:
            if thread_id in self._ignored:
                continue
            thread = self._read_thread(thread_id)
            if thread is not None:
                self._observe_thread(thread, now, out)

    def _read_thread(self, thread_id: str) -> dict[str, Any] | None:
        assert self._conn is not None
        result = self._conn.request("thread/read", {"threadId": thread_id, "includeTurns": False})
        thread = result.get("thread") if isinstance(result, dict) else None
        return thread if isinstance(thread, dict) else None

    def _observe_thread(self, thread: dict[str, Any], now: datetime, out: list[Observation]) -> None:
        thread_id = thread.get("id")
        if not isinstance(thread_id, str):
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

    def _start(self, thread: dict[str, Any], now: datetime, out: list[Observation]) -> _Shift:
        thread_id = thread["id"]
        tail = None
        path = self._rollout_path(thread)
        if path:
            tail = JsonlTail(path)
            # History written before attach is not replayed; live state comes from the app-server.
            tail.seek_end()
        shift = _Shift(ShiftKey(PROVIDER, thread_id), thread_id, tail)
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

    def _rollout_path(self, thread: dict[str, Any]) -> str | None:
        path = thread.get("path")
        if isinstance(path, str) and path:
            return path
        matches = glob.glob(os.path.join(glob.escape(self.home), "sessions", "*", "*", "*", f"rollout-*-{thread['id']}.jsonl"))
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
        elif method == "thread/closed" and thread_id in self._shifts:
            self._end(self._shifts[thread_id], now, out)
        elif method == "thread/status/changed" and isinstance(thread_id, str):
            status = params.get("status")
            if not isinstance(status, dict) or thread_id in self._ignored:
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
        for offset, record in shift.tail.read():
            at = _from_iso(record.get("timestamp")) or now
            raw = RawLocation(shift.tail.path, offset)
            for kind, data in self._interpret(shift, record):
                out.append(Observation(kind, shift.key, at, now, Source.SESSION_LOG, data, raw))

    def _interpret(self, shift: _Shift, record: dict[str, Any]) -> list[tuple[Kind, dict[str, Any]]]:
        rtype = record.get("type")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            return []
        ptype = payload.get("type")
        if rtype == "event_msg":
            if ptype == "task_started":
                return [(Kind.TURN_STARTED, {})]
            if ptype == "task_complete":
                found = []
                if payload.get("error"):
                    found.append((Kind.AGENT_ERROR, {"status": "task_error"}))
                return found + [(Kind.TURN_COMPLETED, {"duration_ms": payload.get("duration_ms")})]
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
                return [(Kind.TOOL_STARTED, {"tool_id": call_id, "tool": name})]
            if ptype in _TOOL_OUTPUTS:
                return [(Kind.TOOL_FINISHED, {"tool_id": call_id, "tool": shift.open_tools.pop(call_id, None), "success": None})]
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
        self._shifts.pop(shift.thread_id, None)
        out.append(self._obs(Kind.PROCESS_EXITED, shift, now, now, {"thread_id": shift.thread_id}))

    @staticmethod
    def _obs(kind: Kind, shift: _Shift, at: datetime, now: datetime, data: dict[str, Any]) -> Observation:
        return Observation(kind, shift.key, at, now, Source.APP_SERVER, data)
