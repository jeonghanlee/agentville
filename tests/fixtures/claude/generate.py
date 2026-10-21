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
OUTSIDE = "/home/user/notes"
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
        self.cwds = {}

    def next_id(self, prefix):
        self.counter += 1
        return f"{prefix}{self.counter:012d}"

    def uid(self):
        self.counter += 1
        return f"00000000-0000-4000-8000-{self.counter:012d}"

    # Session files.

    def session(self, at, pid, session_id, status, tmux="tmux-1:%1", waiting_for=None,
                kind="interactive", name_source="user", bridge=None, job_id=None, cwd=CWD):
        start = self.started.setdefault(pid, at)
        self.cwds.setdefault(session_id, cwd)
        self.snap += 1
        doc = {
            "pid": pid,
            "sessionId": session_id,
            "cwd": cwd,
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
            cwd = self.cwds.get(session_id, CWD)
            base = {
                "uuid": u,
                "parentUuid": self.last_uuid.get(session_id),
                "sessionId": session_id,
                "timestamp": iso(at),
                "cwd": cwd,
                "gitBranch": "master",
                "isSidechain": False,
                "userType": "external",
                "entrypoint": "cli",
                "version": VERSION,
            }
            if cwd != CWD:
                # Outside a repository there is no branch.
                del base["gitBranch"]
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
            {"at": iso(at), "op": "log_append", "cwd": self.cwds.get(session_id, CWD), "session": session_id,
             "file": f"logs/{session_id}.jsonl", "lines": [start, len(log)]}
        )

    def subagent_meta(self, at, session_id, agent_id, tool_use_id):
        name = f"logs/agent-{agent_id}.meta.json"
        os.makedirs(os.path.join(self.dir, "logs"), exist_ok=True)
        with open(os.path.join(self.dir, name), "w") as fh:
            json.dump({"toolUseId": tool_use_id}, fh)
        self.timeline.append({"at": iso(at), "op": "file_write", "path": subagent_rel(session_id, agent_id, ".meta.json"),
                              "file": name})

    def subagent_records(self, at, session_id, agent_id, recs):
        """Subagent transcript records: sidechain, parent sessionId, own uuid chain."""
        key = f"agent-{agent_id}"
        log = self.logs.setdefault(key, [])
        start = len(log)
        for rec in recs:
            spec = dict(rec)
            spec.pop("_snake_session", None)
            record = self._envelope(at, key, True)
            record.update({"sessionId": session_id, "isSidechain": True, "agentId": agent_id})
            if spec.get("sourceToolAssistantUUID") == "<last>":
                spec["sourceToolAssistantUUID"] = record["parentUuid"]
            record.update(spec)
            log.append(record)
        self.timeline.append({"at": iso(at), "op": "log_append", "path": subagent_rel(session_id, agent_id, ".jsonl"),
                              "file": f"logs/{key}.jsonl", "lines": [start, len(log)]})

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


def subagent_rel(session_id, agent_id, ext):
    return f"projects/{CWD.replace('/', '-')}/{session_id}/subagents/agent-{agent_id}{ext}"


def prompt():
    return {"type": "user", "promptId": "<prompt-id>", "permissionMode": "auto", "promptSource": "user",
            "origin": {"kind": "human"}, "turnOrigin": "user", "_snake_session": True,
            "message": {"role": "user", "content": "<text>"}}


