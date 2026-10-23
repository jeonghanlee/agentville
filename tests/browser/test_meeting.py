"""M2 T2a: meeting membership of meeting.js follows P2 (docs/milestone-0.4.0.md, M2), run in Chromium."""

import pytest

from tests.browser_support import launch_options, playwright_sync

playwright = playwright_sync()

from tests.lifecycle_support import HQ

# Builds states from rows [branch, agent, project, state, presence] and runs a sequence of steps through the
# observation tracker and meetings(). Each step: { at (page seconds), rows (kept from the last step when absent),
# restart (reconnect), reload (a new page), mode, closed, capacity, shuffle }. Each result maps a Branch to
# "project:agent@chair,..." or null.
HARNESS = """async () => {
  const meeting = await import("/meeting.js");
  const state = (rows, closed = [], shuffle = false) => {
    const list = shuffle ? [...rows].reverse() : rows;
    const branches = [...new Set(list.map(([branch]) => branch).concat(["b1", "b2"]))].sort();
    return {
      branches: (shuffle ? branches.reverse() : branches).map((branch_id) => ({ branch_id, reachable: true })),
      agents: list.map(([branch_id, agent_id, project_id, , presence = "on_duty"]) => ({ branch_id, agent_id, project_id, presence })),
      // state_since is far in the past and changes at every step: the page's own clock decides, not state_since.
      activities: list.map(([branch_id, agent_id, , value], i) => ({ branch_id, agent_id, state: value,
        state_since: new Date(Date.UTC(2020, 0, 1, 0, 0, i)).toISOString() })),
      contractors: [], lifecycles: closed,
    };
  };
  const summary = (result) => Object.fromEntries(Object.entries(result).map(([branch, m]) => [branch, m
    ? m.project_id + ":" + m.members.map((x) => (x.branch_id === branch ? "" : x.branch_id + "/") + x.agent_id + "@" + x.chair).join(",")
    : null]));
  window.runMeetings = (steps) => {
    let observations = meeting.createObservations(), previous = {}, rows = [], out = [];
    for (const step of steps) {
      rows = step.rows || rows;
      const now = step.at * 1000;
      const current = state(rows, step.closed || [], step.shuffle);
      if (step.reload) { observations = meeting.createObservations(); previous = {}; }
      observations = meeting.observe(observations, current, now, { restart: Boolean(step.restart) });
      previous = meeting.meetings(current, observations, previous, now, step.mode || "live", current.lifecycles, step.capacity ?? 6);
      out.push(summary(previous));
    }
    return out;
  };
  window.meetingModule = meeting;
}"""


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    with HQ(tmp_path_factory.mktemp("meeting") / "hq.sqlite3") as hq, playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(**launch_options())
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(hq.url + "/favicon.svg")
        page.evaluate(HARNESS)
        yield page
        assert not errors
        browser.close()


def run(page, steps):
    return [result["b1"] for result in page.evaluate("(steps) => runMeetings(steps)", steps)]


def pair(state_a="working", state_b="working", project="p"):
    return [["b1", "a", project, state_a], ["b1", "b", project, state_b]]


def test_entry_after_60_seconds_of_working_or_thinking(page):
    rows = pair("working", "thinking")
    assert run(page, [{"at": 0, "rows": rows}, {"at": 30}, {"at": 59.9}, {"at": 60}]) == [None, None, None, "p:a@0,b@1"]
    # Switching between working and thinking keeps the run continuous.
    assert run(page, [{"at": 0, "rows": pair()}, {"at": 30, "rows": pair("thinking", "working")}, {"at": 60}])[-1] == "p:a@0,b@1"
    # A colleague observed later qualifies 60 s after its own first observation.
    late = [{"at": 0, "rows": pair("working", "idle")}, {"at": 20, "rows": pair()}, {"at": 79}, {"at": 80}]
    assert run(page, late) == [None, None, None, "p:a@0,b@1"]
    # One qualifying colleague is not a meeting, nor are colleagues in other states.
    assert run(page, [{"at": 0, "rows": [["b1", "a", "p", "working"]]}, {"at": 120}]) == [None, None]
    assert run(page, [{"at": 0, "rows": pair("idle", "waiting")}, {"at": 120}]) == [None, None]


