"""Sixty-seat audit (M2 post-closure, D13): routes from every seat, simultaneous occupancy, and depth layers."""

import base64
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
@pytest.mark.parametrize("width", [1440, 720])
def test_simultaneous_seats_keep_figures_apart(tmp_path, scenario, width):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        if scenario == "teams":
            full_tables(hq)
        browser, page, errors = open_page(driver, hq.url + ("/?demo=seats" if scenario == "seats" else ""), width)
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
        assert not [item for item in found if item[0] > OVERLAP_TOLERANCE], found[:10]
        assert not errors
        browser.close()


@pytest.mark.parametrize("width", [1440, 720])
@pytest.mark.parametrize("edit", ["fika", "meeting", "divider"])
def test_artwork_edits_keep_pixels_outside_approved_regions(tmp_path, width, edit):
    inputs = {"fika":"fika-spacing-annotations.json","meeting":"meeting-open-annotations.json",
              "divider":"meeting-divider-annotations.json"}
    polygons = []
    for name in inputs.values():
        annotation = json.loads((Path(__file__).parents[2] / "docs/design" / name).read_text())
        polygon = annotation.get("display_polygon")
        if polygon is None:
            x, y, width_source, height_source = annotation["display_bounds"]
            polygon = [[x,y],[x+width_source,y],[x+width_source,y+height_source],[x,y+height_source]]
        polygons.append(polygon)
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + "/?demo=seats", width)
        playwright.expect(page.locator("#characters .agent.seated")).to_have_count(60)
        page.locator("#setting-daylight").select_option("day", force=True)
        page.add_style_tag(content="#characters { visibility:hidden!important }")
        world = page.locator("#world")
        edited = world.screenshot(animations="disabled")
        playwright.expect(page.locator(f'.artwork-patch [data-artwork-edit="{edit}"]')).to_have_count(1)
        page.locator(f'[data-artwork-edit="{edit}"]').evaluate_all("""async (nodes, source) => {
          const original=new Image();original.src='/'+source;await original.decode();
          nodes.forEach(node=>node.querySelector('image').setAttribute('href',source));
        }""", "office-meeting-open.png" if edit == "divider" else "office-modern.png")
        original = world.screenshot(animations="disabled")
        result = page.evaluate("""async ({edited,original,polygons,subject}) => {
          const decode = async text => createImageBitmap(new Blob([Uint8Array.from(atob(text),c=>c.charCodeAt(0))]));
          const first = await decode(edited), second = await decode(original);
          const canvas = document.createElement('canvas'); canvas.width=first.width; canvas.height=first.height;
          const context = canvas.getContext('2d');
          context.drawImage(first,0,0); const a=context.getImageData(0,0,first.width,first.height).data;
          context.clearRect(0,0,first.width,first.height); context.drawImage(second,0,0);
          const b=context.getImageData(0,0,first.width,first.height).data;
          const sx=first.width/1536, sy=first.height/1024;
          const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
          svg.style.cssText='position:absolute;width:0;height:0;pointer-events:none';
          document.body.append(svg);
          const regions=polygons.map(points=>{
            const region=document.createElementNS(svg.namespaceURI,'polygon');
            region.setAttribute('points',points.map(p=>p.join(',')).join(' '));
            // Fractional SVG clipping can cover the raster pixel along the measured boundary.
            region.setAttribute('stroke-width',3/Math.min(sx,sy));svg.append(region);return region;
          });
          let inside=0,other=0,outside=0;const outside_sample=[];
          for(let row=0;row<first.height;row++)for(let col=0;col<first.width;col++) {
            const i=(row*first.width+col)*4;
            if(a[i]===b[i]&&a[i+1]===b[i+1]&&a[i+2]===b[i+2]&&a[i+3]===b[i+3])continue;
            const point=new DOMPoint((col+.5)/sx,(row+.5)/sy);
            const contains=region=>region.isPointInFill(point)||region.isPointInStroke(point);
            if(contains(regions[subject]))inside++;
            else if(regions.some(contains))other++;
            else {outside++;if(outside_sample.length<24)outside_sample.push({x:col,y:row,
              a:[...a.slice(i,i+4)],b:[...b.slice(i,i+4)]});}
          }
          svg.remove();first.close();second.close();return {inside,other,outside,outside_sample};
        }""", {"edited": base64.b64encode(edited).decode(), "original": base64.b64encode(original).decode(),
                "polygons": polygons,"subject":list(inputs).index(edit)})
        assert result["inside"] > 1000, result
        if result["outside"]:
            (tmp_path / "edited.png").write_bytes(edited)
            (tmp_path / "original.png").write_bytes(original)
            (tmp_path / "pixel-difference.json").write_text(json.dumps(result,indent=2)+"\n")
        assert result["outside"] == 0, result
        assert not errors
        browser.close()


