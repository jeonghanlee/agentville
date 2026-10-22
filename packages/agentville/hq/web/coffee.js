import { randomMug } from "./mugs.js";
import { COFFEE_SPOT } from "./floor.js";

const FIRST_VISIT = [9000, 15000];
const NEXT_VISIT = [26000, 48000];
const WAIT = [6000, 10000];
// A walk that has not reported arrival by then is ended, so a visit can never stall.
const WALK_LIMIT = 40000;
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const between = ([min,max]) => min + Math.random()*(max-min);

// Counter visits decorate Fika only; live activity and room membership stay authoritative.
// The colleague walks along the floor routes to the counter, waits, takes a drink, and walks back.
export function createCoffeeBreaks(root, changed, lounge) {
  const cups = new Map();
  let eligible = new Map(), active = null, scope = null, remaining = between(FIRST_VISIT);
  let previous = performance.now();
  function cup(key) {
    if (!cups.has(key)) cups.set(key,randomMug());
    return cups.get(key);
  }
  function end() { active = null; remaining = between(NEXT_VISIT); }
  function advance() {
    if (!active) return;
    if (active.phase === "walking-out") { active.phase = "waiting"; active.remaining = between(WAIT); }
    else if (active.phase === "waiting") {
      lounge?.set(active.key, active.next);
      active.phase = "walking-back"; active.remaining = WALK_LIMIT;
    } else end();
    changed();
  }
  setInterval(() => {
    const now = performance.now(), delta = Math.min(now-previous,500);
    previous = now;
    if (document.hidden || root.closest("[hidden]") || reducedMotion.matches || document.body.classList.contains("reduce-motion")) return;
    if (!active) {
      remaining -= delta;
      if (remaining > 0 || !eligible.size) return;
      const choices = [...eligible.keys()].filter((key) => {
        const node = [...root.querySelectorAll(".agent")].find((actor) => actor.dataset.employeeKey === key);
        return node && !node.classList.contains("filtered") && node.classList.contains("seated");
      });
      if (!choices.length) return;
      const key = choices[Math.floor(Math.random()*choices.length)];
      active = { key, phase: "walking-out", remaining: WALK_LIMIT, next: lounge ? lounge.refill(key) : null };
      changed();
      return;
    }
    active.remaining -= delta;
    if (active.remaining <= 0) advance();
  },200);
  return {
    cup,
    sync(places, branch) {
      eligible = new Map(places);
      if (active && (scope !== branch || !eligible.has(active.key))) end();
      scope = branch;
    },
    // The walker reports arrival at the counter or back at the seat.
    arrived(key) {
      if (active?.key === key && active.phase.startsWith("walking")) advance();
    },
    get(key) {
      if (active?.key !== key) return null;
      return { phase: active.phase, point: active.phase === "walking-back" ? null : COFFEE_SPOT,
        drink: active.phase === "walking-back" ? lounge?.drink(key) : active.next };
    },
  };
}
