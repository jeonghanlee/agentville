// Source-pixel measurements shared by placement, artwork overlays and circulation.
import { GEOMETRY } from "./office-modern-data.js";
import { GRAPH } from "./office-modern-graph.js";
import { pointPercent } from "./layout.js";

export const FLOOR = GEOMETRY.floor.map(pointPercent);
export const FOOTPRINTS = Object.fromEntries(Object.entries({ ...GEOMETRY.contacts,
  "cat-bed-cheese": [[448,723],[456,713],[476,710],[489,718],[492,733],[483,748],[464,751],[450,742]],
  "cat-bed-pepper": [[488,753],[495,742],[516,739],[529,747],[532,762],[522,777],[503,780],[490,771]],
  "cat-bowls": [[441,770],[459,769],[483,774],[486,784],[483,797],[459,798],[441,790]],
}).map(([name, points]) => [name, points.map(pointPercent)]));
export const NODES = GRAPH.nodes;
export const LINKS = GRAPH.links;
export const COFFEE_NODE = "coffee";
export const ENTRANCE = NODES.entrance;
export const CAT_NODES = Array.from({ length: 6 }, (_, i) => "cat:" + i);
export const DESK_ROOMS = ["studio0", "studio1", "studio2", "studio3"];
export const MEETING_ROOMS = [{ id: "meeting", capacity: 6 }, { id: "meeting-east", capacity: 6 }];
const WORK_AREAS = { "window-left": "studio0", "window-middle": "studio1", "window-right": "studio2", center: "studio3" };
const MONITORS = {
  "window-left": [[192,242],[220,258],[219,282],[190,267]],
  "window-middle": [[444,111],[475,129],[474,150],[442,132]],
  "window-right": [[802,110],[832,127],[831,150],[800,133]],
  center: [[608,292],[641,310],[640,334],[606,315]],
};
const MONITOR_STEPS = { "window-left": [65,36], "window-middle": [61,35], "window-right": [61,36], center: [65,37] };
const points = (polygon) => polygon.map((point) => point.join(",")).join(" ");
let fikaIndex = 0;
export const SEATS = GEOMETRY.seats.map((entry) => {
  const [area, index] = entry.id.split("."), access = GRAPH.seats.find((item) => item.id === entry.id);
  const room = WORK_AREAS[area] || (area === "meeting-north" ? "meeting" : area === "meeting-east" ? area : "fika");
  let monitor = entry.monitor;
  if (entry.kind === "desk" && entry.facing === "front" && !monitor) {
    const offset = Number(index) - (area === "center" ? 4 : 2), step = MONITOR_STEPS[area];
    monitor = MONITORS[area].map(([x,y]) => [x + step[0] * offset, y + step[1] * offset]);
  }
  return { ...entry, id: room + "." + (room === "fika" ? fikaIndex++ : index), sourceId: entry.id, scene: "main",
    position: pointPercent(entry.hip), depth: Math.round(entry.hip[1] * 10), approach: "seat:" + entry.id,
    footprints: entry.own, foot: pointPercent(access.foot), workstation: entry.keys || null,
    screen: monitor ? points(monitor) : null, monitor };
});

export const SURFACES = SEATS.flatMap((seat) => {
  const surfaces = [];
  if (seat.back) surfaces.push({ name: seat.sourceId + "-back", depth: seat.depth + 1,
    footprint: seat.footprints.find((id) => id.endsWith("-chair")) || seat.footprints[0], shapes: [points(seat.back)] });
  if (seat.monitor) surfaces.push({ name: seat.sourceId + "-monitor", depth: seat.depth + 2,
    footprint: seat.footprints[0], shapes: [points(seat.monitor)] });
  return surfaces;
}).concat(GEOMETRY.surfaces.map((surface) => ({ name: surface.name, depth: surface.depth,
  footprint: surface.name === "sofa-south-back" ? "sofa-south" : surface.name === "lounge-coffee-table" ? "coffee-table" : surface.name,
  shapes: [points(surface.polygon)] })));

// Walking occlusion is applied to each moving actor, leaving seated hands above their measured keyboards.
export const WALK_SURFACES = Object.entries(GEOMETRY.tabletops).map(([name, polygon]) => {
  const kind = name.startsWith("meeting") ? "meeting" : name.startsWith("fika") ? "fika" : "desk";
  const drop = GEOMETRY.table_floor_drop[kind], [a,b,c,d] = polygon;
  return { footprint: name + "-table", polygon: [a,b,c,[c[0],c[1]+drop],[d[0],d[1]+drop],[a[0],a[1]+drop]] };
}).concat([
  ...GEOMETRY.surfaces.filter((surface) => surface.name === "north-meeting-west" || surface.name === "meeting-separator")
    .map((surface) => ({ footprint: surface.name, polygon: surface.polygon })),
  { footprint: "work-fika-divider", polygon: [[636,503],[650,496],[749,552],[749,599],[736,607],[636,550]] },
  { footprint: "kitchen", polygon: [[1038,448],[1061,430],[1424,633],[1424,685],[1401,703],[1038,495]] },
  { footprint: "fridge", polygon: [[1382,614],[1415,589],[1451,612],[1465,736],[1418,768],[1382,745]] },
]);

export const WINDOWS = [
  "54,268 242,160 242,206 54,314", "342,104 437,50 437,96 342,151",
  "485,65 583,119 583,157 485,103", "686,118 801,52 801,100 686,166",
  "842,64 938,117 938,153 842,102", "1118,65 1480,273 1480,348 1338,266 1338,213 1324,205 1282,234 1118,139",
];
export const LAMPS = [[315,493,35]];
export const FRAMES = [
  { name: "window-west", quad: [[299,149],[320,137],[320,172],[299,185]], depth: 1 },
  { name: "lounge", quad: [[249,482],[283,463],[283,501],[249,521]], depth: 1 },
];

export const ROOM_LAYOUT = {
  studio0: { color: "#adba88", overflow: pointPercent([331,402]) },
  studio1: { color: "#b8a4c8", overflow: pointPercent([577,255]) },
  studio2: { color: "#d9c27a", overflow: pointPercent([931,257]) },
  studio3: { color: "#cf9aa0", overflow: pointPercent([846,533]) },
  common: { color: "#c8b994", overflow: pointPercent([590,755]) },
  fika: { color: "#d1a178", overflow: pointPercent([1090,801]) },
  meeting: { color: "#93b7a6", overflow: pointPercent([1079,398]) },
  "meeting-east": { color: "#93b7a6", overflow: pointPercent([1320,570]) },
};
export const WAITING_SPOTS = { fika: Array.from({ length: 6 }, (_, i) => NODES["waiting:" + i]) };
