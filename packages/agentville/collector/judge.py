"""Judge: turns observations into Employee assignment and activity state.

Emits protocol payloads (``agent``, ``activity``, and ``contractor``) for the Sender.
"""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Protocol

from agentville.collector.project import Project
from agentville.collector.process import ProcessTable
from agentville.common.observations import Kind, Observation, SessionStatus, ShiftKey, Source
from agentville.common.protocol import iso

WORKLOAD_WINDOW = timedelta(minutes=5)
LEAVE_AFTER = timedelta(days=7)
MAX_SESSIONS = 20

_CONFIDENCE = ("low", "medium", "high")
# Contractor status reported by Adapters, mapped to activity states.
_SUBAGENT_STATES = {"active": "working", "waiting": "waiting", "idle": "idle", "error": "error"}


class ProjectResolver(Protocol):
    def resolve(self, cwd: str) -> Project: ...


@dataclass
class Contractor:
    contractor_id: str
    provider: str
    state: str
    state_since: datetime
    tool: str | None = None
    origin: str = "in_process"


@dataclass
class Instance:
    instance_id: str
    shift: ShiftKey
    started_at: datetime
    runtime: dict[str, Any]
    session_id: str | None = None
    state: str = "unknown"
    state_since: datetime | None = None
    source: Source = Source.PROCESS
    confidence: str = "low"
    # Upper bound of confidence the shift's sources support (process.started ``max_confidence``).
    max_confidence: str = "high"
    tool: str | None = None
    reset_at: datetime | None = None
    tool_times: deque[datetime] = field(default_factory=deque)
    reported_workload: int | None = None
    contractors: dict[str, Contractor] = field(default_factory=dict)


@dataclass
class Agent:
    agent_id: str
    project: Project
    provider: str
    seat: int
    presence_since: datetime
    instance: Instance | None = None
    model: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    location: str | None = None
    sessions: list[str] = field(default_factory=list)
    account_alias: str | None = None
    reported_presence: str | None = None

    def remember(self, session_id: str) -> None:
        if session_id in self.sessions:
            self.sessions.remove(session_id)
        self.sessions.append(session_id)
        del self.sessions[:-MAX_SESSIONS]

    def presence(self, now: datetime, leave_after: timedelta) -> str:
        if self.instance is not None:
            return "on_duty"
        return "on_leave" if now - self.presence_since >= leave_after else "off_duty"


