"""HQ history computations over recorded state changes: reachability, transitions, and the work log.

The Store reads rows from SQLite; the functions here only compute. Times are aware UTC datetimes.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from itertools import islice
from datetime import UTC, datetime, timedelta
from typing import Any

from agentville.common.protocol import iso

STATES = ("working", "thinking", "waiting", "idle", "completed", "error", "limited", "unknown")
# Activity states whose entries the work log counts.
ENTRIES = {"waiting": "waits", "error": "errors", "limited": "limits"}

# (branch_id, kind, key) -> payload; kind is branch, agent, activity, or contractor.
StateRows = dict[tuple[str, str, str], dict[str, Any]]
# (branch_id, at, kind, key, payload or None for a removal), in recorded order. An activity payload may hold only
# its state and state_since, which is all these computations read of it.
Change = tuple[str, datetime, str, str, dict[str, Any] | None]
Interval = tuple[datetime, datetime]
# (state, state_since) of an activity.
Mark = tuple[Any, Any]
# The mark of an Employee's latest activity at or before the start of the period, also one removed since.
Prior = Callable[[str, str], Mark | None]
# (received_at in microseconds since the epoch, window in seconds), in received order.
Receipt = tuple[int, float]

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)


def micros(at: datetime) -> int:
    return (at - EPOCH) // _MICROSECOND


def observed(receipts: list[Receipt], start: datetime, end: datetime) -> list[Interval]:
    """Times within [start, end] covered by a received message and its window, merged and in order.

    ``receipts`` holds each message's receipt and window, the window being three heartbeat intervals as known after
    that message. As for the live reachable flag, a Branch is observed while the time since its last message is
    within the window known then, so each window ends at the next message.
    """
    first, last = micros(start), micros(end)
    out: list[list[int]] = []
    for i, (received, window) in enumerate(receipts):
        until = received + window_micros(window)
        if i + 1 < len(receipts):
            until = min(until, max(receipts[i + 1][0], received))
        a, b = max(received, first), min(until, last)
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(EPOCH + a * _MICROSECOND, EPOCH + b * _MICROSECOND) for a, b in out]


def overlap(intervals: list[Interval], a: datetime, b: datetime) -> float:
    """Seconds of [a, b) inside the intervals."""
    total = 0.0
    for start, end in islice(intervals, bisect_right(intervals, a, key=lambda interval: interval[1]), None):
        if start >= b:
            break
        total += (min(end, b) - max(start, a)).total_seconds()
    return total


def reachable_at(receipts: list[Receipt], at: datetime) -> bool:
    when = micros(at)
    last = [(received, window) for received, window in receipts if received <= when]
    return bool(last) and when - last[-1][0] <= window_micros(last[-1][1])


def window_micros(window: float) -> int:
    return round(window * 1_000_000)


def _on_duty(agent: dict[str, Any] | None) -> bool:
    return agent is not None and agent.get("presence") == "on_duty"


def _activity_state(activity: dict[str, Any] | None) -> str:
    state = activity.get("state") if activity else None
    return state if state in STATES else "unknown"


def _no_prior(_branch_id: str, _key: str) -> Mark | None:
    return None


def _mark(activity: dict[str, Any] | None) -> Mark | None:
    return (activity.get("state"), activity.get("state_since")) if activity else None


def transitions(initial: StateRows, changes: Iterable[Change], observed_by_branch: dict[str, list[Interval]],
                start: datetime, end: datetime, limit: int, prior: Prior = _no_prior) -> tuple[list[dict[str, Any]], bool]:
    """The latest ``limit`` activity, presence, and Branch reachability transitions in (start, end], in time order,
    and whether there were more.

    An activity transition is a new state or a new ``state_since``; changes of tool or workload alone are not. Both
    are compared with the last known activity of the Employee, so an activity removed and restored is not new;
    ``prior`` gives it for an Employee without an activity at the start.
    """
    presence = {(b, key): p.get("presence") for (b, kind, key), p in initial.items() if kind == "agent"}
    marks = {(b, key): _mark(p) for (b, kind, key), p in initial.items() if kind == "activity"}
    lifecycles = {(b, key): p for (b, kind, key), p in initial.items() if kind == "lifecycle"}
    # Changes come in time order, so only the latest ``limit`` of them can be among the latest overall.
    out: deque[dict[str, Any]] = deque(maxlen=limit)
    total = 0
    for branch_id, at, kind, key, payload in changes:
        if kind == "lifecycle" and payload is not None:
            previous = lifecycles.get((branch_id, key))
            lifecycles[(branch_id, key)] = payload
            if previous is not None and previous.get("revision") != payload.get("revision"):
                out.append({"at": at, "kind": "lifecycle", "branch_id": branch_id,
                            "target_kind": payload["kind"], "target_id": payload["id"],
                            "alias": payload["alias"], "closed": payload["closed"]})
                total += 1
        if kind == "agent" and payload is not None and payload.get("presence") != presence.get((branch_id, key)):
            out.append({"at": at, "kind": "presence", "branch_id": branch_id, "agent_id": key,
                        "presence": payload.get("presence")})
            total += 1
        if kind == "activity" and (branch_id, key) not in marks:
            marks[(branch_id, key)] = prior(branch_id, key)
        if kind == "activity" and payload is not None and _mark(payload) != marks[(branch_id, key)]:
            out.append({"at": at, "kind": "activity", "branch_id": branch_id, "agent_id": key,
                        "state": payload.get("state"), "state_since": payload.get("state_since")})
            total += 1
        if kind == "agent":
            presence[(branch_id, key)] = payload.get("presence") if payload else None
        elif kind == "activity" and payload is not None:
            marks[(branch_id, key)] = _mark(payload)
    items = list(out)
    for branch_id, intervals in observed_by_branch.items():
        for a, b in intervals:
            if a > start:
                items.append({"at": a, "kind": "reachability", "branch_id": branch_id, "reachable": True})
                total += 1
            if b < end:
                items.append({"at": b, "kind": "reachability", "branch_id": branch_id, "reachable": False})
                total += 1
    items.sort(key=lambda item: item["at"])
    # Times are formatted only for the transitions returned.
    kept = items[-limit:] if limit else []
    for item in kept:
        item["at"] = iso(item["at"])
    return kept, total > limit


@dataclass
class _Colleague:
    """One Employee's running totals while the work log walks the changes."""

    at: datetime
    agent: dict[str, Any] | None = None
    activity: dict[str, Any] | None = None
    last_agent: dict[str, Any] | None = None
    # (state, state_since) of the last known activity, kept while the activity is removed.
    mark: Mark | None = None
    seconds: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    # Waited seconds per wait, keyed by its state_since; a wait interrupted by a Branch gap stays one wait.
    waits: dict[Any, float] = field(default_factory=lambda: defaultdict(float))

    def close(self, until: datetime, intervals: list[Interval]) -> None:
        if until > self.at and _on_duty(self.agent):
            seen = overlap(intervals, self.at, until)
            state = _activity_state(self.activity)
            self.seconds["on_duty"] += seen
            self.seconds[state] += seen
            self.seconds["unobserved"] += (until - self.at).total_seconds() - seen
            if state == "waiting":
                self.waits[self.activity.get("state_since") if self.activity else None] += seen
        self.at = max(self.at, until)


