import { DRINKS, MUGS } from "./mugs.js";
import { mirroredFacing } from "./seats.js";

// Lounge activities are decorative and never change reported activity or room membership.
const TICK = 150;
const SIP_EVERY = [3.2, 9];
const SIP_LENGTH = [.8, 2.4];
const SIP_STYLES = ["raise", "hold", "stir"];
const PAGE_EVERY = [2.6, 6.5];
const SPELLS = { drink: [8000, 15000], read: [7000, 13000], sit: [3000, 6000] };
const TALK_LENGTH = [4200, 7500];
const TURN_LENGTH = [900, 1500];
const TALK_GAP = [5500, 12000];
const DRINK_CHANGE = .45;
// Non-verbal glyphs only; conversations never show words or agent data.
const GLYPHS = ["dots", "heart", "coffee", "idea", "question", "note", "sun"];
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const between = ([min, max], random = Math.random) => min + random() * (max - min);
const pick = (items, random = Math.random) => items[Math.floor(random() * items.length)];

// Stable per-colleague randomness from the agent_id.
function seeded(text) {
  let state = Array.from(String(text)).reduce((hash, ch) => Math.imul(hash ^ ch.charCodeAt(0), 16777619) >>> 0, 2166136261);
  return () => {
    state = (state + 0x6D2B79F5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function profileFor(agentId) {
  const random = seeded("lounge:" + agentId);
  const kind = DRINKS[Math.floor(random() * DRINKS.length)];
  return {
    sipEvery: between(SIP_EVERY, random), sipLength: between(SIP_LENGTH, random), sipStyle: pick(SIP_STYLES, random),
    sipDelay: random(), pageEvery: between(PAGE_EVERY, random), reads: random() < .8,
    still: random() < .5 ? "drink" : "read",
    drink: { kind, mug: Math.floor(random() * MUGS.length) },
  };
}

export const GLYPH_ART = {
  dots: '<path d="M1 4h1v1H1Zm2 0h1v1H3Zm2 0h1v1H5Z" fill="#7d6e55"/>',
  heart: '<path d="M1 2h2v1h1V2h2v2H5v1H4v1H3V5H2V4H1Z" fill="#d0665f"/><path d="M2 2h1v1H2Z" fill="#f2a59c"/>',
  coffee: '<path d="M1 3h4v3H2V5H1Z" fill="#b07a4f"/><path d="M5 3h1v2H5Z" fill="#b07a4f"/><path d="M2 3h2v1H2Z" fill="#6a4c37"/><path d="M2 1h1v1H2Zm1-1h1v1H3Z" fill="#c9b9a0"/>',
  idea: '<path d="M2 1h3v1h1v2H5v1H2V4H1V2h1Z" fill="#f2c94c"/><path d="M2 5h3v1H2Z" fill="#8c8576"/><path d="M3 2h1v1H3Z" fill="#fff4c2"/>',
  question: '<path d="M2 1h3v1h1v1H5v1H4v1H3V3h2V2H2v1H1V2h1Zm1 5h1v1H3Z" fill="#6f8db0"/>',
  note: '<path d="M4 1h2v1H5v3H4Zm-2 3h2v2H2Z" fill="#7a8f62"/>',
  sun: '<path d="M2 2h3v3H2Z" fill="#f0b44a"/><path d="M3 0h1v1H3Zm0 6h1v1H3ZM0 3h1v1H0Zm6 0h1v1H6Z" fill="#e59b3a"/>',
};

export function createLounge(root, { motionAllowed, room = "fika", conversationOnly = false }) {
  const profiles = new Map(), drinks = new Map(), states = new Map();
  let members = [], talk = null, lastPair = "", nextTalk = performance.now() + between([1500, 4000]);
  let previous = performance.now();

  function profile(key, agentId) {
    if (!profiles.has(key)) profiles.set(key, profileFor(agentId));
    return profiles.get(key);
  }
  function drink(key, agentId = key) {
    if (!drinks.has(key)) drinks.set(key, { ...profile(key, agentId).drink });
    return drinks.get(key);
  }
  // A counter visit sometimes switches drinks; coffee and tea get a different mug.
  function refill(key) {
    const current = drink(key);
    const kind = Math.random() < DRINK_CHANGE ? pick(DRINKS.filter((name) => name !== current.kind)) : current.kind;
    const mug = (current.mug + 1 + Math.floor(Math.random() * (MUGS.length - 1))) % MUGS.length;
    return { kind, mug };
  }
  function nodeOf(key) {
    return [...root.querySelectorAll(".agent")].find((node) => node.dataset.employeeKey === key);
  }
  function seated(node) {
    return node && node.dataset.room === room && node.classList.contains("seated") && !node.classList.contains("filtered");
  }
  function spell(state, now, random = Math.random) {
    const choices = ["drink", "drink", "sit", ...(state.profile.reads ? ["read", "read"] : [])].filter((name) => name !== state.activity);
    state.activity = pick(choices, random);
    state.until = now + between(SPELLS[state.activity], random);
    state.sipAt = now + state.profile.sipDelay * state.profile.sipEvery * 1000;
    state.sipUntil = 0;
    state.pageAt = now + state.profile.pageEvery * 1000;
    state.pageUntil = 0;
  }
  function bubble(node, glyph, side) {
    let element = node.querySelector(":scope > .talk-bubble");
    if (!glyph) { element?.remove(); return; }
    if (!element) {
      element = document.createElement("span");
      element.className = "talk-bubble";
      element.setAttribute("aria-hidden", "true");
      node.append(element);
    }
    if (element.dataset.glyph !== glyph) {
      element.dataset.glyph = glyph;
      element.innerHTML = '<svg viewBox="0 0 7 7" shape-rendering="crispEdges">' + GLYPH_ART[glyph] + '</svg>';
    }
    element.dataset.side = side;
  }
  function apply(node, state, now, still) {
    const svg = node.querySelector(":scope > .character");
    if (!svg) return;
    const { profile } = state;
    const activity = talk && !still && (talk.a === state.key || talk.b === state.key) ? "talk"
      : conversationOnly ? "sit" : still ? profile.still : state.activity;
    const set = (name, value) => { if ((svg.dataset[name] || "") !== value) { if (value) svg.dataset[name] = value; else delete svg.dataset[name]; } };
    set("lounge", activity);
    set("sipStyle", profile.sipStyle);
    set("sip", !still && activity === "drink" && now < state.sipUntil ? "up" : "");
    set("page", !still && activity === "read" && now < state.pageUntil ? "turn" : "");
    svg.style.setProperty("--sip-move", Math.min(.7, profile.sipLength / 3).toFixed(2) + "s");
    let glyph = "", side = "";
    if (!still && activity === "talk") {
      const partner = nodeOf(talk.a === state.key ? talk.b : talk.a);
      const toward = partner && parseFloat(partner.style.left) < parseFloat(node.style.left) ? "left" : "right";
      // A mirrored seat draws the figure flipped, so its head turns the other way.
      set("turn", mirroredFacing(node.dataset.seatFacing) ? (toward === "left" ? "right" : "left") : toward);
      if (talk.speaker === state.key && now < talk.turnUntil - 180) { glyph = talk.glyph; side = toward; }
    } else set("turn", "");
    bubble(node, glyph, side);
  }

  function tick() {
    const now = performance.now();
    const delta = Math.min(now - previous, 500);
    previous = now;
    if (document.hidden || root.closest("[hidden]")) {
      // Hidden views pause: shift every deadline by the paused time.
      for (const state of states.values()) for (const field of ["until", "sipAt", "sipUntil", "pageAt", "pageUntil"]) state[field] += delta;
      if (talk) { talk.until += delta; talk.turnUntil += delta; }
      nextTalk += delta;
      return;
    }
    const still = !motionAllowed();
    const present = members.map(([key]) => [key, nodeOf(key)]).filter(([, node]) => seated(node));
    if (talk && (now > talk.until || still || !present.some(([key]) => key === talk.a) || !present.some(([key]) => key === talk.b))) {
      talk = null;
      nextTalk = now + between(TALK_GAP);
    }
    if (!talk && !still && present.length >= 2 && now > nextTalk) {
      // Usually the nearest neighbour, sometimes anyone else; the same pair rarely talks twice in a row.
      const choose = () => {
        const [a, node] = pick(present);
        const others = present.filter(([key, other]) => key !== a && other.dataset.room === node.dataset.room).sort(([, x], [, y]) =>
          Math.hypot(parseFloat(x.style.left) - parseFloat(node.style.left), parseFloat(x.style.top) - parseFloat(node.style.top))
          - Math.hypot(parseFloat(y.style.left) - parseFloat(node.style.left), parseFloat(y.style.top) - parseFloat(node.style.top)));
        const [b] = Math.random() < .55 ? others[0] : pick(others);
        return [a, b];
      };
      let [a, b] = choose();
      for (let retry = 0; retry < 3 && present.length > 2 && [a, b].sort().join() === lastPair; retry++) [a, b] = choose();
      lastPair = [a, b].sort().join();
      talk = { a, b, until: now + between(TALK_LENGTH), speaker: a, glyph: pick(GLYPHS), turnUntil: now + between(TURN_LENGTH) };
    }
    if (talk && now > talk.turnUntil) {
      talk.speaker = talk.speaker === talk.a ? talk.b : talk.a;
      talk.glyph = pick(GLYPHS.filter((glyph) => glyph !== talk.glyph));
      talk.turnUntil = now + between(TURN_LENGTH);
    }
    const shown = new Set(present.map(([, node]) => node));
    root.querySelectorAll(".agent > .talk-bubble").forEach((element) => { if (element.parentElement.dataset.room === room && !shown.has(element.parentElement)) element.remove(); });
    for (const [key, node] of present) {
      const state = states.get(key);
      if (!state) continue;
      if (!still) {
        if (now > state.until) spell(state, now);
        if (now > state.sipAt) {
          state.sipUntil = now + state.profile.sipLength * 1000 * between([.85, 1.15]);
          state.sipAt = now + state.profile.sipEvery * 1000 * between([.8, 1.2]);
        }
        if (now > state.pageAt) {
          state.pageUntil = now + 650;
          state.pageAt = now + state.profile.pageEvery * 1000 * between([.8, 1.25]);
        }
      }
      apply(node, state, now, still);
    }
  }
  setInterval(tick, TICK);

  return {
    drink, refill,
    set(key, value) { drinks.set(key, value); },
    // Members are [key, agent_id] pairs of colleagues currently in the Lounge.
    sync(list) {
      members = list;
      const keys = new Set(list.map(([key]) => key));
      for (const [key, agentId] of list) {
        if (states.has(key)) continue;
        const random = seeded("spell:" + agentId);
        const state = { key, profile: profile(key, agentId), activity: "", until: 0 };
        spell(state, performance.now(), random);
        states.set(key, state);
        drink(key, agentId);
      }
      for (const key of [...states.keys()]) if (!keys.has(key)) states.delete(key);
      for (const key of [...drinks.keys()]) if (!keys.has(key)) { drinks.delete(key); profiles.delete(key); }
      if (talk && (!keys.has(talk.a) || !keys.has(talk.b))) talk = null;
    },
    // Re-apply the current activity after a node was redrawn.
    decorate(node, key) {
      const state = states.get(key);
      if (state && seated(node)) apply(node, state, performance.now(), !motionAllowed());
    },
  };
}
