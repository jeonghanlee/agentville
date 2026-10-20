"""Incremental JSONL reader that survives rotation, truncation, and partial lines."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


@dataclass
class _Position:
    inode: int
    offset: int


class JsonlTail:
    """Yields complete JSON records appended to a file since the last read."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._pos: _Position | None = None

    def read(self) -> Iterator[tuple[int, dict[str, Any]]]:
        """Yield (byte offset, record) for each new complete line."""
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return
        if self._pos is None or self._pos.inode != st.st_ino or st.st_size < self._pos.offset:
            self._pos = _Position(st.st_ino, 0)
        if st.st_size == self._pos.offset:
            return
        with open(self.path, "rb") as fh:
            fh.seek(self._pos.offset)
            data = fh.read(st.st_size - self._pos.offset)
        end = data.rfind(b"\n")
        if end < 0:
            return
        base = self._pos.offset
        cursor = 0
        for line in data[: end + 1].splitlines(keepends=True):
            stripped = line.strip()
            if stripped:
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    record = None
                if isinstance(record, dict):
                    yield base + cursor, record
            cursor += len(line)
        self._pos.offset = base + end + 1
