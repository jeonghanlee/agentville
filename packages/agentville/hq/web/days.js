// Calendar days and durations. A zone is an IANA time zone from branchZone(), or "" for browser time.
const FORMATS = new Map();

function parts(ms, zone) {
  if (!zone) {
    const at = new Date(ms);
    return { year: at.getFullYear(), month: at.getMonth() + 1, day: at.getDate(), hour: at.getHours(), minute: at.getMinutes(), second: at.getSeconds() };
  }
  if (!FORMATS.has(zone)) {
    FORMATS.set(zone, new Intl.DateTimeFormat("en-US", { timeZone: zone, hourCycle: "h23", year: "numeric", month: "numeric",
      day: "numeric", hour: "numeric", minute: "numeric", second: "numeric" }));
  }
  const out = {};
  for (const part of FORMATS.get(zone).formatToParts(new Date(ms))) if (part.type !== "literal") out[part.type] = Number(part.value);
  return out;
}
// "YYYY-MM-DD" of an instant.
export function dayOf(ms, zone) {
  const p = parts(ms, zone);
  return String(p.year).padStart(4, "0") + "-" + String(p.month).padStart(2, "0") + "-" + String(p.day).padStart(2, "0");
}
// The first instant of a day; the zone's wall clock is compared until it reads midnight, which covers daylight saving.
export function dayStart(day, zone) {
  const [year, month, date] = day.split("-").map(Number);
  if (!zone) return new Date(year, month - 1, date).getTime();
  const midnight = Date.UTC(year, month - 1, date);
  let guess = midnight;
  for (let i = 0; i < 3; i++) {
    const p = parts(guess, zone);
    const offset = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - midnight;
    if (!offset) break;
    guess -= offset;
  }
  return guess;
}
export function shiftDay(day, days) {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date + days)).toISOString().slice(0, 10);
}
export function dayEnd(day, zone) { return dayStart(shiftDay(day, 1), zone); }
// Hours and minutes, "h:mm"; zero is "-".
export function duration(seconds) {
  if (!seconds) return "-";
  const minutes = Math.round(seconds / 60);
  return Math.floor(minutes / 60) + ":" + String(minutes % 60).padStart(2, "0");
}
