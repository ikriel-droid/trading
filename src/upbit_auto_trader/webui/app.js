const ids = {
  market: document.getElementById("market-value"),
  mode: document.getElementById("mode-value"),
  equity: document.getElementById("equity-value"),
  cash: document.getElementById("cash-value"),
  position: document.getElementById("position-value"),
  pending: document.getElementById("pending-value"),
  summary: document.getElementById("summary-json"),
  signal: document.getElementById("signal-json"),
  backtest: document.getElementById("backtest-json"),
  optimize: document.getElementById("optimize-json"),
  scan: document.getElementById("scan-json"),
  reconcile: document.getElementById("reconcile-json"),
  config: document.getElementById("config-json"),
  paths: document.getElementById("paths-json"),
  readiness: document.getElementById("readiness-json"),
  chart: document.getElementById("price-chart"),
  chartMeta: document.getElementById("chart-meta"),
  csvPath: document.getElementById("csv-path-input"),
  statePath: document.getElementById("state-path-input"),
  refreshSeconds: document.getElementById("refresh-seconds"),
  optimizeTop: document.getElementById("optimize-top-input"),
  scanMaxMarkets: document.getElementById("scan-max-markets-input"),
  quoteCurrency: document.getElementById("quote-currency-input"),
  syncCount: document.getElementById("sync-count-input"),
  cfgBuyThreshold: document.getElementById("cfg-buy-threshold"),
  cfgSellThreshold: document.getElementById("cfg-sell-threshold"),
  cfgMinAdx: document.getElementById("cfg-min-adx"),
  cfgMinBbWidth: document.getElementById("cfg-min-bb-width"),
  cfgVolumeSpike: document.getElementById("cfg-volume-spike"),
  cfgPollSeconds: document.getElementById("cfg-poll-seconds"),
  cfgSelectorMaxMarkets: document.getElementById("cfg-selector-max-markets"),
};

let dashboardState = {
  paths: {},
  app: {},
  defaults: {},
};
let refreshTimer = null;

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function setMetric(element, value) {
  element.textContent = value ?? "-";
}

function currentInputs() {
  return {
    csv_path: ids.csvPath.value.trim(),
    state_path: ids.statePath.value.trim(),
    top: Number(ids.optimizeTop.value || "5"),
    max_markets: Number(ids.scanMaxMarkets.value || "10"),
    quote_currency: ids.quoteCurrency.value.trim() || "KRW",
    sync_count: Number(ids.syncCount.value || "200"),
  };
}

function syncInputsFromDashboard(payload) {
  dashboardState = {
    paths: payload.paths || {},
    app: payload.app || {},
    defaults: payload.ui_defaults || {},
  };

  if (!ids.csvPath.value && payload.paths?.csv_path) {
    ids.csvPath.value = payload.paths.csv_path;
  }
  if (!ids.statePath.value && payload.paths?.state_path) {
    ids.statePath.value = payload.paths.state_path;
  }
  if (!ids.optimizeTop.value && payload.ui_defaults?.optimize_top) {
    ids.optimizeTop.value = payload.ui_defaults.optimize_top;
  }
  if (!ids.scanMaxMarkets.value && payload.ui_defaults?.scan_max_markets) {
    ids.scanMaxMarkets.value = payload.ui_defaults.scan_max_markets;
  }
  if (!ids.quoteCurrency.value && payload.ui_defaults?.quote_currency) {
    ids.quoteCurrency.value = payload.ui_defaults.quote_currency;
  }

  const editableConfig = payload.editable_config || {};
  ids.cfgBuyThreshold.value = editableConfig["strategy.buy_threshold"] ?? "";
  ids.cfgSellThreshold.value = editableConfig["strategy.sell_threshold"] ?? "";
  ids.cfgMinAdx.value = editableConfig["strategy.min_adx"] ?? "";
  ids.cfgMinBbWidth.value = editableConfig["strategy.min_bollinger_width_fraction"] ?? "";
  ids.cfgVolumeSpike.value = editableConfig["strategy.volume_spike_multiplier"] ?? "";
  ids.cfgPollSeconds.value = editableConfig["runtime.poll_seconds"] ?? "";
  ids.cfgSelectorMaxMarkets.value = editableConfig["selector.max_markets"] ?? "";
  ids.config.textContent = pretty(editableConfig);
}

