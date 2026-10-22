"""HQ storage: applies Branch messages to per-Branch current state in SQLite (WAL)."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from agentville.common.protocol import iso

UNREACHABLE_FACTOR = 3
DEFAULT_HEARTBEAT = 30
MAX_CLOCK_LEAD = timedelta(minutes=5)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    branch_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    event_at TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (branch_id, seq)
);
CREATE INDEX IF NOT EXISTS messages_received ON messages (received_at);
CREATE TABLE IF NOT EXISTS branches (
    branch_id TEXT PRIMARY KEY,
    payload TEXT,
    last_seq INTEGER,
    last_seen_at TEXT NOT NULL,
    heartbeat_interval INTEGER,
    last_sent_at TEXT
);
CREATE TABLE IF NOT EXISTS agents (
    branch_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (branch_id, agent_id)
);
CREATE TABLE IF NOT EXISTS activities (
    branch_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (branch_id, agent_id)
);
CREATE TABLE IF NOT EXISTS contractors (
    branch_id TEXT NOT NULL,
    contractor_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (branch_id, contractor_id)
);
"""


@dataclass
class IngestResult:
    accepted: int = 0
    duplicates: int = 0
    stale: int = 0
    need_snapshot: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "duplicates": self.duplicates,
            "stale": self.stale,
            "need_snapshot": self.need_snapshot,
        }


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class Store:
    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(branches)")}
        if "last_sent_at" not in columns:
            self._db.execute("ALTER TABLE branches ADD COLUMN last_sent_at TEXT")
        self._lock = threading.Lock()
        self.totals = IngestResult()
        # Branches asked for a snapshot after a stale one, with no message applied since.
        self._snapshot_requested: set[str] = set()
        # Branches heard since this HQ started; any other is not reported reachable.
        self._heard: set[str] = set()

    def close(self) -> None:
        with self._lock:
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._db.close()

    # Ingest.

    def ingest(self, branch_id: str, messages: list[dict[str, Any]], now: datetime) -> IngestResult:
        """Apply messages from one Branch in seq order. Caller validates the schema."""
        result = IngestResult()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for message in sorted(messages, key=lambda m: m["seq"]):
                    if message["branch_id"] != branch_id:
                        raise ValueError("branch_id mismatch")
                    self._apply(message, now, result)
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            self._heard.add(branch_id)
            self.totals.accepted += result.accepted
            self.totals.duplicates += result.duplicates
            self.totals.stale += result.stale
            self.totals.need_snapshot = self.totals.need_snapshot or result.need_snapshot
        return result

    def _apply(self, message: dict[str, Any], now: datetime, result: IngestResult) -> None:
        branch_id, seq, kind = message["branch_id"], message["seq"], message["kind"]
        clock_reset = False
        if kind == "snapshot":
            row = self._db.execute(
                "SELECT last_seq, last_sent_at FROM branches WHERE branch_id = ?", (branch_id,)
            ).fetchone()
            if row and row[0] is not None and seq <= row[0]:
                stored = self._db.execute(
                    "SELECT sent_at FROM messages WHERE branch_id = ? AND seq = ?", (branch_id, seq)
                ).fetchone()
                if stored and stored[0] == message["sent_at"]:
                    result.duplicates += 1
                    return
                if row[1] is not None and _parse(message["sent_at"]) < _parse(row[1]):
                    if branch_id not in self._snapshot_requested:
                        # A delayed snapshot from before the current numbering, or a reset
                        # Branch whose clock is behind; a fresh snapshot settles either case.
                        self._snapshot_requested.add(branch_id)
                        result.stale += 1
                        result.need_snapshot = True
                        return
                    # The Branch answered the request with another old snapshot: its clock moved back.
                    clock_reset = True
                # The Branch lost its sequence state; its snapshot starts a new numbering.
                self._db.execute("DELETE FROM messages WHERE branch_id = ? AND seq >= ?", (branch_id, seq))
        inserted = self._db.execute(
            "INSERT OR IGNORE INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
            (branch_id, seq, kind, message["event_at"], message["sent_at"], iso(now), json.dumps(message["payload"])),
        ).rowcount
        if not inserted:
            result.duplicates += 1
            return
        row = self._db.execute("SELECT last_seq FROM branches WHERE branch_id = ?", (branch_id,)).fetchone()
        last_seq = row[0] if row else None
        if kind != "snapshot":
            if last_seq is None:
                result.need_snapshot = True
            elif seq < last_seq:
                result.stale += 1
                self._touch(branch_id, now, last_seq)
                return
            elif seq != last_seq + 1:
                result.need_snapshot = True
        self._touch(branch_id, now, seq)
        sent = self._db.execute("SELECT last_sent_at FROM branches WHERE branch_id = ?", (branch_id,)).fetchone()[0]
        sent_at = _parse(message["sent_at"])
        if sent_at <= now + MAX_CLOCK_LEAD and (sent is None or clock_reset or _parse(sent) < sent_at):
            self._db.execute("UPDATE branches SET last_sent_at = ? WHERE branch_id = ?", (message["sent_at"], branch_id))
        payload = message["payload"]
        if kind == "snapshot":
            self._replace(branch_id, payload)
        elif kind == "branch":
            self._db.execute("UPDATE branches SET payload = ? WHERE branch_id = ?", (json.dumps(payload), branch_id))
        elif kind == "heartbeat":
            self._db.execute("UPDATE branches SET heartbeat_interval = ? WHERE branch_id = ?", (payload["interval"], branch_id))
        elif kind == "agent":
            self._upsert("agents", "agent_id", payload["agent_id"], branch_id, payload)
            if payload.get("instance") is None:
                self._db.execute(
                    "DELETE FROM activities WHERE branch_id = ? AND agent_id = ?", (branch_id, payload["agent_id"])
                )
        elif kind == "activity":
            self._upsert("activities", "agent_id", payload["agent_id"], branch_id, payload)
        elif kind == "contractor":
            if payload["status"] == "ended":
                self._db.execute(
                    "DELETE FROM contractors WHERE branch_id = ? AND contractor_id = ?", (branch_id, payload["contractor_id"])
                )
            else:
                self._upsert("contractors", "contractor_id", payload["contractor_id"], branch_id, payload)
        self._snapshot_requested.discard(branch_id)
        result.accepted += 1

    def _touch(self, branch_id: str, now: datetime, seq: int) -> None:
        self._db.execute(
            "INSERT INTO branches (branch_id, last_seq, last_seen_at) VALUES (?, ?, ?) "
            "ON CONFLICT (branch_id) DO UPDATE SET last_seq = excluded.last_seq, last_seen_at = excluded.last_seen_at",
            (branch_id, seq, iso(now)),
        )

    def _upsert(self, table: str, key: str, value: str, branch_id: str, payload: dict[str, Any]) -> None:
        self._db.execute(
            f"INSERT INTO {table} (branch_id, {key}, payload) VALUES (?, ?, ?) "
            f"ON CONFLICT (branch_id, {key}) DO UPDATE SET payload = excluded.payload",
            (branch_id, value, json.dumps(payload)),
        )

    def _replace(self, branch_id: str, snapshot: dict[str, Any]) -> None:
        for table in ("agents", "activities", "contractors"):
            self._db.execute(f"DELETE FROM {table} WHERE branch_id = ?", (branch_id,))
        self._db.execute("UPDATE branches SET payload = ? WHERE branch_id = ?", (json.dumps(snapshot["branch"]), branch_id))
        for agent in snapshot["agents"]:
            self._upsert("agents", "agent_id", agent["agent_id"], branch_id, agent)
        for activity in snapshot["activities"]:
            self._upsert("activities", "agent_id", activity["agent_id"], branch_id, activity)
        for contractor in snapshot["contractors"]:
            self._upsert("contractors", "contractor_id", contractor["contractor_id"], branch_id, contractor)

    # Read.

    def state(self, now: datetime) -> dict[str, Any]:
        with self._lock:
            branches = []
            for branch_id, payload, last_seq, last_seen, interval in self._db.execute(
                "SELECT branch_id, payload, last_seq, last_seen_at, heartbeat_interval FROM branches ORDER BY branch_id"
            ):
                window = timedelta(seconds=(interval or DEFAULT_HEARTBEAT) * UNREACHABLE_FACTOR)
                reachable = branch_id in self._heard and now - _parse(last_seen) <= window
                branches.append(
                    {
                        "branch_id": branch_id,
                        "branch": json.loads(payload) if payload else None,
                        "last_seq": last_seq,
                        "last_seen_at": last_seen,
                        "reachable": reachable,
                    }
                )
            return {
                "branches": branches,
                "agents": self._rows("agents"),
                "activities": self._rows("activities"),
                "contractors": self._rows("contractors"),
            }

    def _rows(self, table: str) -> list[dict[str, Any]]:
        out = []
        for branch_id, payload in self._db.execute(f"SELECT branch_id, payload FROM {table} ORDER BY rowid"):
            item = json.loads(payload)
            item["branch_id"] = branch_id
            out.append(item)
        return out

    def prune(self, before: datetime) -> int:
        with self._lock:
            return self._db.execute("DELETE FROM messages WHERE received_at < ?", (iso(before),)).rowcount


def now_utc() -> datetime:
    return datetime.now(UTC)
