"""Exercise kitchen routes, meal-time selection and artwork in the real browser."""
import json
from tests.browser.test_seats import open_page
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ

playwright = playwright_sync()


def test_kitchen_routes_and_meal_artwork(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + "/?demo=1", motion="no-preference")
        result = page.evaluate("""async () => {
          const {STOPS, FOODS} = await import('/coffee.js');
          const {clear, route} = await import('/floor.js');
          const {drinkArtwork} = await import('/mugs.js');
          return {routes: Object.fromEntries(Object.entries(STOPS).map(([name, point]) => {
            const path = route(STOPS.coffee, point);
            return [name, clear(point, point) && path.every((p, i) => !i || clear(path[i-1], p))];
          })), foods: FOODS.map(food => {
            const element = document.createElement('div');
            element.innerHTML = drinkArtwork({kind:'food', food}, 0, 0);
            return {food, present: element.querySelector('[data-food="' + food + '"]') !== null};
          })};
        }""")
        assert set(result["routes"]) == {"coffee", "water", "sink", "microwave", "fridge"}
        assert all(result["routes"].values())
        assert len(result["foods"]) == 8 and all(item["present"] for item in result["foods"])
        assert not errors
        browser.close()


def test_meal_time_uses_branch_timezone(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url)
        for hour, expected in [(6, False), (8, True), (12, True), (15, False), (18, True), (22, False)]:
            page.clock.set_fixed_time(f"2026-01-01T{hour:02d}:00:00Z")
            assert page.evaluate("async () => (await import('/coffee.js')).isMealTime('UTC')") is expected
        assert not errors
        browser.close()


def test_drink_after_food_uses_a_valid_mug(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + "/?demo=1")
        result = page.evaluate("""async () => {
          const {createLounge} = await import('/lounge.js');
          const {character, prepareAppearances} = await import('/art.js');
          const lounge = createLounge(document.createElement('div'), {motionAllowed: () => false});
          lounge.set('test', {kind: 'food', food: 'pizza'});
          prepareAppearances(['test']);
          return Array.from({length: 20}, () => {
            const cup = lounge.refill('test');
            const sprite = character('test', 'idle', 'fika', 'normal', false, 'front', null, cup);
            return Number.isInteger(cup.mug) && Boolean(sprite);
          });
        }""")
        assert all(result)
        assert not errors
        browser.close()


def test_kitchen_visits_run_in_live_demo(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser, page, errors = open_page(driver, hq.url + "/?demo=1", motion="no-preference")
        playwright.expect(page.locator('#characters .agent[data-room="fika"]')).not_to_have_count(0)
        observed = set()
        for _ in range(200):
            page.clock.run_for(1000)
            waiting = page.locator('.agent[data-coffee-phase="waiting"]')
            if waiting.count():
                action = waiting.first.get_attribute("data-kitchen-action")
                observed.add(action)
                assert action in {"coffee", "water", "sink", "fridge", "microwave"}
                if action == "fridge":
                    assert page.locator('.kitchen-fridge-door').is_visible()
            if len(observed) >= 2:
                break
        assert observed
        (tmp_path / "observed-actions.json").write_text(json.dumps(sorted(observed)) + "\n")
        page.screenshot(path=str(tmp_path / "kitchen-demo.png"), full_page=True)
        assert not errors
        browser.close()
