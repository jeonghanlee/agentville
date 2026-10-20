"""Generator for synthetic Claude Code fixtures.

Usage: python tests/fixtures/claude/generate.py tests/fixtures
"""

import json
import os
import sys
from datetime import UTC, datetime, timedelta

import yaml

VERSION = "2.1.303"
BASE = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
CWD = "/home/user/repo"
TICKS_AT_BASE = 1_000_000
TICKS_PER_SECOND = 100


def ms(t):
    return int(t.timestamp() * 1000)


def iso(t):
    return t.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def t(seconds):
    return BASE + timedelta(seconds=seconds)


def usage():
    return {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0},
        "service_tier": "standard",
        "server_tool_use": {},
    }


class Scenario:
    def __init__(self, root, sid, title):
        self.dir = os.path.join(root, "claude", VERSION, sid)
        os.makedirs(os.path.join(self.dir, "sessions"), exist_ok=True)
        self.scenario = sid
        self.title = title
        self.timeline = []
        self.expect = []
        self.logs = {}
        self.snap = 0
        self.counter = 0
        self.last_uuid = {}
        self.started = {}

    def next_id(self, prefix):
        self.counter += 1
        return f"{prefix}{self.counter:012d}"

    def uid(self):
        self.counter += 1
        return f"00000000-0000-4000-8000-{self.counter:012d}"

    # Session files.

    def session(self, at, pid, session_id, status, tmux="tmux-1:%1", waiting_for=None,
                kind="interactive", name_source="user", bridge=None, job_id=None):
        start = self.started.setdefault(pid, at)
        self.snap += 1
        doc = {
            "pid": pid,
            "sessionId": session_id,
            "cwd": CWD,
            "startedAt": ms(start),
            "updatedAt": ms(at),
            "status": status,
            "statusUpdatedAt": ms(at),
            "procStart": str(TICKS_AT_BASE + int((start - BASE).total_seconds()) * TICKS_PER_SECOND),
            "pidDomain": "linux:<host>:pid:[1]",
            "kind": kind,
            "entrypoint": "cli",
            "name": "<text>",
            "nameSince": ms(start),
            "nameSource": name_source,
            "tmux": tmux,
            "version": VERSION,
            "peerFeatures": [],
            "peerProtocol": 1,
            "messagingSocketPath": "/tmp/socket-1",
            "bridgeSessionId": bridge,
        }
        for key, value in (("tmux", tmux), ("nameSource", name_source)):
            if value is None:
                del doc[key]
        if job_id:
            doc["jobId"] = job_id
        if waiting_for:
            doc["waitingFor"] = waiting_for
        name = f"sessions/{self.snap:03d}-{pid}.json"
        with open(os.path.join(self.dir, name), "w") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
        self.timeline.append({"at": iso(at), "op": "session_write", "pid": pid, "file": name})

    def remove(self, at, pid):
        self.timeline.append({"at": iso(at), "op": "session_remove", "pid": pid})

    # Transcripts.

    def _envelope(self, at, session_id, chained):
        base = {"sessionId": session_id, "timestamp": iso(at)}
        if chained:
            u = self.uid()
            base = {
                "uuid": u,
                "parentUuid": self.last_uuid.get(session_id),
                "sessionId": session_id,
                "timestamp": iso(at),
                "cwd": CWD,
                "gitBranch": "master",
                "isSidechain": False,
                "userType": "external",
                "entrypoint": "cli",
                "version": VERSION,
            }
            self.last_uuid[session_id] = u
        return base

    def records(self, at, session_id, recs):
        log = self.logs.setdefault(session_id, [])
        start = len(log)
        for rec in recs:
            spec = dict(rec)
            chained = spec.pop("_chained", True)
            stamped = spec.pop("_timestamp", True)
            with_session = spec.pop("_session", True)
            snake = spec.pop("_snake_session", False)
            record = self._envelope(at, session_id, chained)
            if not stamped:
                del record["timestamp"]
            if not with_session:
                del record["sessionId"]
            if snake:
                record["session_id"] = session_id
            if spec.get("sourceToolAssistantUUID") == "<last>":
                spec["sourceToolAssistantUUID"] = record["parentUuid"]
            record.update(spec)
            log.append(record)
        self.timeline.append(
            {"at": iso(at), "op": "log_append", "cwd": CWD, "session": session_id,
             "file": f"logs/{session_id}.jsonl", "lines": [start, len(log)]}
        )

    def check(self, **kw):
        kw["after"] = len(self.timeline)
        self.expect.append(kw)

    def save(self):
        if self.logs:
            os.makedirs(os.path.join(self.dir, "logs"), exist_ok=True)
        for sid, log in self.logs.items():
            with open(os.path.join(self.dir, "logs", f"{sid}.jsonl"), "w") as fh:
                for record in log:
                    fh.write(json.dumps(record) + "\n")
        with open(os.path.join(self.dir, "timeline.jsonl"), "w") as fh:
            for op in self.timeline:
                fh.write(json.dumps(op) + "\n")
        meta = {"provider": "claude", "version": VERSION, "scenario": self.scenario,
                "title": self.title, "expect": self.expect}
        with open(os.path.join(self.dir, "meta.yaml"), "w") as fh:
            yaml.safe_dump(meta, fh, sort_keys=False, default_flow_style=None, width=120)


