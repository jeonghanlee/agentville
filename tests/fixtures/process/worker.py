"""A real Linux process tree with synthetic provider names and an open rollout."""

import ctypes
import json
import os
import signal
import sys


def name(value):
    if ctypes.CDLL(None).prctl(15, value.encode(), 0, 0, 0) != 0:
        raise RuntimeError("PR_SET_NAME failed")


def start(pid):
    with open(f"/proc/{pid}/stat") as fh:
        text = fh.read()
    return text[text.rfind(")") + 2:].split()[19]


name("claude")
read_ready, write_ready = os.pipe()
child = os.fork()
if child == 0:
    os.close(read_ready)
    name("codex")
    with open(sys.argv[1], "a"):
        if sys.argv[2] == "private":
            if ctypes.CDLL(None).prctl(4, 0, 0, 0, 0) != 0:
                raise RuntimeError("PR_SET_DUMPABLE failed")
        os.write(write_ready, b"1")
        os.close(write_ready)
        while True:
            signal.pause()
else:
    os.close(write_ready)
    if os.read(read_ready, 1) != b"1":
        raise RuntimeError("child did not become ready")
    os.close(read_ready)
    print(json.dumps({"parent": os.getpid(), "parent_start": start(os.getpid()),
                      "child": child, "child_start": start(child)}), flush=True)
    try:
        for command in sys.stdin:
            if command.strip() == "stop-child":
                os.kill(child, signal.SIGTERM)
                os.waitpid(child, 0)
                child = None
                print("child-stopped", flush=True)
            elif command.strip() == "exit":
                break
    finally:
        if child is not None:
            os.kill(child, signal.SIGTERM)
            os.waitpid(child, 0)
