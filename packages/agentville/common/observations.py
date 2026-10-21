"""Provider-neutral observations emitted by Adapters and consumed by the Judge."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Kind(StrEnum):
    PROCESS_STARTED = "process.started"
    PROCESS_EXITED = "process.exited"
    SESSION_STARTED = "session.started"
    SESSION_STATUS = "session.status"
    TURN_STARTED = "turn.started"
    TURN_COMPLETED = "turn.completed"
    GENERATION_STARTED = "generation.started"
    GENERATION_ENDED = "generation.ended"
    TOOL_STARTED = "tool.started"
    TOOL_FINISHED = "tool.finished"
    INPUT_REQUESTED = "input.requested"
    INPUT_RESOLVED = "input.resolved"
    LIMIT_REACHED = "limit.reached"
    LIMIT_CLEARED = "limit.cleared"
    AGENT_ERROR = "agent.error"
    MODEL_CHANGED = "model.changed"
    ACCOUNT_CHANGED = "account.changed"
    SUBAGENT_STARTED = "subagent.started"
    SUBAGENT_STATUS = "subagent.status"
    SUBAGENT_ENDED = "subagent.ended"


class Source(StrEnum):
    SESSION_FILE = "session_file"
    SESSION_LOG = "session_log"
    APP_SERVER = "app_server"
    HOOK = "hook"
    PROCESS = "process"


class SessionStatus(StrEnum):
    """Normalized live status reported by a provider for one shift."""

    ACTIVE = "active"
    IDLE = "idle"
    WAITING = "waiting"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ShiftKey:
    """Identity of one shift (AgentInstance) as seen by an Adapter."""

    provider: str
    native_id: str


@dataclass(frozen=True)
class RawLocation:
    path: str
    offset: int


@dataclass(frozen=True)
class Observation:
    kind: Kind
    shift: ShiftKey
    event_at: datetime
    observed_at: datetime
    source: Source
    data: dict[str, Any] = field(default_factory=dict)
    raw: RawLocation | None = None
