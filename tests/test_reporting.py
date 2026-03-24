import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402
from upbit_auto_trader.reporting import write_runtime_report  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402


class ReportingTests(unittest.TestCase):
    def test_write_runtime_report_creates_json_and_html(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        candles = load_csv_candles(str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"))
        state_path = PROJECT_ROOT / "data" / "test-report-state.json"
        backup_path = pathlib.Path(str(state_path) + ".bak")
        reports_dir = PROJECT_ROOT / "data" / "test-session-reports"
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        if reports_dir.exists():
            for path in reports_dir.glob("*"):
                path.unlink()
            reports_dir.rmdir()
        try:
            runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
            minimum_history = runtime.strategy.minimum_history()
            runtime.bootstrap(candles[:minimum_history])
            for candle in candles[minimum_history : minimum_history + 5]:
                runtime.process_candle(candle)

            report = write_runtime_report(
                config_path=str(PROJECT_ROOT / "config.example.json"),
                state_path=str(state_path),
                mode="paper",
                output_dir=str(reports_dir),
                label="test-report",
            )

            self.assertTrue(pathlib.Path(report["json_path"]).exists())
            self.assertTrue(pathlib.Path(report["html_path"]).exists())
            self.assertIn("summary", report)
            self.assertIn("metrics", report)
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()
            if reports_dir.exists():
                for path in reports_dir.glob("*"):
                    path.unlink()
                reports_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
