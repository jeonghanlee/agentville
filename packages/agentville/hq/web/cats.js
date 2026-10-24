import { catArtwork } from "./art.js";
import { t } from "./i18n.js";
import { NODES, neighbourIds, distance, FLOOR_ASPECT } from "./floor.js";
import { walkerDepth } from "./furniture.js";

import { CAT_NODES } from "./office-layout.js";
import { ACTOR_SCALE } from "./layout.js";

// Cats roam the corridor and lounge part of the shared floor graph (floor.js), so they also keep off furniture.
const ROAM = new Set(CAT_NODES);
// Connect the measured lounge and corridor destinations through the existing floor graph.
for (const target of CAT_NODES.slice(1)) {
  const first = CAT_NODES[0], parents = new Map([[first,null]]), open = [first];
  while (open.length && !parents.has(target)) {
    const current = open.shift();
    for (const next of neighbourIds(current)) if (!parents.has(next)) { parents.set(next,current); open.push(next); }
  }
  for (let id = target; id !== null && id !== undefined; id = parents.get(id)) ROAM.add(id);
}
const CATS = [
  { coat: "ginger", name: "Cheese", starts: CAT_NODES.slice(0,3) },
  { coat: "tuxedo", name: "Pepper", starts: CAT_NODES.slice(3) },
];
const RESTS = [
  { state: "sit", duration: [2200, 4500] },
  { state: "groom", duration: [3200, 6000] },
  { state: "nap", duration: [7000, 11000] },
];
const WALK_CHANCE = .55;
// One gait cycle (both diagonal leg pairs stepping once) moves the body by STRIDE percent of the floor width
// at the default cat size; speed = stride / cycle period, so paws do not slide.
const STRIDE = .8 * ACTOR_SCALE;
const CYCLE = [.46, .62];
const BLINK_PERIOD = [5, 8];
const RISE_MS = 420, SETTLE_MS = 520, SETTLE_NAP_MS = 700;
// Speed eases in after rising, down before stopping, and briefly at corners where the cat turns.
const EASE_IN = .7, EASE_OUT = .9, CORNER = .7, CORNER_SPEED = .35;
const MAX_FRAME_MS = 80;
const RETRY_MS = 1600;
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const choose = (items) => items[Math.floor(Math.random() * items.length)];
const between = ([min, max]) => min + Math.random() * (max - min);