def prompt():
    return {"type": "user", "promptId": "<prompt-id>", "permissionMode": "auto", "promptSource": "user",
            "origin": {"kind": "human"}, "turnOrigin": "user", "_snake_session": True,
            "message": {"role": "user", "content": "<text>"}}


def assistant(scenario, blocks, stop, model_on_all=False):
    """One record per content block; split records share message.id and stop_reason."""
    message_id = scenario.next_id("msg_")
    request_id = scenario.next_id("req_")
    out = []
    for index, block in enumerate(blocks):
        record = {
            "type": "assistant",
            "requestId": request_id,
            "effort": "high",
            "perTurnEffort": "high",
            "_snake_session": True,
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": "model-a",
                "content": [block],
                "stop_reason": stop,
                "stop_sequence": None,
                "stop_details": None,
                "container": None,
                "context_management": None,
                "diagnostics": None,
                "usage": usage(),
            },
        }
        if index == 0 or model_on_all:
            record["requestedModel"] = "model-a"
        if block["type"] == "thinking":
            record["thinkingDurationMs"] = 100
        out.append(record)
    return out


def thinking():
    return {"type": "thinking", "thinking": "<text>", "signature": "<signature>"}


def text():
    return {"type": "text", "text": "<text>"}


def tool_use(tid, name):
    return {"type": "tool_use", "id": tid, "name": name, "input": {"<key>": "<tool-input>"}, "caller": {"type": "direct"}}


def tool_result(tid, error=False, extra=None, result_as_string=False):
    block = {"type": "tool_result", "tool_use_id": tid, "content": "<tool-output>"}
    if error is not None:
        block["is_error"] = error
    record = {"type": "user", "promptId": "<prompt-id>", "sourceToolAssistantUUID": "<last>",
              "toolUseResult": "<tool-output>" if result_as_string else {"<key>": "<tool-output>"},
              "message": {"role": "user", "content": [block]}}
    if extra:
        record.update(extra)
    return record


def turn_done():
    return {"type": "system", "subtype": "turn_duration", "durationMs": 1000, "messageCount": 4, "isMeta": False}


def preamble():
    return [
        {"type": "permission-mode", "permissionMode": "auto", "_chained": False, "_timestamp": False},
        {"type": "queue-operation", "operation": "enqueue", "content": "<text>", "commandUuid": "<uuid>",
         "deliveryId": "<id>", "_chained": False},
        {"type": "queue-operation", "operation": "dequeue", "_chained": False},
        {"type": "attachment", "_snake_session": True,
         "attachment": {"type": "model", "identity": "<text>", "text": "<text>"}},
        {"type": "file-history-snapshot", "messageId": "<uuid>", "snapshot": {}, "isSnapshotUpdate": False,
         "_chained": False, "_timestamp": False, "_session": False},
    ]


def epilogue():
    return [
        {"type": "last-prompt", "lastPrompt": "<text>", "leafUuid": "<uuid>", "_chained": False, "_timestamp": False},
        {"type": "cost-state", "_chained": False, "_timestamp": False, "hasUnknownModelCost": False,
         "modelUsage": {}, "startTime": 0, "totalAPIDuration": 0, "totalAPIDurationWithoutRetries": 0,
         "totalCostUSD": 0, "totalDuration": 0, "totalLinesAdded": 0, "totalLinesRemoved": 0,
         "totalToolDuration": 0},
    ]


