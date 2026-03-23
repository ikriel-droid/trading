import json
import time
from typing import Any, Dict
from urllib import error, request

from .config import NotificationConfig


EVENT_LEVELS = {
    "blocked": "warning",
    "buy": "success",
    "sell": "success",
    "buy_submitted": "info",
    "buy_fill": "success",
    "sell_fill": "success",
    "myorder_done": "info",
    "pending_order_cancel_requested": "warning",
}
EVENT_HEADLINES = {
    "blocked": "Blocked Entry",
    "buy": "Paper Buy",
    "sell": "Paper Sell",
    "buy_submitted": "Live Order Submitted",
    "buy_fill": "Buy Fill",
    "sell_fill": "Sell Fill",
    "myorder_done": "Order Update",
    "pending_order_cancel_requested": "Cancel Requested",
}


class NotificationError(Exception):
    pass


class DiscordWebhookNotifier:
    def __init__(self, config: NotificationConfig) -> None:
        self.config = config
        self._last_sent_at: Dict[str, float] = {}

    def notify(self, record: Dict[str, Any]) -> bool:
        event_type = str(record.get("event_type", ""))
        level = self._event_level(event_type)
        if not self._is_enabled(event_type, level):
            return False

        dedupe_key = "{0}:{1}:{2}".format(level, event_type, record.get("market", ""))
        current_time = time.time()
        last_sent_at = self._last_sent_at.get(dedupe_key, 0.0)
        if self.config.cooldown_seconds > 0 and (current_time - last_sent_at) < self.config.cooldown_seconds:
            return False

        payload = {
            "content": self._format_message(record, event_type, level),
        }
        req = request.Request(
            url=self.config.discord_webhook_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                response.read()
        except error.URLError as exc:
            raise NotificationError("discord webhook error: {0}".format(exc.reason))

        self._last_sent_at[dedupe_key] = current_time
        return True

    def send_test(self, message: str) -> bool:
        return self.notify(
            {
                "event_type": "blocked",
                "market": "TEST",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "reason": message,
            }
        )

    def _is_enabled(self, event_type: str, level: str) -> bool:
        webhook_url = str(self.config.discord_webhook_url or "").strip()
        if not webhook_url:
            return False
        if webhook_url.startswith("${") and webhook_url.endswith("}"):
            return False
        if self.config.enabled_event_types and event_type not in self.config.enabled_event_types:
            return False
        if self.config.enabled_levels and level not in self.config.enabled_levels:
            return False
        return True

    def _event_level(self, event_type: str) -> str:
        return EVENT_LEVELS.get(event_type, "info")

    def _format_message(self, record: Dict[str, Any], event_type: str, level: str) -> str:
        headline = EVENT_HEADLINES.get(event_type, event_type or "Runtime Event")
        market = str(record.get("market", ""))
        timestamp = str(record.get("timestamp", ""))
        detail = self._detail_text(record, event_type)
        return "[{0}] {1} {2}\n{3}\n{4}".format(
            level.upper(),
            market,
            headline,
            detail,
            timestamp,
        ).strip()

    def _detail_text(self, record: Dict[str, Any], event_type: str) -> str:
        if event_type == "blocked":
            return "reason={0}".format(record.get("reason", "unknown"))
        if event_type == "buy":
            return "qty={0} price={1} score={2}".format(
                record.get("quantity", 0),
                record.get("price", 0),
                record.get("score", 0),
            )
        if event_type == "sell":
            return "qty={0} price={1} pnl={2}".format(
                record.get("quantity", 0),
                record.get("price", 0),
                record.get("pnl", 0),
            )
        if event_type == "buy_submitted":
            return "uuid={0} budget={1} score={2}".format(
                record.get("uuid", ""),
                record.get("budget", 0),
                record.get("score", 0),
            )
        if event_type in ("buy_fill", "sell_fill"):
            return "uuid={0} qty={1} price={2}".format(
                record.get("uuid", ""),
                record.get("quantity", 0),
                record.get("price", 0),
            )
        if event_type == "myorder_done":
            return "uuid={0} side={1} state={2}".format(
                record.get("uuid", ""),
                record.get("side", ""),
                record.get("state", ""),
            )
        if event_type == "pending_order_cancel_requested":
            return "uuid={0} age_bars={1}".format(
                record.get("uuid", ""),
                record.get("age_bars", 0),
            )
        return json.dumps(record, ensure_ascii=False)
