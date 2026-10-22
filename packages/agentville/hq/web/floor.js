// Walkable floor of office.png in percent of the artwork (x of width, y of height).
// Walkers move only along these connections, which keep their feet off furniture footprints.
export const FLOOR_ASPECT = 1024 / 1536;

function ellipse(cx, cy, rx, ry, sides = 14) {
  return Array.from({ length: sides }, (_, i) => {
    const angle = i / sides * Math.PI * 2;
    return [+(cx + Math.cos(angle) * rx).toFixed(2), +(cy + Math.sin(angle) * ry).toFixed(2)];
  });
}
const box = (x0, y0, x1, y1) => [[x0,y0],[x1,y0],[x1,y1],[x0,y1]];

// Floor contact of furniture, walls, and posts, measured against office.png.
export const FOOTPRINTS = {
  "studio-back-wall": [[14,0],[62,0],[62,25.5],[59,26.5],[47.5,28.6],[43,25.2],[24,18.6],[14,22]],
  "studio-shelves": [[0,20],[16,20],[16,40],[0,46]],
  "studio-desk": [[17.5,31],[19.5,29],[48,39.5],[48,45.8],[42,48],[17.5,38]],
  "studio-chair-near-a": box(22.5,37.6,27.5,41.6),
  "studio-chair-near-b": box(32,42.4,37,46.6),
  "studio-chair-far-a": box(31.5,23.6,35.5,27),
  "studio-chair-far-b": box(40.3,30.6,44,34),
  "studio-plant-desk": box(43.2,40.3,46,43.6),
  "studio-plant-window": box(42.8,24,46.2,27.6),
  "studio-cabinet": [[47.5,29.5],[49.5,27.3],[60.3,32.3],[58.3,34.6]],
  "studio-plant-corner": box(57.5,32.5,61,36),
  "lounge-walls": [[44.8,60],[55,54.4],[66.6,60.4],[66.6,62.8],[63.6,63.5],[60,62.5],[50.4,58.7],[50,62.4],[47,62.5],[44.8,61.8]],
  "lounge-right-door": box(65,60.6,69.6,63),
  "lounge-lamp-table": [[40.3,67.5],[43.8,62.3],[45.4,67.5],[42.6,71.2]],
  "sofa": [[45,68.5],[47,63.6],[63.3,69.8],[59,76.8]],
  "coffee-table": ellipse(48.5,75.3,4.5,3),
  "ottoman": ellipse(51.8,82.8,2.6,1.8),
  "lounge-chair": [[55.6,81],[59.5,77.8],[62.2,79.3],[58.6,84.7]],
  "lounge-side-table": [[61.3,77],[63.5,75.8],[65.5,77.4],[63.3,80.2]],
  "corridor-door": [[35.4,62.9],[38.8,60.8],[39.3,61.8],[35.9,63.9]],
  "corridor-post": box(33.5,64.6,35.6,67),
  "common-shelf-wall": [[21,74],[34.8,65],[35,67.5],[24.5,74.3],[22.8,76]],
  "common-post": box(20.8,73.4,22.9,75.8),
  "common-desk": [[6.5,51],[12,46],[33,56],[22.9,61.6],[21,61.6],[6.5,55.2]],
  "common-chair-a": box(9.5,58.6,14.5,62.6),
  "common-chair-b": box(17,63.6,21,67.6),
  "common-plant": box(4,59.5,7,62.6),
  "common-back-wall": [[0,0],[14,0],[14,44],[1.5,62.8],[0,62.8]],
  "studio1-post": box(61.3,39.4,62.9,42.1),
  "studio1-lamp": box(62.3,39,65.8,41.6),
  "studio1-plant": box(65.5,35.5,68.5,38.6),
  "studio1-desk": [[64.5,35.5],[66.5,32],[88,42.5],[85.5,45.8]],
  "studio1-chair-a": box(73.5,39,78.5,42.6),
  "studio1-chair-b": box(81.5,44.6,86.5,48.6),
  "studio1-back-wall": [[62,0],[100,0],[100,40],[88,40],[62,26]],
  "infirmary-back-wall": [[69.6,47],[86,51.8],[86,56],[71.8,62]],
  "infirmary-wall": [[69.6,47],[71.8,47],[74.8,79.5],[71.8,81],[69.6,81]],
  "infirmary-cabinet": [[74.8,68.5],[77.3,66.5],[80.8,68.5],[78.3,71.8]],
  "bed": [[79.5,66.5],[82.5,60.5],[92.8,66.5],[88.6,73.8]],
  "infirmary-plant": box(90.5,67.4,93.6,70.6),
  "infirmary-basket": box(85,72.4,88.2,75.2),
};

