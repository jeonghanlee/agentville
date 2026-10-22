import { distance } from "./floor.js";
import { walkerDepth } from "./furniture.js";

// Colleagues walk between places along floor.js routes; placement data stays authoritative.
const SPEED = [5.2, 6.4];
const MAX_FRAME_MS = 80;

export function createWalkers(root, { motionAllowed, changed }) {
  const walks = new Map();
  let running = false, previous = 0;

  function position(walk) {
    const from = walk.path[walk.index], to = walk.path[walk.index + 1] || from;
    const length = distance(from, to) || 1;
    const t = Math.max(0, Math.min(1, walk.travelled / length));
    return [from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t];
  }
  function facing(walk) {
    const from = walk.path[walk.index], to = walk.path[walk.index + 1] || from;
    return Math.abs(to[0] - from[0]) < .05 ? walk.facing : to[0] < from[0] ? "left" : "right";
  }
  function place(walk) {
    const node = [...root.querySelectorAll(".agent")].find((actor) => actor.dataset.employeeKey === walk.key);
    if (!node) return;
    const [x, y] = position(walk);
    walk.facing = facing(walk);
    node.style.left = x.toFixed(3) + "%";
    node.style.top = y.toFixed(3) + "%";
    node.style.zIndex = String(walkerDepth(x, y));
    node.dataset.coffeeFacing = walk.facing;
  }
  function finish(walk) {
    walks.delete(walk.key);
    walk.arrive?.();
  }
  function frame(now) {
    // A frame timestamp can precede the start of a walk; never step backwards.
    const delta = Math.max(0, Math.min(now - previous, MAX_FRAME_MS));
    previous = Math.max(previous, now);
    if (!walks.size) { running = false; return; }
    if (!motionAllowed()) {
      // Reduced motion skips the walk and shows the destination.
      const done = [...walks.values()];
      walks.clear();
      done.forEach((walk) => walk.arrive?.());
      running = false;
      changed();
      return;
    }
    if (!document.hidden && !root.closest("[hidden]")) {
      let arrived = false;
      for (const walk of [...walks.values()]) {
        walk.travelled += walk.speed * delta / 1000;
        while (walk.index < walk.path.length - 1 && walk.travelled >= distance(walk.path[walk.index], walk.path[walk.index + 1])) {
          walk.travelled -= distance(walk.path[walk.index], walk.path[walk.index + 1]);
          walk.index++;
        }
        if (walk.index >= walk.path.length - 1) { finish(walk); arrived = true; }
        else place(walk);
      }
      if (arrived) changed();
    }
    requestAnimationFrame(frame);
  }

  return {
    // Start walking along path (floor points); arrive runs once at the end.
    start(key, path, arrive, carrying = false) {
      const old = walks.get(key);
      const walk = { key, path, index: 0, travelled: 0, arrive, carrying,
        speed: old?.speed || SPEED[0] + Math.random() * (SPEED[1] - SPEED[0]), facing: old?.facing || "right" };
      walk.goal = path[path.length - 1];
      walks.set(key, walk);
      walk.facing = facing(walk);
      if (!running) { running = true; previous = performance.now(); requestAnimationFrame(frame); }
      return walk;
    },
    get(key) {
      const walk = walks.get(key);
      if (!walk) return null;
      const [x, y] = position(walk);
      return { x, y, goal: walk.goal, facing: facing(walk), carrying: walk.carrying, depth: walkerDepth(x, y) };
    },
    stop(key) { walks.delete(key); },
    active() { return walks.size > 0; },
  };
}
