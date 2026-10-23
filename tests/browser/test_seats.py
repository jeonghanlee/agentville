"""M2 T1: the main office looks the same before and after the seat table (docs/milestone-0.4.0.md, M2)."""

import json
import os
from pathlib import Path

from tests.browser_support import launch_options, playwright_sync

playwright = playwright_sync()

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
# Boxes are CSS pixels relative to the office artwork (#world), so the page layout above the office, which differs
# between browser builds and fonts, plays no part; the artwork's own size is recorded with them.
RECORD_SCRIPT = """() => {
  const round = (value) => Math.round(value * 100) / 100;
  const world = document.getElementById("world").getBoundingClientRect();
  const box = (node) => { const r = node.getBoundingClientRect(); return [r.x - world.x, r.y - world.y, r.width, r.height].map(round); };
  return { world: [world.width, world.height].map(round), colleagues: [...document.querySelectorAll("#characters .agent")].map((node) => {
    const svg = node.querySelector(":scope > .character");
    return {
      key: node.dataset.employeeKey, room: node.dataset.room, seat: node.dataset.seatIndex, facing: node.dataset.seatFacing,
      pose: svg.dataset.pose || "", frame: svg.querySelector("svg[viewBox]")?.getAttribute("viewBox") || "",
      mirror: getComputedStyle(svg).transform, depth: node.style.zIndex, box: box(node), character: box(svg),
      arms: [...svg.querySelectorAll('path[stroke-width="2.3"]')].map((arm) => arm.getAttribute("d")),
      reach: [...svg.querySelectorAll(".keyboard-reach")].map((reach) => reach.getAttribute("transform")),
    };
  }).sort((a, b) => a.key.localeCompare(b.key)), glass: [...document.querySelectorAll(".screen-off-glass polygon")]
    .map((glass) => ({ points: glass.getAttribute("points"), depth: glass.parentElement.style.zIndex })) };
}"""
# Geometry tolerance in CSS pixels. Browser builds round sub-pixel layout differently by a fraction of a pixel; the
# smallest seat change the table expresses (0.1 % of the artwork) moves a figure by more than 0.5 px in both
# directions at 1440 px, where the artwork is about 882 x 588 px, so that run still catches every moved seat.
TOLERANCE = 0.5
GEOMETRY = ("box", "character")


def assert_same(observed, baseline, width):
    assert all(abs(a - b) <= TOLERANCE for a, b in zip(observed["world"], baseline["world"])), (width, observed["world"])
    assert observed["glass"] == baseline["glass"], width
    assert [c["key"] for c in observed["colleagues"]] == [c["key"] for c in baseline["colleagues"]], width
    for seen, expected in zip(observed["colleagues"], baseline["colleagues"]):
        # Every field other than the boxes is exact.
        assert {k: v for k, v in seen.items() if k not in GEOMETRY} == {k: v for k, v in expected.items() if k not in GEOMETRY}, (width, seen)
        for field in GEOMETRY:
            assert all(abs(a - b) <= TOLERANCE for a, b in zip(seen[field], expected[field])), (width, field, seen, expected)


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
    assert min(observed["1440"]["world"]) * .001 > TOLERANCE
    for width in WIDTHS:
        assert len(observed[str(width)]["colleagues"]) == DEMO_ACTORS
        assert_same(observed[str(width)], baseline[str(width)], width)


# The seat table names footprints, waypoints, and facings that exist, and each seat step from its approach waypoint
# to its feet touches only its own footprints (P3; the route clearance test of step 3 covers the whole graph).
SEAT_TABLE_SCRIPT = """async () => {
  const { SEATS, roomSeats, roomOfSeat, seatFoot } = await import("/seats.js");
  const { FOOTPRINTS, NODES, touched } = await import("/floor.js");
  return SEATS.map((seat) => {
    const side = NODES[seat.approach];
    const foot = seat.facing === "lying" ? side : seatFoot(seat);
    return { id: seat.id, scene: seat.scene, facing: seat.facing, approach: Boolean(side),
      unknown: seat.footprints.filter((name) => !FOOTPRINTS[name]), own: seat.footprints,
      step: side ? touched(side, foot) : null, desk: Boolean(seat.workstation),
      order: roomSeats(roomOfSeat(seat)).indexOf(seat) };
  });
}"""


