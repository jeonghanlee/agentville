import base64
import http.server
import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from agentville.common.protocol import Envelope
from agentville.hq.app import create_app
from agentville.hq.main import load_notify_config
from agentville.hq.notify import KEYS, Message, Notifier, NotifyConfig, Outbox, http_post, load_strings, parse_config
from agentville.hq.store import Store

T0 = datetime(2026, 1, 1, tzinfo=UTC)
BRANCH = {"alias": "Home", "country": "", "time": "UTC", "location": "", "thresholds": {"phone": 300, "doze": 1800, "lounge": 3600, "leave": 604800}}
URL = "https://ntfy.example.org/agentville-test"


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def colleague(agent_id, state, since=0, alias=None, branch_id="b1", provider="claude", seat=1):
    return ({"branch_id": branch_id, "agent_id": agent_id, "project_alias": "alpha", "provider": provider, "seat": seat,
             "alias": alias, "presence": "on_duty"},
            {"branch_id": branch_id, "agent_id": agent_id, "state": state, "state_since": at(since).isoformat()})


def state(*people, branches=(("b1", True),)):
    return {"branches": [{"branch_id": b, "branch": BRANCH, "reachable": r} for b, r in branches],
            "agents": [p[0] for p in people], "activities": [p[1] for p in people], "contractors": []}


class Sent(list):
    def titles(self):
        return [m.title for m in self]


def notifier(**config):
    sent = Sent()
    return Notifier(NotifyConfig(URL, **config), sent.append), sent


HEARD = frozenset({"b1", "b2"})


def test_first_evaluation_and_new_subjects_are_not_announced():
    n, sent = notifier()
    n.observe(state(colleague("a", "waiting")), HEARD, at(0))
    n.observe(state(colleague("a", "waiting"), colleague("b", "error", seat=2)), HEARD, at(1))
    assert sent == []


def test_entries_into_waiting_and_error_are_announced_with_browser_texts():
    n, sent = notifier()
    n.observe(state(colleague("a", "working"), colleague("b", "working", alias="Reviewer", seat=2)), HEARD, at(0))
    n.observe(state(colleague("a", "waiting", 1), colleague("b", "error", 1, alias="Reviewer", seat=2)), HEARD, at(1))
    assert sent == [Message("Claude 1 is waiting", "CL · alpha · Home", "agentville,waiting", "default"),
                    Message("Reviewer has an error", "CL · alpha · Home", "agentville,error", "high")]
    # Limited, completed, and idle are never announced.
    n.observe(state(colleague("a", "limited", 2), colleague("b", "idle", 2, alias="Reviewer", seat=2)), HEARD, at(2))
    assert len(sent) == 2


def test_snapshot_resync_is_not_announced():
    n, sent = notifier()
    n.observe(state(colleague("a", "working")), HEARD, at(0))
    n.observe(state(colleague("a", "waiting", 1)), HEARD, at(1), resynced=frozenset({"b1"}))
    assert sent == []


def test_branch_reachability_is_announced_once_heard_since_start():
    n, sent = notifier(language="ko")
    n.observe(state(branches=(("b1", False),)), frozenset(), at(0))
    # Reporting again after an HQ restart is the Branch's first state since start.
    n.observe(state(branches=(("b1", True),)), HEARD, at(1))
    n.observe(state(branches=(("b1", False),)), HEARD, at(100))
    n.observe(state(branches=(("b1", True),)), HEARD, at(200))
    assert [(m.title, m.priority, m.tags) for m in sent] == [
        ("Home 연락 끊김", "high", "agentville,unreachable"),
        ("Home 응답 재개", "default", "agentville,reachable")]


def test_a_subject_is_held_for_thirty_seconds_and_sent_only_if_still_true():
    n, sent = notifier()
    n.observe(state(colleague("a", "working")), HEARD, at(0))
    n.observe(state(colleague("a", "waiting", 1)), HEARD, at(1))
    n.observe(state(colleague("a", "working", 2)), HEARD, at(2))
    n.observe(state(colleague("a", "waiting", 3)), HEARD, at(3))
    assert len(sent) == 1
    n.observe(state(colleague("a", "waiting", 3)), HEARD, at(31))
    assert sent.titles() == ["Claude 1 is waiting"] * 2
    # A held change that no longer holds is dropped.
    n.observe(state(colleague("a", "working", 40)), HEARD, at(40))
    n.observe(state(colleague("a", "error", 41)), HEARD, at(41))
    n.observe(state(colleague("a", "working", 42)), HEARD, at(42))
    n.observe(state(colleague("a", "working", 42)), HEARD, at(80))
    assert len(sent) == 2


