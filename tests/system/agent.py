"""Publish synthetic Claude presence from a real process inside a test container."""

import ctypes
import json
import os
import signal
from pathlib import Path

if ctypes.CDLL(None).prctl(15, b"claude", 0, 0, 0) != 0:
    raise RuntimeError("PR_SET_NAME failed")
text = Path(f"/proc/{os.getpid()}/stat").read_text()
start = text[text.rfind(")") + 2:].split()[19]
sessions = Path.home() / ".claude/sessions"
sessions.mkdir(parents=True, exist_ok=True)
document = {"pid": os.getpid(), "procStart": start, "sessionId": "33333333-3333-4333-8333-333333333333",
            "cwd": "/workspace/agentville", "status": "idle", "kind": "interactive"}
(sessions / f"{os.getpid()}.json").write_text(json.dumps(document))
while True:
    signal.pause()
