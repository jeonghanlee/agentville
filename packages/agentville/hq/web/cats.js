import { catArtwork } from "./art.js";
import { t } from "./i18n.js";

// Connected floor positions follow the open aisle and the edge of the lounge rug.
const FLOOR = [
  { x: 29, y: 47, links: [1] },
  { x: 37, y: 52, links: [0, 2] },
  { x: 41, y: 56, links: [1, 3] },
  { x: 39, y: 69, links: [2, 4] },
  { x: 35, y: 74, links: [3, 5, 6] },
  { x: 30, y: 77, links: [4, 6] },
  { x: 41, y: 80, links: [4, 5, 7] },
  { x: 48, y: 86, links: [6, 8] },
  { x: 54, y: 90, links: [7, 9] },
  { x: 62, y: 85, links: [8, 10] },
  { x: 67, y: 80, links: [9, 11] },
  { x: 69, y: 72, links: [10, 12] },
  { x: 68, y: 66, links: [11] },
];
const CATS = [
  { coat: "ginger", name: "Cheese", starts: [4, 5, 6] },
  { coat: "tuxedo", name: "Pepper", starts: [9, 10, 11] },
];
const RESTS = [
  { state: "sit", duration: [2200, 4500] },
  { state: "groom", duration: [3200, 6000] },
  { state: "nap", duration: [7000, 11000] },
];
const WALK_CHANCE = .55;
const SPEED = [1.8, 2.6];
const STEP_PERIOD = [.35, .55];
const BLINK_PERIOD = [5, 8];
const MAX_FRAME_MS = 80;
const MIN_WALK_MS = 1500;
const RETRY_MS = 1600;
const FLOOR_ASPECT = 1024 / 1536;
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
    node.dataset.facing = Math.random() < .5 ? "left" : "right";
    node.style.setProperty("--cat-blink", between(BLINK_PERIOD).toFixed(3) + "s");
    node.setAttribute("role", "img");
    const label = document.createElement("span");
    label.className = "cat-name";
    node.append(catArtwork(coat), label);
    root.append(node);
    const cat = { node, label, name, point, previous: -1, target: null, x: FLOOR[point].x,
      y: FLOOR[point].y, state: "sit", remaining: between(RESTS[0].duration) };
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
    cat.node.style.zIndex = String(Math.floor(cat.y));
  }

  function rest(cat, pose = choose(RESTS)) {
    cat.state = pose.state;
    cat.remaining = between(pose.duration);
    cat.node.dataset.state = cat.state;
  }

  function walk(cat) {
    const available = FLOOR[cat.point].links.filter((point) =>
      !cats.some((other) => other !== cat && (other.point === point || other.target === point)));
    if (!available.length) {
      rest(cat, { state: "sit", duration: [RETRY_MS, RETRY_MS] });
      return;
    }
    const forward = available.filter((point) => point !== cat.previous);
    cat.target = choose(forward.length ? forward : available);
    const to = FLOOR[cat.target];
    cat.duration = Math.max(MIN_WALK_MS,
      Math.hypot(to.x - cat.x, (to.y - cat.y) * FLOOR_ASPECT) / between(SPEED) * 1000);
    cat.elapsed = 0;
    cat.state = "walk";
    cat.node.dataset.state = "walk";
    cat.node.dataset.facing = to.x < cat.x ? "left" : "right";
    cat.node.style.setProperty("--cat-step", between(STEP_PERIOD).toFixed(3) + "s");
  }

  let previousFrame = performance.now(), wasPaused = null;
  function tick(now) {
    const delta = Math.min(now - previousFrame, MAX_FRAME_MS);
    previousFrame = now;
    const paused = document.hidden || !!root.closest("[hidden]") || reducedMotion.matches
      || document.body.classList.contains("reduce-motion");
    if (paused !== wasPaused) {
      cats.forEach((cat) => cat.node.classList.toggle("is-paused", paused));
      wasPaused = paused;
    }
    if (!paused) {
      for (const cat of cats) {
        if (cat.state === "walk") {
          cat.elapsed += delta;
          const progress = Math.min(1, cat.elapsed / cat.duration);
          const from = FLOOR[cat.point], to = FLOOR[cat.target];
          cat.x = from.x + (to.x - from.x) * progress;
          cat.y = from.y + (to.y - from.y) * progress;
          place(cat);
          if (progress === 1) {
            cat.previous = cat.point;
            cat.point = cat.target;
            cat.target = null;
            if (Math.random() < WALK_CHANCE) walk(cat); else rest(cat);
          }
        } else {
          cat.remaining -= delta;
          if (cat.remaining <= 0) walk(cat);
        }
      }
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
  return { relabel };
}
