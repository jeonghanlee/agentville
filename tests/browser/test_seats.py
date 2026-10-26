"""Modern office capacity, shared vacancies and real live meeting transitions."""

import copy
from datetime import timedelta
import json
import re
from pathlib import Path

import pytest

from agentville.common.protocol import iso
from tests.browser_support import launch_options, playwright_sync
from tests.lifecycle_support import BRANCH, HQ

playwright = playwright_sync()
ANNOTATIONS = json.loads((Path(__file__).parent / "fixtures/modern-image-annotations.json").read_text())
DESK_COUNTS = [("alpha", 4), ("bravo", 4), ("charlie", 4), ("delta", 6), ("common-office", 2)]


def roster(hq, counts=DESK_COUNTS, state="waiting"):
    at = iso(hq.clock[0])
    people, activities = [], []
    for project, count in counts:
        for i in range(count):
            identity = f"{project}-{i}"
            people.append({"agent_id": identity, "alias": identity, "project_id": project, "project_alias": project,
                           "provider": "codex", "seat": len(people) + 1, "presence": "on_duty", "presence_since": at,
                           "condition": "normal", "instance": {"instance_id": "shift-" + identity, "started_at": at,
                           "runtime": {"type": "shell"}}})
            activities.append({"agent_id": identity, "instance_id": "shift-" + identity, "state": state,
                               "state_since": at, "tool": "Read" if state == "working" else "",
                               "source": "session_log", "confidence": "high"})
    return {"branch": copy.deepcopy(BRANCH), "agents": people, "activities": activities, "contractors": []}


STATE_FRAMES = {}


def open_page(driver, url, width=1440, motion="reduce"):
    browser = driver.chromium.launch(**launch_options())
    page = browser.new_page(viewport={"width": width, "height": 1100}, reduced_motion=motion, locale="en-US")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.clock.install()
    # Live state frames received, so a test can wait for an update before moving the page clock.
    frames = STATE_FRAMES.setdefault(id(page), [0])
    page.on("websocket", lambda socket: socket.on(
        "framereceived", lambda payload: frames.__setitem__(0, frames[0] + 1) if '"state"' in str(payload) else None))
    page.goto(url)
    return browser, page, errors


def placements(page):
    return page.locator("#characters .agent").evaluate_all("""nodes => nodes.map(node => ({
      key:node.dataset.employeeKey,room:node.dataset.room,index:node.dataset.seatIndex,
      facing:node.dataset.seatFacing,x:parseFloat(node.style.left),y:parseFloat(node.style.top),
      walking:node.classList.contains('walking'),queue:node.dataset.queuePosition,
      working:!!node.querySelector('[data-work-gesture]'),hands:node.querySelectorAll('.keyboard-reach').length
    }))""")


@pytest.mark.parametrize("width", [1440, 720])
def test_all_sixty_seats_match_independent_image_measurements(tmp_path, width):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + "/?demo=seats", width)
        playwright.expect(page.locator("#characters .agent")).to_have_count(60)
        for zoom in [100, 175]:
            if zoom == 175:
                for _ in range(3):
                    page.locator("#zoom-in").click()
            observed = placements(page)
            by_id = {row["room"] + "." + row["index"]: row for row in observed}
            assert len(by_id) == 60
            for seat in ANNOTATIONS["seats"]:
                seen = by_id[seat["id"]]
                assert seen["facing"] == seat["facing"], (seat, seen)
                assert abs(seen["x"] * 15.36 - seat["anchor"][0]) < .02, (seat, seen)
                assert abs(seen["y"] * 10.24 - seat["anchor"][1]) < .02, (seat, seen)
                assert not seen["walking"]
                if seen["room"].startswith("meeting"):
                    assert not seen["working"] and not seen["hands"]
            assert page.locator(".flower").count() == 0
            assert page.locator(".painting").count() == 4
            assert len(set(page.locator(".painting").evaluate_all("nodes=>nodes.map(n=>n.dataset.painting)"))) == 4
            for period in ["morning", "day", "evening", "night"]:
                page.locator("#setting-daylight").select_option(period, force=True)
                playwright.expect(page.locator("#scene")).to_have_attribute("data-daylight", period)
            page.screenshot(path=str(tmp_path / f"seats-{width}-{zoom}.png"), full_page=True)
        assert not errors
        browser.close()


