import { icon } from "./art.js";
import { t } from "./i18n.js";
import { WINDOWS, LAMPS } from "./office-layout.js";

const PERIODS = [
  { name: "morning", start: 5, end: 10, icon: "sun" },
  { name: "day", start: 10, end: 17, icon: "sun" },
  { name: "evening", start: 17, end: 20, icon: "sun" },
  { name: "night", start: 20, end: 29, icon: "moon" },
];
const ZONES = new Map();
const STARS = WINDOWS.map((points) => {
  const corners = points.split(" ").map((point) => point.split(",").map(Number));
  return [0,1].map((axis) => corners.reduce((sum,point) => sum+point[axis],0)/corners.length);
});

// A real IANA zone in Branch `time` drives day and night; fictional labels fall back to browser-local time.
export function branchZone(value) {
  if (!value || typeof value !== "string") return "";
  if (!ZONES.has(value)) {
    try { ZONES.set(value, new Intl.DateTimeFormat("en-US", { timeZone: value, hour: "numeric", hourCycle: "h23" })); }
    catch { ZONES.set(value, null); }
  }
  return ZONES.get(value) ? value : "";
}

function hourIn(now, zone) {
  const part = zone && ZONES.get(zone)?.formatToParts(now).find((item) => item.type === "hour");
  return part ? Number(part.value) % 24 : now.getHours();
}

export function createDaylight(world, scene, label, symbol, setting) {
  const layer = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  layer.setAttribute("viewBox", "0 0 1536 1024");
  layer.setAttribute("class", "daylight-layer");
  layer.setAttribute("aria-hidden", "true");
  layer.innerHTML = '<defs><clipPath id="office-window-glass">'
    + WINDOWS.map((points) => '<polygon points="' + points + '"/>').join("")
    + '</clipPath><linearGradient id="window-sky" x2="0" y2="1"><stop class="sky-top"/><stop class="sky-bottom" offset="1"/></linearGradient>'
    + '<radialGradient id="lamp-light"><stop stop-color="#ffcb75" stop-opacity=".65"/><stop offset=".35" stop-color="#ffd898" stop-opacity=".18"/><stop offset="1" stop-color="#ffe3ae" stop-opacity="0"/></radialGradient></defs>'
    + '<g clip-path="url(#office-window-glass)"><rect class="window-tint" width="1536" height="1024" fill="url(#window-sky)"/>'
    + '<g class="night-sky" fill="#f3ebc9"><path transform="translate(' + STARS[0].join(' ') + ')" d="M0 0a11 11 0 1 0 9 18 10 10 0 0 1-9-18Z"/>'
    + STARS.map(([x,y]) => '<circle cx="' + x + '" cy="' + y + '" r="1.3"/>').join("")
    + '</g></g><g class="lamp-glow">'
    + LAMPS.map(([x,y,r]) => '<circle cx="' + x + '" cy="' + y + '" r="' + r + '" fill="url(#lamp-light)"/>').join("") + '</g>';
  world.append(layer);
  let active = "", zone = "";
  function update(now = new Date(), timeZone = zone) {
    zone = branchZone(timeZone);
    const local = hourIn(now, zone);
    const hour = local < 5 ? local + 24 : local;
    const period = PERIODS.find((item) => item.name === setting.value)
      || PERIODS.find((item) => hour >= item.start && hour < item.end);
    if (active === period.name) return;
    active = period.name;
    scene.dataset.daylight = active;
    label.textContent = t("daylight." + active);
    symbol.replaceChildren(icon(period.icon));
  }
  setting.addEventListener("change", () => update());
  update();
  // A language change rewrites the period caption without waiting for the next period.
  function relabel() { if (active) label.textContent = t("daylight." + active); }
  return { update, relabel };
}
