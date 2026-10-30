"""Select office cats and colleagues in the real interface."""
from tests.browser.test_seats import open_page
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()


def test_cat_details_and_colleague_selection(tmp_path):
    with HQ(tmp_path / 'hq.sqlite3') as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + '/?demo=1')
        details = page.locator('#employee-detail')
        for name, liked in [('Cheese', 'Cozy spots and naps'), ('Pepper', 'Watching the room and treats')]:
            cat = page.locator('.office-cat[data-cat-name="' + name + '"]')
            cat.click()
            playwright.expect(cat).to_have_attribute('aria-pressed', 'true')
            playwright.expect(details.locator('strong')).to_have_text(name)
            playwright.expect(details).to_contain_text(liked)
        page.locator('#team-list button').first.click()
        playwright.expect(page.locator('.office-cat[aria-pressed="true"]')).to_have_count(0)
        playwright.expect(details.locator('.detail-id')).to_be_visible()
        cat = page.locator('.office-cat[data-cat-name="Cheese"]')
        cat.focus()
        page.keyboard.press('Enter')
        playwright.expect(details.locator('strong')).to_have_text('Cheese')
        assert not errors
        browser.close()