def test_exit_after_30_seconds_and_immediate_exits(page):
    trio = [["b1", "a", "p", "working"], ["b1", "b", "p", "working"], ["b1", "c", "p", "working"]]
    start = [{"at": 0, "rows": trio}, {"at": 60}]
    for other in ["idle", "completed", "unknown"]:
        changed = [["b1", "a", "p", "working"], ["b1", "b", "p", other], ["b1", "c", "p", "working"]]
        result = run(page, start + [{"at": 70, "rows": changed}, {"at": 99.9}, {"at": 100}])
        assert result[1:] == ["p:a@0,b@1,c@2", "p:a@0,b@1,c@2", "p:a@0,b@1,c@2", "p:a@0,c@2"], other
    # Back to working within 30 s keeps the member.
    back = start + [{"at": 70, "rows": [["b1", "a", "p", "working"], ["b1", "b", "p", "idle"], ["b1", "c", "p", "working"]]},
                    {"at": 90, "rows": trio}, {"at": 130}]
    assert run(page, back)[-1] == "p:a@0,b@1,c@2"
    for state, presence in [("waiting", "on_duty"), ("error", "on_duty"), ("limited", "on_duty"), ("working", "off_duty")]:
        changed = [["b1", "a", "p", "working"], ["b1", "b", "p", state, presence], ["b1", "c", "p", "working"]]
        assert run(page, start + [{"at": 61, "rows": changed}])[-1] == "p:a@0,c@2", state
    # Loss of eligibility: moving to another Project or to the Common Office, a closed Project, or leaving the state.
    moved = [["b1", "a", "p", "working"], ["b1", "b", "q", "working"], ["b1", "c", "p", "working"]]
    assert run(page, start + [{"at": 61, "rows": moved}])[-1] == "p:a@0,c@2"
    common = [["b1", "a", "p", "working"], ["b1", "b", "common-office", "working"], ["b1", "c", "p", "working"]]
    assert run(page, start + [{"at": 61, "rows": common}])[-1] == "p:a@0,c@2"
    assert run(page, start + [{"at": 61, "closed": [{"kind": "project", "id": "p", "closed": True}]}])[-1] is None
    assert run(page, start + [{"at": 61, "rows": trio[:2]}, {"at": 62, "rows": trio[:1]}])[1:] == ["p:a@0,b@1,c@2", "p:a@0,b@1", None]
    # The meeting ends when fewer than two members remain; the member left goes back to the existing rules.
    ends = [{"at": 0, "rows": pair()}, {"at": 60}, {"at": 61, "rows": pair("working", "waiting")}]
    assert run(page, ends) == [None, "p:a@0,b@1", None]


def test_no_preemption_and_tie_rules(page):
    meeting_p = pair()
    more_q = [["b1", "q1", "q", "working"], ["b1", "q2", "q", "working"], ["b1", "q3", "q", "working"]]
    steps = [{"at": 0, "rows": meeting_p}, {"at": 60}, {"at": 61, "rows": meeting_p + more_q}, {"at": 200},
             {"at": 201, "rows": pair("waiting", "waiting") + more_q}]
    assert run(page, steps) == [None, "p:a@0,b@1", "p:a@0,b@1", "p:a@0,b@1", "q:q1@0,q2@1,q3@2"]
    # Most qualifying colleagues first, even if that Project qualified later.
    two = [["b1", "x1", "x", "working"], ["b1", "x2", "x", "working"]]
    three = [["b1", "y1", "y", "idle"], ["b1", "y2", "y", "idle"], ["b1", "y3", "y", "idle"]]
    working_three = [[b, a, p, "working"] for b, a, p, _ in three]
    assert run(page, [{"at": 0, "rows": two + three}, {"at": 10, "rows": two + working_three},
                      {"at": 70}])[-1] == "y:y1@0,y2@1,y3@2"
    # Equal counts: the earliest time a Project qualified (its second colleague), then Project id.
    zeta = [["b1", "z1", "zeta", "working"], ["b1", "z2", "zeta", "working"]]
    alpha_idle = [["b1", "a1", "alpha", "idle"], ["b1", "a2", "alpha", "idle"]]
    alpha = [[b, a, p, "working"] for b, a, p, _ in alpha_idle]
    assert run(page, [{"at": 0, "rows": zeta + alpha_idle}, {"at": 5, "rows": zeta + alpha}, {"at": 70}])[-1] == "zeta:z1@0,z2@1"
    assert run(page, [{"at": 0, "rows": zeta + alpha}, {"at": 70}])[-1] == "alpha:a1@0,a2@1"
    # The second colleague decides when a Project qualified: alpha's first qualifies at 60 s but its second at
    # 70 s, zeta's both at 65 s, so zeta starts although alpha comes first by its first colleague and by id.
    alpha_late = [["b1", "a1", "alpha", "working"], ["b1", "a2", "alpha", "idle"]]
    zeta_idle = [[b, a, p, "idle"] for b, a, p, _ in zeta]
    assert run(page, [{"at": 0, "rows": alpha_late + zeta_idle}, {"at": 5, "rows": alpha_late + zeta},
                      {"at": 10, "rows": alpha + zeta}, {"at": 70}])[-1] == "zeta:z1@0,z2@1"


