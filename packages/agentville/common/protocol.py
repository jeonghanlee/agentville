"""Branch-HQ message envelope (schema version 1)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from importlib import resources
from typing import Any

SCHEMA_VERSION = 1


def load_schema() -> dict[str, Any]:
    """The canonical Branch-HQ message JSON Schema."""
    text = resources.files("agentville.common").joinpath("schemas/protocol-v1.schema.json").read_text(encoding="utf-8")
    return json.loads(text)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Envelope:
    """Wraps payloads with the per-Branch sequence number.

    ``reserve`` is called before a number beyond the reserved range is used, so a
    restarted Branch never reuses a sequence number it may already have sent.
    """

    def __init__(self, branch_id: str, seq: int = 0, reserve: Callable[[int], int] | None = None) -> None:
        self.branch_id = branch_id
        self.seq = seq
        self._reserve = reserve
        self._reserved = seq if reserve else None

    def wrap(self, kind: str, event_at: datetime, payload: dict[str, Any], sent_at: datetime) -> dict[str, Any]:
        if self._reserve is not None and self._reserved is not None and self.seq + 1 > self._reserved:
            self._reserved = self._reserve(self.seq + 1)
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
