"""HQ storage: applies Branch messages to per-Branch current state in SQLite (WAL), and keeps its history."""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from agentville.common.protocol import iso
from agentville.hq import history

UNREACHABLE_FACTOR = 3
DEFAULT_HEARTBEAT = 30
MAX_CLOCK_LEAD = timedelta(minutes=5)
MAX_CHANGES = 5000
# History checkpoints are written at whole multiples of this interval since the epoch (UTC).
CHECKPOINT_INTERVAL = timedelta(hours=1)
# Bytes of write-ahead log above which HQ holds back new history reads until the log is checkpointed and truncated;
# also the size the log file is cut back to after a checkpoint resets it (journal_size_limit).
WAL_LIMIT = 32 * 1024 * 1024
# Passive checkpoint passes before the truncating one, and the frames that may remain for it.
WAL_PASSES = 5
WAL_REMAINDER = 256

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
CREATE TABLE IF NOT EXISTS checkpoints (
    at TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS checkpoint_keys (
    at TEXT NOT NULL,
    branch_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    change_id INTEGER,
    PRIMARY KEY (at, branch_id, kind, key)
);
CREATE TABLE IF NOT EXISTS meta (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Current-state table and key column of each change kind; a Branch payload lives in ``branches``.
_TABLES = {"agent": ("agents", "agent_id"), "activity": ("activities", "agent_id"), "contractor": ("contractors", "contractor_id")}
# The latest change of each key after a time (lower bound "at > ?" or none) and before (op "<") or at or before
# (op "<=") another; equal times keep recording order.
_LATEST = """
SELECT branch_id, kind, key, payload FROM (
    SELECT branch_id, kind, key, payload,
           ROW_NUMBER() OVER (PARTITION BY branch_id, kind, key ORDER BY at DESC, id DESC) AS position
    FROM changes WHERE {lower} at {op} ?
) WHERE position = 1
"""
# The keys of a checkpoint with their payloads; a key without a change id holds its baseline payload.
_CHECKPOINT = """
SELECT k.branch_id, k.kind, k.key, COALESCE(c.payload, b.payload)
FROM checkpoint_keys k
LEFT JOIN changes c ON c.id = k.change_id
LEFT JOIN baseline b ON k.change_id IS NULL AND b.branch_id = k.branch_id AND b.kind = k.kind AND b.key = k.key
WHERE k.at = ?
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
    return datetime.fromisoformat(ts)


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _boundary(at: datetime) -> datetime:
    """The latest checkpoint time at or before ``at``."""
    return at - (at - _EPOCH) % CHECKPOINT_INTERVAL


def _boundary_before(at: str) -> str:
    """The latest checkpoint time strictly before ``at``."""
    return iso(_boundary(_parse(at) - timedelta(microseconds=1)))


class Store:
    def __init__(self, path: str, now: datetime | None = None, wal_limit: int = WAL_LIMIT) -> None:
        self._path = path
        self._wal_limit = wal_limit
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(f"PRAGMA journal_size_limit = {int(wal_limit)}")
        # Ingest never copies the log into the database itself; ``_shrink_wal`` does, outside the lock.
        self._db.execute("PRAGMA wal_autocheckpoint = 0")
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
        # The latest history checkpoint; changes recorded at or before it also update the checkpoints from their time on.
        self._checkpoint: str | None = self._db.execute("SELECT MAX(at) FROM checkpoints").fetchone()[0]
        if self._from is not None:
            # A database without checkpoints gets them now rather than during the first ingest.
            self._db.execute("BEGIN IMMEDIATE")
            self._write_checkpoints(now or now_utc())
            self._db.execute("COMMIT")
        self._lock = threading.Lock()
        # Read-only connections for history queries, which never take the lock; each serves one query at a time.
        self._readers: queue.SimpleQueue[sqlite3.Connection] = queue.SimpleQueue()
        self._opened: list[sqlite3.Connection] = []
        self._opened_lock = threading.Lock()
        # Reader gate: a read transaction keeps the log frames it may need, so a log grown past the limit is
        # checkpointed while new history reads wait and the running ones finish (``_shrink_wal``).
        self._gate = threading.Condition()
        self._reads = 0
        self._draining = False
        self._shrinker: threading.Thread | None = None
        self.totals = IngestResult()
        # Branches asked for a snapshot after a stale one, with no message applied since.
        self._snapshot_requested: set[str] = set()
        # Branches heard since this HQ started; any other is not reported reachable.
        self._heard: set[str] = set()
        # Branches whose snapshot was applied since the last ``observe``.
        self._resynced: set[str] = set()

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
        shrinker = self._shrinker
        if shrinker is not None:
            shrinker.join()
        with self._lock, self._opened_lock:
            for reader in self._opened:
                reader.close()
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._db.close()

    @contextmanager
    def _reading(self) -> Iterator[sqlite3.Connection]:
        """A read-only connection in one read transaction: a consistent view while ingest goes on (WAL)."""
        with self._gate:
            while self._draining:
                self._gate.wait()
            self._reads += 1
        try:
            try:
                db = self._readers.get_nowait()
            except queue.Empty:
                db = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
                db.execute("PRAGMA query_only = ON")
                with self._opened_lock:
                    self._opened.append(db)
            db.execute("BEGIN")
            try:
                yield db
            finally:
                db.execute("COMMIT")
                self._readers.put(db)
        finally:
            with self._gate:
                self._reads -= 1
                self._gate.notify_all()

    def _check_wal(self) -> None:
        """Start shrinking the write-ahead log once it has grown past the limit; called after ingest commits."""
        try:
            size = os.path.getsize(self._path + "-wal")
        except OSError:
            return
        if size <= self._wal_limit:
            return
        with self._gate:
            if self._shrinker is not None and self._shrinker.is_alive():
                return
            self._shrinker = threading.Thread(target=self._shrink_wal, name="agentville-wal", daemon=True)
            self._shrinker.start()

    def _shrink_wal(self) -> None:
        """Hold back new history reads, let the running ones finish, then checkpoint and truncate the log.

        Overlapping read transactions otherwise always keep some log frames in use, and the log never restarts.
        Ingest and the live state do not pass the gate. Passive checkpoints copy the log while ingest goes on;
        the truncating one runs under the store lock and has only the frames written since left to copy.
        """
        with self._gate:
            self._draining = True
            while self._reads:
                self._gate.wait()
        try:
            db = sqlite3.connect(self._path, isolation_level=None)
            try:
                # Passive checkpoints copy the log without blocking ingest; each pass copies what ingest wrote
                # during the previous one, so the remainder becomes small.
                for _ in range(WAL_PASSES):
                    _busy, frames, copied = db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
                    if frames - copied <= WAL_REMAINDER:
                        break
            finally:
                db.close()
            # The writer copies the rest and empties the log under the store lock, so ingest waits on the lock
            # for a short time instead of retrying a busy database.
            with self._lock:
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass  # the next ingest past the limit tries again
        finally:
            with self._gate:
                self._draining = False
                self._gate.notify_all()

    # Ingest.

    def ingest(self, branch_id: str, messages: list[dict[str, Any]], now: datetime) -> IngestResult:
        """Apply messages from one Branch in seq order. Caller validates the schema."""
        result = IngestResult()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            resynced, kept = False, (self._from, self._checkpoint)
            try:
                if self._from is None:
                    self._start_history(iso(now))
                self._write_checkpoints(now)
                for message in sorted(messages, key=lambda m: m["seq"]):
                    if message["branch_id"] != branch_id:
                        raise ValueError("branch_id mismatch")
                    resynced = self._apply(message, now, result) or resynced
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                self._from, self._checkpoint = kept
                raise
            self._heard.add(branch_id)
            if resynced:
                self._resynced.add(branch_id)
            self.totals.accepted += result.accepted
            self.totals.duplicates += result.duplicates
            self.totals.stale += result.stale
            self.totals.need_snapshot = self.totals.need_snapshot or result.need_snapshot
        self._check_wal()
        return result

    def _apply(self, message: dict[str, Any], now: datetime, result: IngestResult) -> bool:
        """Apply one message; True when it was a snapshot applied."""
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
                    return False
                if row[1] is not None and _parse(message["sent_at"]) < _parse(row[1]):
                    if branch_id not in self._snapshot_requested:
                        # A delayed snapshot from before the current numbering, or a reset
                        # Branch whose clock is behind; a fresh snapshot settles either case.
                        self._snapshot_requested.add(branch_id)
                        result.stale += 1
                        result.need_snapshot = True
                        return False
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
            return False
        row = self._db.execute("SELECT last_seq FROM branches WHERE branch_id = ?", (branch_id,)).fetchone()
        last_seq = row[0] if row else None
        if kind != "snapshot":
            if last_seq is None:
                result.need_snapshot = True
            elif seq < last_seq:
                result.stale += 1
                self._touch(branch_id, now, last_seq)
                return False
            elif seq != last_seq + 1:
                result.need_snapshot = True
        self._touch(branch_id, now, seq)
        sent = self._db.execute("SELECT last_sent_at FROM branches WHERE branch_id = ?", (branch_id,)).fetchone()[0]
        sent_at = _parse(message["sent_at"])
        if sent_at <= now + MAX_CLOCK_LEAD and (sent is None or clock_reset or _parse(sent) < sent_at):
            self._db.execute("UPDATE branches SET last_sent_at = ? WHERE branch_id = ?", (message["sent_at"], branch_id))
        payload = message["payload"]
        # The history time of a change is the time of the fact, never later than its receipt by HQ.
        at = min(_parse(message["event_at"]), now)
        if kind == "snapshot":
            self._replace(branch_id, payload, at)
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
        return kind == "snapshot"

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
        stamp = max(iso(at), self._from or "", last or "")
        change_id = self._db.execute(
            "INSERT INTO changes (branch_id, at, kind, key, payload) VALUES (?, ?, ?, ?, ?)",
            (branch_id, stamp, kind, key, payload),
        ).lastrowid
        # A change at or before a checkpoint is the latest of its key there: no change of the key is later.
        if self._checkpoint is not None and stamp <= self._checkpoint:
            for (checkpoint,) in self._db.execute("SELECT at FROM checkpoints WHERE at >= ?", (stamp,)).fetchall():
                if payload is None:
                    self._db.execute("DELETE FROM checkpoint_keys WHERE at = ? AND branch_id = ? AND kind = ? AND key = ?",
                                     (checkpoint, branch_id, kind, key))
                else:
                    self._db.execute("INSERT OR REPLACE INTO checkpoint_keys VALUES (?, ?, ?, ?, ?)",
                                     (checkpoint, branch_id, kind, key, change_id))

    def _write_checkpoints(self, now: datetime) -> None:
        """Write the checkpoints due up to ``now``: the state at each interval boundary that changes crossed.

        Boundaries without a change since the previous checkpoint are skipped, except the latest one. The
        caller holds the write transaction.
        """
        if self._from is None:
            return
        target = iso(_boundary(now))
        if target <= (self._checkpoint or self._from):
            return
        # Each key's latest change id, None for its baseline payload.
        keys: dict[tuple[str, str, str], int | None] = {}
        if self._checkpoint is None:
            for b, kind, key in self._db.execute("SELECT branch_id, kind, key FROM baseline"):
                keys[(b, kind, key)] = None
            rows = self._db.execute("SELECT id, branch_id, kind, key, payload IS NULL, at FROM changes "
                                    "WHERE at <= ? ORDER BY at, id", (target,))
        else:
            for b, kind, key, change_id in self._db.execute(
                    "SELECT branch_id, kind, key, change_id FROM checkpoint_keys WHERE at = ?", (self._checkpoint,)):
                keys[(b, kind, key)] = change_id
            rows = self._db.execute("SELECT id, branch_id, kind, key, payload IS NULL, at FROM changes "
                                    "WHERE at > ? AND at <= ? ORDER BY at, id", (self._checkpoint, target))
        # The first boundary after the last checkpoint written; a change after it starts a new checkpoint.
        following = iso(_boundary(_parse(self._checkpoint or self._from)) + CHECKPOINT_INTERVAL)
        for change_id, b, kind, key, removed, at in rows:
            if at > following:
                boundary = _boundary_before(at)
                self._store_checkpoint(boundary, keys)
                following = iso(_parse(boundary) + CHECKPOINT_INTERVAL)
            if removed:
                keys.pop((b, kind, key), None)
            else:
                keys[(b, kind, key)] = change_id
        self._store_checkpoint(target, keys)

    def _store_checkpoint(self, at: str, keys: dict[tuple[str, str, str], int | None]) -> None:
        self._db.execute("INSERT INTO checkpoints VALUES (?)", (at,))
        self._db.executemany("INSERT INTO checkpoint_keys VALUES (?, ?, ?, ?, ?)",
                             [(at, b, kind, key, change_id) for (b, kind, key), change_id in keys.items()])
        self._checkpoint = at

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
            return self._state(now)

    def observe(self, now: datetime) -> tuple[dict[str, Any], frozenset[str], frozenset[str]]:
        """The current state, the Branches heard, and the Branches resynced since the previous call, read together.

        A snapshot's resync is taken by the first call that sees its state, whichever ingest or loop makes it.
        """
        with self._lock:
            resynced, self._resynced = frozenset(self._resynced), set()
            return self._state(now), frozenset(self._heard), resynced

    def _state(self, now: datetime) -> dict[str, Any]:
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
        """Delete messages received before ``before``, and fold older history into the baseline."""
        cutoff = iso(before)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            kept = (self._from, self._checkpoint)
            try:
                if self._from is not None and cutoff > self._from:
                    # The baseline becomes the state just before the cutoff. A checkpoint key whose change is
                    # folded takes the baseline payload, which is that change's.
                    baseline = _state_text(self._db, cutoff, "<")
                    self._db.execute("UPDATE checkpoint_keys SET change_id = NULL "
                                     "WHERE change_id IN (SELECT id FROM changes WHERE at < ?)", (cutoff,))
                    self._db.execute("DELETE FROM baseline")
                    self._db.executemany("INSERT INTO baseline VALUES (?, ?, ?, ?)",
                                         [(b, kind, key, payload) for (b, kind, key), payload in baseline.items()])
                    self._db.execute("DELETE FROM checkpoint_keys WHERE at < ?", (cutoff,))
                    self._db.execute("DELETE FROM checkpoints WHERE at < ?", (cutoff,))
                    self._db.execute("DELETE FROM changes WHERE at < ?", (cutoff,))
                    self._start_history(cutoff)
                    if self._checkpoint is not None and self._checkpoint < cutoff:
                        self._checkpoint = None
                pruned = self._db.execute("DELETE FROM messages WHERE received_at < ?", (cutoff,)).rowcount
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                self._from, self._checkpoint = kept
                raise
            return pruned

    # History. Queries run on read-only connections without the lock, so they never delay ingest or live state.
    # Their cost follows the period: the state at its start comes from the latest checkpoint at or before it.

    def history_range(self, now: datetime) -> tuple[datetime | None, datetime]:
        """The kept history: from its start (None before the first message) to now."""
        start = self._from
        return (_parse(start) if start else None), now

    def state_at(self, at: datetime) -> dict[str, Any]:
        """The state as of ``at``, in the shape of ``state``; reachability comes from the messages received."""
        with self._reading() as db:
            rows = _state_rows(db, at)
            branches = []
            for (branch_id, kind, _key), payload in sorted(rows.items()):
                if kind != "branch":
                    continue
                last = db.execute(
                    "SELECT seq, received_at FROM messages WHERE branch_id = ? AND received_at <= ? "
                    "ORDER BY received_at DESC, seq DESC LIMIT 1",
                    (branch_id, iso(at)),
                ).fetchone()
                branches.append({
                    "branch_id": branch_id,
                    "branch": payload,
                    "last_seq": last[0] if last else None,
                    "last_seen_at": last[1] if last else None,
                    "reachable": history.reachable_at(_receipts(db, branch_id, at, at), at),
                })

        def of(kind: str) -> list[dict[str, Any]]:
            return [{**payload, "branch_id": b} for (b, k, _key), payload in sorted(rows.items()) if k == kind]

        return {"branches": branches, "agents": of("agent"), "activities": of("activity"), "contractors": of("contractor")}

    def _period(self, start: datetime, end: datetime, branch_id: str | None, now: datetime,
                compute: Callable[[datetime, datetime, history.StateRows, Iterator[history.Change],
                                   dict[str, list[history.Interval]], history.Prior], Any],
                ) -> tuple[datetime, datetime, Any, history.StateRows] | None:
        """Run ``compute`` over the part of [start, end] inside the kept history: its initial state, its changes (read
        while ``compute`` consumes them), the observed times of each Branch, and the lookup of an Employee's last
        activity mark at or before the start. Returns the clipped period, the result, and the last payload of each
        key, which removed keys keep; None when no part is inside.
        """
        with self._reading() as db:
            row = db.execute("SELECT value FROM meta WHERE name = 'history_from'").fetchone()
            if row is None:
                return None
            start, end = max(start, _parse(row[0])), min(end, now)
            if start >= end:
                return None
            initial = _state_rows(db, start, branch_id)
            ids = {b for b, _kind, _key in initial} | _changed_branches(db, start, end, branch_id)
            observed = {b: history.observed(_receipts(db, b, start, end), start, end) for b in sorted(ids)}
            known = dict(initial)

            def changes() -> Iterator[history.Change]:
                for change in _changes(db, start, end, branch_id):
                    if change[4] is not None and change[2] != "activity":
                        known[(change[0], change[2], change[3])] = change[4]
                    yield change

            def prior(branch: str, key: str) -> history.Mark | None:
                row = db.execute(
                    "SELECT json_extract(payload, '$.state'), json_extract(payload, '$.state_since') FROM changes "
                    "WHERE branch_id = ? AND kind = 'activity' AND key = ? AND at <= ? AND payload IS NOT NULL "
                    "ORDER BY at DESC, id DESC LIMIT 1", (branch, key, iso(start))).fetchone()
                if row is not None:
                    return row[0], row[1]
                # Before any kept change the baseline holds it, unless it was removed before the kept history.
                base = db.execute(
                    "SELECT json_extract(payload, '$.state'), json_extract(payload, '$.state_since') FROM baseline "
                    "WHERE branch_id = ? AND kind = 'activity' AND key = ?", (branch, key)).fetchone()
                return (base[0], base[1]) if base is not None else None

            result = compute(start, end, initial, changes(), observed, prior)
        return start, end, result, known

    def changes(self, start: datetime, end: datetime, now: datetime, branch_id: str | None = None,
                limit: int = MAX_CHANGES) -> dict[str, Any]:
        """Activity, presence, and reachability transitions in (start, end], with the Employees and Branches named.

        A period entirely outside the kept history, or after now, gives null ``from`` and ``to`` and empty lists.
        """
        period = self._period(start, end, branch_id, now,
                              lambda s, e, initial, changes, observed, prior: history.transitions(
                                  initial, changes, observed, s, e, limit, prior))
        if period is None:
            return {"from": None, "to": None, "changes": [], "truncated": False, "agents": [], "branches": []}
        start, end, (items, truncated), known = period
        named = {(item["branch_id"], item["agent_id"]) for item in items if "agent_id" in item}
        return {
            "from": iso(start), "to": iso(end), "changes": items, "truncated": truncated,
            "agents": [{**p, "branch_id": b} for (b, kind, key), p in sorted(known.items()) if kind == "agent" and (b, key) in named],
            "branches": [{"branch_id": b, "branch": p} for (b, kind, _key), p in sorted(known.items()) if kind == "branch"],
        }

    def worklog(self, start: datetime, end: datetime, now: datetime, branch_id: str | None = None) -> dict[str, Any]:
        """Seconds per presence and activity state of each Employee within [start, end]; empty as ``changes``."""
        period = self._period(start, end, branch_id, now,
                              lambda s, e, initial, changes, observed, prior: history.work_log(
                                  initial, changes, observed, s, e, prior))
        if period is None:
            return {"from": None, "to": None, "rows": [], "branches": []}
        start, end, rows, known = period
        return {
            "from": iso(start), "to": iso(end), "rows": rows,
            "branches": [{"branch_id": b, "branch": p} for (b, kind, _key), p in sorted(known.items()) if kind == "branch"],
        }


# History reads take the connection, so the writer (prune) and the read-only connections share them.

def _state_text(db: sqlite3.Connection, at: str, op: str = "<=") -> dict[tuple[str, str, str], str]:
    """Each key's payload text at (op "<=") or just before (op "<") a time: the latest checkpoint before it, and
    the latest change of each key since."""
    row = db.execute(f"SELECT MAX(at) FROM checkpoints WHERE at {op} ?", (at,)).fetchone()
    rows: dict[tuple[str, str, str], str] = {}
    if row[0] is None:
        source, params, lower = "SELECT branch_id, kind, key, payload FROM baseline", (), ""
    else:
        source, params, lower = _CHECKPOINT, (row[0],), "at > ? AND"
    for b, kind, key, payload in db.execute(source, params):
        rows[(b, kind, key)] = payload
    for b, kind, key, payload in db.execute(_LATEST.format(lower=lower, op=op), (*params, at)).fetchall():
        if payload is None:
            rows.pop((b, kind, key), None)
        else:
            rows[(b, kind, key)] = payload
    return rows


def _state_rows(db: sqlite3.Connection, at: datetime, branch_id: str | None = None) -> history.StateRows:
    return {k: json.loads(v) for k, v in _state_text(db, iso(at)).items() if branch_id is None or k[0] == branch_id}


def _receipts(db: sqlite3.Connection, branch_id: str, start: datetime, end: datetime) -> list[history.Receipt]:
    """Messages received from a Branch, from the last one at or before ``start`` to ``end``, each with its window."""
    first = db.execute(
        "SELECT received_at FROM messages WHERE branch_id = ? AND received_at <= ? ORDER BY received_at DESC LIMIT 1",
        (branch_id, iso(start)),
    ).fetchone()
    since = first[0] if first else iso(start)
    beat = db.execute(
        "SELECT payload FROM messages WHERE branch_id = ? AND kind = 'heartbeat' AND received_at <= ? "
        "ORDER BY received_at DESC LIMIT 1",
        (branch_id, since),
    ).fetchone()
    interval = json.loads(beat[0])["interval"] if beat else DEFAULT_HEARTBEAT
    out: list[history.Receipt] = []
    # received_at is always written by HQ as YYYY-MM-DDTHH:MM:SS.mmmZ; SQLite turns it into microseconds.
    for received, payload in db.execute(
        "SELECT (CAST(strftime('%s', received_at) AS INTEGER) * 1000 + CAST(substr(received_at, 21, 3) AS INTEGER)) * 1000, "
        "CASE kind WHEN 'heartbeat' THEN payload END FROM messages "
        "WHERE branch_id = ? AND received_at >= ? AND received_at <= ? ORDER BY received_at, seq",
        (branch_id, since, iso(end)),
    ):
        if payload is not None:
            interval = json.loads(payload)["interval"]
        out.append((received, interval * UNREACHABLE_FACTOR))
    return out


def _changed_branches(db: sqlite3.Connection, start: datetime, end: datetime, branch_id: str | None) -> set[str]:
    query = "SELECT DISTINCT branch_id FROM changes WHERE at > ? AND at <= ?"
    params: list[Any] = [iso(start), iso(end)]
    if branch_id is not None:
        query += " AND branch_id = ?"
        params.append(branch_id)
    return {b for (b,) in db.execute(query, params)}


def _changes(db: sqlite3.Connection, start: datetime, end: datetime, branch_id: str | None) -> Iterator[history.Change]:
    """Branch, agent, and activity changes in (start, end] in recorded order. Of an activity only its state and
    state_since are read, in SQLite, so the payload is not parsed here."""
    query = ("SELECT branch_id, at, kind, key, CASE WHEN kind = 'activity' THEN NULL ELSE payload END, payload IS NULL, "
             "CASE WHEN kind = 'activity' THEN json_extract(payload, '$.state') END, "
             "CASE WHEN kind = 'activity' THEN json_extract(payload, '$.state_since') END "
             "FROM changes WHERE at > ? AND at <= ? AND kind IN ('branch', 'agent', 'activity')")
    params: list[Any] = [iso(start), iso(end)]
    if branch_id is not None:
        query += " AND branch_id = ?"
        params.append(branch_id)
    for b, at, kind, key, payload, removed, state, since in db.execute(query + " ORDER BY at, id", params):
        if removed:
            yield b, _parse(at), kind, key, None
        elif kind == "activity":
            yield b, _parse(at), kind, key, {"state": state, "state_since": since}
        else:
            yield b, _parse(at), kind, key, json.loads(payload)


def now_utc() -> datetime:
    return datetime.now(UTC)
