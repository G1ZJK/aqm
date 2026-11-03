"use strict";

// --- Live values + alerts via SSE -----------------------------------------

const statusEl = document.getElementById("status");
const bannerEl = document.getElementById("alert-banner");

function severityForParam(alerts, key) {
  const match = alerts.find((a) => a.param === key);
  return match ? match.severity : "ok";
}

function renderCards(reading, alerts) {
  const values = (reading && reading.values) || {};
  document.querySelectorAll(".card").forEach((card) => {
    const key = card.dataset.key;
    const valEl = document.getElementById("val-" + key);
    if (key in values) {
      const v = values[key];
      valEl.textContent = Number.isInteger(v) ? v : v.toFixed(1);
    } else {
      valEl.textContent = "—";
    }
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
  });
}

async function loadChart() {
  const metric = document.getElementById("chart-metric").value;
  const bucket = document.getElementById("chart-bucket").value;
  const hours = parseInt(document.getElementById("chart-range").value, 10);
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