def test_wall_display_has_no_floor_stand_remnants(tmp_path):
    annotation = json.loads((Path(__file__).parents[2] / "docs/design/meeting-divider-annotations.json").read_text())
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + "/?demo=seats", 1900)
        playwright.expect(page.locator("#characters .agent.seated")).to_have_count(60)
        page.locator("#setting-daylight").select_option("day", force=True)
        page.add_style_tag(content="#world {position:fixed!important;left:0!important;top:0!important;"
                           "width:1536px!important;transform:none!important}"
                           "#world > :not(.office-art):not(.artwork-patch){visibility:hidden!important}")
        world = page.locator("#world")
        assert world.bounding_box()["width"] == 1536
        screenshot = world.screenshot(animations="disabled")
        result = page.evaluate("""async ({rendered,samples,source}) => {
          const png=await createImageBitmap(new Blob([Uint8Array.from(atob(rendered),c=>c.charCodeAt(0))]));
          const expected=new Image();expected.src='/'+source;await expected.decode();
          const canvas=document.createElement('canvas');canvas.width=1536;canvas.height=1024;
          const ctx=canvas.getContext('2d');ctx.drawImage(png,0,0);
          const actual=samples.map(([x,y])=>[...ctx.getImageData(x,y,1,1).data]);
          ctx.clearRect(0,0,1536,1024);ctx.drawImage(expected,0,0);
          const wanted=samples.map(([x,y])=>[...ctx.getImageData(x,y,1,1).data]);
          png.close();return actual.map((pixel,i)=>({point:samples[i],actual:pixel,expected:wanted[i],
            error:Math.max(...pixel.map((value,c)=>Math.abs(value-wanted[i][c])))}));
        }""", {"rendered":base64.b64encode(screenshot).decode(),
                 "samples":annotation["removed_stand_samples"],"source":Path(annotation["source"]).name})
        (tmp_path / "stand-pixels.json").write_text(json.dumps(result,indent=2)+"\n")
        if any(row["error"] > 3 for row in result):
            (tmp_path / "stand-remnants.png").write_bytes(screenshot)
        assert all(row["error"] <= 3 for row in result), result
        assert not errors
        browser.close()


def test_empty_office_fades_original_and_edited_artwork_together(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator("#scene.is-empty")).to_have_count(1)
        page.locator("#setting-daylight").select_option("day",force=True)
        page.clock.pause_at(page.evaluate("Date.now()+100"))
        page.add_style_tag(content="#characters,#characters *,.office-cat,.office-cat *,.scene-empty,.scene-empty * {visibility:hidden!important}")
        world = page.locator("#world")
        empty = world.screenshot(animations="disabled")
        rect = world.bounding_box()
        hidden = page.add_style_tag(content="#world,#world * {visibility:hidden!important}")
        backdrop = page.screenshot(clip=rect,animations="disabled")
        hidden.evaluate("node=>node.remove()")
        hq.send(payload=roster(hq,[("alpha",1)],"working"))
        playwright.expect(page.locator("#characters .agent")).to_have_count(1)
        playwright.expect(page.locator("#scene.is-empty")).to_have_count(0)
        occupied = world.screenshot(animations="disabled")
        result = page.evaluate("""async ({empty,backdrop,occupied}) => {
          const images=await Promise.all([empty,backdrop,occupied].map(async text=>
            createImageBitmap(new Blob([Uint8Array.from(atob(text),c=>c.charCodeAt(0))]))));
          const [first]=images,canvas=document.createElement('canvas');canvas.width=first.width;canvas.height=first.height;
          const ctx=canvas.getContext('2d'),data=images.map(image=>{
            ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0);
            return ctx.getImageData(0,0,canvas.width,canvas.height).data;
          });
          // Static wall, Fika and floor samples measure the complete scene opacity.
          const samples=[[1015,265],[1190,360],[1300,285],[1128,760],[600,600]];
          const screens=[...document.querySelectorAll(".presentation-layer [data-presentation-screen]")]
            .map(node=>document.getElementById(node.getAttribute("clip-path").slice(5,-1)).querySelector("polygon"));
          if(samples.some(point=>screens.some(screen=>screen.isPointInFill(new DOMPoint(...point)))))
            throw new Error("Static fade samples intersect a presentation screen");
          const rows=samples.map(([x,y])=>{
            const col=Math.floor(x/1536*first.width),row=Math.floor(y/1024*first.height),i=(row*first.width+col)*4;
            const actual=[...data[0].slice(i,i+3)],normal=[...data[2].slice(i,i+3)],background=[...data[1].slice(i,i+3)];
            const expected=normal.map((v,c)=>.45*v+.55*background[c]);
            return {source:[x,y],error:Math.max(...actual.map((v,c)=>Math.abs(v-expected[c])))};
          });
          images.forEach(image=>image.close());return rows;
        }""", {name:base64.b64encode(value).decode() for name,value in
               [("empty",empty),("backdrop",backdrop),("occupied",occupied)]})
        maximum = max(row["error"] for row in result)
        if maximum > 3:
            for name,value in [("empty",empty),("backdrop",backdrop),("occupied",occupied)]:
                (tmp_path / (name+".png")).write_bytes(value)
        # Three 8-bit channel levels accommodate native raster and compositing quantization.
        assert maximum <= 3, result
        assert not errors
        browser.close()


