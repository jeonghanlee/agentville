"""Generator for synthetic Codex fixtures.

Usage: python tests/fixtures/codex/generate.py tests/fixtures
"""

import json
import os
import sys
from datetime import UTC, datetime, timedelta

import yaml

VERSION = "0.163.0"
BASE = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
HOME = "/home/user/.codex"
CWD = "/home/user/repo"


def iso(t):
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def t(seconds):
    return BASE + timedelta(seconds=seconds)


def rollout_rel(thread_id):
    return f"sessions/2026/01/01/rollout-2026-01-01T00-00-00-{thread_id}.jsonl"


def thread(thread_id, status, with_path=True, parent=None, thread_source="user", source="vscode"):
    return {
        "agentNickname": None,
        "agentRole": None,
        "canAcceptDirectInput": True,
        "cliVersion": VERSION,
        "createdAt": int(BASE.timestamp()),
        "cwd": CWD,
        "daybreakEnabled": False,
        "environments": [],
        "ephemeral": False,
        "extra": {},
        "forkedFromId": None,
        "gitInfo": {"branch": "master", "sha": "<sha>", "originUrl": "https://github.com/example/repo"},
        "historyMode": "paginated",
        "id": thread_id,
        "model": "model-b",
        "modelProvider": "openai",
        "name": None,
        "originator": "codex-tui",
        "parentThreadId": parent,
        "path": f"{HOME}/{rollout_rel(thread_id)}" if with_path else None,
        "preview": "<text>",
        "projectId": "<project-id>",
        "reasoningEffort": "medium",
        "recencyAt": int(BASE.timestamp()),
        "section": None,
        "sectionEnteredAt": None,
        "sessionId": thread_id,
        "source": source,
        "status": status,
        "threadSource": thread_source,
        "turns": [],
        "updatedAt": int(BASE.timestamp()),
    }


IDLE = {"type": "idle"}
ACTIVE = {"type": "active", "activeFlags": []}
APPROVAL = {"type": "active", "activeFlags": ["waitingOnApproval"]}
NOT_LOADED = {"type": "notLoaded"}


class Scenario:
    def __init__(self, root, sid, title):
        self.dir = os.path.join(root, "codex", VERSION, sid)
        os.makedirs(os.path.join(self.dir, "appserver"), exist_ok=True)
        self.scenario = sid
        self.title = title
        self.timeline = []
        self.expect = []
        self.logs = {}
        self.files = 0
        self.ordinal = 0

    def _write(self, label, payload):
        self.files += 1
        name = f"appserver/{self.files:03d}-{label}.json"
        with open(os.path.join(self.dir, name), "w") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        return name

    def load(self, at, data):
        """Thread already loaded when the Collector first connects; later threads use thread/started."""
        self.timeline.append({"at": iso(at), "op": "appserver_thread", "file": self._write("thread", data)})

    def notify(self, at, method, params):
        name = self._write(method.replace("/", "-"), {"method": method, "params": params})
        self.timeline.append({"at": iso(at), "op": "appserver_notify", "file": name})

    def status(self, at, thread_id, status):
        self.notify(at, "thread/status/changed", {"threadId": thread_id, "status": status})

    def disconnect(self, at):
        self.timeline.append({"at": iso(at), "op": "appserver_disconnect"})

    def rollout(self, at, thread_id, records):
        rel = rollout_rel(thread_id)
        log = self.logs.setdefault(rel, [])
        start = len(log)
        for rtype, payload in records:
            self.ordinal += 1
            log.append({"timestamp": iso(at), "ordinal": self.ordinal, "type": rtype, "payload": payload})
        self.timeline.append({"at": iso(at), "op": "log_append", "path": rel,
                              "file": f"logs/{os.path.basename(rel)}", "lines": [start, len(log)]})

    def check(self, **kw):
        kw["after"] = len(self.timeline)
        self.expect.append(kw)

    def save(self):
        if self.logs:
            os.makedirs(os.path.join(self.dir, "logs"), exist_ok=True)
        for rel, log in self.logs.items():
            with open(os.path.join(self.dir, "logs", os.path.basename(rel)), "w") as fh:
                for record in log:
                    fh.write(json.dumps(record) + "\n")
        with open(os.path.join(self.dir, "timeline.jsonl"), "w") as fh:
            for op in self.timeline:
                fh.write(json.dumps(op) + "\n")
        meta = {"provider": "codex", "version": VERSION, "scenario": self.scenario,
                "title": self.title, "expect": self.expect}
        with open(os.path.join(self.dir, "meta.yaml"), "w") as fh:
            yaml.safe_dump(meta, fh, sort_keys=False, default_flow_style=None, width=120)