def test_capacity_member_order_and_chair_order(page):
    # Eight colleagues of one Project, more than any room's desks ("+N"), first observed at different times.
    names = ["h", "g", "f", "e", "d", "c", "b", "a"]
    steps = [{"at": 0, "rows": [["b1", n, "p", "working" if i < 4 else "idle"] for i, n in enumerate(names)]},
             {"at": 5, "rows": [["b1", n, "p", "working"] for n in names]}, {"at": 65}]
    # Same qualification start: agent id; then later starts. Capacity 6 takes the first six in that order.
    assert run(page, steps)[-1] == "p:e@0,f@1,g@2,h@3,a@4,b@5"
    assert run(page, steps[:2] + [{"at": 65, "capacity": 4}])[-1] == "p:e@0,f@1,g@2,h@3"
    # A member leaving frees its chair for the next qualifying colleague in that order; the others keep their chairs.
    leave = [["b1", n, "p", "waiting" if n == "g" else "working"] for n in names]
    assert run(page, steps + [{"at": 66, "rows": leave}])[-1] == "p:e@0,f@1,c@2,h@3,a@4,b@5"
    leave_two = [["b1", n, "p", "waiting" if n in ("f", "a") else "working"] for n in names]
    assert run(page, steps + [{"at": 66, "rows": leave_two}])[-1] == "p:e@0,c@1,g@2,h@3,d@4,b@5"
    # A colleague observed later joins only after its own 60 s, into the lowest free chair.
    newcomer = leave + [["b1", "aa", "p", "working"]]
    without_e = [r for r in newcomer if r[1] != "e"]
    without_f = [r for r in without_e if r[1] != "f"]
    later = steps + [{"at": 66, "rows": leave}, {"at": 67, "rows": newcomer}, {"at": 68, "rows": without_e},
                     {"at": 127}, {"at": 128, "rows": without_f}]
    assert run(page, later)[-5:] == ["p:e@0,f@1,c@2,h@3,a@4,b@5", "p:e@0,f@1,c@2,h@3,a@4,b@5",
                                     "p:d@0,f@1,c@2,h@3,a@4,b@5", "p:d@0,f@1,c@2,h@3,a@4,b@5", "p:d@0,aa@1,c@2,h@3,a@4,b@5"]
    # No meeting chairs for fewer than two.
    assert run(page, steps[:2] + [{"at": 65, "capacity": 1}])[-1] is None