def test_meeting_geometry_matches_image_annotations(tmp_path):
    annotation = json.loads((Path(__file__).parents[2] / "docs/design/meeting-open-annotations.json").read_text())
    divider = json.loads((Path(__file__).parents[2] / "docs/design/meeting-divider-annotations.json").read_text())
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page()
        page.goto(hq.url + "/favicon.svg")
        actual = page.evaluate("""async () => {
          const {GEOMETRY}=await import('/office-modern-data.js');
          const {SEATS,WALK_SURFACES,FRAMES,LAMPS}=await import('/office-layout.js');
          return {contacts:GEOMETRY.contacts,surfaces:GEOMETRY.surfaces,tabletops:GEOMETRY.tabletops,
            seats:Object.fromEntries(SEATS.filter(s=>s.kind==='meeting').map(s=>[s.sourceId,
              {hip:s.hip,ground_y:s.groundY,support_y:s.supportY}])),
            walking:WALK_SURFACES.map(s=>s.footprint),frames:FRAMES.map(f=>f.name),lamps:LAMPS};
        }""")
        assert actual["contacts"].get("meeting-separator") == divider["divider_contact"]
        assert divider["removed_contact"] not in actual["contacts"]
        surface = next(item for item in actual["surfaces"] if item["name"] == "meeting-separator")
        assert surface["polygon"] == divider["divider_face"]
        assert surface["depth"] == divider["divider_depth"]
        assert "meeting-separator" in actual["walking"]
        assert divider["removed_contact"] not in actual["walking"]
        for name in set(annotation["removed_contacts"]) - {"meeting-separator"}:
            assert name not in actual["contacts"], name
            assert name not in actual["walking"], name
        assert actual["contacts"]["north-meeting-west"] == annotation["upper_left_wall"]
        assert len(actual["seats"]) == 12
        for key, seat in annotation["seats"].items():
            assert actual["seats"][key] == {name:seat[name] for name in ("hip","ground_y","support_y")}
        for name, polygon in annotation["tabletops"].items():
            assert actual["tabletops"][name] == polygon
        assert not {"meeting-north","meeting-east"}.intersection(actual["frames"])
        assert [1084,183,35] not in actual["lamps"] and [1284,330,35] not in actual["lamps"]
        page.goto(hq.url + "/?demo=seats")
        playwright.expect(page.locator("#characters .agent.seated")).to_have_count(60)
        page.locator("#setting-daylight").select_option("night",force=True)
        glass = page.evaluate("""sample => {
          const polygons=[...document.querySelectorAll('#office-window-glass polygon')];
          return {last:polygons.at(-1).getAttribute('points'),
            solid:polygons.some(node=>node.isPointInFill(new DOMPoint(...sample))),
            period:document.querySelector('#scene').dataset.daylight,
            stars:Number(getComputedStyle(document.querySelector('.night-sky')).opacity)};
        }""",divider["solid_wall_samples"][1])
        assert glass["last"] == " ".join(",".join(map(str,point)) for point in divider["perimeter_glass"])
        assert not glass["solid"]
        assert glass["period"] == "night" and glass["stars"] > 0
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
            # Three Projects exercise standing Contractors behind foreground furniture as well as clear spots.
            payload = roster(hq, [("alpha", 8), ("bravo", 8), ("charlie", 4)], "working")
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
