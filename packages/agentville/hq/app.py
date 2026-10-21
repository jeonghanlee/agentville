"""HQ HTTP API: Branch ingest and browser-facing state."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import jsonschema
from fastapi import FastAPI, HTTPException, Request

from agentville.common.protocol import load_schema
from agentville.hq.store import Store, now_utc

LOOPBACK = frozenset({"127.0.0.1", "::1"})
MAX_BATCH = 1000


def create_app(
    store: Store,
    tokens: dict[str, str] | None = None,
    clock: Callable[[], datetime] = now_utc,
    retention: timedelta = timedelta(days=30),
    loopback: frozenset[str] = LOOPBACK,
) -> FastAPI:
    """``tokens`` maps branch_id to its bearer token; loopback Branches need none."""
    tokens = tokens or {}
    validator = jsonschema.Draft202012Validator(load_schema())
    app = FastAPI(title="AgentVille HQ", version="0.0.1")
    last_prune: list[datetime] = []

    def authorize(request: Request, branch_id: str) -> None:
        expected = tokens.get(branch_id)
        header = request.headers.get("authorization", "")
        if expected is not None:
            if not hmac.compare_digest(header, f"Bearer {expected}"):
                raise HTTPException(status_code=401, detail="invalid token")
            return
        client = request.client.host if request.client else ""
        if client not in loopback:
            raise HTTPException(status_code=401, detail="token required")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/ingest/messages")
    async def ingest(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON") from exc
        messages = body.get("messages") if isinstance(body, dict) else None
        if not isinstance(messages, list) or not messages or len(messages) > MAX_BATCH:
            raise HTTPException(status_code=400, detail="messages must be a non-empty list")
        branch_ids = {m.get("branch_id") if isinstance(m, dict) else None for m in messages}
        if len(branch_ids) != 1 or not isinstance(next(iter(branch_ids)), str):
            raise HTTPException(status_code=400, detail="one branch per batch")
        branch_id = branch_ids.pop()
        authorize(request, branch_id)
        for message in messages:
            error = next(validator.iter_errors(message), None)
            if error is not None:
                raise HTTPException(status_code=422, detail=f"schema: {error.message}")
        now = clock()
        if not last_prune or now - last_prune[0] >= timedelta(hours=1):
            store.prune(now - retention)
            last_prune[:] = [now]
        return store.ingest(branch_id, messages, now).as_dict()

    @app.get("/api/v1/state")
    def state() -> dict[str, Any]:
        return store.state(clock())

    @app.get("/api/v1/branches")
    def branches() -> list[dict[str, Any]]:
        return store.state(clock())["branches"]

    @app.get("/api/v1/agents")
    def agents() -> list[dict[str, Any]]:
        return store.state(clock())["agents"]

    return app
