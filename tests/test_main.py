import io
import pathlib
import sys
import unittest
from contextlib import redirect_stdout


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.main import _run_live_daemon, _run_live_supervisor  # noqa: E402
from upbit_auto_trader.models import Balance, Candle  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402
from upbit_auto_trader.websocket_client import UpbitWebSocketClient  # noqa: E402


class FakeSupervisorBroker:
    def __init__(self):
        self.quote_balance = 700000.0
        self.base_balance = 0.0
        self.open_orders = [{"uuid": "open-1", "market": "KRW-BTC", "state": "wait"}]
        self.minute_candles = [
            {
                "candle_date_time_kst": "2026-03-26T10:00:00",
                "opening_price": 101.0,
                "high_price": 102.0,
                "low_price": 100.0,
                "trade_price": 102.0,
                "candle_acc_trade_volume": 1200.0,
            }
        ]

    def websocket_private_headers(self):
        return {"Authorization": "Bearer test-token"}

    def get_accounts(self):
        return [
            Balance(currency="KRW", balance=self.quote_balance, locked=0.0, avg_buy_price=0.0, unit_currency="KRW"),
            Balance(currency="BTC", balance=self.base_balance, locked=0.0, avg_buy_price=0.0, unit_currency="KRW"),
        ]

    def get_order_chance(self, market):
        return {
            "bid_account": {"balance": str(self.quote_balance)},
            "ask_account": {"balance": str(self.base_balance)},
            "market": {
                "bid": {"min_total": "5000"},
                "ask": {"min_total": "5000"},
            },
        }

    def list_open_orders(self, market=None, state=None, states=None, page=None, limit=None, order_by=None):
        return list(self.open_orders)

    def get_minute_candles(self, market, unit, count=200, to=None):
        return list(self.minute_candles)


class MainTests(unittest.TestCase):
    def test_run_live_supervisor_prints_reconcile_and_private_event(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        config.upbit.live_enabled = True
        broker = FakeSupervisorBroker()
        state_path = PROJECT_ROOT / "data" / "test-live-supervisor-state.json"
        if state_path.exists():
            state_path.unlink()
        try:
            runtime = TradingRuntime(config=config, mode="live", state_path=state_path, broker=broker)
            minimum_history = runtime.strategy.minimum_history()
            runtime.bootstrap(
                [
                    Candle(
                        timestamp="2026-03-26T09:{0:02d}:00".format(index),
                        open=100.0,
                        high=100.0,
                        low=100.0,
                        close=100.0,
                        volume=1000.0,
                    )
                    for index in range(minimum_history)
                ]
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = _run_live_supervisor(
                    config=config,
                    broker=broker,
                    state_path=str(state_path),
                    market="KRW-BTC",
                    max_events=1,
                    reconcile_every=1,
                    skip_initial_reconcile=False,
                    client=UpbitWebSocketClient(),
                    message_source=[
                        {
                            "type": "myAsset",
                            "assets": [
                                {"currency": "KRW", "balance": 700000.0, "locked": 0.0},
                                {"currency": "BTC", "balance": 0.0, "locked": 0.0},
                            ],
                            "timestamp": 1710146519000,
                        }
                    ],
                )

            output = stdout.getvalue()
            self.assertEqual(result, 0)
            self.assertIn('"open_order_count": 1', output)
            self.assertIn('"message_type": "myAsset"', output)
            self.assertIn('"reconciled_at"', output)
        finally:
            if state_path.exists():
                state_path.unlink()

    def test_run_live_daemon_prints_reconcile_loop_and_final(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        config.upbit.live_enabled = True
        broker = FakeSupervisorBroker()
        state_path = PROJECT_ROOT / "data" / "test-live-daemon-state.json"
        if state_path.exists():
            state_path.unlink()
        try:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = _run_live_daemon(
                    config=config,
                    broker=broker,
                    state_path=str(state_path),
                    warmup_csv=str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"),
                    poll_seconds=0.0,
                    max_loops=1,
                    reconcile_every_loops=1,
                )

            output = stdout.getvalue()
            self.assertEqual(result, 0)
            self.assertIn('"kind": "reconcile"', output)
            self.assertIn('"kind": "loop"', output)
            self.assertIn('"kind": "final"', output)
        finally:
            if state_path.exists():
                state_path.unlink()


if __name__ == "__main__":
    unittest.main()
