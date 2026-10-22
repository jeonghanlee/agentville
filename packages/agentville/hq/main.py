"""HQ entry point."""

from __future__ import annotations

import argparse
import dataclasses
import ipaddress
import os
import socket
import sqlite3
import ssl
import stat
import sys
from datetime import timedelta
from typing import Any

import uvicorn
import yaml

from agentville import version
from agentville.hq.app import LOCAL_HOSTS, create_app
from agentville.hq.notify import Notifier, NotifyConfig, Outbox, http_post, parse_config
from agentville.hq.store import Store


MIN_TOKEN = 16


def data_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "agentville")


def _read_private(path: str) -> str:
    try:
        if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
            raise SystemExit(f"agentville-hq: {path} must not be accessible by group or others (chmod 600)")
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
        raise SystemExit(f"agentville-hq: cannot read {path}: {reason}") from None


def _load_yaml(path: str) -> Any:
    try:
        return yaml.safe_load(_read_private(path))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise SystemExit(f"agentville-hq: {path}: YAML syntax error{where}") from None


def load_tokens(path: str | None) -> dict[str, str]:
    """YAML mapping of branch_id to bearer token, from a file private to the owner."""
    if not path:
        return {}
    document = _load_yaml(path) or {}
    if not isinstance(document, dict):
        raise SystemExit(f"agentville-hq: {path} must be a mapping of branch_id to token")
    tokens = {}
    for branch_id, token in document.items():
        if not isinstance(token, str) or len(token) < MIN_TOKEN:
            raise SystemExit(f"agentville-hq: token for {branch_id} must be a string of at least {MIN_TOKEN} characters")
        tokens[str(branch_id)] = token
    return tokens


def load_notify_config(path: str) -> NotifyConfig:
    """Notification settings from a file private to the owner, with the bearer token read from its own file."""
    try:
        config = parse_config(_load_yaml(path))
    except ValueError as exc:
        raise SystemExit(f"agentville-hq: {path}: {exc}") from None
    if config.token_file:
        token_file = os.path.expanduser(config.token_file)
        token = _read_private(token_file).strip()
        if not token:
            raise SystemExit(f"agentville-hq: {token_file} holds no token")
        config = dataclasses.replace(config, token=token)
    return config


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_tls(cert: str, key: str) -> None:
    try:
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(cert, key)
    except (OSError, ssl.SSLError) as exc:
        reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
        raise SystemExit(f"agentville-hq: cannot load TLS certificate {cert} and key {key}: {reason}") from None


def listen(host: str, port: int) -> socket.socket:
    """A listening socket for uvicorn, so a failure is reported before the server starts."""
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(2048)
    except OSError as exc:
        sock.close()
        shown = f"[{host}]" if ":" in host else host
        raise SystemExit(f"agentville-hq: cannot listen on {shown}:{port}: {exc.strerror or exc}") from None
    return sock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentville-hq", description="AgentVille HQ")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version()}")
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
    parser.add_argument("--notify-config", help="YAML file configuring notifications to an ntfy topic (mode 0600)")
    args = parser.parse_args(argv)
    if bool(args.tls_cert) != bool(args.tls_key):
        parser.error("--tls-cert and --tls-key are used together")

    remote = not is_loopback(args.host)
    viewer_token = (_read_private(args.viewer_token_file).strip() or None) if args.viewer_token_file else None
    if remote and not (args.allow_remote and viewer_token):
        parser.error("a non-loopback --host requires --allow-remote and --viewer-token-file")
    if args.server_name and not (args.no_trust_loopback and viewer_token):
        parser.error("--server-name requires --no-trust-loopback and --viewer-token-file")
    tokens = load_tokens(args.tokens)
    if args.tls_cert:
        check_tls(args.tls_cert, args.tls_key)
    notify_config = load_notify_config(args.notify_config) if args.notify_config else None

    db = args.db or os.path.join(data_dir(), "hq.sqlite3")
    directory = os.path.dirname(db) or "."
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        store = Store(db)
    except (OSError, sqlite3.Error) as exc:
        raise SystemExit(f"agentville-hq: cannot open database {db}: {getattr(exc, 'strerror', None) or exc}") from None
    outbox = Outbox(http_post(notify_config)) if notify_config else None
    app = create_app(
        store,
        tokens,
        retention=timedelta(days=args.retention_days),
        trust_loopback=not (remote or args.no_trust_loopback),
        viewer_token=viewer_token,
        # A remote bind requires tokens on every path, so the Host guard applies to loopback binds only.
        hosts=None if remote else LOCAL_HOSTS | {args.host},
        server_names=frozenset(args.server_name),
        notifier=Notifier(notify_config, outbox.put) if notify_config and outbox else None,
    )
    sock = listen(args.host, args.port)
    scheme = "https" if args.tls_cert else "http"
    host = f"[{args.host}]" if ":" in args.host else args.host
    print(f"agentville-hq: serving {scheme}://{host}:{sock.getsockname()[1]}/ (database {db})", file=sys.stderr, flush=True)
    config = uvicorn.Config(app, log_level="warning", ssl_certfile=args.tls_cert, ssl_keyfile=args.tls_key)
    try:
        with sock:
            uvicorn.Server(config).run(sockets=[sock])
    finally:
        if outbox is not None:
            outbox.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
