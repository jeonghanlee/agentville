"""Real meeting-monitor presentation changes, suspension and shared artwork copies."""
import json
from pathlib import Path
import pytest
from tests.browser.test_seats import open_page, roster
from tests.browser.paint_compare import capture_artwork, compare_artwork
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()
SCREENS = ".presentation-layer [data-presentation-screen]"


def state(page):
    return page.locator(SCREENS).evaluate_all("nodes=>nodes.map(n=>({id:n.dataset.presentationScreen,slide:n.dataset.slide,revision:Number(n.dataset.revision)}))")


def check_copies(page):
    rows = page.locator("[data-presentation-screen]").evaluate_all("nodes=>nodes.map(n=>({id:n.dataset.presentationScreen,slide:n.dataset.slide,revision:n.dataset.revision,art:n.querySelector('[data-presentation-content]').innerHTML}))")
    assert len(rows) > 4
    for name in ("meeting", "meeting-east"):
        copies = [row for row in rows if row["id"] == name]
        assert copies and all(row == copies[0] for row in copies)


@pytest.mark.parametrize("width", [1440, 720])
def test_meeting_monitors_change_independently_without_repeating(tmp_path, width):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        hq.send(payload=roster(hq, [("alpha",1)], "working"))
        browser, page, errors = open_page(driver, hq.url, width, "no-preference")
        playwright.expect(page.locator(SCREENS)).to_have_count(2)
        before = state(page)
        check_copies(page)
        page.clock.run_for(24500)
        first = state(page)
        assert first[0]["revision"] == before[0]["revision"] + 1
        assert first[0]["slide"] != before[0]["slide"]
        assert first[1] == before[1]
        observed = [before, first]
        for _ in range(8):
            page.clock.run_for(5000)
            current = state(page)
            for old, new in zip(observed[-1], current):
                if new["revision"] != old["revision"]:
                    assert new["revision"] == old["revision"] + 1
                    assert new["slide"] != old["slide"]
            check_copies(page)
            observed.append(current)
        assert observed[-1][1]["revision"] > before[1]["revision"]
        (tmp_path / "presentations.json").write_text(json.dumps(observed,indent=2)+"\n")
        assert not errors
        browser.close()


def test_meeting_monitors_pause_for_reduced_motion_and_hidden_office(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        hq.send(payload=roster(hq, [("alpha",1)], "working"))
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator(SCREENS)).to_have_count(2)
        before = state(page)
        page.clock.run_for(40000)
        assert state(page) == before
        page.emulate_media(reduced_motion="no-preference")
        page.locator("#settings-button").click()
        page.locator("#setting-motion").uncheck()
        page.locator(".dialog-done").click()
        page.clock.run_for(1000)
        page.clock.run_for(34000)
        assert all(a["revision"] > b["revision"] for a,b in zip(state(page),before))
        page.locator('[data-view="dashboard"]').click()
        before = state(page)
        page.clock.run_for(40000)
        assert state(page) == before
        page.locator('[data-view="office"]').click()
        page.clock.run_for(1000)
        page.clock.run_for(10000)
        assert state(page) == before
        page.clock.run_for(24000)
        assert all(a["revision"] > b["revision"] for a,b in zip(state(page),before))
        assert not errors
        browser.close()


def test_meeting_monitors_pause_during_replay(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        hq.send(payload=roster(hq, [("alpha",1)], "working"))
        hq.advance()
        hq.send(payload=roster(hq, [("alpha",1)], "waiting"))
        browser, page, errors = open_page(driver, hq.url, motion="no-preference")
        playwright.expect(page.locator(SCREENS)).to_have_count(2)
        page.locator('[data-view="timeline"]').click()
        playwright.expect(page.locator(".change-event").first).to_be_visible()
        page.locator(".change-event").first.click()
        playwright.expect(page.locator("#replay-banner")).to_be_visible()
        page.locator('[data-view="office"]').click()
        before = state(page)
        desk_before = page.locator(".desk-display-layer [data-desk-screen]").evaluate_all("nodes=>nodes.map(n=>n.dataset.revision)")
        page.clock.run_for(40000)
        assert state(page) == before
        assert page.locator(".desk-display-layer [data-desk-screen]").evaluate_all("nodes=>nodes.map(n=>n.dataset.revision)") == desk_before
        page.locator(".replay-live").click()
        playwright.expect(page.locator("#replay-banner")).to_be_hidden()
        page.clock.run_for(1000)
        page.clock.run_for(10000)
        assert state(page) == before
        page.clock.run_for(24000)
        assert all(a["revision"] > b["revision"] for a,b in zip(state(page),before))
        desk_after = page.locator(".desk-display-layer [data-desk-screen]").evaluate_all("nodes=>nodes.map(n=>n.dataset.revision)")
        assert len(desk_after) == 10 and all(int(a)>int(b) for a,b in zip(desk_after,desk_before))
        assert not errors
        browser.close()


@pytest.mark.parametrize("width", [1440, 720])
def test_changing_slides_preserve_pixels_outside_monitor_interiors(tmp_path, width):
    annotation = json.loads((Path(__file__).parents[2] / "docs/design/meeting-screens-annotations.json").read_text())
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        hq.send(payload=roster(hq, [("alpha",1)], "working"))
        browser, page, errors = open_page(driver, hq.url, width, "no-preference", launch_args=["--disable-partial-raster", "--disable-gpu-rasterization"])
        playwright.expect(page.locator(SCREENS)).to_have_count(2)
        page.locator("#setting-daylight").select_option("day",force=True)
        page.add_style_tag(content="#world > :not(.office-art):not(.artwork-patch):not(.furniture-front),[data-desk-screen]{visibility:hidden!important}")
        polygons = page.locator(SCREENS).evaluate_all("nodes=>nodes.map(n=>document.getElementById(n.getAttribute('clip-path').slice(5,-1)).querySelector('polygon').getAttribute('points'))")
        assert polygons == [" ".join(",".join(map(str,p)) for p in q) for q in annotation["screens"].values()]
        before, frame = capture_artwork(page)
        page.clock.run_for(24500)
        after, final_frame = capture_artwork(page)
        assert frame == final_frame
        result = compare_artwork(page, before, after, list(annotation["screens"].values()), frame)
        (tmp_path / "monitor-pixels.json").write_text(json.dumps(result,indent=2)+"\n")
        if result["outside"]:
            (tmp_path / "before.png").write_bytes(before)
            (tmp_path / "after.png").write_bytes(after)
        assert result["inside"] > 20 and result["outside"] == 0, result
        assert not errors
        browser.close()
