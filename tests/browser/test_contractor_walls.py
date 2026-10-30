"""Track real Contractor movements into meeting rooms against wall contacts."""
import json
import pytest
from tests.browser.test_contractor_teams import hire
from tests.browser.test_seats import open_page, roster
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()


@pytest.mark.parametrize('projects', [1, 2])
def test_contractors_walk_without_crossing_meeting_walls(tmp_path, projects):
    with HQ(tmp_path / 'hq.sqlite3') as hq, playwright.sync_playwright() as driver:
        names = ['alpha', 'bravo'][:projects]
        payload = roster(hq, [(name, 1) for name in names], 'working')
        for name in names:
            hire(hq, payload, name + '-0', 2)
        hq.send(payload=payload)
        browser, page, errors = open_page(driver, hq.url, motion='no-preference')
        playwright.expect(page.locator('#characters .contractor')).to_have_count(2 * projects)
        page.evaluate('''async () => {
          const {touched} = await import('/floor.js');
          const walls = new Set(['north-meeting-west', 'meeting-separator']);
          const last = new Map(); window.contractorTrace = {moving: 0, missingClass: 0, crossings: []};
          const tick = () => {
            for (const node of document.querySelectorAll('#characters .contractor')) {
              const p = [parseFloat(node.style.left), parseFloat(node.style.top)];
              if (!p.every(Number.isFinite)) continue;
              const before = last.get(node.dataset.walkKey);
              if (before && Math.hypot(p[0]-before[0], p[1]-before[1]) > .002) {
                contractorTrace.moving++;
                if (!node.classList.contains('walking') && !node.classList.contains('seated-contractor')) contractorTrace.missingClass++;
                for (const name of touched(before, p)) if (walls.has(name)) contractorTrace.crossings.push({name, before, p});
              }
              last.set(node.dataset.walkKey, p);
            }
            requestAnimationFrame(tick);
          }; requestAnimationFrame(tick);
        }''')
        page.clock.run_for(55000)
        trace = page.evaluate('contractorTrace')
        (tmp_path / 'contractor-trace.json').write_text(json.dumps(trace, indent=2) + '\n')
        assert trace['moving'] > 0, trace
        assert trace['missingClass'] == 0, trace
        assert not trace['crossings'], trace
        assert not errors
        browser.close()
