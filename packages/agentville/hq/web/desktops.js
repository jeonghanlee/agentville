// Anonymous desktop contents share measured glass geometry and reported power overrides.
import { GEOMETRY } from "./office-modern-data.js";
import { DESK_SCREENS } from "./desk-screens.js";
import { screenArtwork } from "./presentations.js";

const NS = "http://www.w3.org/2000/svg";
const INTERVAL = [8000, 15000];
const VIEWS = [
  '<rect width="100" height="60" fill="#344b59"/><rect width="100" height="7" fill="#728b95"/>'
    + '<rect y="7" width="15" height="53" fill="#293e4b"/><path d="M21 16H57M29 24H83M29 32H69M21 40H61M29 48H78" stroke="#a6c9b7" stroke-width="3"/>',
  '<rect width="100" height="60" fill="#e8eeeb"/><rect width="100" height="9" fill="#8199a2"/>'
    + '<rect x="8" y="16" width="25" height="35" fill="#b9ceca"/><rect x="40" y="16" width="51" height="12" fill="#8baead"/>'
    + '<path d="M40 35H85M40 42H78M40 49H89" stroke="#a3b7bd" stroke-width="3"/>',
  '<rect width="100" height="60" fill="#e7ece5"/><path d="M12 14V49H91" fill="none" stroke="#9bafad" stroke-width="2"/>'
    + '<path d="M23 48V32H35V48M45 48V22H57V48M67 48V14H79V48" fill="#86aaa2"/>',
  '<rect width="100" height="60" fill="#303f43"/><rect width="100" height="8" fill="#6e8589"/>'
    + '<path d="M9 17H53M9 25H79M9 33H65M9 41H86M9 49H43" stroke="#acc6a0" stroke-width="3"/>'
    + '<rect x="49" y="46" width="5" height="5" fill="#d1bb83"/>',
];
const OFF = '<rect width="100" height="60" fill="#2a312e"/>';
const visibleIds = new Set(GEOMETRY.seats.filter((seat) => seat.kind === "desk" && seat.facing === "back")
  .map((seat) => seat.id));
const visibleScreens = DESK_SCREENS.filter((screen) => visibleIds.has(screen.id));
const states = new Map(visibleScreens.map((screen) => [screen.id, { slide: 0, revision: 0, next: 0, power: true }]));
const depths = new Map(GEOMETRY.seats.filter((seat) => seat.kind === "desk")
  .map((seat) => [seat.id, seat.hip[1] * 10 + (seat.facing === "front" ? 2 : -1)]));
const delay = () => INTERVAL[0] + Math.random() * (INTERVAL[1] - INTERVAL[0]);
const content = (state) => state.power ? VIEWS[state.slide] : OFF;
const markup = (scope, screen) => {
  const state = states.get(screen.id);
  return screenArtwork(scope, screen, state, content(state), "desk");
};

// Source-copy clips exclude unrelated monitor markup without changing the artwork masks.
export function deskArtwork(scope, clips = null) {
  let area = null;
  if (clips) {
    const points = clips.flatMap((shape) => typeof shape === "string"
      ? shape.trim().split(/\s+/).map((point) => point.split(",").map(Number)) : shape);
    if (!points.length) return "";
    area = [Math.min(...points.map(([x]) => x)), Math.min(...points.map(([,y]) => y)),
      Math.max(...points.map(([x]) => x)), Math.max(...points.map(([,y]) => y))];
  }
  return visibleScreens.filter((screen) => !area || !(Math.max(...screen.quad.map(([x]) => x)) < area[0]
    || Math.min(...screen.quad.map(([x]) => x)) > area[2] || Math.max(...screen.quad.map(([,y]) => y)) < area[1]
    || Math.min(...screen.quad.map(([,y]) => y)) > area[3])).map((screen) => markup(scope, screen)).join("");
}

export function mountDesktops(world, { motionAllowed, paused }) {
  for (const screen of visibleScreens) {
    const state = states.get(screen.id);
    state.slide = Math.floor(Math.random() * VIEWS.length);
    state.next = Date.now() + delay();
    const layer = document.createElementNS(NS, "svg");
    layer.setAttribute("viewBox", "0 0 1536 1024");
    layer.setAttribute("class", "artwork-patch desk-display-layer");
    layer.setAttribute("aria-hidden", "true");
    layer.style.zIndex = String(depths.get(screen.id));
    layer.innerHTML = markup("desk-base-" + screen.id, screen);
    world.append(layer);
  }
  let suspended = false;
  const inactive = () => document.hidden || !world.getClientRects().length || !motionAllowed() || paused();
  const draw = (changed) => world.querySelectorAll("[data-desk-screen]").forEach((node) => {
    if (!changed.has(node.dataset.deskScreen)) return;
    const state = states.get(node.dataset.deskScreen);
    node.dataset.slide = state.slide; node.dataset.revision = state.revision;
    node.dataset.power = state.power ? "on" : "off";
    node.querySelector("[data-desk-content]").innerHTML = content(state);
  });
  draw(new Set(states.keys()));
  return {
    update(disabled) {
      const changed = new Set();
      for (const [id, state] of states) {
        const power = !disabled.has(id);
        if (state.power === power) continue;
        state.power = power; state.next = Date.now() + delay(); changed.add(id);
      }
      if (changed.size) draw(changed);
    },
    pause() { suspended = true; },
    tick() {
      if (inactive()) { suspended = true; return; }
      const now = Date.now();
      if (suspended) {
        for (const state of states.values()) state.next = now + delay();
        suspended = false; return;
      }
      const changed = new Set();
      for (const [id, state] of states) {
        if (!state.power || now < state.next) continue;
        state.slide = (state.slide + 1 + Math.floor(Math.random() * (VIEWS.length - 1))) % VIEWS.length;
        state.revision++; state.next = now + delay(); changed.add(id);
      }
      if (changed.size) draw(changed);
    },
  };
}
