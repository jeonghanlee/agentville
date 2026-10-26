"""Contractor teams (architecture Section 6.2, D14): a colleague with Contractors works with them at a table."""

import copy
import json
import re
from datetime import timedelta

import pytest

from agentville.common.protocol import iso
from tests.browser.test_seated_presentation import MEASURE, area, contractor_conflicts, overlap
from tests.browser.test_seats import open_page, placements, roster
from tests.browser_support import launch_options, playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()


def key(agent_id, branch="b1"):
    return json.dumps([branch, agent_id], separators=(",", ":"))


def hire(hq, payload, agent_id, count, start=0):
    """Add count current Contractors to a colleague of the payload."""
    agent = next(row for row in payload["agents"] if row["agent_id"] == agent_id)
    for i in range(start, start + count):
        payload["contractors"].append({"contractor_id": f"helper-{agent_id}-{i}",
                                       "parent_instance_id": agent["instance"]["instance_id"],
                                       "provider": "codex" if i % 2 else "claude", "origin": "in_process",
                                       "status": "hired", "state": "working", "state_since": iso(hq.clock[0]),
                                       "tool": "Read"})


def dismiss(payload, agent_id):
    payload["contractors"] = [row for row in payload["contractors"] if not row["contractor_id"].startswith(f"helper-{agent_id}-")]


def resend(hq, payload):
    hq.advance()
    hq.send(payload=payload)


def contractors(page):
    return page.locator("#characters .contractor").evaluate_all("""nodes => nodes.map(node => ({
      parent:node.dataset.parentKey,seat:node.dataset.seat,seated:node.classList.contains('seated-contractor'),
      facing:node.dataset.seatFacing,x:parseFloat(node.style.left),y:parseFloat(node.style.top),
      more:node.querySelector(':scope > small')?.textContent||'',hat:!!node.querySelector('.hard-hat'),
      calibrated:!!node.querySelector(':scope > .calibrated-character')
    }))""")


def where(page, agent_id):
    return next((row for row in placements(page) if row["key"] == key(agent_id)), None)


def seated_with(page, agent_id):
    return sorted(row["seat"] for row in contractors(page) if row["parent"] == key(agent_id) and row["seated"])


def test_team_forms_after_ten_seconds_and_keeps_its_desk_reserved(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 2)], "working")
        hire(hq, payload, "alpha-0", 2)
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator("#characters .contractor")).to_have_count(2)
        assert where(page, "alpha-0")["room"] == "studio0" and where(page, "alpha-0")["index"] == "0"
        assert not any(row["seated"] for row in contractors(page))
        page.clock.fast_forward(9000)
        assert where(page, "alpha-0")["room"] == "studio0"
        page.clock.fast_forward(1000)
        playwright.expect(page.locator(f'#characters .agent[data-employee-key=\'{key("alpha-0")}\'][data-room="meeting"]')).to_have_count(1)
        assert where(page, "alpha-0")["index"] == "0"
        assert seated_with(page, "alpha-0") == ["meeting.1", "meeting.2"]
        # Seated Contractors use the seated sprites with the hard hat, facing like their chair.
        for row in contractors(page):
            assert row["hat"] and row["calibrated"] and row["facing"] == "back"
        # The desk stays reserved: it is shown empty and a newcomer takes the next desk.
        assert where(page, "alpha-1")["index"] == "1"
        payload = copy.deepcopy(payload)
        newcomer = copy.deepcopy(payload["agents"][1]); newcomer.update(agent_id="alpha-2", alias="alpha-2", seat=9)
        newcomer["instance"]["instance_id"] = "shift-alpha-2"
        activity = copy.deepcopy(payload["activities"][1]); activity.update(agent_id="alpha-2", instance_id="shift-alpha-2")
        payload["agents"].append(newcomer); payload["activities"].append(activity)
        resend(hq, payload)
        playwright.expect(page.locator("#characters .agent")).to_have_count(3)
        assert where(page, "alpha-2")["index"] == "2"
        assert not any(row["room"] == "studio0" and row["index"] == "0" for row in placements(page))
        # The team colleague stays a member of its Project room for filters and counts.
        page.locator('#rooms [data-focus-key="room-project:alpha"]').click()
        assert page.locator(f'#characters .agent[data-employee-key=\'{key("alpha-0")}\'].filtered').count() == 0
        assert not errors
        browser.close()


