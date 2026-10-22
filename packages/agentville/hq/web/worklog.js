// Work log table: time per state for one day, grouped Branch, Project, colleague, with subtotals.
import { el } from "./dom.js";
import { duration } from "./days.js";
import { t } from "./i18n.js";

const STATES = ["working", "thinking", "waiting", "idle", "completed", "error", "limited", "unknown"];
// Columns shown only when some row has time in them.
const OPTIONAL = new Set(["thinking", "completed", "limited", "unknown", "unobserved"]);

function total(rows) {
  const sum = { seconds: {}, waits: 0, errors: 0, limits: 0, longest_wait: 0 };
  for (const row of rows) {
    for (const [name, value] of Object.entries(row.seconds)) sum.seconds[name] = (sum.seconds[name] || 0) + value;
    sum.waits += row.waits; sum.errors += row.errors; sum.limits += row.limits;
    sum.longest_wait = Math.max(sum.longest_wait, row.longest_wait);
  }
  return sum;
}
function group(rows, key) {
  const groups = new Map();
  for (const row of rows) {
    if (!groups.has(row[key])) groups.set(row[key], []);
    groups.get(row[key]).push(row);
  }
  return groups;
}

// `names` gives { colleague(row), branch(branchId), project(row), badge(provider), repository(projectId) }.
export function worklogTable(rows, names) {
  const columns = ["on_duty", ...STATES, "unobserved"].filter((name) => !OPTIONAL.has(name) || rows.some((r) => r.seconds[name] > 0));
  const heading = [t("worklog.colleague"), ...columns.map((name) => name === "on_duty" ? t("worklog.onDuty")
    : name === "unobserved" ? t("worklog.unobserved") : t("state." + name)),
  t("worklog.waits"), t("worklog.longestWait"), t("worklog.errors"), t("worklog.limits")];
  const cells = (sum) => [...columns.map((name) => el("td", { class: "number" }, duration(sum.seconds[name]))),
    el("td", { class: "number" }, sum.waits || "-"), el("td", { class: "number" }, duration(sum.longest_wait)),
    el("td", { class: "number" }, sum.errors || "-"), el("td", { class: "number" }, sum.limits || "-")];
  const body = [];
  for (const [branchId, branchRows] of group(rows, "branch_id")) {
    body.push(el("tr", { class: "worklog-branch" }, el("th", { scope: "row" }, names.branch(branchId)), cells(total(branchRows))));
    for (const projectRows of group(branchRows, "project_id").values()) {
      const first = projectRows[0];
      body.push(el("tr", { class: "worklog-project" },
        el("th", { scope: "row" }, names.project(first), " ", names.repository(first.project_id)), cells(total(projectRows))));
      for (const row of projectRows) {
        body.push(el("tr", { class: "worklog-colleague" },
          el("th", { scope: "row" }, names.badge(row.provider), names.colleague(row)), cells(row)));
      }
    }
  }
  if (rows.length) body.push(el("tr", { class: "worklog-total" }, el("th", { scope: "row" }, t("worklog.total")), cells(total(rows))));
  return el("div", { class: "table-scroll" }, el("table", { class: "worklog-table" },
    el("thead", {}, el("tr", {}, heading.map((h, i) => el("th", { scope: "col", class: i ? "number" : "" }, h)))),
    el("tbody", {}, body)));
}
