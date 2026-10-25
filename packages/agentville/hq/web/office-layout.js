// Source-pixel measurements shared by placement, artwork overlays and circulation.
import { GEOMETRY } from "./office-modern-data.js";
import { GRAPH } from "./office-modern-graph.js";
import { pointPercent } from "./layout.js";

export const FLOOR = GEOMETRY.floor.map(pointPercent);
export const FOOTPRINTS = Object.fromEntries(Object.entries(GEOMETRY.contacts).map(([name, points]) => [name, points.map(pointPercent)]));
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
  { footprint: "north-meeting-west", polygon: [[974,185],[1110,106],[1114,213],[984,293],[974,293]] },
  { footprint: "north-meeting-back", polygon: [[1106,106],[1326,231],[1326,312],[1319,318],[1106,201]] },
  { footprint: "meeting-separator", polygon: [[1177,336],[1337,228],[1353,239],[1348,324],[1197,434],[1177,434]] },
  { footprint: "east-meeting-back", polygon: [[1340,232],[1519,333],[1519,435],[1510,441],[1340,337]] },
  { footprint: "meeting-kitchen", polygon: [[1033,387],[1046,381],[1386,568],[1386,665],[1373,673],[1033,485]] },
  { footprint: "work-fika-divider", polygon: [[636,503],[650,496],[749,552],[749,599],[736,607],[636,550]] },
  { footprint: "kitchen", polygon: [[1038,448],[1061,430],[1424,633],[1424,685],[1401,703],[1038,495]] },
  { footprint: "fridge", polygon: [[1382,614],[1415,589],[1451,612],[1465,736],[1418,768],[1382,745]] },
]);

export const WINDOWS = [
  "54,268 242,160 242,206 54,314", "342,104 437,50 437,96 342,151",
  "485,65 583,119 583,157 485,103", "686,118 801,52 801,100 686,166",
  "842,64 938,117 938,153 842,102", "994,100 1072,55 1072,99 994,145",
  "1120,60 1305,163 1305,202 1120,100", "1366,271 1479,333 1479,377 1366,315",
];
export const LAMPS = [[181,247,28],[193,300,28],[249,337,28],[425,112,28],[480,139,28],
  [436,165,28],[493,196,28],[791,107,28],[850,138,28],[800,161,28],[855,196,28],
  [557,307,28],[619,342,28],[684,378,28],[750,417,28],[664,327,28],[727,364,28],[794,401,28],
  [1084,183,35],[1284,330,35],[315,493,35]];
export const FRAMES = [
  { name: "window-west", quad: [[299,149],[320,137],[320,172],[299,185]], depth: 1 },
  { name: "meeting-north", quad: [[1021,188],[1045,174],[1045,205],[1021,219]], depth: 1 },
  { name: "meeting-east", quad: [[1221,350],[1242,337],[1242,367],[1221,381]], depth: 1 },
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