@pytest.mark.parametrize("width", [1440, 720])
@pytest.mark.parametrize("staggered", [False, True])
def test_live_arrivals_reservations_overflow_and_four_project_pages(tmp_path, staggered, width):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq)
        initial = copy.deepcopy(payload)
        if staggered:
            initial["agents"] = initial["agents"][::2]
            identities = {a["agent_id"] for a in initial["agents"]}
            initial["activities"] = [a for a in initial["activities"] if a["agent_id"] in identities]
        hq.send(payload=initial)
        browser, page, errors = open_page(driver, hq.url, width)
        playwright.expect(page.locator("#characters .agent")).to_have_count(len(initial["agents"]))
        if staggered:
            before = {row["key"]: (row["room"], row["index"]) for row in placements(page)}
            hq.advance(); hq.send(payload=payload)
            playwright.expect(page.locator("#characters .agent")).to_have_count(20)
            after = {row["key"]: (row["room"], row["index"]) for row in placements(page)}
            assert all(after[key] == value for key, value in before.items())
        seen = placements(page)
        assert len({(row["room"], row["index"]) for row in seen}) == 20
        assert not page.locator(".room-overflow").count()
        removed = copy.deepcopy(payload)
        removed["agents"] = [a for a in removed["agents"] if a["agent_id"] != "alpha-1"]
        removed["activities"] = [a for a in removed["activities"] if a["agent_id"] != "alpha-1"]
        before = {row["key"]: row["index"] for row in seen}
        hq.advance(); hq.send(payload=removed)
        playwright.expect(page.locator("#characters .agent")).to_have_count(19)
        hq.advance(); hq.send(payload=payload)
        playwright.expect(page.locator("#characters .agent")).to_have_count(20)
        assert {row["key"]: row["index"] for row in placements(page)} == before
        expanded = roster(hq, DESK_COUNTS + [("echo", 1)])
        hq.advance(); hq.send(payload=expanded)
        playwright.expect(page.locator("#floor-label")).to_have_text("1 / 2")
        page.locator("#next-floor").click()
        playwright.expect(page.locator("#floor-label")).to_have_text("2 / 2")
        assert {row["room"] for row in placements(page)} <= {"studio0", "common"}
        page.locator("#search").fill("alpha-0")
        page.locator("#team-list button").filter(has_text="alpha-0").click()
        playwright.expect(page.locator("#floor-label")).to_have_text("1 / 2")
        page.locator('#characters .agent[data-employee-key=\'["b1","alpha-0"]\']').focus()
        page.keyboard.press("Enter")
        playwright.expect(page.locator("#employee-detail")).to_contain_text("alpha-0")
        page.locator("#search").fill("")
        overflow = roster(hq, [("alpha", 21), ("bravo", 1)])
        hq.advance(); hq.send(payload=overflow)
        playwright.expect(page.locator(".room-overflow")).to_have_text("+2")
        seen = placements(page)
        assert len(seen) == 20
        assert sum("alpha-" in row["key"] for row in seen) == 19
        assert len({(row["room"], row["index"]) for row in seen}) == 20
        assert not errors
        browser.close()


