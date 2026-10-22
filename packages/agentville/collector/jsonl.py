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
    mid_line: bool = False


class JsonlTail:
    """Yields complete JSON records appended to a file since the last read."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._pos: _Position | None = None

    def seek_end(self) -> None:
        """Skip content already present; a file created later is read from its start."""
        try:
            with open(self.path, "rb") as fh:
                st = os.fstat(fh.fileno())
                fh.seek(max(0, st.st_size - 1))
                mid_line = st.st_size > 0 and fh.read(1) != b"\n"
        except FileNotFoundError:
            return
        self._pos = _Position(st.st_ino, st.st_size, mid_line)

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
        # After seek_end inside a line, resume at the next line boundary.
        cursor = data.find(b"\n") + 1 if self._pos.mid_line else 0
        for line in data[cursor : end + 1].splitlines(keepends=True):
            stripped = line.strip()
            if stripped:
                try:
                    record = json.loads(stripped)
                except ValueError:
                    record = None
                if isinstance(record, dict):
                    yield base + cursor, record
            cursor += len(line)
        self._pos.offset = base + end + 1
        self._pos.mid_line = False
