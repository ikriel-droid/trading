const ids = {
  heroMarket: document.getElementById("hero-market-badge"),
  heroMode: document.getElementById("hero-mode-badge"),
  heroRelease: document.getElementById("hero-release-badge"),
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
  workflow: document.getElementById("workflow-json"),
  releaseArtifactsSummary: document.getElementById("release-artifacts-summary"),
  releaseNextStep: document.getElementById("release-next-step"),
  releaseArtifacts: document.getElementById("release-artifacts-json"),
  jobs: document.getElementById("jobs-json"),
  jobHealth: document.getElementById("job-health-json"),
  jobHealthSummary: document.getElementById("job-health-summary"),
  jobPreview: document.getElementById("job-preview-json"),
  logs: document.getElementById("logs-json"),
  jobHistory: document.getElementById("job-history-json"),
  paths: document.getElementById("paths-json"),
  readiness: document.getElementById("readiness-json"),
  checklistSummary: document.getElementById("checklist-summary"),
  checklistFeed: document.getElementById("checklist-feed"),
  alertsSummary: document.getElementById("alerts-summary"),
  alertsFeed: document.getElementById("alerts-feed"),
  liveControlSummary: document.getElementById("live-control-summary"),
  liveControlStatus: document.getElementById("live-control-status"),
  liveControlJson: document.getElementById("live-control-json"),
  liveTestKrw: document.getElementById("live-test-krw-input"),
  liveCfgBuyThreshold: document.getElementById("live-cfg-buy-threshold"),
  liveCfgSellThreshold: document.getElementById("live-cfg-sell-threshold"),
  liveCfgMaxPositionFraction: document.getElementById("live-cfg-max-position-fraction"),
  liveCfgMaxTradesPerDay: document.getElementById("live-cfg-max-trades-per-day"),
  liveCfgSelectorMaxMarkets: document.getElementById("live-cfg-selector-max-markets"),
  liveCfgIncludeMarkets: document.getElementById("live-cfg-include-markets"),
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
  reportKeep: document.getElementById("report-keep-input"),
  profileName: document.getElementById("profile-name-input"),
  profileNotes: document.getElementById("profile-notes-input"),
  profileSelect: document.getElementById("profile-select"),
  workflowStage: document.getElementById("workflow-stage-select"),
  jobType: document.getElementById("job-type-select"),
  jobAutoRestart: document.getElementById("job-auto-restart-select"),
  jobMaxRestarts: document.getElementById("job-max-restarts-input"),
  jobRestartBackoff: document.getElementById("job-restart-backoff-input"),
  jobReportKeep: document.getElementById("job-report-keep-input"),
  runReleaseRecommended: document.getElementById("run-release-recommended"),
  runReleasePack: document.getElementById("run-release-pack"),
  runReleaseVerify: document.getElementById("run-release-verify"),
  runReleaseClean: document.getElementById("run-release-clean"),
  enableLiveMode: document.getElementById("enable-live-mode"),
  disableLiveMode: document.getElementById("disable-live-mode"),
  runLiveEasyPrep: document.getElementById("run-live-easy-prep"),
  runLiveMarketTest: document.getElementById("run-live-market-test"),
  saveLiveConfig: document.getElementById("save-live-config"),
};

let dashboardState = {
  paths: {},
  app: {},
  defaults: {},
  releaseRecommendedStage: "release-pack",
};
let refreshTimer = null;

const MODE_LABELS = {
  paper: "모의투자",
  live: "실거래",
};

const RELEASE_LABELS = {
  missing: "배포 준비 필요",
  partial: "배포 검토 필요",
  invalid: "배포 파일 오류",
  ready: "배포 가능",
};

const STATUS_LABELS = {
  success: "정상",
  warning: "주의",
  error: "문제",
  info: "안내",
  ready: "준비 완료",
  paper_ready: "모의투자 준비",
  missing: "누락",
  stale: "지연",
  failed: "실패",
  invalid: "오류",
  running: "실행 중",
  stopped: "중지됨",
  retrying: "재시도 중",
  unknown: "확인 중",
};

const JOB_TYPE_LABELS = {
  "paper-loop": "모의투자 단일 감시",
  "paper-selector": "모의투자 자동 종목 선택",
  "live-selector": "실거래 자동 종목 선택",
  "live-daemon": "실거래 단일 감시",
  "live-supervisor": "실거래 상태 감시",
};

const ACTION_LABELS = {
  BUY: "매수",
  SELL: "매도",
  HOLD: "대기",
};

const WORKFLOW_STAGE_LABELS = {
  roadmap: "남은 작업 보기",
  verify: "기본 점검 실행",
  "paper-preflight": "모의투자 시작 전 점검",
  "paper-start": "모의투자 시작",
  "paper-report": "모의투자 리포트 저장",
  "live-preflight": "실거래 시작 전 점검",
  "live-start": "실거래 시작",
  status: "현재 상태 확인",
  "all-safe": "안전한 전체 점검",
  all: "전체 실행",
  "release-pack": "릴리스 팩 만들기",
  "release-verify": "릴리스 팩 검증",
  "release-clean": "릴리스 산출물 정리",
};

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

function setRibbonBadge(element, text, tone = "") {
  if (!element) {
    return;
  }
  element.textContent = text;
  element.className = `ribbon-pill${tone ? ` ${tone}` : ""}`;
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

function statusLabel(value) {
  const key = String(value || "").trim().toLowerCase();
  return STATUS_LABELS[key] || value || "-";
}

function modeLabel(value) {
  const key = String(value || "").trim().toLowerCase();
  return MODE_LABELS[key] || value || "-";
}

function releaseLabel(value) {
  const key = String(value || "").trim().toLowerCase();
  return RELEASE_LABELS[key] || statusLabel(value);
}

function jobTypeLabel(value) {
  const key = String(value || "").trim();
  return JOB_TYPE_LABELS[key] || value || "-";
}

function actionLabel(value) {
  const key = String(value || "").trim().toUpperCase();
  return ACTION_LABELS[key] || value || "-";
}

function workflowStageLabel(value) {
  const key = String(value || "").trim();
  return WORKFLOW_STAGE_LABELS[key] || key || "-";
}

function badgeTone(value) {
  const key = String(value || "").trim().toLowerCase();
  if (["success", "ready"].includes(key)) {
    return "success";
  }
  if (["warning", "stale", "missing", "partial"].includes(key)) {
    return "warning";
  }
  if (["error", "failed", "invalid"].includes(key)) {
    return "error";
  }
  return "info";
}

function formatCurrency(value, maximumFractionDigits = 0) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "-";
  }
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits,
  }).format(numeric);
}

function formatNumber(value, maximumFractionDigits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "-";
  }
  return new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits,
  }).format(numeric);
}

function compactTimestamp(value) {
  if (!value) {
    return "시간 정보 없음";
  }
  return String(value).replace("T", " ").replace("Z", "");
}

function factCard(label, value, tone = "") {
  return `
    <div class="fact-card">
      <span class="fact-label">${escapeXml(label)}</span>
      <strong class="fact-value${tone ? ` ${tone}` : ""}">${escapeXml(value)}</strong>
    </div>
  `;
}

function buildFactGrid(items) {
  return `<div class="fact-grid">${items.join("")}</div>`;
}

function currentJobSettings() {
  return {
    job_type: ids.jobType.value,
    auto_restart: ids.jobAutoRestart.value === "true",
    max_restarts: Number(ids.jobMaxRestarts.value || "0"),
    restart_backoff_seconds: Number(ids.jobRestartBackoff.value || "0"),
    report_keep_latest: Number(ids.jobReportKeep.value || String(dashboardState.defaults.report_keep_latest || 20)),
  };
}

