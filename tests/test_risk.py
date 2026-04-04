import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import RiskConfig  # noqa: E402
from upbit_auto_trader.risk import RiskManager  # noqa: E402


class RiskManagerTests(unittest.TestCase):
    def test_strong_uptrend_plan_keeps_same_stop_but_uses_longer_take_profit(self) -> None:
        config = RiskConfig()
        risk = RiskManager(config)

        normal_plan = risk.build_trade_plan(
            price=100.0,
            atr_value=5.0,
            drawdown_fraction=0.0,
            signal_reasons=["ema_uptrend", "macd_bullish"],
        )
        trend_plan = risk.build_trade_plan(
            price=100.0,
            atr_value=5.0,
            drawdown_fraction=0.0,
            signal_reasons=["ema_uptrend", "macd_bullish", "adx_trend", "breakout"],
        )

        self.assertEqual(normal_plan.stop_loss, trend_plan.stop_loss)
        self.assertGreater(trend_plan.take_profit, normal_plan.take_profit)

    def test_extend_take_profit_only_moves_up_in_strong_uptrend(self) -> None:
        config = RiskConfig()
        risk = RiskManager(config)

        unchanged = risk.extend_take_profit(
            current_price=110.0,
            current_take_profit=122.0,
            atr_value=5.0,
            signal_reasons=["ema_uptrend", "macd_bullish"],
        )
        extended = risk.extend_take_profit(
            current_price=110.0,
            current_take_profit=122.0,
            atr_value=5.0,
            signal_reasons=["ema_uptrend", "macd_bullish", "adx_trend", "volatility_expansion_up"],
        )

        self.assertEqual(unchanged, 122.0)
        self.assertGreater(extended, 122.0)


if __name__ == "__main__":
    unittest.main()