def test_live_meeting_entry_refill_exit_reserves_desks_and_keeps_identity(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 7), ("bravo", 2)], "working")
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator('#characters .agent[data-room="studio0"]')).to_have_count(4)
        page.clock.fast_forward(59000)
        assert not page.locator('#characters .agent[data-room="meeting"]').count()
        page.clock.fast_forward(1000)
        playwright.expect(page.locator('#characters .agent[data-room="meeting"]')).to_have_count(6)
        assert not page.locator('#characters .agent[data-room="studio0"]').count()
        assert page.locator(".room-overflow").count() == 0
        playwright.expect(page.locator('#characters .agent[data-room="meeting-east"]')).to_have_count(2)
        assert {row["key"] for row in placements(page) if row["room"] == "meeting"} == {
            json.dumps(["b1", f"alpha-{i}"], separators=(",", ":")) for i in range(6)}
        for row in placements(page):
            if row["room"].startswith("meeting"):
                assert not row["hands"] and not row["working"]
        changed = copy.deepcopy(payload)
        changed["activities"][0]["state"] = "waiting"
        hq.advance(); hq.send(payload=changed)
        page.wait_for_function("[...document.querySelectorAll('[data-room=meeting]')].some(n=>n.dataset.employeeKey===JSON.stringify(['b1','alpha-6']))")
        at_desk = [row for row in placements(page) if row["room"] == "studio0"]
        assert len(at_desk) == 1 and at_desk[0]["key"] == '["b1","alpha-0"]' and at_desk[0]["index"] == "0"
        page.locator('#rooms [data-focus-key="room-project:alpha"]').click()
        assert page.locator('#characters .agent[data-room="meeting"].filtered').count() == 0
        page.locator("#team-list button").filter(has_text="alpha-6").click()
        playwright.expect(page.locator("#employee-detail")).to_contain_text("alpha-6")
        changed["activities"][1]["state"] = "idle"
        hq.advance(); hq.send(payload=changed)
        playwright.expect(page.locator('#characters .agent[data-employee-key=\'["b1","alpha-1"]\']')).to_have_class(re.compile(r"\bidle\b"))
        page.clock.fast_forward(29000)
        assert len([row for row in placements(page) if row["key"] == '["b1","alpha-1"]' and row["room"] == "meeting"]) == 1
        page.clock.fast_forward(1000)
        assert len([row for row in placements(page) if row["key"] == '["b1","alpha-1"]' and row["room"] == "studio0"]) == 1
        assert not errors
        browser.close()


@pytest.mark.parametrize("width", [1440, 720])
def test_facility_seats_are_used_before_distinct_waiting_spots(tmp_path, width):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 39)], "idle")
        old = iso(hq.clock[0] - timedelta(seconds=4300))
        for i, activity in enumerate(payload["activities"]):
            activity["state_since"] = old
            if i >= 34:
                activity["state"] = "error"
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url, width)
        playwright.expect(page.locator("#characters .agent")).to_have_count(39)
        seen = placements(page)
        assert len([row for row in seen if row["room"] == "fika" and row["index"]]) == 28
        assert len([row for row in seen if row["room"] == "fika" and row["queue"]]) == 6
        assert len([row for row in seen if row["room"] != "fika"]) == 5
        assert not page.locator('[data-room="infirmary"]').count()
        assert len({(row["x"], row["y"]) for row in seen}) == 39
        assert not any(row["walking"] for row in seen)
        held = {row["key"]: row["index"] for row in seen if row["index"]}
        payload["activities"][0].update(state="waiting", state_since=iso(hq.clock[0]))
        payload["activities"][34].update(state="waiting", state_since=iso(hq.clock[0]))
        hq.advance(); hq.send(payload=payload)
        playwright.expect(page.locator('#characters .agent:not([data-room="fika"])')).to_have_count(6)
        after = {row["key"]: row for row in placements(page)}
        assert after['["b1","alpha-28"]']["index"] == "0"
        for key, index in held.items():
            if key != '["b1","alpha-0"]':
                assert after[key]["index"] == index
        assert not errors
        browser.close()


