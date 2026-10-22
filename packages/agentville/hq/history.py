"""HQ history computations over recorded state changes: reachability, transitions, and the work log.

The Store reads rows from SQLite; the functions here only compute. Times are aware UTC datetimes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from agentville.common.protocol import iso

STATES = ("working", "thinking", "waiting", "idle", "completed", "error", "limited", "unknown")
# Activity states whose entries the work log counts.
ENTRIES = {"waiting": "waits", "error": "errors", "limited": "limits"}

# (branch_id, kind, key) -> payload; kind is branch, agent, activity, or contractor.
StateRows = dict[tuple[str, str, str], dict[str, Any]]
# (branch_id, at, kind, key, payload or None for a removal), in recorded order.
Change = tuple[str, datetime, str, str, dict[str, Any] | None]
Interval = tuple[datetime, datetime]


def observed(receipts: list[tuple[datetime, float]], start: datetime, end: datetime) -> list[Interval]:
    """Times within [start, end] covered by a received message and its window, merged and in order.

    ``receipts`` holds (received_at, window seconds) in received order, the window being three heartbeat intervals
    as known after that message. As for the live reachable flag, a Branch is observed while the time since its
    last message is within the window known then, so each window ends at the next message.
    """
    out: list[Interval] = []
    for i, (received, window) in enumerate(receipts):
        until = received + timedelta(seconds=window)
        if i + 1 < len(receipts):
            until = min(until, max(receipts[i + 1][0], received))
        a, b = max(received, start), min(until, end)
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def overlap(intervals: list[Interval], a: datetime, b: datetime) -> float:
    """Seconds of [a, b) inside the intervals."""
    total = 0.0
    for start, end in intervals:
        if end <= a:
            continue
        if start >= b:
            break
        total += (min(end, b) - max(start, a)).total_seconds()
    return total


def reachable_at(receipts: list[tuple[datetime, float]], at: datetime) -> bool:
    last = [(received, window) for received, window in receipts if received <= at]
    return bool(last) and (at - last[-1][0]).total_seconds() <= last[-1][1]


def _on_duty(agent: dict[str, Any] | None) -> bool:
    return agent is not None and agent.get("presence") == "on_duty"


def _activity_state(activity: dict[str, Any] | None) -> str:
    state = activity.get("state") if activity else None
    return state if state in STATES else "unknown"


def _mark(activity: dict[str, Any] | None) -> tuple[Any, Any] | None:
    return (activity.get("state"), activity.get("state_since")) if activity else None


def transitions(initial: StateRows, changes: list[Change], observed_by_branch: dict[str, list[Interval]],
                start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Activity, presence, and Branch reachability transitions in (start, end], in time order.

    An activity transition is a new state or a new ``state_since``; changes of tool or workload alone are not.
    """
    presence = {(b, key): p.get("presence") for (b, kind, key), p in initial.items() if kind == "agent"}
    marks = {(b, key): _mark(p) for (b, kind, key), p in initial.items() if kind == "activity"}
    out: list[dict[str, Any]] = []
    for branch_id, at, kind, key, payload in changes:
        if kind == "agent" and payload is not None and payload.get("presence") != presence.get((branch_id, key)):
            out.append({"at": iso(at), "kind": "presence", "branch_id": branch_id, "agent_id": key,
                        "presence": payload.get("presence")})
        if kind == "activity" and payload is not None and _mark(payload) != marks.get((branch_id, key)):
            out.append({"at": iso(at), "kind": "activity", "branch_id": branch_id, "agent_id": key,
                        "state": payload.get("state"), "state_since": payload.get("state_since")})
        if kind == "agent":
            presence[(branch_id, key)] = payload.get("presence") if payload else None
        elif kind == "activity":
            marks[(branch_id, key)] = _mark(payload)
    for branch_id, intervals in observed_by_branch.items():
        for a, b in intervals:
            if a > start:
                out.append({"at": iso(a), "kind": "reachability", "branch_id": branch_id, "reachable": True})
            if b < end:
                out.append({"at": iso(b), "kind": "reachability", "branch_id": branch_id, "reachable": False})
    out.sort(key=lambda item: item["at"])
    return out


@dataclass
class _Colleague:
    """One Employee's running totals while the work log walks the changes."""

    at: datetime
    agent: dict[str, Any] | None = None
    activity: dict[str, Any] | None = None
    last_agent: dict[str, Any] | None = None
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


def work_log(initial: StateRows, changes: list[Change], observed_by_branch: dict[str, list[Interval]],
             start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Seconds per presence and activity state of each Employee within [start, end].

    Time in a Branch gap counts as unobserved, not as on duty, for Employees last known on duty.
    Entries into waiting, error, and limited are counted when they occur within the range.
    """
    colleagues: dict[tuple[str, str], _Colleague] = {}

    def colleague(branch_id: str, key: str) -> _Colleague:
        if (branch_id, key) not in colleagues:
            colleagues[(branch_id, key)] = _Colleague(start)
        return colleagues[(branch_id, key)]

    for (branch_id, kind, key), payload in initial.items():
        if kind == "agent":
            c = colleague(branch_id, key)
            c.agent = c.last_agent = payload
        elif kind == "activity":
            colleague(branch_id, key).activity = payload
    for branch_id, at, kind, key, payload in changes:
        if kind not in ("agent", "activity"):
            continue
        c = colleague(branch_id, key)
        c.close(at, observed_by_branch.get(branch_id, []))
        if kind == "agent":
            c.agent = payload
            c.last_agent = payload or c.last_agent
            continue
        state = payload.get("state") if payload else None
        if state in ENTRIES and _mark(payload) != _mark(c.activity):
            c.counts[ENTRIES[state]] += 1
        c.activity = payload
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
