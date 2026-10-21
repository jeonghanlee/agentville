import { icon } from "./art.js";

const PERIODS = [
  { name: "morning", start: 5, end: 10, label: "A little morning sunshine", icon: "sun" },
  { name: "day", start: 10, end: 17, label: "Daylight at the office", icon: "sun" },
  { name: "evening", start: 17, end: 20, label: "A warm evening glow", icon: "sun" },
  { name: "night", start: 20, end: 29, label: "A quiet night at the office", icon: "moon" },
];
const WINDOWS = [
  "363,91 391,77 391,191 363,206", "398,73 432,56 432,177 398,192",
  "470,43 514,60 514,190 470,174", "524,65 574,84 574,212 524,194",
  "584,88 633,107 633,231 584,214",
  "1026,199 1053,184 1053,326 1026,341", "1063,178 1094,160 1094,310 1063,325",
  "1374,517 1401,528 1401,625 1374,614", "1409,531 1435,542 1435,639 1409,628",
];
const LAMPS = [[493,302,42],[641,361,42],[854,267,65],[1006,300,80],[1124,290,45],[165,517,45],[675,566,85],[899,454,55],[1340,583,60]];

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
    + '<g class="night-sky" fill="#f3ebc9"><path d="M551 80a11 11 0 1 0 9 18 10 10 0 0 1-9-18Z"/>'
    + [[484,78],[538,115],[600,126],[374,115],[420,95],[1075,201],[1041,251],[1385,545],[1421,568]].map(([x,y]) => '<circle cx="' + x + '" cy="' + y + '" r="1.3"/>').join("")
    + '</g></g><g class="lamp-glow">'
    + LAMPS.map(([x,y,r]) => '<circle cx="' + x + '" cy="' + y + '" r="' + r + '" fill="url(#lamp-light)"/>').join("") + '</g>';
  world.append(layer);
  let active = "";
  function update(now = new Date()) {
    const hour = now.getHours() < 5 ? now.getHours() + 24 : now.getHours();
    const period = PERIODS.find((item) => item.name === setting.value)
      || PERIODS.find((item) => hour >= item.start && hour < item.end);
    if (active === period.name) return;
    active = period.name;
    scene.dataset.daylight = active;
    label.textContent = period.label;
    symbol.replaceChildren(icon(period.icon));
  }
  setting.addEventListener("change", () => update());
  update();
  return { update };
}