def test_team_ends_after_its_last_contractor_or_at_once_on_waiting(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 1), ("common-office", 1)], "working")
        hire(hq, payload, "common-office-0", 1)
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator("#characters .contractor")).to_have_count(1)
        desk = (where(page, "common-office-0")["room"], where(page, "common-office-0")["index"])
        page.clock.fast_forward(10000)
        # Common Office colleagues form teams too.
        playwright.expect(page.locator('#characters .agent[data-room="meeting"]')).to_have_count(1)
        dismiss(payload, "common-office-0")
        resend(hq, payload)
        playwright.expect(page.locator("#characters .contractor")).to_have_count(0)
        page.clock.fast_forward(9000)
        assert where(page, "common-office-0")["room"] == "meeting"
        page.clock.fast_forward(1000)
        playwright.expect(page.locator('#characters .agent[data-room="meeting"]')).to_have_count(0)
        assert (where(page, "common-office-0")["room"], where(page, "common-office-0")["index"]) == desk
        # A new Contractor within the grace keeps the team; waiting ends it at once, with Contractors beside the desk.
        hire(hq, payload, "common-office-0", 2, start=5)
        resend(hq, payload)
        page.clock.fast_forward(10000)
        playwright.expect(page.locator('#characters .agent[data-room="meeting"]')).to_have_count(1)
        dismiss(payload, "common-office-0"); resend(hq, payload)
        page.clock.fast_forward(5000)
        hire(hq, payload, "common-office-0", 2, start=7); resend(hq, payload)
        page.clock.fast_forward(8000)
        assert where(page, "common-office-0")["room"] == "meeting"
        payload["activities"][1]["state"] = "waiting"
        resend(hq, payload)
        playwright.expect(page.locator('#characters .agent[data-room="meeting"]')).to_have_count(0)
        assert (where(page, "common-office-0")["room"], where(page, "common-office-0")["index"]) == desk
        assert [row["seated"] for row in contractors(page)] == [False, False]
        assert not errors
        browser.close()


def test_meeting_and_team_never_displace_each_other(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 1), ("bravo", 2), ("charlie", 2)], "working")
        hire(hq, payload, "alpha-0", 1)
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator("#characters .agent")).to_have_count(5)
        page.clock.fast_forward(10000)
        playwright.expect(page.locator('#characters .agent[data-room="meeting"]')).to_have_count(1)
        page.clock.fast_forward(50000)
        # Both Projects qualify for a meeting; the team keeps its room and only one meeting starts.
        playwright.expect(page.locator('#characters .agent[data-room="meeting-east"]')).to_have_count(2)
        assert where(page, "alpha-0")["room"] == "meeting"
        assert {where(page, f"charlie-{i}")["room"] for i in range(2)} == {"studio2"}
        page.clock.fast_forward(30000)
        assert where(page, "alpha-0")["room"] == "meeting"
        # The other way: with both rooms in meetings, a new team does not displace either meeting.
        payload["activities"][0]["state"] = "waiting"
        resend(hq, payload)
        playwright.expect(page.locator('#characters .agent[data-room="meeting"]')).to_have_count(2)
        payload["activities"][0]["state"] = "working"
        hire(hq, payload, "alpha-0", 1, start=3)
        resend(hq, payload)
        page.clock.fast_forward(10000)
        playwright.expect(page.locator(f'#characters .agent[data-employee-key=\'{key("alpha-0")}\'][data-room="fika"]')).to_have_count(1)
        rooms = {row["key"]: row["room"] for row in placements(page)}
        assert sorted(room for room in rooms.values() if room.startswith("meeting")) == ["meeting"] * 2 + ["meeting-east"] * 2
        assert not errors
        browser.close()


def test_fika_fallback_takes_the_free_group_with_the_lowest_seat_id(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 2), ("bravo", 2), ("charlie", 2), ("delta", 1)], "working")
        payload["activities"][6].update(state="idle", state_since=iso(hq.clock[0] - timedelta(seconds=4300)))
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator("#characters .agent")).to_have_count(7)
        # delta-0 sits in Fika at fika.0, so the first Fika table is not free.
        assert (where(page, "delta-0")["room"], where(page, "delta-0")["index"]) == ("fika", "0")
        page.clock.fast_forward(60000)
        playwright.expect(page.locator('#characters .agent[data-room^="meeting"]')).to_have_count(4)
        hire(hq, payload, "charlie-0", 4)
        resend(hq, payload)
        page.clock.fast_forward(10000)
        # charlie-0 is not in a meeting (both rooms hold alpha and bravo); its team takes the second Fika table.
        playwright.expect(page.locator(f'#characters .agent[data-employee-key=\'{key("charlie-0")}\'][data-room="fika"]')).to_have_count(1)
        assert where(page, "charlie-0")["index"] == "8"
        assert seated_with(page, "charlie-0") == ["fika.10", "fika.11", "fika.12", "fika.9"]
        # Fika colleagues arriving later do not take the team's places.
        payload["activities"][5].update(state="idle", state_since=iso(hq.clock[0] - timedelta(seconds=4300)))
        resend(hq, payload)
        playwright.expect(page.locator(f'#characters .agent[data-employee-key=\'{key("charlie-1")}\'][data-room="fika"]')).to_have_count(1)
        assert where(page, "charlie-1")["index"] == "1"
        assert not errors
        browser.close()


