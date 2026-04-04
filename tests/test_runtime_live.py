import json
import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.models import Action, Balance, Candle, Signal  # noqa: E402
from upbit_auto_trader.risk import TradePlan  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402


class FakeStrategy:
    def __init__(self, actions):
        self.actions = actions

    def minimum_history(self) -> int:
        return 1

    def evaluate(self, candles, position):
        timestamp = candles[-1].timestamp
        action = self.actions.get((timestamp, position is not None), Action.HOLD)
        return Signal(action=action, score=80.0, confidence=0.8, reasons=["test"])


class FakeRiskManager:
    def __init__(self, size_fraction=0.1):
        self.size_fraction = size_fraction

    def build_trade_plan(self, price, atr_value, drawdown_fraction):
        return TradePlan(
            size_fraction=self.size_fraction,
            stop_loss=price * 0.95,
            take_profit=price * 1.05,
            trailing_gap=price * 0.02,
        )


class FakeLiveBroker:
    def __init__(
        self,
        quote_balance,
        base_balance,
        bid_min_total=5000.0,
        ask_min_total=5000.0,
        order_snapshots=None,
        cancel_snapshot=None,
    ):
        self.quote_balance = quote_balance
        self.base_balance = base_balance
        self.bid_min_total = bid_min_total
        self.ask_min_total = ask_min_total
        self.orders = []
        self.order_snapshots = list(order_snapshots or [])
        self.cancel_snapshot = cancel_snapshot
        self.cancelled_orders = []
        self.open_orders = []

    def get_order_chance(self, market):
        return {
            "bid_account": {"balance": str(self.quote_balance)},
            "ask_account": {"balance": str(self.base_balance)},
            "market": {
                "bid": {"min_total": str(self.bid_min_total)},
                "ask": {"min_total": str(self.ask_min_total)},
            },
        }

    def create_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"uuid": "fake-order"}

    def get_accounts(self):
        return [
            Balance(
                currency="KRW",
                balance=float(self.quote_balance),
                locked=0.0,
                avg_buy_price=0.0,
                unit_currency="KRW",
            ),
            Balance(
                currency="BTC",
                balance=float(self.base_balance),
                locked=0.0,
                avg_buy_price=0.0,
                unit_currency="KRW",
            ),
        ]

    def list_open_orders(self, market=None, state=None, states=None, page=None, limit=None, order_by=None):
        return list(self.open_orders)

    def get_order(self, uuid=None, identifier=None):
        if self.order_snapshots:
            return self.order_snapshots.pop(0)
        return {
            "uuid": uuid or "fake-order",
            "market": "KRW-BTC",
            "side": "bid",
            "state": "wait",
            "executed_volume": "0",
            "paid_fee": "0",
            "trades": [],
        }

    def cancel_order(self, uuid=None, identifier=None):
        self.cancelled_orders.append(uuid or identifier)
        if self.cancel_snapshot is not None:
            return self.cancel_snapshot
        return {
            "uuid": uuid or "fake-order",
            "market": "KRW-BTC",
            "side": "bid",
            "state": "cancel",
            "executed_volume": "0",
            "paid_fee": "0",
            "trades": [],
        }


class RecordingNotifier:
    def __init__(self):
        self.records = []

    def notify(self, record):
        self.records.append(dict(record))
        return True


