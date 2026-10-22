"""AgentVille."""

from importlib import metadata


def version() -> str:
    """Installed package version; 0.0.0 when running from an uninstalled tree."""
    try:
        return metadata.version("agentville")
    except metadata.PackageNotFoundError:
        return "0.0.0"
