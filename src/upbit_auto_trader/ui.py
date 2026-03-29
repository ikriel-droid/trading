import json
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .backtest import Backtester
from .brokers.upbit import UpbitBroker
from .config import load_config
from .datafeed import load_csv_candles
from .datafeed import merge_candles, upbit_candles_to_internal, write_csv_candles
from .doctor import build_doctor_report
from .jobs import (
    BackgroundJobManager,
    build_live_daemon_command,
    build_live_supervisor_command,
    build_paper_loop_command,
    build_paper_selector_command,
    cleanup_job_artifacts,
)
from .optimizer import run_grid_search
from .profiles import (
    delete_operator_profile,
    default_profile_dir,
    list_operator_profiles,
    load_operator_profile,
    record_operator_profile_start,
    save_operator_profile,
)
from .presets import (
    apply_strategy_preset,
    default_preset_dir,
    list_strategy_presets,
    save_current_strategy_preset,
    save_grid_search_best_preset,
)
from .reporting import DEFAULT_REPORT_KEEP_LATEST, default_reports_dir, write_runtime_report
from .reporting import delete_session_report, list_session_reports, load_session_report, prune_session_reports
from .runtime import TradingRuntime
from .scanner import MarketScanner
from .strategy import ProfessionalCryptoStrategy


WEBUI_DIR = Path(__file__).with_name("webui")
JOB_MANAGER = BackgroundJobManager()
WORKFLOW_SCRIPT_CMD = "complete_remaining.cmd"
EDITABLE_CONFIG_FIELDS = {
    "strategy.buy_threshold": float,
    "strategy.sell_threshold": float,
    "strategy.min_adx": float,
    "strategy.min_bollinger_width_fraction": float,
    "strategy.volume_spike_multiplier": float,
    "runtime.poll_seconds": float,
    "selector.max_markets": int,
}
ALERT_HEADLINES = {
    "blocked": "Blocked Entry",
    "buy": "Paper Buy",
    "sell": "Paper Sell",
    "buy_submitted": "Order Submitted",
    "buy_fill": "Buy Fill",
    "sell_fill": "Sell Fill",
    "myorder_done": "Order Update",
    "pending_order_cancel_requested": "Cancel Requested",
    "myasset_sync": "Asset Sync",
}
ALERT_LEVELS = {
    "error": 0,
    "warning": 1,
    "success": 2,
    "info": 3,
}
JOURNAL_ALERT_TYPES = {
    "blocked",
    "buy",
    "sell",
    "buy_submitted",
    "buy_fill",
    "sell_fill",
    "myorder_done",
    "pending_order_cancel_requested",
}
NON_BLOCKING_PREFLIGHT_ISSUES = {"discord_webhook_not_configured"}
COMPLETION_WORKFLOW_STAGES = [
    {
        "stage": "verify",
        "label": "Verify",
        "description": "compileall, node --check, unittest",
        "starts_jobs": False,
    },
    {
        "stage": "paper-preflight",
        "label": "Paper Preflight",
        "description": "doctor, save paper profile, preview paper launch",
        "starts_jobs": False,
    },
    {
        "stage": "paper-report",
        "label": "Paper Report",
        "description": "export the current paper session report",
        "starts_jobs": False,
    },
    {
        "stage": "live-preflight",
        "label": "Live Preflight",
        "description": "doctor, save live profile, preview live blockers",
        "starts_jobs": False,
    },
    {
        "stage": "release-pack",
        "label": "Release Pack",
        "description": "build a release pack zip with support bundle included",
        "starts_jobs": False,
    },
    {
        "stage": "release-verify",
        "label": "Release Verify",
        "description": "verify the release pack manifest, zip, and support bundle checksums",
        "starts_jobs": False,
    },
    {
        "stage": "release-clean",
        "label": "Release Clean",
        "description": "remove generated release pack artifacts",
        "starts_jobs": False,
    },
    {
        "stage": "status",
        "label": "Status",
        "description": "list profiles, reports, and job history",
        "starts_jobs": False,
    },
    {
        "stage": "all-safe",
        "label": "All Safe",
        "description": "run verify, paper preflight, paper start, report, status, release pack, and release verify",
        "starts_jobs": True,
    },
    {
        "stage": "roadmap",
        "label": "Roadmap",
        "description": "print the remaining completion roadmap",
        "starts_jobs": False,
    },
]
COMPLETION_WORKFLOW_STAGE_MAP = {item["stage"]: item for item in COMPLETION_WORKFLOW_STAGES}


def _default_selector_state_path(config_path: str) -> str:
    return str(Path(config_path).resolve().parent / "data" / "selector-state-ui.json")


def _default_release_pack_directory(config_path: str) -> str:
    return str(_project_root(config_path) / "dist" / "upbit-control-room-release-pack")


def _default_release_pack_zip_path(config_path: str) -> str:
    return str(_project_root(config_path) / "dist" / "upbit-control-room-release-pack.zip")


def _build_release_pack_status(config_path: str) -> Dict[str, Any]:
    pack_directory = Path(_default_release_pack_directory(config_path))
    zip_path = Path(_default_release_pack_zip_path(config_path))
    manifest_path = pack_directory / "release-pack-manifest.json"
    support_zip_path = pack_directory / "support-bundle.zip"

    pack_exists = pack_directory.exists()
    zip_exists = zip_path.exists()
    manifest_exists = manifest_path.exists()
    support_zip_exists = support_zip_path.exists()

    if pack_exists and zip_exists and manifest_exists and support_zip_exists:
        status = "ready"
    elif pack_exists or zip_exists:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "pack_directory": str(pack_directory),
        "zip_path": str(zip_path),
        "manifest_path": str(manifest_path),
        "support_zip_path": str(support_zip_path),
        "pack_exists": pack_exists,
        "zip_exists": zip_exists,
        "manifest_exists": manifest_exists,
        "support_zip_exists": support_zip_exists,
    }


def _preflight_blocking_issues(report: Dict[str, Any]) -> list[str]:
    issues = []
    upbit = report.get("upbit", {})
    issues.extend(str(item) for item in upbit.get("public_issues", []))
    issues.extend(str(item) for item in upbit.get("private_issues", []))

    state_report = report.get("state", {})
    if state_report.get("path"):
        if not (state_report.get("exists") or state_report.get("backup_exists")):
            issues.append("state_missing")
        elif not state_report.get("load_ok"):
            issues.append("state_unreadable")

    deduped = []
    seen = set()
    for issue in issues:
        if issue in NON_BLOCKING_PREFLIGHT_ISSUES or issue in seen:
            continue
        seen.add(issue)
        deduped.append(issue)
    return deduped


def _resolve_selector_state_path(config_path: str, selector_state_path: Optional[str]) -> str:
    return selector_state_path or _default_selector_state_path(config_path)


def _project_root(config_path: str) -> Path:
    return Path(config_path).resolve().parent