def test_common_office_closed_records_and_remote_colleagues(page):
    common = [["b1", "a", "common-office", "working"], ["b1", "b", "common-office", "working"]]
    assert run(page, [{"at": 0, "rows": common}, {"at": 90}]) == [None, None]
    for closed in [{"kind": "project", "id": "p", "closed": True}, {"kind": "branch", "id": "b1", "closed": True}]:
        assert run(page, [{"at": 0, "rows": pair()}, {"at": 90, "closed": [closed]}])[-1] is None
    reopened = [{"kind": "project", "id": "p", "closed": False}]
    assert run(page, [{"at": 0, "rows": pair()}, {"at": 90, "closed": reopened}])[-1] == "p:a@0,b@1"
    # Remote colleagues of a Branch's Project count on that Branch (whose own colleague may be off duty) and on their
    # home Branch; a remote colleague whose own Branch is closed is not eligible.
    remote = [["b1", "local", "p", "idle", "off_duty"], ["b2", "r1", "p", "working"], ["b2", "r2", "p", "working"],
              ["b2", "other", "elsewhere", "working"], ["b2", "other2", "elsewhere", "working"]]
    both = page.evaluate("(steps) => runMeetings(steps)", [{"at": 0, "rows": remote}, {"at": 60}])[-1]
    assert both == {"b1": "p:b2/r1@0,b2/r2@1", "b2": "elsewhere:other@0,other2@1"}
    alone = page.evaluate("(steps) => runMeetings(steps)",
                          [{"at": 0, "rows": [r for r in remote if r[2] == "p"]}, {"at": 60}])[-1]
    assert alone == {"b1": "p:b2/r1@0,b2/r2@1", "b2": "p:r1@0,r2@1"}
    closed_home = [{"kind": "branch", "id": "b2", "closed": True}]
    assert run(page, [{"at": 0, "rows": remote}, {"at": 60, "closed": closed_home}])[-1] is None


def test_reload_reconnect_branch_and_page_change_and_replay(page):
    # A reload is a new page: nobody qualifies until observed again for the full entry time.
    reload = [{"at": 0, "rows": pair()}, {"at": 60}, {"at": 100, "reload": True}, {"at": 159}, {"at": 160}]
    assert run(page, reload) == [None, "p:a@0,b@1", None, None, "p:a@0,b@1"]
    # A reconnect restarts every clock but is no exit: a meeting in progress keeps its members.
    reconnect = [{"at": 0, "rows": pair()}, {"at": 60}, {"at": 100, "restart": True}, {"at": 159}, {"at": 160}]
    assert run(page, reconnect) == [None, "p:a@0,b@1", "p:a@0,b@1", "p:a@0,b@1", "p:a@0,b@1"]
    # A member's 30 s in another state counts from its observation after the reconnect.
    trio = [["b1", n, "p", "working"] for n in "abc"]
    idle_b = [["b1", n, "p", "idle" if n == "b" else "working"] for n in "abc"]
    steps = [{"at": 0, "rows": trio}, {"at": 60}, {"at": 80, "rows": idle_b}, {"at": 100, "restart": True},
             {"at": 110}, {"at": 129.9}, {"at": 130}]
    assert run(page, steps)[1:] == ["p:a@0,b@1,c@2"] * 5 + ["p:a@0,c@2"]
    # Nobody joins until qualified again: d qualified before the reconnect but must be observed 60 s after it.
    four = [["b1", n, "p", "working"] for n in "abcd"]
    leave_a = [["b1", n, "p", "waiting" if n == "a" else "working"] for n in "abcd"]
    steps = [{"at": 0, "rows": four, "capacity": 3}, {"at": 60, "capacity": 3}, {"at": 100, "restart": True, "capacity": 3},
             {"at": 101, "rows": leave_a, "capacity": 3}, {"at": 159, "capacity": 3}, {"at": 160, "capacity": 3}]
    assert run(page, steps)[1:] == ["p:a@0,b@1,c@2", "p:a@0,b@1,c@2", "p:b@1,c@2", "p:b@1,c@2", "p:d@0,b@1,c@2"]
    # A Branch or page change is no input: states listing Branches and colleagues in another order (as a page with
    # another Branch shown receives them) keep the clocks and the meeting of every Branch.
    two_branches = pair() + [["b2", "c", "q", "working"], ["b2", "d", "q", "working"]]
    steps = [{"at": 0, "rows": two_branches}, {"at": 30, "shuffle": True}, {"at": 60}, {"at": 61, "shuffle": True}]
    results = page.evaluate("(steps) => runMeetings(steps)", steps)
    assert results[2] == results[3] == {"b1": "p:a@0,b@1", "b2": "q:c@0,d@1"}
    # Replay forms no meeting, even when colleagues qualify; back to live the clocks have kept running.
    replay = [{"at": 0, "rows": pair()}, {"at": 70, "mode": "replay"}, {"at": 80, "mode": "replay"}, {"at": 81}]
    assert run(page, replay) == [None, None, None, "p:a@0,b@1"]
    assert run(page, [{"at": 0, "rows": pair()}, {"at": 60}, {"at": 61, "mode": "replay"}]) == [None, "p:a@0,b@1", None]
    # The demo receives a single state; its fixed meeting is data, not formed by these rules.
    assert run(page, [{"at": 0, "rows": pair()}, {"at": 70, "mode": "demo"}])[-1] is None


