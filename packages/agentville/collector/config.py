"""Branch configuration: ``$XDG_CONFIG_HOME/agentville/config.yaml``.

Created on first start. ``host.id`` is generated once and never rewritten.
"""

from __future__ import annotations

import fnmatch
import os
import socket
import stat
import uuid
from dataclasses import dataclass, field
from typing import Any

import yaml

DEFAULT_THRESHOLDS = {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}

MAX_ALIAS = 40

DEFAULT_CONDITIONS: list[dict[str, Any]] = [
    {"provider": "claude", "fast_mode": True, "condition": "extra-coffee"},
    {"provider": "*", "effort": "high", "condition": "study-mode"},
    {"provider": "*", "effort": "xhigh", "condition": "study-mode"},
    {"provider": "*", "effort": "low", "condition": "light"},
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
class ProviderHome:
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
    hq_token: str | None
    thresholds: dict[str, int]
    claude_homes: list[ProviderHome]
    codex_homes: list[ProviderHome]
    conditions: list[dict[str, Any]] = field(default_factory=list)
    poll_interval: float = 1.0
    heartbeat_interval: int = 30
    # Employee display names by agent_id; sent as the agent ``alias``.
    aliases: dict[str, str] = field(default_factory=dict)
    antigravity_homes: list[ProviderHome] = field(default_factory=list)

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


def account_alias(provider: str, number: int) -> str:
    return f"{provider}-account-{number}"


def _discover_homes(home: str, provider: str, keep_primary: bool = False) -> list[dict[str, str]]:
    """``~/.<provider>`` first, then ``~/.<provider>-*`` in name order, one account each."""
    try:
        extra = sorted(n for n in os.listdir(home) if n.startswith(f".{provider}-"))
    except OSError:
        extra = []
    primary = os.path.join(home, f".{provider}")
    paths = [p for p in (os.path.join(home, n) for n in [f".{provider}", *extra])
             if os.path.isdir(p) or (keep_primary and p == primary)]
    return [{"home": p, "account_alias": account_alias(provider, i)} for i, p in enumerate(paths, 1)]


def _homes(entries: Any, provider: str) -> list[ProviderHome]:
    # A single mapping is the earlier one-home form.
    listed = [entries] if isinstance(entries, dict) else entries or []
    if not isinstance(listed, list):
        raise ValueError(f"providers.{provider} must be a list of homes")
    valid = [e for e in listed if isinstance(e, dict) and e.get("home")]
    return [
        ProviderHome(os.path.expanduser(e["home"]), str(e.get("account_alias") or account_alias(provider, i)))
        for i, e in enumerate(valid, 1)
    ]


def _default_document(home: str) -> dict[str, Any]:
    antigravity = [entry for entry in _discover_homes(home, "gemini")
                   if os.path.isdir(os.path.join(entry["home"], "antigravity-cli"))]
    for number, entry in enumerate(antigravity, 1):
        entry["account_alias"] = account_alias("antigravity", number)
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
            "claude": _discover_homes(home, "claude", keep_primary=True),
            "codex": _discover_homes(home, "codex"),
            "antigravity": antigravity,
        },
        "conditions": [dict(rule) for rule in DEFAULT_CONDITIONS],
        "collector": {"poll_interval": 1.0, "heartbeat_interval": 30},
        "aliases": {},
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
        try:
            document = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
            raise ValueError(f"{path}: YAML syntax error{where}") from None
        private = not stat.S_IMODE(os.fstat(fh.fileno()).st_mode) & 0o077
    if not isinstance(document, dict):
        raise ValueError(f"{path}: the top level must be a mapping")
    if isinstance(document.get("hq"), dict) and document["hq"].get("token") and not private:
        raise SystemExit(f"agentville-collector: {path} holds hq.token and must not be accessible by group or others (chmod 600)")
    return parse(document)


def _section(document: dict[str, Any], name: str) -> dict[str, Any]:
    value = document.get(name) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _number(section: str, key: str, value: Any, kind: type[int] | type[float]) -> Any:
    if isinstance(value, bool):
        value = None
    try:
        return kind(value)
    except (TypeError, ValueError):
        raise ValueError(f"{section}.{key} must be {'an integer' if kind is int else 'a number'}") from None


def _aliases(document: dict[str, Any]) -> dict[str, str]:
    value = document.get("aliases") or {}
    if not isinstance(value, dict):
        raise ValueError("aliases must be a mapping of colleague id to name")
    for agent_id, name in value.items():
        if not isinstance(name, str) or not name.strip() or len(name) > MAX_ALIAS:
            raise ValueError(f"aliases.{agent_id} must be a non-empty string of at most {MAX_ALIAS} characters")
    return {str(agent_id): name for agent_id, name in value.items()}


def parse(document: dict[str, Any]) -> BranchConfig:
    host = _section(document, "host")
    host_id = host.get("id")
    if not isinstance(host_id, str) or not host_id:
        raise ValueError("host.id is required")
    providers = _section(document, "providers")
    collector = _section(document, "collector")
    hq = _section(document, "hq")
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update({k: _number("thresholds", k, v, int) for k, v in _section(document, "thresholds").items()
                       if k in DEFAULT_THRESHOLDS})
    if any(v < 0 for v in thresholds.values()):
        raise ValueError("thresholds must not be negative")
    if not thresholds["phone"] <= thresholds["doze"] <= thresholds["lounge"]:
        raise ValueError("thresholds must satisfy phone <= doze <= lounge")
    heartbeat_interval = _number("collector", "heartbeat_interval", collector.get("heartbeat_interval", 30), int)
    if heartbeat_interval < 1:
        raise ValueError("collector.heartbeat_interval must be at least 1")
    poll_interval = _number("collector", "poll_interval", collector.get("poll_interval", 1.0), float)
    if not poll_interval > 0:
        raise ValueError("collector.poll_interval must be greater than 0")
    conditions = (document["conditions"] or []) if "conditions" in document else list(DEFAULT_CONDITIONS)
    if not isinstance(conditions, list) or not all(isinstance(rule, dict) for rule in conditions):
        raise ValueError("conditions must be a list of mappings")
    return BranchConfig(
        host_id=host_id,
        alias=str(host.get("alias") or host_id),
        country=str(host.get("country") or ""),
        time=str(host.get("time") or "UTC"),
        location=str(host.get("location") or ""),
        hq_url=str(hq.get("url") or "http://127.0.0.1:8470"),
        hq_token=hq.get("token") or None,
        thresholds=thresholds,
        claude_homes=_homes(providers.get("claude"), "claude"),
        codex_homes=_homes(providers.get("codex"), "codex"),
        antigravity_homes=_homes(providers.get("antigravity"), "antigravity"),
        conditions=list(conditions),
        poll_interval=poll_interval,
        heartbeat_interval=heartbeat_interval,
        aliases=_aliases(document),
    )
