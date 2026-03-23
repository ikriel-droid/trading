import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.models import PendingOrder, Position  # noqa: E402
from upbit_auto_trader.runtime import RuntimeState, TradingRuntime  # noqa: E402
from upbit_auto_trader.websocket_client import (  # noqa: E402
    build_myasset_subscription,
    build_myorder_subscription,
    build_private_account_subscription,
)


class MyOrderTests(unittest.TestCase):
    def build_runtime(self, state_name):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        config.upbit.live_enabled = True
        state_path = PROJECT_ROOT / "data" / state_name
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        runtime = TradingRuntime(config=config, mode="live", state_path=state_path, broker=None)
        runtime.state = RuntimeState(
            market=config.market,
            cash=1000000.0,
            peak_equity=1000000.0,
        )
        return runtime, state_path, backup_path

    def test_build_myorder_subscription_for_market(self):
        payload = build_myorder_subscription(["krw-btc"])

        self.assertEqual(payload[1]["type"], "myOrder")
        self.assertEqual(payload[1]["codes"], ["KRW-BTC"])

    def test_build_myasset_subscription_has_no_codes(self):
        payload = build_myasset_subscription()

        self.assertEqual(payload[1]["type"], "myAsset")
        self.assertNotIn("codes", payload[1])

    def test_build_private_account_subscription_combines_myorder_and_myasset(self):
        payload = build_private_account_subscription(["krw-btc"])

        self.assertEqual(payload[1]["type"], "myOrder")
        self.assertEqual(payload[1]["codes"], ["KRW-BTC"])
        self.assertEqual(payload[2]["type"], "myAsset")

    def test_apply_myorder_buy_fill_creates_position(self):
        runtime, state_path, backup_path = self.build_runtime("test-myorder-state-1.json")
        try:
            runtime.state.pending_order = PendingOrder(
                uuid="order-1",
                market="KRW-BTC",
                side="bid",
                order_type="price",
                requested_price=100000.0,
                requested_volume=0.0008,
                created_timestamp="2026-03-26T09:00:00",
                created_bar_index=0,
                strategy_score=82.0,
                stop_loss=120000000.0,
                take_profit=140000000.0,
                trailing_stop=125000000.0,
            )

            events = runtime.apply_myorder_event(
                {
                    "type": "myOrder",
                    "code": "KRW-BTC",
                    "uuid": "order-1",
                    "ask_bid": "BID",
                    "state": "done",
                    "avg_price": 130000000.0,
                    "executed_volume": 0.0008,
                    "executed_funds": 104000.0,
                    "paid_fee": 52.0,
                    "timestamp": 1710751597500,
                }
            )

            self.assertTrue(any("MYORDER BUY_FILL" in event for event in events))
            self.assertIsNone(runtime.state.pending_order)
            self.assertIsNotNone(runtime.state.position)
            self.assertAlmostEqual(runtime.state.position.quantity, 0.0008)
            self.assertAlmostEqual(runtime.state.cash, 895948.0)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_apply_myorder_sell_fill_closes_position(self):
        runtime, state_path, backup_path = self.build_runtime("test-myorder-state-2.json")
        try:
            runtime.state.cash = 900000.0
            runtime.state.position = Position(
                market="KRW-BTC",
                entry_timestamp="2026-03-26T09:00:00",
                entry_price=130000000.0,
                quantity=0.001,
                stop_loss=120000000.0,
                take_profit=140000000.0,
                trailing_stop=125000000.0,
                entry_score=82.0,
            )
            runtime.state.pending_order = PendingOrder(
                uuid="order-2",
                market="KRW-BTC",
                side="ask",
                order_type="market",
                requested_price=131000000.0,
                requested_volume=0.001,
                created_timestamp="2026-03-26T09:10:00",
                created_bar_index=2,
                strategy_score=82.0,
            )

            events = runtime.apply_myorder_event(
                {
                    "type": "myOrder",
                    "code": "KRW-BTC",
                    "uuid": "order-2",
                    "ask_bid": "ASK",
                    "state": "done",
                    "avg_price": 131000000.0,
                    "executed_volume": 0.001,
                    "executed_funds": 131000.0,
                    "paid_fee": 65.5,
                    "timestamp": 1710751697500,
                }
            )

            self.assertTrue(any("MYORDER SELL_FILL" in event for event in events))
            self.assertIsNone(runtime.state.pending_order)
            self.assertIsNone(runtime.state.position)
            self.assertEqual(len(runtime.state.closed_trades), 1)
            self.assertGreater(runtime.state.cash, 900000.0)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_apply_myasset_updates_cash_and_snapshot(self):
        runtime, state_path, backup_path = self.build_runtime("test-myasset-state-1.json")
        try:
            events = runtime.apply_myasset_event(
                {
                    "type": "myAsset",
                    "assets": [
                        {"currency": "KRW", "balance": 777777.0, "locked": 123.0},
                        {"currency": "BTC", "balance": 0.0, "locked": 0.0},
                    ],
                    "timestamp": 1710146517267,
                }
            )

            self.assertTrue(any("MYASSET SYNC" in event for event in events))
            self.assertAlmostEqual(runtime.state.cash, 777777.0)
            self.assertEqual(runtime.state.asset_snapshot["KRW"]["locked"], 123.0)
            self.assertEqual(runtime.state.last_asset_sync_timestamp, "1710146517267")
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_apply_myasset_warns_when_untracked_base_balance_exists(self):
        runtime, state_path, backup_path = self.build_runtime("test-myasset-state-2.json")
        try:
            events = runtime.apply_myasset_event(
                {
                    "type": "myAsset",
                    "assets": [
                        {"currency": "KRW", "balance": 700000.0, "locked": 0.0},
                        {"currency": "BTC", "balance": 0.01, "locked": 0.0},
                    ],
                    "timestamp": 1710146518000,
                }
            )

            self.assertTrue(any("untracked_balance" in event for event in events))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()


if __name__ == "__main__":
    unittest.main()
