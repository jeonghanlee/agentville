"""Real weather configuration, transport, persistent cache, and authorized HQ API."""

import json
import threading
import time
from email.utils import formatdate

import pytest
from websockets.sync.client import connect

from agentville.hq import weather as module
from agentville.hq.main import load_weather_config
from agentville.hq.weather import Location, Weather, parse_config
from tests.lifecycle_support import HQ, VIEWER, activity
from tests.weather_support import MetServer


@pytest.fixture
def met(monkeypatch):
    with MetServer() as server:
        monkeypatch.setattr(module, "PROVIDER_URL", server.url)
        yield server


def make_weather(tmp_path, met, locations=None):
    return Weather(locations or {"b1": Location(60, 11)}, str(tmp_path / "weather.sqlite3"), lambda: met.now[0])


@pytest.mark.parametrize("value", [None, [], {}, {"branches": []}, {"branches": {"": {}}},
    {"branches": {"b1": {"latitude": True, "longitude": 0}}},
    {"branches": {"b1": {"latitude": float("nan"), "longitude": 0}}},
    {"branches": {"b1": {"latitude": 91, "longitude": 0}}},
    {"branches": {"b1": {"latitude": 0, "longitude": 181}}},
    {"branches": {"b1": {"latitude": "60", "longitude": 11}}},
    {"branches": {"b1": {"latitude": 60, "longitude": 11, "url": "https://example.invalid"}}}])
def test_invalid_coordinates_fail_clearly(value):
    with pytest.raises(ValueError):
        parse_config(value)


def test_private_loader_and_coordinates(tmp_path):
    config = tmp_path / "weather.yaml"
    config.write_text("branches:\n  b1: {latitude: 60.123456, longitude: 11.123456}\n")
    config.chmod(0o600)
    assert load_weather_config(str(config)) == {"b1": Location(60.1235, 11.1235)}
    config.chmod(0o644)
    with pytest.raises(SystemExit, match="must not be accessible"):
        load_weather_config(str(config))
    config.chmod(0o600)
    config.write_text("branches: {b1: {latitude: .inf, longitude: 11}}")
    with pytest.raises(SystemExit, match="finite"):
        load_weather_config(str(config))


def test_cache_expiry_conditional_refresh_and_restart(tmp_path, met):
    service = make_weather(tmp_path, met, {"b1": Location(60, 11), "b2": Location(60, 11)})
    assert service.display("b1")["status"] == "loading"
    assert service.display("missing")["status"] == "unconfigured"
    service.refresh()
    assert len(met.calls) == 1
    result = service.display("b1")
    assert result["status"] == "available"
    sample = met.document["properties"]["timeseries"][0]
    assert result["temperature"] == sample["data"]["instant"]["details"]["air_temperature"]
    assert result["source"] == "MET Norway" and result["hemisphere"] == "north"
    assert "latitude" not in result and "longitude" not in result
    assert "AgentVille/" in met.calls[0]["headers"]["User-Agent"]
    assert "lat=60.0000&lon=11.0000" in met.calls[0]["path"]
    service.refresh()
    assert len(met.calls) == 1
    service.close()
    service = make_weather(tmp_path, met)
    service.refresh()
    assert len(met.calls) == 1
    met.now[0] += 601
    assert service.display("b1")["status"] == "stale"
    met.code = 304
    service.refresh()
    assert len(met.calls) == 2
    assert met.calls[-1]["headers"]["If-Modified-Since"]
    assert service.display("b1")["status"] == "available"
    service.close()


@pytest.mark.parametrize("code,body", [(429, None), (503, None), (200, b"broken"),
    (200, b"{}"), (200, b"x" * (module.MAX_BODY + 1)), (302, None)],
    ids=["rate-limit", "unavailable", "invalid-json", "invalid-schema", "oversized", "redirect"])