function isLiveJobType(jobType) {
  return jobType === "live-selector" || jobType === "live-daemon" || jobType === "live-supervisor";
}

function formatBlockingIssues(items) {
  return (items || []).map((item) => `- ${item}`).join("\n");
}

function buildLiveStartPrompt(preview) {
  const command = Array.isArray(preview?.command) ? preview.command.join(" ") : "";
  const lines = [
    "실거래 시작 확인",
    "",
    "이 동작은 실제 업비트 주문을 낼 수 있습니다.",
    `실행 방식: ${jobTypeLabel(preview?.job_type || "live")}`,
    `대상 종목: ${dashboardState.app.market || ids.marketFocus.value.trim() || "-"}`,
    `상태 파일: ${preview?.report_state_path || ids.statePath.value.trim() || "-"}`,
  ];
  if (command) {
    lines.push(`실행 명령: ${command}`);
  }
  lines.push("");
  lines.push("계속하려면 LIVE 를 그대로 입력하세요.");
  return lines.join("\n");
}

async function confirmLiveStartFromPreview(preview) {
  ids.jobPreview.textContent = pretty(preview);
  if (!preview || preview.error) {
    ids.jobs.textContent = pretty(preview || { error: "실거래 미리보기를 불러오지 못했습니다." });
    return false;
  }
  if (!preview.can_start) {
    const issues = formatBlockingIssues(preview.blocking_issues || []);
    ids.jobs.textContent = pretty(preview);
    window.alert(`실거래 시작이 차단되었습니다.\n\n${issues || "알 수 없는 차단 사유가 있습니다."}`);
    return false;
  }
  const answer = window.prompt(buildLiveStartPrompt(preview), "");
  if (answer !== "LIVE") {
    ids.jobs.textContent = "실거래 시작을 취소했습니다. 실제 주문이 필요할 때만 LIVE 를 입력해 주세요.";
    return false;
  }
  return true;
}

function renderJobs(jobs) {
  ids.jobs.textContent = pretty(jobs || []);
  const tails = (jobs || [])
    .map((job) => {
      const heartbeat = job.heartbeat || null;
      const heartbeatLine = job.heartbeat_status
        ? `상태: ${statusLabel(job.heartbeat_status)}${job.heartbeat_age_seconds !== null && job.heartbeat_age_seconds !== undefined ? ` · ${Number(job.heartbeat_age_seconds).toFixed(1)}초 전` : ""}${heartbeat?.phase ? ` · 단계 ${heartbeat.phase}` : ""}`
        : "";
      const report = job.last_report || null;
      const reportLine = report?.json_path
        ? `리포트: ${report.json_path}`
        : report?.error
          ? `리포트 저장 문제: ${report.error}`
          : "";
      return [`# ${jobTypeLabel(job.kind || job.name || "")}`, heartbeatLine, reportLine, job.log_tail || ""].filter(Boolean).join("\n").trim();
    })
    .filter(Boolean)
    .join("\n\n");
  ids.logs.textContent = tails || "현재 실행 중인 작업 로그가 없습니다.";
}

function renderJobHistory(historyPayload) {
  ids.jobHistory.textContent = pretty(historyPayload?.items || []);
}

function renderJobHealth(jobHealthPayload) {
  const summary = jobHealthPayload?.summary || {};
  ids.jobHealthSummary.innerHTML = `
    <span class="alert-pill success">정상 ${Number(summary.healthy || 0)}</span>
    <span class="alert-pill warn">지연 ${Number(summary.stale || 0)}</span>
    <span class="alert-pill warn">누락 ${Number(summary.missing || 0)}</span>
    <span class="alert-pill error">실패 ${Number(summary.failed || 0)}</span>
    <span class="alert-pill info">실행 중 ${Number(summary.running || 0)}</span>
    <span class="alert-pill info">자동 재시작 ${Number(summary.auto_restart || 0)}</span>
    <span class="alert-pill danger">주의 필요 ${Number(summary.requires_attention || 0)}</span>
  `;
  ids.jobHealth.textContent = pretty(jobHealthPayload || { summary: {}, items: [] });
}

function renderHeroContext(payload) {
  const market = payload?.app?.market || dashboardState.app.market || "KRW-BTC";
  const mode = String(payload?.app?.mode || dashboardState.app.mode || "paper").toLowerCase();
  const releaseStatus = String(payload?.release_artifacts?.status || "missing").toLowerCase();
  const modeTone = mode === "live" ? "warning" : "info";
  const releaseTone = releaseStatus === "ready" ? "success" : releaseStatus === "invalid" ? "error" : "warning";

  setRibbonBadge(ids.heroMarket, market);
  setRibbonBadge(ids.heroMode, modeLabel(mode), modeTone);
  setRibbonBadge(ids.heroRelease, releaseLabel(releaseStatus), releaseTone);
  document.body.dataset.mode = mode;
}

function renderAlerts(alertPayload) {
  const summary = alertPayload?.summary || {};
  const items = alertPayload?.items || [];
  ids.alertsSummary.innerHTML = `
    <span class="alert-pill danger">주의 필요 ${Number(summary.requires_attention || 0)}</span>
    <span class="alert-pill warn">주의 ${Number(summary.warning || 0)}</span>
    <span class="alert-pill error">문제 ${Number(summary.error || 0)}</span>
    <span class="alert-pill success">정상 ${Number(summary.success || 0)}</span>
    <span class="alert-pill info">안내 ${Number(summary.info || 0)}</span>
  `;

  if (!items.length) {
    ids.alertsFeed.innerHTML = '<div class="empty-state">최근 알림이 없습니다.</div>';
    return;
  }

  ids.alertsFeed.innerHTML = items.map((item) => `
    <article class="alert-card ${escapeXml(item.level || "info")}">
      <div class="alert-card-head">
        <span class="chip ${escapeXml(item.level || "info")}">${escapeXml(statusLabel(item.level || "info"))}</span>
        <span class="alert-source">${escapeXml(item.market ? `${item.market} · ${item.source || "runtime"}` : item.source || "runtime")}</span>
      </div>
      <h3>${escapeXml(item.headline || "알림")}</h3>
      <p>${escapeXml(item.message || "")}</p>
      <div class="alert-meta">${escapeXml(compactTimestamp(item.timestamp))}</div>
    </article>
  `).join("");
}