def test_contractors_beyond_the_chairs_show_as_plus_n(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 2), ("bravo", 6), ("charlie", 1)], "working")
        hire(hq, payload, "charlie-0", 7)
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator("#characters .agent")).to_have_count(9)
        page.clock.fast_forward(10000)
        # The team takes the first room: colleague in chair 0, five Contractors, "+2" on the last seated one.
        playwright.expect(page.locator(f'#characters .agent[data-employee-key=\'{key("charlie-0")}\'][data-room="meeting"]')).to_have_count(1)
        seated = [row for row in contractors(page) if row["parent"] == key("charlie-0")]
        assert sorted(row["seat"] for row in seated) == [f"meeting.{i}" for i in range(1, 6)]
        assert [row["more"] for row in seated if row["more"]] == ["+2"]
        assert next(row for row in seated if row["more"])["seat"] == "meeting.5"
        page.clock.fast_forward(50000)
        # bravo meets in the other room with all six chairs, so its member's Contractor shows as "+1" on the member.
        # A meeting member does not form a team.
        playwright.expect(page.locator('#characters .agent[data-room="meeting-east"]')).to_have_count(6)
        hire(hq, payload, "bravo-0", 1)
        resend(hq, payload)
        page.clock.fast_forward(11000)
        playwright.expect(page.locator(f'#characters .agent[data-employee-key=\'{key("bravo-0")}\'] .team-more')).to_have_count(1)
        assert seated_with(page, "bravo-0") == []
        assert page.locator(f'#characters .agent[data-employee-key=\'{key("bravo-0")}\'] .team-more').text_content() == "+1"
        assert "1 more contractors" in page.locator(f'#characters .agent[data-employee-key=\'{key("bravo-0")}\']').get_attribute("aria-label")
        # The team ends at once; alpha (two members) meets in the freed room and brings four of five Contractors.
        payload["activities"][8]["state"] = "waiting"
        hire(hq, payload, "alpha-0", 5)
        resend(hq, payload)
        playwright.expect(page.locator('#characters .agent[data-room="meeting"]')).to_have_count(2)
        alpha = [row for row in contractors(page) if row["parent"] == key("alpha-0")]
        assert sorted(row["seat"] for row in alpha) == [f"meeting.{i}" for i in range(2, 6)]
        assert [row["more"] for row in alpha if row["more"]] == ["+1"]
        assert not errors
        browser.close()


@pytest.mark.parametrize("width", [1440, 720])
def test_desk_fallback_spaces_contractors_clear_of_other_figures(tmp_path, width):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, state="working")
        for agent in payload["agents"]:
            hire(hq, payload, agent["agent_id"], 2)
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url, width)
        playwright.expect(page.locator("#characters .contractor")).to_have_count(40)
        assert contractor_conflicts(page.evaluate(MEASURE)) == []
        assert not any(row["seated"] for row in contractors(page))
        page.clock.fast_forward(10000)
        # Two rooms and four Fika groups (two tables, two sofas) take six teams; fourteen stay at their desks.
        playwright.expect(page.locator('#characters .agent[data-team="room"]')).to_have_count(2)
        playwright.expect(page.locator('#characters .agent[data-team="fika"]')).to_have_count(4)
        assert page.locator('#characters .agent[data-team="desk"]').count() == 14
        scene = page.evaluate(MEASURE)
        at_desk = {row["key"] for row in placements(page) if not row["room"].startswith("meeting") and row["room"] != "fika"}
        assert contractor_conflicts(scene, at_desk) == []
        # Desks of teams away stay reserved and empty.
        desks = [row for row in placements(page) if row["room"].startswith("studio") or row["room"] == "common"]
        assert len(desks) == 14 and len({(row["room"], row["index"]) for row in desks}) == 14
        assert not errors
        browser.close()


