import json
import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.models import Action, Candle, Signal  # noqa: E402
from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402


class StrongTrendStrategy:
    def minimum_history(self) -> int:
        return 1

    def evaluate(self, candles, position):
        timestamp = candles[-1].timestamp
        if position is None:
            return Signal(
                action=Action.BUY,
                score=92.0,
                confidence=0.92,
                reasons=["ema_uptrend", "macd_bullish", "adx_trend", "breakout"],
            )
        if timestamp == "2026-03-26T13:00:00":
            return Signal(
                action=Action.HOLD,
                score=94.0,
                confidence=0.94,
                reasons=["ema_uptrend", "macd_bullish", "adx_trend", "breakout"],
            )
        return Signal(action=Action.HOLD, score=70.0, confidence=0.4, reasons=["neutral"])


class RuntimeTests(unittest.TestCase):
    def make_candle(self, timestamp, close):
        return Candle(
            timestamp=timestamp,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000.0,
        )

    def test_replay_loop_persists_state(self) -> None:
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        candles = load_csv_candles(str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"))
        state_path = PROJECT_ROOT / "data" / "test-runtime-state-1.json"
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        try:
            runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
            minimum_history = runtime.strategy.minimum_history()

            runtime.bootstrap(candles[:minimum_history])
            for candle in candles[minimum_history : minimum_history + 5]:
                runtime.process_candle(candle)

            self.assertTrue(state_path.exists())

            with open(state_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)

            self.assertEqual(payload["last_processed_timestamp"], candles[minimum_history + 4].timestamp)
            self.assertLessEqual(len(payload["history"]), 300)
            self.assertTrue(backup_path.exists())
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_runtime_extends_take_profit_when_strong_uptrend_continues(self) -> None:
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        config.fee_rate = 0.0
        config.slippage_rate = 0.0
        config.risk.minimum_stop_fraction = 0.015
        config.risk.stop_atr_multiple = 2.2
        config.risk.take_profit_atr_multiple = 3.5
        config.risk.trend_take_profit_atr_multiple = 6.0
        config.risk.trend_take_profit_stop_multiple = 1.8

        state_path = PROJECT_ROOT / "data" / "test-runtime-state-4.json"
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        try:
            runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
            runtime.strategy = StrongTrendStrategy()

            runtime.bootstrap([self.make_candle("2026-03-26T09:00:00", 100.0)])
            runtime.process_candle(self.make_candle("2026-03-26T09:15:00", 100.0))

            self.assertIsNotNone(runtime.state.position)
            initial_take_profit = runtime.state.position.take_profit

            events = runtime.process_candle(self.make_candle("2026-03-26T13:00:00", 110.0))

            self.assertIsNotNone(runtime.state.position)
            self.assertGreater(runtime.state.position.take_profit, initial_take_profit)
            self.assertTrue(any("TAKE_PROFIT_EXTENDED" in event for event in events))
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_full_replay_updates_summary(self) -> None:
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        candles = load_csv_candles(str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"))
        state_path = PROJECT_ROOT / "data" / "test-runtime-state-2.json"
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        try:
            runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
            minimum_history = runtime.strategy.minimum_history()

            runtime.bootstrap(candles[:minimum_history])
            for candle in candles[minimum_history:]:
                runtime.process_candle(candle)

            summary = runtime.summary()
            self.assertEqual(summary["last_processed_timestamp"], candles[-1].timestamp)
            self.assertEqual(summary["processed_bars"], len(candles) - minimum_history)
            self.assertGreaterEqual(summary["trade_count"], 1)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_runtime_restores_from_backup_when_primary_state_is_corrupted(self) -> None:
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        candles = load_csv_candles(str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"))
        state_path = PROJECT_ROOT / "data" / "test-runtime-state-3.json"
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        try:
            runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
            minimum_history = runtime.strategy.minimum_history()
            runtime.bootstrap(candles[:minimum_history])
            for candle in candles[minimum_history : minimum_history + 2]:
                runtime.process_candle(candle)

            with open(state_path, "w", encoding="utf-8") as handle:
                handle.write("{broken json")

            restored_runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
            restored_state = restored_runtime.bootstrap([])

            self.assertTrue(any("STATE RECOVERED source=backup" in event for event in restored_state.events))
            self.assertEqual(restored_state.last_processed_timestamp, runtime.state.last_processed_timestamp)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()


if __name__ == "__main__":
    unittest.main()
