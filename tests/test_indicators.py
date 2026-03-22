import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.indicators import atr, ema, rsi, sma  # noqa: E402
from upbit_auto_trader.models import Candle  # noqa: E402


class IndicatorTests(unittest.TestCase):
    def test_sma(self) -> None:
        self.assertEqual(sma([1, 2, 3, 4, 5], 3), [None, None, 2.0, 3.0, 4.0])

    def test_ema_produces_trend(self) -> None:
        values = [1, 2, 3, 4, 5, 6]
        result = ema(values, 3)
        self.assertIsNone(result[0])
        self.assertIsNotNone(result[-1])
        self.assertGreater(result[-1], result[2])

    def test_rsi_rising_series_is_high(self) -> None:
        values = [float(value) for value in range(1, 30)]
        result = rsi(values, 14)
        self.assertIsNotNone(result[-1])
        self.assertGreater(result[-1], 70.0)

    def test_atr_returns_values_after_period(self) -> None:
        candles = [
            Candle(timestamp=str(index), open=100 + index, high=101 + index, low=99 + index, close=100 + index, volume=1)
            for index in range(20)
        ]
        values = atr(candles, 14)
        self.assertIsNone(values[12])
        self.assertIsNotNone(values[-1])
        self.assertGreater(values[-1], 0.0)


if __name__ == "__main__":
    unittest.main()
