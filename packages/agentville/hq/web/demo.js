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
    ["otto", "Otto", "home", "garden-ui", "codex", "idle", 2460, "", "light"],
    ["noah", "Noah", "home", "common-office", "codex", "working", 32, "exec_command", "normal"],
    ["luna", "Luna", "home", "agentville", "claude", "idle", 4000, "", "extra-coffee"],
    ["pip", "Pip", "home", "garden-ui", "codex", "idle", 5200, "", "lazy"],
    ["remy", "Remy", "home", "garden-ui", "claude", "error", 540, "", "normal"],
    ["wren", "Wren", "home", "common-office", "claude", "limited", 900, "", "normal"],
  ];
  const seats = new Map();
  const agents = people.map(([id, alias, host, project, provider, , , , condition]) => {
    const key = [host, project, provider].join("/");
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
