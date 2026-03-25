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
  report: document.getElementById("report-json"),
  doctor: document.getElementById("doctor-json"),
  config: document.getElementById("config-json"),
  presets: document.getElementById("presets-json"),
  profiles: document.getElementById("profiles-json"),
  jobs: document.getElementById("jobs-json"),
  jobHealth: document.getElementById("job-health-json"),
  jobHealthSummary: document.getElementById("job-health-summary"),
  jobPreview: document.getElementById("job-preview-json"),
  logs: document.getElementById("logs-json"),
  jobHistory: document.getElementById("job-history-json"),
  paths: document.getElementById("paths-json"),
  readiness: document.getElementById("readiness-json"),
  alertsSummary: document.getElementById("alerts-summary"),
  alertsFeed: document.getElementById("alerts-feed"),
  recentTrades: document.getElementById("recent-trades-json"),
  recentEvents: document.getElementById("recent-events-json"),
  selectorSummary: document.getElementById("selector-summary-json"),
  selectorCards: document.getElementById("selector-cards"),
  chart: document.getElementById("price-chart"),
  chartMeta: document.getElementById("chart-meta"),
  selectorActiveChart: document.getElementById("selector-active-chart"),
  selectorActiveChartMeta: document.getElementById("selector-active-chart-meta"),
  selectorActiveSummary: document.getElementById("selector-active-summary-json"),
  selectorActiveEvents: document.getElementById("selector-active-events-json"),
  csvPath: document.getElementById("csv-path-input"),
  statePath: document.getElementById("state-path-input"),
  selectorStatePath: document.getElementById("selector-state-path-input"),
  marketFocus: document.getElementById("market-focus-input"),
  refreshSeconds: document.getElementById("refresh-seconds"),
  optimizeTop: document.getElementById("optimize-top-input"),
  scanMaxMarkets: document.getElementById("scan-max-markets-input"),
  quoteCurrency: document.getElementById("quote-currency-input"),
  syncCount: document.getElementById("sync-count-input"),
  reconcileEvery: document.getElementById("reconcile-every-input"),
  scanCards: document.getElementById("scan-cards"),
  cfgBuyThreshold: document.getElementById("cfg-buy-threshold"),
  cfgSellThreshold: document.getElementById("cfg-sell-threshold"),
  cfgMinAdx: document.getElementById("cfg-min-adx"),
  cfgMinBbWidth: document.getElementById("cfg-min-bb-width"),
  cfgVolumeSpike: document.getElementById("cfg-volume-spike"),
  cfgPollSeconds: document.getElementById("cfg-poll-seconds"),
  cfgSelectorMaxMarkets: document.getElementById("cfg-selector-max-markets"),
  presetName: document.getElementById("preset-name-input"),
  presetSelect: document.getElementById("preset-select"),
  reportSelect: document.getElementById("report-select"),
  profileName: document.getElementById("profile-name-input"),
  profileSelect: document.getElementById("profile-select"),
  jobType: document.getElementById("job-type-select"),
  jobAutoRestart: document.getElementById("job-auto-restart-select"),
  jobMaxRestarts: document.getElementById("job-max-restarts-input"),
  jobRestartBackoff: document.getElementById("job-restart-backoff-input"),
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

function escapeXml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&apos;");
}

function setMetric(element, value) {
  element.textContent = value ?? "-";
}

function currentInputs() {
  return {
    csv_path: ids.csvPath.value.trim(),
    state_path: ids.statePath.value.trim(),
    selector_state_path: ids.selectorStatePath.value.trim(),
    market: ids.marketFocus.value.trim(),
    top: Number(ids.optimizeTop.value || "5"),
    max_markets: Number(ids.scanMaxMarkets.value || "10"),
    quote_currency: ids.quoteCurrency.value.trim() || "KRW",
    sync_count: Number(ids.syncCount.value || "200"),
    reconcile_every: Number(ids.reconcileEvery.value || "10"),
  };
}

function currentJobSettings() {
  return {
    job_type: ids.jobType.value,
    auto_restart: ids.jobAutoRestart.value === "true",
    max_restarts: Number(ids.jobMaxRestarts.value || "0"),
    restart_backoff_seconds: Number(ids.jobRestartBackoff.value || "0"),
  };
}