def test_observation_tracker_is_pure_and_ignores_state_since(page):
    result = page.evaluate("""() => {
      const m = window.meetingModule;
      const state = (value, since) => ({ branches: [{ branch_id: "b1" }],
        agents: [{ branch_id: "b1", agent_id: "a", project_id: "p", presence: "on_duty" }],
        activities: [{ branch_id: "b1", agent_id: "a", state: value, state_since: since }] });
      const first = m.observe(m.createObservations(), state("working", "2020-01-01T00:00:00Z"), 1000);
      const copy = JSON.stringify(first);
      const second = m.observe(first, state("thinking", "2026-01-01T00:00:00Z"), 5000);
      const third = m.observe(second, state("idle", "2026-01-01T00:00:00Z"), 9000);
      const fourth = m.observe(third, state("completed", "2026-01-01T00:00:01Z"), 12000);
      const restarted = m.observe(fourth, state("working", "2020-01-01T00:00:00Z"), 20000, { restart: true });
      return { unchanged: JSON.stringify(first) === copy, first: first.colleagues, second: second.colleagues,
        fourth: fourth.colleagues, restarted };
    }""")
    key = '["b1","a"]'
    assert result["unchanged"]
    assert result["first"][key] == {"state": "working", "qualifiedSince": 1000, "otherSince": None}
    assert result["second"][key] == {"state": "thinking", "qualifiedSince": 1000, "otherSince": None}
    assert result["fourth"][key] == {"state": "completed", "qualifiedSince": None, "otherSince": 9000}
    assert result["restarted"] == {"colleagues": {key: {"state": "working", "qualifiedSince": 20000, "otherSince": None}}}


def test_implementation_clarifications_of_d6(page):
    # (a) A freed chair is refilled before the two-member check: c takes a's chair and b keeps chair 1, instead of
    # the meeting ending and restarting as b@0, c@1.
    trio = [["b1", n, "p", "working"] for n in "abc"]
    leave_a = [["b1", n, "p", "waiting" if n == "a" else "working"] for n in "abc"]
    steps = [{"at": 0, "rows": trio, "capacity": 2}, {"at": 60, "capacity": 2}, {"at": 61, "rows": leave_a, "capacity": 2}]
    assert run(page, steps)[1:] == ["p:a@0,b@1", "p:c@0,b@1"]
    # (b) A closed evaluated Branch excludes every colleague evaluated on it, remote colleagues from an open Branch too.
    remote = [["b1", "local", "p", "idle", "off_duty"], ["b2", "r1", "p", "working"], ["b2", "r2", "p", "working"]]
    closed = [{"kind": "branch", "id": "b1", "closed": True}]
    result = page.evaluate("(steps) => runMeetings(steps)", [{"at": 0, "rows": remote}, {"at": 60, "closed": closed}])[-1]
    assert result == {"b1": None, "b2": "p:r1@0,r2@1"}
    # (c) Colleagues with the same agent id and the same qualification start are ordered by Branch id.
    same = [["b1", "local", "p", "idle", "off_duty"], ["b3", "x", "p", "working"], ["b2", "x", "p", "working"]]
    result = page.evaluate("(steps) => runMeetings(steps)", [{"at": 0, "rows": same}, {"at": 60}])[-1]
    assert result["b1"] == "p:b2/x@0,b3/x@1"
