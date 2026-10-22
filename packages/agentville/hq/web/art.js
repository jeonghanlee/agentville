import { employeeSprite, catSprite } from "./sprites.js";
// Static artwork only. Runtime strings never enter SVG markup.
const NS = "http://www.w3.org/2000/svg";
const ICONS = {
  house: '<path d="m3 10 9-7 9 7v10H3z"/><path d="M9 20v-7h6v7M7 8V4h3"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  people: '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5"/>',
  folder: '<path d="M3 7V5h6l2 3h10v12H3z"/><path d="M3 8h8"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  branches: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><path d="M6.5 10v7h7.5M14 6h6v4"/>',
  settings: '<path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h5l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3z"/><circle cx="11.5" cy="12" r="3"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  moon: '<path d="M19 15A8 8 0 0 1 9 5a8 8 0 1 0 10 10Z"/>',
  sprout: '<path d="M12 22V11m0 5C4 16 2 11 3 6c7 0 9 4 9 10Zm0-5C12 4 16 2 22 3c0 6-4 9-10 8Z"/>',
  right: '<path d="m9 5 7 7-7 7"/>', left: '<path d="m15 5-7 7 7 7"/>',
  chevrons: '<path d="m8 8 4-4 4 4m-8 8 4 4 4-4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>',
  tag: '<path d="m3 3 8 1 10 10-7 7L4 11z"/><circle cx="8" cy="8" r="1"/>',
  pointer: '<path d="m5 3 15 10-7 1-3 7z"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  coffee: '<path d="M4 8h12v8a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4zm12 1h2a3 3 0 0 1 0 6h-2M7 2v3m5-3v3M2 22h18"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  hand: '<path d="M8 13V5a2 2 0 0 1 4 0v6-8a2 2 0 0 1 4 0v9-6a2 2 0 0 1 4 0v9c0 5-3 7-7 7-3 0-5-2-7-5l-3-5a2 2 0 0 1 3-2z"/>',
  heart: '<path d="M12 21 3 12C-2 5 6-1 12 6c6-7 14-1 9 6z"/>',
  spark: '<path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3z"/>',
};
const LOOKS = [
  { hair: "#654737", light: "#8a6044", shirt: "#b67c57", dark: "#8c5b40", skin: "#efc49a", bg: "#eee2d2", style: 0 },
  { hair: "#463d3e", light: "#665452", shirt: "#7f9570", dark: "#5b7350", skin: "#e9b58d", bg: "#e3ebdc", style: 1 },
  { hair: "#9e6437", light: "#be8652", shirt: "#8995ad", dark: "#68748e", skin: "#f5d6b0", bg: "#e5e8ef", style: 2 },
  { hair: "#3c3936", light: "#605a50", shirt: "#ac90ac", dark: "#88718c", skin: "#c88e66", bg: "#ede5ed", style: 3 },
  { hair: "#79704d", light: "#a79966", shirt: "#caad67", dark: "#a28a4e", skin: "#efc49a", bg: "#f2ebd3", style: 4 },
  { hair: "#4e4846", light: "#73645e", shirt: "#6f9a94", dark: "#527b78", skin: "#efbc98", bg: "#e0ece7", style: 5 },
];
const VARIATIONS = [
  { hair: "#cfc3ae", light: "#eee4cf", bg: "#eee5d8" },
  { hair: "#76516c", light: "#9d7890", bg: "#eee0ea" },
  { hair: "#bd7771", light: "#db9d92", bg: "#f2e1de" },
  { hair: "#aaa6a2", light: "#d0cbc2", bg: "#e8e5ed" },
  { hair: "#c89a4b", light: "#e6bd71", bg: "#f3ead0" },
  { hair: "#353e53", light: "#626c80", bg: "#e0e6ef" },
];
LOOKS.push(...VARIATIONS.map((variation, index) => ({
  ...LOOKS[index], ...variation, suffix: "-varied",
})));
const assignedLooks = new Map();

export function icon(name) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name] || ICONS.grid;
  return svg;
}

function appearanceHash(seed) {
  const hash = Array.from(String(seed)).reduce((sum, ch) => (sum * 31 + ch.charCodeAt(0)) >>> 0, 0);
  return hash % LOOKS.length;
}

// Balance the complete roster before filters, while retaining existing identities.
export function prepareAppearances(seeds) {
  const keys = [...new Set(seeds)].sort();
  const counts = LOOKS.map(() => 0);
  keys.forEach((key) => {
    if (assignedLooks.has(key)) counts[assignedLooks.get(key)]++;
  });
  for (const key of keys) {
    if (assignedLooks.has(key)) continue;
    const start = appearanceHash(key), minimum = Math.min(...counts);
    const offset = LOOKS.findIndex((_, index) => counts[(start + index) % LOOKS.length] === minimum);
    const index = (start + offset) % LOOKS.length;
    assignedLooks.set(key, index);
    counts[index]++;
  }
}

function look(seed) {
  return LOOKS[assignedLooks.get(seed) ?? appearanceHash(seed)];
}

export function avatarColor(seed) {
  return look(seed).bg;
}

export function character(seed, state = "idle", detail = "", condition = "normal", contractor = false, desk = "", workstation = null, cup) {
  const appearance = look(seed);
  const sprite = employeeSprite(appearance, state, detail, condition, contractor, desk, workstation, cup);
  sprite.dataset.look = String(LOOKS.indexOf(appearance));
  return sprite;
}

export function catArtwork(coat) {
  return catSprite(coat);
}
