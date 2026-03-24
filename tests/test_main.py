import io
import json
import pathlib
import shutil
import sys
import unittest
from contextlib import redirect_stdout


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.jobs import JOB_HISTORY_PATH  # noqa: E402
from upbit_auto_trader.main import _build_doctor_report, _run_live_daemon, _run_live_supervisor, main  # noqa: E402
from upbit_auto_trader.models import Balance, Candle  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402
from upbit_auto_trader.websocket_client import UpbitWebSocketClient  # noqa: E402


class FakeSupervisorBroker:
    def __init__(self):
        self.quote_balance = 700000.0
        self.base_balance = 0.0
        self.open_orders = [{"uuid": "open-1", "market": "KRW-BTC", "state": "wait"}]
        self.minute_candles = [
            {
                "candle_date_time_kst": "2026-03-26T10:00:00",
                "opening_price": 101.0,
                "high_price": 102.0,
                "low_price": 100.0,
                "trade_price": 102.0,
                "candle_acc_trade_volume": 1200.0,
            }
        ]

    def websocket_private_headers(self):
        return {"Authorization": "Bearer test-token"}

    def get_accounts(self):
        return [
            Balance(currency="KRW", balance=self.quote_balance, locked=0.0, avg_buy_price=0.0, unit_currency="KRW"),
            Balance(currency="BTC", balance=self.base_balance, locked=0.0, avg_buy_price=0.0, unit_currency="KRW"),
        ]

    def get_order_chance(self, market):
        return {
            "bid_account": {"balance": str(self.quote_balance)},
            "ask_account": {"balance": str(self.base_balance)},
            "market": {
                "bid": {"min_total": "5000"},
                "ask": {"min_total": "5000"},
            },
        }

    def list_open_orders(self, market=None, state=None, states=None, page=None, limit=None, order_by=None):
        return list(self.open_orders)

    def get_minute_candles(self, market, unit, count=200, to=None):
        return list(self.minute_candles)


