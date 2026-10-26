"""Seated poses and Contractor placement in the modern office, measured in the rendered page."""

import pytest

from agentville.common.protocol import iso
from tests.browser.test_seats import open_page, roster
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()
# Rendered boxes in artwork source pixels, with each seated colleague's seat-table entry.
MEASURE = """async () => {
  const {SEATS}=await import('/seats.js');
  const world=document.getElementById('world').getBoundingClientRect(), sx=world.width/1536, sy=world.height/1024;
  const box=node=>{const r=node.getBoundingClientRect();
    return [(r.left-world.left)/sx,(r.top-world.top)/sy,(r.right-world.left)/sx,(r.bottom-world.top)/sy];};
  const agents=[...document.querySelectorAll('#characters .agent')].map(node=>{
    const seat=SEATS.find(item=>item.id===node.dataset.room+'.'+node.dataset.seatIndex);
    return {key:node.dataset.employeeKey,room:node.dataset.room,index:node.dataset.seatIndex,facing:node.dataset.seatFacing,
      seated:node.classList.contains('seated'),queue:node.dataset.queuePosition,body:box(node.querySelector(':scope > svg')),
      seat:seat&&{id:seat.sourceId,kind:seat.kind,hip:seat.hip,support:seat.supportY}};
  });
  const contractors=[...document.querySelectorAll('#characters .contractor')].map(node=>({parent:node.dataset.parentKey,
    z:Number(node.style.zIndex),body:box(node.querySelector(':scope > svg')),
    labels:[...node.querySelectorAll('.contractor-tag, small')].map(box)}));
  return {agents,contractors};
}"""
REAR = {"back", "back-left"}


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def overlap(a, b):
    return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def rear_leg_shares(scene):
    """Drawn depth below the hip of each rear-facing chair sitter, as a share of the measured seat height."""
    return {row["seat"]["id"]: (row["body"][3] - row["seat"]["hip"][1]) / (row["seat"]["support"] - row["seat"]["hip"][1])
            for row in scene["agents"] if row["seat"] and row["facing"] in REAR and row["seat"]["kind"] != "high"}


def contractor_conflicts(scene, parents=None):
    """Contractor figures over other colleagues, and provider tags or "+N" counts hidden by another figure or label."""
    found = []
    contractors = [row for row in scene["contractors"] if parents is None or row["parent"] in parents]
    for item in contractors:
        for colleague in scene["agents"]:
            if colleague["key"] == item["parent"]:
                continue
            share = overlap(item["body"], colleague["body"]) / area(item["body"])
            if share > .05:
                found.append(("figure", item["parent"], colleague["key"], round(share, 2)))
            for label in item["labels"]:
                if overlap(label, colleague["body"]) / area(label) > .05:
                    found.append(("label on colleague", item["parent"], colleague["key"]))
        for other in scene["contractors"]:
            if other is item:
                continue
            # At the narrow layout a label is wider than one Contractor step, so the labels of one parent's
            # Contractors may touch; they stay mostly readable.
            limit = .35 if other["parent"] == item["parent"] else 0
            for label in item["labels"]:
                if any(overlap(label, theirs) / area(label) > limit for theirs in other["labels"]):
                    found.append(("labels", item["parent"], other["parent"]))
                if other["z"] >= item["z"] and overlap(label, other["body"]) / area(label) > .25:
                    found.append(("label hidden", item["parent"], other["parent"]))
    return found


@pytest.mark.parametrize("width", [1440, 720])
def test_rear_facing_chair_sitters_rest_their_feet_under_the_table(tmp_path, width):
    # Seen from behind, a sitter's feet rest forward under the table, above the floor point beneath the hip.
    # Calves stretched to that point draw a standing figure behind its chair.
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + "/?demo=seats", width)
        playwright.expect(page.locator("#characters .agent.seated")).to_have_count(60)
        shares = rear_leg_shares(page.evaluate(MEASURE))
        assert len(shares) == 27
        assert max(shares.values()) <= .7, sorted(shares.items(), key=lambda item: -item[1])[:5]
        assert not errors
        browser.close()


@pytest.mark.parametrize("width", [1440, 720])
def test_demo_fika_and_meeting_colleagues_sit_on_free_seats(tmp_path, width):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + "/?demo=1", width)
        playwright.expect(page.locator('#characters .agent[data-room="fika"]')).to_have_count(3)
        scene = page.evaluate(MEASURE)
        fika = [row for row in scene["agents"] if row["room"] == "fika"]
        meeting = [row for row in scene["agents"] if row["room"] == "meeting"]
        assert len(meeting) == 3
        # Twenty-eight Fika places remain far from exhausted, so nobody queues or stands.
        assert all(row["seated"] and not row["queue"] and row["seat"] for row in fika + meeting)
        assert len({row["index"] for row in fika}) == 3
        shares = rear_leg_shares(scene)
        assert {row["seat"]["id"] for row in fika + meeting} <= set(shares)
        assert max(shares[row["seat"]["id"]] for row in fika + meeting) <= .7
        assert not errors
        browser.close()


def test_rear_facing_desk_contractors_stand_on_the_free_side(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        payload = roster(hq, state="working")
        payload["contractors"] = [{"contractor_id": "helper-" + row["agent_id"], "parent_instance_id": row["instance"]["instance_id"],
                                   "provider": "claude", "origin": "in_process", "status": "hired", "state": "working",
                                   "state_since": iso(hq.clock[0]), "tool": "Read"} for row in payload["agents"]]
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url)
        playwright.expect(page.locator("#characters .contractor")).to_have_count(20)
        scene = page.evaluate(MEASURE)
        rear = {row["key"] for row in scene["agents"] if row["facing"] in REAR}
        assert len(rear) == 10
        assert contractor_conflicts(scene, rear) == []
        assert not errors
        browser.close()
