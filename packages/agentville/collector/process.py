"""Linux process lifetimes, ancestry, and rollout ownership; all data stays local."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

START_TOLERANCE = 5.0


@dataclass(frozen=True)
class Process:
    pid: int
    parent: int
    start: str
    name: str
    cwd: str | None
    started_at: float | None

    @property
    def identity(self) -> tuple[int, str]:
        return self.pid, self.start


class ProcessTable:
    def __init__(self, root: str = "/proc") -> None:
        self.root = Path(root)
        self.processes: dict[int, Process] = {}

    def refresh(self) -> None:
        try:
            entries = list(self.root.iterdir())
        except OSError:
            entries = []
        boot = None
        try:
            for line in (self.root / "stat").read_text().splitlines():
                if line.startswith("btime "):
                    boot = float(line.split()[1])
                    break
        except (OSError, ValueError, IndexError):
            pass
        ticks = os.sysconf("SC_CLK_TCK")
        processes = {}
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            try:
                text = (entry / "stat").read_text(encoding="ascii", errors="replace")
                close = text.rfind(")")
                fields = text[close + 2:].split()
                if close < 0 or len(fields) < 20 or fields[0] == "Z":
                    continue
                pid, parent, start = int(entry.name), int(fields[1]), fields[19]
                name = text[text.find("(") + 1:close]
                started = boot + int(start) / ticks if boot is not None else None
                try:
                    cwd = os.readlink(entry / "cwd")
                except OSError:
                    cwd = None
                processes[pid] = Process(pid, parent, start, name, cwd, started)
            except (OSError, ValueError, IndexError):
                continue
        self.processes = processes

    def ancestors(self, process: Process):
        seen = {process.pid}
        current = process
        while current.parent not in seen:
            seen.add(current.parent)
            parent = self.processes.get(current.parent)
            if parent is None or int(parent.start) > int(current.start):
                break
            yield parent
            current = parent

    def match_rollout(self, path: str, created: datetime | None, cwd: str) -> Process | None:
        """Prefer a unique open-file owner, then a unique process creation match."""
        owners, candidates = [], []
        target = os.path.realpath(path)
        for process in self.processes.values():
            if process.name != "codex":
                continue
            try:
                descriptors = list((self.root / str(process.pid) / "fd").iterdir())
            except OSError:
                descriptors = []
            for descriptor in descriptors:
                try:
                    if os.readlink(descriptor) == target:
                        owners.append(process)
                        break
                except OSError:
                    continue
            if created is not None and process.started_at is not None:
                timestamp = created.replace(tzinfo=UTC) if created.tzinfo is None else created
                delta = timestamp.timestamp() - process.started_at
                if -1 <= delta <= START_TOLERANCE and (process.cwd is None or process.cwd == cwd):
                    candidates.append(process)
        if owners:
            return owners[0] if len(owners) == 1 else None
        return candidates[0] if len(candidates) == 1 else None

    def observation_identity(self, process: Process) -> dict:
        return {"pid": process.pid, "proc_start": process.start}

    def lock_owners(self) -> dict[tuple[int, int, int], int]:
        """Kernel lock ownership by device and inode; pending locks are excluded."""
        owners = {}
        try:
            lines = (self.root / "locks").read_text().splitlines()
        except OSError:
            return owners
        for line in lines:
            fields = line.split()
            if len(fields) < 6 or fields[1] == "->":
                continue
            try:
                major, minor, inode = fields[5].split(":")
                pid = int(fields[4])
                if pid > 0:
                    owners[(int(major, 16), int(minor, 16), int(inode))] = pid
            except (ValueError, IndexError):
                continue
        return owners
