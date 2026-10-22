"""Project resolution from a working directory."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass

COMMON_OFFICE_ID = "common-office"
COMMON_OFFICE_ALIAS = "Common Office"


@dataclass(frozen=True)
class Project:
    project_id: str
    alias: str


COMMON_OFFICE = Project(COMMON_OFFICE_ID, COMMON_OFFICE_ALIAS)

_SCP_LIKE = re.compile(r"^(?:[^@/]+@)?(?P<host>[^:/]+):(?P<path>[^/].*)$")
_URL = re.compile(r"^[a-z][a-z0-9+.-]*://(?:[^/]*@)?(?P<host>[^/:@]+)(?::\d+)?/(?P<path>.+)$")


def normalize_remote(url: str) -> str | None:
    """Return ``host/owner/repo`` for a Git remote URL, or None when unparseable."""
    url = url.strip()
    match = _URL.match(url) or _SCP_LIKE.match(url)
    if not match:
        return None
    path = match.group("path").strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{match.group('host').lower()}/{path}"


def local_project_id(host_id: str, root: str) -> str:
    return "local-" + hashlib.sha256(f"{host_id}:{root}".encode()).hexdigest()[:16]


class GitProjectResolver:
    def __init__(self, host_id: str) -> None:
        self.host_id = host_id

    def resolve(self, cwd: str) -> Project:
        root = self._git(cwd, "rev-parse", "--show-toplevel")
        if not root:
            return COMMON_OFFICE
        alias = os.path.basename(root)
        remote = self._git(root, "config", "--get", "remote.origin.url")
        normalized = normalize_remote(remote) if remote else None
        if normalized:
            return Project(normalized, alias)
        return Project(local_project_id(self.host_id, root), alias)

    @staticmethod
    def _git(cwd: str, *args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() or None if result.returncode == 0 else None
