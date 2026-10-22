"""Observe agy presence locks and activity without controlling its sessions."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from agentville.collector.jsonl import JsonlTail
from agentville.collector.process import Process, ProcessTable
from agentville.common.observations import Kind, Observation, RawLocation, ShiftKey, Source

PROVIDER = "antigravity"
TAIL_WINDOW = 256 * 1024


def event_time(record: dict, now: datetime) -> datetime:
    try:
        at = datetime.fromisoformat(str(record.get("created_at", "")).replace("Z", "+00:00"))
        return at.replace(tzinfo=UTC) if at.tzinfo is None else at
    except ValueError:
        return now


def activity_identity(record: dict) -> bytes:
    """Fingerprint activity fields without retaining content or tool arguments."""
    calls = record.get("tool_calls")
    names = [call.get("name") if isinstance(call, dict) else None for call in calls] if isinstance(calls, list) else []
    fields = [record.get(key) for key in ("created_at", "step_index", "type", "source", "status")]
    encoded = json.dumps([*fields, names], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).digest()


@dataclass
class _Shift:
    key: ShiftKey
    process: Process
    tail: JsonlTail
    tools: dict[tuple[Any, int], str] = field(default_factory=dict)
    seen: set[bytes] = field(default_factory=set)


class AntigravityAdapter:
    def __init__(self, home: str, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 account_alias: str | None = None, proc_root: str = "/proc") -> None:
        self.root = Path(home) / "antigravity-cli"
        self.account_alias = account_alias
        self._clock = clock
        self._processes = ProcessTable(proc_root)
        self._shifts: dict[str, _Shift] = {}

    def poll(self) -> list[Observation]:
        now, out = self._clock(), []
        self._processes.refresh()
        owners, seen = self._processes.lock_owners(), set()
        for path in sorted((self.root / "presence").glob("*.lock")):
            try:
                stat = path.stat()
            except OSError:
                continue
            pid = owners.get((os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino))
            process = self._processes.processes.get(pid)
            if process is None or process.name != "agy":
                continue
            conversation = path.stem
            seen.add(conversation)
            shift = self._shifts.get(conversation)
            if shift is not None and shift.process.identity != process.identity:
                out.append(self._obs(Kind.PROCESS_EXITED, shift, now, now))
                shift = None
            if shift is None:
                tail = JsonlTail(str(self.root / "brain" / conversation / ".system_generated/logs/transcript.jsonl"))
                shift = _Shift(ShiftKey(PROVIDER, f"{conversation}:{pid}:{process.start}"), process, tail)
                self._shifts[conversation] = shift
                data = {**self._processes.observation_identity(process), "cwd": process.cwd or "",
                        "session_id": conversation, "runtime": {"type": "shell"},
                        "account_alias": self.account_alias, "max_confidence": "medium"}
                out.append(self._obs(Kind.PROCESS_STARTED, shift, now, now, data))
                out.append(self._obs(Kind.SESSION_STARTED, shift, now, now, {"session_id": conversation}))
                self._seed(shift, now, out)
            self._read(shift, now, out)
        for conversation in list(self._shifts):
            if conversation not in seen:
                out.append(self._obs(Kind.PROCESS_EXITED, self._shifts.pop(conversation), now, now))
        return out

    def _seed(self, shift: _Shift, now: datetime, out: list[Observation]) -> None:
        """Seed current status from complete tail records without replaying tool counts."""
        try:
            with open(shift.tail.path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(0)
                for line in fh:
                    if fh.tell() > size or not line.endswith(b"\n"):
                        break
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict):
                        shift.seen.add(activity_identity(record))
                fh.seek(max(0, size - TAIL_WINDOW))
                data = fh.read(min(size, TAIL_WINDOW))
            lines = data.split(b"\n")[:-1]
            for line in reversed(lines):
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict):
                    continue
                events = self._interpret(shift, record)
                if events:
                    status = "unknown"
                    if any(kind is Kind.AGENT_ERROR for kind, _ in events):
                        out.append(self._obs(Kind.AGENT_ERROR, shift, now, now))
                    else:
                        if any(kind in (Kind.TOOL_STARTED, Kind.TOOL_FINISHED, Kind.TURN_STARTED) for kind, _ in events):
                            status = "active"
                        elif any(kind is Kind.TURN_COMPLETED for kind, _ in events):
                            status = "idle"
                        out.append(self._obs(Kind.SESSION_STATUS, shift, now, now, {"status": status}))
                    break
            shift.tail.seek_end()
        except OSError as exc:
            self._log(exc)

    def _read(self, shift: _Shift, now: datetime, out: list[Observation]) -> None:
        try:
            for offset, record in shift.tail.read():
                identity = activity_identity(record)
                if identity in shift.seen:
                    continue
                shift.seen.add(identity)
                at = event_time(record, now)
                for kind, data in self._interpret(shift, record):
                    out.append(Observation(kind, shift.key, at, now, Source.SESSION_LOG, data,
                                           RawLocation(shift.tail.path, offset)))
        except OSError as exc:
            self._log(exc)

    def _interpret(self, shift: _Shift, record: dict) -> list[tuple[Kind, dict]]:
        kind, status, source = record.get("type"), record.get("status"), record.get("source")
        calls = record.get("tool_calls")
        if kind == "ERROR_MESSAGE":
            shift.tools.clear()
            return [(Kind.TOOL_FINISHED, {}), (Kind.AGENT_ERROR, {})]
        if kind == "USER_INPUT" and source == "USER_EXPLICIT":
            return [(Kind.TURN_STARTED, {})]
        if source != "MODEL":
            return []
        if kind == "GENERIC" and isinstance(calls, list) and calls:
            events = []
            step = record.get("step_index")
            if not isinstance(step, (int, str)):
                return []
            for index, call in enumerate(calls):
                if not isinstance(call, dict) or not isinstance(call.get("name"), str):
                    continue
                key = (step, index)
                if status == "RUNNING" and key not in shift.tools:
                    shift.tools[key] = call["name"]
                    events.append((Kind.TOOL_STARTED, {"tool": call["name"]}))
                elif status in ("DONE", "ERROR"):
                    shift.tools.pop(key, None)
                    events.append((Kind.TOOL_FINISHED, {"success": status == "DONE",
                                                        "remaining_tool": next(reversed(shift.tools.values()), None)}))
            return events
        if kind == "PLANNER_RESPONSE" and not calls:
            if status == "DONE":
                shift.tools.clear()
                return [(Kind.TURN_COMPLETED, {})]
            if status == "RUNNING":
                return [(Kind.TURN_STARTED, {})]
            if status == "ERROR":
                shift.tools.clear()
                return [(Kind.TOOL_FINISHED, {}), (Kind.AGENT_ERROR, {})]
        return []

    @staticmethod
    def _obs(kind: Kind, shift: _Shift, at: datetime, now: datetime, data: dict | None = None) -> Observation:
        return Observation(kind, shift.key, at, now, Source.SESSION_LOG, data or {})

    @staticmethod
    def _log(exc: OSError) -> None:
        print(f"agentville-collector: Antigravity transcript: {exc}", file=sys.stderr, flush=True)
