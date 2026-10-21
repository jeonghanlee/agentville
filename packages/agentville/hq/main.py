"""HQ entry point."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

import uvicorn
import yaml

from agentville.hq.app import create_app
from agentville.hq.store import Store


def data_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "agentville")


def load_tokens(path: str | None) -> dict[str, str]:
    """YAML mapping of branch_id to bearer token; required for non-loopback Branches."""
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        document = yaml.safe_load(fh) or {}
    return {str(k): str(v) for k, v in document.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentville-hq", description="AgentVille HQ")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8470)
    parser.add_argument("--db", help="SQLite path (default: $XDG_DATA_HOME/agentville/hq.sqlite3)")
    parser.add_argument("--tokens", help="YAML file mapping branch_id to bearer token")
    parser.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args(argv)

    db = args.db or os.path.join(data_dir(), "hq.sqlite3")
    os.makedirs(os.path.dirname(db) or ".", exist_ok=True)
    store = Store(db)
    app = create_app(store, load_tokens(args.tokens), retention=timedelta(days=args.retention_days))
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
