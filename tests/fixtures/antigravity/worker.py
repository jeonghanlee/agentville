"""Hold a real Antigravity-style presence lock without starting an agent."""

import ctypes
import fcntl
import sys

if ctypes.CDLL(None).prctl(15, b"agy", 0, 0, 0) != 0:
    raise RuntimeError("PR_SET_NAME failed")
with open(sys.argv[1], "a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    print("locked", flush=True)
    sys.stdin.readline()