def session_meta(thread_id):
    return ("session_meta", {"id": thread_id, "session_id": thread_id, "timestamp": iso(BASE), "cwd": CWD,
                             "git": {"branch": "master", "commit_hash": "<sha>", "repository_url": "https://github.com/example/repo"},
                             "cli_version": VERSION, "model_provider": "openai", "originator": "codex-tui",
                             "source": "vscode", "thread_source": "user", "context_window": 1,
                             "history_mode": "paginated", "runtime_workspace_roots": [CWD],
                             "creator_account_id": "account-1", "creator_user_id": "user-1",
                             "base_instructions": "<text>"})


def task_started(turn):
    return ("event_msg", {"type": "task_started", "turn_id": turn, "root_turn_id": turn, "started_at": 0,
                          "model_context_window": 1, "collaboration_mode_kind": "default", "turn_attribution": None})


def task_complete(turn, error=None):
    return ("event_msg", {"type": "task_complete", "turn_id": turn, "root_turn_id": turn, "started_at": 0,
                          "completed_at": 1, "duration_ms": 1000, "time_to_first_token_ms": 100,
                          "last_agent_message": "<text>", "error": error})


def turn_context(turn, model="model-b", effort="medium"):
    return ("turn_context", {"turn_id": turn, "root_turn_id": turn, "cwd": CWD, "model": model, "effort": effort,
                             "summary": "auto", "approval_policy": "on-request", "sandbox_policy": {"type": "workspace-write"}})


def call(call_id, name="exec_command"):
    return ("response_item", {"type": "function_call", "name": name, "namespace": None, "arguments": "<tool-input>", "call_id": call_id})


def output(call_id):
    return ("response_item", {"type": "function_call_output", "call_id": call_id, "output": "<tool-output>"})


def reasoning():
    return ("response_item", {"type": "reasoning", "summary": [], "encrypted_content": "<secret>"})


def window(used, minutes, resets_after):
    return {"used_percent": used, "window_minutes": minutes, "resets_at": int((BASE + resets_after).timestamp())}


def token_count(used=10.0, weekly=None):
    limits = {"limit_id": "<id>", "plan_type": "<plan>", "primary": window(used, 300, timedelta(hours=5))}
    if weekly is not None:
        limits["secondary"] = window(weekly, 10080, timedelta(days=7))
    limits["credits"] = {"balance": "<balance>", "has_credits": True}
    return ("event_msg", {"type": "token_count", "info": {}, "rate_limits": limits})


TA = "019a0000-0000-7000-8000-00000000000a"
TB = "019a0000-0000-7000-8000-00000000000b"
TS = "019a0000-0000-7000-8000-0000000000aa"
TT = "019a0000-0000-7000-8000-0000000000ab"
TX = "019a0000-0000-7000-8000-0000000000ff"


def s01(root):
    s = Scenario(root, "S01", "One turn with a shell command")
    s.load(t(0), thread(TA, IDLE)); s.check(presence="on_duty", seat=1, state="idle")
    s.rollout(t(0), TA, [session_meta(TA)])
    s.status(t(1), TA, ACTIVE); s.check(state="working")
    s.rollout(t(1), TA, [turn_context("turn-1"), task_started("turn-1"), reasoning(), call("call_1")])
    s.check(state="working", tool="exec_command")
    s.rollout(t(4), TA, [output("call_1"), token_count()]); s.check(state="working", tool=None, workload=1)
    s.rollout(t(5), TA, [task_complete("turn-1")]); s.check(state="idle")
    s.status(t(5), TA, IDLE)
    s.check(state="idle", states_since_start=["unknown", "idle", "working", "completed", "idle"])
    s.save()


