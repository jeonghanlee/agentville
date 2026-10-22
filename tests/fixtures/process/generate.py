"""Generate a synthetic cross-provider S05 and its process ancestry."""

import json
import sys
from pathlib import Path


def generate(root):
    directory = Path(root) / "process/S05"
    directory.mkdir(parents=True, exist_ok=True)
    thread = "019a0000-0000-7000-8000-000000000005"
    fixture = {
        "description": "Claude launches codex exec through a shell; the child runs a tool and exits.",
        "parent": {"sessionId": "55555555-5555-4555-8555-555555555555", "status": "busy", "kind": "interactive"},
        "thread_id": thread,
        "boot_epoch": 1767215600,
        "nested_process": {"pid": 3001, "parent": 2001, "start": 1000030, "name": "claude"},
        "processes": [
            {"pid": 1001, "parent": 1, "start": 1000000, "name": "claude"},
            {"pid": 1501, "parent": 1001, "start": 1000010, "name": "sh"},
            {"pid": 2001, "parent": 1501, "start": 1000020, "name": "codex"},
        ],
        "rollout_records": [
            {"type": "session_meta", "payload": {"id": thread, "source": "exec", "cli_version": "0.163.0"}},
            {"type": "event_msg", "payload": {"type": "task_started"}},
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "call-s05",
                                                   "name": "exec_command", "arguments": '{"cmd":"true"}'}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-s05",
                                                   "output": "Process exited with code 0"}},
            {"type": "event_msg", "payload": {"type": "task_complete"}},
        ],
    }
    (directory / "scenario.json").write_text(json.dumps(fixture, indent=2) + "\n")


if __name__ == "__main__":
    generate(sys.argv[1])
