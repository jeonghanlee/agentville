import asyncio
import json
import re

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from playwright.async_api import async_playwright, expect as async_expect

from agentville.collector.sender import HttpSender
from tests.lifecycle_support import ADMIN, PROJECT, VIEWER, HQ


NOTIFICATION_BOUNDARY = """
window.observedNotifications = [];
class NotificationBoundary {
  static permission = 'granted';
  static requestPermission() { return Promise.resolve('granted'); }
  constructor(title, options) { window.observedNotifications.push({ title, body: options.body }); }
  close() {}
}
Object.defineProperty(window, 'Notification', { value: NotificationBoundary });
"""


@pytest.mark.parametrize("width", [1440, 720])
def test_real_browser_closure_notifications_history_and_credentials(tmp_path, width):
    with HQ(tmp_path / "hq.sqlite3") as hq:
        hq.send(); hq.send(branch="b2")
        with playwright.sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 1000}, reduced_motion="reduce", locale="en-US")
            page.add_init_script(NOTIFICATION_BOUNDARY)
            page.clock.install()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            requests = []
            page.on("request", lambda request: requests.append((request.method, request.url, request.headers)))
            page.goto(hq.url)
            page.locator("#settings-button").click()
            page.locator("#setting-notify").check()
            page.keyboard.press("Escape")
            page.get_by_role("button", name="Projects", exact=True).click()
            project = page.locator('.project-card[data-project-id="' + PROJECT + '"]')
            playwright.expect(project).to_have_count(1)

            def close_project():
                project.locator(".lifecycle-close").click()
                page.get_by_label("Administrator token", exact=True).fill(ADMIN)
                page.locator(".lifecycle-dialog button[type=submit]").click()
                playwright.expect(page.locator(".lifecycle-dialog")).to_have_count(0)
                playwright.expect(project.locator(".closed-badge")).to_have_text("Closed")

            hq.advance()
            close_project()
            assert hq.life("project", PROJECT)["closed"]
            assert ADMIN not in page.url and ADMIN not in page.content()
            assert ADMIN not in page.evaluate("JSON.stringify({...localStorage, ...sessionStorage})")
            assert all(path.endswith("/api/v1/lifecycle/close") for method, path, hdr in requests
                       if hdr.get("authorization") == "Bearer " + ADMIN)
            hq.advance()
            first = hq.send(branch="b2")
            playwright.expect(project.locator(".closed-badge")).to_have_count(0)
            page.wait_for_function("observedNotifications.length === 1")
            assert page.evaluate("observedNotifications[0].title") == "Project Shared reopened"
            assert HttpSender(hq.url)([first]).ok
            page.clock.fast_forward(1000)
            assert page.evaluate("observedNotifications.length") == 1

            hq.advance()
            close_project()
            hq.advance(); hq.send()
            playwright.expect(project.locator(".closed-badge")).to_have_count(0)
            assert page.evaluate("observedNotifications.length") == 1
            hq.advance(31)
            page.clock.fast_forward(31000)
            page.wait_for_function("observedNotifications.length === 2")
            hq.advance(); close_project()
            hq.advance(); hq.send()
            playwright.expect(project.locator(".closed-badge")).to_have_count(0)
            hq.advance(); close_project()
            hq.advance(31); page.clock.fast_forward(31000)
            assert page.evaluate("observedNotifications.length") == 2

            page.locator("#settings-button").click()
            page.locator("#setting-notify").uncheck()
            page.keyboard.press("Escape")
            hq.advance(); hq.send()
            playwright.expect(project.locator(".closed-badge")).to_have_count(0)
            page.clock.fast_forward(31000)
            assert page.evaluate("observedNotifications.length") == 2

            page.locator("#settings-button").click()
            page.locator("#setting-notify").check()
            page.keyboard.press("Escape")
            page.get_by_role("button", name="Timeline", exact=True).click()
            playwright.expect(page.locator(".change-event").first).to_be_visible()
            page.locator(".change-event").first.click()
            playwright.expect(page.locator("body")).to_have_class(re.compile("replaying"))
            page.get_by_role("button", name="Projects", exact=True).click()
            playwright.expect(project.locator(".lifecycle-close")).to_be_disabled()
            hq.close(); hq.advance(); hq.send()
            page.clock.fast_forward(31000)
            assert page.evaluate("observedNotifications.length") == 2
            page.locator(".replay-live").click()
            playwright.expect(project.locator(".lifecycle-close")).to_be_enabled()
            page.screenshot(path=str(tmp_path / f"lifecycle-{width}.png"), full_page=True)
            assert not errors

            page.goto(hq.url + "/?demo=1")
            page.get_by_role("button", name="Projects", exact=True).click()
            playwright.expect(page.locator(".lifecycle-close").first).to_be_disabled()
            before = sum(path.endswith("/api/v1/lifecycle/close") for _, path, _ in requests)
            page.locator(".lifecycle-close").first.evaluate("node => { node.disabled = false; node.click(); }")
            assert page.locator(".lifecycle-dialog").count() == 0
            assert sum(path.endswith("/api/v1/lifecycle/close") for _, path, _ in requests) == before
            assert not errors
            browser.close()
    print("Browser lifecycle evidence:", tmp_path)