def work_log(initial: StateRows, changes: Iterable[Change], observed_by_branch: dict[str, list[Interval]],
             start: datetime, end: datetime, prior: Prior = _no_prior) -> list[dict[str, Any]]:
    """Seconds per presence and activity state of each Employee within [start, end].

    Time in a Branch gap counts as unobserved, not as on duty, for Employees last known on duty.
    Entries into waiting, error, and limited are counted when they occur within the range: a state or
    ``state_since`` that differs from the Employee's last known activity, also across a removal of the activity
    (``prior`` gives it for an Employee without an activity at the start).
    """
    colleagues: dict[tuple[str, str], _Colleague] = {}
    # Employees whose last known activity is settled: present at the start, or looked up with ``prior``.
    settled: set[tuple[str, str]] = set()

    def colleague(branch_id: str, key: str) -> _Colleague:
        if (branch_id, key) not in colleagues:
            colleagues[(branch_id, key)] = _Colleague(start)
        return colleagues[(branch_id, key)]

    for (branch_id, kind, key), payload in initial.items():
        if kind == "agent":
            c = colleague(branch_id, key)
            c.agent = c.last_agent = payload
        elif kind == "activity":
            c = colleague(branch_id, key)
            c.activity, c.mark = payload, _mark(payload)
            settled.add((branch_id, key))
    for branch_id, at, kind, key, payload in changes:
        if kind not in ("agent", "activity"):
            continue
        c = colleague(branch_id, key)
        c.close(at, observed_by_branch.get(branch_id, []))
        if kind == "agent":
            c.agent = payload
            c.last_agent = payload or c.last_agent
            continue
        if (branch_id, key) not in settled:
            c.mark = prior(branch_id, key)
            settled.add((branch_id, key))
        state = payload.get("state") if payload else None
        if state in ENTRIES and _mark(payload) != c.mark:
            c.counts[ENTRIES[state]] += 1
        c.activity = payload
        c.mark = _mark(payload) or c.mark
    rows = []
    for (branch_id, agent_id), c in colleagues.items():
        c.close(end, observed_by_branch.get(branch_id, []))
        if not (c.seconds["on_duty"] or c.seconds["unobserved"] or c.counts) or c.last_agent is None:
            continue
        agent = c.last_agent
        rows.append({
            "branch_id": branch_id,
            "agent_id": agent_id,
            "project_id": agent.get("project_id"),
            "project_alias": agent.get("project_alias"),
            "provider": agent.get("provider"),
            "seat": agent.get("seat"),
            "alias": agent.get("alias"),
            "seconds": {name: round(c.seconds[name], 3) for name in ("on_duty", *STATES, "unobserved")},
            "waits": c.counts["waits"],
            "longest_wait": round(max(c.waits.values(), default=0.0), 3),
            "errors": c.counts["errors"],
            "limits": c.counts["limits"],
        })
    rows.sort(key=lambda r: (r["branch_id"], r["project_alias"] or "", r["provider"] or "", r["seat"] or 0, r["agent_id"]))
    return rows
