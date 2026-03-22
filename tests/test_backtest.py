import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.backtest import Backtester  # noqa: E402
from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402


class BacktestTests(unittest.TestCase):
    def test_demo_backtest_runs(self) -> None:
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        candles = load_csv_candles(str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"))

        result = Backtester(config).run(candles)

        self.assertGreater(result.final_equity, 0.0)
        self.assertGreaterEqual(len(result.events), 1)
        self.assertGreaterEqual(len(result.trades), 1)


if __name__ == "__main__":
    unittest.main()
