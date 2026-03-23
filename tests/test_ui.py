import shutil
import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402
from upbit_auto_trader.models import Balance  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402
from upbit_auto_trader.ui import (  # noqa: E402
    build_dashboard_payload,
    load_editable_config,
    run_backtest_action,
    run_live_reconcile_action,
    run_scan_action,
    run_sync_candles_action,
    run_optimize_action,
    run_signal_action,
    update_editable_config,
)


class FakeUiBroker:
    def __init__(self):
        self.markets = [
            {"market": "KRW-BTC", "market_warning": "NONE"},
            {"market": "KRW-XRP", "market_warning": "NONE"},
        ]
        self.base_balance = 0.01

    def list_markets(self, is_details=True):
        return list(self.markets)

    def get_ticker(self, markets):
        return [
            {"market": "KRW-BTC", "acc_trade_price_24h": 15000000000.0},
            {"market": "KRW-XRP", "acc_trade_price_24h": 3000000000.0},
        ]

    def get_minute_candles(self, market, unit, count=200, to=None):
        candles = load_csv_candles(str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"))
        mapped = []
        for candle in candles[-count:]:
            mapped.append(
                {
                    "candle_date_time_kst": candle.timestamp,
                    "opening_price": candle.open,
                    "high_price": candle.high,
                    "low_price": candle.low,
                    "trade_price": candle.close,
                    "candle_acc_trade_volume": candle.volume,
                }
            )
        return list(reversed(mapped))

    def get_order_chance(self, market):
        return {
            "bid_account": {"balance": "700000"},
            "ask_account": {"balance": str(self.base_balance)},
            "market": {"bid": {"min_total": "5000"}, "ask": {"min_total": "5000"}},
        }

    def get_accounts(self):
        return [
            Balance(currency="KRW", balance=700000.0, locked=0.0, avg_buy_price=0.0, unit_currency="KRW"),
            Balance(currency="BTC", balance=self.base_balance, locked=0.0, avg_buy_price=0.0, unit_currency="KRW"),
        ]

    def list_open_orders(self, market=None, state=None, states=None, page=None, limit=None, order_by=None):
        return [{"uuid": "open-1", "market": "KRW-BTC", "state": "wait"}]


class UiTests(unittest.TestCase):
    def setUp(self):
        self.config_path = str(PROJECT_ROOT / "config.example.json")
        self.temp_config_path = PROJECT_ROOT / "data" / "test-ui-config.json"
        self.temp_csv_path = PROJECT_ROOT / "data" / "test-ui-candles.csv"
        self.csv_path = str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv")
        self.state_path = PROJECT_ROOT / "data" / "test-ui-state.json"
        if self.state_path.exists():
            self.state_path.unlink()
        if self.temp_config_path.exists():
            self.temp_config_path.unlink()
        if self.temp_csv_path.exists():
            self.temp_csv_path.unlink()
        shutil.copyfile(self.config_path, self.temp_config_path)

        config = load_config(self.config_path)
        config.runtime.journal_path = ""
        candles = load_csv_candles(self.csv_path)
        runtime = TradingRuntime(config=config, mode="paper", state_path=self.state_path)
        minimum_history = runtime.strategy.minimum_history()
        runtime.bootstrap(candles[:minimum_history])
        for candle in candles[minimum_history : minimum_history + 3]:
            runtime.process_candle(candle)

    def tearDown(self):
        if self.state_path.exists():
            self.state_path.unlink()
        if self.temp_config_path.exists():
            self.temp_config_path.unlink()
        if self.temp_csv_path.exists():
            self.temp_csv_path.unlink()

    def test_build_dashboard_payload_contains_summary_and_signal(self):
        payload = build_dashboard_payload(
            config_path=self.config_path,
            state_path=str(self.state_path),
            csv_path=self.csv_path,
            mode="paper",
        )

        self.assertEqual(payload["app"]["market"], "KRW-BTC")
        self.assertIsNotNone(payload["state_summary"])
        self.assertIsNotNone(payload["latest_signal"])
        self.assertTrue(payload["csv_info"]["rows"] > 0)
        self.assertEqual(payload["ui_defaults"]["scan_max_markets"], 10)
        self.assertTrue(len(payload["chart"]["points"]) > 0)

    def test_backtest_signal_and_optimize_actions_return_expected_keys(self):
        signal = run_signal_action(self.config_path, self.csv_path)
        backtest = run_backtest_action(self.config_path, self.csv_path)
        optimize = run_optimize_action(self.config_path, self.csv_path, top=3)

        self.assertIn("action", signal)
        self.assertIn("final_equity", backtest)
        self.assertEqual(len(optimize["top"]), 3)

    def test_scan_and_reconcile_actions_return_expected_keys(self):
        broker = FakeUiBroker()
        scan = run_scan_action(self.config_path, max_markets=2, quote_currency="KRW", broker=broker)
        reconcile = run_live_reconcile_action(
            self.config_path,
            str(self.state_path),
            mode="live",
            broker=broker,
        )

        self.assertEqual(scan["scanned_market_count"], 2)
        self.assertTrue(len(scan["scan_results"]) >= 1)
        self.assertEqual(reconcile["open_order_count"], 1)
        self.assertIn("summary", reconcile)

    def test_editable_config_can_be_loaded_and_saved(self):
        before = load_editable_config(str(self.temp_config_path))
        result = update_editable_config(
            str(self.temp_config_path),
            {
                "strategy.buy_threshold": 70.0,
                "strategy.sell_threshold": 42.0,
                "selector.max_markets": 7,
            },
        )
        after = load_editable_config(str(self.temp_config_path))

        self.assertNotEqual(before["strategy.buy_threshold"], after["strategy.buy_threshold"])
        self.assertEqual(result["current"]["strategy.buy_threshold"], 70.0)
        self.assertEqual(result["current"]["selector.max_markets"], 7)

    def test_sync_candles_action_writes_csv(self):
        broker = FakeUiBroker()
        result = run_sync_candles_action(
            config_path=self.config_path,
            csv_path=str(self.temp_csv_path),
            count=50,
            broker=broker,
        )

        self.assertTrue(self.temp_csv_path.exists())
        self.assertEqual(result["rows_written"], 44)


if __name__ == "__main__":
    unittest.main()
