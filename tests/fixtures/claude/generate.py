"""Generator for synthetic Claude Code fixtures. Usage: python tests/fixtures/claude/generate.py tests/fixtures"""

import json
import os
import sys
from datetime import UTC, datetime, timedelta

ROOT = sys.argv[1]
VERSION = "2.1.303"
BASE = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
CWD = "/home/user/repo"


def ms(t):
    return int(t.timestamp() * 1000)


def iso(t):
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Scenario:
    def __init__(self, sid, title):
        self.dir = os.path.join(ROOT, "claude", VERSION, sid)
        os.makedirs(os.path.join(self.dir, "sessions"), exist_ok=True)
        os.makedirs(os.path.join(self.dir, "logs"), exist_ok=True)
        self.title = title
        self.timeline = []
        self.expect = []
        self.logs = {}
        self.snap = 0
        self.uuid_n = 0
        self.last_uuid = {}

    def uid(self):
        self.uuid_n += 1
        return f"00000000-0000-4000-8000-{self.uuid_n:012d}"

    def session(self, t, pid, session_id, status, proc_start="1234567", tmux="tmux-1:%1", waiting_for=None,
                kind="interactive", name_source="auto", bridge=None):
        self.snap += 1
        doc = {
            "pid": pid,
            "sessionId": session_id,
            "cwd": CWD,
            "startedAt": ms(BASE),
            "updatedAt": ms(t),
            "status": status,
            "statusUpdatedAt": ms(t),
            "procStart": proc_start,
            "pidDomain": "linux:<host>:pid:[1]",
            "kind": kind,
            "entrypoint": "cli",
            "name": "<text>",
            "nameSince": ms(BASE),
            "nameSource": name_source,
            "tmux": tmux,
            "version": VERSION,
            "peerFeatures": [],
            "peerProtocol": 1,
            "messagingSocketPath": "/tmp/socket-1",
            "bridgeSessionId": bridge,
        }
        if tmux is None:
            del doc["tmux"]
        if name_source is None:
            del doc["nameSource"]
        if waiting_for:
            doc["waitingFor"] = waiting_for
        name = f"sessions/{self.snap:03d}-{pid}.json"
        with open(os.path.join(self.dir, name), "w") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
        self.timeline.append({"at": iso(t), "op": "session_write", "pid": pid, "file": name})

    def remove(self, t, pid):
        self.timeline.append({"at": iso(t), "op": "session_remove", "pid": pid})

    def records(self, t, session_id, recs):
        log = self.logs.setdefault(session_id, [])
        start = len(log)
        for r in recs:
            u = self.uid()
            base = {
                "uuid": u,
                "parentUuid": self.last_uuid.get(session_id),
                "sessionId": session_id,
                "timestamp": iso(t),
                "cwd": CWD,
                "gitBranch": "master",
                "isSidechain": False,
                "entrypoint": "cli",
                "session_id": session_id,
                "userType": "external",
                "version": VERSION,
            }
            if r.get("type") not in ("user", "assistant", "system"):
                base = {"sessionId": session_id, "timestamp": iso(t)}
            base.update(r)
            self.last_uuid[session_id] = u
            log.append(base)
        self.timeline.append(
            {"at": iso(t), "op": "log_append", "cwd": CWD, "session": session_id,
             "file": f"logs/{session_id}.jsonl", "lines": [start, len(log)]}
        )

    def check(self, **kw):
        kw["after"] = len(self.timeline)
        self.expect.append(kw)

    def save(self):
        for sid, log in self.logs.items():
            with open(os.path.join(self.dir, "logs", f"{sid}.jsonl"), "w") as fh:
                for r in log:
                    fh.write(json.dumps(r) + "\n")
        with open(os.path.join(self.dir, "timeline.jsonl"), "w") as fh:
            for op in self.timeline:
                fh.write(json.dumps(op) + "\n")
        lines = [f"provider: claude", f"version: \"{VERSION}\"", f"scenario: {os.path.basename(self.dir)}",
                 f"title: {self.title}", "expect:"]
        for e in self.expect:
            lines.append("  - " + json.dumps(e))
        with open(os.path.join(self.dir, "meta.yaml"), "w") as fh:
            fh.write("\n".join(lines) + "\n")


def user_text():
    return {"type": "user", "promptId": "<text>", "message": {"role": "user", "content": "<text>"}}


def assistant(items, stop):
    return {"type": "assistant", "requestId": "req-1", "requestedModel": "model-a", "effort": "high",
            "perTurnEffort": None, "thinkingDurationMs": 100,
            "message": {"id": "msg-1", "type": "message", "role": "assistant", "model": "model-a",
                        "content": items, "stop_reason": stop, "stop_sequence": None,
                        "usage": {"input_tokens": 1, "output_tokens": 1}}}


def tool_use(tid, name):
    return {"type": "tool_use", "id": tid, "name": name, "input": {"<key>": "<tool-input>"}, "caller": {"type": "direct"}}


def tool_result(tid, error=False, extra=None):
    block = {"type": "tool_result", "tool_use_id": tid, "content": "<tool-output>"}
    if error is not None:
        block["is_error"] = error
    r = {"type": "user", "toolUseResult": {"<key>": "<tool-output>"}, "sourceToolAssistantUUID": "<uuid>",
         "message": {"role": "user", "content": [block]}}
    if extra:
        r.update(extra)
    return r


