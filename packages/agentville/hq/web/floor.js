// Walkable floor of office.png in percent of the artwork (x of width, y of height).
// Walkers move only along these connections, which keep a walker's feet off furniture footprints.
export const FLOOR_ASPECT = 1024 / 1536;

function ellipse(cx, cy, rx, ry, sides = 16) {
  return Array.from({ length: sides }, (_, i) => {
    const angle = i / sides * Math.PI * 2;
    return [+(cx + Math.cos(angle) * rx).toFixed(2), +(cy + Math.sin(angle) * ry).toFixed(2)];
  });
}
const box = (x0, y0, x1, y1) => [[x0,y0],[x1,y0],[x1,y1],[x0,y1]];

// Floor contact of furniture, walls, and posts, measured against office.png: legs, pedestals, and wheel bases,
// with table and desk tops projected down to the floor where they overhang.
export const FOOTPRINTS = {
  "studio-back-wall": [[14,0],[62,0],[62,25.5],[59,26.5],[47.5,28.6],[43,25.2],[24,18.6],[14,22]],
  "studio-shelves": [[0,20],[16,20],[16,40],[0,46]],
  "studio-desk": [[18.2,34.9],[19.4,31.6],[24.2,30.9],[47.9,40.2],[47.6,41.2],[41.2,47.2],[38.2,46.6]],
  "studio-chair-near-a": ellipse(24.9,39.6,2.4,1.6),
  "studio-chair-near-b": ellipse(34.3,44.2,2.3,1.6),
  "studio-chair-far-a": ellipse(32.3,28,2.4,1.5),
  "studio-chair-far-b": ellipse(42.4,34,2.3,1.5),
  "studio-plant-desk": box(44.8,41.2,46.9,43.6),
  "studio-plant-window": box(42.8,24,46.2,27.6),
  "studio-cabinet": [[47.5,29.5],[49.5,27.3],[60.3,32.3],[58.3,34.6]],
  "studio-plant-corner": box(57.8,31.2,60.4,35.2),
  // Lounge: the left wall and back wall meet behind the counter; the counter, fridge, and side cabinet fill the corner.
  "lounge-walls": [[45.2,52],[64.6,52],[64.6,61.7],[63.2,62.7],[61.8,64.2],[60.2,63.4],[59.6,63.1],[51,58.6],[50.2,60.4],[48,60.4],[47.1,62],[45.2,62.2]],
  "lounge-right-door": [[64.6,56],[69.8,56],[69.8,63.6],[68.8,63.6],[64.6,61.7]],
  // The plant stool and the standing lamp beside it: stool legs and the lamp's three feet.
  "lounge-lamp-table": [[39.5,69.3],[42,64.8],[44.2,65.2],[45.3,66],[44.5,69.2],[43.9,69.9],[41.7,71.3],[39.6,70]],
  // Floor behind the lamp where a walker's head would pass behind the shade (42.4-45.4, 53.4-57.8): kept clear,
  // so nobody seems to walk through the lamp. Feet reach it when the foot point is within 41.4-46.4.
  "lounge-lamp-shade": box(42.75,61.1,45.05,65),
  // Sofa base including both arms and the front feet; the back stands on the line behind the cushions.
  "sofa": [[44.8,69.2],[49.7,66.1],[63.3,73.5],[58.4,76.5]],
  // Round table: the top projected to the floor, enclosing the three visible legs.
  "coffee-table": ellipse(48.15,76.9,4.3,3),
  "ottoman": ellipse(51.3,83.6,2.5,2.1),
  "lounge-chair": [[55.4,82.3],[59.4,79.3],[62.7,81.5],[62.3,84],[58.8,86.4],[55.5,84.4]],
  "lounge-side-table": [[62.2,78.9],[63.9,77.2],[65.7,78.5],[63.9,80.6]],
  "corridor-door": [[35.6,65.9],[38.7,64.1],[38.7,63.5],[35.6,65.2]],
  "corridor-post": [[34,64.8],[35.8,64.8],[35.8,66],[34.9,66.7],[34,66.3]],
  "common-shelf-wall": [[23,73.6],[34,66.2],[34.3,67.8],[33.4,69.8],[26,74.2],[24.4,74.3],[23.1,74.6]],
  "common-post": [[21.4,74],[23.1,73.3],[23.1,75.2],[22.5,75.6],[21.4,75.05]],
  "common-desk": [[6.5,51],[12,46],[33,56],[23,62],[22.6,66.4],[8,58.6],[6.5,55.2]],
  "common-chair-a": ellipse(12.5,62.6,2.3,1.9),
  "common-chair-b": ellipse(19.9,67.4,2,2),
  "common-plant": box(4,59.5,7,62.6),
  "common-back-wall": [[0,0],[14,0],[14,44],[1.5,62.8],[0,62.8]],
  "studio1-post": box(61.9,38.5,63.6,41.4),
  "studio1-lamp": [[63.9,39.6],[65.5,38.8],[67.1,39.7],[65.7,41.5],[64,40.8]],
  "studio1-plant": box(66.7,36,68.7,38.9),
  "studio1-desk": [[69.2,37.8],[70.8,35.6],[89,43.6],[87.6,46.8],[84.6,46.8]],
  "studio1-chair-a": ellipse(73.4,40.8,2.2,1.7),
  "studio1-chair-b": ellipse(82.1,46.1,2.1,1.7),
  "studio1-plant-stand": box(87.6,43.8,91.6,47.9),
  "studio1-back-wall": [[62,0],[100,0],[100,40],[88,40],[62,26]],
  "infirmary-back-wall": [[69.6,47],[86,51.8],[86,56],[71.8,62]],
  // Post at the infirmary entrance and the open door leaf beside it.
  "infirmary-wall": [[70.2,47],[71.6,47],[71.6,63],[74.5,64.5],[74.5,78.9],[73.9,79.3],[71.4,77.3],[70.2,76.8]],
  "infirmary-cabinet": [[74.7,71.6],[74.9,66.6],[80.8,66],[80.8,69.6],[76.6,73]],
  "bed": [[80.8,68],[83.5,62],[93.5,67.5],[93.3,71.3],[88.3,75.2]],
  "infirmary-plant": box(93.8,65,96.7,69.3),
  "infirmary-basket": box(90.2,70.4,92.8,74),
};

