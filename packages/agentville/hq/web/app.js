// Branch-provided strings are rendered through text nodes, never as markup.
import { icon, character, avatarColor, prepareAppearances } from "./art.js";
import { demoState } from "./demo.js";
import { updateWorkGestures, WORK_MOTION_INTERVAL } from "./motion.js";
import { createOfficeCats } from "./cats.js";
import { mountFurniture } from "./furniture.js";
import { createDaylight } from "./daylight.js";
import { SEATED_WIDTH } from "./sprites.js";
import { createCoffeeBreaks } from "./coffee.js";

const DEMO = new URLSearchParams(location.search).get("demo") === "1";
const TOKEN = takeToken();
const COMMON = "common-office";
const STATES = {
  working: "Working", thinking: "Thinking", waiting: "Waiting", idle: "Idle",
  completed: "Done", error: "Error", limited: "Limited", unknown: "Unknown",
};
const PRESENCE = { on_duty: "On duty", off_duty: "Off duty", on_leave: "On leave" };
const CONDITIONS = { normal: "Feeling good", "extra-coffee": "Extra coffee", "study-mode": "Study mode", lazy: "Taking it easy" };
const VIEWS = [
  ["office", "Virtual office", "house", "A good day to build.", "Different minds. Shared space. Good things in the making."],
  ["dashboard", "Dashboard", "grid", "The bigger picture.", "A clear view of the work happening across your branches."],
  ["employees", "Employees", "people", "Meet your little team.", "Every teammate, every project, all in one place."],
  ["projects", "Projects", "folder", "Room for good ideas.", "One project, one room. A place for every kind of work."],
  ["timeline", "Timeline", "clock", "Life around the office.", "Current activity and changes observed during this visit."],
  ["branches", "Branches", "branches", "A world of little offices.", "Different places, connected through one workspace."],
  ["settings", "Settings", "settings", "", ""],
];
const ROOM_LAYOUT = {
  studio0: { color: "#adba88", seats: [[26.5,36.5,"back",38],[36,42,"back",44],[32.4,26.2,"front",25],[42.5,32.2,"front",30]], overflow: [44,47] },
  studio1: { color: "#b8a4c8", seats: [[75.2,37.8,"back",41],[83.8,43.4,"back",47]], overflow: [76,50] },
  common: { color: "#c8b994", seats: [[13.3,59.7,"back",62],[21.8,64.4,"back",67]], overflow: [28,63] },
  fika: { color: "#d1a178", seats: [[49.5,66.9,"front",70],[58.7,80.6,"back-left",82],[56.7,70.6,"front",73]], overflow: [48,85] },
  infirmary: { color: "#93b7a6", seats: [[85.9,63.5,"lying",74]], overflow: [87,82] },
};
const WORKSTATIONS = {
  studio0: [[[397,325],[417,332],[438,333]], [[548,374],[570,381],[599,387]], [[478,265],[495,271],[515,280]], [[622,316],[641,325],[663,333]]],
  studio1: [[[1148,341],[1169,350],[1191,353]], [[1275,391],[1296,401],[1320,411]]],
  common: [[[196,556],[216,566],[241,573]], [[329,607],[351,616],[377,624]]],
};
const WAITING_SPOTS = {
  fika: [[34,79],[40,84],[46,89],[52,94],[65,82],[60,89]],
  infirmary: [[78,81],[84,78],[73,84],[78,87]],
};
const EMPTY = { branches: [], agents: [], activities: [], contractors: [] };
const MAX_EVENTS = 60;
const MIN_ZOOM = 100, MAX_ZOOM = 175, ZOOM_STEP = 25;
const $ = (id) => document.getElementById(id);
const keyOf = (branch, id) => JSON.stringify([branch, id]);
let current = EMPTY, connected = false, view = "office", branchId = "", floor = 0;
let stateFilter = "all", roomFilter = "", selected = "", zoom = 100;
let events = [], eventKeys = new Set(), reconnectTimer = null, activeSocket = null, everOpened = false, failedOpens = 0;
const actors = new Map();
const companions = new Map();
const facilityOccupancy = new Map();
let daylight = null;
let furniture = null;
let coffee = null;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "style") {
      for (const [name, style] of Object.entries(value)) {
        if (name.startsWith("--")) node.style.setProperty(name, style); else node.style[name] = style;
      }
    }
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
// The viewer token leaves the address bar so it is not shared, bookmarked, or kept in history.
function takeToken() {
  const hash = new URLSearchParams(location.hash.slice(1));
  if (!hash.has("token")) {
    try { return sessionStorage.getItem("agentville-viewer-token"); } catch { return null; }
  }
  const token = hash.get("token");
  try { sessionStorage.setItem("agentville-viewer-token", token); } catch {}
  hash.delete("token");
  const rest = hash.toString();
  history.replaceState(history.state, "", location.pathname + location.search + (rest ? "#" + rest : ""));
  return token;
}
function projectRoom(id) { return "project:" + id; }
function button(label, cls, fn, attrs = {}) {
  const node = el("button", { type: "button", class: cls, ...attrs }, label);
  node.addEventListener("click", fn);
  return node;
}
function text(id, value) { $(id).textContent = value; }
function color(state) { return "var(--" + (Object.hasOwn(STATES, state) ? state : "idle") + ")"; }
function badge(provider) {
  return el("span", { class: "provider" + (provider === "codex" ? " codex" : "") },
    provider === "claude" ? "CL" : provider === "codex" ? "CX" : String(provider).slice(0, 2).toUpperCase());
}
function age(iso, compact = true) {
  const seconds = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (!Number.isFinite(seconds)) return "-";
  if (seconds < 60) return compact ? "now" : "just now";
  if (seconds < 3600) return Math.floor(seconds / 60) + (compact ? "m" : " min ago");
  if (seconds < 86400) return Math.floor(seconds / 3600) + (compact ? "h" : " hr ago");
  return Math.floor(seconds / 86400) + (compact ? "d" : " days ago");
}
function idleDetail(activity, branch) {
  const seconds = Math.max(0, (Date.now() - Date.parse(activity?.state_since)) / 1000);
  const thresholds = { phone: 300, doze: 1800, lounge: 3600, ...branch?.branch?.thresholds };
  if (seconds >= thresholds.lounge) return "fika";
  if (seconds >= thresholds.doze) return "dozing";
  if (seconds >= thresholds.phone) return "phone";
  return "at desk";
}
function rows() {
  const branches = new Map(current.branches.map((b) => [b.branch_id, b]));
  const activities = new Map(current.activities.map((a) => [keyOf(a.branch_id, a.agent_id), a]));
  return current.agents.map((agent) => {
    const branch = branches.get(agent.branch_id);
    const activity = activities.get(keyOf(agent.branch_id, agent.agent_id));
    const duty = agent.presence === "on_duty";
    const verified = (DEMO || connected) && Boolean(branch?.reachable);
    const state = duty ? (activity && Object.hasOwn(STATES, activity.state) ? activity.state : "unknown") : "idle";
    const detail = state === "idle" && duty ? idleDetail(activity, branch) : "";
    const contractors = current.contractors.filter((c) =>
      c.branch_id === agent.branch_id && c.parent_instance_id === agent.instance?.instance_id && c.status !== "ended");
    return {
      key: keyOf(agent.branch_id, agent.agent_id), agent, branch, activity, state, detail, duty, verified, contractors,
      name: agent.alias || (agent.provider === "claude" ? "Claude" : agent.provider === "codex" ? "Codex" : agent.provider) + " " + agent.seat,
      branchName: branch?.branch?.alias || "Unnamed branch",
      project: agent.project_alias || "Untitled project",
      since: duty && activity ? activity.state_since : agent.presence_since,
    };
  }).sort((a,b) => a.agent.project_id.localeCompare(b.agent.project_id) || a.agent.seat - b.agent.seat || a.key.localeCompare(b.key));
}
function roomOf(row) {
  if (row.state === "error") return "infirmary";
  if (row.detail === "fika") return "fika";
  return row.agent.project_id === COMMON ? "common" : projectRoom(row.agent.project_id);
}
function queryMatches(row) {
  const query = $("search").value.trim().toLowerCase();
  return !query || [row.name, row.project, row.agent.provider, row.branchName, STATES[row.state],
    row.state === "working" ? row.activity?.tool : ""].filter(Boolean).join(" ").toLowerCase().includes(query);
}
function passes(row) {
  return queryMatches(row) && (stateFilter === "all" || stateFilter === row.state) && (!roomFilter || roomFilter === roomOf(row));
}
function context(all) {
  const local = all.filter((r) => r.agent.branch_id === branchId);
  const projects = [...new Map(local.filter((r) => r.agent.project_id !== COMMON).map((r) =>
    [r.agent.project_id, { id: r.agent.project_id, name: r.project }])).values()].sort((a,b) => a.name.localeCompare(b.name));
  floor = Math.min(floor, Math.max(0, Math.ceil(projects.length / 2) - 1));
  const page = projects.slice(floor * 2, floor * 2 + 2);
  const ids = new Set(projects.map((p) => p.id));
  const present = all.filter((r) => r.duty && (r.agent.branch_id === branchId || ids.has(r.agent.project_id)));
  const pageIds = new Set(page.map((p) => p.id));
  const office = present.filter((r) => pageIds.has(r.agent.project_id)
    || ["common", "fika", "infirmary"].includes(roomOf(r)));
  return { local, projects, page, present, office };
}
function stateLabel(row) {
  const label = !row.duty ? PRESENCE[row.agent.presence] || row.agent.presence
    : row.detail === "fika" ? "Fika" : row.detail === "phone" ? "On a break"
    : row.detail === "dozing" ? "Dozing" : STATES[row.state];
  const unverified = row.duty && !row.verified;
  return el("span", { class: "state-label" + (unverified ? " unverified" : ""), style: { "--state-color": color(row.state) },
    ...(unverified ? { title: "Unverified: last observed " + label } : {}) },
    el("i", { class: "status-dot" }), label, unverified ? el("span", { class: "unverified-mark", "aria-hidden": "true" }, "?") : null,
    unverified ? el("span", { class: "sr-only" }, " (unverified)") : null);
}
function countBadge(list) {
  return el("b", list.some((r) => r.duty && !r.verified) ? { class: "unverified-count" } : {}, list.length);
}
function avatar(row) {
  return el("span", { class: "avatar", style: { "--avatar-color": avatarColor(row.key) } },
    character(row.key, "idle", "", row.agent.condition));
}
function selectEmployee(key) {
  const all = rows();
  const row = all.find((r) => r.key === key);
  if (row && !["common", "fika", "infirmary"].includes(roomOf(row))) {
    const index = context(all).projects.findIndex((p) => p.id === row.agent.project_id);
    if (index >= 0) floor = Math.floor(index / 2);
  }
  selected = key;
  render();
}
function focusKey() { return document.activeElement?.dataset?.focusKey; }
function restoreFocus(key) {
  if (!key) return;
  const match = [...document.querySelectorAll("[data-focus-key]")].find((n) => n.dataset.focusKey === key);
  match?.focus({ preventScroll: true });
}

