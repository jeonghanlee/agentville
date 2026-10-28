"""Distance-driven footsteps through the shipped sprites and live office."""

import copy
import math

from tests.browser_support import launch_options, playwright_sync
from tests.lifecycle_support import HQ, snapshot

playwright = playwright_sync()


def test_painted_legs_alternate_without_changing_scale(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page()
        page.goto(hq.url + "/?demo=1")
        rows = page.evaluate("""async () => {
          const {character,prepareAppearances}=await import('/art.js');
          const world=document.getElementById('world');
          const seeds=Array.from({length:12},(_,i)=>'gait-'+i);prepareAppearances(seeds);
          const rows=[];
          for(const seed of seeds)for(const view of ['front','back']) {
            const node=document.createElement('div');node.className='agent coffee-standing walking';
            node.dataset.walkView=view;node.dataset.coffeeFacing='right';
            const sprite=character(seed,'idle','coffee-walk','normal',false,'walking');
            node.append(sprite);world.append(node);
            const legs=[...sprite.querySelectorAll('.walk-'+view+' .walk-leg')];
            const phases=[];
            for(let phase=0;phase<8;phase++) {
              node.style.setProperty('--walk-phase',String(phase/8));
              await new Promise(requestAnimationFrame);
              phases.push(legs.map(leg=>{
                const matrix=new DOMMatrix(getComputedStyle(leg).transform);
                return [matrix.a,matrix.b,matrix.c,matrix.d,matrix.e,matrix.f];
              }));
            }
            rows.push({look:Number(sprite.dataset.look),view,phases});node.remove();
          }
          return rows;
        }""")
        browser.close()
    assert len(rows) == 24 and len({row["look"] for row in rows}) == 12
    for row in rows:
        for leg in range(2):
            positions = [phase[leg][4] for phase in row["phases"]]
            assert max(positions) - min(positions) > 1, row
        for phase in row["phases"]:
            assert abs(phase[0][4] - phase[1][4]) > .2 or abs(phase[0][5] - phase[1][5]) > .2, row
            for a, b, c, d, _, _ in phase:
                assert abs(a * a + b * b - 1) < .0001, row
                assert abs(c * c + d * d - 1) < .0001, row
                assert abs(a * d - b * c - 1) < .0001, row


def test_live_arrival_steps_follow_motion_and_pause_with_hidden_office(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        hq.send()
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page()
        page.clock.install()
        page.goto(hq.url)
        playwright.expect(page.locator(".agent[data-employee-key]")).to_have_count(1)
        payload = snapshot()
        newcomer = copy.deepcopy(payload["agents"][0])
        newcomer["agent_id"] = "new-arrival"
        payload["agents"].append(newcomer)
        activity = copy.deepcopy(payload["activities"][0])
        activity["agent_id"] = newcomer["agent_id"]
        payload["activities"].append(activity)
        hq.advance()
        hq.send(payload=payload)
        walker = page.locator(".agent.walking[data-employee-key]")
        playwright.expect(walker).to_have_count(1)
        key = walker.get_attribute("data-walk-key")

        def measure():
            return page.evaluate("""key => {
              const node=[...document.querySelectorAll('[data-walk-key]')].find(node=>node.dataset.walkKey===key);
              return {x:parseFloat(node.style.left),y:parseFloat(node.style.top),
                phase:parseFloat(node.style.getPropertyValue('--walk-phase'))};
            }""", key)

        page.clock.run_for(160)
        before = measure()
        page.clock.run_for(160)
        after = measure()
        assert all(math.isfinite(sample["phase"]) for sample in (before, after))
        assert (after["x"], after["y"]) != (before["x"], before["y"])
        assert after["phase"] != before["phase"]
        page.get_by_role("button", name="Branches", exact=True).click()
        paused = measure()
        page.clock.run_for(800)
        assert measure() == paused
        page.get_by_role("button", name="Virtual office", exact=True).click()
        page.clock.run_for(160)
        assert measure() != paused
        page.emulate_media(reduced_motion="reduce")
        page.clock.run_for(160)
        playwright.expect(page.locator(".agent.walking[data-employee-key]")).to_have_count(0)
        browser.close()