def _resolve_project_path(config_path: str, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(_project_root(config_path) / path)


def _resolve_report_keep_latest(value: Optional[int]) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = 0
    return parsed if parsed > 0 else DEFAULT_REPORT_KEEP_LATEST


def _completion_workflow_script_path(config_path: str) -> str:
    return str(_project_root(config_path) / WORKFLOW_SCRIPT_CMD)


def _validate_completion_workflow_stage(stage: str) -> Dict[str, Any]:
    normalized = str(stage or "").strip()
    if normalized in COMPLETION_WORKFLOW_STAGE_MAP:
        return COMPLETION_WORKFLOW_STAGE_MAP[normalized]
    return {}


def _override_market(config: Any, market: Optional[str]) -> Any:
    if market:
        config.market = market
        if hasattr(config, "upbit"):
            config.upbit.market = market
    return config


def _default_market_csv_path(config_path: str, market: str, candle_unit: int) -> str:
    filename = "{0}_{1}m.csv".format(market.lower().replace("-", "_"), candle_unit)
    return str(_project_root(config_path) / "data" / filename)


def _load_raw_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_raw_config(config_path: str, payload: Dict[str, Any]) -> None:
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _get_nested_value(payload: Dict[str, Any], dotted_path: str) -> Any:
    current = payload
    parts = dotted_path.split(".")
    for part in parts:
        current = current[part]
    return current


def _set_nested_value(payload: Dict[str, Any], dotted_path: str, value: Any) -> None:
    current = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def load_editable_config(config_path: str) -> Dict[str, Any]:
    payload = _load_raw_config(config_path)
    return {
        field_name: _get_nested_value(payload, field_name)
        for field_name in EDITABLE_CONFIG_FIELDS
    }


def update_editable_config(config_path: str, values: Dict[str, Any]) -> Dict[str, Any]:
    payload = _load_raw_config(config_path)
    updated = {}
    for field_name, caster in EDITABLE_CONFIG_FIELDS.items():
        if field_name not in values:
            continue
        typed_value = caster(values[field_name])
        _set_nested_value(payload, field_name, typed_value)
        updated[field_name] = typed_value
    _save_raw_config(config_path, payload)
    return {
        "config_path": config_path,
        "updated": updated,
        "current": load_editable_config(config_path),
    }


def _load_runtime_for_dashboard(config_path: str, state_path: Optional[str], mode: str) -> Optional[TradingRuntime]:
    if not state_path:
        return None

    resolved_state_path = _resolve_project_path(config_path, state_path)
    if not Path(resolved_state_path).exists():
        return None

    config = load_config(config_path)
    runtime = TradingRuntime(config=config, mode="paper", state_path=resolved_state_path)
    state = runtime._load_state()  # noqa: SLF001
    if state is None:
        return None
    runtime.state = state
    runtime.mode = mode
    return runtime


def load_runtime_summary(config_path: str, state_path: Optional[str], mode: str) -> Optional[Dict[str, Any]]:
    runtime = _load_runtime_for_dashboard(config_path, state_path, mode)
    if runtime is None:
        return None
    return runtime.summary()


def _serialize_closed_trade(trade: Any) -> Dict[str, Any]:
    return {
        "market": trade.market,
        "entry_timestamp": trade.entry_timestamp,
        "exit_timestamp": trade.exit_timestamp,
        "entry_price": round(trade.entry_price, 8),
        "exit_price": round(trade.exit_price, 8),
        "quantity": round(trade.quantity, 8),
        "gross_pnl": round(trade.gross_pnl, 8),
        "net_pnl": round(trade.net_pnl, 8),
        "return_pct": round(trade.return_pct, 4),
        "exit_reason": trade.exit_reason,
    }


def _build_recent_activity(runtime: Optional[TradingRuntime]) -> Dict[str, Any]:
    if runtime is None or runtime.state is None:
        return {
            "recent_events": [],
            "recent_trades": [],
        }

    recent_trades = [_serialize_closed_trade(item) for item in runtime.state.closed_trades[-10:]]
    recent_trades.reverse()
    recent_events = list(runtime.state.events[-20:])
    recent_events.reverse()
    return {
        "recent_events": recent_events,
        "recent_trades": recent_trades,
    }


def _extract_timestamp_from_event(message: str) -> str:
    if not message:
        return ""
    first_token = message.strip().split(" ", 1)[0]
    if "T" in first_token and ":" in first_token:
        return first_token
    return ""


def _alert_headline(message: str, event_type: str = "") -> str:
    if event_type in ALERT_HEADLINES:
        return ALERT_HEADLINES[event_type]

    normalized = message.upper()
    if "BLOCKED" in normalized:
        return "Blocked Entry"
    if "BUY_FILL" in normalized:
        return "Buy Fill"
    if "SELL_FILL" in normalized:
        return "Sell Fill"
    if "ORDER_SUBMITTED" in normalized:
        return "Order Submitted"
    if "CANCEL" in normalized:
        return "Cancel Requested"
    if "WARNING" in normalized:
        return "Warning"
    if "NOTICE" in normalized:
        return "Notice"
    if "PAPER BUY" in normalized:
        return "Paper Buy"
    if "PAPER SELL" in normalized:
        return "Paper Sell"
    return "Runtime Event"


def _alert_level(message: str, event_type: str = "") -> str:
    normalized = "{0} {1}".format(event_type, message).lower()
    if "error" in normalized or "failed" in normalized:
        return "error"
    if any(keyword in normalized for keyword in ("warning", "blocked", "mismatch", "cancel", "missing")):
        return "warning"
    if any(keyword in normalized for keyword in ("buy_fill", "sell_fill", "paper buy", "paper sell")):
        return "success"
    return "info"


def _append_alert_item(items: list[Dict[str, Any]], seen: set[str], payload: Dict[str, Any]) -> None:
    dedupe_key = "{0}|{1}|{2}".format(
        payload.get("timestamp", ""),
        payload.get("market", ""),
        payload.get("headline", ""),
    )
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)
    items.append(payload)


def _event_to_alert(message: str, source: str, market: str) -> Dict[str, Any]:
    return {
        "source": source,
        "level": _alert_level(message),
        "headline": _alert_headline(message),
        "message": message,
        "market": market,
        "timestamp": _extract_timestamp_from_event(message),
    }


def _journal_path(config_path: str, config: Any) -> str:
    if not config.runtime.journal_path:
        return ""
    return _resolve_project_path(config_path, config.runtime.journal_path)


def _load_recent_journal_records(config_path: str, config: Any, limit: int = 20) -> list[Dict[str, Any]]:
    journal_path = _journal_path(config_path, config)
    if not journal_path or not Path(journal_path).exists():
        return []

    with open(journal_path, "r", encoding="utf-8", errors="replace") as handle:
        lines = list(deque(handle, maxlen=limit))

    records = []
    for raw_line in reversed(lines):
        line = raw_line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"event_type": "journal_line", "message": line})
    return records


def _journal_message(record: Dict[str, Any]) -> str:
    event_type = str(record.get("event_type", ""))
    market = str(record.get("market", ""))
    if event_type == "blocked":
        return "Blocked {0} reason={1}".format(market, record.get("reason", "unknown"))
    if event_type == "buy":
        return "Paper buy {0} qty={1} price={2}".format(market, record.get("quantity", 0), record.get("price", 0))
    if event_type == "sell":
        return "Paper sell {0} qty={1} price={2} pnl={3}".format(
            market,
            record.get("quantity", 0),
            record.get("price", 0),
            record.get("pnl", 0),
        )
    if event_type == "buy_submitted":
        return "Order submitted {0} uuid={1} budget={2}".format(
            market,
            record.get("uuid", ""),
            record.get("budget", 0),
        )
    if event_type == "buy_fill":
        return "Buy fill {0} qty={1} price={2}".format(
            market,
            record.get("quantity", 0),
            record.get("price", 0),
        )
    if event_type == "sell_fill":
        return "Sell fill {0} qty={1} price={2} pnl={3}".format(
            market,
            record.get("quantity", 0),
            record.get("price", 0),
            record.get("pnl", 0),
        )
    if event_type == "myorder_done":
        return "Order update {0} side={1} state={2}".format(
            market,
            record.get("side", ""),
            record.get("state", ""),
        )
    if event_type == "pending_order_cancel_requested":
        return "Cancel requested {0} uuid={1} age_bars={2}".format(
            market,
            record.get("uuid", ""),
            record.get("age_bars", 0),
        )
    if event_type == "myasset_sync":
        return "Asset sync {0} quote_balance={1} base_total={2}".format(
            market,
            record.get("quote_balance", 0),
            record.get("base_total", 0),
        )
    return str(record.get("message") or json.dumps(record, ensure_ascii=False))


def _journal_record_to_alert(record: Dict[str, Any]) -> Dict[str, Any]:
    event_type = str(record.get("event_type", ""))
    message = _journal_message(record)
    return {
        "source": "journal",
        "level": _alert_level(message, event_type=event_type),
        "headline": _alert_headline(message, event_type=event_type),
        "message": message,
        "market": str(record.get("market", "")),
        "timestamp": str(record.get("timestamp") or record.get("saved_at") or ""),
    }


def _job_to_alert(job: Dict[str, Any]) -> Dict[str, Any]:
    running = bool(job.get("running"))
    returncode = job.get("returncode")
    timestamp = ""
    started_at = job.get("started_at")
    if isinstance(started_at, (int, float)):
        timestamp = datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat()

    if running and str(job.get("heartbeat_status", "")) in {"missing", "stale"}:
        heartbeat_status = str(job.get("heartbeat_status", ""))
        heartbeat = job.get("heartbeat") or {}
        heartbeat_age = job.get("heartbeat_age_seconds")
        age_text = "{0:.1f}s".format(float(heartbeat_age)) if isinstance(heartbeat_age, (int, float)) else "unknown"
        phase = str(heartbeat.get("phase", "") or "unknown")
        return {
            "source": "job",
            "level": "warning",
            "headline": "Job Heartbeat {0}".format("Missing" if heartbeat_status == "missing" else "Stale"),
            "message": "{0} heartbeat={1} age={2} phase={3}".format(
                job.get("name", ""),
                heartbeat_status,
                age_text,
                phase,
            ),
            "market": "",
            "timestamp": timestamp,
        }

    if running:
        return {
            "source": "job",
            "level": "info",
            "headline": "Job Running",
            "message": "{0} active pid={1}".format(job.get("name", ""), job.get("pid", "")),
            "market": "",
            "timestamp": timestamp,
        }

    if returncode not in (None, 0):
        return {
            "source": "job",
            "level": "error",
            "headline": "Job Failed",
            "message": "{0} exited rc={1}".format(job.get("name", ""), returncode),
            "market": "",
            "timestamp": timestamp,
        }

    return {
        "source": "job",
        "level": "warning",
        "headline": "Job Stopped",
        "message": "{0} is not running".format(job.get("name", "")),
        "market": "",
        "timestamp": timestamp,
    }