class Judge:
    def __init__(
        self,
        resolver: ProjectResolver,
        emit: Callable[[str, datetime, dict[str, Any]], None],
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
        leave_after: timedelta = LEAVE_AFTER,
        condition_for: Callable[[str, str | None, dict[str, Any]], str] = lambda provider, model, settings: "normal",
        save: Callable[[list[dict[str, Any]]], None] = lambda records: None,
        alias_for: Callable[[str], str | None] = lambda agent_id: None,
        proc_root: str = "/proc",
    ) -> None:
        self._resolver = resolver
        self._emit = emit
        self._new_id = new_id
        self._leave_after = leave_after
        self._condition_for = condition_for
        self._save = save
        self._alias_for = alias_for
        self.agents: list[Agent] = []
        self._by_shift: dict[ShiftKey, Agent] = {}
        self._processes = ProcessTable(proc_root)
        self._shift_processes: dict[ShiftKey, tuple[int, str]] = {}
        self._child_parents: dict[ShiftKey, tuple[Agent, str]] = {}

    def apply_batch(self, observations: list[Observation]) -> None:
        """Resolve process ancestry before assigning new Employees in one poll."""
        self._processes.refresh()
        groups: dict[ShiftKey, list[Observation]] = {}
        for obs in observations:
            groups.setdefault(obs.shift, []).append(obs)
            if obs.kind is Kind.PROCESS_STARTED:
                process = self._processes.processes.get(obs.data.get("pid"))
                if process is not None and str(obs.data.get("proc_start")) == process.start:
                    self._shift_processes[obs.shift] = process.identity
        bindings: dict[int, list[ShiftKey]] = {}
        for shift, identity in self._shift_processes.items():
            process = self._processes.processes.get(identity[0])
            if process is not None and process.identity == identity:
                bindings.setdefault(process.pid, []).append(shift)

        def order(key: ShiftKey) -> int:
            identity = self._shift_processes.get(key)
            process = self._processes.processes.get(identity[0]) if identity else None
            depth = len(list(self._processes.ancestors(process))) if process else 0
            return depth

        ending = {key for key, batch in groups.items() if key in self._by_shift
                  and any(o.kind is Kind.PROCESS_EXITED for o in batch)}
        for obs in observations:
            if obs.shift in ending:
                self.apply(obs)
                if obs.kind is Kind.PROCESS_EXITED:
                    self._shift_processes.pop(obs.shift, None)
        starts = [obs for obs in observations if obs.kind is Kind.PROCESS_STARTED and obs.shift not in ending]
        for obs in sorted(starts, key=lambda o: order(o.shift)):
            parent_shift = self._process_parent(obs.shift, bindings)
            if parent_shift is not None:
                obs = replace(obs, data={**obs.data, "parent_shift": parent_shift})
            self.apply(obs)
        if observations:
            at = max(obs.observed_at for obs in observations)
            for shift in sorted(list(self._by_shift), key=order):
                if shift in self._child_parents:
                    continue
                parent_shift = self._process_parent(shift, bindings)
                if parent_shift is not None:
                    self._reclassify_child(shift, parent_shift, at)
        for obs in observations:
            if obs.shift not in ending and obs.kind is not Kind.PROCESS_STARTED:
                self.apply(obs)
                if obs.kind is Kind.PROCESS_EXITED:
                    self._shift_processes.pop(obs.shift, None)

    def _process_parent(self, shift: ShiftKey, bindings: dict[int, list[ShiftKey]]) -> ShiftKey | None:
        identity = self._shift_processes.get(shift)
        process = self._processes.processes.get(identity[0]) if identity else None
        if process is None or process.identity != identity:
            return None
        for ancestor in self._processes.ancestors(process):
            candidates = bindings.get(ancestor.pid, [])
            if len(candidates) == 1 and candidates[0] in self._by_shift:
                return candidates[0]
        return None

    def _reclassify_child(self, shift: ShiftKey, parent_shift: ShiftKey, at: datetime) -> None:
        """Preserve Employee history while moving its live shift and Contractors to the root."""
        agent, parent = self._by_shift[shift], self._by_shift[parent_shift]
        owner = self._child_parents.get(parent_shift)
        root = owner[0] if owner else parent
        inst = agent.instance
        if inst is None or root.instance is None:
            return
        descendants = {key: (self._by_shift[key], sub_id)
                       for key, (previous_root, sub_id) in self._child_parents.items() if previous_root is agent}
        contractors = dict(inst.contractors)
        self._on_exited(agent, Observation(Kind.PROCESS_EXITED, shift, at, at, Source.PROCESS))
        sub_id = f"process:{shift.provider}:{shift.native_id}"
        self._by_shift[shift] = replace(agent, instance=replace(inst, contractors={}))
        self._child_parents[shift] = (root, sub_id)
        contractor_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentville:contractor:{root.instance.instance_id}:{sub_id}"))
        root.instance.contractors[sub_id] = Contractor(contractor_id, shift.provider, inst.state, at,
                                                      inst.tool, origin="child_process")
        self._emit_activity(self._by_shift[shift], at)
        process_ids = {child_sub_id for _, child_sub_id in descendants.values()}
        for key, contractor in contractors.items():
            target = key if key in process_ids or any(key.startswith(prefix + "/") for prefix in process_ids) else f"{sub_id}/{key}"
            contractor_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentville:contractor:{root.instance.instance_id}:{target}"))
            moved = replace(contractor, contractor_id=contractor_id)
            root.instance.contractors[target] = moved
            self._emit("contractor", at, self.contractor_payload(root.instance, moved, "hired"))
        for child_shift, (child, child_sub_id) in descendants.items():
            self._by_shift[child_shift] = child
            self._child_parents[child_shift] = (root, child_sub_id)

    def apply(self, obs: Observation) -> None:
        if obs.kind is Kind.PROCESS_STARTED:
            self._on_started(obs)
            return
        agent = self._by_shift.get(obs.shift)
        if agent is None or agent.instance is None:
            return
        inst = agent.instance
        owner = self._child_parents.get(obs.shift)
        if owner is not None and obs.kind in (Kind.SUBAGENT_STARTED, Kind.SUBAGENT_STATUS, Kind.SUBAGENT_ENDED):
            root, sub_id = owner
            if root.instance is not None:
                self.apply(replace(obs, shift=root.instance.shift,
                                   data={**obs.data, "subagent_id": f"{sub_id}/{obs.data.get('subagent_id')}"}))
            return
        match obs.kind:
            case Kind.PROCESS_EXITED:
                self._on_exited(agent, obs)
            case Kind.SESSION_STARTED:
                inst.session_id = obs.data.get("session_id")
                if owner is not None:
                    return
                if inst.session_id:
                    # Only the colleague who last worked on a session keeps it, for seat rule 1.
                    for other in self.agents:
                        if other is not agent and inst.session_id in other.sessions:
                            other.sessions.remove(inst.session_id)
                    agent.remember(inst.session_id)
                    self._save(self.records())
                self._emit_activity(agent, obs.event_at)
            case Kind.SESSION_STATUS:
                status = obs.data.get("status")
                if status == SessionStatus.WAITING:
                    self._set(agent, obs, "waiting", "high")
                elif status == SessionStatus.IDLE:
                    inst.tool = None
                    if inst.state not in ("error", "limited"):
                        self._set(agent, obs, "idle", "high")
                elif status == SessionStatus.ACTIVE:
                    if inst.state not in ("working", "thinking"):
                        self._set(agent, obs, "working", "medium")
                else:
                    self._set(agent, obs, "unknown", "low")
            case Kind.INPUT_REQUESTED:
                self._set(agent, obs, "waiting", "high")
            case Kind.TURN_STARTED | Kind.GENERATION_ENDED:
                if inst.state != "waiting":
                    self._set(agent, obs, "working", "medium")
            case Kind.GENERATION_STARTED:
                if inst.state != "waiting":
                    self._set(agent, obs, "thinking", "high")
            case Kind.TOOL_STARTED:
                inst.tool = obs.data.get("tool")
                inst.tool_times.append(obs.event_at)
                if inst.state != "waiting":
                    self._set(agent, obs, "working", "high", force=True)
            case Kind.TOOL_FINISHED:
                inst.tool = obs.data.get("remaining_tool")
                if inst.state == "working":
                    self._emit_activity(agent, obs.event_at)
            case Kind.TURN_COMPLETED:
                inst.tool = None
                # An error or limit lasts until normal activity resumes, not until the turn ends.
                if inst.state not in ("error", "limited"):
                    self._set(agent, obs, "completed", "high", force=True)
                    self._set(agent, obs, "idle", "high", force=True)
            case Kind.AGENT_ERROR:
                self._set(agent, obs, "error", "high", force=True)
            case Kind.LIMIT_REACHED:
                inst.reset_at = obs.data.get("reset_at")
                self._set(agent, obs, "limited", "high", force=True)
            case Kind.LIMIT_CLEARED:
                if inst.state == "limited":
                    self._set(agent, obs, "idle", "high")
            case Kind.SUBAGENT_STARTED | Kind.SUBAGENT_STATUS:
                self._on_subagent(inst, obs)
            case Kind.SUBAGENT_ENDED:
                contractor = inst.contractors.pop(obs.data.get("subagent_id"), None)
                if contractor is not None:
                    self._emit("contractor", obs.event_at, self.contractor_payload(inst, contractor, "ended"))
            case Kind.MODEL_CHANGED:
                agent.model = obs.data.get("model")
                agent.settings = dict(obs.data.get("settings") or {})
                self._emit_agent(agent, obs.event_at)

    def _on_started(self, obs: Observation) -> None:
        if obs.shift in self._by_shift:
            return
        data = obs.data
        parent = self._by_shift.get(data.get("parent_shift"))
        if parent is not None and parent.instance is not None:
            owner = self._child_parents.get(parent.instance.shift)
            root = owner[0] if owner is not None else parent
            if root.instance is None:
                return
            sub_id = f"process:{obs.shift.provider}:{obs.shift.native_id}"
            child = Agent(self._new_id(), root.project, obs.shift.provider, 0, obs.event_at)
            child.instance = Instance(self._new_id(), obs.shift, obs.event_at, {}, state_since=obs.event_at)
            self._by_shift[obs.shift] = child
            self._child_parents[obs.shift] = (root, sub_id)
            contractor_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentville:contractor:{root.instance.instance_id}:{sub_id}"))
            root.instance.contractors[sub_id] = Contractor(contractor_id, obs.shift.provider, "unknown", obs.event_at,
                                                          origin="child_process")
            self._emit_activity(child, obs.event_at)
            return
        project = self._resolver.resolve(data.get("cwd", ""))
        runtime = data.get("runtime") or {}
        location = runtime.get("location")
        agent = self._assign(project, obs.shift.provider, data.get("session_id"), location, obs.event_at)
        agent.location = location
        if data.get("account_alias"):
            agent.account_alias = data["account_alias"]
        agent.presence_since = obs.event_at
        agent.instance = Instance(self._new_id(), obs.shift, obs.event_at, runtime, state_since=obs.event_at)
        if data.get("max_confidence") in _CONFIDENCE:
            agent.instance.max_confidence = data["max_confidence"]
        self._by_shift[obs.shift] = agent
        self._emit_agent(agent, obs.event_at)

    def _assign(
        self, project: Project, provider: str, session_id: str | None, location: str | None, at: datetime
    ) -> Agent:
        pool = [
            a for a in self.agents if a.project.project_id == project.project_id and a.provider == provider
        ]
        free = [a for a in pool if a.instance is None]
        if session_id:
            for agent in free:
                if session_id in agent.sessions:
                    return agent
        if location:
            for agent in free:
                if agent.location == location:
                    return agent
        if free:
            return min(free, key=lambda a: a.seat)
        # Seats are unique per provider on the Branch, so "<provider> <seat>" names one Employee.
        taken = {a.seat for a in self.agents if a.provider == provider}
        seat = next(n for n in range(1, len(taken) + 2) if n not in taken)
        agent = Agent(self._new_id(), project, provider, seat, at)
        self.agents.append(agent)
        return agent

    def _on_subagent(self, inst: Instance, obs: Observation) -> None:
        sub_id = obs.data.get("subagent_id")
        if not isinstance(sub_id, str):
            return
        contractor = inst.contractors.get(sub_id)
        if contractor is None and obs.kind is not Kind.SUBAGENT_STARTED:
            return
        state = _SUBAGENT_STATES.get(obs.data.get("status") or "active", "unknown")
        tool = obs.data.get("tool") if state == "working" else None
        if contractor is None:
            # Stable per parent instance; the provider's subagent id itself is not sent.
            contractor_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentville:contractor:{inst.instance_id}:{sub_id}"))
            contractor = Contractor(contractor_id, obs.data.get("provider") or obs.shift.provider, state, obs.event_at, tool)
            inst.contractors[sub_id] = contractor
        elif (contractor.state, contractor.tool) == (state, tool):
            return
        else:
            if contractor.state != state:
                contractor.state_since = obs.event_at
            contractor.state, contractor.tool = state, tool
        self._emit("contractor", obs.event_at, self.contractor_payload(inst, contractor, "hired"))

    def _on_exited(self, agent: Agent, obs: Observation) -> None:
        assert agent.instance is not None
        owner = self._child_parents.pop(obs.shift, None)
        if owner is not None:
            root, sub_id = owner
            if root.instance is not None:
                for key in list(root.instance.contractors):
                    if key == sub_id or key.startswith(sub_id + "/"):
                        contractor = root.instance.contractors.pop(key)
                        self._emit("contractor", obs.event_at, self.contractor_payload(root.instance, contractor, "ended"))
            self._by_shift.pop(obs.shift, None)
            return
        # A Contractor's lifetime does not exceed its parent's.
        for contractor in agent.instance.contractors.values():
            self._emit("contractor", obs.event_at, self.contractor_payload(agent.instance, contractor, "ended"))
        for shift, (root, _) in list(self._child_parents.items()):
            if root is agent:
                self._child_parents.pop(shift)
                self._by_shift.pop(shift, None)
        self._by_shift.pop(obs.shift, None)
        agent.instance = None
        agent.presence_since = obs.event_at
        self._emit_agent(agent, obs.event_at)

    def _set(self, agent: Agent, obs: Observation, state: str, confidence: str, force: bool = False) -> None:
        inst = agent.instance
        assert inst is not None
        if inst.state == state and not force:
            return
        inst.state = state
        inst.state_since = obs.event_at
        if state != "limited":
            inst.reset_at = None
        inst.source = obs.source
        inst.confidence = min(confidence, inst.max_confidence, key=_CONFIDENCE.index)
        self._emit_activity(agent, obs.event_at)

    def _emit_agent(self, agent: Agent, at: datetime) -> None:
        if agent.instance is not None and agent.instance.shift in self._child_parents:
            return
        payload = self.agent_payload(agent, at)
        agent.reported_presence = payload["presence"]
        self._emit("agent", at, payload)
        self._save(self.records())

    def records(self) -> list[dict[str, Any]]:
        """Employee identities and history kept across restarts; no activity or paths."""
        return [
            {
                "agent_id": a.agent_id,
                "project_id": a.project.project_id,
                "project_alias": a.project.alias,
                "provider": a.provider,
                "seat": a.seat,
                "presence_since": iso(a.presence_since),
                "on_duty": a.instance is not None,
                "location": a.location,
                "sessions": a.sessions,
                "account_alias": a.account_alias,
                "model": a.model,
                "settings": a.settings,
            }
            for a in self.agents
        ]

    def restore(self, records: list[dict[str, Any]], now: datetime) -> None:
        """Reload Employees as off duty; one on duty at the last save is off duty from ``now``."""
        for r in records:
            try:
                since = now if r.get("on_duty") else datetime.fromisoformat(r["presence_since"].replace("Z", "+00:00"))
                agent = Agent(str(r["agent_id"]), Project(str(r["project_id"]), str(r["project_alias"])),
                              str(r["provider"]), int(r["seat"]), since)
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
            agent.location = r.get("location") if isinstance(r.get("location"), str) else None
            agent.sessions = [s for s in r.get("sessions") or [] if isinstance(s, str)][-MAX_SESSIONS:]
            agent.account_alias = r.get("account_alias") if isinstance(r.get("account_alias"), str) else None
            agent.model = r.get("model") if isinstance(r.get("model"), str) else None
            agent.settings = r["settings"] if isinstance(r.get("settings"), dict) else {}
            self.agents.append(agent)
        # Rosters written before seats were unique per provider on the Branch: the first holder keeps a seat,
        # later duplicates take the lowest free ones.
        taken: set[tuple[str, int]] = set()
        duplicates = []
        for agent in self.agents:
            if (agent.provider, agent.seat) in taken:
                duplicates.append(agent)
            taken.add((agent.provider, agent.seat))
        for agent in duplicates:
            agent.seat = next(n for n in range(1, len(self.agents) + 2) if (agent.provider, n) not in taken)
            taken.add((agent.provider, agent.seat))

    def refresh_presence(self, now: datetime) -> None:
        """Emit Employees whose time-based presence changed (off duty to on leave)."""
        for agent in self.agents:
            if agent.reported_presence is not None and agent.presence(now, self._leave_after) != agent.reported_presence:
                self._emit_agent(agent, max(now, agent.presence_since + self._leave_after))

    def refresh_workload(self, now: datetime) -> None:
        """Emit activity for on-duty Employees whose workload changed only by the passing of time."""
        for agent in self.agents:
            inst = agent.instance
            if inst is not None and inst.reported_workload is not None and self._workload(inst, now) != inst.reported_workload:
                self._emit_activity(agent, now)

    @staticmethod
    def _workload(inst: Instance, now: datetime) -> int:
        while inst.tool_times and now - inst.tool_times[0] > WORKLOAD_WINDOW:
            inst.tool_times.popleft()
        return len(inst.tool_times)

    def _emit_activity(self, agent: Agent, at: datetime) -> None:
        inst = agent.instance
        owner = self._child_parents.get(inst.shift) if inst else None
        if owner is not None:
            root, sub_id = owner
            contractor = root.instance.contractors.get(sub_id) if root.instance else None
            if contractor is not None and inst is not None:
                if contractor.state != inst.state:
                    contractor.state_since = at
                contractor.state, contractor.tool = inst.state, inst.tool if inst.state == "working" else None
                self._emit("contractor", at, self.contractor_payload(root.instance, contractor, "hired"))
            return
        self._emit("activity", at, self.activity_payload(agent, at))

    def agent_payload(self, agent: Agent, now: datetime) -> dict[str, Any]:
        inst = agent.instance
        return {
            "agent_id": agent.agent_id,
            "project_id": agent.project.project_id,
            "project_alias": agent.project.alias,
            "provider": agent.provider,
            "seat": agent.seat,
            "alias": self._alias_for(agent.agent_id),
            "presence": agent.presence(now, self._leave_after),
            "presence_since": iso(agent.presence_since),
            "account_alias": agent.account_alias,
            "model": agent.model,
            "settings": agent.settings,
            "condition": self._condition_for(agent.provider, agent.model, agent.settings),
            "instance": None
            if inst is None
            else {"instance_id": inst.instance_id, "started_at": iso(inst.started_at), "runtime": inst.runtime},
        }

    def snapshot(self, now: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Agent payloads for all Employees, and activity and Contractor payloads for those on duty."""
        agents = [self.agent_payload(a, now) for a in self.agents]
        for agent, payload in zip(self.agents, agents, strict=True):
            agent.reported_presence = payload["presence"]
        on_duty = [a for a in self.agents if a.instance is not None]
        activities = [self.activity_payload(a, now) for a in on_duty]
        contractors = [
            self.contractor_payload(a.instance, c, "hired") for a in on_duty if a.instance for c in a.instance.contractors.values()
        ]
        return agents, activities, contractors

    @staticmethod
    def contractor_payload(inst: Instance, contractor: Contractor, status: str) -> dict[str, Any]:
        return {
            "contractor_id": contractor.contractor_id,
            "parent_instance_id": inst.instance_id,
            "provider": contractor.provider,
            "origin": contractor.origin,
            "status": status,
            "state": contractor.state,
            "state_since": iso(contractor.state_since),
            "tool": contractor.tool,
        }

    def activity_payload(self, agent: Agent, now: datetime) -> dict[str, Any]:
        inst = agent.instance
        assert inst is not None
        inst.reported_workload = self._workload(inst, now)
        return {
            "agent_id": agent.agent_id,
            "instance_id": inst.instance_id,
            "session_id": inst.session_id,
            "state": inst.state,
            "state_since": iso(inst.state_since or inst.started_at),
            "source": inst.source.value,
            "confidence": inst.confidence,
            "tool": inst.tool,
            "reset_at": iso(inst.reset_at) if inst.reset_at and inst.state == "limited" else None,
            "workload": inst.reported_workload,
        }
