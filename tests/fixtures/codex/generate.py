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
OUTSIDE = "/home/user/notes"
GIT_INFO = {"branch": "master", "sha": "<sha>", "originUrl": "https://github.com/example/repo"}


def iso(t):
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def t(seconds):
    return BASE + timedelta(seconds=seconds)


def rollout_rel(thread_id):
    return f"sessions/2026/01/01/rollout-2026-01-01T00-00-00-{thread_id}.jsonl"


def codex_home(home):
    """Fixture path of Codex home number ``home`` (1 is ``~/.codex``)."""
    return HOME if home == 1 else f"{HOME}-{home}"


def thread(thread_id, status, with_path=True, parent=None, thread_source="user", source="vscode", home=1,
           created=BASE, cwd=CWD, forked_from=None):
    git_info = dict(GIT_INFO) if cwd == CWD else None
    return {
        "agentNickname": None,
        "agentRole": None,
        "canAcceptDirectInput": True,
        "cliVersion": VERSION,
        "createdAt": int(created.timestamp()),
        "cwd": cwd,
        "daybreakEnabled": False,
        "environments": [],
        "ephemeral": False,
        "extra": {},
        "forkedFromId": forked_from,
        "gitInfo": git_info,
        "historyMode": "paginated",
        "id": thread_id,
        "model": "model-b",
        "modelProvider": "openai",
        "name": None,
        "originator": "codex-tui",
        "parentThreadId": parent,
        "path": f"{codex_home(home)}/{rollout_rel(thread_id)}" if with_path else None,
        "preview": "<text>",
        "projectId": "<project-id>",
        "reasoningEffort": "medium",
        "recencyAt": int(created.timestamp()),
        "section": None,
        "sectionEnteredAt": None,
        "sessionId": thread_id,
        "source": source,
        "status": status,
        "threadSource": thread_source,
        "turns": [],
        "updatedAt": int(created.timestamp()),
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

    def _op(self, op, home):
        # Operations name a Codex home only when it is not the first one.
        if home != 1:
            op["home"] = home
        self.timeline.append(op)

    def load(self, at, data, home=1):
        """Thread already loaded when the Collector first connects; later threads use thread/started."""
        self._op({"at": iso(at), "op": "appserver_thread", "file": self._write("thread", data)}, home)

    def notify(self, at, method, params, home=1):
        name = self._write(method.replace("/", "-"), {"method": method, "params": params})
        self._op({"at": iso(at), "op": "appserver_notify", "file": name}, home)

    def status(self, at, thread_id, status, home=1):
        self.notify(at, "thread/status/changed", {"threadId": thread_id, "status": status}, home)

    def started(self, at, data, home=1):
        self.notify(at, "thread/started", {"thread": data}, home)

    def closed(self, at, thread_id, home=1):
        self.notify(at, "thread/closed", {"threadId": thread_id}, home)

    def disconnect(self, at):
        self.timeline.append({"at": iso(at), "op": "appserver_disconnect"})

    def rollout(self, at, thread_id, records, home=1):
        rel = rollout_rel(thread_id)
        log = self.logs.setdefault(rel, [])
        start = len(log)
        for rtype, payload in records:
            self.ordinal += 1
            log.append({"timestamp": iso(at), "ordinal": self.ordinal, "type": rtype, "payload": payload})
        self._op({"at": iso(at), "op": "log_append", "path": rel,
                  "file": f"logs/{os.path.basename(rel)}", "lines": [start, len(log)]}, home)

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


def session_meta(thread_id, cwd=CWD, created=BASE):
    git = {"branch": "master", "commit_hash": "<sha>", "repository_url": "https://github.com/example/repo"} if cwd == CWD else None
    return ("session_meta", {"id": thread_id, "session_id": thread_id, "timestamp": iso(created), "cwd": cwd,
                             "git": git,
                             "cli_version": VERSION, "model_provider": "openai", "originator": "codex-tui",
                             "source": "vscode", "thread_source": "user", "context_window": 1,
                             "history_mode": "paginated", "runtime_workspace_roots": [cwd],
                             "creator_account_id": "account-1", "creator_user_id": "user-1",
                             "base_instructions": "<text>"})


def task_started(turn):
    return ("event_msg", {"type": "task_started", "turn_id": turn, "root_turn_id": turn, "started_at": 0,
                          "model_context_window": 1, "collaboration_mode_kind": "default", "turn_attribution": None})


def task_error(kind):
    """task_complete.error: an object naming the error kind, with message text."""
    return {"codex_error_info": kind, "message": "<text>"}


def task_complete(turn, error=None):
    return ("event_msg", {"type": "task_complete", "turn_id": turn, "root_turn_id": turn, "started_at": 0,
                          "completed_at": 1, "duration_ms": 1000, "time_to_first_token_ms": 100,
                          "last_agent_message": "<text>", "error": error})


def turn_context(turn, model="model-b", effort="medium", cwd=CWD):
    return ("turn_context", {"turn_id": turn, "root_turn_id": turn, "cwd": cwd, "model": model, "effort": effort,
                             "summary": "auto", "approval_policy": "on-request", "sandbox_policy": {"type": "workspace-write"}})


def call(call_id, name="exec_command"):
    return ("response_item", {"type": "function_call", "name": name, "namespace": None, "arguments": "<tool-input>", "call_id": call_id})


def output(call_id):
    return ("response_item", {"type": "function_call_output", "call_id": call_id, "output": "<tool-output>"})


def reasoning():
    return ("response_item", {"type": "reasoning", "summary": [], "encrypted_content": "<secret>"})


def window(used, minutes, resets_after):
    return {"used_percent": used, "window_minutes": minutes, "resets_at": int((BASE + resets_after).timestamp())}


def token_count(used=10.0, weekly=None, limits=True):
    rate_limits = {
        "credits": {"balance": "<balance>", "has_credits": True},
        "individual_limit": None,
        "limit_id": "<id>",
        "limit_name": "<name>",
        "plan_type": "<plan>",
        "primary": window(used, 300, timedelta(hours=5)),
        "secondary": window(weekly, 10080, timedelta(days=7)) if weekly is not None else None,
        "rate_limit_reached_type": None,
        "spend_control_reached": None,
    }
    return ("event_msg", {"type": "token_count", "info": {}, "rate_limits": rate_limits if limits else None})


TA = "019a0000-0000-7000-8000-00000000000a"
TB = "019a0000-0000-7000-8000-00000000000b"
TS = "019a0000-0000-7000-8000-0000000000aa"
TT = "019a0000-0000-7000-8000-0000000000ab"
TX = "019a0000-0000-7000-8000-0000000000ff"
TC = "019a0000-0000-7000-8000-00000000000c"
TD = "019a0000-0000-7000-8000-00000000000d"
TF = "019a0000-0000-7000-8000-00000000000f"


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
    s = Scenario(root, "S12", "Usage limit by full window or turn error; a new turn resumes work; overload is no error")
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
    # The turn ends with a usage-limit error after the window filled: limited, not an error.
    s.status(t(700), TA, ACTIVE)
    s.rollout(t(700), TA, [task_started("turn-3"), call("call_3"), output("call_3"), token_count(100.0, 60.0)])
    s.check(state="limited", reset_at="2026-01-01T05:00:00.000Z")
    s.rollout(t(701), TA, [task_complete("turn-3", error=task_error("usage_limit_exceeded"))])
    s.status(t(701), TA, IDLE); s.check(state="limited", reset_at="2026-01-01T05:00:00.000Z")
    # A usage-limit error with no full window seen takes the reset of the most used window.
    s.status(t(800), TA, ACTIVE)
    s.rollout(t(800), TA, [task_started("turn-4"), token_count(40.0, 98.0), token_count(limits=False)])
    s.check(state="working", reset_at=None)
    s.rollout(t(801), TA, [task_complete("turn-4", error=task_error("usage_limit_exceeded"))])
    s.status(t(801), TA, IDLE); s.check(state="limited", reset_at="2026-01-08T00:00:00.000Z")
    # An overloaded server ends the turn without an error.
    s.status(t(900), TA, ACTIVE)
    s.rollout(t(900), TA, [task_started("turn-5"), token_count(1.0, 1.0)]); s.check(state="working")
    s.rollout(t(901), TA, [task_complete("turn-5", error=task_error("server_overloaded"))])
    s.status(t(901), TA, IDLE)
    s.check(state="idle", states_since_start=["unknown", "idle", "working", "limited", "working", "completed", "idle",
                                              "working", "limited", "working", "limited", "working", "completed", "idle"])
    s.save()


def turn(s, at, thread_id, turn_id, calls=(), home=1, **context):
    """One complete turn: active status, rollout records, idle status."""
    s.status(t(at), thread_id, ACTIVE, home)
    records = [turn_context(turn_id, **context), task_started(turn_id)]
    for call_id in calls:
        records += [call(call_id), output(call_id)]
    s.rollout(t(at), thread_id, records + [task_complete(turn_id)], home)
    s.status(t(at + 1), thread_id, IDLE, home)


def s03(root):
    s = Scenario(root, "S03", "A failing command keeps the Employee working; the retry succeeds")
    s.load(t(0), thread(TA, IDLE)); s.check(state="idle")
    s.status(t(1), TA, ACTIVE)
    s.rollout(t(1), TA, [turn_context("turn-1"), task_started("turn-1"), call("call_1")])
    s.check(state="working", tool="exec_command")
    # The command's failure is only in its output text, which is not read.
    s.rollout(t(2), TA, [output("call_1")]); s.check(state="working", tool=None, workload=1)
    s.rollout(t(3), TA, [reasoning(), call("call_2")]); s.check(state="working", tool="exec_command", workload=2)
    s.rollout(t(4), TA, [output("call_2")]); s.check(state="working", tool=None)
    s.rollout(t(5), TA, [task_complete("turn-1")])
    s.status(t(5), TA, IDLE)
    s.check(state="idle", states_since_start=["unknown", "idle", "working", "completed", "idle"])
    s.save()


def s06(root):
    s = Scenario(root, "S06", "Resume returns to the thread's Employee; fork takes a free seat")
    s.load(t(0), thread(TA, IDLE)); s.check(seat=1, ref="a", session_id=TA)
    s.started(t(1), thread(TB, IDLE, created=t(1))); s.check(seat=2, ref="b", session_id=TB)
    s.rollout(t(2), TA, [session_meta(TA)])
    turn(s, 2, TA, "turn-1", calls=["call_1"])
    s.rollout(t(4), TB, [session_meta(TB)])
    turn(s, 4, TB, "turn-2"); s.check(seat=2, state="idle")
    s.closed(t(60), TA); s.check(seat=1, presence="off_duty", same_as="a")
    s.closed(t(61), TB); s.check(seat=2, presence="off_duty", same_as="b")
    # codex resume TB: same thread id; the session outranks the lowest free seat.
    s.started(t(120), thread(TB, IDLE, created=t(1)))
    s.check(seat=2, presence="on_duty", same_as="b", session_id=TB, state="idle")
    s.check(seat=1, presence="off_duty", same_as="a")
    # The resumed rollout is appended to; only the new records are read.
    s.status(t(121), TB, ACTIVE)
    s.rollout(t(121), TB, [turn_context("turn-3"), task_started("turn-3"), call("call_3")])
    s.check(seat=2, state="working", tool="exec_command", workload=1)
    s.rollout(t(122), TB, [output("call_3"), task_complete("turn-3")])
    s.status(t(122), TB, IDLE); s.check(seat=2, state="idle")
    # A fork of TB is a new thread with forkedFromId; it takes the lowest free seat.
    s.started(t(130), thread(TF, IDLE, created=t(130), forked_from=TB))
    s.check(seat=1, presence="on_duty", same_as="a", session_id=TF, state="idle")
    s.rollout(t(131), TF, [session_meta(TF, created=t(130))])
    s.status(t(131), TF, ACTIVE)
    s.rollout(t(131), TF, [turn_context("turn-4"), task_started("turn-4"), call("call_4")])
    s.check(seat=1, state="working", tool="exec_command"); s.check(seat=2, state="idle")
    # Closing the fork and resuming TA brings back the Employee that worked on both.
    s.closed(t(140), TF); s.check(seat=1, presence="off_duty", same_as="a")
    s.started(t(150), thread(TA, IDLE)); s.check(seat=1, presence="on_duty", same_as="a", session_id=TA, agent_count=2)
    s.save()


def s08(root):
    s = Scenario(root, "S08", "Model and effort changes map to conditions by the default rules")
    s.load(t(0), thread(TA, IDLE)); s.check(model="model-b", effort="medium", condition="normal")
    turn(s, 1, TA, "turn-1", effort="high"); s.check(model="model-b", effort="high", condition="study-mode")
    turn(s, 10, TA, "turn-2", model="model-c", effort="low"); s.check(model="model-c", effort="low", condition="light")
    turn(s, 20, TA, "turn-3", model="model-c", effort="xhigh"); s.check(model="model-c", effort="xhigh", condition="study-mode")
    turn(s, 30, TA, "turn-4", model="model-b", effort="medium"); s.check(model="model-b", effort="medium", condition="normal")
    s.save()


def s09(root):
    s = Scenario(root, "S09", "The same task under two Codex homes is done by two Employees, one per account")
    s.load(t(0), thread(TA, IDLE)); s.check(seat=1, ref="a", account_alias="codex-account-1")
    s.started(t(1), thread(TB, IDLE, home=2, created=t(1)), home=2)
    s.check(seat=2, ref="b", account_alias="codex-account-2", presence="on_duty", agent_count=2)
    s.rollout(t(2), TA, [session_meta(TA)])
    s.status(t(2), TA, ACTIVE)
    s.rollout(t(2), TA, [turn_context("turn-1"), task_started("turn-1"), call("call_1")])
    s.rollout(t(2), TB, [session_meta(TB)], home=2)
    s.status(t(2), TB, ACTIVE, home=2)
    s.rollout(t(2), TB, [turn_context("turn-1"), task_started("turn-1"), call("call_1")], home=2)
    s.check(seat=1, state="working", tool="exec_command"); s.check(seat=2, state="working", tool="exec_command")
    s.rollout(t(3), TA, [output("call_1"), task_complete("turn-1")])
    s.status(t(3), TA, IDLE); s.check(seat=1, state="idle"); s.check(seat=2, state="working", tool="exec_command")
    s.rollout(t(4), TB, [output("call_1"), task_complete("turn-1")], home=2)
    s.status(t(4), TB, IDLE, home=2); s.check(seat=2, state="idle", account_alias="codex-account-2")
    s.closed(t(60), TA); s.check(seat=1, presence="off_duty", same_as="a")
    s.closed(t(61), TB, home=2); s.check(seat=2, presence="off_duty", same_as="b")
    # Seats follow the seat rules, not the home; the account is an attribute of the Employee on shift.
    s.started(t(120), thread(TC, IDLE, home=2, created=t(120)), home=2)
    s.check(seat=1, presence="on_duty", same_as="a", account_alias="codex-account-2"); s.check(seat=2, presence="off_duty")
    s.started(t(130), thread(TD, IDLE, created=t(130)))
    s.check(seat=2, presence="on_duty", same_as="b", account_alias="codex-account-1", agent_count=2)
    s.save()


def s10(root):
    s = Scenario(root, "S10", "Two concurrent threads in one repository; app-server shifts carry no runtime location")
    s.load(t(0), thread(TA, IDLE)); s.check(seat=1, ref="a", location=None, presence="on_duty")
    s.started(t(1), thread(TB, IDLE)); s.check(seat=2, ref="b", location=None, presence="on_duty")
    s.status(t(2), TA, ACTIVE); s.check(seat=1, state="working"); s.check(seat=2, state="idle")
    s.status(t(3), TB, ACTIVE)
    s.rollout(t(3), TB, [turn_context("turn-1"), task_started("turn-1"), call("call_1")])
    s.check(seat=1, state="working", tool=None); s.check(seat=2, state="working", tool="exec_command")
    s.closed(t(60), TA); s.check(seat=1, presence="off_duty", same_as="a"); s.check(seat=2, presence="on_duty")
    # A new thread takes the lowest free seat while seat 2 is on shift.
    s.started(t(70), thread(TC, IDLE, created=t(70))); s.check(seat=1, presence="on_duty", same_as="a", session_id=TC)
    s.closed(t(80), TB); s.check(seat=2, presence="off_duty", same_as="b")
    s.closed(t(81), TC); s.check(seat=1, presence="off_duty", same_as="a")
    # Without a runtime location, new threads fill seats from the lowest.
    s.started(t(120), thread(TD, IDLE, created=t(120))); s.check(seat=1, presence="on_duty", same_as="a", session_id=TD)
    s.check(seat=2, presence="off_duty", agent_count=2)
    s.save()


def s11(root):
    s = Scenario(root, "S11", "A thread outside any repository works in the Common Office")
    s.load(t(0), thread(TA, IDLE)); s.check(project="github.com/example/repo", seat=1, ref="r", presence="on_duty")
    s.started(t(1), thread(TB, IDLE, cwd=OUTSIDE))
    s.check(project="common-office", seat=1, ref="c", presence="on_duty", state="idle", agent_count=2)
    s.rollout(t(2), TB, [session_meta(TB, cwd=OUTSIDE)])
    s.status(t(2), TB, ACTIVE)
    s.rollout(t(2), TB, [turn_context("turn-1", cwd=OUTSIDE), task_started("turn-1"), call("call_1")])
    s.check(project="common-office", state="working", tool="exec_command"); s.check(project="github.com/example/repo", state="idle")
    s.rollout(t(3), TB, [output("call_1"), task_complete("turn-1")])
    s.status(t(3), TB, IDLE); s.check(project="common-office", state="idle", same_as="c")
    s.closed(t(60), TB); s.check(project="common-office", seat=1, presence="off_duty", same_as="c")
    s.check(project="github.com/example/repo", seat=1, presence="on_duty", same_as="r")
    s.save()


def s13(root):
    s = Scenario(root, "S13", "Turn and thread errors persist through turn end and idle until activity resumes")
    s.load(t(0), thread(TA, IDLE)); s.check(state="idle")
    s.status(t(1), TA, ACTIVE)
    s.rollout(t(1), TA, [turn_context("turn-1"), task_started("turn-1"), call("call_1"), output("call_1")])
    s.check(state="working")
    s.rollout(t(2), TA, [task_complete("turn-1", error=task_error("<error>"))]); s.check(state="error", tool=None)
    s.status(t(2), TA, IDLE); s.check(state="error")
    s.status(t(30), TA, ACTIVE); s.check(state="working")
    s.rollout(t(30), TA, [task_started("turn-2"), task_complete("turn-2")])
    s.status(t(31), TA, IDLE)
    s.check(state="idle", states_since_start=["unknown", "idle", "working", "error", "working", "completed", "idle"])
    s.status(t(40), TA, ACTIVE)
    s.rollout(t(40), TA, [task_started("turn-3")])
    s.status(t(41), TA, {"type": "systemError"}); s.check(state="error")
    s.status(t(50), TA, IDLE); s.check(state="error")
    s.status(t(60), TA, ACTIVE); s.check(state="working")
    s.status(t(61), TA, {"type": "systemError"}); s.check(state="error")
    s.closed(t(70), TA); s.check(presence="off_duty")
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
    for build in (s01, s02, s03, s04, s06, s08, s09, s10, s11, s12, s13, s14):
        build(sys.argv[1])