def _job_report_to_alert(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    report = job.get("last_report") or {}
    if not isinstance(report, dict) or not report:
        return None

    timestamp = str(report.get("generated_at", ""))
    if report.get("error"):
        return {
            "source": "report",
            "level": "warning",
            "headline": "Session Report Failed",
            "message": "{0} report failed: {1}".format(job.get("name", ""), report.get("error", "")),
            "market": "",
            "timestamp": timestamp,
        }

    if report.get("json_path"):
        return {
            "source": "report",
            "level": "success",
            "headline": "Session Report Ready",
            "message": "{0} report saved: {1}".format(job.get("name", ""), report.get("json_path", "")),
            "market": str(report.get("summary", {}).get("market", "")),
            "timestamp": timestamp,
        }

    return None


def _build_alert_feed(
    config_path: str,
    config: Any,
    runtime: Optional[TradingRuntime],
    selector_summary: Dict[str, Any],
    jobs: list[Dict[str, Any]],
    broker_readiness: Dict[str, Any],
    mode: str,
    limit: int = 14,
) -> Dict[str, Any]:
    items: list[Dict[str, Any]] = []
    seen: set[str] = set()

    for job in jobs:
        _append_alert_item(items, seen, _job_to_alert(job))
        report_alert = _job_report_to_alert(job)
        if report_alert is not None:
            _append_alert_item(items, seen, report_alert)

    live_context = mode == "live" or any(
        job.get("kind", "").startswith("live") or job.get("name", "").startswith("live")
        for job in jobs
    )
    if live_context and not broker_readiness.get("private_ready", False):
        _append_alert_item(
            items,
            seen,
            {
                "source": "broker",
                "level": "warning",
                "headline": "Live Not Ready",
                "message": "private trading blocked: {0}".format(
                    ", ".join(broker_readiness.get("private_issues", [])) or "unknown"
                ),
                "market": config.market,
                "timestamp": "",
            },
        )

    if runtime is not None and runtime.state is not None:
        for event in reversed(runtime.state.events[-10:]):
            _append_alert_item(items, seen, _event_to_alert(event, "runtime", runtime.state.market))

    active_market = str(selector_summary.get("active_market", ""))
    selector_events = selector_summary.get("active_market_activity", {}).get("recent_events", [])
    for event in selector_events[:6]:
        _append_alert_item(items, seen, _event_to_alert(str(event), "selector", active_market))

    for record in _load_recent_journal_records(config_path, config, limit=10):
        if str(record.get("event_type", "")) not in JOURNAL_ALERT_TYPES:
            continue
        _append_alert_item(items, seen, _journal_record_to_alert(record))

    counts = {level: 0 for level in ALERT_LEVELS}
    for item in items:
        counts[item["level"]] = counts.get(item["level"], 0) + 1

    items.sort(
        key=lambda item: (
            ALERT_LEVELS.get(str(item.get("level", "info")), 99),
            "" if item.get("timestamp") else "Z",
            str(item.get("timestamp", "")),
        )
    )

    return {
        "summary": {
            **counts,
            "requires_attention": counts["error"] + counts["warning"],
            "journal_path": _journal_path(config_path, config),
        },
        "items": items[:limit],
    }


def _build_job_health_summary(
    jobs: list[Dict[str, Any]],
    job_history: list[Dict[str, Any]],
    limit: int = 10,
) -> Dict[str, Any]:
    summary = {
        "total": len(jobs),
        "running": 0,
        "healthy": 0,
        "stale": 0,
        "missing": 0,
        "unknown": 0,
        "failed": 0,
        "stopped": 0,
        "auto_restart": 0,
        "recent_failures": 0,
        "requires_attention": 0,
    }
    items: list[Dict[str, Any]] = []

    for record in job_history:
        status = str(record.get("status", ""))
        if status in {"failed", "retrying"}:
            summary["recent_failures"] += 1

    for job in jobs:
        running = bool(job.get("running"))
        heartbeat_status = str(job.get("heartbeat_status", "")).strip() or "unknown"
        heartbeat = job.get("heartbeat") or {}
        item = {
            "name": str(job.get("name", "")),
            "kind": str(job.get("kind", "")),
            "running": running,
            "heartbeat_status": heartbeat_status,
            "heartbeat_phase": str(heartbeat.get("phase", "")),
            "heartbeat_age_seconds": job.get("heartbeat_age_seconds"),
            "returncode": job.get("returncode"),
            "auto_restart": bool(job.get("auto_restart", False)),
            "restart_count": int(job.get("restart_count", 0) or 0),
            "termination_reason": str(job.get("termination_reason", "")),
        }
        if item["auto_restart"]:
            summary["auto_restart"] += 1

        if running:
            summary["running"] += 1
            if heartbeat_status == "healthy":
                summary["healthy"] += 1
                item["level"] = "success"
                item["status"] = "healthy"
            elif heartbeat_status == "stale":
                summary["stale"] += 1
                summary["requires_attention"] += 1
                item["level"] = "warning"
                item["status"] = "stale"
            elif heartbeat_status == "missing":
                summary["missing"] += 1
                summary["requires_attention"] += 1
                item["level"] = "warning"
                item["status"] = "missing"
            else:
                summary["unknown"] += 1
                summary["requires_attention"] += 1
                item["level"] = "warning"
                item["status"] = heartbeat_status
        else:
            returncode = job.get("returncode")
            if returncode not in (None, 0):
                summary["failed"] += 1
                summary["requires_attention"] += 1
                item["level"] = "error"
                item["status"] = "failed"
            else:
                summary["stopped"] += 1
                item["level"] = "info"
                item["status"] = "stopped"

        items.append(item)

    items.sort(
        key=lambda item: (
            {"warning": 0, "error": 1, "success": 2, "info": 3}.get(str(item.get("level", "info")), 9),
            str(item.get("name", "")),
        )
    )
    return {
        "summary": summary,
        "items": items[:limit],
    }


def _checklist_item(
    key: str,
    status: str,
    title: str,
    detail: str,
    action: str = "",
) -> Dict[str, Any]:
    return {
        "key": key,
        "status": status,
        "title": title,
        "detail": detail,
        "action": action,
    }


def _build_operator_checklist(
    config_path: str,
    config: Any,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    broker_readiness: Dict[str, Any],
    job_health: Dict[str, Any],
) -> Dict[str, Any]:
    resolved_selector_state_path = _resolve_project_path(config_path, selector_state_path) if selector_state_path else None
    resolved_state_path = _resolve_project_path(config_path, state_path) if state_path else None
    resolved_live_state_path = _resolve_project_path(config_path, "data/live-state.json")
    workflow_script_path = _completion_workflow_script_path(config_path)
    release_pack_status = _build_release_pack_status(config_path)
    live_report = build_doctor_report(
        config_path=config_path,
        config=config,
        state_path=resolved_live_state_path,
        selector_state_path=resolved_selector_state_path,
    )

    items: list[Dict[str, Any]] = []
    next_steps: list[str] = []

    workflow_ok = Path(workflow_script_path).exists()
    items.append(
        _checklist_item(
            key="workflow_script",
            status="success" if workflow_ok else "error",
            title="Completion workflow wrapper",
            detail=workflow_script_path if workflow_ok else "missing completion workflow wrapper",
            action="Run .\\complete_remaining.cmd all-safe" if workflow_ok else "restore complete_remaining.cmd",
        )
    )
    if not workflow_ok:
        next_steps.append("complete_remaining.cmd 를 복구한 뒤 all-safe workflow를 다시 실행하세요.")

    release_detail = "release pack missing"
    release_action = "Run .\\complete_remaining.cmd release-pack"
    release_status = "warning"
    if release_pack_status["status"] == "ready":
        release_detail = "zip, manifest, and support bundle are ready"
        release_action = "Run .\\complete_remaining.cmd release-verify"
        release_status = "success"
    elif release_pack_status["status"] == "partial":
        release_detail = "release pack artifacts are present but incomplete"
        release_action = "Run .\\complete_remaining.cmd release-verify or rebuild the pack"
        release_status = "warning"
    items.append(
        _checklist_item(
            key="release_artifacts",
            status=release_status,
            title="Release artifacts",
            detail=release_detail,
            action=release_action,
        )
    )
    if release_status != "success":
        next_steps.append("배포용 산출물을 맞추려면 release-pack 후 release-verify를 실행하세요.")

    current_state_exists = bool(resolved_state_path and Path(resolved_state_path).exists())
    current_state_ready = current_state_exists
    items.append(
        _checklist_item(
            key="paper_state",
            status="success" if current_state_ready else "warning",
            title="Current paper state",
            detail=resolved_state_path or "state path not selected",
            action="paper-preflight 또는 paper-loop 로 상태 파일을 준비하세요." if not current_state_ready else "paper state loaded",
        )
    )
    if not current_state_ready:
        next_steps.append("paper 상태 파일을 준비하려면 paper-preflight 또는 paper-loop 를 먼저 실행하세요.")

    job_health_summary = job_health.get("summary", {}) if isinstance(job_health, dict) else {}
    attention_count = int(job_health_summary.get("requires_attention", 0) or 0)
    items.append(
        _checklist_item(
            key="managed_jobs",
            status="success" if attention_count == 0 else "warning",
            title="Managed jobs",
            detail="attention={0}, running={1}".format(
                attention_count,
                int(job_health_summary.get("running", 0) or 0),
            ),
            action="Job Health 패널에서 stale/failed job 을 정리하세요." if attention_count else "job health clear",
        )
    )
    if attention_count:
        next_steps.append("Job Health 경고가 있으면 Emergency Stop All 또는 Clean Stopped Jobs 로 먼저 정리하세요.")

    private_ready = bool(broker_readiness.get("private_ready", False))
    private_issues = [str(item) for item in broker_readiness.get("private_issues", [])]
    items.append(
        _checklist_item(
            key="live_api",
            status="success" if private_ready else "error",
            title="Live API readiness",
            detail=", ".join(private_issues) if private_issues else "private API ready",
            action="Upbit access/secret key 와 live 설정을 확인하세요." if not private_ready else "private API ready",
        )
    )
    if not private_ready:
        next_steps.append("Upbit access/secret key 를 .env 또는 config 에 넣고 doctor 를 다시 실행하세요.")

    live_enabled = bool(getattr(config.upbit, "live_enabled", False))
    items.append(
        _checklist_item(
            key="live_enabled",
            status="success" if live_enabled else "warning",
            title="Live trading switch",
            detail="upbit.live_enabled={0}".format(str(live_enabled).lower()),
            action="실거래 직전까지는 false 로 두고, 준비가 끝나면 true 로 바꾸세요." if not live_enabled else "live switch enabled",
        )
    )

    live_state_report = live_report.get("state", {}) if isinstance(live_report, dict) else {}
    live_state_ok = bool(live_state_report.get("load_ok"))
    live_state_exists = bool(live_state_report.get("exists"))
    live_state_detail = str(live_state_report.get("path", resolved_live_state_path))
    if not live_state_exists:
        live_state_detail = "{0} (missing)".format(live_state_detail)
    elif not live_state_ok:
        live_state_detail = "{0} (unreadable)".format(live_state_detail)
    items.append(
        _checklist_item(
            key="live_state",
            status="success" if live_state_ok else "error",
            title="Live state file",
            detail=live_state_detail,
            action="live-state.json 을 준비하거나 live-preflight 로 상태를 확인하세요." if not live_state_ok else "live state ready",
        )
    )
    if not live_state_ok:
        next_steps.append("실거래 전에 data/live-state.json 을 준비하고 live-preflight 결과를 확인하세요.")

    notifications = live_report.get("notifications", {}) if isinstance(live_report, dict) else {}
    discord_configured = bool(notifications.get("discord_webhook_configured"))
    items.append(
        _checklist_item(
            key="discord_notifications",
            status="success" if discord_configured else "warning",
            title="Discord notifications",
            detail="configured" if discord_configured else "discord webhook not configured",
            action="선택 사항이지만 체결/에러 알림을 받으려면 webhook 을 설정하세요." if not discord_configured else "notifications ready",
        )
    )
    if not discord_configured:
        next_steps.append("선택 사항이지만 Discord webhook 을 넣어두면 체결과 에러를 바로 받을 수 있습니다.")

    summary = {
        "success": sum(1 for item in items if item["status"] == "success"),
        "warning": sum(1 for item in items if item["status"] == "warning"),
        "error": sum(1 for item in items if item["status"] == "error"),
        "info": sum(1 for item in items if item["status"] == "info"),
    }
    summary["requires_attention"] = summary["warning"] + summary["error"]
    if summary["error"] == 0 and summary["warning"] == 0:
        summary["overall_status"] = "ready"
    elif summary["error"] == 0:
        summary["overall_status"] = "paper_ready"
    else:
        summary["overall_status"] = "needs_setup"

    deduped_steps = []
    seen_steps = set()
    for step in next_steps:
        if step in seen_steps:
            continue
        seen_steps.add(step)
        deduped_steps.append(step)

    return {
        "summary": summary,
        "items": items,
        "next_steps": deduped_steps[:5],
    }


def _chart_points_from_candles(candles: list[Any], limit: int = 120) -> list[Dict[str, Any]]:
    return [
        {
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles[-limit:]
    ]


def _build_chart_markers(chart_points: list[Dict[str, Any]], runtime: Optional[TradingRuntime]) -> list[Dict[str, Any]]:
    if runtime is None or runtime.state is None:
        return []

    visible_timestamps = {point["timestamp"] for point in chart_points}
    markers = []

    for trade in runtime.state.closed_trades[-40:]:
        if trade.entry_timestamp in visible_timestamps:
            markers.append(
                {
                    "timestamp": trade.entry_timestamp,
                    "price": round(trade.entry_price, 8),
                    "side": "buy",
                    "kind": "entry",
                    "label": "B",
                    "note": "trade entry",
                }
            )
        if trade.exit_timestamp in visible_timestamps:
            markers.append(
                {
                    "timestamp": trade.exit_timestamp,
                    "price": round(trade.exit_price, 8),
                    "side": "sell",
                    "kind": "exit",
                    "label": "S",
                    "note": trade.exit_reason,
                    "net_pnl": round(trade.net_pnl, 8),
                }
            )

    if runtime.state.position is not None and runtime.state.position.entry_timestamp in visible_timestamps:
        markers.append(
            {
                "timestamp": runtime.state.position.entry_timestamp,
                "price": round(runtime.state.position.entry_price, 8),
                "side": "buy",
                "kind": "open_position",
                "label": "O",
                "note": "open position",
            }
        )

    markers.sort(key=lambda item: (item["timestamp"], item["kind"], item["price"]))
    return markers


def _build_runtime_chart(runtime: Optional[TradingRuntime]) -> Dict[str, Any]:
    if runtime is None or runtime.state is None:
        return {"points": [], "markers": []}
    chart_points = _chart_points_from_candles(runtime.state.history)
    return {
        "points": chart_points,
        "markers": _build_chart_markers(chart_points, runtime),
    }


def _selector_market_state_path(config_path: str, selector_state_path: str, market: str) -> str:
    config = load_config(config_path)
    project_root = Path(config_path).resolve().parent
    states_dir = Path(config.selector.states_dir)
    if not states_dir.is_absolute():
        states_dir = project_root / states_dir
    return str(states_dir / (market.replace("-", "_") + ".json"))


def load_selector_summary(config_path: str, selector_state_path: Optional[str]) -> Dict[str, Any]:
    resolved_state_path = _resolve_selector_state_path(config_path, selector_state_path)
    if not Path(resolved_state_path).exists():
        return {
            "selector_state_path": resolved_state_path,
            "exists": False,
            "active_market": "",
            "active_market_state_path": "",
            "cycle_count": 0,
            "last_selected_market": "",
            "last_selected_score": 0.0,
            "last_scan_timestamp": "",
            "last_scan_results": [],
            "active_market_summary": None,
            "active_market_activity": {"recent_events": [], "recent_trades": []},
            "active_market_chart": {"points": [], "markers": []},
        }

    with open(resolved_state_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    active_market = payload.get("active_market", "")
    active_market_summary = None
    if active_market:
        active_state_path = _selector_market_state_path(config_path, resolved_state_path, active_market)
        active_runtime = _load_runtime_for_dashboard(config_path, active_state_path, mode="paper")
        active_market_summary = active_runtime.summary() if active_runtime is not None else None
    else:
        active_state_path = ""
        active_runtime = None

    return {
        "selector_state_path": resolved_state_path,
        "exists": True,
        "active_market": active_market,
        "active_market_state_path": active_state_path,
        "cycle_count": int(payload.get("cycle_count", 0)),
        "last_selected_market": payload.get("last_selected_market", ""),
        "last_selected_score": float(payload.get("last_selected_score", 0.0)),
        "last_scan_timestamp": payload.get("last_scan_timestamp", ""),
        "last_scan_results": list(payload.get("last_scan_results", []))[:6],
        "active_market_summary": active_market_summary,
        "active_market_activity": _build_recent_activity(active_runtime),
        "active_market_chart": _build_runtime_chart(active_runtime),
    }


def run_signal_action(config_path: str, csv_path: str, market: Optional[str] = None) -> Dict[str, Any]:
    config = _override_market(load_config(config_path), market)
    candles = load_csv_candles(_resolve_project_path(config_path, csv_path))
    signal = ProfessionalCryptoStrategy(config.strategy).evaluate(candles, None)
    return {
        "market": config.market,
        "action": signal.action.value,
        "score": signal.score,
        "confidence": signal.confidence,
        "reasons": signal.reasons,
        "csv_path": csv_path,
    }


def run_scan_action(
    config_path: str,
    max_markets: int = 10,
    quote_currency: Optional[str] = None,
    broker: Optional[UpbitBroker] = None,
) -> Dict[str, Any]:
    config = load_config(config_path)
    if quote_currency:
        config.selector.quote_currency = quote_currency
    config.selector.max_markets = max(1, max_markets)
    broker = broker or UpbitBroker(config.upbit)
    scanner = MarketScanner(config, broker)
    markets = scanner.discover_markets()
    results = scanner.scan_markets(markets)
    return {
        "market": config.market,
        "quote_currency": config.selector.quote_currency,
        "scanned_market_count": len(markets),
        "scan_results": [
            {
                "market": item.market,
                "action": item.action,
                "score": item.score,
                "confidence": item.confidence,
                "reasons": item.reasons,
                "timestamp": item.timestamp,
                "close": item.close,
                "liquidity_24h": item.liquidity_24h,
                "liquidity_ok": item.liquidity_ok,
            }
            for item in results[: max_markets]
        ],
    }


def run_sync_candles_action(
    config_path: str,
    csv_path: str,
    count: Optional[int] = None,
    market: Optional[str] = None,
    broker: Optional[UpbitBroker] = None,
) -> Dict[str, Any]:
    config = load_config(config_path)
    if market:
        config.market = market
        config.upbit.market = market
    resolved_csv_path = _resolve_project_path(config_path, csv_path)
    broker = broker or UpbitBroker(config.upbit)
    fetch_count = count or config.upbit.candle_count
    payload = broker.get_minute_candles(
        market=config.market,
        unit=config.upbit.candle_unit,
        count=fetch_count,
    )
    incoming = upbit_candles_to_internal(payload)
    existing = load_csv_candles(resolved_csv_path) if Path(resolved_csv_path).exists() else []
    keep_rows = max(config.runtime.max_history, len(existing) + len(incoming), fetch_count)
    merged = merge_candles(existing, incoming, max_history=keep_rows)
    write_csv_candles(resolved_csv_path, merged)
    return {
        "market": config.market,
        "csv_path": resolved_csv_path,
        "rows_written": len(merged),
        "first_timestamp": merged[0].timestamp if merged else "",
        "last_timestamp": merged[-1].timestamp if merged else "",
    }


def run_backtest_action(config_path: str, csv_path: str, market: Optional[str] = None) -> Dict[str, Any]:
    config = _override_market(load_config(config_path), market)
    resolved_csv_path = _resolve_project_path(config_path, csv_path)
    candles = load_csv_candles(resolved_csv_path)
    result = Backtester(config).run(candles)
    return {
        "market": config.market,
        "csv_path": resolved_csv_path,
        "final_equity": round(result.final_equity, 2),
        "total_return_pct": round(result.total_return_pct, 4),
        "max_drawdown_pct": round(result.max_drawdown_pct, 4),
        "win_rate_pct": round(result.win_rate_pct, 4),
        "trade_count": len(result.trades),
        "recent_events": result.events[-10:],
    }


def run_optimize_action(
    config_path: str,
    csv_path: str,
    top: int = 5,
    market: Optional[str] = None,
    save_best_preset_name: Optional[str] = None,
) -> Dict[str, Any]:
    config = _override_market(load_config(config_path), market)
    resolved_csv_path = _resolve_project_path(config_path, csv_path)
    candles = load_csv_candles(resolved_csv_path)
    results = run_grid_search(
        config=config,
        candles=candles,
        buy_thresholds=[62.0, 65.0, 68.0],
        sell_thresholds=[35.0, 40.0, 45.0],
        min_adx_values=[16.0, 18.0, 20.0],
        min_bollinger_width_values=[0.012, 0.015, 0.018],
        volume_spike_multipliers=[1.2, 1.3, 1.4],
    )
    saved_preset = None
    if save_best_preset_name and results:
        saved_preset = save_grid_search_best_preset(
            config_path=config_path,
            name=save_best_preset_name,
            result=results[0],
            market=config.market,
            csv_path=resolved_csv_path,
        )
    return {
        "market": config.market,
        "csv_path": resolved_csv_path,
        "tested": len(results),
        "top": [
            {
                "rank": index + 1,
                "buy_threshold": item.buy_threshold,
                "sell_threshold": item.sell_threshold,
                "min_adx": item.min_adx,
                "min_bollinger_width_fraction": item.min_bollinger_width_fraction,
                "volume_spike_multiplier": item.volume_spike_multiplier,
                "final_equity": round(item.final_equity, 2),
                "total_return_pct": round(item.total_return_pct, 4),
                "max_drawdown_pct": round(item.max_drawdown_pct, 4),
                "trade_count": item.trade_count,
            }
            for index, item in enumerate(results[: max(1, top)])
        ],
        "saved_preset": saved_preset,
    }


def run_save_current_preset_action(
    config_path: str,
    preset_name: str,
    csv_path: Optional[str] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    config = _override_market(load_config(config_path), market)
    resolved_csv_path = _resolve_project_path(config_path, csv_path) if csv_path else ""
    return save_current_strategy_preset(
        config_path=config_path,
        name=preset_name,
        market=config.market,
        csv_path=resolved_csv_path,
    )


def run_apply_preset_action(config_path: str, preset_ref: str) -> Dict[str, Any]:
    return apply_strategy_preset(config_path, preset_ref)


def run_save_profile_action(
    config_path: str,
    profile_name: str,
    profile_payload: Dict[str, Any],
    notes: str = "",
) -> Dict[str, Any]:
    return save_operator_profile(
        config_path=config_path,
        name=profile_name,
        profile_payload=profile_payload,
        notes=notes,
    )


def run_load_profile_action(config_path: str, profile_ref: str) -> Dict[str, Any]:
    return load_operator_profile(config_path, profile_ref)


def run_delete_profile_action(config_path: str, profile_ref: str) -> Dict[str, Any]:
    return delete_operator_profile(config_path, profile_ref)


def run_preview_profile_action(config_path: str, profile_ref: str) -> Dict[str, Any]:
    loaded = load_operator_profile(config_path, profile_ref)
    profile = loaded["profile"]
    preview = preview_managed_job(
        config_path=config_path,
        job_type=profile["job_type"],
        state_path=profile["state_path"] or None,
        selector_state_path=profile["selector_state_path"] or None,
        csv_path=profile["csv_path"] or None,
        poll_seconds=profile["poll_seconds"] or None,
        reconcile_every_loops=profile["reconcile_every_loops"] or None,
        reconcile_every=profile["reconcile_every"] or None,
        market=profile["market"] or None,
        quote_currency=profile["quote_currency"] or None,
        max_markets=profile["max_markets"] or None,
        auto_restart=profile["auto_restart"],
        max_restarts=profile["max_restarts"],
        restart_backoff_seconds=profile["restart_backoff_seconds"],
        report_keep_latest=profile["report_keep_latest"] or None,
    )
    return {
        "profile": loaded,
        "job_preview": preview,
    }


def run_start_profile_action(
    config_path: str,
    profile_ref: str,
    job_manager: Optional[BackgroundJobManager] = None,
) -> Dict[str, Any]:
    loaded = load_operator_profile(config_path, profile_ref)
    profile = loaded["profile"]
    preset_applied = None
    if profile["preset"]:
        preset_applied = apply_strategy_preset(config_path, profile["preset"])

    job = start_managed_job(
        config_path=config_path,
        job_type=profile["job_type"],
        state_path=profile["state_path"] or None,
        selector_state_path=profile["selector_state_path"] or None,
        csv_path=profile["csv_path"] or None,
        poll_seconds=profile["poll_seconds"] or None,
        reconcile_every_loops=profile["reconcile_every_loops"] or None,
        reconcile_every=profile["reconcile_every"] or None,
        market=profile["market"] or None,
        quote_currency=profile["quote_currency"] or None,
        max_markets=profile["max_markets"] or None,
        auto_restart=profile["auto_restart"],
        max_restarts=profile["max_restarts"],
        restart_backoff_seconds=profile["restart_backoff_seconds"],
        report_keep_latest=profile["report_keep_latest"] or None,
        job_manager=job_manager,
    )
    if not job.get("error"):
        loaded = record_operator_profile_start(config_path, loaded["path"])
    return {
        "profile": loaded,
        "preset_applied": preset_applied,
        "job": job,
    }


def run_session_report_action(
    config_path: str,
    state_path: str,
    mode: str = "paper",
    output_dir: Optional[str] = None,
    label: str = "",
    keep_latest: Optional[int] = None,
) -> Dict[str, Any]:
    resolved_state_path = _resolve_project_path(config_path, state_path)
    resolved_output_dir = _resolve_project_path(config_path, output_dir) if output_dir else None
    return {
        "reports_dir": default_reports_dir(config_path),
        **write_runtime_report(
            config_path=config_path,
            state_path=resolved_state_path,
            mode=mode,
            output_dir=resolved_output_dir,
            label=label,
            keep_latest=keep_latest,
        ),
    }


def run_show_report_action(
    config_path: str,
    report_ref: str,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_output_dir = _resolve_project_path(config_path, output_dir) if output_dir else None
    return load_session_report(config_path=config_path, report_ref=report_ref, output_dir=resolved_output_dir)


def run_delete_report_action(
    config_path: str,
    report_ref: str,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_output_dir = _resolve_project_path(config_path, output_dir) if output_dir else None
    return delete_session_report(config_path=config_path, report_ref=report_ref, output_dir=resolved_output_dir)


def run_prune_reports_action(
    config_path: str,
    keep: int = 10,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_output_dir = _resolve_project_path(config_path, output_dir) if output_dir else None
    return prune_session_reports(config_path=config_path, keep=keep, output_dir=resolved_output_dir)


def run_live_reconcile_action(
    config_path: str,
    state_path: Optional[str],
    mode: str,
    market: Optional[str] = None,
    broker: Optional[UpbitBroker] = None,
) -> Dict[str, Any]:
    if not state_path:
        return {
            "error": "state file not found",
            "state_path": state_path or "",
        }

    resolved_state_path = _resolve_project_path(config_path, state_path)
    if not Path(resolved_state_path).exists():
        return {
            "error": "state file not found",
            "state_path": resolved_state_path,
        }

    config = _override_market(load_config(config_path), market)
    broker = broker or UpbitBroker(config.upbit)
    runtime = TradingRuntime(config=config, mode="live", state_path=resolved_state_path, broker=broker)
    runtime.bootstrap([])
    return runtime.reconcile_live_snapshot()


def run_doctor_action(
    config_path: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
) -> Dict[str, Any]:
    config = load_config(config_path)
    resolved_state_path = _resolve_project_path(config_path, state_path) if state_path else None
    resolved_selector_state_path = _resolve_project_path(config_path, selector_state_path) if selector_state_path else None
    return build_doctor_report(
        config_path=config_path,
        config=config,
        state_path=resolved_state_path,
        selector_state_path=resolved_selector_state_path,
    )


def preview_completion_workflow_action(config_path: str, stage: str) -> Dict[str, Any]:
    stage_meta = _validate_completion_workflow_stage(stage)
    if not stage_meta:
        return {
            "error": "unsupported_workflow_stage",
            "stage": stage,
            "supported_stages": [item["stage"] for item in COMPLETION_WORKFLOW_STAGES],
        }

    script_path = _completion_workflow_script_path(config_path)
    if not Path(script_path).exists():
        return {
            "error": "workflow_script_missing",
            "stage": stage_meta["stage"],
            "script_path": script_path,
        }

    project_root = str(_project_root(config_path))
    job_name = "workflow-{0}".format(stage_meta["stage"])
    warnings = []
    if stage_meta.get("starts_jobs"):
        warnings.append("starts_managed_jobs")

    return {
        "job_type": "completion-workflow",
        "stage": stage_meta["stage"],
        "label": stage_meta["label"],
        "description": stage_meta["description"],
        "command": ["cmd.exe", "/c", WORKFLOW_SCRIPT_CMD, stage_meta["stage"]],
        "cwd": project_root,
        "script_path": script_path,
        "job_name": job_name,
        "report_on_exit": False,
        "report_keep_latest": None,
        "heartbeat_path": str(Path(project_root) / "data" / "webui-jobs" / "{0}.heartbeat.json".format(job_name)),
        "warnings": warnings,
        "can_start": True,
    }


def start_completion_workflow_action(
    config_path: str,
    stage: str,
    job_manager: Optional[BackgroundJobManager] = None,
) -> Dict[str, Any]:
    preview = preview_completion_workflow_action(config_path, stage)
    if preview.get("error"):
        return preview

    job_manager = job_manager or JOB_MANAGER
    job = job_manager.start_job(
        name=str(preview["job_name"]),
        kind="completion-workflow",
        command=list(preview["command"]),
        cwd=str(preview["cwd"]),
        auto_restart=False,
        max_restarts=0,
        restart_backoff_seconds=0.0,
        report_on_exit=False,
        report_config_path="",
        report_state_path="",
        report_mode="paper",
        report_output_dir="",
        report_label=str(preview["stage"]),
        report_keep_latest=None,
    )
    return {
        "workflow": preview,
        "job": job,
    }


def build_dashboard_payload(
    config_path: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    csv_path: Optional[str],
    mode: str,
    focus_market: Optional[str] = None,
    job_manager: Optional[BackgroundJobManager] = None,
) -> Dict[str, Any]:
    config = _override_market(load_config(config_path), focus_market)
    broker = UpbitBroker(config.upbit)
    job_manager = job_manager or JOB_MANAGER
    runtime = _load_runtime_for_dashboard(config_path, state_path, mode)
    resolved_selector_state_path = _resolve_selector_state_path(config_path, selector_state_path)
    selector_summary = load_selector_summary(config_path, resolved_selector_state_path)
    jobs = job_manager.list_jobs()
    job_history = job_manager.list_history()
    broker_readiness = broker.readiness_report()
    job_health = _build_job_health_summary(jobs, job_history)
    suggested_market_csv_path = _default_market_csv_path(config_path, config.market, config.upbit.candle_unit)
    effective_csv_path = _resolve_project_path(
        config_path,
        csv_path or suggested_market_csv_path,
    )
    payload: Dict[str, Any] = {
        "paths": {
            "config_path": config_path,
            "state_path": state_path or "",
            "selector_state_path": resolved_selector_state_path,
            "csv_path": effective_csv_path,
            "suggested_market_csv_path": suggested_market_csv_path,
            "reports_dir": default_reports_dir(config_path),
        },
        "app": {
            "market": config.market,
            "mode": mode,
            "poll_seconds": config.runtime.poll_seconds,
            "selector_max_markets": config.selector.max_markets,
            "candle_unit": config.upbit.candle_unit,
        },
        "broker_readiness": broker_readiness,
        "state_summary": runtime.summary() if runtime is not None else None,
        "selector_summary": selector_summary,
        "activity": _build_recent_activity(runtime),
        "editable_config": load_editable_config(config_path),
        "strategy_presets": {
            "dir": default_preset_dir(config_path),
            "items": list_strategy_presets(config_path),
        },
        "operator_profiles": {
            "dir": default_profile_dir(config_path),
            "items": list_operator_profiles(config_path),
        },
        "completion_workflow": {
            "script_path": _completion_workflow_script_path(config_path),
            "default_stage": COMPLETION_WORKFLOW_STAGES[0]["stage"],
            "items": COMPLETION_WORKFLOW_STAGES,
        },
        "release_artifacts": _build_release_pack_status(config_path),
        "session_reports": {
            "dir": default_reports_dir(config_path),
            "items": list_session_reports(config_path),
        },
        "jobs": jobs,
        "job_health": job_health,
        "operator_checklist": _build_operator_checklist(
            config_path=config_path,
            config=config,
            state_path=state_path,
            selector_state_path=resolved_selector_state_path,
            broker_readiness=broker_readiness,
            job_health=job_health,
        ),
        "job_history": {
            "items": job_history,
        },
        "alerts": _build_alert_feed(
            config_path=config_path,
            config=config,
            runtime=runtime,
            selector_summary=selector_summary,
            jobs=jobs,
            broker_readiness=broker_readiness,
            mode=mode,
        ),
        "ui_defaults": {
            "refresh_seconds": 5,
            "optimize_top": 5,
            "scan_max_markets": min(10, config.selector.max_markets),
            "quote_currency": config.selector.quote_currency,
            "reconcile_every": 10,
            "job_type": "paper-loop",
            "auto_restart": False,
            "max_restarts": 2,
            "restart_backoff_seconds": 2.0,
            "report_keep_latest": DEFAULT_REPORT_KEEP_LATEST,
        },
    }

    if Path(effective_csv_path).exists():
        candles = load_csv_candles(effective_csv_path)
        chart_points = _chart_points_from_candles(candles)
        payload["csv_info"] = {
            "rows": len(candles),
            "first_timestamp": candles[0].timestamp if candles else "",
            "last_timestamp": candles[-1].timestamp if candles else "",
        }
        payload["chart"] = {
            "points": chart_points,
            "markers": _build_chart_markers(chart_points, runtime),
        }
        payload["latest_signal"] = run_signal_action(config_path, effective_csv_path, market=config.market)
    else:
        payload["csv_info"] = None
        payload["chart"] = {"points": [], "markers": []}
        payload["latest_signal"] = None

    return payload


def start_managed_job(
    config_path: str,
    job_type: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    csv_path: Optional[str],
    poll_seconds: Optional[float],
    reconcile_every_loops: Optional[int],
    reconcile_every: Optional[int],
    market: Optional[str],
    quote_currency: Optional[str],
    max_markets: Optional[int],
    auto_restart: bool,
    max_restarts: int,
    restart_backoff_seconds: float,
    report_keep_latest: Optional[int] = None,
    job_manager: Optional[BackgroundJobManager] = None,
) -> Dict[str, Any]:
    project_root = str(Path(config_path).resolve().parent)
    resolved_selector_state_path = _resolve_selector_state_path(config_path, selector_state_path)
    effective_state_path = state_path or ""
    report_mode = "paper"

    if job_type == "paper-loop":
        effective_state_path = state_path or "data/paper-state-ui.json"
        command = build_paper_loop_command(
            config_path=config_path,
            state_path=effective_state_path,
            warmup_csv=csv_path,
            poll_seconds=poll_seconds,
        )
    elif job_type == "paper-selector":
        command = build_paper_selector_command(
            config_path=config_path,
            selector_state_path=resolved_selector_state_path,
            poll_seconds=poll_seconds,
            quote_currency=quote_currency,
            max_markets=max_markets,
        )
    elif job_type == "live-daemon":
        effective_state_path = state_path or "data/live-state-ui.json"
        command = build_live_daemon_command(
            config_path=config_path,
            state_path=effective_state_path,
            warmup_csv=csv_path,
            poll_seconds=poll_seconds,
            reconcile_every_loops=reconcile_every_loops,
        )
        report_mode = "live"
    elif job_type == "live-supervisor":
        effective_state_path = state_path or "data/live-state-ui.json"
        command = build_live_supervisor_command(
            config_path=config_path,
            state_path=effective_state_path,
            market=market,
            reconcile_every=reconcile_every,
        )
        report_mode = "live"
    else:
        return {"error": "unsupported job type", "job_type": job_type}

    resolved_state_path = _resolve_project_path(config_path, effective_state_path) if effective_state_path else ""
    resolved_selector_state_path = _resolve_project_path(config_path, resolved_selector_state_path) if resolved_selector_state_path else ""

    preview = {
        "job_type": job_type,
        "command": command,
        "cwd": project_root,
        "auto_restart": auto_restart,
        "max_restarts": max_restarts,
        "restart_backoff_seconds": restart_backoff_seconds,
        "report_on_exit": bool(resolved_state_path),
        "report_config_path": str(Path(config_path).resolve()),
        "report_state_path": resolved_state_path,
        "report_mode": report_mode,
        "report_output_dir": default_reports_dir(config_path),
        "report_label": job_type,
        "report_keep_latest": _resolve_report_keep_latest(report_keep_latest),
        "heartbeat_path": str(Path(project_root) / "data" / "webui-jobs" / "{0}.heartbeat.json".format(job_type)),
        "blocking_issues": [],
        "warnings": [],
        "preflight": None,
        "can_start": True,
    }

    if report_mode == "live":
        live_config = _override_market(load_config(config_path), market)
        preflight = build_doctor_report(
            config_path=str(Path(config_path).resolve()),
            config=live_config,
            state_path=resolved_state_path or None,
            selector_state_path=resolved_selector_state_path or None,
        )
        blocking_issues = _preflight_blocking_issues(preflight)
        preview["blocking_issues"] = blocking_issues
        preview["warnings"] = [issue for issue in preflight.get("issues", []) if issue not in blocking_issues]
        preview["preflight"] = preflight
        preview["can_start"] = len(blocking_issues) == 0

    job_manager = job_manager or JOB_MANAGER
    if not preview["can_start"]:
        return {
            "error": "live_preflight_failed",
            **preview,
        }

    return job_manager.start_job(
        name=job_type,
        kind=job_type,
        command=preview["command"],
        cwd=preview["cwd"],
        auto_restart=preview["auto_restart"],
        max_restarts=preview["max_restarts"],
        restart_backoff_seconds=preview["restart_backoff_seconds"],
        report_on_exit=preview["report_on_exit"],
        report_config_path=preview["report_config_path"],
        report_state_path=preview["report_state_path"],
        report_mode=preview["report_mode"],
        report_output_dir=preview["report_output_dir"],
        report_label=preview["report_label"],
        report_keep_latest=preview["report_keep_latest"],
    )


def preview_managed_job(
    config_path: str,
    job_type: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    csv_path: Optional[str],
    poll_seconds: Optional[float],
    reconcile_every_loops: Optional[int],
    reconcile_every: Optional[int],
    market: Optional[str],
    quote_currency: Optional[str],
    max_markets: Optional[int],
    auto_restart: bool,
    max_restarts: int,
    restart_backoff_seconds: float,
    report_keep_latest: Optional[int] = None,
) -> Dict[str, Any]:
    project_root = str(Path(config_path).resolve().parent)
    resolved_selector_state_path = _resolve_selector_state_path(config_path, selector_state_path)
    effective_state_path = state_path or ""
    report_mode = "paper"

    if job_type == "paper-loop":
        effective_state_path = state_path or "data/paper-state-ui.json"
        command = build_paper_loop_command(
            config_path=config_path,
            state_path=effective_state_path,
            warmup_csv=csv_path,
            poll_seconds=poll_seconds,
        )
    elif job_type == "paper-selector":
        command = build_paper_selector_command(
            config_path=config_path,
            selector_state_path=resolved_selector_state_path,
            poll_seconds=poll_seconds,
            quote_currency=quote_currency,
            max_markets=max_markets,
        )
    elif job_type == "live-daemon":
        effective_state_path = state_path or "data/live-state-ui.json"
        command = build_live_daemon_command(
            config_path=config_path,
            state_path=effective_state_path,
            warmup_csv=csv_path,
            poll_seconds=poll_seconds,
            reconcile_every_loops=reconcile_every_loops,
        )
        report_mode = "live"
    elif job_type == "live-supervisor":
        effective_state_path = state_path or "data/live-state-ui.json"
        command = build_live_supervisor_command(
            config_path=config_path,
            state_path=effective_state_path,
            market=market,
            reconcile_every=reconcile_every,
        )
        report_mode = "live"
    else:
        return {"error": "unsupported job type", "job_type": job_type}

    resolved_state_path = _resolve_project_path(config_path, effective_state_path) if effective_state_path else ""
    resolved_selector_state_path = _resolve_project_path(config_path, resolved_selector_state_path) if resolved_selector_state_path else ""
    preview = {
        "job_type": job_type,
        "command": command,
        "cwd": project_root,
        "auto_restart": auto_restart,
        "max_restarts": max_restarts,
        "restart_backoff_seconds": restart_backoff_seconds,
        "report_on_exit": bool(resolved_state_path),
        "report_config_path": str(Path(config_path).resolve()),
        "report_state_path": resolved_state_path,
        "report_mode": report_mode,
        "report_output_dir": default_reports_dir(config_path),
        "report_label": job_type,
        "report_keep_latest": _resolve_report_keep_latest(report_keep_latest),
        "heartbeat_path": str(Path(project_root) / "data" / "webui-jobs" / "{0}.heartbeat.json".format(job_type)),
        "blocking_issues": [],
        "warnings": [],
        "preflight": None,
        "can_start": True,
    }
    if report_mode == "live":
        live_config = _override_market(load_config(config_path), market)
        preflight = build_doctor_report(
            config_path=str(Path(config_path).resolve()),
            config=live_config,
            state_path=resolved_state_path or None,
            selector_state_path=resolved_selector_state_path or None,
        )
        blocking_issues = _preflight_blocking_issues(preflight)
        preview["blocking_issues"] = blocking_issues
        preview["warnings"] = [issue for issue in preflight.get("issues", []) if issue not in blocking_issues]
        preview["preflight"] = preflight
        preview["can_start"] = len(blocking_issues) == 0
    return preview


def stop_managed_job(job_name: str, job_manager: Optional[BackgroundJobManager] = None) -> Dict[str, Any]:
    job_manager = job_manager or JOB_MANAGER
    return job_manager.stop_job(job_name)


def stop_all_managed_jobs(job_manager: Optional[BackgroundJobManager] = None) -> Dict[str, Any]:
    job_manager = job_manager or JOB_MANAGER
    return job_manager.stop_all()


def cleanup_managed_jobs(
    job_manager: Optional[BackgroundJobManager] = None,
    remove_logs: bool = False,
) -> Dict[str, Any]:
    job_manager = job_manager or JOB_MANAGER
    local = job_manager.cleanup_stopped(remove_logs=remove_logs)
    orphan = cleanup_job_artifacts(remove_logs=remove_logs)
    return {
        "removed_jobs": int(local.get("removed_jobs", 0)) + int(orphan.get("removed_jobs", 0)),
        "removed_heartbeats": int(local.get("removed_heartbeats", 0)) + int(orphan.get("removed_heartbeats", 0)),
        "removed_logs": int(local.get("removed_logs", 0)) + int(orphan.get("removed_logs", 0)),
        "skipped_running": int(local.get("skipped_running", 0)) + int(orphan.get("skipped_running", 0)),
        "items": [*local.get("items", []), *orphan.get("items", [])],
    }


def _build_handler(
    config_path: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    csv_path: Optional[str],
    mode: str,
):
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path in ("/", "/index.html"):
                self._serve_asset("index.html", "text/html; charset=utf-8")
                return
            if parsed.path == "/styles.css":
                self._serve_asset("styles.css", "text/css; charset=utf-8")
                return
            if parsed.path == "/app.js":
                self._serve_asset("app.js", "application/javascript; charset=utf-8")
                return
            if parsed.path == "/api/dashboard":
                self._write_json(
                    build_dashboard_payload(
                        config_path=config_path,
                        state_path=query.get("state_path", [state_path or ""])[0] or state_path,
                        selector_state_path=(
                            query.get("selector_state_path", [selector_state_path or ""])[0] or selector_state_path
                        ),
                        csv_path=query.get("csv_path", [csv_path or ""])[0] or csv_path,
                        mode=mode,
                        focus_market=query.get("focus_market", [""])[0] or None,
                        job_manager=JOB_MANAGER,
                    )
                )
                return
            if parsed.path == "/api/jobs":
                jobs = JOB_MANAGER.list_jobs()
                history = JOB_MANAGER.list_history()
                self._write_json(
                    {
                        "jobs": jobs,
                        "history": history,
                        "job_health": _build_job_health_summary(jobs, history),
                    }
                )
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            body = self._read_json_body()
            if self.path == "/api/signal":
                self._write_json(
                    run_signal_action(
                        config_path,
                        body.get("csv_path") or csv_path or "",
                        market=body.get("market"),
                    )
                )
                return
            if self.path == "/api/backtest":
                self._write_json(
                    run_backtest_action(
                        config_path,
                        body.get("csv_path") or csv_path or "",
                        market=body.get("market"),
                    )
                )
                return
            if self.path == "/api/optimize":
                self._write_json(
                    run_optimize_action(
                        config_path,
                        body.get("csv_path") or csv_path or "",
                        top=int(body.get("top", 5)),
                        market=body.get("market"),
                        save_best_preset_name=body.get("save_best_preset_name"),
                    )
                )
                return
            if self.path == "/api/preset-save-current":
                self._write_json(
                    run_save_current_preset_action(
                        config_path=config_path,
                        preset_name=body.get("preset_name", ""),
                        csv_path=body.get("csv_path") or csv_path,
                        market=body.get("market"),
                    )
                )
                return
            if self.path == "/api/preset-apply":
                self._write_json(run_apply_preset_action(config_path, body.get("preset", "")))
                return
            if self.path == "/api/scan":
                self._write_json(
                    run_scan_action(
                        config_path=config_path,
                        max_markets=int(body.get("max_markets", 10)),
                        quote_currency=body.get("quote_currency"),
                    )
                )
                return
            if self.path == "/api/reconcile":
                self._write_json(
                    run_live_reconcile_action(
                        config_path=config_path,
                        state_path=body.get("state_path") or state_path,
                        mode=body.get("mode") or mode,
                        market=body.get("market"),
                    )
                )
                return
            if self.path == "/api/doctor":
                self._write_json(
                    run_doctor_action(
                        config_path=config_path,
                        state_path=body.get("state_path") or state_path,
                        selector_state_path=body.get("selector_state_path") or selector_state_path,
                    )
                )
                return
            if self.path == "/api/sync-candles":
                self._write_json(
                    run_sync_candles_action(
                        config_path=config_path,
                        csv_path=body.get("csv_path") or csv_path or "",
                        count=int(body.get("count", 0)) or None,
                        market=body.get("market"),
                    )
                )
                return
            if self.path == "/api/config-save":
                self._write_json(update_editable_config(config_path, body))
                return
            if self.path == "/api/profile-save":
                self._write_json(
                    run_save_profile_action(
                        config_path=config_path,
                        profile_name=body.get("profile_name", ""),
                        profile_payload=body.get("profile", {}),
                        notes=body.get("notes", ""),
                    )
                )
                return
            if self.path == "/api/profile-load":
                self._write_json(run_load_profile_action(config_path, body.get("profile", "")))
                return
            if self.path == "/api/profile-delete":
                self._write_json(run_delete_profile_action(config_path, body.get("profile", "")))
                return
            if self.path == "/api/profile-preview":
                self._write_json(run_preview_profile_action(config_path, body.get("profile", "")))
                return
            if self.path == "/api/profile-start":
                self._write_json(
                    run_start_profile_action(
                        config_path=config_path,
                        profile_ref=body.get("profile", ""),
                        job_manager=JOB_MANAGER,
                    )
                )
                return
            if self.path == "/api/workflow-preview":
                self._write_json(preview_completion_workflow_action(config_path, body.get("stage", "")))
                return
            if self.path == "/api/workflow-start":
                self._write_json(
                    start_completion_workflow_action(
                        config_path=config_path,
                        stage=body.get("stage", ""),
                        job_manager=JOB_MANAGER,
                    )
                )
                return
            if self.path == "/api/session-report":
                self._write_json(
                    run_session_report_action(
                        config_path=config_path,
                        state_path=body.get("state_path") or state_path or "",
                        mode=body.get("mode") or mode,
                        output_dir=body.get("output_dir"),
                        label=body.get("label", ""),
                        keep_latest=(int(body["keep_latest"]) if body.get("keep_latest") not in (None, "") else None),
                    )
                )
                return
            if self.path == "/api/report-show":
                self._write_json(
                    run_show_report_action(
                        config_path=config_path,
                        report_ref=body.get("report", ""),
                        output_dir=body.get("output_dir"),
                    )
                )
                return
            if self.path == "/api/report-delete":
                self._write_json(
                    run_delete_report_action(
                        config_path=config_path,
                        report_ref=body.get("report", ""),
                        output_dir=body.get("output_dir"),
                    )
                )
                return
            if self.path == "/api/report-prune":
                self._write_json(
                    run_prune_reports_action(
                        config_path=config_path,
                        keep=int(body.get("keep", 10) or 10),
                        output_dir=body.get("output_dir"),
                    )
                )
                return
            if self.path == "/api/jobs-start":
                self._write_json(
                    start_managed_job(
                        config_path=config_path,
                        job_type=body.get("job_type", ""),
                        state_path=body.get("state_path") or state_path,
                        selector_state_path=body.get("selector_state_path") or selector_state_path,
                        csv_path=body.get("csv_path") or csv_path,
                        poll_seconds=float(body["poll_seconds"]) if body.get("poll_seconds") not in (None, "") else None,
                        reconcile_every_loops=(
                            int(body["reconcile_every_loops"])
                            if body.get("reconcile_every_loops") not in (None, "")
                            else None
                        ),
                        reconcile_every=(
                            int(body["reconcile_every"])
                            if body.get("reconcile_every") not in (None, "")
                            else None
                        ),
                        market=body.get("market"),
                        quote_currency=body.get("quote_currency"),
                        max_markets=int(body["max_markets"]) if body.get("max_markets") not in (None, "") else None,
                        auto_restart=bool(body.get("auto_restart", False)),
                        max_restarts=int(body.get("max_restarts", 0) or 0),
                        restart_backoff_seconds=float(body.get("restart_backoff_seconds", 0.0) or 0.0),
                        report_keep_latest=(int(body["report_keep_latest"]) if body.get("report_keep_latest") not in (None, "") else None),
                    )
                )
                return
            if self.path == "/api/jobs-preview":
                self._write_json(
                    preview_managed_job(
                        config_path=config_path,
                        job_type=body.get("job_type", ""),
                        state_path=body.get("state_path") or state_path,
                        selector_state_path=body.get("selector_state_path") or selector_state_path,
                        csv_path=body.get("csv_path") or csv_path,
                        poll_seconds=float(body["poll_seconds"]) if body.get("poll_seconds") not in (None, "") else None,
                        reconcile_every_loops=(
                            int(body["reconcile_every_loops"])
                            if body.get("reconcile_every_loops") not in (None, "")
                            else None
                        ),
                        reconcile_every=(
                            int(body["reconcile_every"])
                            if body.get("reconcile_every") not in (None, "")
                            else None
                        ),
                        market=body.get("market"),
                        quote_currency=body.get("quote_currency"),
                        max_markets=int(body["max_markets"]) if body.get("max_markets") not in (None, "") else None,
                        auto_restart=bool(body.get("auto_restart", False)),
                        max_restarts=int(body.get("max_restarts", 0) or 0),
                        restart_backoff_seconds=float(body.get("restart_backoff_seconds", 0.0) or 0.0),
                        report_keep_latest=(int(body["report_keep_latest"]) if body.get("report_keep_latest") not in (None, "") else None),
                    )
                )
                return
            if self.path == "/api/jobs-stop":
                self._write_json(stop_managed_job(body.get("job_name", "")))
                return
            if self.path == "/api/jobs-stop-all":
                self._write_json(stop_all_managed_jobs())
                return
            if self.path == "/api/jobs-cleanup":
                self._write_json(cleanup_managed_jobs(remove_logs=bool(body.get("remove_logs", False))))
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _serve_asset(self, name: str, content_type: str) -> None:
            data = (WEBUI_DIR / name).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw) if raw else {}

        def _write_json(self, payload: Dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return RequestHandler


def run_web_ui_server(
    config_path: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    csv_path: Optional[str],
    mode: str,
    host: str,
    port: int,
) -> None:
    handler = _build_handler(
        config_path=config_path,
        state_path=state_path,
        selector_state_path=selector_state_path,
        csv_path=csv_path,
        mode=mode,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print("Web UI listening on http://{0}:{1}".format(host, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
