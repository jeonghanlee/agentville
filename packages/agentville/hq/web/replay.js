// Timeline replay: the page shows the state HQ had at a chosen time. A chosen time is read exactly; playback reads
// one state per replayed minute, so playing at any speed asks HQ at most once per minute. Fetches are debounced and
// cached. The live socket keeps running meanwhile.
export const SPEEDS = [1, 10, 60];
const MINUTE = 60000;
const TICK = 250;
const DEBOUNCE = 150;
const CACHE = 360;

// `shown()` repaints after a new replay state arrives; `moved()` updates the time display on every step.
export function createReplay({ history, shown, moved, clock = () => Date.now() }) {
  const cache = new Map();
  let active = false, at = 0, playing = false, speed = 1, state = null, failed = false;
  let timer = null, pending = null, ticket = 0, lastTick = 0;
  // HQ's clock minus the browser's, so the end of the kept range moves with HQ time.
  let range = { from: null, to: 0 }, offset = 0;

  async function refreshRange() {
    try {
      const fetched = await history.range();
      offset = fetched.to - clock();
      range = fetched;
    } catch {}
    return range;
  }
  function now() { return clock() + offset; }
  function clamp(ms) { return Math.min(Math.max(ms, range.from ?? ms), now()); }
  // One state per replayed minute, read at its last instant (or now), so changes within the minute are shown.
  function load(ms, exact) {
    const key = exact ? "at:" + ms : Math.floor(ms / MINUTE);
    if (!cache.has(key)) {
      const when = exact ? ms : clamp(Math.min((key + 1) * MINUTE - 1, now()));
      cache.set(key, history.stateAt(when).catch((error) => { cache.delete(key); throw error; }));
      if (cache.size > CACHE) cache.delete(cache.keys().next().value);
    }
    return cache.get(key);
  }
  function fetchSoon(exact, delay) {
    clearTimeout(pending);
    const mine = ++ticket, wanted = at;
    pending = setTimeout(async () => {
      try {
        const next = await load(wanted, exact);
        if (mine === ticket && active) { state = next; failed = false; shown(); }
      } catch {
        if (mine === ticket && active) { failed = true; shown(); }
      }
    }, delay);
  }
  // A seek from a click is read at once; one from dragging the slider after a short pause.
  function seek(ms, immediate = false) {
    if (range.from === null) return;
    active = true;
    at = clamp(ms);
    fetchSoon(true, immediate ? 0 : DEBOUNCE);
    moved();
  }
  function step() {
    const time = clock();
    at = clamp(at + (time - lastTick) * speed);
    lastTick = time;
    if (at >= now()) pause();
    fetchSoon(false, DEBOUNCE);
    moved();
  }
  function play() {
    if (!active) return;
    if (at >= now()) at = range.from ?? at;
    playing = true;
    lastTick = clock();
    clearInterval(timer);
    timer = setInterval(step, TICK);
    moved();
  }
  function pause() {
    playing = false;
    clearInterval(timer);
    moved();
  }
  function stop() {
    pause();
    clearTimeout(pending);
    ticket++;
    active = false; state = null; failed = false;
    shown();
  }
  // The nearest change time before or after the current time, from a sorted list of instants.
  function jump(times, direction) {
    const target = direction < 0 ? [...times].reverse().find((ms) => ms < at - 500) : times.find((ms) => ms > at + 500);
    if (target !== undefined) { pause(); seek(target, true); }
  }
  return {
    get active() { return active; }, get at() { return at; }, get state() { return state; }, get failed() { return failed; },
    get playing() { return playing; }, get speed() { return speed; }, get range() { return range; },
    now, refreshRange, seek, play, pause, stop, jump,
    toggle() { if (playing) pause(); else play(); },
    setSpeed(next) { speed = SPEEDS.includes(next) ? next : 1; lastTick = clock(); moved(); },
  };
}