def test_more_than_three_subjects_are_summarized():
    n, sent = notifier()
    people = [colleague(str(i), "working", seat=i) for i in range(1, 5)]
    n.observe(state(*people, branches=(("b1", True), ("b2", True))), HEARD, at(0))
    waiting = [colleague(str(i), "waiting", 1, seat=i) for i in range(1, 5)]
    n.observe(state(*waiting, branches=(("b1", True), ("b2", True))), HEARD, at(1))
    assert sent == [Message("4 colleagues need attention", "Claude 1, Claude 2, Claude 3 +1", "agentville,summary", "default")]
    n.observe(state(*[colleague(str(i), "error", 40, seat=i) for i in range(1, 4)], branches=(("b1", True), ("b2", False))),
              HEARD, at(40))
    assert sent[-1] == Message("4 colleagues and branches need attention", "Claude 1, Claude 2, Claude 3 +1",
                               "agentville,summary", "high")


def test_events_select_what_is_sent():
    n, sent = notifier(events=frozenset({"error"}))
    n.observe(state(colleague("a", "working"), branches=(("b1", True),)), HEARD, at(0))
    n.observe(state(colleague("a", "waiting", 1), branches=(("b1", False),)), HEARD, at(1))
    n.observe(state(colleague("a", "error", 2), branches=(("b1", False),)), HEARD, at(2))
    assert sent.titles() == ["Claude 1 has an error"]


def test_strings_come_from_the_web_dictionary_in_both_languages():
    english, korean = load_strings("en"), load_strings("ko")
    assert set(english) == set(KEYS) and set(korean) == set(KEYS)
    assert english["notify.waiting"] == "{name} is waiting" and korean["notify.waiting"] != english["notify.waiting"]


@pytest.mark.parametrize("document, text", [
    ("not a mapping", "must be a mapping"),
    ({}, "url must be the URL of an ntfy topic"),
    ({"url": "ftp://ntfy.example.org/t"}, "url must be the URL"),
    ({"url": "http://ntfy.example.org/t"}, "url must use https unless its host is loopback"),
    ({"url": "https://ntfy.example.org/"}, "url must name a topic"),
    ({"url": URL, "events": ["waiting", "limited"]}, "events must be a list of waiting, error, branch"),
    ({"url": URL, "events": []}, "events must be a list"),
    ({"url": URL, "language": "fr"}, "language must be en or ko"),
    ({"url": URL, "token_file": 5}, "token_file must be a path"),
    ({"url": URL, "topic": "x"}, "unknown key topic"),
])
def test_invalid_configuration_is_rejected(document, text):
    with pytest.raises(ValueError, match=text):
        parse_config(document)


def test_configuration_defaults_and_loopback_http():
    config = parse_config({"url": "http://127.0.0.1:8080/alerts"})
    assert (config.events, config.language, config.token_file) == (frozenset({"waiting", "error", "branch"}), "en", None)


def test_configuration_files_must_be_private_and_valid(tmp_path):
    path, token = tmp_path / "notify.yaml", tmp_path / "ntfy.token"
    path.write_text(f"url: {URL}\ntoken_file: {token}\nlanguage: ko\n")
    path.chmod(0o644)
    with pytest.raises(SystemExit, match="chmod 600"):
        load_notify_config(str(path))
    path.chmod(0o600)
    with pytest.raises(SystemExit, match="cannot read"):
        load_notify_config(str(path))
    token.write_text("tk_secret\n")
    token.chmod(0o600)
    config = load_notify_config(str(path))
    assert (config.token, config.language) == ("tk_secret", "ko")
    path.write_text("url: [\n")
    with pytest.raises(SystemExit) as error:
        load_notify_config(str(path))
    assert str(error.value).startswith(f"agentville-hq: {path}: YAML syntax error")
    path.write_text("url: http://ntfy.example.org/t\n")
    with pytest.raises(SystemExit) as error:
        load_notify_config(str(path))
    assert str(error.value) == f"agentville-hq: {path}: url must use https unless its host is loopback"


class _Topic(http.server.BaseHTTPRequestHandler):
    received: list = []
    status = 200

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).received.append((self.path, dict(self.headers), body.decode()))
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def topic():
    _Topic.received, _Topic.status = [], 200
    server = http.server.HTTPServer(("127.0.0.1", 0), _Topic)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/alerts"
    server.shutdown()


