"use strict";

// --- Parameter metadata (descriptions + danger thresholds) -----------------
// Injected server-side as JSON; keyed by parameter for quick lookup.

const PARAMETERS = (() => {
  const el = document.getElementById("parameters-data");
  if (!el) return [];
  try {
    return JSON.parse(el.textContent) || [];
  } catch (e) {
    console.error("bad parameters payload", e);
    return [];
  }
})();

const PARAM_BY_KEY = Object.fromEntries(PARAMETERS.map((p) => [p.key, p]));

// Colors for the danger reference lines drawn on the chart.
const THRESHOLD_STYLES = {
  warn_high: { color: "#d29922", label: "Warn" },
  critical_high: { color: "#f85149", label: "Critical" },
  warn_low: { color: "#d29922", label: "Warn (low)" },
  critical_low: { color: "#f85149", label: "Critical (low)" },
};

// --- Live values + alerts via SSE -----------------------------------------

const statusEl = document.getElementById("status");
const bannerEl = document.getElementById("alert-banner");

function severityForParam(alerts, key) {
  const match = alerts.find((a) => a.param === key);
  return match ? match.severity : "ok";
}

function formatValue(v) {
  // Guard against null/undefined/NaN/Infinity so one bad value can't abort
  // the whole render loop (which previously left later cards stuck on "—").
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function renderCards(reading, alerts) {
  const values = (reading && reading.values) || {};
  document.querySelectorAll(".card").forEach((card) => {
    const key = card.dataset.key;
    const valEl = document.getElementById("val-" + key);
    if (!valEl) return;
    valEl.textContent = key in values ? formatValue(values[key]) : "—";
    card.classList.remove("warn", "critical");
    const sev = severityForParam(alerts, key);
    if (sev === "warn" || sev === "critical") card.classList.add(sev);
  });
}

function renderBanner(alerts) {
  const active = alerts.filter((a) => a.severity === "warn" || a.severity === "critical");
  if (active.length === 0) {
    bannerEl.classList.add("hidden");
    return;
  }
  const hasCritical = active.some((a) => a.severity === "critical");
  bannerEl.classList.remove("hidden");
  bannerEl.classList.toggle("critical", hasCritical);
  const names = active.map((a) => `${a.param.toUpperCase()} (${a.severity})`).join(", ");
  bannerEl.textContent = `⚠ Active alerts: ${names}`;
}

function connectStream() {
  const source = new EventSource("/api/stream");
  source.addEventListener("update", (ev) => {
    statusEl.textContent = "live";
    statusEl.className = "status live";
    try {
      const data = JSON.parse(ev.data);
      renderCards(data.reading, data.alerts || []);
      renderBanner(data.alerts || []);
    } catch (e) {
      console.error("bad SSE payload", e);
    }
  });
  source.onerror = () => {
    statusEl.textContent = "reconnecting…";
    statusEl.className = "status error";
  };
}

// --- Historical trend chart -----------------------------------------------

let chart = null;
const CHART_REFRESH_MS = 30000;

// Chart.js plugin: draws horizontal danger-level reference lines using the
// thresholds stashed on chart.$thresholds by loadChart().
const thresholdLinesPlugin = {
  id: "thresholdLines",
  afterDatasetsDraw(c) {
    const thresholds = c.$thresholds;
    if (!thresholds) return;
    const yScale = c.scales.y;
    const { left, right } = c.chartArea;
    const ctx = c.ctx;
    ctx.save();
    for (const [name, value] of Object.entries(thresholds)) {
      if (typeof value !== "number" || !Number.isFinite(value)) continue;
      if (value < yScale.min || value > yScale.max) continue;
      const style = THRESHOLD_STYLES[name];
      if (!style) continue;
      const y = yScale.getPixelForValue(value);
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = style.color;
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = style.color;
      ctx.font = "11px system-ui, sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "bottom";
      ctx.fillText(`${style.label} (${value})`, right - 4, y - 2);
    }
    ctx.restore();
  },
};

function initChart() {
  const ctx = document.getElementById("trend-chart").getContext("2d");
  chart = new Chart(ctx, {
    type: "line",
    data: { labels: [], datasets: [] },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { color: "#8b98a5" }, grid: { color: "#2d3745" } },
        y: { ticks: { color: "#8b98a5" }, grid: { color: "#2d3745" } },
      },
      plugins: { legend: { labels: { color: "#e6edf3" } } },
    },
    plugins: [thresholdLinesPlugin],
  });
}

function updateDescription(metric) {
  const el = document.getElementById("chart-description");
  if (!el) return;
  const spec = PARAM_BY_KEY[metric];
  el.textContent = spec && spec.description ? spec.description : "";
}

async function loadChart() {
  const metric = document.getElementById("chart-metric").value;
  const bucket = document.getElementById("chart-bucket").value;
  const hours = parseInt(document.getElementById("chart-range").value, 10);
  updateDescription(metric);
  const to = new Date();
  const from = new Date(to.getTime() - hours * 3600 * 1000);
  const url = `/api/history?metric=${metric}&bucket=${bucket}` +
    `&from=${from.toISOString()}&to=${to.toISOString()}`;
  const resp = await fetch(url);
  const data = await resp.json();
  const series = data.series || [];

  const labels = series.map((s) => new Date(s.bucket_start).toLocaleString());
  const avg = series.map((s) => s.avg);
  const upper = series.map((s) => (s.avg != null ? s.avg + (s.stddev || 0) : null));
  const lower = series.map((s) => (s.avg != null ? s.avg - (s.stddev || 0) : null));

  chart.data.labels = labels;
  chart.data.datasets = [
    {
      label: `${metric} avg`,
      data: avg,
      borderColor: "#3b82f6",
      backgroundColor: "rgba(59,130,246,0.15)",
      tension: 0.2,
      fill: false,
    },
    {
      label: "+σ",
      data: upper,
      borderColor: "rgba(59,130,246,0.35)",
      borderDash: [4, 4],
      pointRadius: 0,
      fill: "+1",
      backgroundColor: "rgba(59,130,246,0.08)",
    },
    {
      label: "−σ",
      data: lower,
      borderColor: "rgba(59,130,246,0.35)",
      borderDash: [4, 4],
      pointRadius: 0,
      fill: false,
    },
  ];
  // Danger-level reference lines for the selected metric (if configured).
  const spec = PARAM_BY_KEY[metric];
  chart.$thresholds = (spec && spec.thresholds) || {};
  chart.update();
}

function wireControls() {
  ["chart-metric", "chart-bucket", "chart-range"].forEach((id) => {
    document.getElementById(id).addEventListener("change", loadChart);
  });
}

window.addEventListener("DOMContentLoaded", () => {
  initChart();
  wireControls();
  loadChart();
  connectStream();
  // Auto-refresh the trend chart every 30 seconds.
  setInterval(() => {
    loadChart().catch((e) => console.error("chart refresh failed", e));
  }, CHART_REFRESH_MS);
});
