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
  paths: document.getElementById("paths-json"),
  readiness: document.getElementById("readiness-json"),
};

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function setMetric(element, value) {
  element.textContent = value ?? "-";
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

async function refreshDashboard() {
  try {
    const payload = await getJson("/api/dashboard");
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
  } catch (error) {
    ids.summary.textContent = `dashboard error: ${error.message}`;
  }
}

async function runSignal() {
  try {
    ids.signal.textContent = "계산 중...";
    const payload = await getJson("/api/signal", { method: "POST", body: JSON.stringify({}) });
    ids.signal.textContent = pretty(payload);
  } catch (error) {
    ids.signal.textContent = `signal error: ${error.message}`;
  }
}

async function runBacktest() {
  try {
    ids.backtest.textContent = "백테스트 실행 중...";
    const payload = await getJson("/api/backtest", { method: "POST", body: JSON.stringify({}) });
    ids.backtest.textContent = pretty(payload);
  } catch (error) {
    ids.backtest.textContent = `backtest error: ${error.message}`;
  }
}

async function runOptimize() {
  try {
    ids.optimize.textContent = "그리드 탐색 실행 중...";
    const payload = await getJson("/api/optimize", { method: "POST", body: JSON.stringify({ top: 5 }) });
    ids.optimize.textContent = pretty(payload);
  } catch (error) {
    ids.optimize.textContent = `optimize error: ${error.message}`;
  }
}

document.getElementById("refresh-dashboard").addEventListener("click", refreshDashboard);
document.getElementById("run-signal").addEventListener("click", runSignal);
document.getElementById("run-backtest").addEventListener("click", runBacktest);
document.getElementById("run-optimize").addEventListener("click", runOptimize);

refreshDashboard();