@pytest.mark.parametrize("width", [1440, 720])
def test_branch_keyboard_closure_bad_credentials_and_missing_configuration(tmp_path, width):
    for configured in (True, False):
        with HQ(tmp_path / ("configured.sqlite3" if configured else "disabled.sqlite3"),
                admin_token=ADMIN if configured else None) as hq:
            hq.send()
            with playwright.sync_playwright() as driver:
                browser = driver.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": width, "height": 1000}, reduced_motion="reduce", locale="en-US")
                page.add_init_script(NOTIFICATION_BOUNDARY)
                page.goto(hq.url)
                page.locator("#settings-button").click()
                page.locator("#setting-notify").check()
                page.keyboard.press("Escape")
                page.get_by_role("button", name="Branches", exact=True).click()
                card = page.locator(".branch-card").first
                card.locator(".lifecycle-close").focus()
                page.keyboard.press("Enter")
                token = page.get_by_label("Administrator token", exact=True)
                playwright.expect(token).to_be_focused()
                token.fill(VIEWER)
                token.press("Enter")
                playwright.expect(page.locator(".lifecycle-error")).to_contain_text(
                    "Check the administrator token" if configured else "HQ closure is disabled")
                assert not hq.life()["closed"]
                playwright.expect(token).to_have_value("")
                if configured:
                    token.fill(ADMIN)
                    token.press("Enter")
                    playwright.expect(card.locator(".closed-badge")).to_have_text("Closed")
                    hq.advance(); hq.send()
                    playwright.expect(card.locator(".closed-badge")).to_have_count(0)
                    page.wait_for_function("observedNotifications.length === 1")
                    assert page.evaluate("observedNotifications[0].title") == "Branch Office reopened"
                else:
                    page.keyboard.press("Escape")
                    playwright.expect(page.locator(".lifecycle-dialog")).to_have_count(0)
                browser.close()


@pytest.mark.parametrize("width", [1440, 720])
@pytest.mark.parametrize("kind", ["branch", "project"])
@pytest.mark.parametrize("intervening", ["reopen", "disconnect"])
def test_closure_refresh_preserves_newer_live_state(tmp_path, width, kind, intervening):
    # Keep periodic repair outside the assertion window; changed-state delivery remains immediate.
    with HQ(tmp_path / "hq.sqlite3", live_refresh=60) as hq:
        hq.send()
        asyncio.run(check_refresh_order(hq, tmp_path, width, kind, intervening))