def test_post_sends_title_tags_priority_and_text_body(topic):
    post = http_post(NotifyConfig(topic, token="tk_secret"))
    post(Message("Reviewer is waiting", "CL · alpha · Home", "agentville,waiting", "default"))
    post(Message("Home 연락 끊김", "body\nline", "agentville,unreachable", "high"))
    (path, headers, body), (_, korean, _) = _Topic.received
    assert path == "/alerts" and body == "CL · alpha · Home"
    assert (headers["Title"], headers["Tags"], headers["Priority"]) == ("Reviewer is waiting", "agentville,waiting", "default")
    assert headers["Authorization"] == "Bearer tk_secret"
    encoded = korean["Title"]
    assert encoded.startswith("=?UTF-8?B?") and base64.b64decode(encoded[10:-2]).decode() == "Home 연락 끊김"


def test_outbox_logs_failures_at_most_once_per_minute(topic):
    _Topic.status = 500
    logged, clock = [], [0.0]
    outbox = Outbox(http_post(NotifyConfig(topic)), log=logged.append, monotonic=lambda: clock[0])
    message = Message("t", "b", "agentville,waiting", "default")
    outbox.put(message)
    outbox.put(message)
    outbox.close()
    assert len(_Topic.received) == 2 and len(logged) == 1 and "HTTP Error 500" in logged[0]
    clock[0] = 61.0
    outbox = Outbox(lambda m: (_ for _ in ()).throw(OSError("unreachable")), log=logged.append, monotonic=lambda: clock[0])
    outbox.put(message)
    outbox.close()
    assert len(logged) == 2 and "unreachable" in logged[1]


def test_full_queue_drops_without_blocking():
    release, logged = threading.Event(), []
    outbox = Outbox(lambda m: release.wait(), size=1, log=logged.append)
    message = Message("t", "b", "agentville,waiting", "default")
    for _ in range(5):
        outbox.put(message)
    assert logged == ["notification failed: queue full, notification dropped"]
    release.set()
    outbox.close()


def _batch(env, kind, payload, seconds):
    return {"messages": [env.wrap(kind, at(seconds), payload, at(seconds))]}


def test_hq_evaluates_after_ingest_and_skips_snapshot_resync(tmp_path):
    sent, now = Sent(), [at(0)]
    n = Notifier(NotifyConfig(URL), sent.append)
    app = create_app(Store(str(tmp_path / "hq.sqlite3")), clock=lambda: now[0], loopback=frozenset({"testclient"}),
                     hosts=frozenset({"testserver"}), notifier=n, notify_interval=3600)
    agent = {"agent_id": "a", "project_id": "p", "project_alias": "alpha", "provider": "codex", "seat": 2, "presence": "on_duty",
             "presence_since": "2026-01-01T00:00:00.000Z",
             "instance": {"instance_id": "i", "started_at": "2026-01-01T00:00:00.000Z", "runtime": {}}}

    def activity(state, seconds):
        return {"agent_id": "a", "instance_id": "i", "state": state, "state_since": at(seconds).isoformat().replace("+00:00", "Z"),
                "source": "app_server", "confidence": "high"}

    env = Envelope("b1")
    with TestClient(app) as client:
        client.post("/api/v1/ingest/messages", json=_batch(env, "snapshot",
                    {"branch": BRANCH, "agents": [agent], "activities": [activity("working", 0)], "contractors": []}, 0))
        now[0] = at(5)
        client.post("/api/v1/ingest/messages", json=_batch(env, "activity", activity("waiting", 5), 5))
        assert sent.titles() == ["Codex 2 is waiting"]
        now[0] = at(60)
        client.post("/api/v1/ingest/messages", json=_batch(env, "snapshot",
                    {"branch": BRANCH, "agents": [agent], "activities": [activity("error", 50)], "contractors": []}, 60))
        assert len(sent) == 1


def test_hq_stops_with_one_line_for_a_bad_notification_file(tmp_path):
    from agentville.hq.main import main

    path = tmp_path / "notify.yaml"
    path.write_text("url: https://ntfy.example.org/t\nlanguage: de\n")
    path.chmod(0o600)
    with pytest.raises(SystemExit) as error:
        main(["--notify-config", str(path), "--db", str(tmp_path / "hq.sqlite3"), "--port", "0"])
    assert error.value.code == f"agentville-hq: {path}: language must be en or ko"
