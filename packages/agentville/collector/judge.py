"""Judge: turns observations into Employee assignment and activity state.

Emits protocol payloads (``agent`` and ``activity``) for the Sender.
"""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from agentville.collector.project import Project
from agentville.common.observations import Kind, Observation, SessionStatus, ShiftKey, Source
from agentville.common.protocol import iso

WORKLOAD_WINDOW = timedelta(minutes=5)
LEAVE_AFTER = timedelta(days=7)


class ProjectResolver(Protocol):
    def resolve(self, cwd: str) -> Project: ...


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
    tool: str | None = None
    tool_times: deque[datetime] = field(default_factory=deque)


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
    sessions: set[str] = field(default_factory=set)
    account_alias: str | None = None

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
    ) -> None:
        self._resolver = resolver
        self._emit = emit
        self._new_id = new_id
        self._leave_after = leave_after
        self._condition_for = condition_for
        self.agents: list[Agent] = []
        self._by_shift: dict[ShiftKey, Agent] = {}

    def apply(self, obs: Observation) -> None:
        if obs.kind is Kind.PROCESS_STARTED:
            self._on_started(obs)
            return
        agent = self._by_shift.get(obs.shift)
        if agent is None or agent.instance is None:
            return
        inst = agent.instance
        match obs.kind:
            case Kind.PROCESS_EXITED:
                self._on_exited(agent, obs)
            case Kind.SESSION_STARTED:
                inst.session_id = obs.data.get("session_id")
                if inst.session_id:
                    agent.sessions.add(inst.session_id)
                self._emit_activity(agent, obs.event_at)
            case Kind.SESSION_STATUS:
                status = obs.data.get("status")
                if status == SessionStatus.WAITING:
                    self._set(agent, obs, "waiting", "high")
                elif status == SessionStatus.IDLE:
                    inst.tool = None
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
                inst.tool = None
                if inst.state == "working":
                    self._emit_activity(agent, obs.event_at)
            case Kind.TURN_COMPLETED:
                inst.tool = None
                self._set(agent, obs, "completed", "high", force=True)
                self._set(agent, obs, "idle", "high", force=True)
            case Kind.AGENT_ERROR:
                self._set(agent, obs, "error", "high", force=True)
            case Kind.LIMIT_REACHED:
                self._set(agent, obs, "limited", "high", force=True)
            case Kind.MODEL_CHANGED:
                agent.model = obs.data.get("model")
                agent.settings = dict(obs.data.get("settings") or {})
                self._emit_agent(agent, obs.event_at)

    def _on_started(self, obs: Observation) -> None:
        data = obs.data
        project = self._resolver.resolve(data.get("cwd", ""))
        runtime = data.get("runtime") or {}
        location = runtime.get("location")
        agent = self._assign(project, obs.shift.provider, data.get("session_id"), location, obs.event_at)
        agent.location = location
        if data.get("account_alias"):
            agent.account_alias = data["account_alias"]
        agent.presence_since = obs.event_at
        agent.instance = Instance(self._new_id(), obs.shift, obs.event_at, runtime, state_since=obs.event_at)
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
        taken = {a.seat for a in pool}
        seat = next(n for n in range(1, len(taken) + 2) if n not in taken)
        agent = Agent(self._new_id(), project, provider, seat, at)
        self.agents.append(agent)
        return agent

    def _on_exited(self, agent: Agent, obs: Observation) -> None:
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
        inst.source = obs.source
        inst.confidence = confidence
        self._emit_activity(agent, obs.event_at)

    def _emit_agent(self, agent: Agent, at: datetime) -> None:
        self._emit("agent", at, self.agent_payload(agent, at))

    def _emit_activity(self, agent: Agent, at: datetime) -> None:
        self._emit("activity", at, self.activity_payload(agent, at))

    def agent_payload(self, agent: Agent, now: datetime) -> dict[str, Any]:
        inst = agent.instance
        return {
            "agent_id": agent.agent_id,
            "project_id": agent.project.project_id,
            "project_alias": agent.project.alias,
            "provider": agent.provider,
            "seat": agent.seat,
            "alias": None,
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

    def snapshot(self, now: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Agent payloads for all Employees and activity payloads for those on duty."""
        agents = [self.agent_payload(a, now) for a in self.agents]
        activities = [self.activity_payload(a, now) for a in self.agents if a.instance is not None]
        return agents, activities

    def activity_payload(self, agent: Agent, now: datetime) -> dict[str, Any]:
        inst = agent.instance
        assert inst is not None
        while inst.tool_times and now - inst.tool_times[0] > WORKLOAD_WINDOW:
            inst.tool_times.popleft()
        return {
            "agent_id": agent.agent_id,
            "instance_id": inst.instance_id,
            "session_id": inst.session_id,
            "state": inst.state,
            "state_since": iso(inst.state_since or inst.started_at),
            "source": inst.source.value,
            "confidence": inst.confidence,
            "tool": inst.tool,
            "reset_at": None,
            "workload": len(inst.tool_times),
        }
