// Meeting participation (M2 P2, decision D6). Presentation only: computed in the page from observed state, never
// recorded, sent, or stored, and sharing the meeting room implies no collaboration relationship.
// Times are the page's own wall-clock milliseconds; `state_since` is not used, because the Collector restarts it on
// every tool start.

export const ENTRY_MS = 60000;
export const EXIT_MS = 30000;
const COMMON = "common-office";
const QUALIFYING = new Set(["working", "thinking"]);
// States that end membership at once; any other non-qualifying state ends it after EXIT_MS.
const IMMEDIATE = new Set(["waiting", "error", "limited", "off_duty"]);
const KNOWN = new Set(["working", "thinking", "waiting", "idle", "completed", "error", "limited", "unknown"]);
const keyOf = (branch, id) => JSON.stringify([branch, id]);

// The activity state the page shows for an agent: off duty unless on duty, `unknown` without a known activity.
function observedState(agent, activity) {
  if (agent.presence !== "on_duty") return "off_duty";
  return activity && KNOWN.has(activity.state) ? activity.state : "unknown";
}

// Observation tracker. `observations` is { colleagues }, which maps each colleague key to its last observed state,
// the start of its current continuous run in `working` or `thinking` (qualifiedSince), and the start of its current
// run in any other state (otherSince). Returns the next observations; the input is not changed. A load starts from
// createObservations(); a reconnect passes restart, which restarts every clock from this state, so no colleague
// qualifies until observed for the full entry time again. A Branch or page change does not touch the observations.
export function createObservations() {
  return { colleagues: {} };
}

export function observe(observations, state, now, { restart = false } = {}) {
  const previous = restart ? {} : observations.colleagues;
  const activities = new Map((state.activities || []).map((a) => [keyOf(a.branch_id, a.agent_id), a]));
  const colleagues = {};
  for (const agent of state.agents || []) {
    const key = keyOf(agent.branch_id, agent.agent_id);
    const value = observedState(agent, activities.get(key));
    const last = previous[key];
    colleagues[key] = QUALIFYING.has(value)
      ? { state: value, qualifiedSince: last?.qualifiedSince ?? now, otherSince: null }
      : { state: value, qualifiedSince: null, otherSince: last?.otherSince ?? now };
  }
  return { colleagues };
}

function closedRecord(closed, kind, id) {
  return Boolean((closed || []).find((record) => record.kind === kind && record.id === id)?.closed);
}

// Colleagues eligible on one Branch: on duty, in that Branch's office (its own colleagues and remote colleagues of
// its Projects), of a Project with a project room (not the Common Office), and not in a closed Project or Branch.
// The displayed page and "+N" collapsing play no part.
function eligibleOn(branchId, state, closed) {
  if (closedRecord(closed, "branch", branchId)) return [];
  const projects = new Set((state.agents || []).filter((a) => a.branch_id === branchId).map((a) => a.project_id));
  return (state.agents || []).filter((agent) => agent.presence === "on_duty" && projects.has(agent.project_id)
    && agent.project_id !== COMMON && !closedRecord(closed, "project", agent.project_id)
    && !closedRecord(closed, "branch", agent.branch_id));
}

// Members are ordered by the start of their current continuous qualification, then by agent id (and Branch id for
// remote colleagues that share an agent id).
function byQualification(a, b) {
  return a.since - b.since || a.agent.agent_id.localeCompare(b.agent.agent_id) || a.agent.branch_id.localeCompare(b.agent.branch_id);
}

function member(candidate, chair) {
  return { key: candidate.key, branch_id: candidate.agent.branch_id, agent_id: candidate.agent.agent_id, chair };
}

// The meeting of every Branch in `state`, keyed by branch_id: null, or { project_id, members } with members
// { key, branch_id, agent_id, chair } in chair order.
// - previous: the result of the last call. A meeting in progress survives a reconnect: its members stay until an
//   exit condition is observed, counted on the restarted clocks, and nobody joins until qualified again.
// - mode: "live" forms meetings; "replay" forms none (the replayed state is sampled once per minute), and "demo"
//   forms none either, since the demo receives a single state and lists its fixed meeting as data.
// - closed: the lifecycle records of the state ({ kind, id, closed }).
// - capacity: the number of meeting chairs.
export function meetings(state, observations, previous, now, mode, closed, capacity) {
  const result = {};
  for (const branch of state.branches || []) result[branch.branch_id] = null;
  if (mode !== "live" || capacity < 2) return result;
  for (const branchId of Object.keys(result)) {
    const candidates = eligibleOn(branchId, state, closed).map((agent) => {
      const key = keyOf(agent.branch_id, agent.agent_id);
      const seen = observations.colleagues[key];
      return { key, agent, seen, since: seen?.qualifiedSince ?? Infinity };
    }).filter((candidate) => candidate.seen);
    const qualifies = (c) => c.seen.qualifiedSince !== null && now - c.seen.qualifiedSince >= ENTRY_MS;
    const byKey = new Map(candidates.map((c) => [c.key, c]));
    let meeting = null;
    const last = previous?.[branchId];
    if (last) {
      // Members leave at once on waiting, error, limited, off duty, or loss of eligibility (including a change of
      // Project), and after EXIT_MS in any other non-qualifying state.
      const stay = last.members.filter(({ key }) => {
        const c = byKey.get(key);
        if (!c || c.agent.project_id !== last.project_id) return false;
        if (c.seen.qualifiedSince !== null) return true;
        return !IMMEDIATE.has(c.seen.state) && now - c.seen.otherSince < EXIT_MS;
      });
      // A freed chair goes to the next qualifying colleague of the same Project, lowest chair first.
      const taken = new Set(stay.map((m) => m.chair));
      const members = [...stay];
      const waiting = candidates.filter((c) => c.agent.project_id === last.project_id && qualifies(c)
        && !members.some((m) => m.key === c.key)).sort(byQualification);
      for (let chair = 0; chair < capacity && waiting.length; chair++) {
        if (!taken.has(chair)) members.push(member(waiting.shift(), chair));
      }
      // The meeting ends when fewer than two members remain.
      if (members.length >= 2) {
        meeting = { project_id: last.project_id, members: members.sort((a, b) => a.chair - b.chair) };
      }
    }
    if (!meeting) {
      // No preemption: only without a meeting in progress does the Project with the most qualifying colleagues
      // start, ties broken by the earliest time it qualified (when its second colleague qualified), then Project id.
      const projects = new Map();
      for (const c of candidates.filter(qualifies)) {
        if (!projects.has(c.agent.project_id)) projects.set(c.agent.project_id, []);
        projects.get(c.agent.project_id).push(c);
      }
      const ranked = [...projects].filter(([, list]) => list.length >= 2).map(([id, list]) => {
        list.sort(byQualification);
        return { id, list, qualified: list[1].since + ENTRY_MS };
      }).sort((a, b) => b.list.length - a.list.length || a.qualified - b.qualified || a.id.localeCompare(b.id));
      if (ranked.length) {
        meeting = { project_id: ranked[0].id,
          members: ranked[0].list.slice(0, capacity).map((c, chair) => member(c, chair)) };
      }
    }
    result[branchId] = meeting;
  }
  return result;
}
