// Reads HQ history (Section 4.4 of the architecture): the kept range, past state, recorded changes, and the work log.
// Demo mode answers the same calls from synthetic history, without contacting HQ.
import { demoHistory } from "./demo.js";

const iso = (ms) => new Date(ms).toISOString();

export function createHistory({ demo, token, now }) {
  if (demo) {
    const history = demoHistory(now);
    return {
      range: async () => history.range(),
      stateAt: async (ms) => history.stateAt(ms),
      changes: async (from, to, branchId) => history.changes(from, to, branchId),
      worklog: async (from, to, branchId) => history.worklog(from, to, branchId),
    };
  }
  // The viewer token goes in a header, never in the URL.
  async function get(path, params = {}) {
    const url = new URL(path, location.origin);
    for (const [key, value] of Object.entries(params)) if (value) url.searchParams.set(key, value);
    const response = await fetch(url, { cache: "no-store", headers: token ? { Authorization: "Bearer " + token } : {} });
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }
  return {
    range: async () => {
      const range = await get("/api/v1/history");
      return { from: range.from ? Date.parse(range.from) : null, to: Date.parse(range.to) };
    },
    stateAt: (ms) => get("/api/v1/state", { at: iso(ms) }),
    changes: (from, to, branchId) => get("/api/v1/changes", { from: iso(from), to: iso(to), branch_id: branchId }),
    worklog: (from, to, branchId) => get("/api/v1/worklog", { from: iso(from), to: iso(to), branch_id: branchId }),
  };
}