// The floor slab up to its cut front edge, where the front walls are cut away. In front of the Common Office corner
// post, which stands on the edge, the outline dips onto the top of the cut face so walkers can pass the post.
export const FLOOR = [[0,0],[100,0],[100,67.86],[77,87.64],[68.5,81.02],[52.3,94.33],[33.8,80.97],[33.8,83.83],
  [24,77.17],[23,76.6],[21.2,76.6],[19.6,75.95],[18.2,73.23],[0,60.86]];

// Floor contact of a walker's feet around its foot point: the widest stance of the walking frames
// (the rear view, mirrored either way), and the depth of the soles behind and in front of the point.
export const FOOT = { half: 1.35, back: .7, front: .15 };

export const NODES = {
  // Project room on the left: in front of and behind the long desk.
  s0a: [24.5,44.5], s0b: [33.5,50], s0c: [40,53], s0d: [48.5,48.5], s0e: [50,38.6], s0f: [46.2,31], s0g: [38,27.4],
  // Aisle behind the lounge to the project room on the right.
  a1: [55,42], a2: [60.5,42.6], a3: [67,44.4], s1a: [72,45.2], s1b: [79.5,48.6],
  // Corridor between the lamp and the corridor door, down to the lounge entrance and its front strip.
  c1: [40,58.4], c2: [40.2,64.6], c2b: [38,68.5], c3: [37.8,73.5], c4: [42.9,73.6],
  c5: [43.5,81], c6: [47.4,86.9], c7: [55.5,89], c7b: [59.6,87.6], c8a: [62,86.2], c8: [63.8,84.7], c9: [67.5,80],
  // Lounge: in front of the left sofa cushion (the gap to the coffee table closes further right), around the table
  // and between it and the ottoman, in front of the armchair and the right sofa cushion, between the sofa end and
  // the side table, and up the right side to the strip behind the sofa and the counter.
  f1: [46.2,72.6], f0: [49.2,73], l1: [42.3,77.4], l2: [46.8,81], l3: [51.2,80.6],
  f2: [55.5,77.1], f3: [54.1,79.7], f5: [59.4,77.6], f6: [64.7,75.2],
  c10: [67.4,70.5], c11: [64.8,66], m1: [60.5,65.8], machine: [54.5,62.9],
  // Common Office, entered along its open front edge past the corner post.
  k0: [11.5,65.6], k1: [18.5,70.6], k2: [20,75.8], k2b: [21.2,76.35], k2c: [24,76.4], k3: [27,76.3],
  // Infirmary, entered below its open door.
  i1: [72.8,83.3], i2: [78.5,80.6], i3: [82.2,73.8],
};