async def check_refresh_order(hq, evidence, width, kind, intervening):
    held, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    identity = "b1" if kind == "branch" else PROJECT
    facts = {"kind": kind, "width": width, "intervening": intervening, "frames": []}
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": 1000}, reduced_motion="reduce", locale="en-US")
        await page.add_init_script(NOTIFICATION_BOUNDARY)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def record_frame(payload):
            message = json.loads(payload)
            if message.get("type") == "state":
                value = next(v for v in message["state"]["lifecycles"] if (v["kind"], v["id"]) == (kind, identity))
                facts["frames"].append({"closed": value["closed"], "revision": value["revision"]})

        page.on("websocket", lambda connection: connection.on("framereceived", record_frame))

        async def delay_response(route):
            try:
                response = await route.fetch()
                (evidence / "held-state.json").write_bytes(await response.body())
                data = await response.json()
                value = next(v for v in data["lifecycles"] if (v["kind"], v["id"]) == (kind, identity))
                facts["held_http"] = {"status": response.status, "closed": value["closed"], "revision": value["revision"]}
                held.set()
                await release.wait()
                await route.fulfill(response=response)
            finally:
                finished.set()

        try:
            await page.goto(hq.url)
            await page.locator("#settings-button").click()
            await page.locator("#setting-notify").check()
            await page.keyboard.press("Escape")
            await page.get_by_role("button", name="Branches" if kind == "branch" else "Projects", exact=True).click()
            card = page.locator(".branch-card" if kind == "branch" else ".project-card").first
            await async_expect(card.locator(".lifecycle-close")).to_be_enabled()
            await page.route("**/api/v1/state", delay_response, times=1)
            await card.locator(".lifecycle-close").click()
            await page.get_by_label("Administrator token", exact=True).fill(ADMIN)
            await page.locator(".lifecycle-dialog button[type=submit]").click()
            await asyncio.wait_for(held.wait(), 5)
            assert facts["held_http"] == {"status": 200, "closed": True, "revision": 1}
            assert hq.life(kind, identity)["closed"]
            if intervening == "reopen":
                hq.advance(); hq.send()
                await async_expect(card.locator(".closed-badge")).to_have_count(0)
                assert {"closed": False, "revision": 2} in facts["frames"]
                assert not hq.life(kind, identity)["closed"]
                await page.wait_for_function("observedNotifications.length === 1")
            else:
                hq.server.should_exit = True
                await asyncio.to_thread(hq.thread.join, 10)
                assert not hq.thread.is_alive()
                await async_expect(page.locator("#connection")).to_have_class(re.compile("disconnected"))
            release.set()
            await async_expect(page.locator(".lifecycle-dialog")).to_have_count(0)
            if intervening == "reopen":
                await async_expect(card.locator(".closed-badge")).to_have_count(0)
                await async_expect(card.locator(".lifecycle-close")).to_be_enabled()
                assert len(await page.evaluate("observedNotifications")) == 1
                hq.advance()
                await card.locator(".lifecycle-close").click()
                await page.get_by_label("Administrator token", exact=True).fill(ADMIN)
                await page.locator(".lifecycle-dialog button[type=submit]").click()
                await async_expect(page.locator(".lifecycle-dialog")).to_have_count(0)
                assert hq.life(kind, identity)["closed"] and hq.life(kind, identity)["revision"] == 3
            else:
                await page.get_by_role("button", name="Projects" if kind == "branch" else "Branches", exact=True).click()
                other = page.locator(".project-card" if kind == "branch" else ".branch-card").first
                await async_expect(other.locator(".closed-badge")).to_have_count(0)
                await async_expect(other.locator(".lifecycle-close")).to_be_disabled()
            assert not errors
        finally:
            release.set()
            if held.is_set():
                await asyncio.wait_for(finished.wait(), 5)
            (evidence / "response-order.json").write_text(json.dumps(facts, indent=2))
            await page.screenshot(path=str(evidence / f"refresh-{intervening}-{kind}-{width}.png"), full_page=True)
            await browser.close()
