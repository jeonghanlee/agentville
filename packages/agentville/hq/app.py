"""HQ HTTP API: Branch ingest and browser-facing state."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from importlib import resources
from typing import Any
from urllib.parse import urlsplit

import jsonschema
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from agentville.common.protocol import load_schema
from agentville.hq.store import Store, now_utc

LOOPBACK = frozenset({"127.0.0.1", "::1"})
LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_BATCH = 1000
MAX_BODY = 4 * 1024 * 1024
LIVE_REFRESH = 10.0
SEND_TIMEOUT = 5.0


def _bearer_matches(request: Request, token: str) -> bool:
    return hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}")


def _hostname(netloc: str) -> str | None:
    try:
        return urlsplit("//" + netloc).hostname
    except ValueError:
        return None


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
    send_timeout: float = SEND_TIMEOUT,
) -> FastAPI:
    """Build the HQ app.

    ``tokens`` maps branch_id to its bearer token. With ``trust_loopback``, a Branch
    connecting from loopback needs no token; disable it behind a local reverse proxy.
    ``viewer_token``, when set, is required on every read endpoint.
    ``hosts`` lists the accepted Host header names (DNS rebinding guard); None accepts any.
    """
    tokens = tokens or {}
    validator = jsonschema.Draft202012Validator(load_schema())
    last_prune: list[datetime] = []

    viewers: set[Any] = set()
    changed = asyncio.Event()

    async def send(socket: Any, message: dict[str, Any]) -> None:
        try:
            await asyncio.wait_for(socket.send_json(message), send_timeout)
        except Exception:  # noqa: BLE001 - a broken or stalled viewer is dropped
            viewers.discard(socket)
            with contextlib.suppress(Exception):
                await socket.close()

    async def broadcast() -> None:
        if not viewers:
            return
        state = await run_in_threadpool(store.state, clock())
        message = {"type": "state", "state": state}
        await asyncio.gather(*(send(socket, message) for socket in list(viewers)))

    async def broadcast_loop() -> None:
        # Ingest only signals a change; bursts coalesce into one broadcast, and
        # reachability and idle progression are refreshed periodically.
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(changed.wait(), live_refresh)
            changed.clear()
            await broadcast()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(broadcast_loop())
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        store.close()

    app = FastAPI(title="AgentVille HQ", version="0.0.1", lifespan=lifespan)
    app.state.viewers = viewers

    def host_allowed(netloc: str) -> bool:
        return hosts is None or _hostname(netloc) in hosts

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

    def ingest_batch(branch_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        for message in messages:
            error = next(validator.iter_errors(message), None)
            if error is not None:
                raise HTTPException(status_code=422, detail=f"schema: {error.message}")
        now = clock()
        if not last_prune or now - last_prune[0] >= timedelta(hours=1):
            store.prune(now - retention)
            last_prune[:] = [now]
        return store.ingest(branch_id, messages, now).as_dict()

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
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
            raise HTTPException(status_code=413, detail="body too large")
        raw = bytearray()
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_BODY:
                raise HTTPException(status_code=413, detail="body too large")
        try:
            body = json.loads(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc
        messages = body.get("messages") if isinstance(body, dict) else None
        if not isinstance(messages, list) or not messages or len(messages) > MAX_BATCH:
            raise HTTPException(status_code=400, detail="messages must be a non-empty list")
        ids = [m.get("branch_id") if isinstance(m, dict) else None for m in messages]
        if not all(isinstance(i, str) for i in ids) or len(set(ids)) != 1:
            raise HTTPException(status_code=400, detail="one branch per batch")
        branch_id = ids[0]
        authorize_branch(request, branch_id)
        result = await run_in_threadpool(ingest_batch, branch_id, messages)
        changed.set()
        return result

    @app.websocket("/ws/v1/live")
    async def live(socket: WebSocket) -> None:
        host = socket.headers.get("host", "")
        origin = socket.headers.get("origin")
        # Browsers apply no CORS to WebSockets; accept only same-origin pages.
        if not host_allowed(host) or (origin is not None and urlsplit(origin).netloc.lower() != host.lower()):
            await socket.close(code=4403)
            return
        if viewer_token is not None and not hmac.compare_digest(socket.query_params.get("token", ""), viewer_token):
            await socket.close(code=4401)
            return
        await socket.accept()
        viewers.add(socket)
        try:
            await socket.send_json({"type": "state", "state": await run_in_threadpool(store.state, clock())})
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            viewers.discard(socket)

    @app.get("/api/v1/state", dependencies=[Depends(authorize_viewer)])
    def state() -> dict[str, Any]:
        return store.state(clock())

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
