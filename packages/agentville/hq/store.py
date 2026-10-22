"""HQ storage: applies Branch messages to per-Branch current state in SQLite (WAL), and keeps its history."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from agentville.common.protocol import iso
from agentville.hq import history

UNREACHABLE_FACTOR = 3
DEFAULT_HEARTBEAT = 30
MAX_CLOCK_LEAD = timedelta(minutes=5)
MAX_CHANGES = 5000

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
CREATE INDEX IF NOT EXISTS messages_branch_received ON messages (branch_id, received_at);
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
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY,
    branch_id TEXT NOT NULL,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS changes_at ON changes (at);
CREATE INDEX IF NOT EXISTS changes_key ON changes (branch_id, kind, key, at);
CREATE TABLE IF NOT EXISTS baseline (
    branch_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (branch_id, kind, key)
);
CREATE TABLE IF NOT EXISTS meta (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Current-state table and key column of each change kind; a Branch payload lives in ``branches``.
_TABLES = {"agent": ("agents", "agent_id"), "activity": ("activities", "agent_id"), "contractor": ("contractors", "contractor_id")}
# The latest change of each key before (op "<") or at or before (op "<=") a time; equal times keep recording order.
_LATEST = """
SELECT branch_id, kind, key, payload FROM (
    SELECT branch_id, kind, key, payload,
           ROW_NUMBER() OVER (PARTITION BY branch_id, kind, key ORDER BY at DESC, id DESC) AS position
    FROM changes WHERE at {op} ?
) WHERE position = 1
"""


@dataclass
class IngestResult:
    accepted: int = 0
    duplicates: int = 0
    stale: int = 0
    need_snapshot: bool = False
    # A snapshot was applied; not part of the response.
    resynced: bool = False

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
    def __init__(self, path: str, now: datetime | None = None) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(branches)")}
        if "last_sent_at" not in columns:
            self._db.execute("ALTER TABLE branches ADD COLUMN last_sent_at TEXT")
        # Start of the kept history; the baseline holds the state as of this time.
        row = self._db.execute("SELECT value FROM meta WHERE name = 'history_from'").fetchone()
        self._from: str | None = row[0] if row else None
        if self._from is None and self._db.execute(
            "SELECT 1 FROM agents UNION ALL SELECT 1 FROM branches WHERE payload IS NOT NULL LIMIT 1"
        ).fetchone():
            self._seed_baseline(now or now_utc())
        self._lock = threading.Lock()
        self.totals = IngestResult()
        # Branches asked for a snapshot after a stale one, with no message applied since.
        self._snapshot_requested: set[str] = set()
        # Branches heard since this HQ started; any other is not reported reachable.
        self._heard: set[str] = set()

    def _seed_baseline(self, now: datetime) -> None:
        """A database written before history was kept starts its history from the current state."""
        self._db.execute("BEGIN IMMEDIATE")
        self._db.execute("INSERT OR REPLACE INTO baseline SELECT branch_id, 'branch', '', payload FROM branches WHERE payload IS NOT NULL")
        for kind, (table, column) in _TABLES.items():
            self._db.execute(f"INSERT OR REPLACE INTO baseline SELECT branch_id, ?, {column}, payload FROM {table}", (kind,))
        self._start_history(iso(now))
        self._db.execute("COMMIT")

    def _start_history(self, at: str) -> None:
        self._db.execute("INSERT OR REPLACE INTO meta VALUES ('history_from', ?)", (at,))
        self._from = at

    def heard(self) -> frozenset[str]:
        """Branches heard since this HQ started."""
        with self._lock:
            return frozenset(self._heard)

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
                if self._from is None:
                    self._start_history(iso(now))
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
        # The history time of a change is the time of the fact, never far ahead of HQ's clock.
        at = min(_parse(message["event_at"]), now + MAX_CLOCK_LEAD)
        if kind == "snapshot":
            self._replace(branch_id, payload, at)
            result.resynced = True
        elif kind == "branch":
            self._set("branch", branch_id, "", payload, at)
        elif kind == "heartbeat":
            self._db.execute("UPDATE branches SET heartbeat_interval = ? WHERE branch_id = ?", (payload["interval"], branch_id))
        elif kind == "agent":
            self._set("agent", branch_id, payload["agent_id"], payload, at)
            if payload.get("instance") is None:
                self._remove("activity", branch_id, payload["agent_id"], at)
        elif kind == "activity":
            self._set("activity", branch_id, payload["agent_id"], payload, at)
        elif kind == "contractor":
            if payload["status"] == "ended":
                self._remove("contractor", branch_id, payload["contractor_id"], at)
            else:
                self._set("contractor", branch_id, payload["contractor_id"], payload, at)
        self._snapshot_requested.discard(branch_id)
        result.accepted += 1

    def _touch(self, branch_id: str, now: datetime, seq: int) -> None:
        self._db.execute(
            "INSERT INTO branches (branch_id, last_seq, last_seen_at) VALUES (?, ?, ?) "
            "ON CONFLICT (branch_id) DO UPDATE SET last_seq = excluded.last_seq, last_seen_at = excluded.last_seen_at",
            (branch_id, seq, iso(now)),
        )

    # Every change of current state that alters a key is recorded in history.

    def _set(self, kind: str, branch_id: str, key: str, payload: dict[str, Any], at: datetime) -> None:
        if kind == "branch":
            row = self._db.execute("SELECT payload FROM branches WHERE branch_id = ?", (branch_id,)).fetchone()
        else:
            table, column = _TABLES[kind]
            row = self._db.execute(f"SELECT payload FROM {table} WHERE branch_id = ? AND {column} = ?", (branch_id, key)).fetchone()
        if row and row[0] is not None and json.loads(row[0]) == payload:
            return
        text = json.dumps(payload)
        if kind == "branch":
            self._db.execute("UPDATE branches SET payload = ? WHERE branch_id = ?", (text, branch_id))
        else:
            self._db.execute(
                f"INSERT INTO {table} (branch_id, {column}, payload) VALUES (?, ?, ?) "
                f"ON CONFLICT (branch_id, {column}) DO UPDATE SET payload = excluded.payload",
                (branch_id, key, text),
            )
        self._record(branch_id, kind, key, text, at)

    def _remove(self, kind: str, branch_id: str, key: str, at: datetime) -> None:
        table, column = _TABLES[kind]
        if self._db.execute(f"DELETE FROM {table} WHERE branch_id = ? AND {column} = ?", (branch_id, key)).rowcount:
            self._record(branch_id, kind, key, None, at)

    def _record(self, branch_id: str, kind: str, key: str, payload: str | None, at: datetime) -> None:
        # The times of one key never go backwards, so time order keeps the order in which changes were applied;
        # none falls before the start of the kept history.
        last = self._db.execute(
            "SELECT MAX(at) FROM changes WHERE branch_id = ? AND kind = ? AND key = ?", (branch_id, kind, key)
        ).fetchone()[0]
        self._db.execute(
            "INSERT INTO changes (branch_id, at, kind, key, payload) VALUES (?, ?, ?, ?, ?)",
            (branch_id, max(iso(at), self._from or "", last or ""), kind, key, payload),
        )

    def _replace(self, branch_id: str, snapshot: dict[str, Any], at: datetime) -> None:
        """Replace the Branch state; only the keys the snapshot changes or removes are recorded."""
        self._set("branch", branch_id, "", snapshot["branch"], at)
        for kind, items in (("agent", snapshot["agents"]), ("activity", snapshot["activities"]),
                            ("contractor", snapshot["contractors"])):
            table, column = _TABLES[kind]
            keep = {item[column] for item in items}
            for (key,) in self._db.execute(f"SELECT {column} FROM {table} WHERE branch_id = ?", (branch_id,)).fetchall():
                if key not in keep:
                    self._remove(kind, branch_id, key, at)
            for item in items:
                self._set(kind, branch_id, item[column], item, at)

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
        """Delete messages received before ``before``, and fold older history changes into the baseline."""
        cutoff = iso(before)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if self._from is not None and cutoff > self._from:
                    for branch_id, kind, key, payload in self._db.execute(_LATEST.format(op="<"), (cutoff,)).fetchall():
                        if payload is None:
                            self._db.execute("DELETE FROM baseline WHERE branch_id = ? AND kind = ? AND key = ?",
                                             (branch_id, kind, key))
                        else:
                            self._db.execute("INSERT OR REPLACE INTO baseline VALUES (?, ?, ?, ?)", (branch_id, kind, key, payload))
                    self._db.execute("DELETE FROM changes WHERE at < ?", (cutoff,))
                    self._start_history(cutoff)
                pruned = self._db.execute("DELETE FROM messages WHERE received_at < ?", (cutoff,)).rowcount
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            return pruned

    # History.

    def history_range(self, now: datetime) -> tuple[datetime | None, datetime]:
        """The kept history: from its start (None before the first message) to now."""
        with self._lock:
            return (_parse(self._from) if self._from else None), now

    def _state_rows(self, at: datetime, branch_id: str | None = None) -> history.StateRows:
        rows: history.StateRows = {}
        for b, kind, key, payload in self._db.execute("SELECT branch_id, kind, key, payload FROM baseline"):
            rows[(b, kind, key)] = json.loads(payload)
        for b, kind, key, payload in self._db.execute(_LATEST.format(op="<="), (iso(at),)).fetchall():
            if payload is None:
                rows.pop((b, kind, key), None)
            else:
                rows[(b, kind, key)] = json.loads(payload)
        return {k: v for k, v in rows.items() if branch_id is None or k[0] == branch_id}

    def _receipts(self, branch_id: str, start: datetime, end: datetime) -> list[tuple[datetime, float]]:
        """Messages received from a Branch, from the last one at or before ``start`` to ``end``, each with its window."""
        first = self._db.execute(
            "SELECT received_at FROM messages WHERE branch_id = ? AND received_at <= ? ORDER BY received_at DESC LIMIT 1",
            (branch_id, iso(start)),
        ).fetchone()
        since = first[0] if first else iso(start)
        beat = self._db.execute(
            "SELECT payload FROM messages WHERE branch_id = ? AND kind = 'heartbeat' AND received_at <= ? "
            "ORDER BY received_at DESC LIMIT 1",
            (branch_id, since),
        ).fetchone()
        interval = json.loads(beat[0])["interval"] if beat else DEFAULT_HEARTBEAT
        out: list[tuple[datetime, float]] = []
        for received, kind, payload in self._db.execute(
            "SELECT received_at, kind, payload FROM messages WHERE branch_id = ? AND received_at >= ? AND received_at <= ? "
            "ORDER BY received_at, seq",
            (branch_id, since, iso(end)),
        ):
            if kind == "heartbeat":
                interval = json.loads(payload)["interval"]
            out.append((_parse(received), interval * UNREACHABLE_FACTOR))
        return out

    def state_at(self, at: datetime) -> dict[str, Any]:
        """The state as of ``at``, in the shape of ``state``; reachability comes from the messages received."""
        with self._lock:
            rows = self._state_rows(at)
            branches = []
            for (branch_id, kind, _key), payload in sorted(rows.items()):
                if kind != "branch":
                    continue
                last = self._db.execute(
                    "SELECT seq, received_at FROM messages WHERE branch_id = ? AND received_at <= ? "
                    "ORDER BY received_at DESC, seq DESC LIMIT 1",
                    (branch_id, iso(at)),
                ).fetchone()
                branches.append({
                    "branch_id": branch_id,
                    "branch": payload,
                    "last_seq": last[0] if last else None,
                    "last_seen_at": last[1] if last else None,
                    "reachable": history.reachable_at(self._receipts(branch_id, at, at), at),
                })

            def of(kind: str) -> list[dict[str, Any]]:
                return [{**payload, "branch_id": b} for (b, k, _key), payload in sorted(rows.items()) if k == kind]

            return {"branches": branches, "agents": of("agent"), "activities": of("activity"), "contractors": of("contractor")}

    def _changes(self, start: datetime, end: datetime, branch_id: str | None) -> list[history.Change]:
        query = "SELECT branch_id, at, kind, key, payload FROM changes WHERE at > ? AND at <= ?"
        params: list[Any] = [iso(start), iso(end)]
        if branch_id is not None:
            query += " AND branch_id = ?"
            params.append(branch_id)
        return [(b, _parse(at), kind, key, json.loads(payload) if payload is not None else None)
                for b, at, kind, key, payload in self._db.execute(query + " ORDER BY at, id", params)]

    def _period(self, start: datetime, end: datetime, branch_id: str | None, now: datetime) -> tuple[
            datetime, datetime, history.StateRows, list[history.Change], dict[str, list[history.Interval]]] | None:
        """The part of [start, end] inside the kept history, its initial state, changes, and observed times."""
        if self._from is None:
            return None
        start, end = max(start, _parse(self._from)), min(end, now)
        if start >= end:
            return None
        initial = self._state_rows(start, branch_id)
        changes = self._changes(start, end, branch_id)
        ids = {b for b, _kind, _key in initial} | {c[0] for c in changes}
        observed = {b: history.observed(self._receipts(b, start, end), start, end) for b in sorted(ids)}
        return start, end, initial, changes, observed

    @staticmethod
    def _known(initial: history.StateRows, changes: list[history.Change]) -> history.StateRows:
        """The last payload of each key up to the end of the changes; removed keys keep their last one."""
        known = dict(initial)
        for b, _at, kind, key, payload in changes:
            if payload is not None:
                known[(b, kind, key)] = payload
        return known

    def changes(self, start: datetime, end: datetime, now: datetime, branch_id: str | None = None,
                limit: int = MAX_CHANGES) -> dict[str, Any]:
        """Activity, presence, and reachability transitions in (start, end], with the Employees and Branches named."""
        with self._lock:
            period = self._period(start, end, branch_id, now)
        if period is None:
            return {"from": iso(start), "to": iso(end), "changes": [], "truncated": False, "agents": [], "branches": []}
        start, end, initial, changes, observed = period
        items = history.transitions(initial, changes, observed, start, end)
        known = self._known(initial, changes)
        # The latest transitions are kept when the period holds more than the limit.
        truncated, items = len(items) > limit, items[-limit:]
        named = {(item["branch_id"], item["agent_id"]) for item in items if "agent_id" in item}
        return {
            "from": iso(start), "to": iso(end), "changes": items, "truncated": truncated,
            "agents": [{**p, "branch_id": b} for (b, kind, key), p in sorted(known.items()) if kind == "agent" and (b, key) in named],
            "branches": [{"branch_id": b, "branch": p} for (b, kind, _key), p in sorted(known.items()) if kind == "branch"],
        }

    def worklog(self, start: datetime, end: datetime, now: datetime, branch_id: str | None = None) -> dict[str, Any]:
        """Seconds per presence and activity state of each Employee within [start, end]."""
        with self._lock:
            period = self._period(start, end, branch_id, now)
        if period is None:
            return {"from": iso(start), "to": iso(end), "rows": [], "branches": []}
        start, end, initial, changes, observed = period
        known = self._known(initial, changes)
        return {
            "from": iso(start), "to": iso(end), "rows": history.work_log(initial, changes, observed, start, end),
            "branches": [{"branch_id": b, "branch": p} for (b, kind, _key), p in sorted(known.items()) if kind == "branch"],
        }


def now_utc() -> datetime:
    return datetime.now(UTC)
