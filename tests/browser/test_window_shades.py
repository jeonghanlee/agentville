"""Window tint follows real forecast and daylight selections."""
import pytest

from agentville.hq import weather as module
from agentville.hq.weather import Location, Weather
from tests.browser.test_weather import open_weather
from tests.browser_support import playwright_sync
from tests.lifecycle_support import HQ
from tests.weather_support import MetServer

playwright = playwright_sync()


@pytest.mark.parametrize("width", [1440, 720])
@pytest.mark.parametrize("symbol,condition", [("clearsky_day", "clear"), ("lightrain_day", "rain")])
def test_window_tint_follows_forecast_and_daylight(tmp_path, monkeypatch, width, symbol, condition):
    with MetServer() as met:
        met.symbols(symbol)
        monkeypatch.setattr(module, "PROVIDER_URL", met.url)
        service = Weather({"b1": Location(60, 11)}, str(tmp_path / "weather.sqlite3"), lambda: met.now[0])
        service.refresh()
        with HQ(tmp_path / "hq.sqlite3", weather=service) as hq, playwright.sync_playwright() as driver:
            hq.send()
            browser, page, errors = open_weather(driver, hq, met, width)
            playwright.expect(page.locator("#scene")).to_have_attribute("data-weather", condition)
            page.locator("#setting-daylight").select_option("day", force=True)
            nature = page.locator(".window-nature")
            assert nature.count() == 6
            assert page.locator(".window-blind").count() == 0
            assert page.locator(".window-tint").count() == 0
            assert nature.evaluate_all("nodes=>nodes.every(n=>getComputedStyle(n).display==='block')") == (condition == "clear")
            page.locator("#world").screenshot(path=str(tmp_path / "day.png"), animations="disabled")
            page.locator("#setting-daylight").select_option("night", force=True)
            assert page.locator(".window-blind").count() == 0
            assert page.locator(".window-tint").count() == 0
            assert nature.evaluate_all("nodes=>nodes.every(n=>getComputedStyle(n).display==='none')")
            assert page.locator('.daylight-layer > g[clip-path="url(#office-window-glass)"]').count() == 1
            page.locator("#world").screenshot(path=str(tmp_path / "night.png"), animations="disabled")
            assert not errors
            browser.close()
