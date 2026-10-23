"""HQ HTTP API: Branch ingest and browser-facing state."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import math
import threading
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import Any
from urllib.parse import urlsplit

import jsonschema
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from agentville import version
from agentville.common.protocol import iso, load_schema
from agentville.hq.notify import Notifier
from agentville.hq.store import Store, now_utc

log = logging.getLogger(__name__)

LOOPBACK = frozenset({"127.0.0.1", "::1"})
LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_BATCH = 1000
MAX_BODY = 4 * 1024 * 1024
MAX_CLOSE_BODY = 4096
MIN_ADMIN_TOKEN = 16
LIVE_REFRESH = 10.0
SEND_TIMEOUT = 5.0
AUTH_TIMEOUT = 5.0
# Seconds between notification evaluations without ingest; reachability changes with time alone.
NOTIFY_INTERVAL = 5.0
# Longest period one changes or work log request may cover.
MAX_RANGE = timedelta(days=31)
# Changes and work log responses are kept this many seconds, for this many distinct requests, and at most this many
# are computed at once, so history reads never take every worker thread from ingest and the live state.
HISTORY_TTL = 30.0
HISTORY_ENTRIES = 32
HISTORY_WORKERS = 2


def _bearer_matches(request: Request, token: str) -> bool:
    return hmac.compare_digest(request.headers.get("authorization", "").encode(), f"Bearer {token}".encode())


def _hostname(netloc: str) -> str | None:
    try:
        return urlsplit("//" + netloc).hostname
    except ValueError:
        return None


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name}")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("non-finite number")
    return value


_FORMATS = jsonschema.FormatChecker(formats=())


@_FORMATS.checks("date-time", raises=ValueError)
def _date_time(value: object) -> bool:
    if not isinstance(value, str):
        return True
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return False
    try:
        # A time whose UTC form falls outside the datetime range is not a usable time.
        parsed.astimezone(UTC)
    except OverflowError:
        return False
    return True


def _time(value: str | None, name: str) -> datetime:
    """An ISO 8601 query time with an explicit offset, as UTC."""
    if not value:
        raise HTTPException(status_code=400, detail=f"{name} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name} must be an ISO 8601 time") from None
    if parsed.tzinfo is None:
        raise HTTPException(status_code=400, detail=f"{name} must include a time zone")
    try:
        return parsed.astimezone(UTC)
    except OverflowError:
        raise HTTPException(status_code=400, detail=f"{name} is out of range") from None


def _period(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    first, last = _time(start, "from"), _time(end, "to")
    if last <= first:
        raise HTTPException(status_code=400, detail="to must be later than from")
    if last - first > MAX_RANGE:
        raise HTTPException(status_code=400, detail=f"the period must not exceed {MAX_RANGE.days} days")
    return first, last


def _encode_state(state: dict[str, Any]) -> str:
    return json.dumps({"type": "state", "state": state}, allow_nan=False, separators=(",", ":"))


class _Results:
    """Recent history responses by request; concurrent identical requests share one computation."""

    def __init__(self, ttl: float, size: int, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._ttl, self._size, self._monotonic = ttl, size, monotonic
        self._entries: OrderedDict[tuple[Any, ...], tuple[float, asyncio.Future[Any]]] = OrderedDict()

    async def get(self, key: tuple[Any, ...], compute: Callable[[], Awaitable[Any]]) -> Any:
        now = self._monotonic()
        entry = self._entries.get(key)
        if entry is None or entry[0] <= now:
            entry = (now + self._ttl, asyncio.ensure_future(compute()))
            self._entries[key] = entry
            while len(self._entries) > self._size:
                self._entries.popitem(last=False)
        self._entries.move_to_end(key)
        try:
            return await asyncio.shield(entry[1])
        except Exception:
            # A failure is not kept.
            if self._entries.get(key) is entry:
                del self._entries[key]
            raise

    def invalidate(self) -> None:
        self._entries.clear()


class _Viewer:
    """One live socket with a single-slot mailbox holding the latest state."""

    def __init__(self, socket: WebSocket) -> None:
        self.socket = socket
        self.latest: str | None = None
        self.ready = asyncio.Event()

    def offer(self, text: str) -> None:
        self.latest = text
        self.ready.set()


def create_app(
    store: Store,
    tokens: dict[str, str] | None = None,
    clock: Callable[[], datetime] = now_utc,
    retention: timedelta = timedelta(days=30),
    loopback: frozenset[str] = LOOPBACK,
    trust_loopback: bool = True,
    viewer_token: str | None = None,
    live_refresh: float = LIVE_REFRESH,
    hosts: frozenset[str] | None = LOCAL_HOSTS,
    server_names: frozenset[str] = frozenset(),
    send_timeout: float = SEND_TIMEOUT,
    auth_timeout: float = AUTH_TIMEOUT,
    notifier: Notifier | None = None,
    notify_interval: float = NOTIFY_INTERVAL,
    admin_token: str | None = None,
) -> FastAPI:
    """Build the HQ app.

    ``tokens`` maps branch_id to its bearer token. With ``trust_loopback``, a Branch
    connecting from loopback needs no token; disable it behind a local reverse proxy.
    ``viewer_token``, when set, is required on every read endpoint, and on the live
    socket as its first message ``{"type": "auth", "token": ...}`` within ``auth_timeout``.
    ``hosts`` lists the accepted Host header names (DNS rebinding guard); None accepts any.
    ``server_names`` are public names of a reverse proxy, accepted as Host and as page Origin.
    ``notifier``, when set, is evaluated after each ingest and every ``notify_interval`` seconds.
    """
    tokens = tokens or {}
    if admin_token is not None and (
        not admin_token.isascii() or len(admin_token) < MIN_ADMIN_TOKEN or any(c.isspace() for c in admin_token)
        or admin_token == viewer_token or admin_token in tokens.values()
    ):
        raise ValueError("administrator token must be distinct, ASCII, without whitespace, and at least 16 characters")
    validator = jsonschema.Draft202012Validator(load_schema(), format_checker=_FORMATS)
    last_prune: list[datetime] = []

    viewers: set[_Viewer] = set()
    changed = asyncio.Event()
    results = _Results(HISTORY_TTL, HISTORY_ENTRIES)
    workers = asyncio.Semaphore(HISTORY_WORKERS)
    # Evaluations run one at a time, each on the state and resyncs it read, so none announces a resync's changes.
    evaluating = threading.Lock()

    async def broadcast() -> None:
        if not viewers:
            return
        text = _encode_state(await run_in_threadpool(store.state, clock()))
        for viewer in list(viewers):
            viewer.offer(text)

    async def broadcast_loop() -> None:
        # Ingest only signals a change; bursts coalesce into one broadcast, and
        # reachability and idle progression are refreshed periodically.
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(changed.wait(), live_refresh)
            changed.clear()
            try:
                await broadcast()
            except Exception:  # noqa: BLE001 - the loop must outlive one failed refresh
                log.exception("live broadcast failed")

    async def deliver(viewer: _Viewer) -> None:
        # Each viewer has its own sender, so a stalled one never delays the others.
        while True:
            await viewer.ready.wait()
            viewer.ready.clear()
            text, viewer.latest = viewer.latest, None
            if text is not None:
                await asyncio.wait_for(viewer.socket.send_text(text), send_timeout)

    async def authenticated(socket: WebSocket) -> bool:
        assert viewer_token is not None
        try:
            message = await asyncio.wait_for(socket.receive(), auth_timeout)
            data = json.loads(message.get("text") or "")
        except (TimeoutError, ValueError):
            return False
        token = data.get("token") if isinstance(data, dict) and data.get("type") == "auth" else None
        return isinstance(token, str) and hmac.compare_digest(token.encode(), viewer_token.encode())

    def evaluate() -> None:
        assert notifier is not None
        try:
            with evaluating:
                now = clock()
                state, heard, resynced = store.observe(now)
                notifier.observe(state, heard, now, resynced)
        except Exception:  # noqa: BLE001 - notifications never affect ingest
            log.exception("notification evaluation failed")

    async def notify_loop() -> None:
        while True:
            await run_in_threadpool(evaluate)
            await asyncio.sleep(notify_interval)

    async def drain(socket: WebSocket) -> None:
        while (await socket.receive())["type"] != "websocket.disconnect":
            pass

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if notifier is not None:
            await run_in_threadpool(evaluate)
        tasks = [asyncio.create_task(broadcast_loop())]
        if notifier is not None:
            tasks.append(asyncio.create_task(notify_loop()))
        yield
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        store.close()

    app = FastAPI(title="AgentVille HQ", version=version(), lifespan=lifespan)

    def host_allowed(netloc: str) -> bool:
        return hosts is None or _hostname(netloc) in hosts | server_names

    def origin_allowed(origin: str, host: str) -> bool:
        try:
            parts = urlsplit(origin)
            return parts.netloc.lower() == host.lower() or parts.hostname in server_names
        except ValueError:
            return False

    @app.middleware("http")
    async def check_host(request: Request, call_next: Callable[[Request], Any]) -> Any:
        if not host_allowed(request.headers.get("host", "")):
            return PlainTextResponse("invalid host", status_code=400)
        return await call_next(request)

    def authorize_branch(request: Request, branch_id: str) -> None:
        expected = tokens.get(branch_id)
        if expected is not None:
            if not _bearer_matches(request, expected):
                raise HTTPException(status_code=401, detail="invalid token")
            return
        client = request.client.host if request.client else ""
        if not (trust_loopback and client in loopback):
            raise HTTPException(status_code=401, detail="token required")

    def authorize_viewer(request: Request) -> None:
        if viewer_token is not None and not _bearer_matches(request, viewer_token):
            raise HTTPException(status_code=401, detail="viewer token required")

    def authorize_admin(request: Request) -> None:
        if admin_token is None:
            raise HTTPException(status_code=503, detail="administrator token is not configured")
        if not _bearer_matches(request, admin_token):
            raise HTTPException(status_code=401, detail="administrator token required")

    @app.post("/api/v1/lifecycle/close", dependencies=[Depends(authorize_admin)])
    async def close_record(request: Request) -> dict[str, Any]:
        origin = request.headers.get("origin")
        if origin is not None and not origin_allowed(origin, request.headers.get("host", "")):
            raise HTTPException(status_code=403, detail="invalid origin")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(status_code=415, detail="application/json required")
        raw = bytearray()
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_CLOSE_BODY:
                raise HTTPException(status_code=413, detail="body too large")
        try:
            body = json.loads(raw)
        except (ValueError, RecursionError):
            raise HTTPException(status_code=400, detail="invalid JSON") from None
        if (not isinstance(body, dict) or set(body) != {"kind", "id"}
                or body["kind"] not in ("branch", "project") or not isinstance(body["id"], str) or not body["id"]):
            raise HTTPException(status_code=400, detail="kind and id are required")
        try:
            value = await run_in_threadpool(store.close_record, body["kind"], body["id"], clock())
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown lifecycle target") from None
        changed.set()
        results.invalidate()
        if notifier is not None:
            await run_in_threadpool(evaluate)
        return value

    def ingest_batch(branch_id: str, messages: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
        for message in messages:
            error = next(validator.iter_errors(message), None)
            if error is not None:
                raise HTTPException(status_code=422, detail=f"schema: {error.message}")
        now = clock()
        if not last_prune or now - last_prune[0] >= timedelta(hours=1):
            store.prune(now - retention)
            last_prune[:] = [now]
        result = store.ingest(branch_id, messages, now)
        if notifier is not None:
            # Changes revealed by a snapshot are a resync, not transitions; the store hands the resync to
            # whichever evaluation first reads the snapshot's state.
            evaluate()
        return result.as_dict(), result.lifecycle_changed

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/ingest/messages")
    async def ingest(request: Request) -> dict[str, Any]:
        # Collectors send no Origin; a browser always does on cross-site POST.
        if "origin" in request.headers:
            raise HTTPException(status_code=403, detail="browser requests are not accepted")
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(status_code=415, detail="application/json required")
        # Authorization needs the batch's branch_id; reject callers holding no known token before reading it.
        client = request.client.host if request.client else ""
        if not (trust_loopback and client in loopback) and not any(_bearer_matches(request, t) for t in tokens.values()):
            raise HTTPException(status_code=401, detail="invalid token" if "authorization" in request.headers else "token required")
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
            raise HTTPException(status_code=413, detail="body too large")
        raw = bytearray()
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_BODY:
                raise HTTPException(status_code=413, detail="body too large")
        try:
            body = json.loads(raw, parse_constant=_reject_constant, parse_float=_finite_float)
        except (ValueError, RecursionError) as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc
        messages = body.get("messages") if isinstance(body, dict) else None
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail="messages must be a non-empty list")
        if len(messages) > MAX_BATCH:
            raise HTTPException(status_code=413, detail=f"at most {MAX_BATCH} messages per batch")
        ids = [m.get("branch_id") if isinstance(m, dict) else None for m in messages]
        if not all(isinstance(i, str) for i in ids) or len(set(ids)) != 1:
            raise HTTPException(status_code=400, detail="one branch per batch")
        branch_id = ids[0]
        authorize_branch(request, branch_id)
        result, lifecycle_changed = await run_in_threadpool(ingest_batch, branch_id, messages)
        if lifecycle_changed:
            results.invalidate()
        changed.set()
        return result

    @app.websocket("/ws/v1/live")
    async def live(socket: WebSocket) -> None:
        host = socket.headers.get("host", "")
        origin = socket.headers.get("origin")
        # Browsers apply no CORS to WebSockets; accept only same-origin pages.
        # Rejections are sent after accept() so the page receives the close code.
        allowed = host_allowed(host) and (origin is None or origin_allowed(origin, host))
        await socket.accept()
        if not allowed:
            await socket.close(code=4403)
            return
        # The viewer token comes in the first message, never in the URL; no state is sent before it.
        if viewer_token is not None and not await authenticated(socket):
            with contextlib.suppress(Exception):
                await socket.close(code=4401)
            return
        viewer = _Viewer(socket)
        viewer.offer(_encode_state(await run_in_threadpool(store.state, clock())))
        viewers.add(viewer)
        sender = asyncio.create_task(deliver(viewer))
        receiver = asyncio.create_task(drain(socket))
        try:
            await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            viewers.discard(viewer)
            sender.cancel()
            receiver.cancel()
        if receiver.done() and not receiver.cancelled():
            receiver.exception()
        if sender.done() and not sender.cancelled() and sender.exception() is not None:
            # A stalled or broken viewer; closing must not hang this handler either.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(socket.close(), 1.0)

    async def read_history(compute: Callable[..., dict[str, Any]], *args: Any) -> dict[str, Any]:
        async with workers:
            return await run_in_threadpool(compute, *args)

    @app.get("/api/v1/state", dependencies=[Depends(authorize_viewer)])
    async def state(at: str | None = None) -> dict[str, Any]:
        if at is None:
            return await run_in_threadpool(store.state, clock())
        when = _time(at, "at")
        start, now = store.history_range(clock())
        if start is None or not start <= when <= now:
            raise HTTPException(status_code=400, detail="at is outside the kept history")
        return await read_history(store.state_at, when)

    @app.get("/api/v1/history", dependencies=[Depends(authorize_viewer)])
    def history() -> dict[str, Any]:
        start, now = store.history_range(clock())
        return {"from": iso(start) if start else None, "to": iso(now)}

    @app.get("/api/v1/changes", dependencies=[Depends(authorize_viewer)])
    async def changes(start: str | None = Query(None, alias="from"), end: str | None = Query(None, alias="to"),
                      branch_id: str | None = None) -> dict[str, Any]:
        first, last = _period(start, end)
        return await results.get(("changes", first, last, branch_id),
                                 lambda: read_history(store.changes, first, last, clock(), branch_id))

    @app.get("/api/v1/worklog", dependencies=[Depends(authorize_viewer)])
    async def worklog(start: str | None = Query(None, alias="from"), end: str | None = Query(None, alias="to"),
                      branch_id: str | None = None) -> dict[str, Any]:
        first, last = _period(start, end)
        return await results.get(("worklog", first, last, branch_id),
                                 lambda: read_history(store.worklog, first, last, clock(), branch_id))

    @app.get("/api/v1/branches", dependencies=[Depends(authorize_viewer)])
    def branches() -> list[dict[str, Any]]:
        return store.state(clock())["branches"]

    @app.get("/api/v1/agents", dependencies=[Depends(authorize_viewer)])
    def agents() -> list[dict[str, Any]]:
        return store.state(clock())["agents"]

    @app.get("/api/v1/stats", dependencies=[Depends(authorize_viewer)])
    def stats() -> dict[str, Any]:
        return {"ingest": store.totals.as_dict()}

    web = resources.files("agentville.hq").joinpath("web")
    app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
    return app