function renderPriceChart(chartPayload) {
  if (!chartPayload || !chartPayload.points || chartPayload.points.length === 0) {
    ids.chart.innerHTML = "";
    ids.chartMeta.textContent = "No chart data";
    return;
  }

  const width = 960;
  const height = 320;
  const padding = 20;
  const closes = chartPayload.points.map((point) => point.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = Math.max(max - min, 1e-9);
  const stepX = (width - (padding * 2)) / Math.max(chartPayload.points.length - 1, 1);

  const coords = chartPayload.points.map((point, index) => {
    const x = padding + (index * stepX);
    const y = height - padding - (((point.close - min) / range) * (height - (padding * 2)));
    return { x, y, close: point.close, timestamp: point.timestamp };
  });

  const linePath = coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${height - padding} L ${coords[0].x} ${height - padding} Z`;
  const latest = coords[coords.length - 1];

  ids.chart.innerHTML = `
    <defs>
      <linearGradient id="price-fill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="rgba(199, 92, 42, 0.34)"></stop>
        <stop offset="100%" stop-color="rgba(199, 92, 42, 0.02)"></stop>
      </linearGradient>
    </defs>
    <path d="${areaPath}" fill="url(#price-fill)"></path>
    <path d="${linePath}" fill="none" stroke="#c75c2a" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
    <circle cx="${latest.x}" cy="${latest.y}" r="6" fill="#8d2f1b"></circle>
  `;
  ids.chartMeta.textContent = `Last ${chartPayload.points.length} candles | low ${min.toFixed(2)} | high ${max.toFixed(2)} | latest ${latest.close.toFixed(2)} @ ${latest.timestamp}`;
}

async function getJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function postJson(url, payload) {
  return getJson(url, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

async function refreshDashboard() {
  try {
    const payload = await getJson("/api/dashboard");
    syncInputsFromDashboard(payload);
    const summary = payload.state_summary || {};
    setMetric(ids.market, payload.app.market);
    setMetric(ids.mode, payload.app.mode);
    setMetric(ids.equity, summary.equity ?? "-");
    setMetric(ids.cash, summary.cash ?? "-");
    setMetric(ids.position, summary.position ? "OPEN" : "FLAT");
    setMetric(ids.pending, summary.pending_order ? summary.pending_order.side : "NONE");
    ids.summary.textContent = pretty(summary);
    ids.signal.textContent = pretty(payload.latest_signal);
    ids.paths.textContent = pretty(payload.paths);
    ids.readiness.textContent = pretty(payload.broker_readiness);
    renderPriceChart(payload.chart);
  } catch (error) {
    ids.summary.textContent = `dashboard error: ${error.message}`;
  }
}

async function runSignal() {
  try {
    ids.signal.textContent = "Running signal...";
    const payload = await postJson("/api/signal", {
      csv_path: currentInputs().csv_path,
    });
    ids.signal.textContent = pretty(payload);
  } catch (error) {
    ids.signal.textContent = `signal error: ${error.message}`;
  }
}

async function runBacktest() {
  try {
    ids.backtest.textContent = "Running backtest...";
    const payload = await postJson("/api/backtest", {
      csv_path: currentInputs().csv_path,
    });
    ids.backtest.textContent = pretty(payload);
  } catch (error) {
    ids.backtest.textContent = `backtest error: ${error.message}`;
  }
}

async function runOptimize() {
  try {
    ids.optimize.textContent = "Running optimizer...";
    const inputs = currentInputs();
    const payload = await postJson("/api/optimize", {
      csv_path: inputs.csv_path,
      top: inputs.top,
    });
    ids.optimize.textContent = pretty(payload);
  } catch (error) {
    ids.optimize.textContent = `optimize error: ${error.message}`;
  }
}

async function runScan() {
  try {
    ids.scan.textContent = "Running market scan...";
    const inputs = currentInputs();
    const payload = await postJson("/api/scan", {
      max_markets: inputs.max_markets,
      quote_currency: inputs.quote_currency,
    });
    ids.scan.textContent = pretty(payload);
  } catch (error) {
    ids.scan.textContent = `scan error: ${error.message}`;
  }
}

async function runReconcile() {
  try {
    ids.reconcile.textContent = "Running reconcile...";
    const inputs = currentInputs();
    const payload = await postJson("/api/reconcile", {
      state_path: inputs.state_path,
      mode: dashboardState.app.mode || "paper",
      market: dashboardState.app.market || undefined,
    });
    ids.reconcile.textContent = pretty(payload);
  } catch (error) {
    ids.reconcile.textContent = `reconcile error: ${error.message}`;
  }
}

async function runSyncCandles() {
  try {
    ids.paths.textContent = "Syncing candles...";
    const inputs = currentInputs();
    const payload = await postJson("/api/sync-candles", {
      csv_path: inputs.csv_path,
      count: inputs.sync_count,
      market: dashboardState.app.market || undefined,
    });
    ids.paths.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.paths.textContent = `sync error: ${error.message}`;
  }
}

async function saveConfig() {
  try {
    ids.config.textContent = "Saving config...";
    const payload = await postJson("/api/config-save", {
      "strategy.buy_threshold": Number(ids.cfgBuyThreshold.value || "0"),
      "strategy.sell_threshold": Number(ids.cfgSellThreshold.value || "0"),
      "strategy.min_adx": Number(ids.cfgMinAdx.value || "0"),
      "strategy.min_bollinger_width_fraction": Number(ids.cfgMinBbWidth.value || "0"),
      "strategy.volume_spike_multiplier": Number(ids.cfgVolumeSpike.value || "0"),
      "runtime.poll_seconds": Number(ids.cfgPollSeconds.value || "0"),
      "selector.max_markets": Number(ids.cfgSelectorMaxMarkets.value || "0"),
    });
    ids.config.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.config.textContent = `config error: ${error.message}`;
  }
}

function resetAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  const seconds = Number(ids.refreshSeconds.value || "0");
  if (seconds > 0) {
    refreshTimer = setInterval(refreshDashboard, seconds * 1000);
  }
}

document.getElementById("refresh-dashboard").addEventListener("click", refreshDashboard);
document.getElementById("run-signal").addEventListener("click", runSignal);
document.getElementById("run-backtest").addEventListener("click", runBacktest);
document.getElementById("run-optimize").addEventListener("click", runOptimize);
document.getElementById("run-scan").addEventListener("click", runScan);
document.getElementById("run-reconcile").addEventListener("click", runReconcile);
document.getElementById("run-sync-candles").addEventListener("click", runSyncCandles);
document.getElementById("save-config").addEventListener("click", saveConfig);
ids.refreshSeconds.addEventListener("change", resetAutoRefresh);

refreshDashboard();
resetAutoRefresh();
