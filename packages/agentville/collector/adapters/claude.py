"""Claude Code adapter.

Live state comes from ``<home>/sessions/<pid>.json``; detail comes from the
transcript ``<home>/projects/<encoded-cwd>/<sessionId>.jsonl``. An ``Agent``
tool call is a Contractor, followed through its subagent transcript
``<sessionId>/subagents/agent-<agentId>.jsonl`` when present.
"""

from __future__ import annotations

import glob
import json
import os
import sys
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
SUBAGENT_TOOL = "Agent"

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


def reset_time(value: Any) -> datetime | None:
    """``quotaLimits.resetsAt`` given as epoch seconds, epoch milliseconds, or ISO 8601."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    at = _from_iso(value)
    return at.replace(tzinfo=UTC) if at is not None and at.tzinfo is None else at


def first_timestamp(path: str, lines: int = 20) -> datetime | None:
    """Timestamp of the earliest record among the file's first lines."""
    try:
        with open(path, "rb") as fh:
            head = [fh.readline() for _ in range(lines)]
    except OSError:
        return None
    for line in head:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        at = _from_iso(record.get("timestamp")) if isinstance(record, dict) else None
        if at is not None:
            return at
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


def _model_data(model: tuple[str | None, str | None]) -> dict[str, Any]:
    return {"model": model[0], "settings": {"effort": model[1]} if model[1] else {}}