function renderJobs(jobs) {
  ids.jobs.textContent = pretty(jobs || []);
  const tails = (jobs || [])
    .map((job) => {
      const heartbeat = job.heartbeat || null;
      const heartbeatLine = job.heartbeat_status
        ? `heartbeat: ${job.heartbeat_status}${job.heartbeat_age_seconds !== null && job.heartbeat_age_seconds !== undefined ? ` age=${Number(job.heartbeat_age_seconds).toFixed(1)}s` : ""}${heartbeat?.phase ? ` phase=${heartbeat.phase}` : ""}`
        : "";
      const report = job.last_report || null;
      const reportLine = report?.json_path
        ? `report: ${report.json_path}`
        : report?.error
          ? `report error: ${report.error}`
          : "";
      return [`# ${job.name}`, heartbeatLine, reportLine, job.log_tail || ""].filter(Boolean).join("\n").trim();
    })
    .filter(Boolean)
    .join("\n\n");
  ids.logs.textContent = tails || "No active job logs";
}

function renderJobHistory(historyPayload) {
  ids.jobHistory.textContent = pretty(historyPayload?.items || []);
}

function renderJobHealth(jobHealthPayload) {
  const summary = jobHealthPayload?.summary || {};
  ids.jobHealthSummary.innerHTML = `
    <span class="alert-pill success">healthy ${Number(summary.healthy || 0)}</span>
    <span class="alert-pill warn">stale ${Number(summary.stale || 0)}</span>
    <span class="alert-pill warn">missing ${Number(summary.missing || 0)}</span>
    <span class="alert-pill error">failed ${Number(summary.failed || 0)}</span>
    <span class="alert-pill info">running ${Number(summary.running || 0)}</span>
    <span class="alert-pill info">auto restart ${Number(summary.auto_restart || 0)}</span>
    <span class="alert-pill danger">attention ${Number(summary.requires_attention || 0)}</span>
  `;
  ids.jobHealth.textContent = pretty(jobHealthPayload || { summary: {}, items: [] });
}