def assistant(scenario, blocks, stop, model_on_all=False, model="model-a", effort="high"):
    """One record per content block; split records share message.id and stop_reason."""
    message_id = scenario.next_id("msg_")
    request_id = scenario.next_id("req_")
    out = []
    for index, block in enumerate(blocks):
        record = {
            "type": "assistant",
            "requestId": request_id,
            "effort": effort,
            "perTurnEffort": effort,
            "_snake_session": True,
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "model": model,
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
            record["requestedModel"] = model
        if block["type"] == "thinking":
            record["thinkingDurationMs"] = 100
        out.append(record)
    return out


def api_error(scenario):
    """Assistant record standing in for a failed API request."""
    records = assistant(scenario, [text()], "stop_sequence")
    records[0].update({"isApiErrorMessage": True, "apiError": "<text>", "apiErrorStatus": 500})
    return records


def thinking():
    return {"type": "thinking", "thinking": "<text>", "signature": "<signature>"}


def text():
    return {"type": "text", "text": "<text>"}


def tool_use(tid, name, tool_input=None):
    return {"type": "tool_use", "id": tid, "name": name, "input": tool_input or {"<key>": "<tool-input>"},
            "caller": {"type": "direct"}}


def agent_use(tid):
    return tool_use(tid, "Agent", {"description": "<text>", "prompt": "<text>", "subagent_type": "<text>"})


def tool_result(tid, error=False, extra=None, result_as_string=False, result=None):
    block = {"type": "tool_result", "tool_use_id": tid, "content": "<tool-output>"}
    if error is not None:
        block["is_error"] = error
    record = {"type": "user", "promptId": "<prompt-id>", "sourceToolAssistantUUID": "<last>",
              "toolUseResult": "<tool-output>" if result_as_string else result or {"<key>": "<tool-output>"},
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
SD = "44444444-4444-4444-8444-444444444444"
SE = "55555555-5555-4555-8555-555555555555"
AGENT_1 = "a000000000000001"


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


def s04(root):
    s = Scenario(root, "S04", "Agent tool launches a subagent; parent exit ends an unfinished one")
    s.session(t(0), 1001, SA, "idle"); s.check(state="idle", contractors=[])
    s.records(t(1), SA, [prompt()])
    s.session(t(1), 1001, SA, "busy")
    s.records(t(2), SA, assistant(s, [agent_use("toolu_01")], "tool_use"))
    s.check(state="working", tool="Agent", contractors=[{"state": "working", "tool": None}])
    s.subagent_meta(t(2), SA, AGENT_1, "toolu_01")
    s.subagent_records(t(2), SA, AGENT_1, [{"type": "user", "promptId": "<prompt-id>",
                                            "message": {"role": "user", "content": "<text>"}}])
    s.check(contractors=[{"state": "working", "tool": None}])
    s.subagent_records(t(3), SA, AGENT_1, assistant(s, [tool_use("toolu_s1", "Read")], "tool_use"))
    s.check(state="working", tool="Agent", contractors=[{"state": "working", "tool": "Read"}])
    s.subagent_records(t(4), SA, AGENT_1, [tool_result("toolu_s1")]); s.check(contractors=[{"state": "working", "tool": None}])
    s.subagent_records(t(5), SA, AGENT_1, assistant(s, [text()], "end_turn"))
    s.check(contractors=[{"state": "idle", "tool": None}])
    s.records(t(6), SA, [tool_result("toolu_01", result={"agentId": AGENT_1, "<key>": "<tool-output>"})])
    s.check(state="working", tool=None, contractors=[], contractors_ended=1)
    s.records(t(7), SA, assistant(s, [text()], "end_turn") + [turn_done()])
    s.session(t(7), 1001, SA, "idle"); s.check(state="idle")
    s.records(t(10), SA, [prompt()])
    s.session(t(10), 1001, SA, "busy")
    s.records(t(11), SA, assistant(s, [agent_use("toolu_02")], "tool_use"))
    s.check(contractors=[{"state": "working", "tool": None}], contractors_ended=1)
    s.remove(t(20), 1001); s.check(presence="off_duty", contractors=[], contractors_ended=2)
    s.save()


def turn(s, at, session_id, pid, tools=(), **assistant_kw):
    """Prompt, optional tool calls, final answer, and the session file going busy then idle."""
    s.records(t(at), session_id, [prompt()])
    s.session(t(at), pid, session_id, "busy")
    for offset, (tid, name) in enumerate(tools, start=1):
        s.records(t(at + offset), session_id, assistant(s, [tool_use(tid, name)], "tool_use", **assistant_kw))
        s.records(t(at + offset), session_id, [tool_result(tid)])
    s.records(t(at + len(tools) + 1), session_id, assistant(s, [text()], "end_turn", **assistant_kw) + [turn_done()])
    s.session(t(at + len(tools) + 1), pid, session_id, "idle")


def s03(root):
    s = Scenario(root, "S03", "A failing command keeps the Employee working; the retry succeeds")
    s.session(t(0), 1001, SA, "idle"); s.check(state="idle")
    s.records(t(1), SA, [prompt()])
    s.session(t(1), 1001, SA, "busy"); s.check(state="working")
    s.records(t(2), SA, assistant(s, [tool_use("toolu_01", "Bash")], "tool_use")); s.check(state="working", tool="Bash")
    s.records(t(3), SA, [tool_result("toolu_01", error=True, result_as_string=True)])
    s.check(state="working", tool=None, workload=1)
    s.records(t(4), SA, assistant(s, [thinking(), tool_use("toolu_02", "Bash")], "tool_use"))
    s.check(state="working", tool="Bash", workload=2)
    s.records(t(5), SA, [tool_result("toolu_02", error=False, result_as_string=True)]); s.check(state="working", tool=None)
    s.records(t(6), SA, assistant(s, [text()], "end_turn") + [turn_done()])
    s.session(t(6), 1001, SA, "idle")
    s.check(state="idle", states_since_start=["unknown", "idle", "working", "completed", "idle"])
    s.save()


# Not generated: a resume of a session first seen during the same Collector run replays its whole
# history (see the S06 note in docs/fixtures.md). Add s06 to the build list once that is fixed.
def s06(root):
    s = Scenario(root, "S06", "Resume returns to the session's Employee; fork takes a free or new seat")
    s.session(t(0), 1001, SA, "idle", tmux="tmux-1:%1"); s.check(seat=1, ref="a", session_id=SA)
    s.session(t(1), 1002, SB, "idle", tmux="tmux-1:%2"); s.check(seat=2, ref="b", session_id=SB)
    turn(s, 2, SA, 1001)
    turn(s, 5, SB, 1002); s.check(seat=2, state="idle")
    s.remove(t(60), 1001); s.check(seat=1, presence="off_duty", same_as="a")
    s.remove(t(61), 1002); s.check(seat=2, presence="off_duty", same_as="b")
    # --resume SB from the pane seat 1 last used: the session outranks location and the lowest free seat.
    s.session(t(120), 1003, SB, "idle", tmux="tmux-1:%1")
    s.check(pid=1003, seat=2, presence="on_duty", same_as="b", session_id=SB, state="idle")
    s.check(seat=1, presence="off_duty", same_as="a")
    # The resumed session appends to the same transcript; only the new records are read.
    s.records(t(121), SB, [prompt()]); s.check(pid=1003, state="working")
    s.session(t(121), 1003, SB, "busy")
    s.records(t(122), SB, assistant(s, [tool_use("toolu_11", "Read")], "tool_use")); s.check(pid=1003, state="working", tool="Read")
    s.records(t(123), SB, [tool_result("toolu_11")])
    s.records(t(124), SB, assistant(s, [text()], "end_turn") + [turn_done()])
    s.session(t(124), 1003, SB, "idle"); s.check(pid=1003, state="idle", workload=1)
    # --fork-session from SB: a new session id with no reference to SB takes the lowest free seat.
    s.session(t(130), 1004, SD, "idle", tmux="tmux-1:%4")
    s.check(pid=1004, seat=1, presence="on_duty", same_as="a", session_id=SD)
    s.records(t(131), SD, [prompt()]); s.check(pid=1004, state="working")
    s.check(pid=1003, state="idle")
    # A fork while every seat is taken opens a new seat.
    s.session(t(140), 1005, SE, "idle", tmux=None); s.check(pid=1005, seat=3, presence="on_duty", ref="e", session_id=SE)
    s.check(agent_count=3)
    s.save()


def s07(root):
    s = Scenario(root, "S07", "/clear starts a new session in the same process and shift")
    s.session(t(0), 1001, SA, "idle"); s.check(seat=1, ref="a", shift_ref="s", session_id=SA)
    turn(s, 1, SA, 1001, tools=[("toolu_01", "Read")]); s.check(state="idle", workload=1)
    s.session(t(10), 1001, SB, "idle")
    s.check(seat=1, same_as="a", same_shift_as="s", session_id=SB, state="idle", workload=1, agent_count=1)
    s.records(t(11), SB, [prompt()]); s.check(state="working", same_shift_as="s")
    s.session(t(11), 1001, SB, "busy")
    s.records(t(12), SB, assistant(s, [tool_use("toolu_02", "Bash")], "tool_use")); s.check(state="working", tool="Bash", workload=2)
    s.records(t(13), SB, [tool_result("toolu_02")])
    s.records(t(14), SB, assistant(s, [text()], "end_turn") + [turn_done()])
    s.session(t(14), 1001, SB, "idle")
    s.check(state="idle", same_shift_as="s",
            states_since_start=["unknown", "idle", "working", "completed", "idle", "working", "completed", "idle"])
    s.remove(t(20), 1001); s.check(presence="off_duty", same_as="a", agent_count=1)
    s.save()


def s08(root):
    s = Scenario(root, "S08", "Model and effort changes map to conditions by the default rules")
    s.session(t(0), 1001, SA, "idle"); s.check(model=None, effort=None, condition="normal")
    turn(s, 1, SA, 1001); s.check(model="model-a", effort="high", condition="study-mode")
    turn(s, 10, SA, 1001, model="model-c", effort="low"); s.check(model="model-c", effort="low", condition="lazy")
    turn(s, 20, SA, 1001, model="model-c", effort="medium"); s.check(model="model-c", effort="medium", condition="normal")
    turn(s, 30, SA, 1001, model="model-a", effort="xhigh"); s.check(model="model-a", effort="xhigh", condition="study-mode")
    s.save()


def s10(root):
    s = Scenario(root, "S10", "Two concurrent agents in one repository, one in tmux; seats return by runtime location")
    s.session(t(0), 1001, SA, "idle", tmux=None); s.check(seat=1, ref="a", location=None, presence="on_duty")
    s.session(t(1), 1002, SB, "idle", tmux="tmux-1:%1"); s.check(seat=2, ref="b", location="tmux-1:%1", presence="on_duty")
    s.records(t(2), SA, [prompt()])
    s.session(t(2), 1001, SA, "busy"); s.check(seat=1, state="working"); s.check(seat=2, state="idle")
    s.records(t(3), SB, [prompt()])
    s.session(t(3), 1002, SB, "busy")
    s.records(t(4), SB, assistant(s, [tool_use("toolu_01", "Bash")], "tool_use"))
    s.check(seat=1, state="working", tool=None); s.check(seat=2, state="working", tool="Bash")
    s.remove(t(60), 1001); s.check(seat=1, presence="off_duty", same_as="a")
    s.remove(t(61), 1002); s.check(seat=2, presence="off_duty", same_as="b")
    # New sessions after restart: the tmux pane selects seat 2 over the lower free seat 1.
    s.session(t(120), 1003, SC, "idle", tmux="tmux-1:%1"); s.check(pid=1003, seat=2, same_as="b", presence="on_duty")
    s.session(t(121), 1004, SD, "idle", tmux=None); s.check(pid=1004, seat=1, same_as="a", presence="on_duty")
    s.check(agent_count=2)
    s.save()


def s11(root):
    s = Scenario(root, "S11", "An agent outside any repository works in the Common Office")
    s.session(t(0), 1001, SA, "idle", tmux="tmux-1:%1")
    s.check(project="github.com/example/repo", seat=1, ref="r", presence="on_duty")
    s.session(t(1), 1002, SB, "idle", tmux="tmux-1:%2", cwd=OUTSIDE)
    s.check(project="common-office", seat=1, ref="c", presence="on_duty", state="idle")
    s.records(t(2), SB, [prompt()])
    s.session(t(2), 1002, SB, "busy"); s.check(project="common-office", state="working")
    s.records(t(3), SB, assistant(s, [tool_use("toolu_01", "Bash")], "tool_use"))
    s.check(project="common-office", state="working", tool="Bash"); s.check(project="github.com/example/repo", state="idle")
    s.records(t(4), SB, [tool_result("toolu_01")])
    s.records(t(5), SB, assistant(s, [text()], "end_turn") + [turn_done()])
    s.session(t(5), 1002, SB, "idle"); s.check(project="common-office", state="idle", same_as="c")
    s.remove(t(60), 1002); s.check(project="common-office", seat=1, presence="off_duty", same_as="c")
    s.check(project="github.com/example/repo", seat=1, presence="on_duty", same_as="r", agent_count=2)
    s.save()


def s13(root):
    s = Scenario(root, "S13", "API error: error persists through turn end and idle until activity resumes")
    s.session(t(0), 1001, SA, "idle"); s.check(state="idle")
    s.records(t(1), SA, [prompt()])
    s.session(t(1), 1001, SA, "busy"); s.check(state="working")
    s.records(t(2), SA, api_error(s)); s.check(state="error", model=None)
    s.records(t(3), SA, [turn_done()]); s.check(state="error")
    s.session(t(3), 1001, SA, "idle"); s.check(state="error")
    s.records(t(30), SA, [prompt()]); s.check(state="working")
    s.session(t(30), 1001, SA, "busy"); s.check(state="working")
    s.records(t(31), SA, assistant(s, [text()], "end_turn") + [turn_done()])
    s.session(t(31), 1001, SA, "idle")
    s.check(state="idle", model="model-a",
            states_since_start=["unknown", "idle", "working", "error", "working", "completed", "idle"])
    s.records(t(40), SA, [prompt()])
    s.session(t(40), 1001, SA, "busy")
    s.records(t(41), SA, api_error(s)); s.check(state="error", model="model-a")
    s.session(t(41), 1001, SA, "idle"); s.check(state="error")
    s.remove(t(50), 1001); s.check(presence="off_duty")
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
    for build in (s01, s02, s03, s04, s07, s08, s10, s11, s13, s14):
        build(sys.argv[1])
