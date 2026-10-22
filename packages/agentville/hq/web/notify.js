// Browser notifications: opt-in, sent only for transitions observed while the page is open.
// Notifications carry names and aliases only; tool names, arguments, prompts, paths, and accounts never leave the page.
import { t } from "./i18n.js";

const STORAGE_KEY = "agentville-notifications";
const ALERT_STATES = ["waiting", "error"];
const SUBJECT_INTERVAL = 30000;
const SUMMARY_AFTER = 3;
const TAG = "agentville:";

function supported() {
  try { return typeof Notification === "function"; } catch { return false; }
}
function permission() {
  try { return Notification.permission; } catch { return "denied"; }
}
function saved() {
  try { return localStorage.getItem(STORAGE_KEY) === "on"; } catch { return false; }
}
function save(on) {
  try { localStorage.setItem(STORAGE_KEY, on ? "on" : "off"); } catch {}
}
// Older browsers take a callback instead of returning a promise.
function requestPermission() {
  return new Promise((resolve) => {
    try {
      const result = Notification.requestPermission(resolve);
      if (result && typeof result.then === "function") result.then(resolve, () => resolve(permission()));
    } catch { resolve(permission()); }
  });
}

// `toggle` is the settings checkbox, `status` its state line, and `open(target)` reveals a subject in the page.
export function createNotifications({ toggle, status, demo, open }) {
  // seen: last observed marker per subject; sent: time and marker of the last notification; pending: deferred by the rate limit.
  const seen = new Map(), sent = new Map(), pending = new Map();
  let wanted = saved();

  function availability() {
    if (demo) return "demo";
    if (!supported()) return "unsupported";
    if (!window.isSecureContext) return "insecure";
    if (permission() === "denied") return "blocked";
    return "";
  }
  function enabled() { return wanted && !availability() && permission() === "granted"; }
  function refresh() {
    const blocked = availability();
    toggle.disabled = Boolean(blocked);
    toggle.checked = enabled();
    status.textContent = t("notify.status." + (blocked || (enabled() ? "on" : "off")));
    status.classList.toggle("blocked", Boolean(blocked) && blocked !== "demo");
  }
  async function change() {
    if (!toggle.checked) { wanted = false; save(false); refresh(); return; }
    if (availability()) { refresh(); return; }
    // The permission prompt is requested from the click itself.
    const answer = permission() === "granted" ? "granted" : await requestPermission();
    wanted = answer === "granted";
    save(wanted);
    refresh();
  }
  function marker(subject) {
    if (subject.kind === "branch") return subject.reachable ? "reachable" : "unreachable";
    return ALERT_STATES.includes(subject.state) ? subject.state + "@" + subject.since : subject.state;
  }
  function content(subject) {
    if (subject.kind === "branch") {
      const key = subject.reachable ? "reachable" : "unreachable";
      return { title: t("notify.branch." + key, { branch: subject.branch }), body: t("notify.branch." + key + "Body") };
    }
    return { title: t("notify." + subject.state, { name: subject.name }),
      body: [subject.provider, subject.project, subject.branch].join(" · ") };
  }
  function show(title, body, tag, target) {
    try {
      const notification = new Notification(title, { body, tag, icon: new URL("favicon.svg", location.href).href });
      notification.onclick = (event) => {
        event?.preventDefault?.();
        try { window.focus(); } catch {}
        open(target);
        try { notification.close(); } catch {}
      };
    } catch {}
  }
  // A subject notified less than 30 s ago waits for the end of that window and is sent only if it still holds.
  function deliver(changes) {
    const now = Date.now(), due = [];
    for (const subject of changes) {
      const wait = (sent.get(subject.id)?.at ?? -Infinity) + SUBJECT_INTERVAL - now;
      if (wait <= 0) { due.push(subject); continue; }
      if (!pending.has(subject.id)) setTimeout(() => flush(subject.id), wait);
      pending.set(subject.id, subject);
    }
    for (const subject of due) { pending.delete(subject.id); sent.set(subject.id, { at: now, mark: marker(subject) }); }
    if (due.length > SUMMARY_AFTER) {
      const colleagues = due.filter((subject) => subject.kind === "colleague");
      const names = due.slice(0, SUMMARY_AFTER).map((subject) => subject.kind === "branch" ? subject.branch : subject.name);
      const first = colleagues[0] || due[0];
      show(t(colleagues.length === due.length ? "notify.summary" : "notify.summaryMixed", { n: due.length }),
        names.join(", ") + (due.length > names.length ? " +" + (due.length - names.length) : ""), TAG + "summary", first.target);
      return;
    }
    for (const subject of due) {
      const { title, body } = content(subject);
      show(title, body, TAG + subject.id, subject.target);
    }
  }
  function flush(id) {
    const subject = pending.get(id);
    pending.delete(id);
    if (!subject || !enabled() || seen.get(id) !== marker(subject) || sent.get(id)?.mark === marker(subject)) return;
    deliver([subject]);
  }
  // A baseline update (first state after load or after a reconnect) only records states.
  // Subjects seen for the first time are recorded, never announced.
  function observe(subjects, baseline) {
    const changes = [], present = new Set();
    if (baseline) pending.clear();
    for (const subject of subjects) {
      present.add(subject.id);
      const previous = seen.get(subject.id), mark = marker(subject);
      seen.set(subject.id, mark);
      if (baseline || previous === undefined || previous === mark) continue;
      if (subject.kind === "branch" || ALERT_STATES.includes(subject.state)) changes.push(subject);
    }
    for (const id of seen.keys()) if (!present.has(id)) seen.delete(id);
    if (changes.length && enabled()) deliver(changes);
  }

  toggle.addEventListener("change", change);
  try {
    navigator.permissions?.query({ name: "notifications" }).then((state) => { state.onchange = refresh; }, () => {});
  } catch {}
  refresh();
  return { observe, relabel: refresh };
}
