import json
import pathlib
import sys
import unittest
from unittest import mock


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import NotificationConfig  # noqa: E402
from upbit_auto_trader.notifier import DiscordWebhookNotifier  # noqa: E402


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b"ok"


class NotifierTests(unittest.TestCase):
    def test_notify_posts_to_discord_webhook(self):
        config = NotificationConfig(
            discord_webhook_url="https://example.test/webhook",
            enabled_levels=["warning"],
            enabled_event_types=["blocked"],
            cooldown_seconds=0.0,
            timeout_seconds=1.0,
        )
        notifier = DiscordWebhookNotifier(config)

        with mock.patch("upbit_auto_trader.notifier.request.urlopen", return_value=FakeResponse()) as mocked:
            sent = notifier.notify(
                {
                    "event_type": "blocked",
                    "market": "KRW-BTC",
                    "timestamp": "2026-03-23T00:00:00",
                    "reason": "daily_loss_limit",
                }
            )

        self.assertTrue(sent)
        request_obj = mocked.call_args.args[0]
        body = json.loads(request_obj.data.decode("utf-8"))
        self.assertIn("Blocked Entry", body["content"])
        self.assertIn("daily_loss_limit", body["content"])

    def test_notify_respects_cooldown_for_same_event(self):
        config = NotificationConfig(
            discord_webhook_url="https://example.test/webhook",
            enabled_levels=["warning"],
            enabled_event_types=["blocked"],
            cooldown_seconds=60.0,
            timeout_seconds=1.0,
        )
        notifier = DiscordWebhookNotifier(config)

        with mock.patch("upbit_auto_trader.notifier.request.urlopen", return_value=FakeResponse()) as mocked:
            first = notifier.notify(
                {
                    "event_type": "blocked",
                    "market": "KRW-BTC",
                    "timestamp": "2026-03-23T00:00:00",
                    "reason": "daily_loss_limit",
                }
            )
            second = notifier.notify(
                {
                    "event_type": "blocked",
                    "market": "KRW-BTC",
                    "timestamp": "2026-03-23T00:00:05",
                    "reason": "daily_loss_limit",
                }
            )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(mocked.call_count, 1)

    def test_notify_returns_false_when_webhook_is_not_configured(self):
        notifier = DiscordWebhookNotifier(NotificationConfig(discord_webhook_url=""))

        sent = notifier.notify(
            {
                "event_type": "blocked",
                "market": "KRW-BTC",
                "timestamp": "2026-03-23T00:00:00",
                "reason": "daily_loss_limit",
            }
        )

        self.assertFalse(sent)


if __name__ == "__main__":
    unittest.main()