export const LINKS = [
  ["s0a","s0b"], ["s0b","s0c"], ["s0c","s0d"], ["s0d","s0e"], ["s0e","s0f"], ["s0f","s0g"],
  ["s0d","a1"], ["a1","a2"], ["a2","a3"], ["a3","s1a"], ["s1a","s1b"],
  ["s0c","c1"], ["c1","c2"], ["c2","c2b"], ["c2b","c3"], ["c3","c4"], ["c3","c5"],
  ["c4","f1"], ["f1","f0"], ["c4","l1"], ["l1","c5"], ["c5","l2"], ["l2","l3"], ["l3","f3"],
  ["f3","f2"], ["f3","f5"], ["f2","f5"], ["f5","f6"], ["f6","c10"],
  ["c10","c11"], ["c11","m1"], ["m1","machine"], ["c10","c9"],
  ["c5","c6"], ["c6","c7"], ["c7","c7b"], ["c7b","c8a"], ["c8a","c8"], ["c8","c9"],
  ["c3","k3"], ["k3","k2c"], ["k2c","k2b"], ["k2b","k2"], ["k2","k1"], ["k1","k0"], ["c9","i1"], ["i1","i2"], ["i2","i3"],
];

// The free side of each seat, where a walker stands before sitting down and after getting up: behind a rear-facing
// desk chair, behind the desk for a front-facing one, in front of the sofa cushion, in front of the armchair seat.
export const APPROACH = {
  studio0: ["s0a", "s0b", "s0g", "s0f"],
  studio1: ["s1a", "s1b"],
  common: ["k0", "k1"],
  fika: ["f0", "f3", "f2"],
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
function crosses(a, b, c, d) {
  const side = (p, q, r) => Math.sign((q[0]-p[0]) * (r[1]-p[1]) - (q[1]-p[1]) * (r[0]-p[0]));
  return side(a,b,c) !== side(a,b,d) && side(c,d,a) !== side(c,d,b);
}
function bounds(polygon) {
  const xs = polygon.map(([x]) => x), ys = polygon.map(([,y]) => y);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
const AREAS = Object.entries(FOOTPRINTS).map(([name, polygon]) => ({ name, polygon, bounds: bounds(polygon) }));
function overlaps(shape, area) {
  const [x0,y0,x1,y1] = bounds(shape), [u0,v0,u1,v1] = area.bounds;
  if (x1 < u0 || u1 < x0 || y1 < v0 || v1 < y0) return false;
  const other = area.polygon;
  for (let i = 0; i < shape.length; i++) for (let j = 0; j < other.length; j++)
    if (crosses(shape[i], shape[(i+1) % shape.length], other[j], other[(j+1) % other.length])) return true;
  return inside(shape[0], other) || inside(other[0], shape);
}

// The feet of a walker standing at point.
export function feet([x, y]) {
  return [[x-FOOT.half, y-FOOT.back], [x+FOOT.half, y-FOOT.back], [x+FOOT.half, y+FOOT.front], [x-FOOT.half, y+FOOT.front]];
}
// Area the feet sweep along a straight step: the hull of the feet at both ends.
function sweep(a, b) {
  const points = [...feet(a), ...feet(b)].sort((p, q) => p[0]-q[0] || p[1]-q[1]);
  const turn = (o, p, q) => (p[0]-o[0]) * (q[1]-o[1]) - (p[1]-o[1]) * (q[0]-o[0]);
  const lower = [], upper = [];
  for (const p of points) { while (lower.length > 1 && turn(lower.at(-2), lower.at(-1), p) <= 0) lower.pop(); lower.push(p); }
  for (const p of points.reverse()) { while (upper.length > 1 && turn(upper.at(-2), upper.at(-1), p) <= 0) upper.pop(); upper.push(p); }
  return lower.slice(0,-1).concat(upper.slice(0,-1));
}

// Footprint touched by the feet of a walker standing at point, or "".
export function blockedBy(point) {
  return AREAS.find((area) => overlaps(feet(point), area))?.name || "";
}

// A straight step is clear when the swept feet touch no footprint and the foot point stays on the floor slab.
export function clear(a, b) {
  const swept = sweep(a, b);
  if (AREAS.some((area) => overlaps(swept, area))) return false;
  return inside(a, FLOOR) && inside(b, FLOOR) && FLOOR.every((corner, i) => !crosses(a, b, corner, FLOOR[(i+1) % FLOOR.length]));
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