# Wider provider tags than any Chromium build draws, so neighbouring seated Contractors' tags must be separated by the
# page rather than by lucky text metrics.
WIDE_TAGS = """document.addEventListener('DOMContentLoaded', () => { const style = document.createElement('style');
  style.textContent = '.contractor-tag{font-size:9px!important;letter-spacing:3px!important;padding:2px 4px!important}';
  document.head.append(style); });"""


@pytest.mark.parametrize("width,tags", [(1440, "normal"), (720, "normal"), (1440, "wide"), (720, "wide")])
def test_demo_team_and_meeting_contractors_keep_tags_readable(tmp_path, width, tags):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page(viewport={"width": width, "height": 1100}, reduced_motion="reduce", locale="en-US")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if tags == "wide":
            page.add_init_script(WIDE_TAGS)
        page.goto(hq.url + "/?demo=1")
        playwright.expect(page.locator("#characters .contractor.seated-contractor")).to_have_count(5)
        rows = {row["key"]: row for row in placements(page)}
        assert rows['["home","noah"]']["room"] == "meeting-east" and rows['["home","noah"]']["index"] == "0"
        assert sorted(row["seat"] for row in contractors(page) if row["parent"] == '["home","noah"]') == ["meeting-east.1", "meeting-east.2"]
        assert sorted(row["seat"] for row in contractors(page) if row["parent"] != '["home","noah"]') == [
            "meeting.3", "meeting.4", "meeting.5"]

        def collisions():
            scene = page.evaluate(MEASURE)
            labels = [(row["parent"], label) for row in scene["contractors"] for label in row["labels"]]
            return [(parent, other_parent, round(overlap(label, other) / area(label), 3))
                    for i, (parent, label) in enumerate(labels) for other_parent, other in labels[i + 1:]
                    if overlap(label, other) / area(label) > .05]

        assert collisions() == []
        # Zooming scales the floor but not the tags; they are separated again.
        page.locator("#zoom-in").click()
        page.wait_for_timeout(300)
        assert collisions() == []
        assert not errors
        browser.close()


def test_motion_walks_together_while_reduced_motion_and_replay_place_directly(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, [("alpha", 1)], "working")
        hire(hq, payload, "alpha-0", 2)
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url, motion="no-preference")
        playwright.expect(page.locator("#characters .contractor")).to_have_count(2)
        before = {row["parent"] + str(i): (row["x"], row["y"]) for i, row in enumerate(contractors(page))}
        page.clock.fast_forward(10000)
        member = page.locator('#characters .agent[data-room="meeting"]')
        playwright.expect(member).to_have_count(1)
        playwright.expect(member.locator('[data-pose="walking"]')).to_have_count(1)
        assert not any(row["seated"] for row in contractors(page))
        page.clock.run_for(1000)
        moved = {row["parent"] + str(i): (row["x"], row["y"]) for i, row in enumerate(contractors(page))}
        assert all(moved[name] != before[name] for name in before)
        page.clock.run_for(30000)
        playwright.expect(page.locator("#characters .contractor.seated-contractor")).to_have_count(2)
        playwright.expect(page.locator('#characters .agent[data-room="meeting"].seated')).to_have_count(1)
        # A recorded change while the team works, then the team ends and walks back; replaying that change places the
        # team directly, without walking.
        payload["activities"][0]["state"] = "thinking"
        resend(hq, payload)
        payload["activities"][0]["state"] = "waiting"
        dismiss(payload, "alpha-0")
        resend(hq, payload)
        page.clock.run_for(30000)
        playwright.expect(page.locator('#characters .agent[data-room="studio0"].seated')).to_have_count(1)
        page.get_by_role("button", name="Timeline", exact=True).click()
        playwright.expect(page.locator(".change-event").first).to_be_visible()
        # The older change, while the colleague had its Contractors (the list is newest first).
        page.locator(".change-event").last.click()
        playwright.expect(page.locator("body")).to_have_class(re.compile("replaying"))
        page.get_by_role("button", name="Virtual office", exact=True).click()
        playwright.expect(page.locator("#characters .contractor.seated-contractor")).to_have_count(2)
        assert not page.locator('#characters [data-pose="walking"]').count()
        page.locator(".replay-live").click()
        assert not errors
        browser.close()
        # Reduced motion: the team forms and sits without walking.
        payload["activities"][0]["state"] = "working"
        hire(hq, payload, "alpha-0", 2, start=2)
        resend(hq, payload)
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator("#characters .contractor")).to_have_count(2)
        page.clock.fast_forward(10000)
        playwright.expect(page.locator("#characters .contractor.seated-contractor")).to_have_count(2)
        assert not page.locator('#characters [data-pose="walking"]').count()
        assert not errors
        browser.close()
