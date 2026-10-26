"""Sixty-seat audit (M2 post-closure, D13): routes from every seat, simultaneous occupancy, and depth layers."""

import json
from pathlib import Path

import pytest

from tests.browser.png_alpha import alpha_mask
from tests.browser.test_contractor_teams import hire
from tests.browser.test_seats import open_page, roster
from tests.browser_support import launch_options, playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()
ANNOTATIONS = Path(__file__).parent / "fixtures" / "modern-image-annotations.json"
# Share of the smaller silhouette two seated figures may cover of each other.
OVERLAP_TOLERANCE = .1
# Artwork-side: the stools high-west.1 and high-east.0 of neighbouring high tables stand one behind the other in the
# picture, so their sitters cover each other (open item in the M2 record); no code placement can separate them.
KNOWN = {("fika.25", "fika.26")}
# Rendered figures without labels, signals, cats, artwork or furniture layers, so screenshots hold one silhouette.
HIDE = """() => { const style = document.createElement('style');
  style.textContent = '#world > :not(#characters){visibility:hidden!important}'
    + '#characters .agent-name,#characters .contractor-name,#characters .agent-signal,#characters .agent-seat-id,'
    + '#characters .contractor-tag,#characters small,#characters .done-check,#characters .talk-bubble,'
    + '#characters .office-cat,#characters .room-overflow{display:none!important}'
    + 'html,body,#world,.scene,.scene-viewport,.office-card{background:transparent!important}';
  document.head.append(style); }"""
FIGURES = """() => [...document.querySelectorAll('#characters .agent.seated, #characters .contractor.seated-contractor')]
  .map((node, i) => { node.dataset.auditIndex = i; const r = node.getBoundingClientRect();
    return { i, name: node.dataset.seat || node.dataset.room + '.' + node.dataset.seatIndex,
      contractor: node.classList.contains('contractor'), box: [r.left, r.top, r.width, r.height] }; })"""


def silhouettes(page):
    """Opaque pixels of each seated figure in page pixels, drawn alone."""
    page.evaluate(HIDE)
    figures = page.evaluate(FIGURES)
    for figure in figures:
        page.evaluate("""i => document.querySelectorAll('#characters .agent, #characters .contractor')
          .forEach(node => node.style.visibility = node.dataset.auditIndex === String(i) ? 'visible' : 'hidden')""", figure["i"])
        x, y, w, h = figure["box"]
        clip = {"x": max(0, int(x) - 2), "y": max(0, int(y) - 2), "width": int(w) + 5, "height": int(h) + 5}
        figure["pixels"] = {(px + clip["x"], py + clip["y"])
                            for px, py in alpha_mask(page.screenshot(clip=clip, omit_background=True))}
    return figures


def overlaps(figures):
    found = []
    for i, a in enumerate(figures):
        for b in figures[i + 1:]:
            shared = len(a["pixels"] & b["pixels"])
            if shared:
                found.append((shared / min(len(a["pixels"]), len(b["pixels"])), a["name"], b["name"]))
    return sorted(found, reverse=True)


def full_tables(hq):
    """Six teams: two fill both meeting rooms, four fill both Fika tables and both sofas."""
    payload = roster(hq, [("alpha", 4), ("bravo", 2)], "working")
    for agent_id, count in [("alpha-0", 5), ("alpha-1", 5), ("alpha-2", 7), ("alpha-3", 7), ("bravo-0", 2), ("bravo-1", 2)]:
        hire(hq, payload, agent_id, count)
    hq.send(payload=payload)


@pytest.mark.parametrize("scenario", ["seats", "teams"])
def test_simultaneous_seats_keep_figures_apart(tmp_path, scenario):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        if scenario == "teams":
            full_tables(hq)
        browser, page, errors = open_page(driver, hq.url + ("/?demo=seats" if scenario == "seats" else ""))
        if scenario == "seats":
            playwright.expect(page.locator("#characters .agent.seated")).to_have_count(60)
        else:
            playwright.expect(page.locator("#characters .contractor")).to_have_count(12)
            page.clock.fast_forward(10000)
            # 12 meeting chairs and 22 Fika table and sofa places: 6 colleagues and 28 seated Contractors.
            playwright.expect(page.locator("#characters .contractor.seated-contractor")).to_have_count(28)
        figures = silhouettes(page)
        assert len(figures) == (60 if scenario == "seats" else 34)
        assert all(figure["pixels"] for figure in figures)
        found = overlaps(figures)
        assert not [item for item in found if item[0] > OVERLAP_TOLERANCE and item[1:] not in KNOWN], found[:10]
        assert not errors
        browser.close()