class MainTests(unittest.TestCase):
    def test_run_live_supervisor_prints_reconcile_and_private_event(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        config.upbit.live_enabled = True
        broker = FakeSupervisorBroker()
        state_path = PROJECT_ROOT / "data" / "test-live-supervisor-state.json"
        if state_path.exists():
            state_path.unlink()
        try:
            runtime = TradingRuntime(config=config, mode="live", state_path=state_path, broker=broker)
            minimum_history = runtime.strategy.minimum_history()
            runtime.bootstrap(
                [
                    Candle(
                        timestamp="2026-03-26T09:{0:02d}:00".format(index),
                        open=100.0,
                        high=100.0,
                        low=100.0,
                        close=100.0,
                        volume=1000.0,
                    )
                    for index in range(minimum_history)
                ]
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = _run_live_supervisor(
                    config=config,
                    broker=broker,
                    state_path=str(state_path),
                    market="KRW-BTC",
                    max_events=1,
                    reconcile_every=1,
                    skip_initial_reconcile=False,
                    client=UpbitWebSocketClient(),
                    message_source=[
                        {
                            "type": "myAsset",
                            "assets": [
                                {"currency": "KRW", "balance": 700000.0, "locked": 0.0},
                                {"currency": "BTC", "balance": 0.0, "locked": 0.0},
                            ],
                            "timestamp": 1710146519000,
                        }
                    ],
                )

            output = stdout.getvalue()
            self.assertEqual(result, 0)
            self.assertIn('"open_order_count": 1', output)
            self.assertIn('"message_type": "myAsset"', output)
            self.assertIn('"reconciled_at"', output)
        finally:
            if state_path.exists():
                state_path.unlink()

    def test_run_live_daemon_prints_reconcile_loop_and_final(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        config.upbit.live_enabled = True
        broker = FakeSupervisorBroker()
        state_path = PROJECT_ROOT / "data" / "test-live-daemon-state.json"
        if state_path.exists():
            state_path.unlink()
        try:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = _run_live_daemon(
                    config=config,
                    broker=broker,
                    state_path=str(state_path),
                    warmup_csv=str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"),
                    poll_seconds=0.0,
                    max_loops=1,
                    reconcile_every_loops=1,
                )

            output = stdout.getvalue()
            self.assertEqual(result, 0)
            self.assertIn('"kind": "reconcile"', output)
            self.assertIn('"kind": "loop"', output)
            self.assertIn('"kind": "final"', output)
        finally:
            if state_path.exists():
                state_path.unlink()

    def test_doctor_reports_state_backup_and_missing_webhook(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        state_path = PROJECT_ROOT / "data" / "test-doctor-state.json"
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        try:
            runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
            minimum_history = runtime.strategy.minimum_history()
            runtime.bootstrap(
                [
                    Candle(
                        timestamp="2026-03-26T09:{0:02d}:00".format(index),
                        open=100.0,
                        high=100.0,
                        low=100.0,
                        close=100.0,
                        volume=1000.0,
                    )
                    for index in range(minimum_history)
                ]
            )

            report = _build_doctor_report(
                config_path=str(PROJECT_ROOT / "config.example.json"),
                config=config,
                state_path=str(state_path),
                selector_state_path=str(PROJECT_ROOT / "data" / "selector-state.json"),
            )

            self.assertTrue(report["state"]["exists"])
            self.assertTrue(report["state"]["backup_exists"])
            self.assertTrue(report["state"]["load_ok"])
            self.assertIn("discord_webhook_not_configured", report["issues"])
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_doctor_recovers_when_primary_state_is_corrupted(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        state_path = PROJECT_ROOT / "data" / "test-doctor-state-corrupt.json"
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        try:
            runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
            minimum_history = runtime.strategy.minimum_history()
            runtime.bootstrap(
                [
                    Candle(
                        timestamp="2026-03-26T10:{0:02d}:00".format(index),
                        open=100.0,
                        high=100.0,
                        low=100.0,
                        close=100.0,
                        volume=1000.0,
                    )
                    for index in range(minimum_history)
                ]
            )
            with open(state_path, "w", encoding="utf-8") as handle:
                handle.write("{broken")

            report = _build_doctor_report(
                config_path=str(PROJECT_ROOT / "config.example.json"),
                config=config,
                state_path=str(state_path),
                selector_state_path=None,
            )

            self.assertTrue(report["state"]["load_ok"])
            self.assertTrue(report["state"]["recovered_from_backup"])
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()

    def test_cli_optimize_can_save_and_apply_preset(self):
        config_path = PROJECT_ROOT / "test-main-config.json"
        preset_path = PROJECT_ROOT / "data" / "strategy-presets" / "test-main-best.json"
        if config_path.exists():
            config_path.unlink()
        if preset_path.exists():
            preset_path.unlink()
        try:
            shutil.copyfile(PROJECT_ROOT / "config.example.json", config_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "optimize-grid",
                        "--config",
                        str(config_path),
                        "--csv",
                        str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"),
                        "--top",
                        "1",
                        "--save-best-preset",
                        "test-main-best",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertTrue(preset_path.exists())

            with open(config_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            raw["strategy"]["buy_threshold"] = 99.0
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(raw, handle, indent=2)
                handle.write("\n")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "preset-apply",
                        "--config",
                        str(config_path),
                        "--preset",
                        "test-main-best",
                    ]
                )

            self.assertEqual(result, 0)
            updated = load_config(str(config_path))
            self.assertNotEqual(updated.strategy.buy_threshold, 99.0)
        finally:
            if config_path.exists():
                config_path.unlink()
            if preset_path.exists():
                preset_path.unlink()

    def test_cli_profile_save_show_and_list(self):
        config_path = PROJECT_ROOT / "test-main-profile-config.json"
        profile_path = PROJECT_ROOT / "data" / "operator-profiles" / "test-main-paper.json"
        if config_path.exists():
            config_path.unlink()
        if profile_path.exists():
            profile_path.unlink()
        try:
            shutil.copyfile(PROJECT_ROOT / "config.example.json", config_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "profile-save",
                        "--config",
                        str(config_path),
                        "--name",
                        "test-main-paper",
                        "--job-type",
                        "paper-loop",
                        "--market",
                        "KRW-BTC",
                        "--csv",
                        "data/demo_krw_btc_15m.csv",
                        "--state",
                        "data/paper-state.json",
                        "--auto-restart",
                        "--max-restarts",
                        "2",
                        "--restart-backoff-seconds",
                        "1.5",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertTrue(profile_path.exists())

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "profile-show",
                        "--config",
                        str(config_path),
                        "--profile",
                        "test-main-paper",
                    ]
                )

            self.assertEqual(result, 0)
            shown = json.loads(stdout.getvalue())
            self.assertEqual(shown["profile"]["job_type"], "paper-loop")
            self.assertTrue(shown["profile"]["auto_restart"])

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "profile-list",
                        "--config",
                        str(config_path),
                    ]
                )

            self.assertEqual(result, 0)
            listed = json.loads(stdout.getvalue())
            self.assertTrue(any(item["name"] == "test-main-paper" for item in listed["items"]))
        finally:
            if config_path.exists():
                config_path.unlink()
            if profile_path.exists():
                profile_path.unlink()

    def test_cli_session_report_writes_files(self):
        reports_dir = PROJECT_ROOT / "data" / "test-main-reports"
        state_path = PROJECT_ROOT / "data" / "test-main-report-state.json"
        backup_path = pathlib.Path(str(state_path) + ".bak")
        if state_path.exists():
            state_path.unlink()
        if backup_path.exists():
            backup_path.unlink()
        if reports_dir.exists():
            for path in reports_dir.glob("*"):
                path.unlink()
            reports_dir.rmdir()
        try:
            config = load_config(str(PROJECT_ROOT / "config.example.json"))
            config.runtime.journal_path = ""
            runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
            minimum_history = runtime.strategy.minimum_history()
            candles = [
                Candle(
                    timestamp="2026-03-26T11:{0:02d}:00".format(index),
                    open=100.0,
                    high=100.0,
                    low=100.0,
                    close=100.0,
                    volume=1000.0,
                )
                for index in range(minimum_history + 2)
            ]
            runtime.bootstrap(candles[:minimum_history])
            for candle in candles[minimum_history:]:
                runtime.process_candle(candle)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "session-report",
                        "--config",
                        str(PROJECT_ROOT / "config.example.json"),
                        "--state",
                        str(state_path),
                        "--output-dir",
                        str(reports_dir),
                        "--label",
                        "test-main",
                    ]
                )

            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(pathlib.Path(payload["json_path"]).exists())
            self.assertTrue(pathlib.Path(payload["html_path"]).exists())

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "report-list",
                        "--config",
                        str(PROJECT_ROOT / "config.example.json"),
                        "--output-dir",
                        str(reports_dir),
                    ]
                )

            self.assertEqual(result, 0)
            listed = json.loads(stdout.getvalue())
            self.assertEqual(len(listed["items"]), 1)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "report-show",
                        "--config",
                        str(PROJECT_ROOT / "config.example.json"),
                        "--report",
                        payload["json_path"],
                        "--output-dir",
                        str(reports_dir),
                    ]
                )

            self.assertEqual(result, 0)
            shown = json.loads(stdout.getvalue())
            self.assertEqual(shown["json_path"], payload["json_path"])
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()
            if reports_dir.exists():
                for path in reports_dir.glob("*"):
                    path.unlink()
                reports_dir.rmdir()

    def test_cli_job_history_lists_saved_runs(self):
        original_text = JOB_HISTORY_PATH.read_text(encoding="utf-8") if JOB_HISTORY_PATH.exists() else None
        JOB_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(JOB_HISTORY_PATH, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "name": "paper-loop",
                            "status": "completed",
                            "returncode": 0,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "job-history",
                        "--config",
                        str(PROJECT_ROOT / "config.example.json"),
                        "--limit",
                        "5",
                    ]
                )

            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["items"][0]["name"], "paper-loop")
            self.assertEqual(payload["items"][0]["status"], "completed")
        finally:
            if original_text is None:
                if JOB_HISTORY_PATH.exists():
                    JOB_HISTORY_PATH.unlink()
            else:
                JOB_HISTORY_PATH.write_text(original_text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
