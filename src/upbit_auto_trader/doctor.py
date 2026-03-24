import os
from typing import Optional

from .brokers.upbit import UpbitBroker
from .config import AppConfig
from .runtime import TradingRuntime


def has_real_webhook_url(config: AppConfig) -> bool:
    value = str(config.notifications.discord_webhook_url or "").strip()
    if not value:
        return False
    return not (value.startswith("${") and value.endswith("}"))


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

    issues = []
    readiness = broker.readiness_report()
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

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "market": config.market,
        "upbit": readiness,
        "notifications": notification_report,
        "state": state_report,
        "selector_state": selector_report,
        "runtime": {
            "journal_path": config.runtime.journal_path,
            "poll_seconds": config.runtime.poll_seconds,
            "pending_order_max_bars": config.runtime.pending_order_max_bars,
        },
        "config_path": config_path,
    }