def thinking():
    return {"type": "thinking", "thinking": "<text>", "signature": "<signature>"}


def preamble():
    return [
        {"type": "permission-mode", "permissionMode": "default"},
        {"type": "queue-operation", "operation": "enqueue", "content": "<text>"},
        {"type": "queue-operation", "operation": "dequeue"},
        {"type": "attachment", "attachment": {"type": "model", "content": "<text>"}},
        {"type": "file-history-snapshot", "messageId": "<uuid>", "snapshot": {}, "isSnapshotUpdate": False},
    ]


def epilogue():
    return [
        {"type": "last-prompt", "lastPrompt": "<text>", "leafUuid": "<uuid>"},
        {"type": "cost-state", "totalCostUSD": 0, "totalDuration": 0, "modelUsage": {}},
    ]


def turn_done():
    return {"type": "system", "subtype": "turn_duration", "durationMs": 1000, "messageCount": 4, "isMeta": False}


def t(s):
    return BASE + timedelta(seconds=s)


SA = "11111111-1111-4111-8111-111111111111"
SB = "22222222-2222-4222-8222-222222222222"

# S01: one turn reading a file and running a shell command.
s = Scenario("S01", "One turn that reads a file and runs a shell command")
s.session(t(0), 1001, SA, "idle"); s.check(presence="on_duty", seat=1, state="idle")
s.records(t(1), SA, preamble() + [user_text()]); s.check(state="working")
s.session(t(1), 1001, SA, "busy"); s.check(state="working")
s.records(t(3), SA, [assistant([thinking(), tool_use("toolu_01", "Read")], "tool_use")])
s.check(state="working", tool="Read")
s.records(t(4), SA, [tool_result("toolu_01", extra={"permissionDecision": {"decision": "accept", "source": "config", "reasonType": "rule"}})])
s.check(state="working", tool=None)
s.records(t(5), SA, [assistant([tool_use("toolu_02", "Bash")], "tool_use")]); s.check(state="working", tool="Bash", workload=2)
s.records(t(9), SA, [tool_result("toolu_02", error=None)]); s.check(state="working", tool=None)
s.records(t(10), SA, [assistant([{"type": "text", "text": "<text>"}], "end_turn"), turn_done()] + epilogue())
s.check(state="idle", states_since_start=["unknown", "idle", "working", "completed", "idle"])
s.session(t(10), 1001, SA, "idle"); s.check(state="idle")
s.save()

# S02: waiting on an ask rule, denied once and approved once.
s = Scenario("S02", "Command hitting an ask rule; deny once, approve once")
s.session(t(0), 1001, SA, "idle"); s.check(state="idle")
s.records(t(1), SA, [user_text()])
s.session(t(1), 1001, SA, "busy")
s.records(t(2), SA, [assistant([tool_use("toolu_01", "Bash")], "tool_use")]); s.check(state="working", tool="Bash")
s.session(t(3), 1001, SA, "waiting", waiting_for="permission <text>"); s.check(state="waiting")
s.session(t(20), 1001, SA, "idle"); s.check(state="idle")
s.records(t(20), SA, [tool_result("toolu_01", error=True, extra={"toolDenialKind": "user-rejected"}),
                      {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "<text>"}]}, "isMeta": True},
                      turn_done()])
s.check(state="idle")
s.records(t(30), SA, [user_text()])
s.session(t(30), 1001, SA, "busy")
s.records(t(31), SA, [assistant([tool_use("toolu_02", "Bash")], "tool_use")])
s.session(t(32), 1001, SA, "waiting", waiting_for="permission <text>"); s.check(state="waiting")
s.session(t(40), 1001, SA, "busy"); s.check(state="working")
s.records(t(41), SA, [tool_result("toolu_02", extra={"permissionDecision": {"decision": "accept", "source": "user"}})])
s.records(t(42), SA, [assistant([{"type": "text", "text": "<text>"}], "end_turn"), turn_done()])
s.session(t(42), 1001, SA, "idle"); s.check(state="idle")
s.save()

# S14: normal exit; resume and runtime location select the returning Employee.
SC = "33333333-3333-4333-8333-333333333333"
s = Scenario("S14", "Normal exit; resume and runtime location select the returning Employee")
s.session(t(0), 1001, SA, "idle", tmux="tmux-1:%1"); s.check(presence="on_duty", seat=1, ref="a")
s.session(t(10), 1003, SB, "idle", proc_start="3000000", tmux=None, kind="bg", name_source=None, bridge="<bridge-id>")
s.check(presence="on_duty", seat=2, ref="b")
s.remove(t(60), 1001); s.check(presence="off_duty", seat=1, same_as="a")
s.remove(t(70), 1003); s.check(presence="off_duty", seat=2, same_as="b")
s.session(t(120), 1002, SB, "idle", proc_start="2000000", tmux="tmux-1:%9"); s.check(presence="on_duty", seat=2, same_as="b", pid=1002)
s.session(t(130), 1004, SC, "idle", proc_start="4000000", tmux="tmux-1:%1"); s.check(presence="on_duty", seat=1, same_as="a", pid=1004)
s.remove(t(200), 1002); s.check(presence="off_duty", seat=2, same_as="b")
s.save()
