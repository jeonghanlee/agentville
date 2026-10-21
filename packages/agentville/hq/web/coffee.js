import { randomMug } from "./mugs.js";

const FIRST_VISIT = [9000, 15000];
const NEXT_VISIT = [26000, 48000];
const WAIT = [6000, 10000];
const MACHINE = [53, 60];
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const between = ([min,max]) => min + Math.random()*(max-min);

// Coffee visits decorate Fika only; live activity and room membership stay authoritative.
export function createCoffeeBreaks(root, changed) {
  const cups = new Map();
  let eligible = new Map(), active = null, scope = null, remaining = between(FIRST_VISIT);
  let previous = performance.now();
  function cup(key) {
    if (!cups.has(key)) cups.set(key,randomMug());
    return cups.get(key);
  }
  function start(key, home) {
    const foot = [home[0],home[1] + (home[2].startsWith("back") ? 2.2 : 3.6)];
    const route = home[1] > 75 ? [[50,88],[43,80],[43,69],[43,61],MACHINE] : [[43,70],[43,61],MACHINE];
    const stages = [{ position: foot, phase: "leaving", duration: 100 }];
    for (const position of route) stages.push({ position, phase: "walking-out", duration: 2200 });
    stages.push({ position: MACHINE, phase: "waiting", duration: between(WAIT) });
    for (const position of [...route.slice(0,-1).reverse(),foot]) stages.push({ position, phase: "walking-back", duration: 2200 });
    active = { key, stages, index: 0, remaining: stages[0].duration };
    changed();
  }
  setInterval(() => {
    const now = performance.now(), delta = Math.min(now-previous,500);
    previous = now;
    if (document.hidden || root.closest("[hidden]") || reducedMotion.matches || document.body.classList.contains("reduce-motion")) return;
    if (!active) {
      remaining -= delta;
      if (remaining > 0 || !eligible.size) return;
      const choices = [...eligible.entries()].filter(([key]) => {
        const node = [...root.querySelectorAll(".agent")].find((actor) => actor.dataset.employeeKey === key);
        return node && !node.classList.contains("filtered");
      });
      if (!choices.length) return;
      start(...choices[Math.floor(Math.random()*choices.length)]);
      return;
    }
    active.remaining -= delta;
    if (active.remaining > 0) return;
    if (active.stages[active.index].phase === "waiting") cups.set(active.key,randomMug(cup(active.key)));
    active.index++;
    if (active.index >= active.stages.length) { active = null; remaining = between(NEXT_VISIT); }
    else active.remaining = active.stages[active.index].duration;
    changed();
  },200);
  return {
    cup,
    sync(places, branch) {
      eligible = new Map(places);
      if (active && (scope !== branch || !eligible.has(active.key))) { active = null; remaining = between(NEXT_VISIT); }
      scope = branch;
    },
    get(key) {
      if (active?.key !== key) return null;
      const stage = active.stages[active.index];
      const from = active.stages[Math.max(0,active.index-1)].position;
      return { phase: stage.phase, seat: [...stage.position,"coffee-back",Math.floor(stage.position[1])+1],
        facing: stage.position[0] < from[0] ? "left" : "right", cup: stage.phase === "walking-back" };
    },
  };
}
