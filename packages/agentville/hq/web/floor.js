// Walkable floor and measured contacts of the single office artwork.
import { ARTWORK } from "./layout.js";
import { FLOOR, FOOTPRINTS, NODES, LINKS, COFFEE_NODE } from "./office-layout.js";
export { FLOOR, FOOTPRINTS, NODES, LINKS };
export const FLOOR_ASPECT = ARTWORK.height / ARTWORK.width;
export const FOOT = { half: 1.35, back: .7, front: .15 };
export const COFFEE_SPOT = NODES[COFFEE_NODE];
const GEOMETRY_EPSILON = 1e-10;

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
  const side = (p, q, r) => {
    const value = (q[0]-p[0]) * (r[1]-p[1]) - (q[1]-p[1]) * (r[0]-p[0]);
    return Math.abs(value) <= GEOMETRY_EPSILON ? 0 : Math.sign(value);
  };
  return side(a,b,c) !== side(a,b,d) && side(c,d,a) !== side(c,d,b);
}
function bounds(polygon) {
  const xs = polygon.map(([x]) => x), ys = polygon.map(([,y]) => y);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
function overlaps(shape, area) {
  const [x0,y0,x1,y1] = bounds(shape), [u0,v0,u1,v1] = area.bounds;
  if (x1 + GEOMETRY_EPSILON < u0 || u1 + GEOMETRY_EPSILON < x0
    || y1 + GEOMETRY_EPSILON < v0 || v1 + GEOMETRY_EPSILON < y0) return false;
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

// Each scene uses the same foot box and routing rules with its own measured artwork geometry.
export function createFloor({ footprints: FOOTPRINTS, floor: FLOOR, nodes: NODES, links: LINKS, wholeFoot = false, clearance = 0 }) {
  const AREAS = Object.entries(FOOTPRINTS).map(([name, polygon]) => ({ name, polygon, bounds: bounds(polygon) }));
  const neighbours = new Map(Object.keys(NODES).map((id) => [id, []]));
  for (const [a,b] of LINKS) { neighbours.get(a).push(b); neighbours.get(b).push(a); }
  const neighbourIds = (id) => neighbours.get(id) || [];

  // Footprint touched by the feet of a walker standing at point, or "".
  function blockedBy(point) {
    return AREAS.find((area) => overlaps(feet(point), area))?.name || "";
  }

  // Footprints touched by the feet swept along a straight step; a seat step touches only the seat's own (seats.js).
  function touched(a, b) {
    const swept = sweep(a, b);
    return AREAS.filter((area) => overlaps(swept, area)).map((area) => area.name);
  }

  // A straight step touches no furniture and stays on the scene's floor. Whole-foot scenes contain the
  // entire swept hull; point-boundary scenes retain their cut-edge foot-point routes.
  function clear(a, b) {
    const swept = sweep(a, b);
    if (AREAS.some((area) => overlaps(swept, area))) return false;
    if (wholeFoot) return swept.every((point) => inside(point, FLOOR)) && swept.every((point, i) =>
      FLOOR.every((corner, j) => !crosses(point, swept[(i+1) % swept.length], corner, FLOOR[(j+1) % FLOOR.length])));
    return inside(a, FLOOR) && inside(b, FLOOR) && FLOOR.every((corner, i) => !crosses(a, b, corner, FLOOR[(i+1) % FLOOR.length]));
  }

  // Circulation keeps the full aisle width; only final seat steps use named furniture exceptions.
  function circulationClear(a, b) {
    const margin = Math.max(0, (clearance / ARTWORK.width * 100 - FOOT.half * 2) / 2);
    return [-margin, 0, margin].every((shift) => clear([a[0]+shift,a[1]], [b[0]+shift,b[1]]));
  }

  function nearestClear(point) {
    return Object.keys(NODES).filter((id) => circulationClear(point, NODES[id]))
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
  function route(from, to) {
    if (distance(from, to) < .05) return [from];
    if (circulationClear(from, to) && distance(from, to) < 6) return [from, to];
    const start = nearestClear(from), end = nearestClear(to);
    const points = [from, ...shortest(start, end).map((id) => NODES[id]), to];
    // Drop corners that a clear straight step can skip, so walkers do not zigzag.
    const path = [points[0]];
    let index = 0;
    while (index < points.length-1) {
      let next = points.length-1;
      while (next > index+1 && !circulationClear(points[index], points[next])) next--;
      path.push(points[next]);
      index = next;
    }
    return path.filter((point, i) => i === 0 || distance(point, path[i-1]) > .01);
  }

  return { FOOTPRINTS, FLOOR, NODES, LINKS, neighbourIds, blockedBy, touched, clear, route };
}

const main = createFloor({ footprints: FOOTPRINTS, floor: FLOOR, nodes: NODES, links: LINKS, wholeFoot: true, clearance: 46 });
export const { neighbourIds, blockedBy, touched, clear, route } = main;
