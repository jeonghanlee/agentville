// AgentVille Dashboard: renders HQ state from /ws/v1/live.
// All Branch-provided text is untrusted and is written with textContent only.

const token = new URLSearchParams(location.hash.slice(1)).get("token");
const STATE_LABEL = {
  working: "WORKING", thinking: "THINKING", waiting: "WAITING", idle: "IDLE",
  completed: "COMPLETED", error: "ERROR", limited: "LIMITED", unknown: "UNKNOWN",
};
const PROVIDER_COLOR = { claude: "var(--claude)", codex: "var(--codex)" };

let current = null;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "style") Object.assign(node.style, value);
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function text(id, value) {
  document.getElementById(id).textContent = value;
}

function minutesSince(iso, now) {
  return Math.max(0, Math.floor((now - Date.parse(iso)) / 60000));
}

function duration(minutes) {
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
  return `${Math.floor(minutes / 1440)} d`;
}

function clock(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function idleDetail(activity, thresholds, now) {
  const seconds = (now - Date.parse(activity.state_since)) / 1000;
  if (seconds >= thresholds.lounge) return "fika";
  if (seconds >= thresholds.doze) return "dozing";
  if (seconds >= thresholds.phone) return "phone";
  return "at desk";
}

function buildRows(state, now) {
  const branches = new Map(state.branches.map((b) => [b.branch_id, b]));
  const activities = new Map(state.activities.map((a) => [`${a.branch_id}/${a.agent_id}`, a]));
  const contractors = new Map();
  for (const c of state.contractors) {
    contractors.set(c.parent_instance_id, (contractors.get(c.parent_instance_id) || 0) + 1);
  }
  return state.agents.map((agent) => {
    const branch = branches.get(agent.branch_id);
    const reachable = branch ? branch.reachable : false;
    const thresholds = (branch && branch.branch && branch.branch.thresholds) || { phone: 300, doze: 1800, lounge: 3600 };
    const activity = activities.get(`${agent.branch_id}/${agent.agent_id}`);
    const onDuty = agent.presence === "on_duty";
    let state_ = onDuty && activity ? activity.state : null;
    if (onDuty && !reachable) state_ = "unknown";
    let detail = "";
    if (state_ === "idle" && activity) detail = idleDetail(activity, thresholds, now);
    if (state_ === "waiting" && activity) detail = duration(minutesSince(activity.state_since, now));
    const presence = { on_duty: "On duty", off_duty: "Off duty", on_leave: "On leave" }[agent.presence] || agent.presence;
    const since = onDuty && activity ? activity.state_since : agent.presence_since;
    return {
      branchAlias: (branch && branch.branch && branch.branch.alias) || agent.branch_id,
      reachable,
      agent,
      activity,
      state: state_,
      detail,
      presence: onDuty && !reachable ? "On duty (unverified)" : presence,
      since,
      contractors: activity ? contractors.get(activity.instance_id) || 0 : 0,
    };
  });
}

function render() {
  if (!current) return;
  const now = Date.now();
  const rows = buildRows(current, now);
  const showOff = document.getElementById("show-off").checked;
  const query = document.getElementById("search").value.trim().toLowerCase();

  const reachable = current.branches.filter((b) => b.reachable).length;
  text("c-branches", current.branches.length);
  text("c-branches-sub", `${reachable} reachable · ${current.branches.length - reachable} unreachable`);
  const onDuty = rows.filter((r) => r.agent.presence === "on_duty");
  const byProvider = {};
  for (const r of onDuty) byProvider[r.agent.provider] = (byProvider[r.agent.provider] || 0) + 1;
  text("c-duty", onDuty.length);
  text("c-duty-sub", Object.entries(byProvider).map(([p, n]) => `${n} ${p}`).join(" · ") || "nobody");
  const waiting = rows.filter((r) => r.state === "waiting");
  const sick = rows.filter((r) => r.state === "error");
  text("c-waiting", waiting.length);
  text("c-waiting-sub", waiting.map((r) => `${r.agent.provider} · ${r.agent.project_alias}`).join(", "));
  text("c-error", sick.length);
  text("c-error-sub", sick.map((r) => `${r.agent.provider} · ${r.agent.project_alias}`).join(", "));

  const alerts = document.getElementById("alerts");
  const alertItems = [];
  for (const r of waiting) {
    alertItems.push(el("li", {}, el("span", { class: "tag s-waiting" }, "WAITING"),
      `${r.agent.provider} seat ${r.agent.seat} in ${r.agent.project_alias} is waiting for you`,
      el("span", { class: "time" }, `${r.branchAlias} · ${clock(r.since)}`)));
  }
  for (const r of sick) {
    alertItems.push(el("li", {}, el("span", { class: "tag s-error" }, "ERROR"),
      `${r.agent.provider} seat ${r.agent.seat} in ${r.agent.project_alias} moved to the infirmary`,
      el("span", { class: "time" }, `${r.branchAlias} · ${clock(r.since)}`)));
  }
  for (const b of current.branches.filter((x) => !x.reachable)) {
    const alias = (b.branch && b.branch.alias) || b.branch_id;
    alertItems.push(el("li", {}, el("span", { class: "tag s-unknown" }, "BRANCH"),
      `${alias} is unreachable — last contact ${duration(minutesSince(b.last_seen_at, now))} ago`));
  }
  alerts.replaceChildren(...(alertItems.length ? alertItems : [el("li", { class: "empty" }, "No alerts.")]));

  const order = { on_duty: 0, off_duty: 1, on_leave: 2 };
  const visible = rows
    .filter((r) => showOff || r.agent.presence === "on_duty")
    .filter((r) => {
      if (!query) return true;
      const hay = [r.branchAlias, r.agent.project_alias, r.agent.provider, r.activity && r.activity.tool, r.state]
        .filter(Boolean).join(" ").toLowerCase();
      return hay.includes(query);
    })
    .sort((a, b) => (order[a.agent.presence] - order[b.agent.presence])
      || a.branchAlias.localeCompare(b.branchAlias)
      || a.agent.project_alias.localeCompare(b.agent.project_alias)
      || a.agent.provider.localeCompare(b.agent.provider)
      || a.agent.seat - b.agent.seat);

  const body = document.getElementById("rows");
  if (!visible.length) {
    body.replaceChildren(el("tr", { class: "empty-row" }, el("td", { colspan: "8" }, "No Employees to show.")));
    return;
  }
  body.replaceChildren(...visible.map((r) => {
    const cls = r.agent.presence === "on_leave" ? "faint" : (r.agent.presence === "off_duty" || !r.reachable ? "dim" : "");
    const stateKey = r.state || "none";
    const label = r.state ? STATE_LABEL[r.state] || r.state.toUpperCase() : "—";
    return el("tr", { class: cls },
      el("td", {}, `${r.branchAlias} / ${r.agent.project_alias}`),
      el("td", { class: "name" },
        el("span", { class: "swatch", style: { background: PROVIDER_COLOR[r.agent.provider] || "var(--faint)" }, "aria-hidden": "true" }),
        `${r.agent.alias || r.agent.provider} · seat ${r.agent.seat}`,
        r.contractors ? el("span", { class: "contractors" }, `+${r.contractors} contractor`) : null),
      el("td", {}, r.presence),
      el("td", {}, el("span", { class: `tag s-${stateKey}` }, label), r.detail ? ` ${r.detail}` : ""),
      el("td", { class: "mono" }, (r.activity && r.activity.tool) || "—"),
      el("td", {}, r.agent.presence === "on_duty" ? r.agent.condition : "—"),
      el("td", { class: "mono" }, r.activity && r.agent.presence === "on_duty" ? `${r.activity.workload ?? 0} / 5 min` : "—"),
      el("td", { class: "mono" }, r.agent.presence === "on_leave" ? duration(minutesSince(r.since, now)) : clock(r.since)));
  }));
}

function connect(delay = 1000) {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  const socket = new WebSocket(`${scheme}://${location.host}/ws/v1/live${query}`);
  const status = document.getElementById("connection");
  socket.addEventListener("open", () => {
    status.textContent = "live";
    status.classList.add("live");
    delay = 1000;
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "state") {
      current = message.state;
      render();
    }
  });
  socket.addEventListener("close", () => {
    status.textContent = "reconnecting…";
    status.classList.remove("live");
    setTimeout(() => connect(Math.min(delay * 2, 30000)), delay);
  });
}

document.getElementById("search").addEventListener("input", render);
document.getElementById("show-off").addEventListener("change", render);
setInterval(render, 30000);
connect();