DEPTH = """async () => {
  const {SURFACES} = await import('/office-layout.js');
  const {FOOTPRINTS} = await import('/floor.js');
  const {SEATS} = await import('/seats.js');
  const world = document.getElementById('world').getBoundingClientRect(), sx = world.width / 1536, sy = world.height / 1024;
  const span = (polygon, x) => { const ys = [];
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) { const [x1, y1] = polygon[j], [x2, y2] = polygon[i];
      if ((x1 <= x && x <= x2) || (x2 <= x && x <= x1)) ys.push(x1 === x2 ? Math.min(y1, y2) : y1 + (y2 - y1) * (x - x1) / (x2 - x1)); }
    return ys.length ? [Math.min(...ys), Math.max(...ys)] : null; };
  const failures = [], checked = [];
  for (const node of document.querySelectorAll('#characters .agent.seated, #characters .contractor')) {
    // Seated figures stand on the floor beneath the hip; standing Contractors on their feet.
    const standing = node.classList.contains('contractor') && !node.classList.contains('seated-contractor');
    const id = standing ? 'standing:' + node.dataset.parentKey : node.dataset.seat || node.dataset.room + '.' + node.dataset.seatIndex;
    const seat = standing ? { footprints: [] } : SEATS.find((s) => s.id === id);
    const r = node.getBoundingClientRect(), box = [(r.left - world.left) / sx, (r.top - world.top) / sy, (r.right - world.left) / sx, (r.bottom - world.top) / sy];
    const z = Number(node.style.zIndex);
    const fx = standing ? parseFloat(node.style.left) : seat.position[0], fy = standing ? parseFloat(node.style.top) : seat.groundY / 1024 * 100;
    for (const surface of SURFACES) {
      const points = surface.shapes.join(' ').trim().split(/\\s+/).map((p) => p.split(',').map(Number));
      const xs = points.map(([x]) => x), ys = points.map(([, y]) => y);
      if (Math.max(...xs) < box[0] || Math.min(...xs) > box[2] || Math.max(...ys) < box[1] || Math.min(...ys) > box[3]) continue;
      // The seat's own chair back and monitor are calibrated with the seat; other pieces follow the floor order.
      if (seat.footprints.includes(surface.footprint)) continue;
      const footprint = FOOTPRINTS[surface.footprint], fxs = footprint.map(([x]) => x);
      const s = span(footprint, Math.min(Math.max(fx, Math.min(...fxs)), Math.max(...fxs)));
      if (!s) continue;
      checked.push(id + '/' + surface.name);
      // A piece standing wholly in front of the floor beneath the hip covers the figure; one wholly behind is covered by it.
      if (s[0] > fy && surface.depth <= z) failures.push({ id, surface: surface.name, expected: 'front', z, depth: surface.depth });
      if (s[1] < fy && surface.depth >= z) failures.push({ id, surface: surface.name, expected: 'behind', z, depth: surface.depth });
    }
  }
  return { failures, checked: checked.length };
}"""


@pytest.mark.parametrize("scenario", ["seats", "teams", "desks"])
def test_figures_follow_furniture_depth_layers(tmp_path, scenario):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        if scenario == "teams":
            full_tables(hq)
        if scenario == "desks":
            payload = roster(hq, state="working")
            for agent in payload["agents"]:
                hire(hq, payload, agent["agent_id"], 2)
            hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url + ("/?demo=seats" if scenario == "seats" else ""))
        if scenario == "seats":
            playwright.expect(page.locator("#characters .agent.seated")).to_have_count(60)
        elif scenario == "desks":
            # Forty Contractors stand beside twenty desks before any team forms.
            playwright.expect(page.locator("#characters .contractor")).to_have_count(40)
        else:
            playwright.expect(page.locator("#characters .contractor")).to_have_count(12)
            page.clock.fast_forward(10000)
            playwright.expect(page.locator("#characters .contractor.seated-contractor")).to_have_count(28)
        result = page.evaluate(DEPTH)
        assert result["checked"] >= (1 if scenario == "desks" else 10)
        assert result["failures"] == []
        assert not errors
        browser.close()