function renderChecklist(checklistPayload) {
  const summary = checklistPayload?.summary || {};
  const items = checklistPayload?.items || [];
  const nextSteps = checklistPayload?.next_steps || [];

  ids.checklistSummary.innerHTML = `
    <span class="alert-pill success">정상 ${Number(summary.success || 0)}</span>
    <span class="alert-pill warn">주의 ${Number(summary.warning || 0)}</span>
    <span class="alert-pill error">문제 ${Number(summary.error || 0)}</span>
    <span class="alert-pill info">상태 ${escapeXml(statusLabel(summary.overall_status || "unknown"))}</span>
  `;

  if (!items.length) {
    ids.checklistFeed.innerHTML = '<div class="empty-state">운영 체크 항목이 아직 없습니다.</div>';
    return;
  }

  const cards = items.map((item) => `
    <article class="alert-card ${escapeXml(item.status || "info")}">
      <div class="alert-card-head">
        <span class="chip ${escapeXml(item.status || "info")}">${escapeXml(statusLabel(item.status || "info"))}</span>
        <span class="alert-source">${escapeXml(item.key || "item")}</span>
      </div>
      <h3>${escapeXml(item.title || "점검 항목")}</h3>
      <p>${escapeXml(item.detail || "")}</p>
      <div class="alert-meta">${escapeXml(item.action || "")}</div>
    </article>
  `);

  if (nextSteps.length) {
    cards.push(`
      <article class="alert-card info">
        <div class="alert-card-head">
          <span class="chip info">다음</span>
          <span class="alert-source">운영 안내</span>
        </div>
        <h3>지금 하면 좋은 일</h3>
        <p>${nextSteps.map((item, index) => `${index + 1}. ${escapeXml(item)}`).join("<br>")}</p>
        <div class="alert-meta">아래 실행 패널이나 완료 워크플로에서 바로 이어갈 수 있습니다.</div>
      </article>
    `);
  }

  ids.checklistFeed.innerHTML = cards.join("");
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
  if (!ids.jobReportKeep.value && payload.ui_defaults?.report_keep_latest !== undefined) {
    ids.jobReportKeep.value = payload.ui_defaults.report_keep_latest;
  }
  if (!ids.liveTestKrw.value && payload.ui_defaults?.live_validation_buy_krw !== undefined) {
    ids.liveTestKrw.value = payload.ui_defaults.live_validation_buy_krw;
  }

  const editableConfig = payload.editable_config || {};
  ids.cfgBuyThreshold.value = editableConfig["strategy.buy_threshold"] ?? "";
  ids.cfgSellThreshold.value = editableConfig["strategy.sell_threshold"] ?? "";
  ids.cfgMinAdx.value = editableConfig["strategy.min_adx"] ?? "";
  ids.cfgMinBbWidth.value = editableConfig["strategy.min_bollinger_width_fraction"] ?? "";
  ids.cfgVolumeSpike.value = editableConfig["strategy.volume_spike_multiplier"] ?? "";
  ids.liveCfgBuyThreshold.value = editableConfig["strategy.buy_threshold"] ?? "";
  ids.liveCfgSellThreshold.value = editableConfig["strategy.sell_threshold"] ?? "";
  ids.liveCfgMaxPositionFraction.value = editableConfig["risk.max_position_fraction"] ?? "";
  ids.liveCfgMaxTradesPerDay.value = editableConfig["runtime.max_trades_per_day"] ?? "";
  ids.liveCfgSelectorMaxMarkets.value = editableConfig["selector.max_markets"] ?? "";
  ids.liveCfgIncludeMarkets.value = Array.isArray(editableConfig["selector.include_markets"])
    ? editableConfig["selector.include_markets"].join(", ")
    : (editableConfig["selector.include_markets"] ?? "");
  ids.cfgPollSeconds.value = editableConfig["runtime.poll_seconds"] ?? "";
  ids.cfgSelectorMaxMarkets.value = editableConfig["selector.max_markets"] ?? "";
  ids.config.textContent = pretty(editableConfig);
}