def last_model(path: str, window: int = 256 * 1024) -> tuple[str | None, str | None] | None:
    """Model and effort of the last non-error assistant record in the file's tail."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - window))
            data = fh.read()
    except OSError:
        return None
    for line in reversed(data.splitlines()):
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict) or record.get("type") != "assistant" or record.get("isApiErrorMessage"):
            continue
        message = record.get("message") if isinstance(record.get("message"), dict) else {}
        model = (record.get("requestedModel") or message.get("model"), record.get("effort"))
        if any(model):
            return model
    return None


def _default_is_alive(pid: int, proc_start: str | None, proc_root: str = "/proc") -> bool:
    fields = _proc_stat_fields(pid, proc_root)
    if fields is None or fields[0] == "Z":
        return False
    return proc_start is None or fields[19] == str(proc_start)


@dataclass
class _SubAgent:
    tool_use_id: str
    tail: JsonlTail | None = None
    status: str = "active"
    tool: str | None = None
    reported: tuple[str, str | None] = ("active", None)
    # The Agent tool returned; a background run still ends with its own transcript.
    released: bool = False


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
    subagents: dict[str, _SubAgent] = field(default_factory=dict)


class ClaudeAdapter:
    def __init__(
        self,
        home: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        is_alive: Callable[[int, str | None], bool] = _default_is_alive,
        account_alias: str | None = None,
    ) -> None:
        self.home = home
        self.account_alias = account_alias
        self._clock = clock
        self._is_alive = is_alive
        self._shifts: dict[int, _Shift] = {}
        self._attached_at: datetime | None = None
        self._followed: set[str] = set()

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
        if self._attached_at is None:
            self._attached_at = now
        return out

    def _history_before_attach(self, path: str) -> bool:
        # A transcript created after attach is read from its start; a resumed one is not,
        # including one already followed earlier in this run.
        resumed = path in self._followed
        self._followed.add(path)
        if self._attached_at is None or resumed:
            return True
        if not os.path.exists(path):
            return False
        started = first_timestamp(path)
        return started is None or started < self._attached_at

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
                    "account_alias": self.account_alias,
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
            for tool_use_id in shift.subagents:
                out.append(Observation(Kind.SUBAGENT_ENDED, shift.key, at, now, Source.SESSION_FILE, {"subagent_id": tool_use_id}))
            shift.subagents.clear()
            shift.session_id = session_id
            shift.tail = JsonlTail(self._transcript_path(shift.cwd, session_id))
            if self._history_before_attach(shift.tail.path):
                # History written before attach is not replayed; live state comes from the session file.
                shift.tail.seek_end()
            model = last_model(shift.tail.path)
            if model is not None and model != shift.model:
                shift.model = model
                out.append(
                    Observation(Kind.MODEL_CHANGED, shift.key, at, now, Source.SESSION_LOG, _model_data(model))
                )
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
        try:
            for offset, record in shift.tail.read():
                raw = RawLocation(shift.tail.path, offset)
                at = _from_iso(record.get("timestamp")) or now
                for kind, data in self._interpret(shift, record):
                    out.append(Observation(kind, shift.key, at, now, Source.SESSION_LOG, data, raw))
        except OSError as exc:
            # One unreadable transcript must not discard observations of the other shifts.
            print(f"agentville-collector: {shift.tail.path}: {exc}", file=sys.stderr, flush=True)
        for sub in list(shift.subagents.values()):
            self._read_subagent(shift, sub, now, out)
            if sub.released and (sub.tail is None or sub.status != "active"):
                del shift.subagents[sub.tool_use_id]
                out.append(Observation(Kind.SUBAGENT_ENDED, shift.key, now, now, Source.SESSION_LOG, {"subagent_id": sub.tool_use_id}))

    def _subagent_tail(self, shift: _Shift, sub: _SubAgent) -> JsonlTail | None:
        assert shift.tail is not None
        directory = os.path.join(os.path.dirname(shift.tail.path), str(shift.session_id), "subagents")
        for meta_path in glob.glob(os.path.join(glob.escape(directory), "agent-*.meta.json")):
            try:
                with open(meta_path, encoding="utf-8") as fh:
                    meta = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(meta, dict) and meta.get("toolUseId") == sub.tool_use_id:
                return JsonlTail(meta_path[: -len(".meta.json")] + ".jsonl")
        return None

    def _read_subagent(self, shift: _Shift, sub: _SubAgent, now: datetime, out: list[Observation]) -> None:
        if sub.tail is None:
            sub.tail = self._subagent_tail(shift, sub)
            if sub.tail is None:
                return
        try:
            for offset, record in sub.tail.read():
                if not self._interpret_subagent(sub, record):
                    continue
                tool = sub.tool if sub.status == "active" else None
                if (sub.status, tool) == sub.reported:
                    continue
                sub.reported = (sub.status, tool)
                at = _from_iso(record.get("timestamp")) or now
                data = {"subagent_id": sub.tool_use_id, "status": sub.status, "tool": tool}
                out.append(Observation(Kind.SUBAGENT_STATUS, shift.key, at, now, Source.SESSION_LOG, data, RawLocation(sub.tail.path, offset)))
        except OSError as exc:
            print(f"agentville-collector: {sub.tail.path}: {exc}", file=sys.stderr, flush=True)

    @staticmethod
    def _interpret_subagent(sub: _SubAgent, record: dict[str, Any]) -> bool:
        """Update the subagent's status and tool from one of its records; True when relevant."""
        rtype = record.get("type")
        if rtype == "system" and record.get("subtype") == "turn_duration":
            sub.status, sub.tool = "idle", None
            return True
        message = record.get("message")
        if rtype not in ("user", "assistant") or not isinstance(message, dict):
            return False
        items = [i for i in message.get("content") or [] if isinstance(i, dict)] if isinstance(message.get("content"), list) else []
        if rtype == "user":
            if any(i.get("type") == "tool_result" for i in items):
                sub.tool = None
            sub.status = "active"
            return True
        if record.get("isApiErrorMessage"):
            sub.status, sub.tool = "error", None
            return True
        tools = [i.get("name") for i in items if i.get("type") == "tool_use"]
        if tools:
            sub.status, sub.tool = "active", tools[-1]
        elif message.get("stop_reason") == "end_turn":
            sub.status, sub.tool = "idle", None
        else:
            sub.status = "active"
        return True

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
                    if tool_id in shift.subagents:
                        shift.subagents[tool_id].released = True
                return found
            if record.get("isMeta") or record.get("toolUseResult") is not None:
                return []
            if isinstance(content, str) or any(isinstance(i, dict) and i.get("type") == "text" for i in items):
                return [(Kind.TURN_STARTED, {})]
            return []
        if rtype == "assistant":
            found = []
            quota = record.get("quotaLimits")
            if record.get("isApiErrorMessage") and isinstance(quota, dict):
                # A usage limit; none of the record's error text is sent.
                found.append((Kind.LIMIT_REACHED, {"reset_at": reset_time(quota.get("resetsAt"))}))
            elif record.get("isApiErrorMessage"):
                found.append((Kind.AGENT_ERROR, {"status": record.get("apiErrorStatus")}))
            model = (record.get("requestedModel") or message.get("model"), record.get("effort"))
            if not record.get("isApiErrorMessage") and model != shift.model and any(model):
                shift.model = model
                found.append((Kind.MODEL_CHANGED, _model_data(model)))
            for item in items:
                if isinstance(item, dict) and item.get("type") == "tool_use":
                    tool_id = item.get("id")
                    shift.open_tools[tool_id] = item.get("name")
                    found.append((Kind.TOOL_STARTED, {"tool_id": tool_id, "tool": item.get("name")}))
                    if item.get("name") == SUBAGENT_TOOL and isinstance(tool_id, str) and tool_id not in shift.subagents:
                        shift.subagents[tool_id] = _SubAgent(tool_id)
                        found.append((Kind.SUBAGENT_STARTED, {"subagent_id": tool_id, "provider": PROVIDER, "status": "active", "tool": None}))
            return found
        return []

    def _end(self, shift: _Shift, now: datetime) -> list[Observation]:
        self._shifts.pop(shift.pid, None)
        out: list[Observation] = []
        self._read_transcript(shift, now, out)
        return out + [Observation(Kind.PROCESS_EXITED, shift.key, now, now, Source.PROCESS, {"pid": shift.pid})]
