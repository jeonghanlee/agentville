// Branch-provided strings are rendered through text nodes, never as markup.
import { icon, character, avatarColor, prepareAppearances } from "./art.js";
import { demoState } from "./demo.js";
import { updateWorkGestures, WORK_MOTION_INTERVAL } from "./motion.js";
import { createOfficeCats } from "./cats.js";
import { mountFurniture } from "./furniture.js";
import { mountDecor } from "./decor.js";
import { createDaylight, branchZone } from "./daylight.js";
import { SEATED_WIDTH, screenOffSprite } from "./sprites.js";
import { createCoffeeBreaks } from "./coffee.js";
import { createLounge } from "./lounge.js";
import { createWalkers } from "./walk.js";
import { APPROACH, NODES, route, distance, clear, blockedBy } from "./floor.js";
import { walkerDepth } from "./furniture.js";
import { t, locale, currentLanguage, setLanguage, translateDocument } from "./i18n.js";
import { createNotifications } from "./notify.js";
import { el, button } from "./dom.js";
import { dayOf, dayStart, dayEnd, shiftDay, duration } from "./days.js";
import { createHistory } from "./history.js";
import { createReplay, SPEEDS } from "./replay.js";
import { worklogTable } from "./worklog.js";

const DEMO = new URLSearchParams(location.search).get("demo") === "1";
const TOKEN = takeToken();
const COMMON = "common-office";
const STATES = ["working", "thinking", "waiting", "idle", "completed", "error", "limited", "unknown"];
const PRESENCE = ["on_duty", "off_duty", "on_leave"];
// "lazy" is the legacy name of "light"; both keep the same label and pose.
const CONDITIONS = ["normal", "extra-coffee", "study-mode", "light", "lazy"];
// Labels, titles, and descriptions come from the dictionary as nav.<id>, view.<id>.title, and view.<id>.description.
const VIEWS = [["office", "house"], ["dashboard", "grid"], ["employees", "people"], ["projects", "folder"],
  ["timeline", "clock"], ["worklog", "book"], ["branches", "branches"], ["settings", "settings"]];
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
// Visible screen glass of rear-facing desks, in office artwork pixels; front-facing desks hide their screens.
const SCREENS = {
  studio0: ["405,257 453,277 453,308 404,290", "555,312 605,327 605,363 555,347"],
  studio1: ["1147,287 1190,302 1190,333 1147,317", "1270,337 1313,352 1313,385 1270,370"],
  common: ["202,493 247,511 247,546 202,528", "328,541 378,558 378,592 328,574"],
};
// Standing spots on open floor, clear of furniture for a walker's feet (floor.js).
const WAITING_SPOTS = {
  fika: [[38,78.5],[42.5,82.5],[46.5,86.5],[52,89.5],[66.4,80.6],[57.5,88.7]],
  infirmary: [[78,81],[84,78],[73.5,83.2],[80.5,83.5]],
};
const EMPTY = { branches: [], agents: [], activities: [], contractors: [] };
const MAX_EVENTS = 60;
// Timeline list length, refresh interval of the shown day's changes, and of today's work log for waiting times.
const MAX_DAY_CHANGES = 400, DAY_REFRESH = 15000, TODAY_REFRESH = 60000;
const COMPLETED_MS = 4000, MAX_CONTRACTORS = 2;
const MIN_ZOOM = 100, MAX_ZOOM = 175, ZOOM_STEP = 25;
const $ = (id) => document.getElementById(id);
const keyOf = (branch, id) => JSON.stringify([branch, id]);
let current = EMPTY, connected = false, view = "office", branchId = "", floor = 0;
let stateFilter = "all", roomFilter = "", selected = "", zoom = 100;
let events = [], eventKeys = new Set(), reconnectTimer = null, activeSocket = null, everOpened = false, failedOpens = 0;
const actors = new Map();
const companions = new Map();
const screensOff = new Map();
const completions = new Map();
const lastStates = new Map();
// Seat reservations per shown room: Map of colleague key to seat index, or null while waiting or overflowing.
const seatOccupancy = new Map();
let daylight = null;
let furniture = null;
let decor = null;
let coffee = null;
let lounge = null;
let walkers = null;
// Last floor place of each shown colleague, so a change of place becomes a walk.
const places = new Map();
const motionAllowed = () => !matchMedia("(prefers-reduced-motion: reduce)").matches && !document.body.classList.contains("reduce-motion");
let cats = null;
let notifications = null;
// The first state of each socket is a baseline: it records states without notifying.
let resync = true;
let connection = ["connection.connecting", ""];
// The latest state from HQ; `current` is what the page shows, which is a past state while replaying.
let live = EMPTY;
// History reads (history.js); a module binding named after a window global (history, location, name) would shadow it.
let records = null, replay = null;
// Timeline: the shown day and its recorded changes. Work log: the chosen day and Branch ("" for all) and its rows.
let timelineDay = "", dayChanges = null, dayChangesKey = "", dayChangesAt = 0;
let worklogDay = "", worklogBranch = "", worklogData = null, worklogKey = "", worklogFailed = false;
// Today's work log in browser time, for waiting times on the Dashboard and in Colleague details.
let today = { key: "", data: null, at: 0 };
// Controls that keep their element across renders, so a drag or an open date picker survives a refresh.
let kept = {};
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
// The time the page shows: the replay time while replaying.
function nowMs() { return replay?.active ? replay.at : Date.now(); }
function text(id, value) { $(id).textContent = value; }
function known(state) { return STATES.includes(state); }
function color(state) { return "var(--" + (known(state) ? state : "idle") + ")"; }
function stateName(state) { return t("state." + (known(state) ? state : "unknown")); }
function presenceName(presence) { return PRESENCE.includes(presence) ? t("presence." + presence) : presence; }
function conditionName(condition) {
  return CONDITIONS.includes(condition) ? t("condition." + (condition === "lazy" ? "light" : condition)) : condition;
}
// Every room except the Common Office is one repository.
function repositoryTag(projectId) {
  return projectId === COMMON ? null : el("span", { class: "room-kind" }, t("room.repository"));
}
function branchName(branch, peers = current.branches) {
  const alias = branch?.branch?.alias || t("branch.unnamed");
  const duplicate = branch && peers.some((other) => other.branch_id !== branch.branch_id
    && (other.branch?.alias || t("branch.unnamed")) === alias);
  return duplicate ? alias + " (" + branch.branch_id + ")" : alias;
}
function providerInitials(provider) {
  return provider === "claude" ? "CL" : provider === "codex" ? "CX" : provider === "antigravity" ? "AG" : String(provider).slice(0, 2).toUpperCase();
}
function badge(provider) {
  return el("span", { class: "provider" + (provider === "codex" ? " codex" : "") }, providerInitials(provider));
}
function age(iso, compact = true) {
  const seconds = Math.max(0, (nowMs() - Date.parse(iso)) / 1000);
  if (!Number.isFinite(seconds)) return "-";
  if (seconds < 60) return t(compact ? "age.now" : "age.justNow");
  if (seconds < 3600) return t(compact ? "age.m" : "age.minutes", { n: Math.floor(seconds / 60) });
  if (seconds < 86400) return t(compact ? "age.h" : "age.hours", { n: Math.floor(seconds / 3600) });
  const days = Math.floor(seconds / 86400);
  return t(compact ? "age.d" : days === 1 ? "age.day" : "age.days", { n: days });
}
function displayZone() {
  return branchZone(current.branches.find((b) => b.branch_id === branchId)?.branch?.time);
}
// Clock times use the displayed Branch zone, matching the heading clock, in the selected language's locale.
function clockTime(iso) {
  const at = new Date(iso || NaN);
  if (!Number.isFinite(at.getTime())) return "";
  const zone = displayZone(), options = zone ? { timeZone: zone } : {};
  const sameDay = at.toLocaleDateString("en-US", options) === new Date(nowMs()).toLocaleDateString("en-US", options);
  return (sameDay ? "" : at.toLocaleDateString(locale(), { weekday: "short", ...options }) + " ")
    + at.toLocaleTimeString(locale(), { hour: "numeric", minute: "2-digit", ...options });
}
function resetLabel(row) {
  const time = row.state === "limited" ? clockTime(row.activity?.reset_at) : "";
  return time ? t("reset", { time }) : "";
}
function workloadText(row) {
  const n = row.activity?.workload ?? 0;
  return t(n === 1 ? "workload.one" : "workload.other", { n });
}
function contractorState(contractor) {
  return known(contractor.state) ? contractor.state : "unknown";
}
function contractorTool(contractor) {
  return contractorState(contractor) === "working" ? contractor.tool || "" : "";
}
function providerName(provider) {
  return provider === "claude" ? "Claude" : provider === "codex" ? "Codex" : provider === "antigravity" ? "Antigravity" : String(provider);
}
// A completed turn shows a brief checkmark even when idle follows quickly.
// Completed and idle can arrive together, so working or thinking turning idle also counts as a finished turn.
function noteCompletions(all) {
  for (const row of all) {
    const previous = lastStates.get(row.key);
    lastStates.set(row.key, row.state);
    const finished = row.state === "completed" || (row.state === "idle" && (previous === "working" || previous === "thinking"));
    if (!row.duty || !finished) continue;
    if (completions.get(row.key)?.since === row.activity.state_since) continue;
    completions.set(row.key, { since: row.activity.state_since, until: Date.now() + COMPLETED_MS });
    setTimeout(render, COMPLETED_MS + 50);
  }
}
function showsDone(row) { return (completions.get(row.key)?.until || 0) > Date.now(); }
function idleDetail(activity, branch) {
  const seconds = Math.max(0, (nowMs() - Date.parse(activity?.state_since)) / 1000);
  const thresholds = { phone: 300, doze: 1800, lounge: 3600, ...branch?.branch?.thresholds };
  if (seconds >= thresholds.lounge) return "fika";
  if (seconds >= thresholds.doze) return "dozing";
  if (seconds >= thresholds.phone) return "phone";
  return "at desk";
}
function colleagueName(agent) { return agent.alias || providerName(agent.provider) + " " + agent.seat; }
function rows(data = current) {
  const branches = new Map(data.branches.map((b) => [b.branch_id, b]));
  const activities = new Map(data.activities.map((a) => [keyOf(a.branch_id, a.agent_id), a]));
  return data.agents.map((agent) => {
    const branch = branches.get(agent.branch_id);
    const activity = activities.get(keyOf(agent.branch_id, agent.agent_id));
    const duty = agent.presence === "on_duty";
    const verified = hqConnected() && Boolean(branch?.reachable);
    const state = duty ? (activity && known(activity.state) ? activity.state : "unknown") : "idle";
    const detail = state === "idle" && duty ? idleDetail(activity, branch) : "";
    const contractors = data.contractors.filter((c) =>
      c.branch_id === agent.branch_id && c.parent_instance_id === agent.instance?.instance_id && c.status !== "ended");
    return {
      key: keyOf(agent.branch_id, agent.agent_id), agent, branch, activity, state, detail, duty, verified, contractors,
      name: colleagueName(agent),
      branchName: branchName(branch),
      project: agent.project_alias || t("project.unnamed"),
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
  return !query || [row.name, row.project, row.agent.provider, row.branchName, stateName(row.state),
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
// Unverified has two causes: the page has no HQ connection, or HQ is connected but has no fresh Branch report.
// Both keep the last observed state; only the wording differs.
// A replayed state is a recorded one; only its own reachability marks it unverified.
function hqConnected() { return DEMO || connected || Boolean(replay?.active); }
function branchWording(branch) {
  return branch?.reachable && hqConnected() ? "reporting" : hqConnected() ? "awaiting" : "hqLost";
}
function stateLabel(row) {
  const label = !row.duty ? presenceName(row.agent.presence)
    : row.detail && row.detail !== "at desk" ? t("idle." + row.detail) : stateName(row.state);
  const unverified = !row.verified;
  return el("span", { class: "state-label" + (unverified ? " unverified" : ""), style: { "--state-color": color(row.state) },
    ...(unverified ? { title: t(hqConnected() ? "state.awaitingTitle" : "state.unverifiedTitle", { label }) } : {}) },
    el("i", { class: "status-dot" }), label, unverified ? el("span", { class: "unverified-mark", "aria-hidden": "true" }, "?") : null,
    unverified ? el("span", { class: "sr-only" }, t("state.unverifiedSuffix")) : null);
}
function statusText(row) {
  const label = row.state === "idle" && row.detail ? t("idle.value", { state: stateName("idle"), detail: t("idle." + row.detail) })
    : stateName(row.state);
  return row.verified ? label : t("state.unverifiedValue", { label });
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
    s === "all" ? t("filters.all") : stateName(s),
    countBadge(ctx.present.filter((r) => s === "all" || r.state === s)),
  ], "filter", () => { stateFilter = s; render(); },
  { "aria-pressed": String(s === stateFilter), "data-focus-key": "filter-" + s, "data-filter": s })));
}
function renderRooms(ctx) {
  const rooms = ctx.page.map((p,i) => ({ ...p, id: projectRoom(p.id), color: ROOM_LAYOUT["studio" + i].color, repository: true }));
  rooms.push({ id: "common", name: t("room.common"), color: ROOM_LAYOUT.common.color },
    { id: "fika", name: t("room.fika"), color: ROOM_LAYOUT.fika.color },
    { id: "infirmary", name: t("room.infirmary"), color: ROOM_LAYOUT.infirmary.color });
  $("rooms").replaceChildren(...rooms.map((room) => button([
    el("i", { class: "room-square", style: { "--room-color": room.color } }), room.name,
    room.repository ? el("small", { class: "room-kind" }, t("room.repository")) : null,
    countBadge(ctx.present.filter((r) => roomOf(r) === room.id)),
  ], "room-tab", () => { roomFilter = roomFilter === room.id ? "" : room.id; render(); },
  { "aria-pressed": String(roomFilter === room.id), "data-focus-key": "room-" + room.id })));
  const count = Math.max(1, Math.ceil(ctx.projects.length / 2));
  $("floor-controls").hidden = count <= 1;
  text("floor-label", (floor + 1) + " / " + count);
  $("previous-floor").disabled = floor === 0;
  $("next-floor").disabled = floor >= count - 1;
}
// The reservation scope of a shown room. Facilities are kept per Branch; desk rooms also follow the shown floor
// page and the repository in that room, so another Branch or page starts with fresh desk assignments.
function seatScope(ctx, room) {
  if (Object.hasOwn(WAITING_SPOTS, room)) return keyOf(branchId, "facility:" + room);
  const project = room.startsWith("studio") ? ctx.page[Number(room.slice(6))]?.id : COMMON;
  return keyOf(branchId, "desk:" + room + ":" + floor + ":" + project);
}
// Where a colleague stands for a place: in front of a chair, beside the bed, or on a standing spot.
// Seats also name the free side of the chair, which walkers pass through when sitting down or getting up.
function placeOf(room, index, home, spot) {
  if (spot) return { foot: spot, approach: null };
  const side = APPROACH[room]?.[index];
  if (home[2] === "lying") return { foot: side ? NODES[side] : home.slice(0,2), approach: null };
  return { foot: [home[0], home[1] + (home[2].startsWith("back") ? 2.2 : 3.6)], approach: side ? NODES[side] : null };
}
// A changed place starts a walk along the floor routes; the first sighting, another Branch, or reduced motion places directly.
function moveWalker(key, target) {
  const last = places.get(key);
  places.set(key, { ...target, scope: branchId });
  const current = walkers?.get(key);
  if (!walkers || !last || last.scope !== branchId || !motionAllowed()) { walkers?.stop(key); return null; }
  if (distance(current ? current.goal : last.foot, target.foot) < .05) return current;
  const start = current ? [current.x, current.y] : last.foot;
  // A walker leaves a seat through its free side; one turned around on the step into or out of a seat first
  // reaches the free end of that step, since the step itself touches the seat.
  const leave = current ? (clear(...current.stretch) ? [] : [current.stretch.find((point) => !blockedBy(point)) || current.stretch[0]])
    : last.approach ? [last.approach] : [];
  const path = [start, ...route(leave[0] || start, target.approach || target.foot).slice(leave.length ? 0 : 1),
    ...(target.approach ? [target.foot] : [])].filter((point, i, all) => i === 0 || distance(point, all[i-1]) > .01);
  if (path.length < 2) return null;
  const visit = coffee?.get(key);
  walkers.start(key, path, () => coffee?.arrived(key), visit?.phase === "walking-back");
  return walkers.get(key);
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
  // Every room keeps its seats for the visit: a colleague holds its desk, lounge chair, or bed until it leaves the room,
  // newcomers take the lowest free seat (people arrive in seat-number order), and the others stay put.
  // Facilities keep a waiting line in first-arrival order; desk rooms show further people as "+N".
  // Desk assignments start over when the shown Branch or floor page changes.
  const scopes = new Set();
  for (const room of new Set([...groups.keys(), ...Object.keys(WAITING_SPOTS)])) {
    const id = seatScope(ctx, room);
    scopes.add(id);
    if (!seatOccupancy.has(id)) seatOccupancy.set(id,new Map());
    const occupants = seatOccupancy.get(id);
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
  for (const id of seatOccupancy.keys()) if (!scopes.has(id) && !JSON.parse(id)[1].startsWith("facility:")) seatOccupancy.delete(id);
  const fika = seatOccupancy.get(seatScope(ctx,"fika"));
  coffee?.sync([...fika].filter(([,index]) => index !== null)
    .map(([key,index]) => [key,ROOM_LAYOUT.fika.seats[index]]),branchId);
  lounge?.sync([...fika.keys()].map((key) => [key, JSON.parse(key)[1]]));
  const used = new Set(), hired = new Set(), dark = new Set();
  $("characters").querySelectorAll(".room-overflow").forEach((n) => n.remove());
  for (const [room, people] of groups) {
    const layout = ROOM_LAYOUT[room];
    const occupants = seatOccupancy.get(seatScope(ctx,room));
    const waiting = WAITING_SPOTS[room] ? [...occupants].filter(([,index]) => index === null).map(([key]) => key) : [];
    const shownWaiting = waiting.slice(0,WAITING_SPOTS[room]?.length || 0);
    if (waiting.includes(selected) && !shownWaiting.includes(selected)) shownWaiting[shownWaiting.length-1] = selected;
    const placed = people.map((row) => ({ row, index: occupants.get(row.key) }))
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
      const condition = CONDITIONS.includes(row.agent.condition) ? row.agent.condition : "normal";
      node.className = ["agent", row.state, row.detail, condition, row.verified ? "" : "unverified",
        selected === row.key ? "selected" : "", visible ? "" : "filtered"].join(" ");
      const reset = resetLabel(row), done = showsDone(row);
      node.setAttribute("aria-label", row.name + ", " + stateName(row.state) + (row.verified ? "" : t("state.unverifiedSuffix"))
        + (done && row.state !== "completed" ? ", " + stateName("completed") : "") + (reset ? ", " + reset : "") + ", " + row.project);
      node.setAttribute("aria-pressed", String(row.key === selected));
      node.tabIndex = visible ? 0 : -1;
      const visit = coffee?.get(row.key);
      const waitingIndex = shownWaiting.indexOf(row.key);
      const spot = waitingIndex >= 0 ? WAITING_SPOTS[room][waitingIndex] : null;
      const home = spot ? [...spot,"standing",Math.floor(spot[1])+1] : layout.seats[index];
      const walk = moveWalker(row.key, visit?.point ? { foot: visit.point, approach: null } : placeOf(room, index, home, spot));
      const counter = !walk && visit?.point;
      const seat = walk ? [walk.x, walk.y, "walking", walk.depth]
        : counter ? [...visit.point, "coffee-back", walkerDepth(...visit.point)] : home;
      const desk = seat[2];
      node.classList.add(walk || counter ? "coffee-standing" : spot ? "standing" : desk === "lying" ? "reclining" : "seated");
      if (walk) node.classList.add("walking");
      node.dataset.room = room;
      node.dataset.seatFacing = desk;
      node.dataset.coffeePhase = visit?.phase || (walk ? "walking" : "");
      node.dataset.coffeeFacing = walk?.facing || (counter ? "right" : "");
      node.dataset.walkView = walk?.view || "";
      node.dataset.queuePosition = spot ? String(waiting.indexOf(row.key)+1) : "";
      node.dataset.seatIndex = index === null ? "" : String(index);
      node.style.width = desk === "lying" ? "8%" : SEATED_WIDTH + "%";
      node.style.left = seat[0] + "%";
      node.style.top = seat[1] + "%";
      node.style.zIndex = String(seat[3]);
      // Keep unchanged SVG nodes alive so data refreshes do not restart gestures.
      const workstation = WORKSTATIONS[room]?.[index] ? { seat, keys: WORKSTATIONS[room][index] } : null;
      // Lounge colleagues hold their own drink; a counter visit shows the drink being fetched.
      const drink = row.detail === "fika" && lounge ? lounge.drink(row.key, row.agent.agent_id) : null;
      const cup = visit?.drink || drink || coffee?.cup(row.key);
      const detail = walk ? (walk.carrying ? "coffee-cup" : "coffee-walk")
        : counter ? (visit.phase === "waiting" ? "coffee-wait" : "coffee-walk") : row.detail;
      // Limited Employees switch off the visible desk screen, or show a small dark monitor when none is visible.
      const glass = row.state === "limited" && !visit && !spot ? SCREENS[room]?.[index] : null;
      if (glass) {
        dark.add(row.key);
        let screen = screensOff.get(row.key);
        if (!screen) {
          screen = document.createElementNS("http://www.w3.org/2000/svg", "svg");
          screen.setAttribute("viewBox", "0 0 1536 1024");
          screen.setAttribute("class", "screen-off-glass");
          screen.setAttribute("aria-hidden", "true");
          screensOff.set(row.key, screen);
          $("world").append(screen);
        }
        if (screen.dataset.glass !== glass) {
          screen.innerHTML = '<polygon points="' + glass + '"/>';
          screen.dataset.glass = glass;
        }
        screen.style.zIndex = String(seat[3] - 1);
      }
      const appearance = JSON.stringify([currentLanguage(), row.state, detail, condition, desk, workstation, cup, node.dataset.queuePosition,
        row.name, row.agent.provider, row.branchName, row.agent.branch_id === branchId, reset, done, Boolean(glass)]);
      if (node.dataset.appearance !== appearance) {
        const name = el("span", { class: "agent-name" }, badge(row.agent.provider), row.name,
          row.agent.branch_id === branchId ? null : el("span", { class: "remote-badge" }, row.branchName),
          reset ? el("span", { class: "reset-time" }, reset) : null);
        const children = [character(row.key, row.state, detail, condition, false, desk, workstation, cup),
          name, el("span", { class: "agent-signal", style: { background: color(row.state) } })];
        if (row.state === "limited" && !glass) children.push(screenOffSprite());
        if (done) children.push(el("span", { class: "done-check", title: stateName("completed") }, icon("check")));
        if (counter && visit.phase === "waiting") children.push(el("span", { class: "coffee-status" },
          t({ coffee: "coffee.brewing", tea: "drink.steeping" }[visit.drink?.kind || "coffee"] || "drink.pouring")));
        if (spot) children.push(el("span", { class: "queue-status" },
          t(room === "infirmary" ? "queue.bed" : "queue.seat") + " / " + node.dataset.queuePosition));
        node.replaceChildren(...children);
        node.dataset.appearance = appearance;
      }
      lounge?.decorate(node, row.key);
      // Each Contractor shows its own activity; further Contractors collapse into "+N".
      const shown = row.contractors.slice(0, MAX_CONTRACTORS);
      shown.forEach((contractor, i) => {
        const id = JSON.stringify([row.key, contractor.contractor_id]);
        let companion = companions.get(id);
        if (!companion) {
          companion = button("", "contractor", () => selectEmployee(row.key), { "data-parent-key": row.key });
          companions.set(id, companion);
          $("characters").append(companion);
        }
        hired.add(id);
        const state = contractorState(contractor), tool = contractorTool(contractor);
        const extra = i === shown.length - 1 ? row.contractors.length - shown.length : 0;
        companion.className = ["contractor", state, row.verified ? "" : "unverified", visible ? "" : "filtered"].join(" ");
        companion.setAttribute("aria-label", t("contractor.label", { provider: providerName(contractor.provider), name: row.name, state: stateName(state) })
          + (row.verified ? "" : t("state.unverifiedSuffix")) + (tool ? ", " + tool : "") + (extra ? t("contractor.more", { n: extra }) : ""));
        companion.tabIndex = visible ? 0 : -1;
        const foot = desk === "lying" ? [seat[0]+4.2,seat[1]+13]
          : [seat[0]+3.1,seat[1]+(visit || spot ? 0 : desk.startsWith("back") ? 2.2 : 3.6)];
        companion.style.left = (foot[0] + i * 2.8) + "%";
        companion.style.top = (foot[1] + i * .9) + "%";
        companion.style.zIndex = String(Math.floor(foot[1] + i * .9)+1);
        const appearance = JSON.stringify([currentLanguage(), state, tool, contractor.provider, extra]);
        if (companion.dataset.appearance !== appearance) {
          companion.replaceChildren(character(row.key + "helper:" + contractor.contractor_id, state, "", "normal", true, "standing"),
            el("span", { class: "contractor-tag" + (contractor.provider === "codex" ? " codex" : ""), "aria-hidden": "true" }, providerInitials(contractor.provider)),
            el("span", { class: "contractor-name" }, badge(contractor.provider), t("contractor") + " / " + stateName(state), tool ? " / " + tool : null),
            ...(extra ? [el("small", {}, "+" + extra)] : []));
          companion.dataset.appearance = appearance;
        }
      });
    });
    if (people.length > placed.length) {
      const overflow = button("+" + (people.length - placed.length), "room-overflow", () => {
        roomFilter = room.startsWith("studio") ? projectRoom(ctx.page[Number(room.slice(-1))].id) : room;
        render();
      }, { "aria-label": t("room.showAll") });
      overflow.style.left = layout.overflow[0] + "%";
      overflow.style.top = layout.overflow[1] + "%";
      $("characters").append(overflow);
    }
  }
  for (const [key,node] of actors) {
    if (!used.has(key)) { node.remove(); actors.delete(key); walkers?.stop(key); places.delete(key); }
  }
  for (const [key,node] of companions) {
    if (!hired.has(key)) { node.remove(); companions.delete(key); }
  }
  for (const [key,node] of screensOff) {
    if (!dark.has(key)) { node.remove(); screensOff.delete(key); }
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
    : [el("div", { class: "empty-list" }, t(ctx.present.length ? "team.noMatch" : "team.none"))]));
  const row = ctx.present.find((r) => r.key === selected);
  if (!row) {
    $("employee-detail").replaceChildren(el("p", { class: "detail-eyebrow" }, t("detail.eyebrow")),
      el("p", { class: "detail-note" }, t("detail.select")));
    return;
  }
  const stats = [[t("detail.status"), statusText(row)], [t("detail.condition"), conditionName(row.agent.condition)],
    [t("detail.tool"), row.state === "working" ? row.activity?.tool || "-" : "-"],
    [t("detail.workload"), row.verified ? workloadText(row) : "-"]];
  if (resetLabel(row)) stats.push([t("detail.limit"), resetLabel(row)]);
  // Waiting time of the browser day; not shown for a replayed time.
  if (!replay?.active && today.data) {
    const log = today.data.rows.find((r) => r.branch_id === row.agent.branch_id && r.agent_id === row.agent.agent_id);
    stats.push([t("detail.waitedToday"), log ? t(log.waits === 1 ? "detail.waitedOne" : "detail.waitedMany",
      { duration: duration(log.seconds.waiting) || "-", n: log.waits }) : "-"]);
  }
  const occupants = seatOccupancy.get(keyOf(branchId,"facility:" + roomOf(row)));
  const waiting = occupants?.get(row.key) === null;
  if (waiting) stats.push([t("detail.place"), t(roomOf(row) === "infirmary" ? "queue.bed" : "queue.seat")]);
  const note = !row.verified ? t(hqConnected() ? "detail.awaiting" : "detail.unverified") : row.state === "limited" ? t("detail.limited")
    : row.state === "unknown" ? t("detail.unknown") : "";
  const observed = clockTime(row.branch?.last_seen_at);
  $("employee-detail").replaceChildren(el("p", { class: "detail-eyebrow" }, t("detail.eyebrow")),
    el("div", { class: "detail-top" }, avatar(row), el("div", {}, el("strong", {}, row.name),
      el("small", {}, row.project, " ", repositoryTag(row.agent.project_id), " / " + row.branchName))),
    // The id is shown so it can be copied into the Collector configuration `aliases`.
    el("p", { class: "detail-id" }, t("detail.agentId") + " ", el("code", {}, row.agent.agent_id)),
    el("dl", { class: "detail-grid" }, ...stats.map(([name,value]) => el("div", {}, el("dt", {}, name), el("dd", {}, value)))),
    ...(row.contractors.length ? [el("div", { class: "detail-contractors" }, el("p", { class: "detail-eyebrow" }, t("contractor.upper")),
      el("ul", {}, ...row.contractors.map((contractor) => {
        const state = contractorState(contractor), tool = contractorTool(contractor);
        return el("li", {}, badge(contractor.provider), el("span", {}, t("contractor")),
          stateLabel({ ...row, state, detail: "", duty: true }), el("small", {}, tool || "-"));
      })))] : []),
    ...(note ? [el("p", { class: "detail-note" }, note)] : []),
    ...(observed ? [el("p", { class: "detail-note" }, t("detail.lastObserved", { time: observed }))] : []));
}
function eventLabel(event) { return t("event." + event.kind); }
function eventNode(event) {
  const symbol = { working: "spark", thinking: "spark", waiting: "hand", idle: "coffee", error: "heart", completed: "check", unknown: "branches", limited: "clock" }[event.state] || "clock";
  return el("div", { class: "event" }, el("span", { class: "event-icon" }, icon(symbol)),
    el("div", {}, el("p", {}, el("strong", {}, event.name), " " + eventLabel(event)),
      el("small", {}, event.project + " / " + age(event.at, false))));
}
// While replaying, recent activity is the recorded changes of the shown day up to the replay time.
function visibleEvents() {
  const q = $("search").value.trim().toLowerCase();
  const list = replay?.active ? dayEvents().filter((e) => Date.parse(e.at) <= replay.at) : events;
  return list.filter((e) => !q || [e.name,e.project,eventLabel(e)].join(" ").toLowerCase().includes(q));
}
// Recorded changes as timeline events, newest first.
function dayEvents() {
  if (!dayChanges) return [];
  const agents = new Map(dayChanges.agents.map((a) => [keyOf(a.branch_id, a.agent_id), a]));
  const branches = new Map(dayChanges.branches.map((b) => [b.branch_id, b]));
  return dayChanges.changes.map((change) => {
    const branch = branchName(branches.get(change.branch_id) || current.branches.find((b) => b.branch_id === change.branch_id));
    if (change.kind === "reachability") {
      return { name: branch, project: "", state: change.reachable ? "idle" : "unknown", kind: change.reachable ? "reachable" : "unreachable", at: change.at };
    }
    const agent = agents.get(keyOf(change.branch_id, change.agent_id));
    const state = change.kind === "activity" ? (known(change.state) ? change.state : "unknown") : "idle";
    const kind = change.kind === "activity" ? state : PRESENCE.includes(change.presence) ? change.presence : "unknown";
    return { name: agent ? colleagueName(agent) : change.agent_id, project: (agent?.project_alias || t("project.unnamed")) + " / " + branch,
      state, kind, at: change.at };
  }).reverse();
}
function recordEvents(all) {
  for (const row of all) {
    const key = JSON.stringify([row.key,row.agent.presence,row.activity?.state,row.since]);
    if (eventKeys.has(key)) continue;
    eventKeys.add(key);
    // Events keep a dictionary kind, so a language change relabels past entries.
    const kind = !row.duty ? (PRESENCE.includes(row.agent.presence) ? row.agent.presence : "unknown") : row.state;
    events.push({ name: row.name, project: row.project, state: row.state, kind, at: row.since });
  }
  events.sort((a,b) => Date.parse(b.at) - Date.parse(a.at));
  events = events.slice(0, MAX_EVENTS);
  if (eventKeys.size > 1000) eventKeys = new Set(all.map((r) => JSON.stringify([r.key,r.agent.presence,r.activity?.state,r.since])));
}
function employeeTable(all) {
  const heading = ["table.room", "table.colleague", "table.presence", "table.activity", "table.tool", "table.condition", "table.workload", "table.since"];
  const body = all.filter(queryMatches).map((r) => el("tr", {},
    el("td", {}, r.branchName, el("br"), r.project, " ", repositoryTag(r.agent.project_id)),
    el("td", {}, badge(r.agent.provider), r.name, r.contractors.length ? " +" + r.contractors.length : ""),
    el("td", {}, presenceName(r.agent.presence) + (r.verified ? "" : t("state.unverifiedSuffix"))),
    el("td", {}, stateLabel(r)), el("td", {}, r.state === "working" ? r.activity?.tool || "-" : "-"),
    el("td", {}, r.duty ? conditionName(r.agent.condition) : "-"),
    el("td", {}, r.duty && r.verified ? workloadText(r) : "-"),
    el("td", {}, age(r.since, false))));
  return el("div", { class: "data-card" }, el("h2", {}, t("table.title")),
    el("div", { class: "table-scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, heading.map((h) => el("th", { scope: "col" }, t(h))))),
      el("tbody", {}, body.length ? body : el("tr", {}, el("td", { colspan: 8 }, t("team.noMatch")))))));
}
function waitMetrics(all) {
  const waiting = all.filter((r) => r.duty && r.state === "waiting").map((r) => [r, (nowMs() - Date.parse(r.activity?.state_since)) / 1000])
    .filter(([, seconds]) => Number.isFinite(seconds)).sort((a,b) => b[1] - a[1]);
  const longest = waiting[0];
  const out = [el("div", { class: "metric" }, el("span", {}, t("metric.longestWait")),
    el("strong", {}, longest ? duration(Math.max(longest[1], 60)) : "-"), el("small", {}, longest ? longest[0].name : t("metric.noWait")))];
  // The day's total waiting time comes from the work log of the browser day; a replayed time has none.
  if (!replay?.active) {
    const rows = today.data?.rows || [];
    const seconds = rows.reduce((sum, r) => sum + r.seconds.waiting, 0), count = rows.reduce((sum, r) => sum + r.waits, 0);
    out.unshift(el("div", { class: "metric" }, el("span", {}, t("metric.waitedToday")), el("strong", {}, today.data ? duration(seconds) : "-"),
      el("small", {}, t(count === 1 ? "metric.waitsOne" : "metric.waitsMany", { n: count }))));
  }
  return out;
}
function renderData(all) {
  const root = $("data-view");
  if (view === "employees") root.replaceChildren(employeeTable(all));
  if (view === "dashboard") {
    const metrics = [[t("metric.branches"), current.branches], [t("metric.onDuty"), all.filter((r) => r.duty)],
      [t("metric.waiting"), all.filter((r) => r.duty && r.state === "waiting")], [t("metric.error"), all.filter((r) => r.duty && r.state === "error")]];
    root.replaceChildren(el("div", { class: "dashboard-summary" }, metrics.map(([title,list]) => {
      const unverified = list.some((r) => r.duty && !r.verified);
      return el("div", { class: "metric" + (unverified ? " unverified" : "") }, el("span", {}, title), el("strong", {}, list.length),
        unverified ? el("small", {}, t("state.unverified")) : null);
    }), waitMetrics(all)), employeeTable(all));
  }
  if (view === "timeline") renderTimeline(root);
  if (view === "worklog") renderWorklog(root);
  if (view === "projects") {
    const projects = [...new Map(all.filter(queryMatches).map((r) => [r.agent.project_id, r.project])).entries()];
    root.replaceChildren(el("div", { class: "data-grid" }, projects.length ? projects.map(([id,name]) => {
      const members = all.filter((r) => r.agent.project_id === id);
      return el("article", { class: "project-card" }, icon("folder"), el("h2", {}, name),
        id === COMMON ? null : el("p", { class: "room-kind" }, t("room.repository")),
        el("p", {}, t("project.counts", { duty: members.filter((r) => r.duty).length, branches: new Set(members.map((r) => r.agent.branch_id)).size })),
        button(t("project.open"), "secondary-button", () => {
          branchId = members[0].agent.branch_id;
          const ctx = context(all);
          const index = ctx.projects.findIndex((p) => p.id === id);
          floor = Math.max(0, Math.floor(index / 2));
          roomFilter = id === COMMON ? "common" : projectRoom(id); stateFilter = "all";
          setView("office");
        }));
    }) : el("p", { class: "empty-list" }, t("project.none"))));
  }
  if (view === "branches") {
    const query = $("search").value.trim().toLowerCase();
    const branches = current.branches.filter((b) => !query || (b.branch?.alias || "").toLowerCase().includes(query));
    root.replaceChildren(el("div", { class: "data-grid" }, branches.length ? branches.map((b) =>
      el("article", { class: "branch-card" }, icon("house"), el("h2", {}, branchName(b)),
        el("p", {}, t("branch." + branchWording(b))),
        el("p", {}, t("branch.counts", { duty: all.filter((r) => r.agent.branch_id === b.branch_id && r.duty).length, age: age(b.last_seen_at, false) })),
        button(t("branch.open"), "secondary-button", () => { branchId = b.branch_id; floor = 0; roomFilter = ""; stateFilter = "all"; setView("office"); })))
      : el("p", { class: "empty-list" }, t("branch.noMatch"))));
  }
}
function updateClock() {
  const now = new Date(nowMs()), zone = displayZone(), options = zone ? { timeZone: zone } : {};
  const branch = current.branches.find((b) => b.branch_id === branchId);
  text("today", now.toLocaleDateString(locale(), { weekday: "short", month: "short", day: "numeric", ...options }).toUpperCase());
  text("local-time", now.toLocaleTimeString(locale(), { hour: "numeric", minute: "2-digit", ...options }));
  text("clock-label", zone ? zone.replaceAll("_", " ") : t("clock.browser"));
  $("clock-label").title = zone ? t("clock.branch", { branch: branchName(branch) }) : "";
  daylight?.update(now, zone);
}
function render() {
  const focused = focusKey();
  const all = rows();
  prepareAppearances(all.flatMap((row) => [row.key, ...row.contractors.map((c) => row.key + "helper:" + c.contractor_id)]));
  if (!current.branches.some((b) => b.branch_id === branchId)) { branchId = current.branches[0]?.branch_id || ""; floor = 0; roomFilter = ""; }
  const ctx = context(all);
  const matching = ctx.present.filter(passes);
  const onFloor = ctx.office.filter(passes);
  if (!selected || !matching.some((r) => r.key === selected)) {
    selected = onFloor.find((r) => r.state === "working")?.key || onFloor[0]?.key || matching[0]?.key || "";
  }
  $("branch-select").replaceChildren(...(current.branches.length ? current.branches.map((b) =>
    el("option", { value: b.branch_id }, branchName(b))) : [el("option", { value: "" }, t("branch.none"))]));
  $("branch-select").value = branchId;
  $("branch-select").disabled = !current.branches.length;
  const branch = current.branches.find((b) => b.branch_id === branchId);
  text("branch-subtitle", branch ? (branch.branch?.location || t("branch.noLocation")) : t("branch.waiting"));
  const wording = branch || !hqConnected() ? branchWording(branch) : "noReport";
  $("office-open").classList.toggle("unreachable", wording !== "reporting");
  $("office-open").replaceChildren(el("i", { class: "status-dot" }), t("branch." + wording));
  const projects = new Set(all.filter((r) => r.agent.project_id !== COMMON).map((r) => r.agent.project_id));
  $("summary").replaceChildren(...[["people", all.filter((r) => r.duty).length, "summary.onDuty"],
    ["folder", projects.size, "summary.projects"], ["branches", current.branches.length, "summary.branches"]].map(([symbol,n,label]) =>
    el("span", { class: "summary-item" }, icon(symbol), el("strong", {}, n), t(label))));
  decor?.update(branchId);
  renderFilters(ctx); renderRooms(ctx); renderCharacters(ctx); renderTeam(ctx);
  $("scene-empty").hidden = ctx.present.length > 0;
  $("scene").classList.toggle("is-empty", ctx.present.length === 0);
  const first = !current.branches.length;
  text("empty-title", t(first ? "empty.firstTitle" : "empty.dutyTitle"));
  text("empty-text", t(first ? "empty.firstText" : "empty.dutyText"));
  text("office-footer-text", hqConnected() ? t("footer.counts", { present: ctx.present.length, rooms: ctx.projects.length })
    : t(everOpened ? "footer.hqLost" : "footer.waiting"));
  $("recent-activity").replaceChildren(...(visibleEvents().length ? visibleEvents().slice(0,4).map(eventNode)
    : [el("p", { class: "empty-list" }, t("activity.none"))]));
  $("branch-statuses").replaceChildren(...current.branches.map((b) =>
    el("span", { class: "branch-status" + (branchWording(b) === "reporting" ? "" : " unreachable") },
      el("i", { class: "status-dot" }), branchName(b),
      el("time", { datetime: b.last_seen_at },
        t({ reporting: "branch.lastReport", awaiting: "branch.awaitingAge", hqLost: "branch.hqLostAge" }[branchWording(b)], { age: age(b.last_seen_at) })))));
  if (view !== "office") renderData(all);
  updateReplay();
  updateClock();
  restoreFocus(focused);
}
// Replay (Section 6.5 of the architecture). The banner and the Timeline card share the controls.
function showReplay() {
  current = replay.active && replay.state ? replay.state : live;
  render();
}
function backToLive() { replay.stop(); }
function zoneTime(ms, withDate) {
  const zone = displayZone();
  return new Date(ms).toLocaleString(locale(), { ...(withDate ? { month: "short", day: "numeric" } : {}),
    hour: "numeric", minute: "2-digit", second: "2-digit", ...(zone ? { timeZone: zone } : {}) });
}
function dayLabel(day, zone) {
  return new Date(dayStart(day, zone) + 43200000).toLocaleDateString(locale(),
    { weekday: "short", month: "short", day: "numeric", ...(zone ? { timeZone: zone } : {}) });
}
function changeTimes() { return (dayChanges?.changes || []).map((c) => Date.parse(c.at)); }
function startReplay(ms, exact = false) { replay.pause(); replay.seek(ms, exact); }
function replayButtons() {
  const previous = button(icon("back"), "icon-button", () => replay.jump(changeTimes(), -1), { "aria-label": t("replay.previous"), title: t("replay.previous") });
  const play = button("", "icon-button replay-play", () => {
    if (!replay.active) replay.seek(sliderBounds()[0]);
    replay.toggle();
  });
  const next = button(icon("forward"), "icon-button", () => replay.jump(changeTimes(), 1), { "aria-label": t("replay.next"), title: t("replay.next") });
  const speeds = el("span", { class: "replay-speeds", role: "group", "aria-label": t("replay.speed") },
    SPEEDS.map((n) => button(n + "x", "replay-speed", () => replay.setSpeed(n), { "data-speed": String(n) })));
  return el("span", { class: "replay-buttons" }, previous, play, next, speeds);
}
function buildBanner() {
  $("replay-banner").replaceChildren(el("span", { class: "replay-label" }, icon("clock"), el("strong", { id: "replay-label" })),
    replayButtons(), button(t("replay.live"), "secondary-button replay-live", backToLive));
}
// The slider covers the shown day within the kept history and up to now.
function sliderBounds() {
  const zone = displayZone(), range = replay.range;
  const start = Math.max(dayStart(timelineDay || dayOf(nowMs(), zone), zone), range.from ?? -Infinity);
  return [start, Math.max(start, Math.min(dayEnd(timelineDay || dayOf(nowMs(), zone), zone), replay.now()))];
}
function updateReplay() {
  const active = Boolean(replay?.active);
  document.body.classList.toggle("replaying", active);
  $("replay-banner").hidden = !active;
  if (active) {
    text("replay-label", t("replay.banner", { time: zoneTime(replay.at, true) }) + (replay.failed ? " / " + t("replay.failed") : ""));
    // Playing across midnight moves the Timeline to the next day.
    const day = dayOf(replay.at, displayZone());
    if (timelineDay && day !== timelineDay) { timelineDay = day; loadDayChanges(); }
  }
  const times = changeTimes();
  document.querySelectorAll(".replay-buttons").forEach((group) => {
    const [previous, play, next] = group.children;
    play.replaceChildren(icon(replay?.playing ? "pause" : "play"));
    play.setAttribute("aria-label", t(replay?.playing ? "replay.pause" : "replay.play"));
    play.title = t(replay?.playing ? "replay.pause" : "replay.play");
    play.disabled = !replay?.range.from;
    previous.disabled = !active || !times.some((ms) => ms < replay.at - 500);
    next.disabled = !active || !times.some((ms) => ms > replay.at + 500);
    group.querySelectorAll(".replay-speed").forEach((node) => node.setAttribute("aria-pressed", String(Number(node.dataset.speed) === replay?.speed)));
  });
  if (kept.slider) {
    const [min, max] = sliderBounds();
    kept.slider.min = String(min); kept.slider.max = String(max);
    if (!kept.dragging) kept.slider.value = String(active ? Math.min(Math.max(replay.at, min), max) : max);
    kept.slider.disabled = !replay.range.from;
    kept.time.textContent = active ? zoneTime(replay.at, false) : t("replay.liveNow");
    kept.day.value = timelineDay;
    const zone = displayZone();
    if (replay.range.from) { kept.day.min = dayOf(replay.range.from, zone); kept.day.max = dayOf(replay.now(), zone); }
  }
  updateClock();
}
function replayCard() {
  if (kept.replay) return kept.replay;
  kept.day = el("input", { type: "date", class: "day-input", "aria-label": t("replay.day") });
  kept.day.addEventListener("change", () => {
    if (!kept.day.value) return;
    timelineDay = kept.day.value;
    loadDayChanges();
    if (replay.active) startReplay(sliderBounds()[0]);
    render();
  });
  kept.slider = el("input", { type: "range", class: "replay-slider", step: "1000", "aria-label": t("replay.time") });
  kept.slider.addEventListener("pointerdown", () => { kept.dragging = true; });
  kept.slider.addEventListener("pointerup", () => { kept.dragging = false; });
  kept.slider.addEventListener("input", () => startReplay(Number(kept.slider.value)));
  kept.time = el("output", { class: "replay-time" });
  kept.replay = el("section", { class: "data-card replay-card" },
    el("div", { class: "replay-heading" }, el("h2", {}, t("replay.title")), el("p", {}, t("replay.help"))),
    el("div", { class: "replay-row" }, el("label", { class: "day-field" }, el("span", {}, t("replay.day")), kept.day),
      replayButtons(), kept.time),
    kept.slider);
  return kept.replay;
}
function changeNode(event) {
  const symbol = { reachable: "branches", unreachable: "branches" }[event.kind]
    || { working: "spark", thinking: "spark", waiting: "hand", idle: "coffee", error: "heart", completed: "check", unknown: "branches", limited: "clock" }[event.state] || "clock";
  const at = Date.parse(event.at);
  const later = replay.active && at > replay.at;
  return button([el("span", { class: "event-icon" }, icon(symbol)),
    el("span", { class: "event-text" }, el("time", { datetime: event.at }, zoneTime(at, false)),
      el("span", {}, el("strong", {}, event.name), " " + eventLabel(event)), event.project ? el("small", {}, event.project) : null)],
  "event change-event" + (later ? " later" : ""), () => startReplay(at, true), { "aria-label": t("replay.at", { time: zoneTime(at, false) }) + ", " + event.name + " " + eventLabel(event) });
}
function loadDayChanges() {
  const zone = displayZone();
  if (!timelineDay) timelineDay = dayOf(nowMs(), zone);
  const key = JSON.stringify([timelineDay, zone, replay.range.from]);
  const isToday = timelineDay === dayOf(replay.now(), zone);
  if (key === dayChangesKey && !(isToday && Date.now() - dayChangesAt > DAY_REFRESH)) return;
  if (!replay.range.from) return;
  dayChangesKey = key; dayChangesAt = Date.now();
  const [start, end] = [dayStart(timelineDay, zone), dayEnd(timelineDay, zone)];
  if (end <= replay.range.from) { dayChanges = { changes: [], agents: [], branches: [], truncated: false }; return; }
  // The whole day is asked for, so HQ clips it to now and serves every refresh and page from one result for a while.
  records.changes(Math.max(start, replay.range.from), end, "")
    .then((result) => { if (dayChangesKey === key) { dayChanges = result; render(); } })
    .catch(() => { if (dayChangesKey === key) { dayChangesKey = ""; dayChanges = null; } });
}
function renderTimeline(root) {
  loadDayChanges();
  const q = $("search").value.trim().toLowerCase();
  const list = dayEvents().filter((e) => !q || [e.name, e.project, eventLabel(e)].join(" ").toLowerCase().includes(q));
  const card = el("section", { class: "data-card" }, el("h2", {}, t("timeline.dayTitle", { day: dayLabel(timelineDay, displayZone()) })),
    !replay.range.from ? el("p", { class: "empty-list" }, t("replay.unavailable"))
      : el("div", { class: "timeline-list day-changes" }, list.length ? list.slice(0, MAX_DAY_CHANGES).map(changeNode)
        : el("p", { class: "empty-list" }, dayChanges ? t("timeline.none") : t("worklog.loading"))),
    list.length > MAX_DAY_CHANGES || dayChanges?.truncated ? el("p", { class: "detail-note" }, t("timeline.truncated", { n: Math.min(list.length, MAX_DAY_CHANGES) })) : null);
  // The list scrolls on its own; a refresh keeps its position.
  const scrolled = root.querySelector(".day-changes")?.scrollTop || 0;
  root.replaceChildren(replayCard(), card);
  const box = root.querySelector(".day-changes");
  if (box) box.scrollTop = scrolled;
  // A new replay time brings its latest change into view.
  if (box && replay.active && kept.scrolledFor !== replay.at) {
    kept.scrolledFor = replay.at;
    const reached = box.querySelector(".change-event:not(.later)");
    if (reached) box.scrollTop = reached.offsetTop;
  }
}
// Work log: one day in the chosen Branch's time zone, or browser time for all Branches.
function worklogZone() { return worklogBranch ? branchZone(live.branches.find((b) => b.branch_id === worklogBranch)?.branch?.time) : ""; }
function loadWorklog() {
  const zone = worklogZone();
  if (!worklogDay) worklogDay = dayOf(Date.now(), zone);
  const key = JSON.stringify([worklogDay, worklogBranch, zone]);
  const isToday = worklogDay === dayOf(Date.now(), zone);
  if (key === worklogKey && !(isToday && Date.now() - (worklogData?.loadedAt || 0) > TODAY_REFRESH)) return;
  worklogKey = key; worklogFailed = false;
  if (worklogData?.key !== key) worklogData = null;
  records.worklog(dayStart(worklogDay, zone), dayEnd(worklogDay, zone), worklogBranch)
    .then((result) => { if (worklogKey === key) { worklogData = { ...result, key, loadedAt: Date.now() }; render(); } })
    .catch(() => { if (worklogKey === key) { worklogFailed = true; worklogKey = ""; render(); } });
}
function worklogControls() {
  if (kept.worklog) return kept.worklog;
  kept.worklogBranch = el("select", { class: "worklog-branch-select", "aria-label": t("worklog.branch") });
  kept.worklogBranch.addEventListener("change", () => { worklogBranch = kept.worklogBranch.value; render(); });
  kept.worklogDay = el("input", { type: "date", class: "day-input", "aria-label": t("worklog.day") });
  kept.worklogDay.addEventListener("change", () => { if (kept.worklogDay.value) { worklogDay = kept.worklogDay.value; render(); } });
  const step = (days) => () => { worklogDay = shiftDay(worklogDay, days); render(); };
  kept.worklogZone = el("small", { class: "worklog-zone" });
  kept.worklog = el("div", { class: "worklog-controls" },
    el("label", { class: "day-field" }, el("span", {}, t("worklog.branch")), kept.worklogBranch),
    el("span", { class: "day-field" }, el("span", {}, t("worklog.day")),
      el("span", { class: "day-stepper" }, button(icon("left"), "icon-button", step(-1), { "aria-label": t("worklog.previousDay"), title: t("worklog.previousDay") }),
        kept.worklogDay, button(icon("right"), "icon-button", step(1), { "aria-label": t("worklog.nextDay"), title: t("worklog.nextDay") }))),
    kept.worklogZone);
  return kept.worklog;
}
function renderWorklog(root) {
  const controls = worklogControls();
  if (worklogBranch && !live.branches.some((b) => b.branch_id === worklogBranch)) worklogBranch = "";
  kept.worklogBranch.replaceChildren(el("option", { value: "" }, t("worklog.allBranches")),
    ...live.branches.map((b) => el("option", { value: b.branch_id }, branchName(b, live.branches))));
  kept.worklogBranch.value = worklogBranch;
  loadWorklog();
  const zone = worklogZone();
  kept.worklogDay.value = worklogDay;
  kept.worklogDay.max = dayOf(Date.now(), zone);
  kept.worklogZone.textContent = zone ? t("worklog.zoneBranch", { zone: zone.replaceAll("_", " ") }) : t("worklog.zoneBrowser");
  const q = $("search").value.trim().toLowerCase();
  const branches = new Map([...live.branches, ...(worklogData?.branches || [])].map((b) => [b.branch_id, b]));
  const rows = (worklogData?.rows || []).filter((r) => !q || [colleagueName(r), r.project_alias, branchName(branches.get(r.branch_id))]
    .join(" ").toLowerCase().includes(q));
  const start = replay.range.from;
  const outside = start && dayEnd(worklogDay, zone) <= start;
  const partial = start && !outside && dayStart(worklogDay, zone) < start;
  const body = worklogFailed ? el("p", { class: "empty-list" }, t("worklog.failed"))
    : !worklogData ? el("p", { class: "empty-list" }, t("worklog.loading"))
    : outside || !start ? el("p", { class: "empty-list" }, t("worklog.outside"))
    : rows.length ? worklogTable(rows, { colleague: colleagueName, branch: (id) => branchName(branches.get(id), [...branches.values()]),
      project: (r) => r.project_alias || t("project.unnamed"), badge, repository: repositoryTag })
    : el("p", { class: "empty-list" }, t("worklog.none"));
  root.replaceChildren(el("section", { class: "data-card worklog-card" }, el("h2", {}, t("worklog.title")), controls,
    partial ? el("p", { class: "detail-note" }, t("worklog.partial", { time: new Date(start).toLocaleString(locale(),
      { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", ...(zone ? { timeZone: zone } : {}) }) })) : null, body));
}
// Today's work log in browser time, for waiting times.
function refreshToday() {
  if (!records || !replay?.range.from) return;
  const day = dayOf(Date.now(), "");
  if (today.key === day && Date.now() - today.at < TODAY_REFRESH - 1000) return;
  today = { ...today, key: day, at: Date.now() };
  records.worklog(dayStart(day, ""), dayEnd(day, ""), "").then((data) => {
    if (today.key === day) { today = { key: day, data, at: Date.now() }; if (view === "dashboard" || view === "office") render(); }
  }).catch(() => { today = { key: "", data: today.data, at: 0 }; });
}
function setView(next) {
  if (next === "settings") { $("settings-dialog").showModal(); return; }
  if (!VIEWS.some(([id]) => id === next)) return;
  view = next;
  document.querySelectorAll(".nav-button").forEach((n) => {
    if (n.dataset.view === view) n.setAttribute("aria-current", "page"); else n.removeAttribute("aria-current");
  });
  text("breadcrumb-view", t("nav." + view)); text("page-title", t("view." + view + ".title"));
  text("page-description", t("view." + view + ".description"));
  text("page-eyebrow", t(view === "office" ? "view.office.eyebrow" : "view.other.eyebrow"));
  $("office-view").hidden = view !== "office"; $("activity-card").hidden = view !== "office";
  $("data-view").hidden = view === "office";
  if (view === "dashboard") refreshToday();
  render();
}
function setConnection(key, cls) {
  connection = [key, cls];
  $("connection").className = "connection " + cls;
  $("connection").replaceChildren(el("i", { class: "status-dot" }), t(key));
}
// Notification subjects carry only names, aliases, and provider initials.
function notificationSubjects(all, data) {
  return [...all.map((row) => ({ id: "colleague:" + row.key, kind: "colleague", state: row.state, since: row.activity?.state_since || "",
      name: row.name, provider: providerInitials(row.agent.provider), project: row.project, branch: row.branchName,
      target: { kind: "colleague", key: row.key, branchId: row.agent.branch_id } })),
    ...data.branches.map((b) => ({ id: "branch:" + b.branch_id, kind: "branch", reachable: Boolean(b.reachable),
      branch: branchName(b), target: { kind: "branch", branchId: b.branch_id } }))];
}
// A notification click shows the colleague in their Branch office, or the Branches view for a Branch.
function openNotified(target) {
  if ($("settings-dialog").open) $("settings-dialog").close();
  $("search").value = ""; stateFilter = "all"; roomFilter = "";
  if (replay?.active) replay.stop();
  if (target.kind === "branch") { setView("branches"); return; }
  if (current.branches.some((b) => b.branch_id === target.branchId)) { branchId = target.branchId; floor = 0; }
  selectEmployee(target.key);
  setView("office");
}
function acceptState(state) {
  if (!state || !["branches","agents","activities","contractors"].every((key) => Array.isArray(state[key]))) return false;
  live = state; connected = true;
  const all = rows(live);
  recordEvents(all);
  // While replaying, live states are recorded as a baseline: notifications are suppressed and the page is not repainted.
  if (!DEMO) { notifications?.observe(notificationSubjects(all, live), resync || Boolean(replay?.active)); resync = false; }
  if (replay?.active) return true;
  current = live;
  noteCompletions(all);
  render(); return true;
}
function connect(delay = 1000) {
  if (DEMO) return;
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(scheme + "://" + location.host + "/ws/v1/live");
  activeSocket = socket;
  // The viewer token travels in the first message, so it never appears in a URL or access log.
  socket.addEventListener("open", () => {
    everOpened = true; failedOpens = 0; resync = true;
    socket.send(JSON.stringify({ type: "auth", token: TOKEN || null }));
  });
  socket.addEventListener("message", (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.type === "state" && acceptState(message.state)) {
        delay = 1000;
        setConnection("connection.live", "live");
      }
    } catch { setConnection("connection.invalid", "disconnected"); }
  });
  socket.addEventListener("close", (event) => {
    if (activeSocket !== socket) return;
    connected = false; render();
    if (event.code === 4401) { setConnection("connection.token", "disconnected"); return; }
    if (event.code === 4403) { setConnection("connection.refused", "disconnected"); return; }
    // A socket that never opens may be a rejected token or a wrong HQ address; keep retrying.
    if (!everOpened && ++failedOpens >= 5) setConnection("connection.unreachable", "disconnected");
    else setConnection("connection.reconnecting", "disconnected");
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
  $("labels-toggle").setAttribute("aria-label", t(enabled ? "labels.hide" : "labels.show"));
  $("setting-labels").checked = enabled;
}
function changeZoom(value) {
  zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
  $("world").style.width = zoom + "%";
  text("zoom-reset", zoom + "%");
  $("zoom-out").disabled = zoom === MIN_ZOOM; $("zoom-in").disabled = zoom === MAX_ZOOM;
}
// Static strings, navigation, and mode text are rebuilt in place when the language changes.
function applyLanguage() {
  translateDocument();
  kept = {};
  buildBanner();
  $("setting-language").value = currentLanguage();
  $("navigation").replaceChildren(...VIEWS.map(([id,symbol]) =>
    button([icon(symbol), el("span", {}, t("nav." + id))], "nav-button", () => setView(id),
      { "data-view": id, "aria-label": t("nav." + id), title: t("nav." + id),
        ...(id === view ? { "aria-current": "page" } : {}) })));
  text("workspace-name", t(DEMO ? "workspace.demo" : "workspace.local"));
  text("workspace-mode", t(DEMO ? "workspace.toLive" : "workspace.live"));
  $("owner-avatar").title = t(DEMO ? "workspace.demo" : "workspace.local");
  text("settings-mode", t(DEMO ? "settings.demo" : "settings.live"));
  text("settings-mode-description", t(DEMO ? "settings.demoHelp" : "settings.liveHelp"));
  text("settings-mode-toggle", t(DEMO ? "settings.toLive" : "settings.toDemo"));
  setConnection(...connection);
  labels($("labels-toggle").getAttribute("aria-pressed") === "true");
  daylight?.relabel(); cats?.relabel(); notifications?.relabel();
  setView(view);
}
document.querySelectorAll("[data-icon]").forEach((node) => node.replaceChildren(icon(node.dataset.icon)));
$("setting-language").addEventListener("change", (event) => { setLanguage(event.target.value); applyLanguage(); });
document.querySelector(".brand").href = location.pathname + location.search + location.hash;
$("search").addEventListener("input", render);
$("branch-select").addEventListener("change", (event) => { branchId = event.target.value; floor = 0; roomFilter = ""; stateFilter = "all"; render(); });
$("all-employees").addEventListener("click", () => setView("employees"));
$("all-activity").addEventListener("click", () => setView("timeline"));
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && replay?.active && !$("settings-dialog").open) backToLive(); });
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
lounge = createLounge($("characters"), { motionAllowed });
walkers = createWalkers($("characters"), { motionAllowed, changed: render });
coffee = createCoffeeBreaks($("characters"),render,lounge);
notifications = createNotifications({ toggle: $("setting-notify"), status: $("setting-notify-status"), demo: DEMO, open: openNotified });
const demoNow = Date.now();
records = createHistory({ demo: DEMO, token: TOKEN, now: demoNow });
replay = createReplay({ history: records, shown: showReplay, moved: updateReplay });
if (DEMO) {
  acceptState(demoState(demoNow));
  connection = ["connection.demo", "demo"];
  $("demo-note").hidden = false;
}
changeZoom(100);
cats = createOfficeCats($("characters"));
applyLanguage();
decor = mountDecor($("world"));
furniture = mountFurniture($("world"));
furniture.update();
if (!DEMO) connect();
replay.refreshRange().then(() => { refreshToday(); render(); });
setInterval(() => replay.refreshRange(), TODAY_REFRESH);
setInterval(refreshToday, TODAY_REFRESH);
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
