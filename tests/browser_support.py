import os

# A Chromium build other than the one the installed Playwright expects, e.g. a preinstalled system browser.
CHROMIUM = os.environ.get("AGENTVILLE_CHROMIUM") or None


def launch_options() -> dict:
    return {"headless": True, "executable_path": CHROMIUM}