def test_failures_and_backoff_preserve_stale_data(tmp_path, met, code, body):
    service = make_weather(tmp_path, met)
    service.refresh()
    met.now[0] += 601
    met.code, met.body = code, body
    met.headers = {"Retry-After": "300", "Location": "http://example.invalid/"}
    service.refresh()
    assert service.display("b1")["status"] == "stale"
    calls = len(met.calls)
    met.now[0] += 299
    service.refresh()
    assert len(met.calls) == calls
    service.close()


def test_timeout_and_empty_cache_failure(tmp_path, met, monkeypatch):
    monkeypatch.setattr(module, "TIMEOUT", .15)
    met.release.clear()
    service = make_weather(tmp_path, met)
    service.refresh()
    assert met.received.is_set()
    assert service.display("b1")["status"] == "unavailable"
    service.close()


def test_future_and_unknown_forecasts_are_not_clear_weather(tmp_path, met):
    met.symbols("new-provider-condition_day")
    service = make_weather(tmp_path, met)
    service.refresh()
    assert service.display("b1")["condition"] == "unknown"
    met.now[0] -= 301
    assert service.display("b1")["status"] == "unavailable"
    service.close()


def test_authentication_and_slow_provider_do_not_block_hq(tmp_path, met):
    met.release.clear()
    service = make_weather(tmp_path, met)
    with HQ(tmp_path / "hq.sqlite3", weather=service, viewer_token=VIEWER) as hq:
        assert met.received.wait(3)
        hq.send()
        with connect(hq.url.replace("http://", "ws://") + "/ws/v1/live", open_timeout=2) as socket:
            socket.send(json.dumps({"type": "auth", "token": VIEWER}))
            assert json.loads(socket.recv(timeout=2))["type"] == "state"
            hq.advance()
            hq.send("activity", activity("b1", "working"))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                frame = json.loads(socket.recv(timeout=2))
                if frame["state"]["activities"][0]["state"] == "working":
                    break
            else:
                pytest.fail("live activity did not arrive while weather transport was blocked")
        assert hq.request("/api/v1/weather", params={"branch_id": "b1"})[0] == 401
        assert hq.get("/api/v1/weather", branch_id="b1")["status"] == "loading"
        assert hq.get()["agents"]
        assert hq.request("/api/v1/weather", token=VIEWER, params={"branch_id": "missing"})[0] == 404
        met.release.set()
        deadline = time.monotonic() + 3
        while hq.get("/api/v1/weather", branch_id="b1")["status"] != "available" and time.monotonic() < deadline:
            time.sleep(.02)
        assert hq.get("/api/v1/weather", branch_id="b1")["status"] == "available"


def test_unconfigured_hq_does_not_contact_provider(tmp_path, met):
    with HQ(tmp_path / "hq.sqlite3") as hq:
        hq.send()
        assert hq.get("/api/v1/weather", branch_id="b1")["status"] == "unconfigured"
    assert not met.calls


def test_concurrent_refresh_does_not_duplicate_requests(tmp_path, met):
    service = make_weather(tmp_path, met)
    met.release.clear()
    worker = threading.Thread(target=service.refresh)
    worker.start()
    assert met.received.wait(3)
    service.refresh()
    assert len(met.calls) == 1
    met.release.set()
    worker.join(5)
    assert not worker.is_alive()
    assert service.display("b1")["status"] == "available"
    service.close()


def test_rate_limit_http_date_and_missing_location(tmp_path, met):
    service = make_weather(tmp_path, met)
    met.code = 429
    met.headers = {"Retry-After": formatdate(met.now[0] + 300, usegmt=True)}
    service.refresh()
    assert service.display("b1")["status"] == "unavailable"
    met.now[0] += 299
    service.refresh()
    assert len(met.calls) == 1
    assert service.display("b2")["status"] == "unconfigured"
    met.now[0] += 2
    met.code = 200
    service.refresh()
    assert len(met.calls) == 2
    assert service.display("b1")["status"] == "available"
    service.close()


def test_equatorial_forecast_does_not_invent_a_hemisphere(tmp_path, met):
    service = make_weather(tmp_path, met, {"b1": Location(0, 11)})
    service.refresh()
    assert service.display("b1")["status"] == "available"
    assert service.display("b1")["hemisphere"] == ""
    service.close()
