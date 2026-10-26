// Contractor teams (architecture Section 6.2). Presentation only: computed in the page from observed state, never
// recorded, sent, or stored. A colleague with Contractors works with them away from its desk, at a meeting-room
// table or in a Fika group; sharing a table implies no collaboration relationship.
// Times are the page's own wall-clock milliseconds, as for meetings (meeting.js); `state_since` is not used.

export const TEAM_ENTRY_MS = 10000;
export const TEAM_EXIT_MS = 10000;
const COMMON = "common-office";
// States that end a team at once; the colleague then returns to where the other rules place it.
const IMMEDIATE = new Set(["waiting", "error", "limited", "off_duty"]);
const KNOWN = new Set(["working", "thinking", "waiting", "idle", "completed", "error", "limited", "unknown"]);
const keyOf = (branch, id) => JSON.stringify([branch, id]);

function observedState(agent, activity) {
  if (agent.presence !== "on_duty") return "off_duty";
  return activity && KNOWN.has(activity.state) ? activity.state : "unknown";
}

// The current Contractors of each colleague, keyed like colleagues, in the order of the state.
export function contractorsByColleague(state) {
  const result = new Map();
  for (const agent of state.agents || []) {
    const list = (state.contractors || []).filter((c) => c.branch_id === agent.branch_id
      && c.parent_instance_id === agent.instance?.instance_id && c.status !== "ended");
    result.set(keyOf(agent.branch_id, agent.agent_id), list);
  }
  return result;
}

// Observation tracker: colleagues[key] = { state, count, withSince, withoutSince }. withSince starts a continuous
// run with at least one current Contractor in a state that does not end a team; withoutSince starts a run without
// Contractors. A load starts from createTeamObservations(); a reconnect passes restart, which restarts every clock.
export function createTeamObservations() {
  return { colleagues: {} };
}

export function observeTeams(observations, state, now, { restart = false } = {}) {
  const previous = restart ? {} : observations.colleagues;
  const activities = new Map((state.activities || []).map((a) => [keyOf(a.branch_id, a.agent_id), a]));
  const contractors = contractorsByColleague(state);
  const colleagues = {};
  for (const agent of state.agents || []) {
    const key = keyOf(agent.branch_id, agent.agent_id);
    const value = observedState(agent, activities.get(key)), count = contractors.get(key)?.length || 0;
    const last = previous[key];
    const withContractors = count > 0 && !IMMEDIATE.has(value);
    colleagues[key] = { state: value, count,
      withSince: withContractors ? last?.withSince ?? now : null,
      withoutSince: count > 0 ? null : last?.withoutSince ?? now };
  }
  return { colleagues };
}

function closedRecord(closed, kind, id) {
  return Boolean((closed || []).find((record) => record.kind === kind && record.id === id)?.closed);
}

// Colleagues that can form a team on one Branch: on duty, in that Branch's office (its own colleagues, Common Office
// included, and remote colleagues of its Project rooms), and not in a closed Project or Branch.
function eligibleOn(branchId, state, closed) {
  if (closedRecord(closed, "branch", branchId)) return [];
  const projects = new Set((state.agents || []).filter((a) => a.branch_id === branchId && a.project_id !== COMMON)
    .map((a) => a.project_id));
  return (state.agents || []).filter((agent) => agent.presence === "on_duty"
    && (agent.branch_id === branchId || projects.has(agent.project_id))
    && !closedRecord(closed, "project", agent.project_id) && !closedRecord(closed, "branch", agent.branch_id));
}

