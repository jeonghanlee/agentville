"""Branch configuration: ``$XDG_CONFIG_HOME/agentville/config.yaml``.

Created on first start. ``host.id`` is generated once and never rewritten.
"""

from __future__ import annotations

import fnmatch
import os
import socket
import uuid
from dataclasses import dataclass, field
from typing import Any

import yaml

DEFAULT_THRESHOLDS = {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}

DEFAULT_CONDITIONS: list[dict[str, Any]] = [
    {"provider": "claude", "fast_mode": True, "condition": "extra-coffee"},
    {"provider": "*", "effort": "high", "condition": "study-mode"},
    {"provider": "*", "effort": "xhigh", "condition": "study-mode"},
    {"provider": "*", "effort": "low", "condition": "lazy"},
]


def config_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "agentville", "config.yaml")


def state_dir() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "agentville")


def local_timezone() -> str:
    tz = os.environ.get("TZ", "").lstrip(":")
    if tz and ("/" in tz or tz == "UTC"):
        return tz
    try:
        with open("/etc/timezone", encoding="utf-8") as fh:
            name = fh.read().strip()
            if name:
                return name
    except OSError:
        pass
    try:
        target = os.readlink("/etc/localtime")
        marker = "zoneinfo/"
        if marker in target:
            return target.split(marker, 1)[1]
    except OSError:
        pass
    return "UTC"


@dataclass
class CodexHome:
    home: str
    account_alias: str


@dataclass
class BranchConfig:
    host_id: str
    alias: str
    country: str
    time: str
    location: str
    hq_url: str
    thresholds: dict[str, int]
    claude_home: str | None
    codex_homes: list[CodexHome]
    conditions: list[dict[str, Any]] = field(default_factory=list)
    poll_interval: float = 1.0
    heartbeat_interval: int = 30

    def branch_payload(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "country": self.country,
            "time": self.time,
            "location": self.location,
            "thresholds": dict(self.thresholds),
        }

    def condition_for(self, provider: str, model: str | None, settings: dict[str, Any]) -> str:
        for rule in self.conditions:
            if not fnmatch.fnmatchcase(provider, str(rule.get("provider", "*"))):
                continue
            if "model" in rule and not fnmatch.fnmatchcase(model or "", str(rule["model"])):
                continue
            if any(key in rule and settings.get(key) != rule[key] for key in ("effort", "fast_mode")):
                continue
            return str(rule.get("condition", "normal"))
        return "normal"


def _default_document(home: str) -> dict[str, Any]:
    codex = [
        {"home": path, "account_alias": os.path.basename(path).lstrip(".")}
        for path in (os.path.join(home, ".codex"), os.path.join(home, ".codex-work"))
        if os.path.isdir(path)
    ]
    return {
        "host": {
            "id": str(uuid.uuid4()),
            "alias": socket.gethostname(),
            "country": "",
            "time": local_timezone(),
            "location": "",
        },
        "hq": {"url": "http://127.0.0.1:8470"},
        "thresholds": dict(DEFAULT_THRESHOLDS),
        "providers": {
            "claude": {"home": os.path.join(home, ".claude")},
            "codex": codex,
        },
        "conditions": [dict(rule) for rule in DEFAULT_CONDITIONS],
        "collector": {"poll_interval": 1.0, "heartbeat_interval": 30},
    }


def load_or_create(path: str | None = None, home: str | None = None) -> BranchConfig:
    path = path or config_path()
    home = home or os.path.expanduser("~")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        document = _default_document(home)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(document, fh, sort_keys=False)
    with open(path, encoding="utf-8") as fh:
        document = yaml.safe_load(fh) or {}
    return parse(document)


def parse(document: dict[str, Any]) -> BranchConfig:
    host = document.get("host") or {}
    host_id = host.get("id")
    if not isinstance(host_id, str) or not host_id:
        raise ValueError("host.id is required")
    providers = document.get("providers") or {}
    claude = providers.get("claude") or {}
    codex = providers.get("codex") or []
    collector = document.get("collector") or {}
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update({k: int(v) for k, v in (document.get("thresholds") or {}).items() if k in DEFAULT_THRESHOLDS})
    return BranchConfig(
        host_id=host_id,
        alias=str(host.get("alias") or host_id),
        country=str(host.get("country") or ""),
        time=str(host.get("time") or "UTC"),
        location=str(host.get("location") or ""),
        hq_url=str((document.get("hq") or {}).get("url") or "http://127.0.0.1:8470"),
        thresholds=thresholds,
        claude_home=os.path.expanduser(claude["home"]) if claude.get("home") else None,
        codex_homes=[
            CodexHome(os.path.expanduser(entry["home"]), str(entry.get("account_alias") or os.path.basename(entry["home"])))
            for entry in codex
            if isinstance(entry, dict) and entry.get("home")
        ],
        conditions=list(document["conditions"] or []) if "conditions" in document else list(DEFAULT_CONDITIONS),
        poll_interval=float(collector.get("poll_interval", 1.0)),
        heartbeat_interval=int(collector.get("heartbeat_interval", 30)),
    )