class RuntimeLiveTests(unittest.TestCase):
    def build_runtime(self, state_name, broker, notifier=None):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        config.upbit.live_enabled = True
        state_path = PROJECT_ROOT / "data" / state_name
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        runtime = TradingRuntime(config=config, mode="live", state_path=state_path, broker=broker, notifier=notifier)
        return runtime, state_path, backup_path

    def make_candle(self, timestamp, close):
        return Candle(
            timestamp=timestamp,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000.0,
        )

    def test_live_bootstrap_uses_exchange_quote_balance(self):
        broker = FakeLiveBroker(quote_balance=123456.78, base_balance=0.0)
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-1.json", broker)
        try:
            runtime.strategy = FakeStrategy({})
            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])
            self.assertAlmostEqual(runtime.state.cash, 123456.78)
            self.assertAlmostEqual(runtime.state.peak_equity, 123456.78)
            self.assertEqual(runtime.state.last_processed_timestamp, "2026-03-26T09:00:00")
            self.assertGreaterEqual(runtime.state.processed_bars, 1)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_live_bootstrap_primes_existing_state_cursor_when_blank(self):
        broker = FakeLiveBroker(quote_balance=123456.78, base_balance=0.0)
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-primed.json", broker)
        try:
            runtime.strategy = FakeStrategy({})
            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])

            with open(state_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            payload["last_processed_timestamp"] = ""
            payload["processed_bars"] = 0
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)

            restored = TradingRuntime(config=runtime.config, mode="live", state_path=state_path, broker=broker)
            restored.bootstrap([])

            self.assertEqual(restored.state.last_processed_timestamp, "2026-03-26T09:00:00")
            self.assertGreaterEqual(restored.state.processed_bars, 1)
            self.assertTrue(any("LIVE CURSOR PRIMED" in item for item in restored.state.events))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_live_bootstrap_resets_state_when_candle_unit_mismatches(self):
        broker = FakeLiveBroker(quote_balance=123456.78, base_balance=0.0)
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-unit-reset.json", broker)
        try:
            stale_payload = {
                "market": "KRW-BTC",
                "cash": 500000.0,
                "peak_equity": 500000.0,
                "history": [
                    {
                        "timestamp": "2026-03-26T09:00:00",
                        "open": 100.0,
                        "high": 100.0,
                        "low": 100.0,
                        "close": 100.0,
                        "volume": 1000.0,
                    },
                    {
                        "timestamp": "2026-03-26T09:15:00",
                        "open": 101.0,
                        "high": 101.0,
                        "low": 101.0,
                        "close": 101.0,
                        "volume": 1000.0,
                    },
                ],
                "last_processed_timestamp": "2026-03-26T09:15:00",
                "processed_bars": 2,
            }
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump(stale_payload, handle, indent=2)

            runtime.strategy = FakeStrategy({})
            runtime.bootstrap([self.make_candle("2026-03-26T13:00:00", 120.0)])

            self.assertEqual(runtime.state.candle_unit, runtime.config.upbit.candle_unit)
            self.assertEqual(runtime.state.history[-1].timestamp, "2026-03-26T13:00:00")
            self.assertEqual(runtime.state.last_processed_timestamp, "2026-03-26T13:00:00")
            self.assertTrue(any("STATE RESET reason=candle_unit_mismatch" in item for item in runtime.state.events))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_live_recenter_skips_historical_catchup_candles(self):
        broker = FakeLiveBroker(quote_balance=123456.78, base_balance=0.0)
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-recenter.json", broker)
        try:
            runtime.strategy = FakeStrategy({})
            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])

            payload = runtime.recenter_live_state_to_latest_candles(
                [
                    self.make_candle("2026-03-26T10:00:00", 101.0),
                    self.make_candle("2026-03-26T10:15:00", 102.0),
                    self.make_candle("2026-03-26T10:30:00", 103.0),
                ]
            )

            self.assertTrue(payload["recentered"])
            self.assertEqual(payload["previous_timestamp"], "2026-03-26T09:00:00")
            self.assertEqual(payload["latest_timestamp"], "2026-03-26T10:30:00")
            self.assertEqual(payload["skipped_visible_candles"], 3)
            self.assertEqual(runtime.state.last_processed_timestamp, "2026-03-26T10:30:00")
            self.assertEqual(runtime.state.history[-1].timestamp, "2026-03-26T10:30:00")
            self.assertTrue(any("LIVE STARTUP RECENTERED" in item for item in runtime.state.events))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_live_startup_latest_candle_buy_runs_once(self):
        broker = FakeLiveBroker(quote_balance=1000000.0, base_balance=0.0)
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-startup-entry.json", broker)
        try:
            runtime.strategy = FakeStrategy({("2026-03-26T10:30:00", False): Action.BUY})
            runtime.risk = FakeRiskManager(size_fraction=0.1)
            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])

            latest = self.make_candle("2026-03-26T10:30:00", 103.0)
            runtime.recenter_live_state_to_latest_candles(
                [
                    self.make_candle("2026-03-26T10:00:00", 101.0),
                    self.make_candle("2026-03-26T10:15:00", 102.0),
                    latest,
                ]
            )

            events = runtime.evaluate_startup_latest_candle_once(latest)
            second_events = runtime.evaluate_startup_latest_candle_once(latest)

            self.assertTrue(any("LIVE ORDER_SUBMITTED BUY" in event for event in events))
            self.assertEqual(second_events, [])
            self.assertEqual(len(broker.orders), 1)
            self.assertEqual(runtime.state.last_startup_signal_timestamp, "2026-03-26T10:30:00")
            self.assertIsNotNone(runtime.state.pending_order)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_live_bootstrap_blocks_existing_asset_balance(self):
        broker = FakeLiveBroker(quote_balance=100000.0, base_balance=0.25)
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-2.json", broker)
        try:
            runtime.strategy = FakeStrategy({})
            with self.assertRaises(ValueError):
                runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_live_bootstrap_promotes_pending_buy_when_exchange_balance_exists(self):
        broker = FakeLiveBroker(quote_balance=205000.0, base_balance=0.25)
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-promote-buy.json", broker)
        try:
            payload = {
                "market": "KRW-BTC",
                "cash": 216000.0,
                "peak_equity": 216000.0,
                "candle_unit": runtime.config.upbit.candle_unit,
                "history": [
                    {
                        "timestamp": "2026-03-26T09:00:00",
                        "open": 100.0,
                        "high": 100.0,
                        "low": 100.0,
                        "close": 100.0,
                        "volume": 1000.0,
                    }
                ],
                "last_processed_timestamp": "2026-03-26T09:00:00",
                "processed_bars": 1,
                "position": None,
                "pending_order": {
                    "uuid": "fake-order",
                    "market": "KRW-BTC",
                    "side": "bid",
                    "order_type": "price",
                    "requested_price": 25000.0,
                    "requested_volume": 0.25,
                    "created_timestamp": "2026-03-26T09:00:00",
                    "created_bar_index": 1,
                    "strategy_score": 80.0,
                    "stop_loss": 95.0,
                    "take_profit": 105.0,
                    "trailing_stop": 98.0,
                },
            }
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)

            restored = TradingRuntime(config=runtime.config, mode="live", state_path=state_path, broker=broker)
            restored.bootstrap([])

            self.assertIsNone(restored.state.pending_order)
            self.assertIsNotNone(restored.state.position)
            self.assertAlmostEqual(restored.state.position.quantity, 0.25)
            self.assertAlmostEqual(restored.state.position.entry_price, 100000.0)
            self.assertTrue(any("LIVE SYNC BUY_PROMOTED" in item for item in restored.state.events))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_live_buy_is_blocked_below_minimum_order_total(self):
        broker = FakeLiveBroker(quote_balance=10000.0, base_balance=0.0, bid_min_total=9000.0)
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-3.json", broker)
        try:
            runtime.strategy = FakeStrategy({("2026-03-26T09:01:00", False): Action.BUY})
            runtime.risk = FakeRiskManager(size_fraction=0.1)
            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])

            events = runtime.process_candle(self.make_candle("2026-03-26T09:01:00", 100.0))

            self.assertTrue(any("reason=minimum_order_bid" in event for event in events))
            self.assertEqual(broker.orders, [])
            self.assertIsNone(runtime.state.position)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_live_pending_order_poll_applies_partial_fill(self):
        broker = FakeLiveBroker(
            quote_balance=1000000.0,
            base_balance=0.0,
            order_snapshots=[
                {
                    "uuid": "fake-order",
                    "market": "KRW-BTC",
                    "side": "bid",
                    "state": "wait",
                    "executed_volume": "0.0005",
                    "paid_fee": "30",
                    "trades": [
                        {
                            "funds": "65000",
                        }
                    ],
                }
            ],
        )
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-4.json", broker)
        try:
            runtime.config.runtime.pending_order_max_bars = 10
            runtime.strategy = FakeStrategy({("2026-03-26T09:01:00", False): Action.BUY})
            runtime.risk = FakeRiskManager(size_fraction=0.1)
            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])

            runtime.process_candle(self.make_candle("2026-03-26T09:01:00", 100.0))
            events = runtime.process_candle(self.make_candle("2026-03-26T09:02:00", 101.0))

            self.assertTrue(any("MYORDER BUY_FILL" in event for event in events))
            self.assertIsNotNone(runtime.state.pending_order)
            self.assertIsNotNone(runtime.state.position)
            self.assertAlmostEqual(runtime.state.position.quantity, 0.0005)
            self.assertAlmostEqual(runtime.state.cash, 934970.0)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_live_pending_order_is_cancelled_after_max_bars(self):
        broker = FakeLiveBroker(
            quote_balance=1000000.0,
            base_balance=0.0,
            order_snapshots=[
                {
                    "uuid": "fake-order",
                    "market": "KRW-BTC",
                    "side": "bid",
                    "state": "wait",
                    "executed_volume": "0",
                    "paid_fee": "0",
                    "trades": [],
                }
            ],
            cancel_snapshot={
                "uuid": "fake-order",
                "market": "KRW-BTC",
                "side": "bid",
                "state": "cancel",
                "executed_volume": "0",
                "paid_fee": "0",
                "trades": [],
            },
        )
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-5.json", broker)
        try:
            runtime.config.runtime.pending_order_max_bars = 1
            runtime.strategy = FakeStrategy({("2026-03-26T09:01:00", False): Action.BUY})
            runtime.risk = FakeRiskManager(size_fraction=0.1)
            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])

            runtime.process_candle(self.make_candle("2026-03-26T09:01:00", 100.0))
            events = runtime.process_candle(self.make_candle("2026-03-26T09:02:00", 101.0))

            self.assertTrue(any("LIVE ORDER_CANCEL_REQUESTED" in event for event in events))
            self.assertTrue(any("state=cancel" in event for event in events))
            self.assertEqual(broker.cancelled_orders, ["fake-order"])
            self.assertIsNone(runtime.state.pending_order)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_reconcile_live_snapshot_returns_open_order_report(self):
        broker = FakeLiveBroker(quote_balance=777777.0, base_balance=0.0)
        broker.open_orders = [{"uuid": "open-1", "market": "KRW-BTC", "state": "wait"}]
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-6.json", broker)
        try:
            runtime.strategy = FakeStrategy({})
            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])

            payload = runtime.reconcile_live_snapshot()

            self.assertEqual(payload["open_order_count"], 1)
            self.assertEqual(payload["open_orders"][0]["uuid"], "open-1")
            self.assertAlmostEqual(payload["summary"]["cash"], 777777.0)
            self.assertTrue(any("MYASSET SYNC" in event for event in payload["events"]))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_blocked_entry_is_forwarded_to_notifier(self):
        broker = FakeLiveBroker(quote_balance=10000.0, base_balance=0.0, bid_min_total=9000.0)
        notifier = RecordingNotifier()
        runtime, state_path, backup_path = self.build_runtime("test-runtime-live-7.json", broker, notifier=notifier)
        try:
            runtime.strategy = FakeStrategy({("2026-03-26T09:01:00", False): Action.BUY})
            runtime.risk = FakeRiskManager(size_fraction=0.1)
            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])

            runtime.process_candle(self.make_candle("2026-03-26T09:01:00", 100.0))

            self.assertTrue(any(record["event_type"] == "blocked" for record in notifier.records))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()


if __name__ == "__main__":
    unittest.main()
