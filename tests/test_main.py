import io
import json
import os
import pathlib
import shutil
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.jobs import HEARTBEAT_ENV_VAR, JOB_HISTORY_PATH  # noqa: E402
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
                        "--report-keep-latest",
                        "14",
                        "--notes",
                        "main paper profile",
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
            self.assertEqual(shown["profile"]["report_keep_latest"], 14)
            self.assertEqual(shown["notes"], "main paper profile")

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

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "profile-preview",
                        "--config",
                        str(config_path),
                        "--profile",
                        "test-main-paper",
                    ]
                )

            self.assertEqual(result, 0)
            previewed = json.loads(stdout.getvalue())
            self.assertEqual(previewed["profile"]["name"], "test-main-paper")
            self.assertEqual(previewed["profile"]["notes"], "main paper profile")
            self.assertTrue(previewed["job_preview"]["can_start"])
            self.assertIn("run-loop", previewed["job_preview"]["command"])
            self.assertEqual(previewed["job_preview"]["report_keep_latest"], 14)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "profile-delete",
                        "--config",
                        str(config_path),
                        "--profile",
                        "test-main-paper",
                    ]
                )

            self.assertEqual(result, 0)
            deleted = json.loads(stdout.getvalue())
            self.assertEqual(deleted["name"], "test-main-paper")
            self.assertTrue(deleted["removed"])
            self.assertFalse(profile_path.exists())
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

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "report-delete",
                        "--config",
                        str(PROJECT_ROOT / "config.example.json"),
                        "--report",
                        payload["json_path"],
                        "--output-dir",
                        str(reports_dir),
                    ]
                )

            self.assertEqual(result, 0)
            deleted = json.loads(stdout.getvalue())
            self.assertTrue(deleted["removed_json"])
            self.assertTrue(deleted["removed_html"])
            self.assertFalse(pathlib.Path(payload["json_path"]).exists())
            self.assertFalse(pathlib.Path(payload["html_path"]).exists())

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
                        "test-main-prune-a",
                    ]
                )
            self.assertEqual(result, 0)
            first_payload = json.loads(stdout.getvalue())

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
                        "test-main-prune-b",
                    ]
                )
            self.assertEqual(result, 0)
            second_payload = json.loads(stdout.getvalue())

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "report-prune",
                        "--config",
                        str(PROJECT_ROOT / "config.example.json"),
                        "--output-dir",
                        str(reports_dir),
                        "--keep",
                        "1",
                    ]
                )

            self.assertEqual(result, 0)
            pruned = json.loads(stdout.getvalue())
            self.assertEqual(pruned["keep"], 1)
            self.assertEqual(pruned["removed_count"], 1)
            self.assertFalse(pathlib.Path(first_payload["json_path"]).exists())
            self.assertTrue(pathlib.Path(second_payload["json_path"]).exists())
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

    def test_cli_session_report_respects_keep_latest(self):
        state_path = PROJECT_ROOT / "data" / "test-main-retention-state.json"
        backup_path = pathlib.Path(str(state_path) + ".bak")
        reports_dir = PROJECT_ROOT / "data" / "test-main-retention-reports"
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
                    timestamp="2026-03-26T12:{0:02d}:00".format(index),
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
                        "test-main-retention-a",
                        "--keep-latest",
                        "1",
                    ]
                )

            self.assertEqual(result, 0)
            first_payload = json.loads(stdout.getvalue())

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
                        "test-main-retention-b",
                        "--keep-latest",
                        "1",
                    ]
                )

            self.assertEqual(result, 0)
            second_payload = json.loads(stdout.getvalue())
            self.assertEqual(second_payload["retention"]["keep"], 1)
            self.assertEqual(second_payload["retention"]["removed_count"], 1)
            self.assertFalse(pathlib.Path(first_payload["json_path"]).exists())
            self.assertTrue(pathlib.Path(second_payload["json_path"]).exists())
        finally:
            if state_path.exists():
                state_path.unlink()
            if backup_path.exists():
                backup_path.unlink()
            if reports_dir.exists():
                for path in reports_dir.glob("*"):
                    path.unlink()
                reports_dir.rmdir()

    def test_cli_job_preview_supports_paper_and_live(self):
        config_path = PROJECT_ROOT / "test-main-job-preview-config.json"
        if config_path.exists():
            config_path.unlink()
        try:
            shutil.copyfile(PROJECT_ROOT / "config.example.json", config_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "job-preview",
                        "--config",
                        str(config_path),
                        "--job-type",
                        "paper-loop",
                        "--state",
                        "data/paper-state.json",
                        "--csv",
                        "data/demo_krw_btc_15m.csv",
                        "--poll-seconds",
                        "15",
                        "--report-keep-latest",
                        "8",
                    ]
                )

            self.assertEqual(result, 0)
            preview = json.loads(stdout.getvalue())
            self.assertTrue(preview["can_start"])
            self.assertIn("run-loop", preview["command"])
            self.assertIn("paper", preview["command"])
            self.assertEqual(preview["report_keep_latest"], 8)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "job-preview",
                        "--config",
                        str(config_path),
                        "--job-type",
                        "live-daemon",
                        "--state",
                        "data/live-state.json",
                    ]
                )

            self.assertEqual(result, 0)
            preview = json.loads(stdout.getvalue())
            self.assertFalse(preview["can_start"])
            self.assertIn("live_enabled=false", preview["blocking_issues"])
            self.assertIn("run-live-daemon", preview["command"])
        finally:
            if config_path.exists():
                config_path.unlink()

    def test_cli_job_stop_all_prints_heartbeat_stop_summary(self):
        stdout = io.StringIO()
        with mock.patch(
            "upbit_auto_trader.main.stop_jobs_by_heartbeat",
            return_value={
                "requested": 2,
                "stopped": 2,
                "items": [
                    {"job_name": "paper-loop", "status": "stopped"},
                    {"job_name": "paper-selector", "status": "stopped"},
                ],
            },
        ) as patched:
            with redirect_stdout(stdout):
                result = main(
                    [
                        "job-stop-all",
                        "--config",
                        str(PROJECT_ROOT / "config.example.json"),
                        "--timeout",
                        "1.5",
                    ]
                )

        self.assertEqual(result, 0)
        patched.assert_called_once_with(timeout_seconds=1.5)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["requested"], 2)
        self.assertEqual(payload["stopped"], 2)

    def test_cli_job_cleanup_prints_cleanup_summary(self):
        stdout = io.StringIO()
        with mock.patch(
            "upbit_auto_trader.main.cleanup_job_artifacts",
            return_value={
                "removed_jobs": 2,
                "removed_heartbeats": 2,
                "removed_logs": 0,
                "skipped_running": 1,
                "items": [
                    {"name": "paper-loop"},
                    {"name": "paper-selector"},
                ],
            },
        ) as patched:
            with redirect_stdout(stdout):
                result = main(
                    [
                        "job-cleanup",
                        "--config",
                        str(PROJECT_ROOT / "config.example.json"),
                    ]
                )

        self.assertEqual(result, 0)
        patched.assert_called_once_with(remove_logs=False)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["removed_jobs"], 2)
        self.assertEqual(payload["skipped_running"], 1)

    def test_run_live_daemon_updates_heartbeat_file(self):
        config = load_config(str(PROJECT_ROOT / "config.example.json"))
        config.runtime.journal_path = ""
        config.upbit.live_enabled = True
        broker = FakeSupervisorBroker()
        state_path = PROJECT_ROOT / "data" / "test-live-daemon-heartbeat-state.json"
        heartbeat_path = PROJECT_ROOT / "data" / "test-live-daemon-heartbeat.json"
        original_heartbeat = os.environ.get(HEARTBEAT_ENV_VAR)
        if state_path.exists():
            state_path.unlink()
        if heartbeat_path.exists():
            heartbeat_path.unlink()
        try:
            os.environ[HEARTBEAT_ENV_VAR] = str(heartbeat_path)
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

            self.assertEqual(result, 0)
            self.assertTrue(heartbeat_path.exists())
            with open(heartbeat_path, "r", encoding="utf-8") as handle:
                heartbeat = json.load(handle)
            self.assertEqual(heartbeat["kind"], "live-daemon")
            self.assertEqual(heartbeat["phase"], "completed")
            self.assertEqual(heartbeat["mode"], "live")
        finally:
            if original_heartbeat is None:
                os.environ.pop(HEARTBEAT_ENV_VAR, None)
            else:
                os.environ[HEARTBEAT_ENV_VAR] = original_heartbeat
            if state_path.exists():
                state_path.unlink()
            if heartbeat_path.exists():
                heartbeat_path.unlink()


if __name__ == "__main__":
    unittest.main()
