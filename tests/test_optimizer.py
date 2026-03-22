import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402
from upbit_auto_trader.optimizer import run_grid_search  # noqa: E402


class OptimizerTests(unittest.TestCase):
    def test_run_grid_search_returns_sorted_results(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        candles = load_csv_candles(str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"))

        results = run_grid_search(
            config=config,
            candles=candles,
            buy_thresholds=[62.0, 65.0],
            sell_thresholds=[35.0],
            min_adx_values=[18.0],
            min_bollinger_width_values=[0.015],
            volume_spike_multipliers=[1.3],
        )

        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(results[0].final_equity, results[1].final_equity)
        self.assertIn(results[0].buy_threshold, [62.0, 65.0])


if __name__ == "__main__":
    unittest.main()
