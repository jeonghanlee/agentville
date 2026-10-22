// Synthetic display data, isolated from the HQ store and real provider sessions.
export function demoState(now = Date.now()) {
  const ago = (seconds) => new Date(now - seconds * 1000).toISOString();
  const branch = (branch_id, alias, reachable, location, time) => ({
    branch_id, reachable, last_seen_at: ago(reachable ? 4 : 840), heartbeat_interval: 30,
    branch: { alias, location, country: "", time, thresholds: { phone: 300, doze: 1800, lounge: 3600, leave: 604800 } },
  });
  const people = [
    ["milo", "Milo", "home", "agentville", "claude", "working", 96, "Bash", "extra-coffee"],
    ["june", "June", "home", "agentville", "codex", "waiting", 140, "", "normal"],
    ["theo", "Theo", "home", "agentville", "claude", "thinking", 45, "", "study-mode"],
    ["sage", "Sage", "garden", "agentville", "codex", "working", 225, "apply_patch", "normal"],
    ["ivy", "Ivy", "home", "garden-ui", "claude", "idle", 720, "", "normal"],
    ["otto", "Otto", "home", "garden-ui", "codex", "idle", 4300, "", "light"],
    ["noah", "Noah", "home", "common-office", "codex", "working", 32, "exec_command", "normal"],
    ["luna", "Luna", "home", "agentville", "claude", "idle", 4000, "", "extra-coffee"],
    ["pip", "Pip", "home", "garden-ui", "codex", "idle", 5200, "", "lazy"],
    ["remy", "Remy", "home", "garden-ui", "claude", "error", 540, "", "normal"],
    ["wren", "Wren", "home", "common-office", "claude", "limited", 900, "", "normal"],
  ];
  const seats = new Map();
  const agents = people.map(([id, alias, host, project, provider, , , , condition]) => {
    const key = [host, provider].join("/");
    const seat = (seats.get(key) || 0) + 1;
    seats.set(key, seat);
    return {
      branch_id: host, agent_id: id, alias, project_id: project,
      project_alias: project === "common-office" ? "Common Office" : project,
      provider, seat, presence: "on_duty", presence_since: ago(10800),
      account_alias: "Demo", model: "", settings: {}, condition,
      instance: { instance_id: "instance-" + id, started_at: ago(10800), runtime: { type: "shell" } },
    };
  });
  const activities = people.map(([id, , host, , , state, seconds, tool]) => ({
    branch_id: host, agent_id: id, instance_id: "instance-" + id, session_id: "demo-" + id,
    state, state_since: ago(seconds), tool, workload: state === "working" ? 12 : 0,
    reset_at: state === "limited" ? new Date(now + 5400 * 1000).toISOString() : null,
    source: "session_log", confidence: "high",
  }));
  const contractor = (parent, id, provider, state, seconds, tool = null) => ({ branch_id: parent === "sage" ? "garden" : "home",
    contractor_id: "helper-" + id, parent_instance_id: "instance-" + parent, provider, origin: "in_process",
    status: "hired", state, state_since: ago(seconds), tool });
  return {
    branches: [branch("home", "Home studio", true, "Stockholm", "Europe/Stockholm"),
      branch("garden", "Garden studio", true, "Seoul", "Asia/Seoul"),
      branch("night", "Night studio", false, "Vancouver", "America/Vancouver")],
    agents, activities,
    contractors: [contractor("milo", "milo", "claude", "working", 240, "Read"),
      contractor("sage", "sage-1", "codex", "working", 80, "exec_command"), contractor("sage", "sage-2", "claude", "waiting", 30),
      contractor("sage", "sage-3", "claude", "idle", 300)],
  };
}

