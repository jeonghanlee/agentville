"""Actual HQ/client/browser integration across weather, seasons, and replay."""

from datetime import UTC, datetime

import pytest

from agentville.hq import weather as module
from agentville.hq.weather import Location, Weather
from tests.browser_support import launch_options, playwright_sync
from tests.lifecycle_support import HQ, activity
from tests.weather_support import MetServer

playwright = playwright_sync()


def open_weather(driver, hq, met, width=1440, motion="reduce"):
    browser = driver.chromium.launch(**launch_options())
    page = browser.new_page(viewport={"width": width, "height": 1100}, reduced_motion=motion, locale="en-US")
    page.clock.install(time=datetime.fromtimestamp(met.now[0], UTC))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(hq.url)
    playwright.expect(page.locator("#weather-report")).to_contain_text("forecast)")
    return browser, page, errors


@pytest.mark.parametrize("symbol,condition", [("clearsky_day", "clear"), ("cloudy", "cloud"),
    ("lightrain_day", "rain"), ("heavysnow", "snow"), ("sleet", "sleet"), ("fog", "fog"),
    ("rainandthunder", "thunder"), ("provider-extension", "unknown")])
@pytest.mark.parametrize("width", [1440, 720])
def test_real_forecast_reaches_window_effects(tmp_path, monkeypatch, symbol, condition, width):
    with MetServer() as met:
        met.symbols(symbol)
        monkeypatch.setattr(module, "PROVIDER_URL", met.url)
        service = Weather({"b1": Location(60, 11)}, str(tmp_path / "weather.sqlite3"), lambda: met.now[0])
        service.refresh()
        with HQ(tmp_path / "hq.sqlite3", weather=service) as hq, playwright.sync_playwright() as driver:
            hq.send()
            browser, page, errors = open_weather(driver, hq, met, width)
            for zoom in (100, 175):
                if zoom == 175:
                    for _ in range(3):
                        page.locator("#zoom-in").click()
                playwright.expect(page.locator("#zoom-reset")).to_have_text(str(zoom) + "%")
                playwright.expect(page.locator("#scene")).to_have_attribute("data-weather", condition)
                assert page.locator('.weather-layer > g').get_attribute("clip-path") == "url(#weather-window-glass)"
                assert page.locator(".weather-layer").evaluate("n=>getComputedStyle(n).pointerEvents") == "none"
            playwright.expect(page.locator("#weather-source")).to_be_visible()
            page.evaluate("""() => {
              window.weatherAnnouncements=0;
              new MutationObserver(records=>weatherAnnouncements+=records.length)
                .observe(document.getElementById('weather-report'),{childList:true,characterData:true,subtree:true});
            }""")
            page.clock.run_for(2100)
            assert page.evaluate("weatherAnnouncements") == 0
            assert page.locator(".weather-layer").evaluate("n=>getComputedStyle(n).pointerEvents") == "none"
            assert page.locator('.weather-layer > g').get_attribute("clip-path") == "url(#weather-window-glass)"
            assert page.locator(".weather-layer clipPath polygon").count() == 8
            if condition in {"rain", "snow", "sleet"}:
                selector = ".weather-snow" if condition == "snow" else ".weather-rain"
                assert page.locator(selector).evaluate("n=>getComputedStyle(n).animationName") == "none"
            page.clock.fast_forward(601000)
            playwright.expect(page.locator("#weather-report")).to_contain_text("out of date")
            playwright.expect(page.locator("#scene")).to_have_attribute("data-weather", "")
            assert not errors
            browser.close()