def test_seat_table_entries_and_seat_steps(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_demo(driver, hq.url, 1440)
        seats = page.evaluate(SEAT_TABLE_SCRIPT)
        assert not errors
        browser.close()
    assert [seat["id"] for seat in seats] == ["studio0.0", "studio0.1", "studio0.2", "studio0.3", "studio1.0", "studio1.1",
                                              "common.0", "common.1", "fika.0", "fika.1", "fika.2", "infirmary.0"]
    for seat in seats:
        assert seat["scene"] == "main" and seat["approach"] and not seat["unknown"], seat
        assert seat["facing"] in {"front", "back", "front-right", "back-left", "lying"}, seat
        assert set(seat["step"]) <= set(seat["own"]), seat
        assert seat["order"] == int(seat["id"].split(".")[1]), seat
        assert seat["desk"] == seat["id"].startswith(("studio", "common")), seat


# Screen points of a drawn colleague's working arms and of the mouse its pointer hand moves to, and the screen points
# of its seat's workstation, in CSS pixels.
HANDS_SCRIPT = """async (key) => {
  const { SEATS } = await import("/seats.js");
  const node = [...document.querySelectorAll("#characters .agent")].find((n) => n.dataset.employeeKey === key);
  const svg = node.querySelector(":scope > .character");
  const seat = SEATS.find((s) => s.id === node.dataset.room + "." + node.dataset.seatIndex);
  const world = document.getElementById("world").getBoundingClientRect();
  const screen = (svgPoint, element) => { const p = new DOMPoint(svgPoint.x, svgPoint.y).matrixTransform(element.getScreenCTM()); return [p.x, p.y]; };
  const arms = [...svg.querySelectorAll('path[stroke-width="2.3"]')];
  const ends = arms.map((arm) => arm.getPointAtLength(arm.getTotalLength()));
  const style = getComputedStyle(svg);
  const mouse = { x: ends[1].x + parseFloat(svg.style.getPropertyValue("--mouse-x")), y: ends[1].y + parseFloat(svg.style.getPropertyValue("--mouse-y")) };
  return { facing: node.dataset.seatFacing, pose: svg.dataset.pose, mirror: style.transform,
    hands: [screen(ends[0], arms[0]), screen(ends[1], arms[1]), screen(mouse, arms[1])],
    keys: seat.workstation.map(([x, y]) => [world.x + x / 1536 * world.width, world.y + y / 1024 * world.height]) };
}"""

# Turns the front desk seat of a working demo colleague into a mirrored "front-right" seat for this page only: the
# module's table entry is changed in place and its workstation mirrored about the seat, then the office redraws.
MIRROR_SCRIPT = """async (id) => {
  const { SEATS } = await import("/seats.js");
  const seat = SEATS.find((s) => s.id === id);
  const axis = seat.position[0] * 15.36;
  seat.facing = "front-right";
  seat.workstation = seat.workstation.map(([x, y]) => [2 * axis - x, y]);
  document.querySelector('#filters [data-filter="all"]').click();
}"""


def test_front_right_desk_seat_draws_mirrored_hands_on_its_workstation(tmp_path):
    def assert_on_workstation(record):
        for hand, key in zip(record["hands"], record["keys"]):
            assert abs(hand[0] - key[0]) < 1 and abs(hand[1] - key[1]) < 1, record

    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_demo(driver, hq.url, 1440)
        # Unmirrored desks first: rear-facing (studio0.0, common.0) and front-facing (studio0.2).
        for key, facing in [('["garden","sage"]', "back"), ('["home","noah"]', "back"), ('["home","milo"]', "front")]:
            record = page.evaluate(HANDS_SCRIPT, key)
            assert (record["facing"], record["pose"], record["mirror"]) == (facing, facing, "none")
            assert_on_workstation(record)
        before = page.evaluate(HANDS_SCRIPT, '["home","milo"]')
        page.evaluate(MIRROR_SCRIPT, "studio0.2")
        record = page.evaluate(HANDS_SCRIPT, '["home","milo"]')
        assert (record["facing"], record["pose"], record["mirror"]) == ("front-right", "front-right", "matrix(-1, 0, 0, 1, 0, 0)")
        assert_on_workstation(record)
        # The pointer hand and the mouse are now on the other side of the figure.
        assert (record["keys"][2][0] - record["keys"][1][0]) * (before["keys"][2][0] - before["keys"][1][0]) < 0
        assert record["hands"][2][0] < record["hands"][1][0] < record["hands"][0][0]
        assert not errors
        browser.close()
