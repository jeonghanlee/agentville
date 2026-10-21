"""Collector run loop: polls Adapters, feeds the Judge, and emits protocol messages."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, TextIO

from agentville.collector.adapters.claude import ClaudeAdapter
from agentville.collector.adapters.codex import CodexAdapter
from agentville.collector.config import BranchConfig, load_or_create, state_dir
from agentville.collector.judge import Judge, ProjectResolver
from agentville.collector.project import GitProjectResolver
from agentville.collector.sender import Delivery, HttpSender
from agentville.common.observations import Observation
from agentville.common.protocol import Envelope


class Adapter(Protocol):
    def poll(self) -> list[Observation]: ...


Deliver = Callable[[list[dict[str, Any]]], Delivery]

RETRY_MIN = timedelta(seconds=1)
RETRY_MAX = timedelta(seconds=60)


class SeqStore:
    """Persists a reserved upper bound of the per-Branch sequence number.

    A restart resumes after the reserved bound, so numbers may skip but are never reused.
    """

    BLOCK = 1000

    def __init__(self, path: str) -> None:
        self.path = path

    def reserve(self, next_seq: int) -> int:
        bound = next_seq + self.BLOCK - 1
        self.save(bound)
        return bound

    def load(self) -> int:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return int(fh.read().strip() or 0)
        except (OSError, ValueError):
            return 0

    def save(self, seq: int) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(f"{seq}\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)


def build_adapters(config: BranchConfig) -> list[Adapter]:
    adapters: list[Adapter] = []
    if config.claude_home and os.path.isdir(config.claude_home):
        adapters.append(ClaudeAdapter(config.claude_home))
    for entry in config.codex_homes:
        if os.path.isdir(entry.home):
            adapters.append(CodexAdapter(entry.home, account_alias=entry.account_alias))
    return adapters


class Collector:
    def __init__(
        self,
        config: BranchConfig,
        deliver: Deliver,
        adapters: list[Adapter],
        resolver: ProjectResolver,
        seq_store: SeqStore,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.config = config
        self.adapters = adapters
        self._deliver = deliver
        self._clock = clock
        self._seq_store = seq_store
        self._envelope = Envelope(config.host_id, seq_store.load(), reserve=seq_store.reserve)
        self._now = clock()
        self._batch: list[dict[str, Any]] = []
        self._needs_snapshot = True
        self._retry_at: datetime | None = None
        self._retry_delay = RETRY_MIN
        self._last_heartbeat: datetime | None = None
        self.judge = Judge(
            resolver,
            self._emit_judge,
            leave_after=timedelta(seconds=config.thresholds["leave"]),
            condition_for=config.condition_for,
        )

    def _send(self, kind: str, at: datetime, payload: dict[str, Any]) -> None:
        self._batch.append(self._envelope.wrap(kind, at, payload, self._now))

    def _emit_judge(self, kind: str, at: datetime, payload: dict[str, Any]) -> None:
        # While a snapshot is pending, individual changes are superseded by it.
        if not self._needs_snapshot:
            self._send(kind, at, payload)

    def tick(self) -> None:
        self._now = self._clock()
        for adapter in self.adapters:
            try:
                observations = adapter.poll()
            except Exception as exc:  # noqa: BLE001 - one failing provider must not stop the others
                self._log(f"{type(adapter).__name__}: {type(exc).__name__}: {exc}")
                continue
            for obs in observations:
                self.judge.apply(obs)
        self.judge.refresh_presence(self._now)
        if self._retry_at is not None and self._now < self._retry_at:
            return
        if self._needs_snapshot:
            self.send_snapshot()
        interval = timedelta(seconds=self.config.heartbeat_interval)
        if self._last_heartbeat is None or self._now - self._last_heartbeat >= interval:
            self._send("heartbeat", self._now, {"interval": self.config.heartbeat_interval})
            self._last_heartbeat = self._now
        self._flush()

    def _flush(self) -> None:
        if not self._batch:
            return
        batch, self._batch = self._batch, []
        result = self._deliver(batch)
        if not result.ok:
            # Changes are not queued across a disconnection; the next contact starts with a snapshot.
            self._log(f"delivery failed: {result.error}")
            self._needs_snapshot = True
            self._retry_at = self._now + self._retry_delay
            self._retry_delay = min(self._retry_delay * 2, RETRY_MAX)
            return
        self._retry_at = None
        self._retry_delay = RETRY_MIN
        self._needs_snapshot = result.need_snapshot

    @staticmethod
    def _log(text: str) -> None:
        print(f"agentville-collector: {text}", file=sys.stderr, flush=True)

    def send_snapshot(self) -> None:
        agents, activities = self.judge.snapshot(self._now)
        self._batch.clear()
        self._needs_snapshot = False
        self._send(
            "snapshot",
            self._now,
            {"branch": self.config.branch_payload(), "agents": agents, "activities": activities, "contractors": []},
        )

    def close(self) -> None:
        for adapter in self.adapters:
            close = getattr(adapter, "close", None)
            if close is not None:
                close()


def jsonl_deliver(stream: TextIO) -> Deliver:
    def write(messages: list[dict[str, Any]]) -> Delivery:
        for message in messages:
            stream.write(json.dumps(message, separators=(",", ":")) + "\n")
        stream.flush()
        return Delivery(True)

    return write


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentville-collector", description="AgentVille Branch Collector")
    parser.add_argument("--config", help="configuration file (default: $XDG_CONFIG_HOME/agentville/config.yaml)")
    parser.add_argument("--output", help="write JSONL messages to this path (- for stdout) instead of sending to HQ")
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    args = parser.parse_args(argv)

    config = load_or_create(args.config)
    stop = False

    def request_stop(signum: int, frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    stream: TextIO | None = None
    if args.output == "-":
        deliver: Deliver = jsonl_deliver(sys.stdout)
    elif args.output:
        stream = open(args.output, "a", encoding="utf-8")
        deliver = jsonl_deliver(stream)
    else:
        deliver = HttpSender(config.hq_url, config.hq_token)
    collector: Collector | None = None
    try:
        collector = Collector(
            config,
            deliver,
            build_adapters(config),
            GitProjectResolver(config.host_id),
            SeqStore(os.path.join(state_dir(), "seq")),
        )
        while True:
            collector.tick()
            if args.once or stop:
                break
            time.sleep(config.poll_interval)
            if stop:
                break
    finally:
        if collector is not None:
            collector.close()
        if stream is not None:
            stream.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