// Synthetic history for the Work log and Timeline replay: three days of deterministic shifts and activity that end in
// demoState(now). Queries follow HQ's rules (architecture Sections 4.4 and 4.5) over these records.
const DAY = 86400000, MINUTE = 60000, HOUR = 3600000;
const HISTORY_DAYS = 3;
const STATES = ["working", "thinking", "waiting", "idle", "completed", "error", "limited", "unknown"];
const ENTRIES = { waiting: "waits", error: "errors", limited: "limits" };
// Activity mix: [state, weight, shortest and longest minutes].
const MIX = [["working", 44, 3, 30], ["thinking", 8, 1, 5], ["waiting", 16, 1, 14], ["idle", 26, 3, 40], ["error", 3, 2, 10], ["limited", 3, 15, 50]];

function seeded(text) {
  let a = 2166136261;
  for (const c of text) a = Math.imul(a ^ c.charCodeAt(0), 16777619);
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let x = Math.imul(a ^ (a >>> 15), a | 1);
    x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}
const iso = (ms) => new Date(ms).toISOString();

export function demoHistory(now = Date.now()) {
  const final = demoState(now);
  const from = now - HISTORY_DAYS * DAY;
  const records = [];
  const push = (branch_id, at, kind, key, payload) => records.push({ branch_id, at, kind, key, payload });
  for (const b of final.branches) push(b.branch_id, from, "branch", "", b.branch);
  for (const agent of final.agents) {
    const random = seeded(agent.agent_id);
    const last = final.activities.find((a) => a.agent_id === agent.agent_id);
    const finalSince = Date.parse(last.state_since);
    // Shifts back from the current one: a rest of 1 to 13 hours, then 2 to 9 hours of work.
    const shifts = [[Date.parse(agent.presence_since), now]];
    for (let start = shifts[0][0]; start > from;) {
      const end = start - (1 + random() * 12) * HOUR;
      if (end <= from) break;
      start = Math.max(from, end - (2 + random() * 7) * HOUR);
      shifts.unshift([start, end]);
    }
    const off = (at) => push(agent.branch_id, at, "agent", agent.agent_id,
      { ...agent, presence: "off_duty", presence_since: iso(at), instance: null });
    if (shifts[0][0] > from) off(from);
    shifts.forEach(([start, end], index) => {
      const current = index === shifts.length - 1;
      const instance = current ? agent.instance
        : { ...agent.instance, instance_id: agent.instance.instance_id + "-" + index, started_at: iso(start) };
      push(agent.branch_id, start, "agent", agent.agent_id, { ...agent, presence_since: iso(start), instance });
      let previous = "";
      for (let at = start, limit = current ? finalSince : end; at < limit;) {
        let pick;
        do {
          let roll = random() * 100;
          pick = MIX.find(([, weight]) => (roll -= weight) < 0) || MIX[0];
        } while (pick[0] === previous);
        previous = pick[0];
        push(agent.branch_id, at, "activity", agent.agent_id, { ...last, instance_id: instance.instance_id, state: pick[0],
          state_since: iso(at), tool: pick[0] === "working" ? last.tool || "Read" : "", workload: pick[0] === "working" ? 6 : 0,
          reset_at: pick[0] === "limited" ? iso(at + pick[3] * MINUTE) : null });
        at = Math.min(limit, at + (pick[2] + random() * (pick[3] - pick[2])) * MINUTE);
      }
      if (current) push(agent.branch_id, finalSince, "activity", agent.agent_id, last);
      else { push(agent.branch_id, end, "activity", agent.agent_id, null); off(end); }
    });
  }
  for (const c of final.contractors) push(c.branch_id, Date.parse(c.state_since), "contractor", c.contractor_id, c);
  records.sort((a, b) => a.at - b.at);
  // Reporting periods: Home stopped for 36 minutes yesterday; Night stopped 14 minutes ago.
  const observed = {
    home: [[from, now - 26 * HOUR], [now - 25.4 * HOUR, now]],
    garden: [[from, now]],
    night: [[from, now - 750000]],
  };
  const clip = (start, end) => [Math.max(start, from), Math.min(end, now)];

  function latest(at, branchId) {
    const rows = new Map();
    for (const r of records) {
      if (r.at > at) break;
      if (branchId && r.branch_id !== branchId) continue;
      const key = JSON.stringify([r.branch_id, r.kind, r.key]);
      if (r.payload === null) rows.delete(key); else rows.set(key, r);
    }
    return rows;
  }
  function overlap(intervals, a, b) {
    return intervals.reduce((sum, [start, end]) => sum + Math.max(0, Math.min(end, b) - Math.max(start, a)), 0);
  }
  function between(start, end, branchId) {
    return records.filter((r) => r.at > start && r.at <= end && (!branchId || r.branch_id === branchId));
  }
  function branchesOf(rows) {
    return rows.filter((r) => r.kind === "branch").map((r) => ({ branch_id: r.branch_id, branch: r.payload }));
  }
  function stateAt(at) {
    const rows = [...latest(at).values()];
    const of = (kind) => rows.filter((r) => r.kind === kind).map((r) => ({ ...r.payload, branch_id: r.branch_id }));
    return {
      branches: rows.filter((r) => r.kind === "branch").map((r) => {
        const spans = observed[r.branch_id] || [];
        const reachable = spans.some(([start, end]) => start <= at && at <= end);
        const lastEnd = Math.max(from, ...spans.filter(([start]) => start <= at).map(([, end]) => Math.min(end, at)));
        return { branch_id: r.branch_id, branch: r.payload, last_seq: null, reachable,
          last_seen_at: iso(reachable ? at - 4000 : lastEnd - 90000) };
      }),
      agents: of("agent"), activities: of("activity"), contractors: of("contractor"),
    };
  }
  // An activity's state and state_since; a transition or an entry is a mark other than the last known one.
  const mark = (p) => p ? p.state + "@" + p.state_since : null;
  // The mark of a colleague's latest activity at or before a time, also one removed since.
  function prior(at, branchId, key) {
    let found = null;
    for (const r of records) {
      if (r.at > at) break;
      if (r.kind === "activity" && r.payload && r.branch_id === branchId && r.key === key) found = mark(r.payload);
    }
    return found;
  }
  function changes(start, end, branchId) {
    [start, end] = clip(start, end);
    // A period entirely outside the kept history, or after now, is empty (Section 4.2).
    if (start >= end) return { from: null, to: null, changes: [], truncated: false, agents: [], branches: [] };
    const initial = latest(start, branchId);
    const presence = new Map(), marks = new Map(), out = [], known = new Map(initial);
    for (const r of initial.values()) {
      if (r.kind === "agent") presence.set(r.key, r.payload.presence);
      if (r.kind === "activity") marks.set(r.key, mark(r.payload));
    }
    for (const r of between(start, end, branchId)) {
      if (r.payload) known.set(JSON.stringify([r.branch_id, r.kind, r.key]), r);
      if (r.kind === "agent") {
        if (r.payload && r.payload.presence !== presence.get(r.key)) {
          out.push({ at: iso(r.at), kind: "presence", branch_id: r.branch_id, agent_id: r.key, presence: r.payload.presence });
        }
        presence.set(r.key, r.payload?.presence);
      } else if (r.kind === "activity") {
        if (!marks.has(r.key)) marks.set(r.key, prior(start, r.branch_id, r.key));
        if (r.payload && mark(r.payload) !== marks.get(r.key)) {
          out.push({ at: iso(r.at), kind: "activity", branch_id: r.branch_id, agent_id: r.key,
            state: r.payload.state, state_since: r.payload.state_since });
        }
        // A removed activity keeps its last mark, so restoring it is not a new transition.
        if (r.payload) marks.set(r.key, mark(r.payload));
      }
    }
    for (const [branch_id, spans] of Object.entries(observed)) {
      if (branchId && branch_id !== branchId) continue;
      for (const [a, b] of spans) {
        if (a > start && a <= end) out.push({ at: iso(a), kind: "reachability", branch_id, reachable: true });
        if (b > start && b < end) out.push({ at: iso(b), kind: "reachability", branch_id, reachable: false });
      }
    }
    out.sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
    const ids = new Set(out.filter((c) => c.agent_id).map((c) => c.branch_id + "/" + c.agent_id));
    const rows = [...known.values()];
    return { from: iso(start), to: iso(end), changes: out, truncated: false, branches: branchesOf(rows),
      agents: rows.filter((r) => r.kind === "agent" && ids.has(r.branch_id + "/" + r.key)).map((r) => ({ ...r.payload, branch_id: r.branch_id })) };
  }
  function worklog(start, end, branchId) {
    [start, end] = clip(start, end);
    if (start >= end) return { from: null, to: null, rows: [], branches: [] };
    const people = new Map();
    const person = (r) => {
      const key = r.branch_id + "/" + r.key;
      if (!people.has(key)) {
        people.set(key, { branch_id: r.branch_id, agent_id: r.key, at: start, agent: null, activity: null, last: null, mark: null,
          seconds: Object.fromEntries(["on_duty", ...STATES, "unobserved"].map((s) => [s, 0])), waits: 0, errors: 0, limits: 0, runs: new Map() });
      }
      return people.get(key);
    };
    const close = (p, until) => {
      if (until > p.at && p.agent?.presence === "on_duty") {
        const seen = overlap(observed[p.branch_id] || [], p.at, until) / 1000;
        const state = STATES.includes(p.activity?.state) ? p.activity.state : "unknown";
        p.seconds.on_duty += seen; p.seconds[state] += seen; p.seconds.unobserved += (until - p.at) / 1000 - seen;
        if (state === "waiting") p.runs.set(p.activity.state_since, (p.runs.get(p.activity.state_since) || 0) + seen);
      }
      p.at = Math.max(p.at, until);
    };
    for (const r of latest(start, branchId).values()) {
      if (r.kind === "agent") { const p = person(r); p.agent = p.last = r.payload; }
      if (r.kind === "activity") { const p = person(r); p.activity = r.payload; p.mark = mark(r.payload); p.settled = true; }
    }
    for (const r of between(start, end, branchId)) {
      if (r.kind !== "agent" && r.kind !== "activity") continue;
      const p = person(r);
      close(p, r.at);
      if (r.kind === "agent") { p.agent = r.payload; p.last = r.payload || p.last; continue; }
      const state = r.payload?.state;
      // An entry is a state or state_since other than the last known one, also after the activity was removed.
      if (!p.settled) { p.mark = prior(start, r.branch_id, r.key); p.settled = true; }
      if (ENTRIES[state] && mark(r.payload) !== p.mark) p[ENTRIES[state]]++;
      p.activity = r.payload;
      p.mark = mark(r.payload) || p.mark;
    }
    const rows = [];
    for (const p of people.values()) {
      close(p, end);
      if (!p.last || !(p.seconds.on_duty || p.seconds.unobserved || p.waits || p.errors || p.limits)) continue;
      rows.push({ branch_id: p.branch_id, agent_id: p.agent_id, project_id: p.last.project_id, project_alias: p.last.project_alias,
        provider: p.last.provider, seat: p.last.seat, alias: p.last.alias, seconds: p.seconds, waits: p.waits,
        longest_wait: Math.max(0, ...p.runs.values()), errors: p.errors, limits: p.limits });
    }
    rows.sort((a, b) => a.branch_id.localeCompare(b.branch_id) || a.project_alias.localeCompare(b.project_alias)
      || a.provider.localeCompare(b.provider) || a.seat - b.seat);
    return { from: iso(start), to: iso(end), rows, branches: branchesOf([...latest(end, branchId).values()]) };
  }
  return { range: () => ({ from, to: now }), stateAt, changes, worklog };
}