export const NODES = {
  // Project room on the left: in front of and behind the long desk.
  s0a: [24.5,44.5], s0b: [33.5,50], s0c: [40,53], s0d: [48.5,48.5], s0e: [50,38.6], s0f: [46.2,31], s0g: [38,27.4],
  // Aisle behind the lounge to the project room on the right.
  a1: [55,42], a2: [60.5,42.6], a3: [67,44.4], s1a: [72,45.2], s1b: [80,48.2],
  // Corridor, lounge, and the strip behind the sofa to the coffee counter.
  c1: [40,58.4], c2: [38.8,66.6], c3: [37.5,75], c4: [43.4,73.4], c5: [43.5,81], c6: [47,86.6], c7: [55,88.2],
  c8: [62.6,85.6], c9: [67.3,80], c10: [66.8,70], c11: [64.6,65.7], m1: [60.5,65.8], machine: [54.5,62.9],
  f0: [46.6,71], f2: [55.2,77.1],
  // Common Office, entered along its open front edge.
  k0: [11.5,65.6], k1: [18.5,70.6], k2: [19.8,75.6], k3: [24.5,78.3],
  // Infirmary, entered below its open door.
  i1: [72.8,83.3], i2: [78.5,80.6], i3: [82.2,73.8],
};

export const LINKS = [
  ["s0a","s0b"], ["s0b","s0c"], ["s0c","s0d"], ["s0d","s0e"], ["s0e","s0f"], ["s0f","s0g"],
  ["s0d","a1"], ["a1","a2"], ["a2","a3"], ["a3","s1a"], ["s1a","s1b"],
  ["s0c","c1"], ["c1","c2"], ["c2","c3"], ["c2","c4"], ["c3","c4"], ["c4","f0"], ["c3","c5"], ["c4","c5"],
  ["c5","c6"], ["c6","c7"], ["c7","f2"], ["c7","c8"], ["c8","c9"], ["c9","c10"], ["c10","c11"], ["c11","m1"], ["m1","machine"],
  ["c3","k3"], ["k3","k2"], ["k2","k1"], ["k1","k0"], ["c9","i1"], ["i1","i2"], ["i2","i3"],
];

// The free side of each seat, where a walker stands before sitting down and after getting up.
export const APPROACH = {
  studio0: ["s0a", "s0b", "s0g", "s0f"],
  studio1: ["s1a", "s1b"],
  common: ["k0", "k1"],
  fika: ["f0", "c8", "f2"],
  infirmary: ["i3"],
};
export const COFFEE_SPOT = NODES.machine;

const neighbours = new Map(Object.keys(NODES).map((id) => [id, []]));
for (const [a,b] of LINKS) { neighbours.get(a).push(b); neighbours.get(b).push(a); }
export const neighbourIds = (id) => neighbours.get(id) || [];

export function distance(a, b) {
  return Math.hypot(b[0]-a[0], (b[1]-a[1]) * FLOOR_ASPECT);
}

function inside(point, polygon) {
  let hit = false;
  for (let i = 0, j = polygon.length-1; i < polygon.length; j = i++) {
    const [xi,yi] = polygon[i], [xj,yj] = polygon[j];
    if ((yi > point[1]) !== (yj > point[1]) && point[0] < (xj-xi) * (point[1]-yi) / (yj-yi) + xi) hit = !hit;
  }
  return hit;
}

export function blockedBy(point) {
  return Object.keys(FOOTPRINTS).find((name) => inside(point, FOOTPRINTS[name])) || "";
}

// A straight step is clear when sampled feet positions stay outside every footprint.
export function clear(a, b) {
  const steps = Math.max(1, Math.ceil(distance(a, b) / .2));
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    if (blockedBy([a[0] + (b[0]-a[0]) * t, a[1] + (b[1]-a[1]) * t])) return false;
  }
  return true;
}

function nearestClear(point) {
  return Object.keys(NODES).filter((id) => clear(point, NODES[id]))
    .sort((x, y) => distance(point, NODES[x]) - distance(point, NODES[y]))[0]
    || Object.keys(NODES).sort((x, y) => distance(point, NODES[x]) - distance(point, NODES[y]))[0];
}

function shortest(from, to) {
  const cost = new Map([[from, 0]]), previous = new Map(), open = new Set([from]);
  while (open.size) {
    const id = [...open].reduce((best, next) => cost.get(next) < cost.get(best) ? next : best);
    open.delete(id);
    if (id === to) break;
    for (const next of neighbours.get(id)) {
      const total = cost.get(id) + distance(NODES[id], NODES[next]);
      if (total < (cost.get(next) ?? Infinity)) { cost.set(next, total); previous.set(next, id); open.add(next); }
    }
  }
  const ids = [to];
  while (ids[0] !== from && previous.has(ids[0])) ids.unshift(previous.get(ids[0]));
  return ids[0] === from ? ids : [from, to];
}

// Route between two floor points through the connection graph.
export function route(from, to) {
  if (distance(from, to) < .05) return [from];
  if (clear(from, to) && distance(from, to) < 6) return [from, to];
  const start = nearestClear(from), end = nearestClear(to);
  const points = [from, ...shortest(start, end).map((id) => NODES[id]), to];
  // Drop corners that a clear straight step can skip, so walkers do not zigzag.
  const path = [points[0]];
  let index = 0;
  while (index < points.length-1) {
    let next = points.length-1;
    while (next > index+1 && !clear(points[index], points[next])) next--;
    path.push(points[next]);
    index = next;
  }
  return path.filter((point, i) => i === 0 || distance(point, path[i-1]) > .01);
}
