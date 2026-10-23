import socket
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
import uvicorn

playwright = pytest.importorskip("playwright.sync_api")

from tests.browser_support import launch_options
from agentville.collector.sender import HttpSender
from agentville.common.protocol import Envelope, iso
from agentville.hq.app import create_app
from agentville.hq.store import Store


@pytest.mark.parametrize("width", [1440, 720])
def test_duplicate_branch_aliases_and_antigravity_in_real_browser(tmp_path, width):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    app = create_app(Store(str(tmp_path / "hq.sqlite3")))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        at = datetime.now(UTC) - timedelta(seconds=10)
        url = f"http://127.0.0.1:{port}"
        for suffix, provider, alias in [("a", "antigravity", "Agy colleague"), ("b", "codex", "Codex colleague")]:
            branch = "synthetic-branch-" + suffix
            agent = {"agent_id": "agent-" + suffix, "project_id": "common-office", "project_alias": "Common Office",
                     "provider": provider, "seat": 1, "alias": alias, "presence": "on_duty", "presence_since": iso(at),
                     "instance": {"instance_id": "shift-" + suffix, "started_at": iso(at), "runtime": {"type": "shell"}}}
            activity = {"agent_id": agent["agent_id"], "instance_id": agent["instance"]["instance_id"],
                        "state": "working", "state_since": iso(at), "source": "session_log", "confidence": "medium"}
            payload = {"branch": {"alias": "Office", "country": "", "time": "UTC", "location": "",
                                  "thresholds": {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}},
                       "agents": [agent], "activities": [activity], "contractors": []}
            assert HttpSender(url)([Envelope(branch).wrap("snapshot", at, payload, at)]).ok
        with playwright.sync_playwright() as driver:
            browser = driver.chromium.launch(**launch_options())
            page = browser.new_page(viewport={"width": width, "height": 1000}, reduced_motion="reduce", locale="en-US")
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            playwright.expect(page.locator("#branch-select option[value='synthetic-branch-a']")).to_have_count(1)
            page.locator("#branch-select").select_option("synthetic-branch-a")
            page.locator("#team-list button").filter(has_text="Agy colleague").click()
            playwright.expect(page.locator("#employee-detail")).to_contain_text("Office (synthetic-branch-a)")
            playwright.expect(page.locator("#team-list .provider").first).to_have_text("AG")
            page.screenshot(path=str(tmp_path / "office.png"), full_page=True)
            page.get_by_role("button", name="Work log", exact=True).click()
            playwright.expect(page.locator("#data-view")).to_contain_text("Office (synthetic-branch-a)")
            playwright.expect(page.locator("#data-view")).to_contain_text("Office (synthetic-branch-b)")
            page.screenshot(path=str(tmp_path / "worklog.png"), full_page=True)
            assert not errors
            print(f"Browser evidence ({width}px): {tmp_path}")
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()
