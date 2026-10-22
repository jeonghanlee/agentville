"""HQ entry point."""

from __future__ import annotations

import argparse
import ipaddress
import os
import stat
import sys
from datetime import timedelta

import uvicorn
import yaml

from agentville.hq.app import LOCAL_HOSTS, create_app
from agentville.hq.store import Store


MIN_TOKEN = 16


def data_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "agentville")


def _read_private(path: str) -> str:
    if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
        raise SystemExit(f"agentville-hq: {path} must not be accessible by group or others (chmod 600)")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def load_tokens(path: str | None) -> dict[str, str]:
    """YAML mapping of branch_id to bearer token, from a file private to the owner."""
    if not path:
        return {}
    document = yaml.safe_load(_read_private(path)) or {}
    if not isinstance(document, dict):
        raise SystemExit(f"agentville-hq: {path} must be a mapping of branch_id to token")
    tokens = {}
    for branch_id, token in document.items():
        if not isinstance(token, str) or len(token) < MIN_TOKEN:
            raise SystemExit(f"agentville-hq: token for {branch_id} must be a string of at least {MIN_TOKEN} characters")
        tokens[str(branch_id)] = token
    return tokens


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentville-hq", description="AgentVille HQ")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8470)
    parser.add_argument("--db", help="SQLite path (default: $XDG_DATA_HOME/agentville/hq.sqlite3)")
    parser.add_argument("--tokens", help="YAML file mapping branch_id to bearer token")
    parser.add_argument("--viewer-token-file", help="file holding the bearer token required on read endpoints")
    parser.add_argument("--allow-remote", action="store_true", help="permit binding to a non-loopback address")
    parser.add_argument("--no-trust-loopback", action="store_true", help="require tokens from loopback Branches too (reverse proxy)")
    parser.add_argument("--server-name", action="append", default=[],
                        help="public name of a reverse proxy, accepted as Host and page Origin; repeatable")
    parser.add_argument("--tls-cert", help="PEM certificate file; serve HTTPS (with --tls-key)")
    parser.add_argument("--tls-key", help="PEM private key file for --tls-cert")
    parser.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args(argv)
    if bool(args.tls_cert) != bool(args.tls_key):
        parser.error("--tls-cert and --tls-key are used together")

    remote = not is_loopback(args.host)
    viewer_token = (_read_private(args.viewer_token_file).strip() or None) if args.viewer_token_file else None
    if remote and not (args.allow_remote and viewer_token):
        parser.error("a non-loopback --host requires --allow-remote and --viewer-token-file")
    if args.server_name and not (args.no_trust_loopback and viewer_token):
        parser.error("--server-name requires --no-trust-loopback and --viewer-token-file")

    db = args.db or os.path.join(data_dir(), "hq.sqlite3")
    directory = os.path.dirname(db) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    store = Store(db)
    app = create_app(
        store,
        load_tokens(args.tokens),
        retention=timedelta(days=args.retention_days),
        trust_loopback=not (remote or args.no_trust_loopback),
        viewer_token=viewer_token,
        # A remote bind requires tokens on every path, so the Host guard applies to loopback binds only.
        hosts=None if remote else LOCAL_HOSTS | {args.host},
        server_names=frozenset(args.server_name),
    )
    scheme = "https" if args.tls_cert else "http"
    host = f"[{args.host}]" if ":" in args.host else args.host
    print(f"agentville-hq: serving {scheme}://{host}:{args.port}/ (database {db})", file=sys.stderr, flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning",
                ssl_certfile=args.tls_cert, ssl_keyfile=args.tls_key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