def test_motion_walks_between_desk_fika_counter_and_error_desk(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 3)])
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url, motion="no-preference")
        playwright.expect(page.locator("#characters .agent")).to_have_count(3)
        old = "2020-01-01T00:00:00.000Z"
        for activity in payload["activities"]:
            activity.update(state="idle", state_since=old)
        hq.advance(); hq.send(payload=payload)
        playwright.expect(page.locator('#characters .agent[data-room="fika"].walking')).not_to_have_count(0)
        # Redirect one colleague while it is on the seat departure step.
        payload["activities"][0].update(state="error", state_since=iso(hq.clock[0]))
        hq.advance(); hq.send(payload=payload)
        playwright.expect(page.locator('#characters .agent.error')).to_have_count(1)
        visited_counter = False
        for _ in range(90):
            page.clock.run_for(500)
            visits = page.locator('.agent[data-coffee-phase="waiting"]')
            assert visits.count() <= 1
            visited_counter |= visits.count() == 1
        assert visited_counter
        error_desk = page.locator('#characters .agent.error')
        playwright.expect(error_desk).to_have_class(re.compile(r"\bseated\b"))
        assert not error_desk.locator('[data-pose="walking"]').count()
        assert not page.locator('[data-room="infirmary"]').count()
        assert not errors
        browser.close()


def test_off_page_remote_meeting_reconnect_reload_and_replay(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, DESK_COUNTS + [("echo", 3)])
        for activity in payload["activities"]:
            if activity["agent_id"].startswith("echo"):
                activity["state"] = "working"
        hq.send(payload=payload)
        remote = roster(hq, [("echo", 1)], "working")
        hq.send(payload=remote, branch="b2")
        browser, page, errors = open_page(driver, hq.url)
        page.add_init_script("""const NativeSocket=window.WebSocket;window.observedSockets=[];
          window.WebSocket=class extends NativeSocket {constructor(...args){super(...args);window.observedSockets.push(this);}};""")
        page.reload()
        playwright.expect(page.locator('#characters .agent[data-room="studio0"]')).to_have_count(4)
        page.get_by_role("button", name="Dashboard", exact=True).click()
        page.clock.fast_forward(60000)
        page.get_by_role("button", name="Virtual office", exact=True).click()
        meeting = page.locator('#characters .agent[data-room="meeting"]')
        playwright.expect(meeting).to_have_count(4)
        assert meeting.locator(".remote-badge").count() == 1
        assert len({row["key"] for row in placements(page)}) == 24
        page.locator("#next-floor").click()
        playwright.expect(meeting).to_have_count(4)
        assert all("common-office" in row["key"] for row in placements(page) if not row["room"].startswith("meeting"))
        page.locator("#previous-floor").click()
        page.evaluate("observedSockets.at(-1).close()")
        playwright.expect(page.locator("#office-open")).to_have_class(re.compile("unreachable"))
        for activity in payload["activities"]:
            if activity["agent_id"] == "echo-0":
                activity["state"] = "idle"
        hq.advance(); hq.send(payload=payload)
        page.clock.fast_forward(1100)
        page.wait_for_function("observedSockets.length===2")
        playwright.expect(page.locator("#office-open")).not_to_have_class(re.compile("unreachable"))
        playwright.expect(meeting).to_have_count(4)
        page.clock.fast_forward(29000)
        playwright.expect(meeting).to_have_count(4)
        page.clock.fast_forward(1000)
        playwright.expect(meeting).to_have_count(3)
        page.reload()
        playwright.expect(page.locator("#branch-select option")).to_have_count(2)
        assert not meeting.count()
        page.clock.fast_forward(60000)
        playwright.expect(meeting).to_have_count(3)
        page.get_by_role("button", name="Timeline", exact=True).click()
        playwright.expect(page.locator(".change-event").first).to_be_visible()
        page.locator(".change-event").first.click()
        playwright.expect(page.locator("body")).to_have_class(re.compile("replaying"))
        playwright.expect(meeting).to_have_count(0)
        page.locator(".replay-live").click()
        playwright.expect(meeting).to_have_count(3)
        hq.close(kind="project", identity="echo")
        playwright.expect(meeting).to_have_count(0)
        assert not errors
        browser.close()


