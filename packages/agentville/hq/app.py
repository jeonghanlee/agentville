"""HQ HTTP API: Branch ingest and browser-facing state."""

from __future__ import annotations

import hmac
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import jsonschema
from fastapi import Depends, FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from agentville.common.protocol import load_schema
from agentville.hq.store import Store, now_utc

LOOPBACK = frozenset({"127.0.0.1", "::1"})
MAX_BATCH = 1000
MAX_BODY = 4 * 1024 * 1024


def _bearer_matches(request: Request, token: str) -> bool:
    return hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}")


def create_app(
    store: Store,
    tokens: dict[str, str] | None = None,
    clock: Callable[[], datetime] = now_utc,
    retention: timedelta = timedelta(days=30),
    loopback: frozenset[str] = LOOPBACK,
    trust_loopback: bool = True,
    viewer_token: str | None = None,
) -> FastAPI:
    """Build the HQ app.

    ``tokens`` maps branch_id to its bearer token. With ``trust_loopback``, a Branch
    connecting from loopback needs no token; disable it behind a local reverse proxy.
    ``viewer_token``, when set, is required on every read endpoint.
    """
    tokens = tokens or {}
    validator = jsonschema.Draft202012Validator(load_schema())
    last_prune: list[datetime] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        store.close()

    app = FastAPI(title="AgentVille HQ", version="0.0.1", lifespan=lifespan)

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
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
            raise HTTPException(status_code=413, detail="body too large")
        raw = await request.body()
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
        return await run_in_threadpool(ingest_batch, branch_id, messages)

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

    return app