function defaultCsvPathForMarket(market) {
  if (!market) {
    return "";
  }
  const candleUnit = Number(dashboardState.app.candle_unit || 240);
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
    return new Intl.NumberFormat("ko-KR", {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(numeric);
  }
  return formatNumber(numeric, 2);
}

function eventHeadline(message) {
  const normalized = String(message || "").toUpperCase();
  if (normalized.includes("BUY")) {
    return "매수 관련 알림";
  }
  if (normalized.includes("SELL")) {
    return "매도 관련 알림";
  }
  if (normalized.includes("BLOCK")) {
    return "보호 장치로 차단됨";
  }
  if (normalized.includes("ORDER")) {
    return "주문 상태 변경";
  }
  if (normalized.includes("RECONCILE")) {
    return "상태 점검";
  }
  return "자동매매 동작 기록";
}

function trimTimestampPrefix(message) {
  const text = String(message || "");
  const parts = text.split(" ");
  if (parts.length > 1 && parts[0].includes("T")) {
    return parts.slice(1).join(" ");
  }
  return text;
}

function renderActivityCards(target, items, emptyMessage) {
  if (!items || !items.length) {
    target.innerHTML = `<div class="empty-state">${escapeXml(emptyMessage)}</div>`;
    return;
  }
  target.innerHTML = items.map((item) => {
    if (typeof item === "string") {
      const raw = String(item);
      const firstToken = raw.split(" ", 1)[0];
      const timestamp = firstToken.includes("T") ? compactTimestamp(firstToken) : "방금";
      return `
        <article class="activity-card">
          <div class="alert-card-head">
            <span class="chip info">기록</span>
            <span class="alert-source">${escapeXml(timestamp)}</span>
          </div>
          <h3>${escapeXml(eventHeadline(raw))}</h3>
          <p>${escapeXml(trimTimestampPrefix(raw))}</p>
        </article>
      `;
    }
    return `
      <article class="activity-card">
        <div class="alert-card-head">
          <span class="chip info">${escapeXml(statusLabel(item.level || "info"))}</span>
          <span class="alert-source">${escapeXml(compactTimestamp(item.timestamp || ""))}</span>
        </div>
        <h3>${escapeXml(item.title || item.headline || "최근 기록")}</h3>
        <p>${escapeXml(item.detail || item.message || "")}</p>
      </article>
    `;
  }).join("");
}

function renderRecentTrades(trades) {
  if (!trades || !trades.length) {
    ids.recentTrades.innerHTML = '<div class="empty-state">아직 완료된 거래가 없습니다.</div>';
    return;
  }
  ids.recentTrades.innerHTML = trades.map((trade) => {
    const tone = Number(trade.net_pnl || 0) >= 0 ? "success" : "error";
    const title = `${trade.market || dashboardState.app.market || "-"} · ${trade.side === "buy" ? "매수" : "매도"} 완료`;
    return `
      <article class="activity-card">
        <div class="alert-card-head">
          <span class="chip ${tone}">${escapeXml(Number(trade.net_pnl || 0) >= 0 ? "수익" : "손실")}</span>
          <span class="alert-source">${escapeXml(compactTimestamp(trade.exit_timestamp || trade.entry_timestamp || ""))}</span>
        </div>
        <h3>${escapeXml(title)}</h3>
        ${buildFactGrid([
          factCard("진입가", formatNumber(trade.entry_price, 0)),
          factCard("청산가", formatNumber(trade.exit_price, 0)),
          factCard("순손익", formatCurrency(trade.net_pnl || 0), tone),
          factCard("수익률", `${formatNumber((trade.return_pct || 0) * 100, 2)}%`, tone),
        ])}
      </article>
    `;
  }).join("");
}

function renderRecentEvents(events) {
  renderActivityCards(ids.recentEvents, events || [], "최근 동작이 아직 없습니다.");
}

function renderSelectorSummary(selectorPayload) {
  if (!selectorPayload || !Object.keys(selectorPayload).length) {
    ids.selectorSummary.innerHTML = '<div class="empty-state">자동 종목 선택 결과를 아직 불러오지 못했습니다.</div>';
    return;
  }
  const lastScan = selectorPayload.last_scan_results || [];
  ids.selectorSummary.innerHTML = buildFactGrid([
    factCard("현재 선택 종목", selectorPayload.active_market || "없음"),
    factCard("후보 종목 수", formatNumber(lastScan.length, 0)),
    factCard("최근 스캔 시각", compactTimestamp(selectorPayload.last_scan_timestamp || "")),
    factCard("자동 선택 상태", selectorPayload.active_market ? "선택 중" : "대기 중"),
  ]);
}

function renderSelectorActiveSummary(summary) {
  if (!summary || !Object.keys(summary).length) {
    ids.selectorActiveSummary.innerHTML = '<div class="empty-state">선택된 종목이 아직 없습니다.</div>';
    return;
  }
  ids.selectorActiveSummary.innerHTML = buildFactGrid([
    factCard("종목", summary.market || "-"),
    factCard("모드", modeLabel(summary.mode || dashboardState.app.mode || "paper")),
    factCard("평가 금액", formatCurrency(summary.equity || 0)),
    factCard("보유 현금", formatCurrency(summary.cash || 0)),
    factCard("거래 횟수", formatNumber(summary.trade_count || 0, 0)),
    factCard("마지막 신호", summary.last_signal?.action ? actionLabel(summary.last_signal.action) : "없음"),
  ]);
}

function renderLiveControl(liveControl) {
  const payload = liveControl || {};
  const blockers = Array.isArray(payload.readiness_blockers) ? payload.readiness_blockers : [];
  const liveEnabled = Boolean(payload.live_enabled);
  const privateReady = Boolean(payload.private_ready);
  const stateReady = Boolean(payload.state_exists);
  const lastValidation = payload.last_validation || {};
  const lastValidationAt = lastValidation.generated_at || lastValidation.generatedAt || "";
  const statusMessage = blockers.length
    ? `아직 확인이 필요한 항목이 ${blockers.length}개 있습니다. 먼저 실거래 준비 다시 확인을 눌러 주세요.`
    : liveEnabled
      ? "실거래를 시작할 준비가 되어 있습니다. 실제 주문은 실거래 시작 버튼에서 한 번 더 LIVE 를 입력해야 합니다."
      : "현재는 안전 모드입니다. 실제 주문을 하려면 먼저 실거래 켜기를 눌러 주세요.";

  ids.liveControlSummary.innerHTML = buildFactGrid([
    factCard("실거래 스위치", liveEnabled ? "켜짐" : "꺼짐", liveEnabled ? "success" : ""),
    factCard("업비트 키 상태", privateReady ? "정상" : "확인 필요", privateReady ? "success" : "error"),
    factCard("상태 파일", stateReady ? "준비됨" : "없음", stateReady ? "success" : "error"),
    factCard("대상 종목", payload.market || dashboardState.app.market || "-"),
    factCard("남은 차단 항목", formatNumber(blockers.length, 0)),
    factCard("최근 검증", lastValidationAt ? compactTimestamp(lastValidationAt) : "없음"),
  ]);

  ids.liveControlStatus.textContent = statusMessage;
  ids.liveControlJson.textContent = pretty(payload);
}

function renderMarketCards(target, results, emptyMessage, options = {}) {
  if (!results.length) {
    target.innerHTML = `<div class="empty-state">${escapeXml(emptyMessage)}</div>`;
    return;
  }

  const activeMarket = options.activeMarket || "";
  const buttonLabel = options.buttonLabel || "이 종목 보기";

  target.innerHTML = results.map((item, index) => {
    const action = String(item.action || "HOLD").toLowerCase();
    const normalizedReasons = (item.reasons || []).slice(0, 4).map((value) => escapeXml(value)).join(" · ");
    const warningChip = item.market_warning && item.market_warning !== "NONE"
      ? `<span class="chip warn">주의 ${escapeXml(item.market_warning)}</span>`
      : '<span class="chip good">주의 없음</span>';
    const liquidityChip = item.liquidity_ok
      ? '<span class="chip good">거래대금 양호</span>'
      : '<span class="chip warn">거래대금 낮음</span>';
    const activeChip = item.market === activeMarket
      ? '<span class="chip active">선택됨</span>'
      : "";
    return `
      <article class="scan-card">
        <div class="scan-card-head">
          <div>
            <p class="scan-rank">후보 ${index + 1}</p>
            <h3>${escapeXml(item.market)}</h3>
          </div>
          <span class="scan-badge ${action}">${escapeXml(actionLabel(item.action || "HOLD"))}</span>
        </div>
        <div class="scan-meta">
          <span>${escapeXml(compactTimestamp(item.timestamp || ""))}</span>
          <span>신뢰도 ${formatNumber(item.confidence || 0, 2)}</span>
        </div>
        <div class="scan-metrics">
          <div class="scan-metric">
            <span class="scan-metric-label">점수</span>
            <strong class="scan-metric-value">${formatNumber(item.score || 0, 1)}</strong>
          </div>
          <div class="scan-metric">
            <span class="scan-metric-label">현재가</span>
            <strong class="scan-metric-value">${formatNumber(item.close, 0)}</strong>
          </div>
          <div class="scan-metric">
            <span class="scan-metric-label">24시간 거래대금</span>
            <strong class="scan-metric-value">${formatCompactNumber(item.liquidity_24h)}</strong>
          </div>
          <div class="scan-metric">
            <span class="scan-metric-label">판단 근거 수</span>
            <strong class="scan-metric-value">${(item.reasons || []).length}</strong>
          </div>
        </div>
        <div class="chip-row">
          ${liquidityChip}
          ${warningChip}
          ${activeChip}
        </div>
        <p class="scan-reasons">${normalizedReasons || "아직 충분한 판단 근거가 모이지 않았습니다."}</p>
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
    "아직 스캔 결과가 없습니다. 아래에서 시장 스캔을 실행해 보세요.",
  );
}

function renderSelectorCards(selectorPayload) {
  renderMarketCards(
    ids.selectorCards,
    selectorPayload?.last_scan_results || [],
    "자동 종목 선택 결과를 아직 불러오지 못했습니다.",
    {
      activeMarket: selectorPayload?.active_market || "",
      buttonLabel: "이 종목 기준으로 보기",
    },
  );
}

function renderPresets(presetPayload) {
  const items = presetPayload?.items || [];
  ids.presets.textContent = pretty(presetPayload || { dir: "", items: [] });

  const currentValue = ids.presetSelect.value;
  if (!items.length) {
    ids.presetSelect.innerHTML = '<option value="">저장된 전략이 없습니다</option>';
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

function assignOptionalNumber(target, key, rawValue) {
  const normalized = String(rawValue ?? "").trim();
  if (!normalized) {
    return;
  }
  target[key] = Number(normalized);
}

function renderProfiles(profilePayload) {
  const items = profilePayload?.items || [];
  ids.profiles.textContent = pretty(profilePayload || { dir: "", items: [] });

  const currentValue = ids.profileSelect.value;
  if (!items.length) {
    ids.profileSelect.innerHTML = '<option value="">저장된 운영 프로필이 없습니다</option>';
    return;
  }

  ids.profileSelect.innerHTML = items
    .map((item) => {
      const summary = item.summary || {};
      const runs = Number(item.start_count || 0);
      const label = [
        item.name || "프로필",
        jobTypeLabel(summary.job_type || ""),
        summary.market || "",
        summary.report_keep_latest ? `리포트 ${summary.report_keep_latest}개 유지` : "",
        runs > 0 ? `실행 ${runs}회` : "",
      ].filter(Boolean).join(" | ");
      return `<option value="${escapeXml(item.path)}">${escapeXml(label)}</option>`;
    })
    .join("");

  const nextValue = items.some((item) => item.path === currentValue)
    ? currentValue
    : items[0].path;
  ids.profileSelect.value = nextValue;
}

function renderCompletionWorkflow(workflowPayload) {
  const items = workflowPayload?.items || [];
  ids.workflow.textContent = pretty(workflowPayload || { items: [] });

  const currentValue = ids.workflowStage.value;
  if (!items.length) {
    ids.workflowStage.innerHTML = '<option value="">실행 가능한 마감 단계가 없습니다</option>';
    return;
  }

  ids.workflowStage.innerHTML = items
    .map((item) => `<option value="${escapeXml(item.stage)}">${escapeXml(item.label || workflowStageLabel(item.stage))} | ${escapeXml(item.description)}</option>`)
    .join("");

  const fallbackValue = workflowPayload?.default_stage || items[0].stage;
  const nextValue = items.some((item) => item.stage === currentValue)
    ? currentValue
    : fallbackValue;
  ids.workflowStage.value = nextValue;
}

function renderReleaseArtifacts(releasePayload) {
  const payload = releasePayload || {};
  const status = String(payload.status || "missing");
  const issues = Array.isArray(payload.issues) ? payload.issues : [];
  const formattedIssues = issues.slice(0, 3).map((item) => String(item).replaceAll(":", " "));
  const statusClass = status === "ready" ? "success" : status === "partial" ? "warn" : status === "missing" ? "warn" : "error";
  const manifestState = payload.manifest_exists
    ? (payload.manifest_load_ok ? "설명서 읽기 완료" : "설명서 읽기 실패")
    : "설명서 없음";
  const zipState = payload.zip_exists ? "배포 파일 준비됨" : "배포 파일 없음";
  const checksumState = payload.checksum_ok ? "무결성 확인 완료" : "무결성 확인 필요";
  const verificationState = payload.verification_current
    ? "검증 완료"
    : payload.verification_exists
      ? (payload.verification_load_ok ? "검증 다시 필요" : "검증 파일 읽기 실패")
      : "검증 전";
  const supportState = payload.includes_support_bundle
    ? (payload.support_zip_exists ? "지원 번들 포함" : "지원 번들 없음")
    : "지원 번들 선택";
  let recommendedStage = "release-pack";
  let recommendation = "배포 전에 최신 릴리스 팩을 다시 만들어 주세요.";

  if (status === "ready") {
    if (payload.verification_current) {
      recommendedStage = "release-clean";
      recommendation = payload.verified_at
        ? `${compactTimestamp(payload.verified_at)} 기준으로 배포 검증이 끝났습니다. 전달이 끝나면 정리 버튼으로 마무리하세요.`
        : "배포 검증이 끝났습니다. 전달이 끝나면 정리 버튼으로 마무리하세요.";
    } else {
      recommendedStage = "release-verify";
      recommendation = "배포 파일은 만들어졌습니다. 실제 전달 전에는 검증 버튼으로 마지막 확인을 해 주세요.";
    }
  } else if (status === "invalid") {
    recommendedStage = "release-pack";
    recommendation = formattedIssues.length
      ? `배포 파일에 문제가 있습니다: ${formattedIssues.join(", ")}. 다시 만들기부터 진행하세요.`
      : "배포 파일에 문제가 있습니다. 다시 만들기부터 진행하세요.";
  } else if (status === "partial") {
    recommendedStage = "release-pack";
    recommendation = formattedIssues.length
      ? `배포 파일이 일부만 준비되었습니다: ${formattedIssues.join(", ")}. 다시 만들고 검증까지 진행하세요.`
      : "배포 파일이 일부만 준비되었습니다. 다시 만들고 검증까지 진행하세요.";
  }

  ids.releaseArtifactsSummary.innerHTML = `
    <span class="alert-pill ${statusClass}">상태 ${escapeXml(releaseLabel(status))}</span>
    <span class="alert-pill info">${escapeXml(manifestState)}</span>
    <span class="alert-pill info">${escapeXml(zipState)}</span>
    <span class="alert-pill info">${escapeXml(checksumState)}</span>
    <span class="alert-pill info">${escapeXml(verificationState)}</span>
    <span class="alert-pill info">${escapeXml(supportState)}</span>
    <span class="alert-pill info">파일 ${Number(payload.manifest_file_count || 0)}개</span>
  `;
  ids.releaseNextStep.innerHTML = `
    <strong>추천 작업</strong>
    <p>${escapeXml(recommendation)}</p>
    <div class="release-next-step-meta">추천 단계: ${escapeXml(recommendedStage)}</div>
    ${payload.verified_at ? `<div class="release-next-step-meta">검증 시각: ${escapeXml(compactTimestamp(payload.verified_at))}</div>` : ""}
    ${formattedIssues.length ? `<div class="release-next-step-meta">확인 필요: ${escapeXml(formattedIssues.join(" | "))}</div>` : ""}
  `;
  dashboardState.releaseRecommendedStage = recommendedStage;
  ids.runReleaseRecommended.textContent = recommendedStage === "release-pack"
    ? "추천 작업 실행: 릴리스 팩 만들기"
    : recommendedStage === "release-verify"
      ? "추천 작업 실행: 릴리스 팩 검증"
      : "추천 작업 실행: 릴리스 산출물 정리";
  ids.runReleasePack.classList.toggle("recommended", recommendedStage === "release-pack");
  ids.runReleaseVerify.classList.toggle("recommended", recommendedStage === "release-verify");
  ids.runReleaseClean.classList.toggle("recommended", recommendedStage === "release-clean");
  ids.releaseArtifacts.textContent = pretty(payload);
}

function applyLoadedProfileMeta(payload) {
  if (!payload) {
    return;
  }
  ids.profileName.value = payload.name || ids.profileName.value;
  ids.profileNotes.value = payload.notes || "";
}

function renderReports(reportPayload) {
  const items = reportPayload?.items || [];
  const currentValue = ids.reportSelect.value;
  if (!items.length) {
    ids.reportSelect.innerHTML = '<option value="">저장된 리포트가 없습니다</option>';
    return;
  }

  ids.reportSelect.innerHTML = items
    .map((item) => {
      const label = `${item.market || "시장 미지정"} | ${modeLabel(item.mode || "paper")} | 거래 ${item.trade_count}회 | 손익 ${formatCurrency(item.total_net_pnl || 0, 0)}`;
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
  ids.jobReportKeep.value = profilePayload.report_keep_latest || dashboardState.defaults.report_keep_latest || 20;
  if (profilePayload.preset) {
    ids.presetSelect.value = profilePayload.preset;
  }
}

function renderChart(chartElement, metaElement, chartPayload) {
  if (!chartPayload || !chartPayload.points || chartPayload.points.length === 0) {
    chartElement.innerHTML = "";
    metaElement.textContent = "차트 데이터가 아직 없습니다.";
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
        <stop offset="0%" stop-color="rgba(20, 86, 255, 0.26)"></stop>
        <stop offset="100%" stop-color="rgba(20, 86, 255, 0.02)"></stop>
      </linearGradient>
    </defs>
    <path d="${areaPath}" fill="url(#${gradientId})"></path>
    <path d="${linePath}" fill="none" stroke="#1456ff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
    ${markers}
    <circle cx="${latest.x}" cy="${latest.y}" r="6" fill="#0d3cae"></circle>
  `;
  metaElement.textContent = `최근 ${chartPayload.points.length}개 캔들 · 표시 ${(chartPayload.markers || []).length}개 · 저가 ${formatNumber(min, 0)} · 고가 ${formatNumber(max, 0)} · 최신 ${formatNumber(latest.close, 0)} @ ${compactTimestamp(latest.timestamp)}`;
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
    renderHeroContext(payload);
    const summary = payload.state_summary || {};
    setMetric(ids.market, payload.app.market);
    setMetric(ids.mode, modeLabel(payload.app.mode));
    setMetric(ids.equity, formatCurrency(summary.equity ?? 0));
    setMetric(ids.cash, formatCurrency(summary.cash ?? 0));
    setMetric(ids.position, summary.position ? "보유 중" : "없음");
    setMetric(ids.pending, summary.pending_order ? actionLabel(summary.pending_order.side || "hold") : "없음");
    ids.summary.textContent = pretty(summary);
    ids.signal.textContent = pretty(payload.latest_signal);
    ids.paths.textContent = pretty(payload.paths);
    ids.readiness.textContent = pretty(payload.broker_readiness);
    renderLiveControl(payload.live_control || {});
    renderAlerts(payload.alerts || null);
    renderChecklist(payload.operator_checklist || null);
    renderJobHealth(payload.job_health || null);
    renderRecentTrades(payload.activity?.recent_trades || []);
    renderRecentEvents(payload.activity?.recent_events || []);
    renderSelectorSummary(payload.selector_summary || {});
    renderSelectorActiveSummary(payload.selector_summary?.active_market_summary || {});
    renderActivityCards(
      ids.selectorActiveEvents,
      payload.selector_summary?.active_market_activity?.recent_events || [],
      "선택된 종목의 최근 기록이 아직 없습니다.",
    );
    renderSelectorCards(payload.selector_summary || null);
    renderPresets(payload.strategy_presets || null);
    renderProfiles(payload.operator_profiles || null);
    renderCompletionWorkflow(payload.completion_workflow || null);
    renderReleaseArtifacts(payload.release_artifacts || null);
    renderReports(payload.session_reports || null);
    renderChart(ids.selectorActiveChart, ids.selectorActiveChartMeta, payload.selector_summary?.active_market_chart);
    renderJobs(payload.jobs);
    renderJobHistory(payload.job_history);
    renderPriceChart(payload.chart);
  } catch (error) {
    ids.summary.textContent = `화면을 불러오는 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runSignal() {
  try {
    ids.signal.textContent = "최신 신호를 계산하고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/signal", {
      csv_path: inputs.csv_path,
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.signal.textContent = pretty(payload);
  } catch (error) {
    ids.signal.textContent = `신호 계산 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runBacktest() {
  try {
    ids.backtest.textContent = "백테스트를 실행하고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/backtest", {
      csv_path: inputs.csv_path,
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.backtest.textContent = pretty(payload);
  } catch (error) {
    ids.backtest.textContent = `백테스트 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runOptimize(saveBest = false) {
  try {
    ids.optimize.textContent = saveBest ? "전략 조합을 찾고 가장 좋은 값을 저장하는 중입니다..." : "전략 조합을 찾고 있습니다...";
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
    ids.optimize.textContent = `전략 조정 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runScan() {
  try {
    ids.scan.textContent = "시장 후보를 스캔하고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/scan", {
      max_markets: inputs.max_markets,
      quote_currency: inputs.quote_currency,
    });
    ids.scan.textContent = pretty(payload);
    renderScanCards(payload);
  } catch (error) {
    ids.scan.textContent = `시장 스캔 중 문제가 발생했습니다: ${error.message}`;
    renderScanCards(null);
  }
}

async function runReconcile() {
  try {
    ids.reconcile.textContent = "계좌와 상태를 다시 맞추고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/reconcile", {
      state_path: inputs.state_path,
      mode: dashboardState.app.mode || "paper",
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.reconcile.textContent = pretty(payload);
  } catch (error) {
    ids.reconcile.textContent = `상태 점검 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runDoctor() {
  try {
    ids.doctor.textContent = "운영 상태를 점검하고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/doctor", {
      state_path: inputs.state_path,
      selector_state_path: inputs.selector_state_path,
    });
    ids.doctor.textContent = pretty(payload);
  } catch (error) {
    ids.doctor.textContent = `점검 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function toggleLiveMode(enabled) {
  try {
    ids.liveControlStatus.textContent = enabled
      ? "실거래 스위치를 켜는 중입니다..."
      : "실거래 스위치를 끄는 중입니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/live-toggle", {
      enabled,
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.liveControlJson.textContent = pretty(payload);
    ids.liveControlStatus.textContent = payload.message || (enabled ? "실거래를 켰습니다." : "실거래를 껐습니다.");
    await refreshDashboard();
  } catch (error) {
    ids.liveControlStatus.textContent = `실거래 스위치 변경 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runLiveEasyPrep() {
  try {
    ids.liveControlStatus.textContent = "실거래 준비를 다시 확인하고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/live-easy-prep", {
      state_path: inputs.state_path,
      selector_state_path: inputs.selector_state_path,
      csv_path: inputs.csv_path,
      market: inputs.market || dashboardState.app.market || undefined,
      count: inputs.sync_count,
    });
    ids.liveControlJson.textContent = pretty(payload);
    ids.liveControlStatus.textContent = payload.message || "실거래 준비를 마쳤습니다.";
    await refreshDashboard();
  } catch (error) {
    ids.liveControlStatus.textContent = `실거래 준비 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runLiveMarketTest() {
  try {
    const buyKrw = Number(ids.liveTestKrw.value || "0");
    if (!Number.isFinite(buyKrw) || buyKrw < 5000) {
      ids.liveControlStatus.textContent = "시장가 검증 금액은 5000원 이상으로 입력해 주세요.";
      return;
    }
    const answer = window.prompt(
      `실제 주문 확인\n\n이 동작은 업비트에 시장가 매수 1회와 시장가 매도 1회를 보냅니다.\n검증 금액: ${formatCurrency(buyKrw, 0)}\n\n계속하려면 LIVE 를 입력하세요.`,
      "",
    );
    if (answer !== "LIVE") {
      ids.liveControlStatus.textContent = "시장가 소액 검증을 취소했습니다.";
      return;
    }
    ids.liveControlStatus.textContent = "시장가 소액 검증을 진행하고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/live-market-test", {
      state_path: inputs.state_path,
      market: inputs.market || dashboardState.app.market || undefined,
      buy_krw: buyKrw,
      confirm: answer,
    });
    ids.liveControlJson.textContent = pretty(payload);
    ids.liveControlStatus.textContent = payload.message || "시장가 소액 검증을 마쳤습니다.";
    await refreshDashboard();
  } catch (error) {
    ids.liveControlStatus.textContent = `시장가 소액 검증 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runSyncCandles() {
  try {
    ids.paths.textContent = "최신 캔들 데이터를 가져오고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/sync-candles", {
      csv_path: inputs.csv_path,
      count: inputs.sync_count,
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.paths.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.paths.textContent = `캔들 동기화 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runSessionReport() {
  try {
    ids.report.textContent = "세션 리포트를 저장하고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/session-report", {
      state_path: inputs.state_path,
      mode: dashboardState.app.mode || "paper",
      label: (inputs.market || dashboardState.app.market || "session").toLowerCase(),
    });
    ids.report.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.report.textContent = `리포트 저장 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function loadSessionReport() {
  try {
    const report = ids.reportSelect.value;
    if (!report) {
      ids.report.textContent = "먼저 불러올 리포트를 선택해 주세요.";
      return;
    }
    ids.report.textContent = "리포트를 불러오고 있습니다...";
    const payload = await postJson("/api/report-show", { report });
    ids.report.textContent = pretty(payload);
  } catch (error) {
    ids.report.textContent = `리포트 불러오기 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function deleteSessionReport() {
  try {
    const report = ids.reportSelect.value;
    if (!report) {
      ids.report.textContent = "먼저 삭제할 리포트를 선택해 주세요.";
      return;
    }
    ids.report.textContent = "리포트를 삭제하고 있습니다...";
    const payload = await postJson("/api/report-delete", { report });
    ids.report.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.report.textContent = `리포트 삭제 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function pruneSessionReports() {
  try {
    ids.report.textContent = "오래된 리포트를 정리하고 있습니다...";
    const keep = Number(ids.reportKeep.value || "10");
    const payload = await postJson("/api/report-prune", { keep });
    ids.report.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.report.textContent = `리포트 정리 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function refreshJobs() {
  try {
    const payload = await getJson("/api/jobs");
    renderJobs(payload.jobs);
    renderJobHealth(payload.job_health || null);
    renderJobHistory({ items: payload.history || [] });
  } catch (error) {
    ids.jobs.textContent = `실행 중인 작업을 불러오는 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function startJob(jobType) {
  try {
    ids.jobs.textContent = `${jobTypeLabel(jobType)} 시작 준비 중입니다...`;
    const inputs = currentInputs();
    const jobSettings = currentJobSettings();
    if (isLiveJobType(jobType)) {
      const preview = await postJson("/api/jobs-preview", {
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
        report_keep_latest: jobSettings.report_keep_latest,
      });
      const confirmed = await confirmLiveStartFromPreview(preview);
      if (!confirmed) {
        return;
      }
    }
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
      report_keep_latest: jobSettings.report_keep_latest,
    });
    ids.jobs.textContent = pretty(payload);
    if (payload?.error) {
      return;
    }
    await refreshJobs();
  } catch (error) {
    ids.jobs.textContent = `작업 시작 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function previewJob(jobType = ids.jobType.value) {
  try {
    ids.jobPreview.textContent = `${jobTypeLabel(jobType)} 미리보기를 준비하고 있습니다...`;
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
      report_keep_latest: jobSettings.report_keep_latest,
    });
    ids.jobPreview.textContent = pretty(payload);
  } catch (error) {
    ids.jobPreview.textContent = `미리보기 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function stopJob(jobName) {
  try {
    ids.jobs.textContent = `${jobTypeLabel(jobName)} 중지 중입니다...`;
    const payload = await postJson("/api/jobs-stop", { job_name: jobName });
    ids.jobs.textContent = pretty(payload);
    await refreshJobs();
  } catch (error) {
    ids.jobs.textContent = `작업 중지 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function stopAllJobs() {
  try {
    ids.jobs.textContent = "실행 중인 작업을 모두 중지하고 있습니다...";
    const payload = await postJson("/api/jobs-stop-all", {});
    ids.jobs.textContent = pretty(payload);
    await refreshJobs();
  } catch (error) {
    ids.jobs.textContent = `전체 중지 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function cleanupJobs() {
  try {
    ids.jobs.textContent = "중지된 작업 흔적을 정리하고 있습니다...";
    const payload = await postJson("/api/jobs-cleanup", { remove_logs: false });
    ids.jobs.textContent = pretty(payload);
    await refreshJobs();
  } catch (error) {
    ids.jobs.textContent = `작업 정리 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function saveConfig() {
  try {
    ids.config.textContent = "설정을 저장하고 있습니다...";
    const request = {};
    assignOptionalNumber(request, "strategy.buy_threshold", ids.cfgBuyThreshold.value);
    assignOptionalNumber(request, "strategy.sell_threshold", ids.cfgSellThreshold.value);
    assignOptionalNumber(request, "strategy.min_adx", ids.cfgMinAdx.value);
    assignOptionalNumber(request, "strategy.min_bollinger_width_fraction", ids.cfgMinBbWidth.value);
    assignOptionalNumber(request, "strategy.volume_spike_multiplier", ids.cfgVolumeSpike.value);
    assignOptionalNumber(request, "runtime.poll_seconds", ids.cfgPollSeconds.value);
    assignOptionalNumber(request, "selector.max_markets", ids.cfgSelectorMaxMarkets.value);
    const payload = await postJson("/api/config-save", request);
    ids.config.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.config.textContent = `설정 저장 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function saveLiveConfig() {
  try {
    ids.liveControlStatus.textContent = "실거래 설정을 저장하고 있습니다...";
    const request = {};
    assignOptionalNumber(request, "strategy.buy_threshold", ids.liveCfgBuyThreshold.value);
    assignOptionalNumber(request, "strategy.sell_threshold", ids.liveCfgSellThreshold.value);
    assignOptionalNumber(request, "risk.max_position_fraction", ids.liveCfgMaxPositionFraction.value);
    assignOptionalNumber(request, "runtime.max_trades_per_day", ids.liveCfgMaxTradesPerDay.value);
    assignOptionalNumber(request, "selector.max_markets", ids.liveCfgSelectorMaxMarkets.value);
    request["selector.include_markets"] = ids.liveCfgIncludeMarkets.value.trim();
    const payload = await postJson("/api/config-save", request);
    ids.liveControlStatus.textContent = "실거래 설정을 저장했습니다. 준비 다시 확인 후 시작하면 됩니다.";
    ids.liveControlJson.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.liveControlStatus.textContent = `실거래 설정 저장 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function saveCurrentPreset() {
  try {
    ids.presets.textContent = "현재 전략을 저장하고 있습니다...";
    const inputs = currentInputs();
    const payload = await postJson("/api/preset-save-current", {
      preset_name: resolvePresetName("current"),
      csv_path: inputs.csv_path,
      market: inputs.market || dashboardState.app.market || undefined,
    });
    ids.presets.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.presets.textContent = `전략 저장 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function applyPreset() {
  try {
    const preset = ids.presetSelect.value;
    if (!preset) {
      ids.presets.textContent = "먼저 적용할 전략을 선택해 주세요.";
      return;
    }
    ids.presets.textContent = "전략을 적용하고 있습니다...";
    const payload = await postJson("/api/preset-apply", { preset });
    ids.presets.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.presets.textContent = `전략 적용 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function saveProfile() {
  try {
    ids.profiles.textContent = "운영 프로필을 저장하고 있습니다...";
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
        report_keep_latest: jobSettings.report_keep_latest,
      },
      notes: ids.profileNotes.value.trim(),
    });
    ids.profiles.textContent = pretty(payload);
    applyLoadedProfileMeta(payload);
    await refreshDashboard();
  } catch (error) {
    ids.profiles.textContent = `운영 프로필 저장 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function loadProfile() {
  try {
    const profile = ids.profileSelect.value;
    if (!profile) {
      ids.profiles.textContent = "먼저 불러올 운영 프로필을 선택해 주세요.";
      return;
    }
    ids.profiles.textContent = "운영 프로필을 불러오고 있습니다...";
    const payload = await postJson("/api/profile-load", { profile });
    ids.profiles.textContent = pretty(payload);
    applyLoadedProfileMeta(payload);
    applyProfileToForm(payload.profile);
    await refreshDashboard();
  } catch (error) {
    ids.profiles.textContent = `운영 프로필 불러오기 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function deleteProfile() {
  try {
    const profile = ids.profileSelect.value;
    if (!profile) {
      ids.profiles.textContent = "먼저 삭제할 운영 프로필을 선택해 주세요.";
      return;
    }
    ids.profiles.textContent = "운영 프로필을 삭제하고 있습니다...";
    const payload = await postJson("/api/profile-delete", { profile });
    ids.profiles.textContent = pretty(payload);
    await refreshDashboard();
  } catch (error) {
    ids.profiles.textContent = `운영 프로필 삭제 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function previewProfile() {
  try {
    const profile = ids.profileSelect.value;
    if (!profile) {
      ids.profiles.textContent = "먼저 미리볼 운영 프로필을 선택해 주세요.";
      return;
    }
    ids.jobPreview.textContent = "운영 프로필 미리보기를 준비하고 있습니다...";
    const payload = await postJson("/api/profile-preview", { profile });
    ids.jobPreview.textContent = pretty(payload);
    if (payload.profile) {
      applyLoadedProfileMeta(payload.profile);
    }
    if (payload.profile?.profile) {
      applyProfileToForm(payload.profile.profile);
    }
  } catch (error) {
    ids.jobPreview.textContent = `운영 프로필 미리보기 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function startProfile() {
  try {
    const profile = ids.profileSelect.value;
    if (!profile) {
      ids.profiles.textContent = "먼저 시작할 운영 프로필을 선택해 주세요.";
      return;
    }
    ids.jobs.textContent = "운영 프로필을 시작하고 있습니다...";
    const preview = await postJson("/api/profile-preview", { profile });
    ids.jobPreview.textContent = pretty(preview);
    if (preview?.job_preview && isLiveJobType(preview.job_preview.job_type || preview.profile?.profile?.job_type || "")) {
      const confirmed = await confirmLiveStartFromPreview(preview.job_preview);
      if (!confirmed) {
        return;
      }
    }
    const payload = await postJson("/api/profile-start", { profile });
    ids.jobs.textContent = pretty(payload);
    if (payload.profile) {
      applyLoadedProfileMeta(payload.profile);
    }
    if (payload.profile?.profile) {
      applyProfileToForm(payload.profile.profile);
    }
    if (payload?.error) {
      return;
    }
    await refreshJobs();
    await refreshDashboard();
  } catch (error) {
    ids.jobs.textContent = `운영 프로필 시작 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function previewWorkflow() {
  try {
    const stage = ids.workflowStage.value;
    if (!stage) {
      ids.workflow.textContent = "먼저 미리볼 마감 단계를 선택해 주세요.";
      return;
    }
    ids.workflow.textContent = `선택한 마감 단계(${stage})를 미리보고 있습니다...`;
    const payload = await postJson("/api/workflow-preview", { stage });
    ids.workflow.textContent = pretty(payload);
  } catch (error) {
    ids.workflow.textContent = `마감 단계 미리보기 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function startWorkflow() {
  try {
    const stage = ids.workflowStage.value;
    if (!stage) {
      ids.workflow.textContent = "먼저 실행할 마감 단계를 선택해 주세요.";
      return;
    }
    ids.workflow.textContent = `마감 단계(${stage})를 실행하고 있습니다...`;
    const payload = await postJson("/api/workflow-start", { stage });
    ids.workflow.textContent = pretty(payload);
    if (payload?.error) {
      return;
    }
    await refreshJobs();
    await refreshDashboard();
  } catch (error) {
    ids.workflow.textContent = `마감 단계 실행 중 문제가 발생했습니다: ${error.message}`;
  }
}

async function runReleaseWorkflow(stage) {
  try {
    ids.releaseArtifacts.textContent = `${stage} 단계를 실행하고 있습니다...`;
    const payload = await postJson("/api/workflow-start", { stage });
    ids.releaseArtifacts.textContent = pretty(payload);
    if (payload?.error) {
      return;
    }
    await refreshJobs();
    await refreshDashboard();
  } catch (error) {
    ids.releaseArtifacts.textContent = `배포 단계 실행 중 문제가 발생했습니다: ${error.message}`;
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
document.getElementById("enable-live-mode").addEventListener("click", () => toggleLiveMode(true));
document.getElementById("disable-live-mode").addEventListener("click", () => toggleLiveMode(false));
document.getElementById("run-live-easy-prep").addEventListener("click", runLiveEasyPrep);
document.getElementById("run-live-market-test").addEventListener("click", runLiveMarketTest);
document.getElementById("save-live-config").addEventListener("click", saveLiveConfig);
document.getElementById("run-sync-candles").addEventListener("click", runSyncCandles);
document.getElementById("run-session-report").addEventListener("click", runSessionReport);
document.getElementById("load-session-report").addEventListener("click", loadSessionReport);
document.getElementById("delete-session-report").addEventListener("click", deleteSessionReport);
document.getElementById("prune-session-reports").addEventListener("click", pruneSessionReports);
document.getElementById("save-config").addEventListener("click", saveConfig);
document.getElementById("save-current-preset").addEventListener("click", saveCurrentPreset);
document.getElementById("save-best-preset").addEventListener("click", () => runOptimize(true));
document.getElementById("apply-preset").addEventListener("click", applyPreset);
document.getElementById("save-profile").addEventListener("click", saveProfile);
document.getElementById("load-profile").addEventListener("click", loadProfile);
document.getElementById("delete-profile").addEventListener("click", deleteProfile);
document.getElementById("preview-profile").addEventListener("click", previewProfile);
document.getElementById("start-profile").addEventListener("click", startProfile);
document.getElementById("preview-workflow").addEventListener("click", previewWorkflow);
document.getElementById("start-workflow").addEventListener("click", startWorkflow);
document.getElementById("run-release-recommended").addEventListener("click", () => runReleaseWorkflow(dashboardState.releaseRecommendedStage || "release-pack"));
document.getElementById("run-release-pack").addEventListener("click", () => runReleaseWorkflow("release-pack"));
document.getElementById("run-release-verify").addEventListener("click", () => runReleaseWorkflow("release-verify"));
document.getElementById("run-release-clean").addEventListener("click", () => runReleaseWorkflow("release-clean"));
document.getElementById("refresh-jobs").addEventListener("click", refreshJobs);
document.getElementById("preview-job").addEventListener("click", () => previewJob());
ids.scanCards.addEventListener("click", (event) => {
  const button = event.target.closest("[data-market]");
  if (!button) {
    return;
  }
  setFocusMarket(button.dataset.market || "", ids.scan, "기준 종목을 바꿨습니다:");
  refreshDashboard();
});
ids.selectorCards.addEventListener("click", (event) => {
  const button = event.target.closest("[data-market]");
  if (!button) {
    return;
  }
  setFocusMarket(button.dataset.market || "", ids.selectorSummary, "기준 종목을 바꿨습니다:");
  refreshDashboard();
});
document.getElementById("start-paper-loop").addEventListener("click", () => startJob("paper-loop"));
document.getElementById("stop-paper-loop").addEventListener("click", () => stopJob("paper-loop"));
document.getElementById("start-paper-selector").addEventListener("click", () => startJob("paper-selector"));
document.getElementById("stop-paper-selector").addEventListener("click", () => stopJob("paper-selector"));
document.getElementById("start-live-selector").addEventListener("click", () => startJob("live-selector"));
document.getElementById("stop-live-selector").addEventListener("click", () => stopJob("live-selector"));
document.getElementById("start-live-daemon").addEventListener("click", () => startJob("live-daemon"));
document.getElementById("stop-live-daemon").addEventListener("click", () => stopJob("live-daemon"));
document.getElementById("start-live-supervisor").addEventListener("click", () => startJob("live-supervisor"));
document.getElementById("stop-live-supervisor").addEventListener("click", () => stopJob("live-supervisor"));
document.getElementById("stop-all-jobs").addEventListener("click", stopAllJobs);
document.getElementById("cleanup-jobs").addEventListener("click", cleanupJobs);
ids.refreshSeconds.addEventListener("change", resetAutoRefresh);

renderScanCards(null);
renderSelectorCards(null);
renderPresets(null);
renderProfiles(null);
renderCompletionWorkflow(null);
renderReleaseArtifacts(null);
renderChecklist(null);
renderChart(ids.selectorActiveChart, ids.selectorActiveChartMeta, null);
refreshDashboard();
resetAutoRefresh();
