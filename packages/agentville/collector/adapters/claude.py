"""Claude Code adapter.

Live state comes from ``<home>/sessions/<pid>.json``; detail comes from the
transcript ``<home>/projects/<encoded-cwd>/<sessionId>.jsonl``.
"""

from __future__ import annotations

import glob
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentville.collector.jsonl import JsonlTail
from agentville.common.observations import (
    Kind,
    Observation,
    RawLocation,
    SessionStatus,
    ShiftKey,
    Source,
)

PROVIDER = "claude"

_STATUS_MAP = {
    "busy": SessionStatus.ACTIVE,
    "idle": SessionStatus.IDLE,
    "waiting": SessionStatus.WAITING,
}


def encode_cwd(cwd: str) -> str:
    return cwd.replace("/", "-").replace(".", "-")


def _from_epoch_ms(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    return None


def _from_iso(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _proc_stat_fields(pid: int, proc_root: str) -> list[str] | None:
    """Return /proc/<pid>/stat fields from field 3 (state) onward."""
    try:
        with open(os.path.join(proc_root, str(pid), "stat"), encoding="ascii", errors="replace") as fh:
            stat = fh.read()
    except OSError:
        return None
    fields = stat[stat.rfind(")") + 2 :].split()
    return fields if len(fields) > 19 else None


def proc_start_ticks(pid: int, proc_root: str = "/proc") -> str | None:
    """Return field 22 of /proc/<pid>/stat (start time in clock ticks since boot)."""
    fields = _proc_stat_fields(pid, proc_root)
    return fields[19] if fields else None


def _default_is_alive(pid: int, proc_start: str | None, proc_root: str = "/proc") -> bool:
    fields = _proc_stat_fields(pid, proc_root)
    if fields is None or fields[0] == "Z":
        return False
    return proc_start is None or fields[19] == str(proc_start)


@dataclass
class _Shift:
    key: ShiftKey
    pid: int
    cwd: str
    session_id: str | None
    status: str | None
    waiting: bool
    tail: JsonlTail | None
    proc_start: str | None = None
    model: tuple[str | None, str | None] = (None, None)
    open_tools: dict[str, str] = field(default_factory=dict)


class ClaudeAdapter:
    def __init__(
        self,
        home: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        is_alive: Callable[[int, str | None], bool] = _default_is_alive,
    ) -> None:
        self.home = home
        self._clock = clock
        self._is_alive = is_alive
        self._shifts: dict[int, _Shift] = {}

    def poll(self) -> list[Observation]:
        now = self._clock()
        out: list[Observation] = []
        seen: set[int] = set()
        for pid, doc in self._read_session_files():
            shift = self._shifts.get(pid)
            if doc is None:
                # Present but unreadable (e.g. mid-write): keep the shift until the next good read.
                if shift is not None and self._is_alive(pid, shift.proc_start):
                    seen.add(pid)
                    self._read_transcript(shift, now, out)
                continue
            if not self._is_alive(pid, doc.get("procStart")):
                continue
            seen.add(pid)
            if shift is not None and shift.key.native_id != self._native_id(pid, doc):
                out.extend(self._end(shift, now))
                shift = None
            if shift is None:
                shift = self._start(pid, doc, now, out)
            self._update(shift, doc, now, out)
            self._read_transcript(shift, now, out)
        for pid in list(self._shifts):
            if pid not in seen:
                out.extend(self._end(self._shifts[pid], now))
        return out

    def _read_session_files(self) -> list[tuple[int, dict[str, Any] | None]]:
        directory = os.path.join(self.home, "sessions")
        try:
            names = os.listdir(directory)
        except FileNotFoundError:
            return []
        result = []
        for name in sorted(names):
            stem, ext = os.path.splitext(name)
            if ext != ".json" or not stem.isdigit():
                continue
            try:
                with open(os.path.join(directory, name), encoding="utf-8") as fh:
                    doc = json.load(fh)
            except FileNotFoundError:
                continue
            except (OSError, json.JSONDecodeError):
                doc = None
            if doc is None or (isinstance(doc, dict) and doc.get("pid") == int(stem)):
                result.append((int(stem), doc))
        return result

    @staticmethod
    def _native_id(pid: int, doc: dict[str, Any]) -> str:
        return f"{pid}:{doc.get('procStart')}"

    def _start(self, pid: int, doc: dict[str, Any], now: datetime, out: list[Observation]) -> _Shift:
        key = ShiftKey(PROVIDER, self._native_id(pid, doc))
        shift = _Shift(key, pid, doc.get("cwd", ""), None, None, False, None, doc.get("procStart"))
        self._shifts[pid] = shift
        started = _from_epoch_ms(doc.get("startedAt")) or now
        out.append(
            Observation(
                Kind.PROCESS_STARTED,
                key,
                started,
                now,
                Source.SESSION_FILE,
                {
                    "pid": pid,
                    "cwd": shift.cwd,
                    "session_id": doc.get("sessionId"),
                    "kind": doc.get("kind"),
                    "runtime": {"type": "tmux", "location": doc["tmux"]} if doc.get("tmux") else {"type": "shell"},
                },
            )
        )
        return shift

    def _update(self, shift: _Shift, doc: dict[str, Any], now: datetime, out: list[Observation]) -> None:
        at = _from_epoch_ms(doc.get("statusUpdatedAt")) or _from_epoch_ms(doc.get("updatedAt")) or now
        session_id = doc.get("sessionId")
        if session_id and session_id != shift.session_id:
            self._read_transcript(shift, now, out)
            shift.open_tools.clear()
            shift.session_id = session_id
            # History written before attach is not replayed; live state comes from the session file.
            shift.tail = JsonlTail(self._transcript_path(shift.cwd, session_id))
            shift.tail.seek_end()
            out.append(Observation(Kind.SESSION_STARTED, shift.key, at, now, Source.SESSION_FILE, {"session_id": session_id}))
        status = doc.get("status")
        if status == shift.status:
            return
        shift.status = status
        normalized = _STATUS_MAP.get(status, SessionStatus.UNKNOWN)
        waiting = normalized is SessionStatus.WAITING
        if waiting and not shift.waiting:
            reason = str(doc.get("waitingFor", "")).split(" ", 1)[0] or None
            out.append(Observation(Kind.INPUT_REQUESTED, shift.key, at, now, Source.SESSION_FILE, {"reason": reason}))
        elif shift.waiting and not waiting:
            out.append(Observation(Kind.INPUT_RESOLVED, shift.key, at, now, Source.SESSION_FILE))
        shift.waiting = waiting
        out.append(
            Observation(Kind.SESSION_STATUS, shift.key, at, now, Source.SESSION_FILE, {"status": normalized.value, "native": status})
        )

    def _transcript_path(self, cwd: str, session_id: str) -> str:
        expected = os.path.join(self.home, "projects", encode_cwd(cwd), f"{session_id}.jsonl")
        if os.path.exists(expected):
            return expected
        matches = glob.glob(os.path.join(glob.escape(self.home), "projects", "*", f"{session_id}.jsonl"))
        return matches[0] if matches else expected

    def _read_transcript(self, shift: _Shift, now: datetime, out: list[Observation]) -> None:
        if shift.tail is None:
            return
        if not os.path.exists(shift.tail.path) and shift.session_id:
            resolved = self._transcript_path(shift.cwd, shift.session_id)
            if resolved != shift.tail.path:
                shift.tail = JsonlTail(resolved)
        for offset, record in shift.tail.read():
            raw = RawLocation(shift.tail.path, offset)
            at = _from_iso(record.get("timestamp")) or now
            for kind, data in self._interpret(shift, record):
                out.append(Observation(kind, shift.key, at, now, Source.SESSION_LOG, data, raw))

    def _interpret(self, shift: _Shift, record: dict[str, Any]) -> list[tuple[Kind, dict[str, Any]]]:
        rtype = record.get("type")
        if record.get("isSidechain"):
            return []
        if rtype == "system" and record.get("subtype") == "turn_duration":
            return [(Kind.TURN_COMPLETED, {"duration_ms": record.get("durationMs")})]
        message = record.get("message")
        if not isinstance(message, dict):
            return []
        content = message.get("content")
        items = content if isinstance(content, list) else []
        if rtype == "user":
            results = [i for i in items if isinstance(i, dict) and i.get("type") == "tool_result"]
            if results:
                found = []
                for item in results:
                    tool_id = item.get("tool_use_id")
                    found.append(
                        (
                            Kind.TOOL_FINISHED,
                            {
                                "tool_id": tool_id,
                                "tool": shift.open_tools.pop(tool_id, None),
                                "success": item.get("is_error") is not True,
                                "denial": record.get("toolDenialKind"),
                            },
                        )
                    )
                return found
            if record.get("isMeta") or record.get("toolUseResult") is not None:
                return []
            if isinstance(content, str) or any(isinstance(i, dict) and i.get("type") == "text" for i in items):
                return [(Kind.TURN_STARTED, {})]
            return []
        if rtype == "assistant":
            found = []
            if record.get("isApiErrorMessage"):
                found.append((Kind.AGENT_ERROR, {"status": record.get("apiErrorStatus")}))
            model = (record.get("requestedModel") or message.get("model"), record.get("effort"))
            if not record.get("isApiErrorMessage") and model != shift.model and any(model):
                shift.model = model
                found.append((Kind.MODEL_CHANGED, {"model": model[0], "settings": {"effort": model[1]} if model[1] else {}}))
            for item in items:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    shift.open_tools[item.get("id")] = item.get("name")
                    found.append((Kind.TOOL_STARTED, {"tool_id": item.get("id"), "tool": item.get("name")}))
            return found
        return []

    def _end(self, shift: _Shift, now: datetime) -> list[Observation]:
        self._shifts.pop(shift.pid, None)
        out: list[Observation] = []
        self._read_transcript(shift, now, out)
        return out + [Observation(Kind.PROCESS_EXITED, shift.key, now, now, Source.PROCESS, {"pid": shift.pid})]
