"""Branch-HQ message envelope (schema version 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = 1


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Envelope:
    """Wraps payloads with the per-Branch sequence number."""

    def __init__(self, branch_id: str, seq: int = 0) -> None:
        self.branch_id = branch_id
        self.seq = seq

    def wrap(self, kind: str, event_at: datetime, payload: dict[str, Any], sent_at: datetime) -> dict[str, Any]:
        self.seq += 1
        return {
            "schema_version": SCHEMA_VERSION,
            "branch_id": self.branch_id,
            "seq": self.seq,
            "kind": kind,
            "event_at": iso(event_at),
            "sent_at": iso(sent_at),
            "payload": payload,
        }
