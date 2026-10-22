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

from agentville import version
from agentville.collector.adapters.claude import ClaudeAdapter
from agentville.collector.adapters.antigravity import AntigravityAdapter
from agentville.collector.adapters.codex import CodexAdapter
from agentville.collector.config import BranchConfig, load_or_create, state_dir
from agentville.collector.judge import Judge, ProjectResolver
from agentville.collector.project import GitProjectResolver
from agentville.collector.roster import Roster, atomic_write
from agentville.collector.sender import Delivery, HttpSender, SHARED_HOST_WARNING
from agentville.common.observations import Observation
from agentville.common.protocol import Envelope


class Adapter(Protocol):
    def poll(self) -> list[Observation]: ...


Deliver = Callable[[list[dict[str, Any]]], Delivery]

RETRY_MIN = timedelta(seconds=1)
RETRY_MAX = timedelta(seconds=60)
IDENTITY_WARNING_INTERVAL = timedelta(minutes=1)


class SeqStore:
    """Persists a reserved upper bound of the per-Branch sequence number.

    A restart resumes after the reserved bound, so numbers may skip but are never reused.
    """

    BLOCK = 1000

    def __init__(self, path: str, readonly: bool = False) -> None:
        self.path = path
        self.readonly = readonly

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
        if not self.readonly:
            atomic_write(self.path, f"{seq}\n")


def build_adapters(config: BranchConfig) -> list[Adapter]:
    adapters: list[Adapter] = []
    for entry in config.claude_homes:
        if os.path.isdir(entry.home):
            adapters.append(ClaudeAdapter(entry.home, account_alias=entry.account_alias))
    for entry in config.codex_homes:
        if os.path.isdir(entry.home):
            adapters.append(CodexAdapter(entry.home, account_alias=entry.account_alias))
    for entry in config.antigravity_homes:
        if os.path.isdir(os.path.join(entry.home, "antigravity-cli")):
            adapters.append(AntigravityAdapter(entry.home, account_alias=entry.account_alias))
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
        roster: Roster | None = None,
        proc_root: str = "/proc",
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
        self._last_identity_warning: datetime | None = None
        self.judge = Judge(
            resolver,
            self._emit_judge,
            leave_after=timedelta(seconds=config.thresholds["leave"]),
            condition_for=config.condition_for,
            save=self._save_roster,
            alias_for=config.aliases.get,
            proc_root=proc_root,
        )
        self._roster = roster
        if roster is not None:
            self.judge.restore(roster.load(), self._now)

    def _save_roster(self, records: list[dict[str, Any]]) -> None:
        if self._roster is None:
            return
        try:
            self._roster.save(records)
        except OSError as exc:
            self._log(f"roster not saved: {exc}")

    def _send(self, kind: str, at: datetime, payload: dict[str, Any]) -> None:
        self._batch.append(self._envelope.wrap(kind, at, payload, self._now))

    def _emit_judge(self, kind: str, at: datetime, payload: dict[str, Any]) -> None:
        # While a snapshot is pending, individual changes are superseded by it.
        if not self._needs_snapshot:
            self._send(kind, at, payload)

    def tick(self) -> None:
        self._now = self._clock()
        pending: list[Observation] = []
        for adapter in self.adapters:
            try:
                observations = adapter.poll()
            except Exception as exc:  # noqa: BLE001 - one failing provider must not stop the others
                self._log(f"{type(adapter).__name__}: {type(exc).__name__}: {exc}")
                continue
            pending.extend(observations)
        self.judge.apply_batch(pending)
        self.judge.refresh_presence(self._now)
        self.judge.refresh_workload(self._now)
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
        if result.shared_host_id and (self._last_identity_warning is None
                                      or self._now - self._last_identity_warning >= IDENTITY_WARNING_INTERVAL):
            self._log(SHARED_HOST_WARNING)
            self._last_identity_warning = self._now
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
        agents, activities, contractors = self.judge.snapshot(self._now)
        self._batch.clear()
        self._needs_snapshot = False
        self._send(
            "snapshot",
            self._now,
            {"branch": self.config.branch_payload(), "agents": agents, "activities": activities,
             "contractors": contractors},
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
    parser.add_argument("--version", action="version", version=f"%(prog)s {version()}")
    parser.add_argument("--config", help="configuration file (default: $XDG_CONFIG_HOME/agentville/config.yaml)")
    parser.add_argument("--output", help="write JSONL messages to this path (- for stdout) instead of sending to HQ")
    parser.add_argument("--once", action="store_true", help="poll once and exit")
    args = parser.parse_args(argv)

    try:
        config = load_or_create(args.config)
    except ValueError as exc:
        raise SystemExit(f"agentville-collector: invalid configuration: {exc}") from None
    except OSError as exc:
        raise SystemExit(f"agentville-collector: configuration {exc.filename or args.config}: {exc.strerror or exc}") from None
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
        try:
            deliver = HttpSender(config.hq_url, config.hq_token)
        except ValueError as exc:
            raise SystemExit(f"agentville-collector: hq.url {config.hq_url}: {exc}") from None
    target = args.output or config.hq_url
    print(f"agentville-collector: Branch {config.alias} ({config.host_id}) reporting to {target}", file=sys.stderr, flush=True)
    collector: Collector | None = None
    try:
        collector = Collector(
            config,
            deliver,
            build_adapters(config),
            GitProjectResolver(config.host_id),
            # Diagnostic output starts from the stored state but never writes it back.
            SeqStore(os.path.join(state_dir(), "seq"), readonly=bool(args.output)),
            roster=Roster(os.path.join(state_dir(), "roster.json"), readonly=bool(args.output)),
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