function renderAlerts(alertPayload) {
  const summary = alertPayload?.summary || {};
  const items = alertPayload?.items || [];
  ids.alertsSummary.innerHTML = `
    <span class="alert-pill danger">attention ${Number(summary.requires_attention || 0)}</span>
    <span class="alert-pill warn">warning ${Number(summary.warning || 0)}</span>
    <span class="alert-pill error">error ${Number(summary.error || 0)}</span>
    <span class="alert-pill success">success ${Number(summary.success || 0)}</span>
    <span class="alert-pill info">info ${Number(summary.info || 0)}</span>
  `;

  if (!items.length) {
    ids.alertsFeed.innerHTML = '<div class="empty-state">No recent alerts.</div>';
    return;
  }

  ids.alertsFeed.innerHTML = items.map((item) => `
    <article class="alert-card ${escapeXml(item.level || "info")}">
      <div class="alert-card-head">
        <span class="chip ${escapeXml(item.level || "info")}">${escapeXml(item.level || "info")}</span>
        <span class="alert-source">${escapeXml(item.source || "runtime")}${item.market ? ` • ${escapeXml(item.market)}` : ""}</span>
      </div>
      <h3>${escapeXml(item.headline || "Alert")}</h3>
      <p>${escapeXml(item.message || "")}</p>
      <div class="alert-meta">${escapeXml(item.timestamp || "timestamp unavailable")}</div>
    </article>
  `).join("");
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
  if (!ids.selectorStatePath.value && payload.paths?.selector_state_path) {
    ids.selectorStatePath.value = payload.paths.selector_state_path;
  }
  if (!ids.marketFocus.value && payload.app?.market) {
    ids.marketFocus.value = payload.app.market;
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
  if (!ids.reconcileEvery.value && payload.ui_defaults?.reconcile_every) {
    ids.reconcileEvery.value = payload.ui_defaults.reconcile_every;
  }
  if (!ids.jobType.value && payload.ui_defaults?.job_type) {
    ids.jobType.value = payload.ui_defaults.job_type;
  }
  if (!ids.jobAutoRestart.value && payload.ui_defaults) {
    ids.jobAutoRestart.value = String(Boolean(payload.ui_defaults.auto_restart));
  }
  if (!ids.jobMaxRestarts.value && payload.ui_defaults?.max_restarts !== undefined) {
    ids.jobMaxRestarts.value = payload.ui_defaults.max_restarts;
  }
  if (!ids.jobRestartBackoff.value && payload.ui_defaults?.restart_backoff_seconds !== undefined) {
    ids.jobRestartBackoff.value = payload.ui_defaults.restart_backoff_seconds;
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

function defaultCsvPathForMarket(market) {
  if (!market) {
    return "";
  }
  const candleUnit = Number(dashboardState.app.candle_unit || 15);
  return `data/${String(market).toLowerCase().replaceAll("-", "_")}_${candleUnit}m.csv`;
}

function setFocusMarket(market, statusElement, statusPrefix) {
  if (!market) {
    return;
  }
  ids.marketFocus.value = market;
  const currentCsvPath = ids.csvPath.value.trim();
  const previousFocus = dashboardState.app.market || "";
  const previousDefault = defaultCsvPathForMarket(previousFocus);
  const nextDefault = defaultCsvPathForMarket(market);
  if (!currentCsvPath || currentCsvPath === previousDefault) {
    ids.csvPath.value = nextDefault;
  }
  statusElement.textContent = `${statusPrefix} ${market}`;
}

function defaultPresetName(suffix) {
  const market = (ids.marketFocus.value.trim() || dashboardState.app.market || "market")
    .toLowerCase()
    .replaceAll("-", "_");
  return `${market}-${suffix}`;
}

function resolvePresetName(suffix) {
  const current = ids.presetName.value.trim();
  if (current) {
    return current;
  }
  const generated = defaultPresetName(suffix);
  ids.presetName.value = generated;
  return generated;
}

function resolveProfileName(suffix) {
  const current = ids.profileName.value.trim();
  if (current) {
    return current;
  }
  const generated = defaultPresetName(suffix);
  ids.profileName.value = generated;
  return generated;
}

function formatCompactNumber(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return "-";
  }
  if (Math.abs(numeric) >= 1000) {
    return new Intl.NumberFormat("en-US", {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(numeric);
  }
  return numeric.toFixed(2);
}

function renderMarketCards(target, results, emptyMessage, options = {}) {
  if (!results.length) {
    target.innerHTML = `<div class="empty-state">${escapeXml(emptyMessage)}</div>`;
    return;
  }

  const activeMarket = options.activeMarket || "";
  const buttonLabel = options.buttonLabel || "Use Market";

  target.innerHTML = results.map((item, index) => {
    const action = String(item.action || "HOLD").toLowerCase();
    const normalizedReasons = (item.reasons || []).slice(0, 4).map((value) => escapeXml(value)).join(" | ");
    const reasons = (item.reasons || []).slice(0, 4).map((value) => escapeXml(value)).join(" · ");
    const warningChip = item.market_warning && item.market_warning !== "NONE"
      ? `<span class="chip warn">warning ${escapeXml(item.market_warning)}</span>`
      : '<span class="chip good">warning clear</span>';
    const liquidityChip = item.liquidity_ok
      ? '<span class="chip good">liquidity ok</span>'
      : '<span class="chip warn">liquidity low</span>';
    const activeChip = item.market === activeMarket
      ? '<span class="chip active">active</span>'
      : "";
    return `
      <article class="scan-card">
        <div class="scan-card-head">
          <div>
            <p class="scan-rank">Rank #${index + 1}</p>
            <h3>${escapeXml(item.market)}</h3>
          </div>
          <span class="scan-badge ${action}">${escapeXml(item.action || "HOLD")}</span>
        </div>
        <div class="scan-meta">
          <span>${escapeXml(item.timestamp || "-")}</span>
          <span>confidence ${Number(item.confidence || 0).toFixed(2)}</span>
        </div>
        <div class="scan-metrics">
          <div class="scan-metric">
            <span class="scan-metric-label">Score</span>
            <strong class="scan-metric-value">${Number(item.score || 0).toFixed(1)}</strong>
          </div>
          <div class="scan-metric">
            <span class="scan-metric-label">Close</span>
            <strong class="scan-metric-value">${formatCompactNumber(item.close)}</strong>
          </div>
          <div class="scan-metric">
            <span class="scan-metric-label">24H Liquidity</span>
            <strong class="scan-metric-value">${formatCompactNumber(item.liquidity_24h)}</strong>
          </div>
          <div class="scan-metric">
            <span class="scan-metric-label">Signal Count</span>
            <strong class="scan-metric-value">${(item.reasons || []).length}</strong>
          </div>
        </div>
        <div class="chip-row">
          ${liquidityChip}
          ${warningChip}
          ${activeChip}
        </div>
        <p class="scan-reasons">${normalizedReasons || "No reasons provided."}</p>
        <div class="scan-actions">
          <button class="ghost-button small scan-use-button" data-market="${escapeXml(item.market)}">${escapeXml(buttonLabel)}</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderScanCards(scanPayload) {
  renderMarketCards(
    ids.scanCards,
    scanPayload?.scan_results || [],
    "Run a scan to load ranked markets.",
  );
}

function renderSelectorCards(selectorPayload) {
  renderMarketCards(
    ids.selectorCards,
    selectorPayload?.last_scan_results || [],
    "Selector state not loaded yet.",
    {
      activeMarket: selectorPayload?.active_market || "",
      buttonLabel: "Focus Market",
    },
  );
}

function renderPresets(presetPayload) {
  const items = presetPayload?.items || [];
  ids.presets.textContent = pretty(presetPayload || { dir: "", items: [] });

  const currentValue = ids.presetSelect.value;
  if (!items.length) {
    ids.presetSelect.innerHTML = '<option value="">No presets</option>';
    return;
  }

  ids.presetSelect.innerHTML = items
    .map((item) => `<option value="${escapeXml(item.path)}">${escapeXml(item.name)}</option>`)
    .join("");

  const nextValue = items.some((item) => item.path === currentValue)
    ? currentValue
    : items[0].path;
  ids.presetSelect.value = nextValue;
}

function renderProfiles(profilePayload) {
  const items = profilePayload?.items || [];
  ids.profiles.textContent = pretty(profilePayload || { dir: "", items: [] });

  const currentValue = ids.profileSelect.value;
  if (!items.length) {
    ids.profileSelect.innerHTML = '<option value="">No profiles</option>';
    return;
  }

  ids.profileSelect.innerHTML = items
    .map((item) => `<option value="${escapeXml(item.path)}">${escapeXml(item.name)}</option>`)
    .join("");

  const nextValue = items.some((item) => item.path === currentValue)
    ? currentValue
    : items[0].path;
  ids.profileSelect.value = nextValue;
}

function renderReports(reportPayload) {
  const items = reportPayload?.items || [];
  const currentValue = ids.reportSelect.value;
  if (!items.length) {
    ids.reportSelect.innerHTML = '<option value="">No reports</option>';
    return;
  }

  ids.reportSelect.innerHTML = items
    .map((item) => {
      const label = `${item.market || "market"} | ${item.mode || "paper"} | trades ${item.trade_count} | pnl ${Number(item.total_net_pnl || 0).toFixed(2)}`;
      return `<option value="${escapeXml(item.json_path)}">${escapeXml(label)}</option>`;
    })
    .join("");

  const nextValue = items.some((item) => item.json_path === currentValue)
    ? currentValue
    : items[0].json_path;
  ids.reportSelect.value = nextValue;
}

function applyProfileToForm(profilePayload) {
  if (!profilePayload) {
    return;
  }
  ids.jobType.value = profilePayload.job_type || ids.jobType.value;
  ids.marketFocus.value = profilePayload.market || ids.marketFocus.value;
  ids.csvPath.value = profilePayload.csv_path || ids.csvPath.value;
  ids.statePath.value = profilePayload.state_path || ids.statePath.value;
  ids.selectorStatePath.value = profilePayload.selector_state_path || ids.selectorStatePath.value;
  ids.quoteCurrency.value = profilePayload.quote_currency || ids.quoteCurrency.value;
  ids.scanMaxMarkets.value = profilePayload.max_markets || ids.scanMaxMarkets.value;
  ids.reconcileEvery.value = profilePayload.reconcile_every || ids.reconcileEvery.value;
  ids.cfgPollSeconds.value = profilePayload.poll_seconds || ids.cfgPollSeconds.value;
  ids.jobAutoRestart.value = String(Boolean(profilePayload.auto_restart));
  ids.jobMaxRestarts.value = profilePayload.max_restarts || 0;
  ids.jobRestartBackoff.value = profilePayload.restart_backoff_seconds || 0;
  if (profilePayload.preset) {
    ids.presetSelect.value = profilePayload.preset;
  }
}

function renderChart(chartElement, metaElement, chartPayload) {
  if (!chartPayload || !chartPayload.points || chartPayload.points.length === 0) {
    chartElement.innerHTML = "";
    metaElement.textContent = "No chart data";
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
  const timestampIndex = new Map(coords.map((point) => [point.timestamp, point]));
  const markerOffsets = {};
  const markers = (chartPayload.markers || [])
    .map((marker) => {
      const point = timestampIndex.get(marker.timestamp);
      if (!point) {
        return "";
      }

      const offsetKey = `${marker.timestamp}:${marker.kind}`;
      const stackIndex = markerOffsets[offsetKey] || 0;
      markerOffsets[offsetKey] = stackIndex + 1;
      const markerY = height - padding - (((marker.price - min) / range) * (height - (padding * 2))) - (stackIndex * 18);
      const markerX = point.x;
      let fill = "#d18a1f";
      if (marker.side === "buy") {
        fill = marker.kind === "open_position" ? "#c9892a" : "#0f9b62";
      } else if (marker.side === "sell") {
        fill = "#b2392e";
      }
      const label = escapeXml(marker.label || "?");
      const title = escapeXml(
        `${marker.timestamp} ${marker.kind} price=${Number(marker.price || 0).toFixed(2)}`
        + (marker.note ? ` ${marker.note}` : "")
        + (marker.net_pnl !== undefined ? ` pnl=${Number(marker.net_pnl).toFixed(2)}` : ""),
      );
      return `
        <g class="chart-marker">
          <line x1="${markerX}" y1="${markerY + 8}" x2="${markerX}" y2="${height - padding}" stroke="${fill}" stroke-width="1.5" stroke-dasharray="3 3" opacity="0.65"></line>
          <circle cx="${markerX}" cy="${markerY}" r="8" fill="${fill}" stroke="#fff8ec" stroke-width="2">
            <title>${title}</title>
          </circle>
          <text x="${markerX}" y="${markerY + 3}" text-anchor="middle" font-size="9" font-weight="700" fill="#fff8ec">${label}</text>
        </g>
      `;
    })
    .filter(Boolean)
    .join("");

  const linePath = coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${height - padding} L ${coords[0].x} ${height - padding} Z`;
  const latest = coords[coords.length - 1];
  const gradientId = `${chartElement.id}-price-fill`;

  chartElement.innerHTML = `
    <defs>
      <linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="rgba(199, 92, 42, 0.34)"></stop>
        <stop offset="100%" stop-color="rgba(199, 92, 42, 0.02)"></stop>
      </linearGradient>
    </defs>
    <path d="${areaPath}" fill="url(#${gradientId})"></path>
    <path d="${linePath}" fill="none" stroke="#c75c2a" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
    ${markers}
    <circle cx="${latest.x}" cy="${latest.y}" r="6" fill="#8d2f1b"></circle>
  `;
  metaElement.textContent = `Last ${chartPayload.points.length} candles | markers ${(chartPayload.markers || []).length} | low ${min.toFixed(2)} | high ${max.toFixed(2)} | latest ${latest.close.toFixed(2)} @ ${latest.timestamp}`;
}

function renderPriceChart(chartPayload) {
  renderChart(ids.chart, ids.chartMeta, chartPayload);
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
    const inputs = currentInputs();
    const query = new URLSearchParams({
      state_path: inputs.state_path,
      selector_state_path: inputs.selector_state_path,
      csv_path: inputs.csv_path,
      focus_market: inputs.market,
    });
    const payload = await getJson(`/api/dashboard?${query.toString()}`);
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
      renderAlerts(payload.alerts || null);
      renderJobHealth(payload.job_health || null);
      ids.recentTrades.textContent = pretty(payload.activity?.recent_trades || []);
      ids.recentEvents.textContent = pretty(payload.activity?.recent_events || []);
    ids.selectorSummary.textContent = pretty(payload.selector_summary || {});
    ids.selectorActiveSummary.textContent = pretty(payload.selector_summary?.active_market_summary || {});
    ids.selectorActiveEvents.textContent = pretty(payload.selector_summary?.active_market_activity?.recent_events || []);
    renderSelectorCards(payload.selector_summary || null);
    renderPresets(payload.strategy_presets || null);
    renderProfiles(payload.operator_profiles || null);
    renderReports(payload.session_reports || null);
    renderChart(ids.selectorActiveChart, ids.selectorActiveChartMeta, payload.selector_summary?.active_market_chart);
    renderJobs(payload.jobs);
    renderJobHistory(payload.job_history);
    renderPriceChart(payload.chart);
  } catch (error) {
    ids.summary.textContent = `dashboard error: ${error.message}`;
  }
}

async function runSignal() {
  try {
    ids.signal.textContent = "Running signal...";
    const inputs = currentInputs();
    const payload = await postJson("/api/signal", {
      csv_path: inputs.csv_path,
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.signal.textContent = pretty(payload);
  } catch (error) {
    ids.signal.textContent = `signal error: ${error.message}`;
  }
}

async function runBacktest() {
  try {
    ids.backtest.textContent = "Running backtest...";
    const inputs = currentInputs();
    const payload = await postJson("/api/backtest", {
      csv_path: inputs.csv_path,
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.backtest.textContent = pretty(payload);
  } catch (error) {
    ids.backtest.textContent = `backtest error: ${error.message}`;
  }
}

async function runOptimize(saveBest = false) {
  try {
    ids.optimize.textContent = saveBest ? "Running optimizer and saving preset..." : "Running optimizer...";
    const inputs = currentInputs();
    const payload = await postJson("/api/optimize", {
      csv_path: inputs.csv_path,
      top: inputs.top,
      market: inputs.market || dashboardState.app.market || undefined,
      save_best_preset_name: saveBest ? resolvePresetName("best") : undefined,
    });
    ids.optimize.textContent = pretty(payload);
    if (payload.saved_preset) {
      ids.presets.textContent = pretty(payload.saved_preset);
      await refreshDashboard();
    }
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
    renderScanCards(payload);
  } catch (error) {
    ids.scan.textContent = `scan error: ${error.message}`;
    renderScanCards(null);
  }
}

async function runReconcile() {
  try {
    ids.reconcile.textContent = "Running reconcile...";
    const inputs = currentInputs();
    const payload = await postJson("/api/reconcile", {
      state_path: inputs.state_path,
      mode: dashboardState.app.mode || "paper",
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.reconcile.textContent = pretty(payload);
  } catch (error) {
    ids.reconcile.textContent = `reconcile error: ${error.message}`;
  }
}

async function runDoctor() {
  try {
    ids.doctor.textContent = "Running doctor...";
    const inputs = currentInputs();
    const payload = await postJson("/api/doctor", {
      state_path: inputs.state_path,
      selector_state_path: inputs.selector_state_path,
    });
    ids.doctor.textContent = pretty(payload);
  } catch (error) {
    ids.doctor.textContent = `doctor error: ${error.message}`;
  }
}

async function runSyncCandles() {
  try {
    ids.paths.textContent = "Syncing candles...";
    const inputs = currentInputs();
    const payload = await postJson("/api/sync-candles", {
      csv_path: inputs.csv_path,
      count: inputs.sync_count,
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.paths.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.paths.textContent = `sync error: ${error.message}`;
  }
}

async function runSessionReport() {
  try {
    ids.report.textContent = "Exporting session report...";
    const inputs = currentInputs();
    const payload = await postJson("/api/session-report", {
      state_path: inputs.state_path,
      mode: dashboardState.app.mode || "paper",
      label: (inputs.market || dashboardState.app.market || "session").toLowerCase(),
    });
    ids.report.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.report.textContent = `report error: ${error.message}`;
  }
}

async function loadSessionReport() {
  try {
    const report = ids.reportSelect.value;
    if (!report) {
      ids.report.textContent = "report load error: select a report first";
      return;
    }
    ids.report.textContent = "Loading session report...";
    const payload = await postJson("/api/report-show", { report });
    ids.report.textContent = pretty(payload);
  } catch (error) {
    ids.report.textContent = `report load error: ${error.message}`;
  }
}

async function refreshJobs() {
  try {
    const payload = await getJson("/api/jobs");
    renderJobs(payload.jobs);
    renderJobHealth(payload.job_health || null);
    renderJobHistory({ items: payload.history || [] });
  } catch (error) {
    ids.jobs.textContent = `jobs error: ${error.message}`;
  }
}

async function startJob(jobType) {
  try {
    ids.jobs.textContent = `Starting ${jobType}...`;
    const inputs = currentInputs();
    const jobSettings = currentJobSettings();
    const payload = await postJson("/api/jobs-start", {
      job_type: jobType,
      state_path: inputs.state_path,
      selector_state_path: inputs.selector_state_path,
      csv_path: inputs.csv_path,
      market: inputs.market || dashboardState.app.market || undefined,
      max_markets: inputs.max_markets,
      quote_currency: inputs.quote_currency,
      poll_seconds: Number(ids.cfgPollSeconds.value || dashboardState.app.poll_seconds || "10"),
      reconcile_every: inputs.reconcile_every,
      reconcile_every_loops: 3,
      auto_restart: jobSettings.auto_restart,
      max_restarts: jobSettings.max_restarts,
      restart_backoff_seconds: jobSettings.restart_backoff_seconds,
    });
    ids.jobs.textContent = pretty(payload);
    if (payload?.error) {
      return;
    }
    await refreshJobs();
  } catch (error) {
    ids.jobs.textContent = `start job error: ${error.message}`;
  }
}

async function previewJob(jobType = ids.jobType.value) {
  try {
    ids.jobPreview.textContent = `Previewing ${jobType}...`;
    const inputs = currentInputs();
    const jobSettings = currentJobSettings();
    const payload = await postJson("/api/jobs-preview", {
      job_type: jobType,
      state_path: inputs.state_path,
      selector_state_path: inputs.selector_state_path,
      csv_path: inputs.csv_path,
      market: inputs.market || dashboardState.app.market || undefined,
      max_markets: inputs.max_markets,
      quote_currency: inputs.quote_currency,
      poll_seconds: Number(ids.cfgPollSeconds.value || dashboardState.app.poll_seconds || "10"),
      reconcile_every: inputs.reconcile_every,
      reconcile_every_loops: 3,
      auto_restart: jobSettings.auto_restart,
      max_restarts: jobSettings.max_restarts,
      restart_backoff_seconds: jobSettings.restart_backoff_seconds,
    });
    ids.jobPreview.textContent = pretty(payload);
  } catch (error) {
    ids.jobPreview.textContent = `preview error: ${error.message}`;
  }
}

async function stopJob(jobName) {
  try {
    ids.jobs.textContent = `Stopping ${jobName}...`;
    const payload = await postJson("/api/jobs-stop", { job_name: jobName });
    ids.jobs.textContent = pretty(payload);
    await refreshJobs();
  } catch (error) {
    ids.jobs.textContent = `stop job error: ${error.message}`;
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

async function saveCurrentPreset() {
  try {
    ids.presets.textContent = "Saving current preset...";
    const inputs = currentInputs();
    const payload = await postJson("/api/preset-save-current", {
      preset_name: resolvePresetName("current"),
      csv_path: inputs.csv_path,
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.presets.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.presets.textContent = `preset save error: ${error.message}`;
  }
}

async function applyPreset() {
  try {
    const preset = ids.presetSelect.value;
    if (!preset) {
      ids.presets.textContent = "preset apply error: select a preset first";
      return;
    }
    ids.presets.textContent = "Applying preset...";
    const payload = await postJson("/api/preset-apply", { preset });
    ids.presets.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.presets.textContent = `preset apply error: ${error.message}`;
  }
}

async function saveProfile() {
  try {
    ids.profiles.textContent = "Saving profile...";
    const inputs = currentInputs();
    const jobSettings = currentJobSettings();
    const payload = await postJson("/api/profile-save", {
      profile_name: resolveProfileName("profile"),
      profile: {
        job_type: jobSettings.job_type,
        market: inputs.market || dashboardState.app.market || "",
        csv_path: inputs.csv_path,
        state_path: inputs.state_path,
        selector_state_path: inputs.selector_state_path,
        quote_currency: inputs.quote_currency,
        max_markets: inputs.max_markets,
        poll_seconds: Number(ids.cfgPollSeconds.value || dashboardState.app.poll_seconds || "10"),
        reconcile_every: inputs.reconcile_every,
        reconcile_every_loops: 3,
        preset: ids.presetSelect.value || "",
        auto_restart: jobSettings.auto_restart,
        max_restarts: jobSettings.max_restarts,
        restart_backoff_seconds: jobSettings.restart_backoff_seconds,
      },
    });
    ids.profiles.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.profiles.textContent = `profile save error: ${error.message}`;
  }
}

async function loadProfile() {
  try {
    const profile = ids.profileSelect.value;
    if (!profile) {
      ids.profiles.textContent = "profile load error: select a profile first";
      return;
    }
    ids.profiles.textContent = "Loading profile...";
    const payload = await postJson("/api/profile-load", { profile });
    ids.profiles.textContent = pretty(payload);
    applyProfileToForm(payload.profile);
    await refreshDashboard();
  } catch (error) {
    ids.profiles.textContent = `profile load error: ${error.message}`;
  }
}

async function previewProfile() {
  try {
    const profile = ids.profileSelect.value;
    if (!profile) {
      ids.profiles.textContent = "profile preview error: select a profile first";
      return;
    }
    ids.jobPreview.textContent = "Previewing profile...";
    const payload = await postJson("/api/profile-preview", { profile });
    ids.jobPreview.textContent = pretty(payload);
    if (payload.profile?.profile) {
      applyProfileToForm(payload.profile.profile);
    }
  } catch (error) {
    ids.jobPreview.textContent = `profile preview error: ${error.message}`;
  }
}

async function startProfile() {
  try {
    const profile = ids.profileSelect.value;
    if (!profile) {
      ids.profiles.textContent = "profile start error: select a profile first";
      return;
    }
    ids.jobs.textContent = "Starting profile...";
    const payload = await postJson("/api/profile-start", { profile });
    ids.jobs.textContent = pretty(payload);
    if (payload.profile?.profile) {
      applyProfileToForm(payload.profile.profile);
    }
    if (payload?.error) {
      return;
    }
    await refreshJobs();
    await refreshDashboard();
  } catch (error) {
    ids.jobs.textContent = `profile start error: ${error.message}`;
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
document.getElementById("run-optimize").addEventListener("click", () => runOptimize(false));
document.getElementById("run-scan").addEventListener("click", runScan);
document.getElementById("run-reconcile").addEventListener("click", runReconcile);
document.getElementById("run-doctor").addEventListener("click", runDoctor);
document.getElementById("run-sync-candles").addEventListener("click", runSyncCandles);
document.getElementById("run-session-report").addEventListener("click", runSessionReport);
document.getElementById("load-session-report").addEventListener("click", loadSessionReport);
document.getElementById("save-config").addEventListener("click", saveConfig);
document.getElementById("save-current-preset").addEventListener("click", saveCurrentPreset);
document.getElementById("save-best-preset").addEventListener("click", () => runOptimize(true));
document.getElementById("apply-preset").addEventListener("click", applyPreset);
document.getElementById("save-profile").addEventListener("click", saveProfile);
document.getElementById("load-profile").addEventListener("click", loadProfile);
document.getElementById("preview-profile").addEventListener("click", previewProfile);
document.getElementById("start-profile").addEventListener("click", startProfile);
document.getElementById("refresh-jobs").addEventListener("click", refreshJobs);
document.getElementById("preview-job").addEventListener("click", () => previewJob());
ids.scanCards.addEventListener("click", (event) => {
  const button = event.target.closest("[data-market]");
  if (!button) {
    return;
  }
  setFocusMarket(button.dataset.market || "", ids.scan, "focus market set to");
  refreshDashboard();
});
ids.selectorCards.addEventListener("click", (event) => {
  const button = event.target.closest("[data-market]");
  if (!button) {
    return;
  }
  setFocusMarket(button.dataset.market || "", ids.selectorSummary, "focus market set to");
  refreshDashboard();
});
document.getElementById("start-paper-loop").addEventListener("click", () => startJob("paper-loop"));
document.getElementById("stop-paper-loop").addEventListener("click", () => stopJob("paper-loop"));
document.getElementById("start-paper-selector").addEventListener("click", () => startJob("paper-selector"));
document.getElementById("stop-paper-selector").addEventListener("click", () => stopJob("paper-selector"));
document.getElementById("start-live-daemon").addEventListener("click", () => startJob("live-daemon"));
document.getElementById("stop-live-daemon").addEventListener("click", () => stopJob("live-daemon"));
document.getElementById("start-live-supervisor").addEventListener("click", () => startJob("live-supervisor"));
document.getElementById("stop-live-supervisor").addEventListener("click", () => stopJob("live-supervisor"));
ids.refreshSeconds.addEventListener("change", resetAutoRefresh);

renderScanCards(null);
renderSelectorCards(null);
renderPresets(null);
renderProfiles(null);
renderChart(ids.selectorActiveChart, ids.selectorActiveChartMeta, null);
refreshDashboard();
resetAutoRefresh();