// The teams of every Branch in `state`, keyed by branch_id: a list of { key, branch_id, agent_id, since } in the
// order they formed (since), then by agent id and Branch id.
// - previous: the result of the last call. A team ends TEAM_EXIT_MS after its last Contractor ends, or at once on
//   waiting, error, limited, off duty, or loss of eligibility.
// - mode: "live" forms a team after TEAM_ENTRY_MS of observation; "replay" forms one from each sampled state at once,
//   since the replayed state is sampled once per minute; "demo" forms none (the demo lists its fixed team as data).
export function teams(state, observations, previous, now, mode, closed) {
  const result = {};
  for (const branch of state.branches || []) result[branch.branch_id] = [];
  if (mode === "demo") return result;
  const contractors = mode === "replay" ? contractorsByColleague(state) : null;
  const activities = mode === "replay" ? new Map((state.activities || []).map((a) => [keyOf(a.branch_id, a.agent_id), a])) : null;
  for (const branchId of Object.keys(result)) {
    const held = new Map((previous?.[branchId] || []).map((team) => [team.key, team]));
    const list = [];
    for (const agent of eligibleOn(branchId, state, closed)) {
      const key = keyOf(agent.branch_id, agent.agent_id);
      if (mode === "replay") {
        if ((contractors.get(key)?.length || 0) && !IMMEDIATE.has(observedState(agent, activities.get(key))))
          list.push({ key, branch_id: agent.branch_id, agent_id: agent.agent_id, since: now });
        continue;
      }
      const seen = observations.colleagues[key];
      if (!seen || IMMEDIATE.has(seen.state)) continue;
      const last = held.get(key);
      if (last && (seen.count > 0 || now - seen.withoutSince < TEAM_EXIT_MS)) { list.push(last); continue; }
      if (seen.withSince !== null && now - seen.withSince >= TEAM_ENTRY_MS)
        list.push({ key, branch_id: agent.branch_id, agent_id: agent.agent_id, since: seen.withSince + TEAM_ENTRY_MS });
    }
    result[branchId] = list.sort((a, b) => a.since - b.since || a.agent_id.localeCompare(b.agent_id)
      || a.branch_id.localeCompare(b.branch_id));
  }
  return result;
}

// Where each team of the displayed Branch works. Rooms and Fika groups are held first come: a team keeps the place it
// holds; a team at its desk takes the first free meeting room, otherwise the free Fika group with the lowest seat id.
// - list: the teams in formation order, with `count`, the number of current Contractors.
// - rooms: [{ id, seats }] meeting rooms in order; busy: room ids used by meetings.
// - groups: [{ id, seats }] Fika groups (seat indices of the Fika room, ascending); taken: Fika indices in use.
// - previous: the last result. Returns Map key -> { kind: "room", room, seats, extra } (seat indices of that room,
//   the colleague's first), { kind: "fika", group, seats, extra } (Fika indices), or { kind: "desk" }.
export function placeTeams(list, { rooms, busy, groups, taken, previous }) {
  const placed = new Map(), usedRooms = new Set(busy), usedGroups = new Set();
  const seatsFor = (count, free) => {
    const seats = free.slice(0, 1 + count);
    return { seats, extra: count - (seats.length - 1) };
  };
  const roomPlace = (team, room) => ({ kind: "room", room: room.id, ...seatsFor(team.count, room.seats) });
  const groupPlace = (team, group) => ({ kind: "fika", group: group.id,
    ...seatsFor(team.count, group.seats.filter((index) => !taken.has(index))) });
  // Holdings first, so a newer team never takes a place held by an older or longer-standing one.
  for (const team of list) {
    const last = previous?.get(team.key);
    if (last?.kind === "room" && !usedRooms.has(last.room)) {
      const room = rooms.find((item) => item.id === last.room);
      if (room) { placed.set(team.key, roomPlace(team, room)); usedRooms.add(room.id); }
    } else if (last?.kind === "fika" && !usedGroups.has(last.group)) {
      // The held places are kept out of Fika allocation, so they are still free.
      const group = groups.find((item) => item.id === last.group);
      if (group) { placed.set(team.key, groupPlace(team, group)); usedGroups.add(group.id); }
    }
  }
  for (const team of list) {
    if (placed.has(team.key)) continue;
    const room = rooms.find((item) => !usedRooms.has(item.id));
    if (room) { placed.set(team.key, roomPlace(team, room)); usedRooms.add(room.id); continue; }
    // A free group has none of its places in use and seats the colleague with at least one Contractor.
    const group = groups.filter((item) => !usedGroups.has(item.id) && item.seats.length >= 2
      && item.seats.every((index) => !taken.has(index))).sort((a, b) => a.seats[0] - b.seats[0])[0];
    if (group) { placed.set(team.key, groupPlace(team, group)); usedGroups.add(group.id); continue; }
    placed.set(team.key, { kind: "desk" });
  }
  return placed;
}
