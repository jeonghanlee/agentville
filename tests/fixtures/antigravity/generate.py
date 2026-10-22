"""Generate synthetic activity records in the observed agy 1.4.5 format."""

import json
import sys
from pathlib import Path


def generate(root):
    destination = Path(root) / "antigravity/1.4.5/S01"
    destination.mkdir(parents=True, exist_ok=True)
    command = {"name": "run_command", "args": {"CommandLine": "true", "Cwd": "/home/user/repo"}}
    steps = [
        (0, "USER_INPUT", "USER_EXPLICIT", "DONE", {"content": "<text>"}),
        (1, "GENERIC", "MODEL", "RUNNING", {"tool_calls": [command]}),
        (1, "GENERIC", "MODEL", "DONE", {"tool_calls": [command], "content": "<tool-output>"}),
        (2, "PLANNER_RESPONSE", "MODEL", "DONE", {"content": "<text>"}),
        (3, "ERROR_MESSAGE", "SYSTEM", "ERROR", {"content": "<error>"}),
    ]
    with (destination / "transcript.jsonl").open("w") as fh:
        for second, (step, kind, source, status, data) in enumerate(steps):
            record = {"created_at": f"2026-01-01T00:00:{second:02d}Z", "step_index": step,
                      "type": kind, "source": source, "status": status, **data}
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    generate(sys.argv[1])