@pytest.mark.parametrize("width", [1440, 720])
def test_seasons_settings_languages_and_replay(tmp_path, monkeypatch, width):
    with MetServer() as met:
        met.symbols("rain")
        monkeypatch.setattr(module, "PROVIDER_URL", met.url)
        service = Weather({"b1": Location(60, 11), "b2": Location(-33, 18)},
                          str(tmp_path / "weather.sqlite3"), lambda: met.now[0])
        service.refresh()
        hq_clock = [datetime.fromtimestamp(met.now[0], UTC)]
        with HQ(tmp_path / "hq.sqlite3", clock=hq_clock, weather=service) as hq, playwright.sync_playwright() as driver:
            hq.send()
            hq.send(branch="b2")
            hq.advance()
            hq.send("activity", activity("b2", "working"), branch="b2")
            browser, page, errors = open_weather(driver, hq, met, width, "no-preference")
            north = page.locator("#scene").get_attribute("data-season")
            page.locator("#branch-select").select_option("b2")
            opposite = {"spring": "autumn", "summer": "winter", "autumn": "spring", "winter": "summer"}
            playwright.expect(page.locator("#scene")).to_have_attribute("data-season", opposite[north])
            page.locator("#settings-button").click()
            page.locator("#setting-season").select_option("winter")
            playwright.expect(page.locator("#scene")).to_have_attribute("data-season", "winter")
            page.locator("#setting-weather").uncheck()
            playwright.expect(page.locator("#weather-report")).to_have_text("Weather display off")
            page.locator("#setting-weather").focus()
            page.keyboard.press("Space")
            page.locator("#setting-motion").check()
            assert page.locator(".weather-rain").evaluate("n=>getComputedStyle(n).animationName") == "none"
            page.locator("#setting-language").select_option("ko")
            assert "forecast" not in page.locator("#weather-report").inner_text()
            assert page.locator("#setting-season").get_attribute("aria-label") != "Calendar season"
            page.locator("#setting-language").select_option("en")
            page.locator(".dialog-done").click()
            for _ in range(3):
                page.locator("#zoom-in").click()
            assert page.locator("#zoom-reset").inner_text() == "175%"
            page.locator('[data-view="timeline"]').click()
            playwright.expect(page.locator(".change-event").first).to_be_visible()
            page.locator(".change-event").first.click()
            playwright.expect(page.locator("#replay-banner")).to_be_visible()
            playwright.expect(page.locator("#weather-report")).to_have_text("Historical weather unavailable")
            playwright.expect(page.locator("#scene")).to_have_attribute("data-weather", "")
            page.locator(".replay-live").click()
            playwright.expect(page.locator("#weather-report")).to_contain_text("forecast)")
            page.screenshot(path=str(tmp_path / f"weather-replay-{width}.png"), full_page=True)
            page.locator("#settings-button").click()
            page.locator("#setting-weather").uncheck()
            page.reload()
            playwright.expect(page.locator("#setting-season")).to_have_value("winter")
            playwright.expect(page.locator("#setting-weather")).not_to_be_checked()
            playwright.expect(page.locator("#weather-report")).to_have_text("Weather display off")
            playwright.expect(page.locator("#scene")).to_have_attribute("data-season", "winter")
            assert not errors
            browser.close()


def test_demo_and_calendar_boundaries_use_shipped_modules(tmp_path):
    with HQ(tmp_path / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        hq.send()
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page(locale="en-US")
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        page.goto(hq.url)
        playwright.expect(page.locator("#weather-report")).to_have_text("Weather location not configured")
        playwright.expect(page.locator("#scene")).to_have_attribute("data-weather", "")
        requests.clear()
        page.goto(hq.url + "/?demo=1")
        playwright.expect(page.locator("#weather-report")).to_contain_text("Demo forecast")
        observed = page.evaluate("""async () => {
          const {calendarSeason}=await import('/weather.js');
          return [calendarSeason(new Date('2026-03-01T00:30:00Z'),'America/Los_Angeles','north'),
            calendarSeason(new Date('2026-03-01T00:30:00Z'),'Asia/Seoul','north'),
            calendarSeason(new Date('2026-03-01T00:30:00Z'),'Asia/Seoul','south'),
            calendarSeason(new Date('2026-03-01T00:30:00Z'),'UTC','')];
        }""")
        assert observed == ["winter", "spring", "autumn", ""]
        months = page.evaluate("""async () => {
          const {calendarSeason}=await import('/weather.js');
          return ['north','south'].map(hemisphere=>Array.from({length:12},(_,i)=>
            calendarSeason(new Date(Date.UTC(2026,i,15)),'UTC',hemisphere)));
        }""")
        assert months == [
            ["winter", "winter", "spring", "spring", "spring", "summer", "summer", "summer", "autumn", "autumn", "autumn", "winter"],
            ["summer", "summer", "autumn", "autumn", "autumn", "winter", "winter", "winter", "spring", "spring", "spring", "summer"]]
        assert not any("/api/v1/weather" in url or "api.met.no" in url for url in requests)
        browser.close()


def test_previous_branch_response_cannot_repaint_selected_branch(tmp_path, monkeypatch):
    with MetServer() as met:
        monkeypatch.setattr(module, "PROVIDER_URL", met.url)
        service = Weather({"b1": Location(60, 11), "b2": Location(-33, 18)},
                          str(tmp_path / "weather.sqlite3"), lambda: met.now[0])
        service.refresh()
        with HQ(tmp_path / "hq.sqlite3", weather=service) as hq, playwright.sync_playwright() as driver:
            hq.send()
            hq.send(branch="b2")
            browser, page, errors = open_weather(driver, hq, met)
            north = page.locator("#scene").get_attribute("data-season")
            replies = []

            def delay_previous_response(route):
                response = route.fetch()
                replies.append(response.status)
                page.locator("#branch-select").select_option("b2")
                page.evaluate("""() => {
                  window.seasonChanges=[];
                  new MutationObserver(()=>seasonChanges.push(document.getElementById('scene').dataset.season))
                    .observe(document.getElementById('scene'),{attributes:true,attributeFilter:['data-season']});
                }""")
                route.fulfill(response=response)

            page.route("**/api/v1/weather?branch_id=b1", delay_previous_response, times=1)
            page.clock.fast_forward(61000)
            playwright.expect(page.locator("#branch-select")).to_have_value("b2")
            opposite = {"spring": "autumn", "summer": "winter", "autumn": "spring", "winter": "summer"}
            playwright.expect(page.locator("#scene")).to_have_attribute("data-season", opposite[north])
            assert replies == [200]
            assert north not in page.evaluate("seasonChanges")
            assert not errors
            browser.close()
