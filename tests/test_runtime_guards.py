import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.models import Action, Candle, Signal  # noqa: E402
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

    def build_trade_plan(self, price, atr_value, drawdown_fraction, signal_reasons=None):
        return TradePlan(
            size_fraction=self.size_fraction,
            stop_loss=price * 0.95,
            take_profit=price * 1.05,
            trailing_gap=price * 0.02,
        )


class RuntimeGuardTests(unittest.TestCase):
    def build_runtime(self, state_name):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.initial_cash = 1000000.0
        config.runtime.journal_path = ""
        state_path = PROJECT_ROOT / "data" / state_name
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
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

    def test_cooldown_blocks_immediate_reentry(self):
        runtime, state_path, backup_path = self.build_runtime("test-runtime-guard-1.json")
        try:
            runtime.config.runtime.cooldown_bars_after_exit = 1
            runtime.config.runtime.max_trades_per_day = 10
            runtime.config.runtime.daily_loss_limit_fraction = 1.0
            runtime.strategy = FakeStrategy(
                {
                    ("2026-03-23T09:01:00", False): Action.BUY,
                    ("2026-03-23T09:02:00", True): Action.SELL,
                    ("2026-03-23T09:03:00", False): Action.BUY,
                    ("2026-03-23T09:04:00", False): Action.BUY,
                }
            )
            runtime.risk = FakeRiskManager()

            runtime.bootstrap([self.make_candle("2026-03-23T09:00:00", 100.0)])
            events = []
            for candle in [
                self.make_candle("2026-03-23T09:01:00", 100.0),
                self.make_candle("2026-03-23T09:02:00", 101.0),
                self.make_candle("2026-03-23T09:03:00", 102.0),
                self.make_candle("2026-03-23T09:04:00", 103.0),
            ]:
                events.extend(runtime.process_candle(candle))

            self.assertTrue(any("reason=cooldown_after_exit" in event for event in events))
            self.assertTrue(any("2026-03-23T09:04:00 PAPER BUY" in event for event in events))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_daily_loss_limit_blocks_new_entries(self):
        runtime, state_path, backup_path = self.build_runtime("test-runtime-guard-2.json")
        try:
            runtime.config.runtime.cooldown_bars_after_exit = 0
            runtime.config.runtime.max_trades_per_day = 10
            runtime.config.runtime.daily_loss_limit_fraction = 0.0005
            runtime.strategy = FakeStrategy(
                {
                    ("2026-03-24T09:01:00", False): Action.BUY,
                    ("2026-03-24T09:02:00", True): Action.SELL,
                    ("2026-03-24T09:03:00", False): Action.BUY,
                }
            )
            runtime.risk = FakeRiskManager(size_fraction=0.5)

            runtime.bootstrap([self.make_candle("2026-03-24T09:00:00", 100.0)])
            events = []
            for candle in [
                self.make_candle("2026-03-24T09:01:00", 100.0),
                self.make_candle("2026-03-24T09:02:00", 80.0),
                self.make_candle("2026-03-24T09:03:00", 81.0),
            ]:
                events.extend(runtime.process_candle(candle))

            self.assertTrue(any("reason=daily_loss_limit" in event for event in events))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_max_trades_per_day_blocks_third_entry(self):
        runtime, state_path, backup_path = self.build_runtime("test-runtime-guard-3.json")
        try:
            runtime.config.runtime.cooldown_bars_after_exit = 0
            runtime.config.runtime.max_trades_per_day = 2
            runtime.config.runtime.daily_loss_limit_fraction = 1.0
            runtime.strategy = FakeStrategy(
                {
                    ("2026-03-25T09:01:00", False): Action.BUY,
                    ("2026-03-25T09:02:00", True): Action.SELL,
                    ("2026-03-25T09:03:00", False): Action.BUY,
                    ("2026-03-25T09:04:00", True): Action.SELL,
                    ("2026-03-25T09:05:00", False): Action.BUY,
                }
            )
            runtime.risk = FakeRiskManager()

            runtime.bootstrap([self.make_candle("2026-03-25T09:00:00", 100.0)])
            events = []
            for candle in [
                self.make_candle("2026-03-25T09:01:00", 100.0),
                self.make_candle("2026-03-25T09:02:00", 101.0),
                self.make_candle("2026-03-25T09:03:00", 102.0),
                self.make_candle("2026-03-25T09:04:00", 103.0),
                self.make_candle("2026-03-25T09:05:00", 104.0),
            ]:
                events.extend(runtime.process_candle(candle))

            self.assertTrue(any("reason=max_trades_per_day" in event for event in events))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()


if __name__ == "__main__":
    unittest.main()
