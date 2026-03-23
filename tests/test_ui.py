import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402
from upbit_auto_trader.ui import (  # noqa: E402
    build_dashboard_payload,
    run_backtest_action,
    run_optimize_action,
    run_signal_action,
)


class UiTests(unittest.TestCase):
    def setUp(self):
        self.config_path = str(PROJECT_ROOT / "config.example.json")
        self.csv_path = str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv")
        self.state_path = PROJECT_ROOT / "data" / "test-ui-state.json"
        if self.state_path.exists():
            self.state_path.unlink()

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

    def test_backtest_signal_and_optimize_actions_return_expected_keys(self):
        signal = run_signal_action(self.config_path, self.csv_path)
        backtest = run_backtest_action(self.config_path, self.csv_path)
        optimize = run_optimize_action(self.config_path, self.csv_path, top=3)

        self.assertIn("action", signal)
        self.assertIn("final_equity", backtest)
        self.assertEqual(len(optimize["top"]), 3)


if __name__ == "__main__":
    unittest.main()
