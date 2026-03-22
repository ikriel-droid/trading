import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.models import Action, Candle  # noqa: E402
from upbit_auto_trader.strategy import ProfessionalCryptoStrategy  # noqa: E402


class StrategyTests(unittest.TestCase):
    def build_strategy(self) -> ProfessionalCryptoStrategy:
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        return ProfessionalCryptoStrategy(config.strategy)

    def test_trending_series_includes_adx_reason(self):
        strategy = self.build_strategy()
        candles = [
            Candle(
                timestamp="2026-03-26T09:{0:02d}:00".format(index),
                open=100 + (index * 2),
                high=101 + (index * 2.2),
                low=99 + (index * 1.8),
                close=100 + (index * 2.1),
                volume=1000 + (index * 50),
            )
            for index in range(strategy.minimum_history() + 10)
        ]

        signal = strategy.evaluate(candles, None)

        self.assertEqual(signal.action, Action.BUY)
        self.assertIn("adx_trend", signal.reasons)

    def test_flat_series_penalizes_chop(self):
        strategy = self.build_strategy()
        candles = [
            Candle(
                timestamp="2026-03-26T10:{0:02d}:00".format(index),
                open=100.0 + ((index % 2) * 0.1),
                high=100.3,
                low=99.7,
                close=100.0 + (((index % 3) - 1) * 0.1),
                volume=900 + (index % 5),
            )
            for index in range(strategy.minimum_history() + 10)
        ]

        signal = strategy.evaluate(candles, None)

        self.assertIn("adx_chop", signal.reasons)
        self.assertLess(signal.score, 65.0)


if __name__ == "__main__":
    unittest.main()
