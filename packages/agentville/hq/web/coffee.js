import { randomMug } from "./mugs.js";
import { COFFEE_SPOT } from "./floor.js";
import { pointPercent } from "./layout.js";

const FIRST_VISIT = [9000, 15000];
const NEXT_VISIT = [26000, 48000];
const WAIT = [6000, 10000];
// A walk that has not reported arrival by then is ended, so a visit can never stall.
const WALK_LIMIT = 40000;
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const between = ([min,max]) => min + Math.random()*(max-min);
export const FOODS = ["spaghetti", "pizza", "pasta", "hamburger", "danish", "croissant", "gimbap", "ramen"];
export const STOPS = {
  coffee: COFFEE_SPOT, water: pointPercent([1160,615]), sink: pointPercent([1205,650]),
  microwave: pointPercent([1290,680]), fridge: pointPercent([1390,790]),
};
const pick = (items) => items[Math.floor(Math.random()*items.length)];
export function isMealTime(zone) {
  const hour = Number(new Intl.DateTimeFormat("en-US", { hour: "numeric", hourCycle: "h23",
    ...(zone ? { timeZone: zone } : {}) }).format(new Date()));
  return (hour >= 7 && hour < 10) || (hour >= 11 && hour < 14) || (hour >= 17 && hour < 20);
}

// Counter visits decorate Fika only; live activity and room membership stay authoritative.
// The colleague walks along the floor routes to the counter, waits, takes a drink, and walks back.
export function createCoffeeBreaks(root, changed, lounge, zone = () => "") {
  const cups = new Map();
  const door = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  door.setAttribute("viewBox", "0 0 1536 1024");
  door.setAttribute("class", "kitchen-fridge-door");
  door.setAttribute("aria-hidden", "true");
  door.innerHTML = '<defs><clipPath id="fridge-door-face"><path d="M1380 617 1417 639 1417 765 1380 742Z"/></clipPath></defs>'
    + '<path d="M1381 619 1416 640 1416 762 1381 741Z" fill="#252a2c" stroke="#4d5151" stroke-width="2"/>'
    + '<path d="M1384 626 1413 643 1413 754 1384 737Z" fill="#d4d9d2"/>'
    + '<path d="M1384 652 1413 669 M1384 680 1413 697 M1384 708 1413 725" stroke="#858f89" stroke-width="3"/>'
    + '<path d="M1388 637v12m5-8v11m9-6v11m-14 5v13m8-8v12m9-7v12" stroke="#a8b39d" stroke-width="4"/>'
    + '<image href="office-modern.png" width="1536" height="1024" clip-path="url(#fridge-door-face)" transform="matrix(-0.324 0.243 0 1 1827.12 -335.34)"/>'
    + '<path d="M1378 626 1370 647 1370 766 1378 739Z" fill="#c6cdc5" stroke="#59615b" stroke-width="1"/>'
    + '<path d="M1371 677 1377 661 M1371 710 1377 694 M1371 743 1377 727" stroke="#8b968c" stroke-width="2"/>';
  root.parentElement.append(door);
  const showDoor = () => { door.style.display = active?.phase === "waiting" && active.stops[active.index] === "fridge" ? "block" : "none"; };
  let eligible = new Map(), active = null, scope = null, remaining = between(FIRST_VISIT);
  let previous = performance.now();
  function cup(key) {
    if (!cups.has(key)) cups.set(key,randomMug());
    return cups.get(key);
  }
  function end() { active = null; remaining = between(NEXT_VISIT); showDoor(); }
  function advance() {
    if (!active) return;
    if (active.phase === "walking-out") { active.phase = "waiting"; active.remaining = between(WAIT); }
    else if (active.phase === "waiting") {
      if (++active.index < active.stops.length) { active.phase = "walking-out"; active.remaining = WALK_LIMIT; }
      else {
        if (active.next) lounge?.set(active.key, active.next);
        active.phase = "walking-back"; active.remaining = WALK_LIMIT;
      }
    } else end();
    showDoor(); changed();
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
      const kind = pick(["coffee", "water", "sink", "fridge", ...(isMealTime(zone()) ? ["meal", "meal"] : [])]);
      const next = kind === "meal" ? { kind: "food", food: pick(FOODS) }
        : kind === "water" ? { kind: "water", mug: cup(key) }
        : kind === "coffee" ? { ...(lounge ? lounge.refill(key) : { mug: cup(key) }), kind: "coffee" } : null;
      active = { key, kind, stops: kind === "meal" ? ["fridge", "microwave"] : [kind], index: 0,
        phase: "walking-out", remaining: WALK_LIMIT, next };
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
      return { phase: active.phase, point: active.phase === "walking-back" ? null : STOPS[active.stops[active.index]],
        action: active.stops[active.index], carry: Boolean(active.next),
        drink: active.phase === "walking-back" ? lounge?.drink(key) : active.next };
    },
  };
}
