// Regional forecasts remain separate from colleague state and the selected window-light period.
import { WINDOWS } from "./office-layout.js";
import { t, locale } from "./i18n.js";

const REFRESH = 60000;
const SEASONS = ["spring", "summer", "autumn", "winter"];
const SOURCE = "https://www.met.no/en";
const LICENSE = "https://creativecommons.org/licenses/by/4.0/";

function saved(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function save(key, value) { try { localStorage.setItem(key, value); } catch {} }
function text(node, value) { if (node.textContent !== value) node.textContent = value; }

export function calendarSeason(now, zone, hemisphere) {
  if (!["north", "south"].includes(hemisphere)) return "";
  const month = Number(new Intl.DateTimeFormat("en-US", { ...(zone ? { timeZone: zone } : {}), month: "numeric" })
    .format(now));
  const index = Math.floor((month % 12) / 3);
  return ["winter", "spring", "summer", "autumn"][(index + (hemisphere === "south" ? 2 : 0)) % 4];
}

export function createWeather({ world, scene, report, seasonReport, source, license, updated, seasonSetting,
  weatherSetting, demo, token }) {
  const layer = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  layer.setAttribute("viewBox", "0 0 1536 1024");
  layer.setAttribute("class", "weather-layer"); layer.setAttribute("aria-hidden", "true");
  layer.innerHTML = '<defs><clipPath id="weather-window-glass">'
    + WINDOWS.map((points) => '<polygon points="' + points + '"/>').join("") + '</clipPath></defs>'
    + '<g clip-path="url(#weather-window-glass)"><rect class="season-tint" width="1536" height="1024"/>'
    + '<rect class="weather-cloud" width="1536" height="1024"/>'
    + '<g class="weather-rain">' + Array.from({ length: 80 }, (_, i) => {
      const x = 40 + i % 20 * 78, y = 30 + Math.floor(i / 20) * 120;
      return '<path d="M' + x + ' ' + y + 'l-7 18"/>';
    }).join("") + '</g><g class="weather-snow">'
    + Array.from({ length: 80 }, (_, i) => '<circle cx="' + (40 + i % 20 * 78)
      + '" cy="' + (30 + Math.floor(i / 20) * 120) + '" r="2.5"/>').join("") + '</g></g>';
  world.append(layer);
  const stored = saved("agentville-season", "auto");
  seasonSetting.value = ["auto", "off", ...SEASONS].includes(stored) ? stored : "auto";
  weatherSetting.checked = saved("agentville-weather", "on") !== "off";
  source.href = SOURCE; license.href = LICENSE;
  let context = null, entry = null, identity = null, last = -Infinity, ticket = 0, controller = null;
  function effect(value) { if (scene.dataset.weather !== value) scene.dataset.weather = value; }

  function paint() {
    if (!context) return;
    const { now, zone, replay } = context;
    const selected = seasonSetting.value;
    const season = selected === "off" ? "" : SEASONS.includes(selected) ? selected
      : calendarSeason(now, zone, entry?.hemisphere);
    if (scene.dataset.season !== season) scene.dataset.season = season;
    text(seasonReport, season ? t("season." + season) : t("season.none"));
    const showSource = weatherSetting.checked && !replay && entry?.updated_at && !demo;
    source.hidden = license.hidden = !showSource;
    updated.hidden = !showSource;
    if (!weatherSetting.checked || replay) {
      const status = replay && weatherSetting.checked ? "replay" : "off";
      effect(""); report.dataset.status = status; text(report, t("weather." + status)); return;
    }
    let status = entry?.status || (identity ? "loading" : "unconfigured");
    const valid = entry && Date.parse(entry.valid_from) <= now.getTime() && now.getTime() < Date.parse(entry.valid_to)
      && now.getTime() < Date.parse(entry.expires_at);
    if (status === "available" && !valid) status = "stale";
    report.dataset.status = status;
    const temperature = typeof entry?.temperature === "number" && Number.isFinite(entry.temperature)
      ? new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(entry.temperature) : "";
    const condition = t("weather." + (entry?.condition || "unknown"));
    const label = status === "available"
      ? t(demo ? "weather.demo" : "weather.forecast", { condition, temperature }) : t("weather." + status);
    text(report, label + (entry?.deprecated ? " - " + t("weather.deprecated") : ""));
    effect(status === "available" ? entry.condition : "");
    if (showSource) {
      const time = new Date(entry.updated_at);
      if (Number.isFinite(time.getTime())) {
        updated.hidden = false; updated.dateTime = time.toISOString();
        text(updated, t("weather.updated", { time: time.toLocaleString(locale(), zone ? { timeZone: zone } : {}) }));
      }
      source.hidden = license.hidden = false;
    }
    text(source, t("weather.source")); text(license, t("weather.license"));
  }

  async function load() {
    const mine = ++ticket;
    controller?.abort(); controller = new AbortController(); last = Date.now();
    try {
      const response = await fetch("/api/v1/weather?branch_id=" + encodeURIComponent(identity), {
        cache: "no-store", signal: controller.signal, headers: token ? { Authorization: "Bearer " + token } : {},
      });
      if (!response.ok) throw new Error("Weather HTTP status " + response.status);
      const value = await response.json();
      if (mine !== ticket) return;
      entry = value;
    } catch (error) {
      if (mine !== ticket || error.name === "AbortError") return;
      entry = { ...entry, status: entry?.updated_at ? "stale" : "unavailable" };
    }
    paint();
  }

  function update(next = context) {
    if (!next) return;
    context = next;
    if (identity !== next.branchId) {
      identity = next.branchId; ticket++; controller?.abort(); entry = null; last = -Infinity;
    }
    if (demo && identity) {
      entry = { status: "available", hemisphere: identity === "garden" ? "south" : "north", temperature: 12,
        condition: "rain", valid_from: new Date(next.now.getTime() - REFRESH).toISOString(),
        valid_to: new Date(next.now.getTime() + REFRESH).toISOString(),
        expires_at: new Date(next.now.getTime() + REFRESH).toISOString() };
    } else if (identity && Date.now() - last >= REFRESH && (!next.replay || !entry)) { load(); }
    paint();
  }
  seasonSetting.addEventListener("change", () => { save("agentville-season", seasonSetting.value); paint(); });
  weatherSetting.addEventListener("change", () => {
    save("agentville-weather", weatherSetting.checked ? "on" : "off"); last = -Infinity; update();
  });
  return { update, relabel: paint };
}
