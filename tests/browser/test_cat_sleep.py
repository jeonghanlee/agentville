"""Verify both cats' real timed rest cycles in the office."""
import json
from pathlib import Path
from tests.browser.test_seats import open_page
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()


def test_cat_beds_are_inside_the_floor_and_have_separate_routes(tmp_path):
    source = Path(__file__).parent / 'fixtures' / 'modern-image-annotations.json'
    annotations = json.loads(source.read_text())
    with HQ(tmp_path / 'hq.sqlite3') as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + '/?demo=1')
        result = page.evaluate('''async data => {
          const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
          document.body.append(svg);
          const shape = points => {
            const node = document.createElementNS(svg.namespaceURI, 'polygon');
            node.setAttribute('points', points.map(p => p.join(',')).join(' ')); svg.append(node); return node;
          };
          const floor = shape(data.floor), names = ['cat-bed-cheese', 'cat-bed-pepper', 'cat-bowls'];
          const inside = names.every(name => data.contacts[name].every(([x,y]) => floor.isPointInFill(new DOMPoint(x,y))));
          const a = shape(data.contacts[names[0]]), b = shape(data.contacts[names[1]]);
          const separate = !data.contacts[names[0]].some(([x,y]) => b.isPointInFill(new DOMPoint(x,y)))
            && !data.contacts[names[1]].some(([x,y]) => a.isPointInFill(new DOMPoint(x,y)));
          const {touched,NODES} = await import('/floor.js');
          const {pointPercent} = await import('/layout.js');
          const q = pointPercent;
          const approach = touched(NODES.entrance, q([530,690]));
          const cheese = touched(q([530,690]), q([470,730]));
          const pepper = touched(NODES.entrance, q([510,760]));
          svg.remove(); return {inside,separate,approach,cheese,pepper};
        }''', annotations)
        assert result == {'inside': True, 'separate': True, 'approach': [],
                          'cheese': ['cat-bed-cheese'], 'pepper': ['cat-bed-pepper']}
        assert not errors
        browser.close()


def test_cats_return_to_their_beds_and_sleep_for_ten_minutes(tmp_path):
    with HQ(tmp_path / 'hq.sqlite3') as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + '/?demo=1', motion='no-preference')
        cats = page.locator('.office-cat')
        playwright.expect(cats).to_have_count(2)
        page.evaluate('''() => {
          window.catSleepEvents = [];
          new MutationObserver(records => {
            for (const record of records) {
              const node = record.target;
              if (record.attributeName === 'data-state' && node.dataset.state === 'nap')
                catSleepEvents.push({name: node.dataset.catName, bed: node.dataset.location, start: performance.now()});
            }
          }).observe(document.querySelector('#characters'), {subtree: true, attributes: true, attributeFilter: ['data-state']});
        }''')
        page.clock.run_for(1000)
        page.clock.fast_forward(29 * 60 * 1000)
        page.clock.run_for(1000)
        assert cats.evaluate_all("nodes => nodes.every(n => n.dataset.restCycle === 'roaming')")
        page.clock.fast_forward(60 * 1000)
        for _ in range(240):
            page.clock.run_for(1000)
            if page.locator('.office-cat[data-state="nap"]').count() == 2:
                break
        playwright.expect(page.locator('.office-cat[data-state="nap"]')).to_have_count(2)
        events = page.evaluate('catSleepEvents')
        assert {event['name'] for event in events} == {'Cheese', 'Pepper'}
        assert all(event['bed'] == 'cat:bed:' + event['name'] for event in events)
        page.locator('#world').screenshot(path=str(tmp_path / 'both-cats-asleep.png'))
        first = min(event['start'] for event in events)
        now = page.evaluate('performance.now()')
        page.clock.fast_forward(max(0, int(first + 598000 - now)))
        page.clock.run_for(500)
        playwright.expect(page.locator('.office-cat[data-state="nap"]')).to_have_count(2)
        page.clock.fast_forward(5000)
        page.clock.run_for(1000)
        assert page.locator('.office-cat[data-rest-cycle="roaming"]').count() >= 1
        page.clock.fast_forward(240000)
        page.clock.run_for(1000)
        playwright.expect(page.locator('.office-cat[data-rest-cycle="roaming"]')).to_have_count(2)
        assert not errors
        browser.close()
