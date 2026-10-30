"""Verify the office and its foreground furniture use the same source image."""
from tests.browser.test_seats import open_page
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ
from pathlib import Path

playwright = playwright_sync()


def test_office_and_furniture_share_one_image(tmp_path):
    with HQ(tmp_path / 'hq.sqlite3') as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + '/?demo=seats')
        playwright.expect(page.locator('#characters .agent.seated')).to_have_count(60)
        assert page.locator('.office-art').get_attribute('src') == 'office-modern.png'
        sources = page.locator('.furniture-front image').evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('href'))")
        assert sources and set(sources) == {'office-modern.png'}
        assert page.locator('[data-artwork-edit]').count() == 0
        assets = Path(__file__).parents[2] / 'packages/agentville/hq/web'
        assert sorted(path.name for path in assets.glob('office*.png')) == ['office-modern.png']
        assert page.request.get(hq.url + '/office-modern.png').ok
        assert page.request.get(hq.url + '/office-lounge-books.png').status == 404
        assert not errors
        browser.close()