@pytest.mark.parametrize("mode,count", [("1", 3), ("meeting", 6)])
def test_fixed_demo_meeting_and_desk_reservations(tmp_path, mode, count):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + "/?demo=" + mode)
        meeting = page.locator('#characters .agent[data-room="meeting"]')
        playwright.expect(meeting).to_have_count(count)
        assert len(placements(page)) == (11 if mode == "1" else 60)
        if mode == "1":
            assert {row["key"] for row in placements(page) if row["room"] == "meeting"} == {
                '["home","milo"]', '["home","theo"]', '["garden","sage"]'}
            assert page.locator('#characters .agent[data-room="studio0"]').count() == 1
        else:
            page.locator("#next-floor").click()
            playwright.expect(meeting).to_have_count(count)
            assert not page.locator('#characters .agent[data-room="studio0"]').count()
            page.locator("#previous-floor").click()
            playwright.expect(meeting).to_have_count(count)
        assert not errors
        browser.close()


@pytest.mark.parametrize("width", [1440, 720])
def test_live_workstation_gestures_follow_independent_image_targets(tmp_path, width):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        hq.send(payload=roster(hq, state="working"))
        browser, page, errors = open_page(driver, hq.url, width)
        playwright.expect(page.locator("#characters .agent")).to_have_count(20)
        records = page.evaluate("""data => {
          const world=document.querySelector('#world').getBoundingClientRect();
          return [...document.querySelectorAll('#characters .agent')].map(node=>{
            const id=node.dataset.room+'.'+node.dataset.seatIndex;
            const seat=data.seats.find(s=>s.id===id),sprite=node.querySelector(':scope > .character');
            const arms=[...sprite.querySelectorAll('path[stroke-width="2.3"]')];
            const ends=arms.map(arm=>arm.getPointAtLength(arm.getTotalLength()));
            const mouse=new DOMPoint(ends[1].x+parseFloat(sprite.style.getPropertyValue('--mouse-x')),
              ends[1].y+parseFloat(sprite.style.getPropertyValue('--mouse-y')));
            const actual=[...ends,mouse].map((point,i)=>{
              const p=new DOMPoint(point.x,point.y).matrixTransform(arms[Math.min(i,1)].getScreenCTM());return [p.x,p.y];
            });
            const expected=seat.workstation.map(([x,y])=>[world.x+x/1536*world.width,world.y+y/1024*world.height]);
            return {id,actual,expected};
          });
        }""", ANNOTATIONS)
        assert len(records) == 20
        for record in records:
            assert all(max(abs(a-b) for a, b in zip(actual, expected)) < 1
                       for actual, expected in zip(record["actual"], record["expected"])), record
        assert not errors
        browser.close()


def test_live_meeting_walks_to_table_and_back_without_typing(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 2)], "working")
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url, motion="no-preference")
        playwright.expect(page.locator("#characters .agent")).to_have_count(2)
        page.clock.fast_forward(60000)
        meeting = page.locator('#characters .agent[data-room="meeting"]')
        playwright.expect(meeting).to_have_count(2)
        assert meeting.locator('[data-pose="walking"]').count() == 2
        page.clock.run_for(30000)
        playwright.expect(page.locator('#characters .agent[data-room="meeting"].seated')).to_have_count(2)
        assert not meeting.locator(".keyboard-reach, [data-work-gesture]").count()
        bubbles = False
        # Observe beyond the longest normal conversation gap without replacing randomness.
        for _ in range(32):
            page.clock.run_for(500)
            for glyph in meeting.locator(".talk-bubble").evaluate_all("nodes=>nodes.map(n=>n.dataset.glyph)"):
                bubbles = True
                assert glyph in {"dots", "heart", "coffee", "idea", "question", "note", "sun"}
        assert bubbles
        payload["activities"][0]["state"] = "waiting"
        hq.advance(); hq.send(payload=payload)
        playwright.expect(meeting).to_have_count(0)
        page.clock.run_for(30000)
        desks = page.locator('#characters .agent[data-room="studio0"].seated')
        playwright.expect(desks).to_have_count(2)
        assert {row["index"] for row in placements(page)} == {"0", "1"}
        assert not errors
        browser.close()
