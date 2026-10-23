"""M2 T1: the main office looks the same before and after the seat table (docs/milestone-0.4.0.md, M2)."""

import json
import os
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from tests.browser_support import launch_options
from tests.lifecycle_support import HQ

BASELINE = Path(__file__).parent / "fixtures" / "m2-t1-baseline.json"
# Set to rewrite the baseline from the code under test; only done before step 1 of M2 changed the page.
RECORD = os.environ.get("AGENTVILLE_RECORD_T1") == "1"
WIDTHS = [1440, 720]
# The demo roster of the Home Branch: four in the left studio, one in the right, two in the Common Office,
# three in Fika, and one in the infirmary.
DEMO_ACTORS = 11

# Each drawn colleague: room and seat index, facing and sprite pose, atlas frame, mirror, stacking depth, and boxes,
# plus the working arms and switched-off screen glass, which follow the workstation points and screens of the seat.
RECORD_SCRIPT = """() => {
  const round = (value) => Math.round(value * 100) / 100;
  const box = (node) => { const r = node.getBoundingClientRect(); return [r.x, r.y, r.width, r.height].map(round); };
  return [...document.querySelectorAll("#characters .agent")].map((node) => {
    const svg = node.querySelector(":scope > .character");
    return {
      key: node.dataset.employeeKey, room: node.dataset.room, seat: node.dataset.seatIndex, facing: node.dataset.seatFacing,
      pose: svg.dataset.pose || "", frame: svg.querySelector("svg[viewBox]")?.getAttribute("viewBox") || "",
      mirror: getComputedStyle(svg).transform, depth: node.style.zIndex, box: box(node), character: box(svg),
      arms: [...svg.querySelectorAll('path[stroke-width="2.3"]')].map((arm) => arm.getAttribute("d")),
      reach: [...svg.querySelectorAll(".keyboard-reach")].map((reach) => reach.getAttribute("transform")),
    };
  }).sort((a, b) => a.key.localeCompare(b.key)).concat([...document.querySelectorAll(".screen-off-glass polygon")]
    .map((glass) => ({ glass: glass.getAttribute("points"), depth: glass.parentElement.style.zIndex })));
}"""


def open_demo(driver, url, width):
    browser = driver.chromium.launch(**launch_options())
    page = browser.new_page(viewport={"width": width, "height": 1000}, reduced_motion="reduce", locale="en-US")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.goto(url + "/?demo=1")
    playwright.expect(page.locator("#characters .agent")).to_have_count(DEMO_ACTORS)
    page.evaluate("document.fonts.ready")
    return browser, page, errors


def test_t1_main_office_matches_baseline(tmp_path):
    observed = {}
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        for width in WIDTHS:
            browser, page, errors = open_demo(driver, hq.url, width)
            observed[str(width)] = page.evaluate(RECORD_SCRIPT)
            assert not errors
            browser.close()
    if RECORD:
        BASELINE.parent.mkdir(exist_ok=True)
        BASELINE.write_text(json.dumps(observed, indent=1) + "\n")
    baseline = json.loads(BASELINE.read_text())
    for width in WIDTHS:
        assert len([entry for entry in observed[str(width)] if "key" in entry]) == DEMO_ACTORS
        assert observed[str(width)] == baseline[str(width)], width