SA = "11111111-1111-4111-8111-111111111111"
SB = "22222222-2222-4222-8222-222222222222"
SC = "33333333-3333-4333-8333-333333333333"


def s01(root):
    s = Scenario(root, "S01", "One turn that reads a file and runs a shell command")
    s.session(t(0), 1001, SA, "idle"); s.check(presence="on_duty", seat=1, state="idle")
    s.records(t(1), SA, preamble() + [prompt()]); s.check(state="working")
    s.session(t(1), 1001, SA, "busy", job_id="<job-id>"); s.check(state="working")
    s.records(t(3), SA, assistant(s, [thinking(), tool_use("toolu_01", "Read")], "tool_use"))
    s.check(state="working", tool="Read")
    s.records(t(4), SA, [tool_result("toolu_01", extra={"permissionDecision": {"decision": "accept", "source": "config", "reasonType": "rule"}})])
    s.check(state="working", tool=None)
    s.records(t(5), SA, assistant(s, [tool_use("toolu_02", "Bash")], "tool_use")); s.check(state="working", tool="Bash", workload=2)
    s.records(t(9), SA, [tool_result("toolu_02", error=None, result_as_string=True)]); s.check(state="working", tool=None)
    s.records(t(10), SA, assistant(s, [text()], "end_turn") + [turn_done()] + epilogue())
    s.check(state="idle", states_since_start=["unknown", "idle", "working", "completed", "idle"])
    s.session(t(10), 1001, SA, "idle"); s.check(state="idle")
    s.save()


def s02(root):
    s = Scenario(root, "S02", "Command hitting an ask rule; deny once, approve once")
    s.session(t(0), 1001, SA, "idle"); s.check(state="idle")
    s.records(t(1), SA, [prompt()])
    s.session(t(1), 1001, SA, "busy")
    s.records(t(2), SA, assistant(s, [tool_use("toolu_01", "Bash")], "tool_use")); s.check(state="working", tool="Bash")
    s.session(t(3), 1001, SA, "waiting", waiting_for="permission <text>"); s.check(state="waiting")
    s.session(t(20), 1001, SA, "idle"); s.check(state="idle")
    s.records(t(20), SA, [tool_result("toolu_01", error=True, extra={"toolDenialKind": "user-rejected"}),
                          {"type": "user", "isMeta": True, "message": {"role": "user", "content": [text()]}},
                          turn_done()])
    s.check(state="idle")
    s.records(t(30), SA, [prompt()])
    s.session(t(30), 1001, SA, "busy")
    s.records(t(31), SA, assistant(s, [tool_use("toolu_02", "Bash")], "tool_use"))
    s.session(t(32), 1001, SA, "waiting", waiting_for="permission <text>"); s.check(state="waiting")
    s.session(t(40), 1001, SA, "busy"); s.check(state="working")
    s.records(t(41), SA, [tool_result("toolu_02", extra={"permissionDecision": {"decision": "accept", "source": "user"}})])
    s.records(t(42), SA, assistant(s, [text()], "end_turn") + [turn_done()])
    s.session(t(42), 1001, SA, "idle"); s.check(state="idle")
    s.save()


def s14(root):
    s = Scenario(root, "S14", "Normal exit; resume and runtime location select the returning Employee")
    s.session(t(0), 1001, SA, "idle", tmux="tmux-1:%1"); s.check(presence="on_duty", seat=1, ref="a")
    s.session(t(10), 1003, SB, "idle", tmux=None, kind="bg", name_source=None, bridge="<bridge-id>")
    s.check(presence="on_duty", seat=2, ref="b")
    s.remove(t(60), 1001); s.check(presence="off_duty", seat=1, same_as="a")
    s.remove(t(70), 1003); s.check(presence="off_duty", seat=2, same_as="b")
    s.session(t(120), 1002, SB, "idle", tmux="tmux-1:%9"); s.check(presence="on_duty", seat=2, same_as="b", pid=1002)
    s.session(t(130), 1004, SC, "idle", tmux="tmux-1:%1"); s.check(presence="on_duty", seat=1, same_as="a", pid=1004)
    s.remove(t(200), 1002); s.check(presence="off_duty", seat=2, same_as="b")
    s.save()


if __name__ == "__main__":
    for build in (s01, s02, s14):
        build(sys.argv[1])