export function createOfficeCats(root) {
  if (root.querySelector(".office-cat")) return;
  const cats = CATS.map(({ coat, name, starts }) => {
    const point = choose(starts);
    const node = document.createElement("div");
    node.className = "office-cat";
    node.dataset.coat = coat;
    node.dataset.state = "sit";
    node.style.setProperty("--cat-blink", between(BLINK_PERIOD).toFixed(3) + "s");
    node.setAttribute("role", "img");
    const label = document.createElement("span");
    label.className = "cat-name";
    node.append(catArtwork(coat), label);
    root.append(node);
    const [x, y] = NODES[point];
    // Each cat keeps its own pace for the whole visit.
    const cat = { node, label, name, point, previous: "", target: null, x, y, state: "sit", phase: Math.random(),
      cycle: between(CYCLE), remaining: between(RESTS[0].duration), facing: Math.random() < .5 ? -1 : 1, next: null };
    face(cat, cat.facing, 0);
    place(cat);
    return cat;
  });

  // Cat names are interface strings, so they follow the selected language.
  function relabel() {
    for (const cat of cats) {
      const name = t("cat." + cat.name);
      cat.label.textContent = name;
      cat.node.setAttribute("aria-label", t("cat.label", { name }));
    }
  }
  relabel();

  function place(cat) {
    cat.node.style.left = cat.x.toFixed(3) + "%";
    cat.node.style.top = cat.y.toFixed(3) + "%";
    cat.node.style.zIndex = String(walkerDepth(cat.x, cat.y));
  }
  // Turning flips the body through a short scale transition; slopes tilt it slightly.
  function face(cat, facing, tilt) {
    cat.facing = facing;
    cat.node.dataset.facing = facing < 0 ? "left" : "right";
    cat.node.style.setProperty("--cat-flip", String(facing));
    cat.node.style.setProperty("--cat-tilt", tilt.toFixed(1) + "deg");
  }
  function setState(cat, state) {
    cat.state = state;
    cat.node.dataset.state = state;
  }
  function rest(cat, pose = choose(RESTS)) {
    // Stopping: a settling step lowers the hindquarters first, then the cat sits; a nap follows a short sit.
    cat.next = pose;
    setState(cat, "settle");
    cat.remaining = SETTLE_MS;
  }
  function stride() { return STRIDE; }
  function choosePath(cat) {
    const options = neighbourIds(cat.point).filter((id) => ROAM.has(id)
      && !cats.some((other) => other !== cat && (other.point === id || other.target === id)));
    if (!options.length) return null;
    const forward = options.filter((id) => id !== cat.previous);
    return choose(forward.length ? forward : options);
  }
  function walk(cat) {
    const target = choosePath(cat);
    if (!target) { cat.next = null; setState(cat, "sit"); cat.remaining = RETRY_MS; return; }
    cat.target = target;
    cat.from = [cat.x, cat.y];
    cat.travelled = 0;
    // Rising: a short stand-up before the first step.
    setState(cat, cat.state === "walk" ? "walk" : "rise");
    cat.remaining = cat.state === "rise" ? RISE_MS : 0;
    const to = NODES[target];
    if (Math.abs(to[0] - cat.x) > .05) face(cat, to[0] < cat.x ? -1 : 1, slope(cat.from, to));
  }
  function slope(from, to) {
    const dx = Math.abs(to[0] - from[0]) || .01, dy = (to[1] - from[1]) * FLOOR_ASPECT;
    return Math.max(-8, Math.min(8, Math.atan2(dy, dx) * 180 / Math.PI * .35));
  }

  let previousFrame = performance.now(), wasPaused = null;
  function tick(now) {
    const delta = Math.max(0, Math.min(now - previousFrame, MAX_FRAME_MS));
    previousFrame = Math.max(previousFrame, now);
    const paused = document.hidden || !!root.closest("[hidden]") || reducedMotion.matches
      || document.body.classList.contains("reduce-motion");
    if (paused !== wasPaused) {
      cats.forEach((cat) => cat.node.classList.toggle("is-paused", paused));
      wasPaused = paused;
    }
    if (!paused) {
      const unit = stride();
      for (const cat of cats) {
        if (cat.state === "rise") {
          cat.remaining -= delta;
          if (cat.remaining <= 0) { setState(cat, "walk"); cat.easeIn = true; }
          continue;
        }
        if (cat.state === "walk") {
          const to = NODES[cat.target], length = distance(cat.from, to);
          const left = length - cat.travelled;
          // Look ahead: will the cat stop at this point, or turn sharply onto the next segment?
          if (cat.after === undefined) cat.after = Math.random() < WALK_CHANCE ? "walk" : "rest";
          let factor = 1;
          if (cat.easeIn) factor = Math.min(factor, .3 + .7 * Math.min(1, cat.travelled / EASE_IN));
          if (cat.after === "rest") factor = Math.min(factor, .25 + .75 * Math.min(1, left / EASE_OUT));
          else factor = Math.min(factor, CORNER_SPEED + (1 - CORNER_SPEED) * Math.min(1, left / CORNER));
          const speed = unit / cat.cycle * factor;
          const step = Math.min(left, speed * delta / 1000);
          cat.travelled += step;
          cat.phase = (cat.phase + step / unit) % 1;
          const progress = length ? cat.travelled / length : 1;
          cat.x = cat.from[0] + (to[0] - cat.from[0]) * progress;
          cat.y = cat.from[1] + (to[1] - cat.from[1]) * progress;
          cat.node.style.setProperty("--cat-phase", cat.phase.toFixed(3));
          place(cat);
          if (progress >= 1) {
            cat.previous = cat.point;
            cat.point = cat.target;
            cat.target = null;
            cat.easeIn = cat.after === "rest";
            const after = cat.after;
            cat.after = undefined;
            if (after === "walk") { walk(cat); cat.easeIn = false; }
            else rest(cat);
          }
        } else if (cat.state === "settle") {
          cat.remaining -= delta;
          if (cat.remaining > 0) continue;
          const pose = cat.next || RESTS[0];
          if (pose.state === "nap" && !cat.napping) {
            cat.napping = true;
            setState(cat, "sit");
            cat.remaining = SETTLE_NAP_MS;
            continue;
          }
          cat.napping = false;
          setState(cat, pose.state);
          cat.remaining = between(pose.duration);
        } else {
          cat.remaining -= delta;
          if (cat.remaining > 0) continue;
          if (cat.napping) { cat.napping = false; setState(cat, "nap"); cat.remaining = between(cat.next.duration); continue; }
          walk(cat);
        }
      }
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
  return { relabel };
}
