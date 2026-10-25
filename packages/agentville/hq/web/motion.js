// Work gestures are decorative and never change reported activity.
const GESTURES = [
  { name: "type-steady", duration: [3200, 6200], tempo: [.42, .62] },
  { name: "type-quick", duration: [2400, 4400], tempo: [.22, .34] },
  { name: "type-hunt", duration: [3000, 5800], tempo: [1.3, 1.9] },
  { name: "mouse-move", duration: [2600, 4800], tempo: [1.6, 2.4] },
  { name: "mouse-click", duration: [2000, 3800], tempo: [.9, 1.5] },
  { name: "mouse-scroll", duration: [2600, 5000], tempo: [1.1, 1.8] },
];
export const WORK_MOTION_INTERVAL = 400;
const progress = new WeakMap();
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

function between([min, max]) {
  return min + Math.random() * (max - min);
}

export function updateWorkGestures(root) {
  if (document.hidden || root.closest("[hidden]") || reducedMotion.matches
      || document.body.classList.contains("reduce-motion")) return;
  const now = performance.now();
  for (const svg of root.querySelectorAll('.character[data-activity="working"]')) {
    if (svg.closest(".filtered") || svg.closest('.agent[data-room^="meeting"]')) continue;
    const previous = progress.get(svg);
    if (previous && now < previous.until) continue;
    const choices = GESTURES.filter((gesture) => gesture.name !== previous?.name);
    const gesture = choices[Math.floor(Math.random() * choices.length)];
    const tempo = between(gesture.tempo);
    svg.dataset.workGesture = gesture.name;
    svg.style.setProperty("--work-tempo", tempo.toFixed(3) + "s");
    svg.style.setProperty("--work-phase", (-Math.random() * tempo).toFixed(3) + "s");
    progress.set(svg, { name: gesture.name, until: now + between(gesture.duration) });
  }
}