PATHS = """async (data) => {
  const scene = await import('/floor.js');
  const {SEATS, seatFoot} = await import('/seats.js');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  document.documentElement.append(svg);
  const polygon = (points) => { const node = document.createElementNS(svg.namespaceURI, 'polygon');
    node.setAttribute('points', points.map((p) => p.join(',')).join(' ')); svg.append(node); return node; };
  const slab = polygon(data.floor), contacts = Object.entries(data.contacts).map(([id, points]) => [id, polygon(points), points]);
  const inside = (p, shape) => shape.isPointInFill(new DOMPoint(...p));
  const turn = (a, b, c) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  const crosses = (a, b, c, d) => turn(a,b,c)*turn(a,b,d) < 0 && turn(c,d,a)*turn(c,d,b) < 0;
  const hull = (points) => { points.sort((a,b) => a[0]-b[0] || a[1]-b[1]); const lower = [], upper = [];
    for (const p of points) { while (lower.length > 1 && turn(lower.at(-2), lower.at(-1), p) <= 0) lower.pop(); lower.push(p); }
    for (const p of [...points].reverse()) { while (upper.length > 1 && turn(upper.at(-2), upper.at(-1), p) <= 0) upper.pop(); upper.push(p); }
    return lower.slice(0, -1).concat(upper.slice(0, -1)); };
  // Independent foot box in source pixels: the 46 px aisle for circulation, the foot width for seat steps.
  const foot = (p, half) => { const x = p[0]*15.36, y = p[1]*10.24; return [[x-half,y-7.168],[x+half,y-7.168],[x+half,y+1.536],[x-half,y+1.536]]; };
  const failures = [], checked = new Map();
  const check = (a, b, own = [], wide = true, path = '') => {
    const key = JSON.stringify([a, b, own, wide]); if (checked.has(key)) return; checked.set(key, true);
    const swept = hull([...foot(a, wide ? 23 : 20.736), ...foot(b, wide ? 23 : 20.736)]);
    const edges = swept.map((p, i) => [p, swept[(i+1) % swept.length]]);
    if (swept.some((p) => !inside(p, slab)) || edges.some(([p, q]) => data.floor.some((c, i) => crosses(p, q, c, data.floor[(i+1) % data.floor.length]))))
      failures.push({ kind: 'slab', path, a, b });
    const shape = polygon(swept);
    for (const [id, node, points] of contacts) {
      if (own.includes(id)) continue;
      if (swept.some((p) => inside(p, node)) || points.some((p) => inside(p, shape))
        || edges.some(([p, q]) => points.some((c, i) => crosses(p, q, c, points[(i+1) % points.length])))) failures.push({ kind: 'contact', id, path, a, b });
    }
    shape.remove();
  };
  // The path a colleague walks, as the page builds it: off the seat through its approach, along the routes, onto the target.
  const targets = SEATS.filter((s) => s.id.startsWith('meeting')).map((s) => ({ name: s.id, foot: seatFoot(s), approach: scene.NODES[s.approach], own: s.footprints }))
    .concat([{ name: 'coffee', foot: scene.NODES.coffee, approach: null, own: [] }]);
  let paths = 0;
  for (const seat of SEATS) for (const target of targets) {
    if (target.name === seat.id) continue;
    const from = scene.NODES[seat.approach], name = seat.id + '->' + target.name;
    check(seatFoot(seat), from, seat.footprints, false, name);
    const route = scene.route(from, target.approach || target.foot);
    for (let i = 1; i < route.length; i++) check(route[i-1], route[i], [], true, name);
    if (target.approach) check(target.approach, target.foot, target.own, false, name);
    paths++;
  }
  svg.remove();
  return { failures, paths, segments: checked.size };
}"""


def test_every_seat_walks_clear_to_each_meeting_chair_and_the_coffee_spot(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page()
        page.goto(hq.url + "/favicon.svg")
        result = page.evaluate(PATHS, json.loads(ANNOTATIONS.read_text()))
        browser.close()
    # 60 seats to 12 meeting chairs (less its own chair for a meeting seat) and the coffee spot.
    assert result["paths"] == 60 * 13 - 12
    assert result["failures"] == [], result["failures"][:10]
