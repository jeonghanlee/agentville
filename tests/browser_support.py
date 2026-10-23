import importlib
import os

import pytest

# A Chromium build other than the one the installed Playwright expects, e.g. a preinstalled system browser.
CHROMIUM = os.environ.get("AGENTVILLE_CHROMIUM") or None


def launch_options() -> dict:
    return {"headless": True, "executable_path": CHROMIUM}


def playwright_sync():
    """The Playwright sync API; skipped when absent, unless AGENTVILLE_REQUIRE_BROWSER=1 makes that a failure."""
    if os.environ.get("AGENTVILLE_REQUIRE_BROWSER") == "1":
        return importlib.import_module("playwright.sync_api")
    return pytest.importorskip("playwright.sync_api")