function renderFilters(ctx) {
  const states = ["all", "working", "thinking", "waiting", "idle", "error"];
  for (const s of ["limited", "unknown", "completed"]) {
    if (ctx.present.some((r) => r.state === s) || stateFilter === s) states.push(s);
  }
  $("filters").replaceChildren(...states.map((s) => button([
    s === "all" ? null : el("i", { class: "status-dot", style: { background: color(s) } }),
    s === "all" ? "Everyone" : STATES[s],
    countBadge(ctx.present.filter((r) => s === "all" || r.state === s)),
  ], "filter", () => { stateFilter = s; render(); },
  { "aria-pressed": String(s === stateFilter), "data-focus-key": "filter-" + s, "data-filter": s })));
}
function renderRooms(ctx) {
  const rooms = ctx.page.map((p,i) => ({ ...p, id: projectRoom(p.id), color: ROOM_LAYOUT["studio" + i].color }));
  rooms.push({ id: "common", name: "Common office", color: ROOM_LAYOUT.common.color },
    { id: "fika", name: "Fika lounge", color: ROOM_LAYOUT.fika.color },
    { id: "infirmary", name: "Infirmary", color: ROOM_LAYOUT.infirmary.color });
  $("rooms").replaceChildren(...rooms.map((room) => button([
    el("i", { class: "room-square", style: { "--room-color": room.color } }), room.name,
    countBadge(ctx.present.filter((r) => roomOf(r) === room.id)),
  ], "room-tab", () => { roomFilter = roomFilter === room.id ? "" : room.id; render(); },
  { "aria-pressed": String(roomFilter === room.id), "data-focus-key": "room-" + room.id })));
  const count = Math.max(1, Math.ceil(ctx.projects.length / 2));
  $("floor-controls").hidden = count <= 1;
  text("floor-label", (floor + 1) + " / " + count);
  $("previous-floor").disabled = floor === 0;
  $("next-floor").disabled = floor >= count - 1;
}
function renderCharacters(ctx) {
  const groups = new Map();
  for (const row of ctx.office) {
    let room = roomOf(row);
    const projectIndex = ctx.page.findIndex((p) => projectRoom(p.id) === room);
    if (projectIndex !== -1) room = "studio" + projectIndex;
    if (!Object.hasOwn(ROOM_LAYOUT, room)) continue;
    if (!groups.has(room)) groups.set(room, []);
    groups.get(room).push(row);
  }
  // Reserve facility seats until departure; insertion order keeps the waiting line stable.
  for (const room of Object.keys(WAITING_SPOTS)) {
    const id = keyOf(branchId,room);
    if (!facilityOccupancy.has(id)) facilityOccupancy.set(id,new Map());
    const occupants = facilityOccupancy.get(id);
    const people = groups.get(room) || [];
    const members = new Set(people.map((row) => row.key));
    for (const key of occupants.keys()) if (!members.has(key)) occupants.delete(key);
    for (const row of people) if (!occupants.has(row.key)) occupants.set(row.key,null);
    const occupied = new Set([...occupants.values()].filter((index) => index !== null));
    for (const [key,index] of occupants) {
      if (index !== null) continue;
      const free = ROOM_LAYOUT[room].seats.findIndex((_,i) => !occupied.has(i));
      if (free < 0) break;
      occupants.set(key,free); occupied.add(free);
    }
  }
  const lounge = facilityOccupancy.get(keyOf(branchId,"fika"));
  coffee?.sync([...lounge].filter(([,index]) => index !== null)
    .map(([key,index]) => [key,ROOM_LAYOUT.fika.seats[index]]),branchId);
  const used = new Set();
  $("characters").querySelectorAll(".room-overflow").forEach((n) => n.remove());
  for (const [room, people] of groups) {
    const layout = ROOM_LAYOUT[room];
    const occupants = facilityOccupancy.get(keyOf(branchId,room));
    const waiting = occupants ? [...occupants].filter(([,index]) => index === null).map(([key]) => key) : [];
    const shownWaiting = waiting.slice(0,WAITING_SPOTS[room]?.length || 0);
    if (waiting.includes(selected) && !shownWaiting.includes(selected)) shownWaiting[shownWaiting.length-1] = selected;
    const placed = people.map((row,i) => ({ row, index: occupants ? occupants.get(row.key) : i }))
      .filter(({ row,index }) => index === null ? shownWaiting.includes(row.key) : index < layout.seats.length);
    placed.forEach(({ row,index }) => {
      let node = actors.get(row.key);
      if (!node) {
        node = button("", "agent", () => selectEmployee(row.key), { "data-focus-key": "actor-" + row.key });
        actors.set(row.key, node);
        $("characters").append(node);
      }
      used.add(row.key);
      node.dataset.employeeKey = row.key;
      const visible = passes(row);
      const condition = Object.hasOwn(CONDITIONS, row.agent.condition) ? row.agent.condition : "normal";
      node.className = ["agent", row.state, row.detail, condition, row.verified ? "" : "unverified",
        selected === row.key ? "selected" : "", visible ? "" : "filtered"].join(" ");
      node.setAttribute("aria-label", row.name + ", " + STATES[row.state] + (row.verified ? "" : " (unverified)") + ", " + row.project);
      node.setAttribute("aria-pressed", String(row.key === selected));
      node.tabIndex = visible ? 0 : -1;
      const visit = coffee?.get(row.key);
      const waitingIndex = shownWaiting.indexOf(row.key);
      const spot = waitingIndex >= 0 ? WAITING_SPOTS[room][waitingIndex] : null;
      const seat = visit?.seat || (spot ? [...spot,"standing",Math.floor(spot[1])+1] : layout.seats[index]);
      const desk = seat[2];
      node.classList.add(visit ? "coffee-standing" : spot ? "standing" : desk === "lying" ? "reclining" : "seated");
      node.dataset.room = room;
      node.dataset.seatFacing = desk;
      node.dataset.coffeePhase = visit?.phase || "";
      node.dataset.coffeeFacing = visit?.facing || "";
      node.dataset.queuePosition = spot ? String(waiting.indexOf(row.key)+1) : "";
      node.dataset.seatIndex = index === null ? "" : String(index);
      node.style.width = desk === "lying" ? "8%" : SEATED_WIDTH + "%";
      node.style.left = seat[0] + "%";
      node.style.top = seat[1] + "%";
      node.style.zIndex = String(seat[3]);
      // Keep unchanged SVG nodes alive so data refreshes do not restart gestures.
      const workstation = WORKSTATIONS[room]?.[index] ? { seat, keys: WORKSTATIONS[room][index] } : null;
      const cup = coffee?.cup(row.key);
      const detail = visit ? visit.cup ? "coffee-cup" : visit.phase === "waiting" ? "coffee-wait" : "coffee-walk" : row.detail;
      const appearance = JSON.stringify([row.state, detail, condition, desk, workstation, cup, node.dataset.queuePosition, row.contractors.length,
        row.name, row.agent.provider, row.branchName, row.agent.branch_id === branchId]);
      if (node.dataset.appearance !== appearance) {
        const name = el("span", { class: "agent-name" }, badge(row.agent.provider), row.name,
          row.agent.branch_id === branchId ? null : el("span", { class: "remote-badge" }, row.branchName));
        const children = [character(row.key, row.state, detail, condition, false, desk, workstation, cup),
          name, el("span", { class: "agent-signal", style: { background: color(row.state) } })];
        if (visit?.phase === "waiting") children.push(el("span", { class: "coffee-status" }, "Brewing..."));
        if (spot) children.push(el("span", { class: "queue-status" },
          (room === "infirmary" ? "Waiting for bed" : "Waiting for seat") + " / " + node.dataset.queuePosition));
        node.replaceChildren(...children);
        node.dataset.appearance = appearance;
      }
      if (row.contractors.length) {
        let companion = companions.get(row.key);
        if (!companion) {
          companion = button("", "contractor", () => selectEmployee(row.key), { "data-parent-key": row.key });
          companions.set(row.key,companion);
          $("characters").append(companion);
        }
        companion.className = "contractor working" + (visible ? "" : " filtered");
        companion.setAttribute("aria-label", row.name + ", " + row.contractors.length + " contractors");
        companion.tabIndex = visible ? 0 : -1;
        const foot = desk === "lying" ? [seat[0]+4.2,seat[1]+13]
          : [seat[0]+3.1,seat[1]+(visit || spot ? 0 : desk.startsWith("back") ? 2.2 : 3.6)];
        companion.style.left = foot[0] + "%";
        companion.style.top = foot[1] + "%";
        companion.style.zIndex = String(Math.floor(foot[1])+1);
        const appearance = String(row.contractors.length);
        if (companion.dataset.appearance !== appearance) {
          companion.replaceChildren(character(row.key + "helper", "working", "", "normal", true, "standing"));
          if (row.contractors.length > 1) companion.append(el("small", {}, "+" + row.contractors.length));
          companion.dataset.appearance = appearance;
        }
      } else if (companions.has(row.key)) {
        companions.get(row.key).remove(); companions.delete(row.key);
      }
    });
    if (people.length > placed.length) {
      const overflow = button("+" + (people.length - placed.length), "room-overflow", () => {
        roomFilter = room.startsWith("studio") ? projectRoom(ctx.page[Number(room.slice(-1))].id) : room;
        render();
      }, { "aria-label": "Show all teammates in this room" });
      overflow.style.left = layout.overflow[0] + "%";
      overflow.style.top = layout.overflow[1] + "%";
      $("characters").append(overflow);
    }
  }
  for (const [key,node] of actors) {
    if (!used.has(key)) { node.remove(); actors.delete(key); }
  }
  for (const [key,node] of companions) {
    if (!used.has(key)) { node.remove(); companions.delete(key); }
  }
  updateWorkGestures($("characters"));
}

