// Measured display interiors share their current slides across every artwork copy.
const NS = "http://www.w3.org/2000/svg";
const WIDTH = 100, HEIGHT = 60;
const SCREENS = [
  { id: "meeting", quad: [[1016,152],[1070,118],[1070,162],[1016,196]], interval: [16000,24000] },
  { id: "meeting-east", quad: [[1232,298],[1286,262],[1286,307],[1232,343]], interval: [25000,33000] },
];
const HEADER = '<rect width="100" height="60" fill="#edf1ed"/><rect width="100" height="8" fill="#536d7c"/>'
  + '<rect x="6" y="3" width="22" height="2" fill="#edf1ed"/>';
const SLIDES = [
  '<path d="M12 17V50H91" fill="none" stroke="#b5c6c2" stroke-width="2"/>'
    + '<path d="M22 48V34H34V48M43 48V25H55V48M64 48V16H76V48" fill="#83a8a1"/>'
    + '<path d="M22 30L49 21L77 12" fill="none" stroke="#bb995e" stroke-width="2"/>',
  '<path d="M11 17V49H91M12 39L27 35L43 39L60 24L76 28L89 17" fill="none" stroke="#6f95a9" stroke-width="3"/>'
    + '<path d="M12 44L27 40L43 44L60 36L76 39L89 32" fill="none" stroke="#b39a70" stroke-width="2"/>',
  '<path d="M28 30H43M57 30H72" stroke="#90a5ab" stroke-width="3"/>'
    + '<rect x="9" y="20" width="22" height="20" rx="2" fill="#8faca4"/>'
    + '<rect x="39" y="16" width="22" height="28" rx="2" fill="#7b95aa"/>'
    + '<rect x="69" y="20" width="22" height="20" rx="2" fill="#bfaa80"/>',
  '<rect x="9" y="15" width="82" height="37" rx="2" fill="#3f5361"/>'
    + '<path d="M16 22H48M23 29H73M23 36H62M16 43H52" stroke="#a7c7bc" stroke-width="3"/>'
    + '<path d="M53 22H74M67 36H81" stroke="#d0b77e" stroke-width="3"/>',
];
const states = SCREENS.map((screen, slide) => ({ slide, revision: 0, next: 0 }));
const delay = (screen) => screen.interval[0] + Math.random() * (screen.interval[1] - screen.interval[0]);
const content = (state) => HEADER + SLIDES[state.slide];

export function screenArtwork(scope, screen, state, art, prefix = "presentation") {
  const [tl,tr,,bl] = screen.quad, id = `${scope}-screen-${screen.id}`;
  const matrix = [(tr[0]-tl[0])/WIDTH,(tr[1]-tl[1])/WIDTH,
    (bl[0]-tl[0])/HEIGHT,(bl[1]-tl[1])/HEIGHT,...tl];
  const power = state.power === undefined ? "" : ` data-power="${state.power ? "on" : "off"}"`;
  return `<defs><clipPath id="${id}"><polygon points="${screen.quad.map((p) => p.join(",")).join(" ")}"/></clipPath></defs>`
    + `<g data-${prefix}-screen="${screen.id}" data-slide="${state.slide}" data-revision="${state.revision}"${power} clip-path="url(#${id})">`
    + `<g data-${prefix}-content transform="matrix(${matrix.join(" ")})">${art}</g></g>`;
}

export function presentationArtwork(scope) {
  return SCREENS.map((screen, index) => screenArtwork(scope, screen, states[index], content(states[index]))).join("");
}

export function mountPresentations(world, { motionAllowed, paused }) {
  const layer = document.createElementNS(NS, "svg");
  layer.setAttribute("viewBox", "0 0 1536 1024");
  layer.setAttribute("class", "artwork-patch presentation-layer");
  layer.setAttribute("aria-hidden", "true");
  layer.style.zIndex = "0";
  layer.innerHTML = presentationArtwork("presentation-base");
  world.append(layer);
  let branch = null, suspended = false;
  const inactive = () => document.hidden || !world.getClientRects().length || !motionAllowed() || paused();
  const schedule = (now) => states.forEach((state, index) => { state.next = now + delay(SCREENS[index]); });
  const draw = () => world.querySelectorAll("[data-presentation-screen]").forEach((node) => {
    const state = states[SCREENS.findIndex((screen) => screen.id === node.dataset.presentationScreen)];
    node.dataset.slide = state.slide;
    node.dataset.revision = state.revision;
    node.querySelector("[data-presentation-content]").innerHTML = content(state);
  });
  return {
    update(identity) {
      if (branch === identity) return;
      branch = identity;
      states.forEach((state) => { state.slide = Math.floor(Math.random() * SLIDES.length); state.revision = 0; });
      schedule(Date.now()); suspended = inactive(); draw();
    },
    pause() { suspended = true; },
    tick() {
      if (inactive()) { suspended = true; return; }
      const now = Date.now();
      if (suspended) { schedule(now); suspended = false; return; }
      let changed = false;
      states.forEach((state, index) => {
        if (now < state.next) return;
        state.slide = (state.slide + 1 + Math.floor(Math.random() * (SLIDES.length - 1))) % SLIDES.length;
        state.revision++; state.next = now + delay(SCREENS[index]); changed = true;
      });
      if (changed) draw();
    },
  };
}
