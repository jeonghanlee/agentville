"""Employee roster persisted across Collector restarts."""

from __future__ import annotations

import json
import os
from typing import Any


def atomic_write(path: str, text: str) -> None:
    """Replace ``path`` with ``text`` durably; the file is private to the owner."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    tmp = f"{path}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Roster:
    """JSON list of Employee records; an unreadable file starts an empty roster."""

    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> list[dict[str, Any]]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                records = json.load(fh)
        except (OSError, ValueError):
            return []
        return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []

    def save(self, records: list[dict[str, Any]]) -> None:
        atomic_write(self.path, json.dumps(records, separators=(",", ":")) + "\n")