function renderTeam(ctx) {
  const list = ctx.present.filter(passes);
  text("team-count", list.length);
  $("team-list").replaceChildren(...(list.length ? list.map((row) =>
    button([avatar(row), el("span", { class: "teammate-main" },
      el("span", { class: "teammate-name" }, el("span", {}, row.name), badge(row.agent.provider)),
      el("span", { class: "teammate-project" }, row.project + (row.agent.branch_id === branchId ? "" : " / " + row.branchName))),
    el("span", { class: "teammate-state" }, stateLabel(row), el("time", { datetime: row.since }, age(row.since)))],
    "teammate", () => selectEmployee(row.key),
    { "aria-pressed": String(row.key === selected), "data-focus-key": "team-" + row.key }))
    : [el("div", { class: "empty-list" }, ctx.present.length ? "No teammates match this view." : "A quiet moment in the office.")]));
  const row = ctx.present.find((r) => r.key === selected);
  if (!row) {
    $("employee-detail").replaceChildren(el("p", { class: "detail-eyebrow" }, "A LITTLE HELLO"),
      el("p", { class: "detail-note" }, "Choose a teammate to see how their day is going."));
    return;
  }
  const stats = [["Status", !row.verified ? "Unverified (" + STATES[row.state] + ")" : STATES[row.state]], ["Condition", CONDITIONS[row.agent.condition] || row.agent.condition],
    ["Tool", row.state === "working" ? row.activity?.tool || "-" : "-"],
    ["Workload", row.verified ? (row.activity?.workload ?? 0) + " / 5 min" : "-"]];
  const occupants = facilityOccupancy.get(keyOf(branchId,roomOf(row)));
  const waiting = occupants?.get(row.key) === null;
  if (waiting) stats.push(["Place", "Waiting for " + (roomOf(row) === "infirmary" ? "bed" : "seat")]);
  $("employee-detail").replaceChildren(el("p", { class: "detail-eyebrow" }, "IN THEIR LITTLE CORNER"),
    el("div", { class: "detail-top" }, avatar(row), el("div", {}, el("strong", {}, row.name), el("small", {}, row.project + " / " + row.branchName))),
    el("dl", { class: "detail-grid" }, ...stats.map(([name,value]) => el("div", {}, el("dt", {}, name), el("dd", {}, value)))),
    el("p", { class: "detail-note" }, !row.verified ? "Last seen like this. Waiting for a fresh update."
      : row.state === "waiting" ? "A little help from you, and we're off."
      : row.detail === "fika" ? "Good ideas need a coffee break, too." : row.state === "error" ? "A little rest in the infirmary."
      : row.state === "unknown" ? "Waiting for a fresh update." : row.agent.condition === "extra-coffee" ? "Powered by a little extra coffee." : "Quietly making good things happen."));
}
function eventNode(event) {
  const symbol = { working: "spark", thinking: "spark", waiting: "hand", idle: "coffee", error: "heart", completed: "check", unknown: "branches", limited: "clock" }[event.state] || "clock";
  return el("div", { class: "event" }, el("span", { class: "event-icon" }, icon(symbol)),
    el("div", {}, el("p", {}, el("strong", {}, event.name), " " + event.label),
      el("small", {}, event.project + " / " + age(event.at, false))));
}
function visibleEvents() {
  const q = $("search").value.trim().toLowerCase();
  return events.filter((e) => !q || [e.name,e.project,e.label].join(" ").toLowerCase().includes(q));
}
function recordEvents(all) {
  for (const row of all) {
    const key = JSON.stringify([row.key,row.agent.presence,row.activity?.state,row.since]);
    if (eventKeys.has(key)) continue;
    eventKeys.add(key);
    const label = !row.duty ? "is " + PRESENCE[row.agent.presence]?.toLowerCase() + "."
      : { working: "is making things happen.", thinking: "is thinking it through.", waiting: "is waiting for you.",
        idle: "is taking a breather.", error: "is in the infirmary.", limited: "is waiting for a reset.",
        unknown: "has an unverified status.", completed: "finished a turn." }[row.state];
    events.push({ name: row.name, project: row.project, state: row.state, label, at: row.since });
  }
  events.sort((a,b) => Date.parse(b.at) - Date.parse(a.at));
  events = events.slice(0, MAX_EVENTS);
  if (eventKeys.size > 1000) eventKeys = new Set(all.map((r) => JSON.stringify([r.key,r.agent.presence,r.activity?.state,r.since])));
}
function employeeTable(all) {
  const heading = ["Branch / Room", "Employee", "Presence", "Activity", "Tool", "Condition", "Workload", "Since"];
  const body = all.filter(queryMatches).map((r) => el("tr", {},
    el("td", {}, r.branchName, el("br"), r.project),
    el("td", {}, badge(r.agent.provider), r.name, r.contractors.length ? " +" + r.contractors.length : ""),
    el("td", {}, r.duty && !r.verified ? "On duty (unverified)" : PRESENCE[r.agent.presence]),
    el("td", {}, stateLabel(r)), el("td", {}, r.state === "working" ? r.activity?.tool || "-" : "-"),
    el("td", {}, r.duty ? CONDITIONS[r.agent.condition] || r.agent.condition : "-"),
    el("td", {}, r.duty && r.verified ? (r.activity?.workload ?? 0) + " / 5 min" : "-"),
    el("td", {}, age(r.since, false))));
  return el("div", { class: "data-card" }, el("h2", {}, "Your teammates"),
    el("div", { class: "table-scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, heading.map((h) => el("th", { scope: "col" }, h)))),
      el("tbody", {}, body.length ? body : el("tr", {}, el("td", { colspan: 8 }, "No teammates match this view."))))));
}
function renderData(all) {
  const root = $("data-view");
  if (view === "employees") root.replaceChildren(employeeTable(all));
  if (view === "dashboard") {
    const metrics = [["Branches", current.branches], ["On duty", all.filter((r) => r.duty)],
      ["Waiting for you", all.filter((r) => r.duty && r.state === "waiting")], ["In the infirmary", all.filter((r) => r.duty && r.state === "error")]];
    root.replaceChildren(el("div", { class: "dashboard-summary" }, metrics.map(([title,list]) => {
      const unverified = list.some((r) => r.duty && !r.verified);
      return el("div", { class: "metric" + (unverified ? " unverified" : "") }, el("span", {}, title), el("strong", {}, list.length),
        unverified ? el("small", {}, "Unverified") : null);
    })), employeeTable(all));
  }
  if (view === "timeline") root.replaceChildren(el("div", { class: "data-card" }, el("h2", {}, "Recent activity"),
    el("div", { class: "timeline-list" }, visibleEvents().length ? visibleEvents().map(eventNode) : el("p", { class: "empty-list" }, "Activity will appear as teammates check in."))));
  if (view === "projects") {
    const projects = [...new Map(all.filter(queryMatches).map((r) => [r.agent.project_id, r.project])).entries()];
    root.replaceChildren(el("div", { class: "data-grid" }, projects.length ? projects.map(([id,name]) => {
      const members = all.filter((r) => r.agent.project_id === id);
      return el("article", { class: "project-card" }, icon("folder"), el("h2", {}, name),
        el("p", {}, members.filter((r) => r.duty).length + " on duty / " + new Set(members.map((r) => r.agent.branch_id)).size + " branches"),
        button("Visit room", "secondary-button", () => {
          branchId = members[0].agent.branch_id;
          const ctx = context(all);
          const index = ctx.projects.findIndex((p) => p.id === id);
          floor = Math.max(0, Math.floor(index / 2));
          roomFilter = id === COMMON ? "common" : projectRoom(id); stateFilter = "all";
          setView("office");
        }));
    }) : el("p", { class: "empty-list" }, "Projects appear when a teammate checks in.")));
  }
  if (view === "branches") {
    const query = $("search").value.trim().toLowerCase();
    const branches = current.branches.filter((b) => !query || (b.branch?.alias || "").toLowerCase().includes(query));
    root.replaceChildren(el("div", { class: "data-grid" }, branches.length ? branches.map((b) =>
      el("article", { class: "branch-card" }, icon("house"), el("h2", {}, b.branch?.alias || "Unnamed branch"),
        el("p", {}, b.reachable && (DEMO || connected) ? "Connected to HQ" : "Connection unverified"),
        el("p", {}, all.filter((r) => r.agent.branch_id === b.branch_id && r.duty).length + " on duty / last contact " + age(b.last_seen_at, false)),
        button("Visit office", "secondary-button", () => { branchId = b.branch_id; floor = 0; roomFilter = ""; stateFilter = "all"; setView("office"); })))
      : el("p", { class: "empty-list" }, "No branches match this view.")));
  }
}
function updateClock() {
  const now = new Date();
  text("today", now.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }).toUpperCase());
  text("local-time", now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }));
  daylight?.update(now);
}
function render() {
  const focused = focusKey();
  const all = rows();
  prepareAppearances(all.flatMap((row) => row.contractors.length ? [row.key, row.key + "helper"] : [row.key]));
  if (!current.branches.some((b) => b.branch_id === branchId)) { branchId = current.branches[0]?.branch_id || ""; floor = 0; roomFilter = ""; }
  const ctx = context(all);
  const matching = ctx.present.filter(passes);
  const onFloor = ctx.office.filter(passes);
  if (!selected || !matching.some((r) => r.key === selected)) {
    selected = onFloor.find((r) => r.state === "working")?.key || onFloor[0]?.key || matching[0]?.key || "";
  }
  $("branch-select").replaceChildren(...(current.branches.length ? current.branches.map((b) =>
    el("option", { value: b.branch_id }, b.branch?.alias || "Unnamed branch")) : [el("option", { value: "" }, "Your office")]));
  $("branch-select").value = branchId;
  $("branch-select").disabled = !current.branches.length;
  const branch = current.branches.find((b) => b.branch_id === branchId);
  text("branch-subtitle", branch ? (branch.branch?.location || "A place for your team") : "Waiting for the first teammate");
  const available = branch?.reachable && (DEMO || connected);
  $("office-open").classList.toggle("unreachable", !available);
  $("office-open").replaceChildren(el("i", { class: "status-dot" }), available ? "Office is open" : "Office is quiet");
  const projects = new Set(all.filter((r) => r.agent.project_id !== COMMON).map((r) => r.agent.project_id));
  $("summary").replaceChildren(...[["people", all.filter((r) => r.duty).length, "on duty"],
    ["folder", projects.size, "projects"], ["branches", current.branches.length, "branches"]].map(([symbol,n,label]) =>
    el("span", { class: "summary-item" }, icon(symbol), el("strong", {}, n), label)));
  renderFilters(ctx); renderRooms(ctx); renderCharacters(ctx); renderTeam(ctx);
  $("scene-empty").hidden = ctx.present.length > 0;
  $("scene").classList.toggle("is-empty", ctx.present.length === 0);
  text("office-footer-text", ctx.present.length + " teammates / " + ctx.projects.length + " project rooms");
  $("recent-activity").replaceChildren(...(visibleEvents().length ? visibleEvents().slice(0,4).map(eventNode)
    : [el("p", { class: "empty-list" }, "Waiting for a little activity.")]));
  $("branch-statuses").replaceChildren(...current.branches.map((b) =>
    el("span", { class: "branch-status" + (b.reachable && (DEMO || connected) ? "" : " unreachable") },
      el("i", { class: "status-dot" }), b.branch?.alias || "Unnamed branch",
      el("time", { datetime: b.last_seen_at },
        (b.reachable && (DEMO || connected) ? "last contact " : "unverified / ") + age(b.last_seen_at)))));
  if (view !== "office") renderData(all);
  updateClock();
  restoreFocus(focused);
}
function setView(next) {
  if (next === "settings") { $("settings-dialog").showModal(); return; }
  const config = VIEWS.find(([id]) => id === next);
  if (!config) return;
  view = next;
  document.querySelectorAll(".nav-button").forEach((n) => {
    if (n.dataset.view === view) n.setAttribute("aria-current", "page"); else n.removeAttribute("aria-current");
  });
  text("breadcrumb-view", config[1]); text("page-title", config[3]); text("page-description", config[4]);
  text("page-eyebrow", view === "office" ? "WELCOME TO YOUR LITTLE WORLD" : "YOUR WORKSPACE, AT A GLANCE");
  $("office-view").hidden = view !== "office"; $("activity-card").hidden = view !== "office";
  $("data-view").hidden = view === "office";
  render();
}
function setConnection(label, cls) {
  $("connection").className = "connection " + cls;
  $("connection").replaceChildren(el("i", { class: "status-dot" }), label);
}
function acceptState(state) {
  if (!state || !["branches","agents","activities","contractors"].every((key) => Array.isArray(state[key]))) return false;
  current = state; connected = true; recordEvents(rows()); render(); return true;
}
function connect(delay = 1000) {
  if (DEMO) return;
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(scheme + "://" + location.host + "/ws/v1/live" + (TOKEN ? "?token=" + encodeURIComponent(TOKEN) : ""));
  activeSocket = socket;
  socket.addEventListener("open", () => { everOpened = true; failedOpens = 0; });
  socket.addEventListener("message", (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.type === "state" && acceptState(message.state)) {
        delay = 1000;
        setConnection("Live workspace", "live");
      }
    } catch { setConnection("Invalid update", "disconnected"); }
  });
  socket.addEventListener("close", (event) => {
    if (activeSocket !== socket) return;
    connected = false; render();
    if (event.code === 4401) { setConnection("Viewer token required", "disconnected"); return; }
    if (event.code === 4403) { setConnection("Connection refused by HQ", "disconnected"); return; }
    // A socket that never opens may be a rejected token or a wrong HQ address; keep retrying.
    if (!everOpened && ++failedOpens >= 5) setConnection("Can't reach HQ. Check the viewer token or address", "disconnected");
    else setConnection("Reconnecting", "disconnected");
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => connect(Math.min(delay * 2, 30000)), delay);
  });
}
function changeMode() {
  const url = new URL(location.href);
  if (DEMO) url.searchParams.delete("demo"); else url.searchParams.set("demo", "1");
  location.assign(url);
}
function labels(enabled) {
  $("world").classList.toggle("show-labels", enabled);
  $("labels-toggle").setAttribute("aria-pressed", String(enabled));
  $("labels-toggle").setAttribute("aria-label", enabled ? "Hide names until selected" : "Show all names");
  $("setting-labels").checked = enabled;
}
function changeZoom(value) {
  zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
  $("world").style.width = zoom + "%";
  text("zoom-reset", zoom + "%");
  $("zoom-out").disabled = zoom === MIN_ZOOM; $("zoom-in").disabled = zoom === MAX_ZOOM;
}
document.querySelectorAll("[data-icon]").forEach((node) => node.replaceChildren(icon(node.dataset.icon)));
$("navigation").replaceChildren(...VIEWS.map(([id,label,symbol]) =>
  button([icon(symbol), el("span", {}, label)], "nav-button", () => setView(id),
    { "data-view": id, "aria-label": label, title: label })));