def s02(root):
    s = Scenario(root, "S02", "Approval requested through activeFlags, then granted")
    s.load(t(0), thread(TA, IDLE)); s.check(state="idle")
    s.status(t(1), TA, ACTIVE)
    s.rollout(t(1), TA, [task_started("turn-1"), call("call_1")]); s.check(state="working", tool="exec_command")
    s.status(t(2), TA, APPROVAL); s.check(state="waiting")
    s.status(t(9), TA, ACTIVE); s.check(state="working")
    s.rollout(t(10), TA, [output("call_1"), task_complete("turn-1")])
    s.status(t(10), TA, IDLE); s.check(state="idle")
    s.save()


def s04(root):
    s = Scenario(root, "S04", "Subagent threads are Contractors of the parent; system threads are ignored")
    s.load(t(0), thread(TA, IDLE)); s.check(agent_count=1, contractors=[])
    s.status(t(1), TA, ACTIVE)
    s.notify(t(1), "thread/started", {"thread": thread(TS, ACTIVE, parent=TA, source={"subAgent": "review"})})
    s.check(agent_count=1, state="working", contractors=[{"state": "working", "tool": None}])
    s.rollout(t(2), TS, [session_meta(TS), task_started("turn-s1"), call("call_s1")])
    s.check(contractors=[{"state": "working", "tool": "exec_command"}])
    s.status(t(3), TS, APPROVAL); s.check(contractors=[{"state": "waiting", "tool": None}])
    s.status(t(4), TS, ACTIVE); s.check(contractors=[{"state": "working", "tool": "exec_command"}])
    s.rollout(t(5), TS, [output("call_s1"), task_complete("turn-s1")])
    s.status(t(5), TS, IDLE); s.check(contractors=[{"state": "idle", "tool": None}])
    s.status(t(6), TS, NOT_LOADED); s.check(agent_count=1, contractors=[], contractors_ended=1)
    s.notify(t(7), "thread/started", {"thread": thread(TT, ACTIVE, parent=TA, source={"subAgent": "review"})})
    s.check(contractors=[{"state": "working", "tool": None}])
    s.notify(t(8), "thread/started", {"thread": thread(TX, IDLE, with_path=False, thread_source="system")})
    s.status(t(9), TX, ACTIVE); s.check(agent_count=1, state="working")
    s.status(t(10), TA, NOT_LOADED); s.check(presence="off_duty", contractors=[], contractors_ended=2)
    s.save()


def s12(root):
    s = Scenario(root, "S12", "Usage limit reached; a new turn after reset resumes work")
    s.load(t(0), thread(TA, IDLE)); s.check(state="idle", reset_at=None)
    s.status(t(1), TA, ACTIVE)
    s.rollout(t(1), TA, [task_started("turn-1"), call("call_1"), output("call_1"), token_count(90.0, 50.0)])
    s.check(state="working", reset_at=None)
    s.rollout(t(2), TA, [token_count(100.0, 100.0)]); s.check(state="limited", reset_at="2026-01-08T00:00:00.000Z")
    s.rollout(t(3), TA, [task_complete("turn-1")])
    s.status(t(3), TA, IDLE); s.check(state="limited", reset_at="2026-01-08T00:00:00.000Z")
    s.status(t(600), TA, ACTIVE); s.check(state="working", reset_at=None)
    s.rollout(t(600), TA, [task_started("turn-2"), token_count(1.0, 1.0), task_complete("turn-2")])
    s.status(t(601), TA, IDLE)
    s.check(state="idle", states_since_start=["unknown", "idle", "working", "limited", "working", "completed", "idle"])
    s.save()


def s14(root):
    s = Scenario(root, "S14", "Unload, reload of the same thread, and daemon reconnect")
    s.load(t(0), thread(TA, IDLE)); s.check(presence="on_duty", seat=1, ref="a")
    s.notify(t(10), "thread/started", {"thread": thread(TB, IDLE)}); s.check(presence="on_duty", seat=2, ref="b")
    s.status(t(60), TA, NOT_LOADED); s.check(presence="off_duty", seat=1, same_as="a")
    s.status(t(120), TA, IDLE); s.check(presence="on_duty", seat=1, same_as="a")
    s.disconnect(t(130)); s.check(seat=2, state="unknown")
    s.notify(t(131), "thread/closed", {"threadId": TB}); s.check(presence="off_duty", seat=2, same_as="b")
    s.save()


if __name__ == "__main__":
    for build in (s01, s02, s04, s12, s14):
        build(sys.argv[1])
