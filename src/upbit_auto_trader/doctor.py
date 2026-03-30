import os
from typing import Optional

from .brokers.upbit import UpbitBroker, UpbitError
from .config import AppConfig
from .jobs import JOB_LOG_DIR, list_job_heartbeats
from .runtime import TradingRuntime


def has_real_config_secret(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return not (text.startswith("${") and text.endswith("}"))


def has_real_webhook_url(config: AppConfig) -> bool:
    value = str(config.notifications.discord_webhook_url or "").strip()
    if not value:
        return False
    return not (value.startswith("${") and value.endswith("}"))


def _is_out_of_scope_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return "out_of_scope" in message or "403" in message


def _validate_live_private_api_scope(config: AppConfig, broker: UpbitBroker) -> dict:
    report = {
        "checked": False,
        "market": config.market,
        "items": [],
        "issues": [],
    }
    if not config.upbit.live_enabled:
        return report
    if not has_real_config_secret(config.upbit.access_key) or not has_real_config_secret(config.upbit.secret_key):
        return report

    report["checked"] = True
    checks = [
        ("accounts", lambda: broker.get_accounts(), "accounts_scope_missing"),
        ("order_chance", lambda: broker.get_order_chance(config.market), "order_chance_scope_missing"),
        ("open_orders", lambda: broker.list_open_orders(market=config.market, states=["wait", "watch"]), "open_orders_scope_missing"),
    ]
    issues = []
    items = []

    for name, callback, scope_issue in checks:
        item = {
            "name": name,
            "ok": False,
            "issue": "",
            "detail": "",
        }
        try:
            callback()
            item["ok"] = True
        except UpbitError as exc:
            item["detail"] = str(exc)
            if _is_out_of_scope_error(exc):
                item["issue"] = scope_issue
                issues.append(scope_issue)
            else:
                item["issue"] = "{0}_check_failed".format(name)
                issues.append(item["issue"])
        items.append(item)

    report["items"] = items
    report["issues"] = issues
    return report


def build_doctor_report(config_path: str, config: AppConfig, state_path: Optional[str], selector_state_path: Optional[str]) -> dict:
    broker = UpbitBroker(config.upbit)
    state_report = {
        "path": state_path or "",
        "exists": False,
        "backup_path": "",
        "backup_exists": False,
        "load_ok": False,
        "recovered_from_backup": False,
        "last_processed_timestamp": "",
    }
    selector_report = {
        "path": selector_state_path or "",
        "exists": False,
    }

    if state_path:
        resolved_state = state_path
        backup_path = resolved_state + ".bak"
        state_report["path"] = resolved_state
        state_report["exists"] = os.path.exists(resolved_state)
        state_report["backup_path"] = backup_path
        state_report["backup_exists"] = os.path.exists(backup_path)
        if state_report["exists"] or state_report["backup_exists"]:
            try:
                runtime = TradingRuntime(config=config, mode="paper", state_path=resolved_state)
                restored = runtime.bootstrap([])
                state_report["load_ok"] = True
                state_report["recovered_from_backup"] = any(
                    "STATE RECOVERED source=backup" in event for event in restored.events
                )
                state_report["last_processed_timestamp"] = restored.last_processed_timestamp
            except ValueError as exc:
                state_report["error"] = str(exc)

    if selector_state_path:
        selector_report["path"] = selector_state_path
        selector_report["exists"] = os.path.exists(selector_state_path)

    notification_report = {
        "discord_webhook_configured": has_real_webhook_url(config),
        "enabled_levels": list(config.notifications.enabled_levels),
        "enabled_event_types": list(config.notifications.enabled_event_types),
    }
    managed_job_items = list_job_heartbeats(limit=12)
    managed_jobs_report = {
        "path": str(JOB_LOG_DIR),
        "items": managed_job_items,
        "summary": {
            "healthy": sum(1 for item in managed_job_items if item.get("status") == "healthy"),
            "stale": sum(1 for item in managed_job_items if item.get("status") == "stale"),
            "completed": sum(1 for item in managed_job_items if item.get("status") == "completed"),
            "unknown": sum(1 for item in managed_job_items if item.get("status") == "unknown"),
            "missing": sum(1 for item in managed_job_items if item.get("status") == "missing"),
        },
    }

    readiness = broker.readiness_report()
    private_issues = list(readiness.get("private_issues", []))
    if not has_real_config_secret(config.upbit.access_key) and "access_key_missing" not in private_issues:
        private_issues.append("access_key_missing")
    if not has_real_config_secret(config.upbit.secret_key) and "secret_key_missing" not in private_issues:
        private_issues.append("secret_key_missing")
    readiness = {
        **readiness,
        "private_issues": private_issues,
        "private_ready": bool(readiness.get("public_ready", False)) and len(private_issues) == 0,
    }
    live_api_validation = _validate_live_private_api_scope(config, broker)
    if live_api_validation.get("issues"):
        merged_private_issues = list(readiness["private_issues"])
        for item in live_api_validation["issues"]:
            if item not in merged_private_issues:
                merged_private_issues.append(item)
        readiness["private_issues"] = merged_private_issues
        readiness["private_ready"] = bool(readiness.get("public_ready", False)) and len(merged_private_issues) == 0

    issues = []
    if not readiness["public_ready"]:
        issues.extend(readiness["public_issues"])
    if config.upbit.live_enabled and not readiness["private_ready"]:
        issues.extend(readiness["private_issues"])
    if state_path and not (state_report["exists"] or state_report["backup_exists"]):
        issues.append("state_missing")
    if state_path and (state_report["exists"] or state_report["backup_exists"]) and not state_report["load_ok"]:
        issues.append("state_unreadable")
    if config.notifications.enabled_event_types and not notification_report["discord_webhook_configured"]:
        issues.append("discord_webhook_not_configured")
    for item in managed_job_items:
        if item.get("status") == "stale":
            issues.append("job_heartbeat_stale:{0}".format(item.get("job_name", "")))

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "market": config.market,
        "upbit": readiness,
        "notifications": notification_report,
        "state": state_report,
        "selector_state": selector_report,
        "live_api_validation": live_api_validation,
        "runtime": {
            "journal_path": config.runtime.journal_path,
            "poll_seconds": config.runtime.poll_seconds,
            "pending_order_max_bars": config.runtime.pending_order_max_bars,
        },
        "managed_jobs": managed_jobs_report,
        "config_path": config_path,
    }