document.querySelector(".brand").href = location.pathname + location.search + location.hash;
$("search").addEventListener("input", render);
$("branch-select").addEventListener("change", (event) => { branchId = event.target.value; floor = 0; roomFilter = ""; stateFilter = "all"; render(); });
$("all-employees").addEventListener("click", () => setView("employees"));
$("all-activity").addEventListener("click", () => setView("timeline"));
$("settings-button").addEventListener("click", () => setView("settings"));
$("mode-toggle").addEventListener("click", () => setView("settings"));
$("settings-mode-toggle").addEventListener("click", changeMode);
$("empty-demo").addEventListener("click", () => { if (!DEMO) changeMode(); else { branchId = current.branches[0]?.branch_id || ""; render(); } });
$("labels-toggle").addEventListener("click", () => labels($("labels-toggle").getAttribute("aria-pressed") !== "true"));
$("setting-labels").addEventListener("change", (e) => labels(e.target.checked));
$("setting-motion").checked = matchMedia("(prefers-reduced-motion: reduce)").matches;
$("setting-motion").addEventListener("change", (e) => document.body.classList.toggle("reduce-motion", e.target.checked));
$("zoom-in").addEventListener("click", () => changeZoom(zoom + ZOOM_STEP));
$("zoom-out").addEventListener("click", () => changeZoom(zoom - ZOOM_STEP));
$("zoom-reset").addEventListener("click", () => changeZoom(100));
$("previous-floor").addEventListener("click", () => { floor--; roomFilter = ""; render(); });
$("next-floor").addEventListener("click", () => { floor++; roomFilter = ""; render(); });
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); $("search").focus(); }
});
$("settings-dialog").addEventListener("click", (event) => { if (event.target === $("settings-dialog")) $("settings-dialog").close(); });
daylight = createDaylight($("world"), $("scene"), $("scene-weather"), document.querySelector(".scene-sun"), $("setting-daylight"));
coffee = createCoffeeBreaks($("characters"),render);
if (DEMO) {
  acceptState(demoState());
  setConnection("Demo workspace", "demo");
  text("workspace-name", "Demo workspace"); text("workspace-mode", "Switch to your live HQ");
  text("settings-mode", "Demo workspace");
  text("settings-mode-description", "These are fictional teammates. Your HQ data is not changed.");
  text("settings-mode-toggle", "Open live workspace"); $("demo-note").hidden = false;
}
changeZoom(100); setView("office");
furniture = mountFurniture($("world"));
furniture.update();
createOfficeCats($("characters"));
if (!DEMO) connect();
setInterval(render, 30000);
setInterval(updateClock, 1000);
setInterval(() => { updateWorkGestures($("characters")); furniture.update(); }, WORK_MOTION_INTERVAL);
window.addEventListener("pagehide", () => {
  clearTimeout(reconnectTimer);
  const socket = activeSocket;
  activeSocket = null;
  socket?.close();
  connected = false; render();
});
window.addEventListener("pageshow", (event) => { if (event.persisted && !DEMO) connect(); });
