import pathlib
import sys
import time
import unittest
import uuid


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.jobs import (  # noqa: E402
    BackgroundJobManager,
    HEARTBEAT_ENV_VAR,
    JOB_LOG_DIR,
    RotatingLogWriter,
    build_live_supervisor_command,
    build_paper_selector_command,
    list_job_history,
    stop_jobs_by_heartbeat,
)
from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402


class JobTests(unittest.TestCase):
    def setUp(self):
        self.managers = []
        self.config_path = PROJECT_ROOT / "config.example.json"
        self.csv_path = PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"
        self.state_path = PROJECT_ROOT / "data" / "test-job-report-state.json"
        self.state_backup_path = pathlib.Path(str(self.state_path) + ".bak")
        self.reports_dir = PROJECT_ROOT / "data" / "session-reports"
        self.history_path = PROJECT_ROOT / "data" / "test-job-history.jsonl"
        if self.state_path.exists():
            self.state_path.unlink()
        if self.state_backup_path.exists():
            self.state_backup_path.unlink()
        if self.history_path.exists():
            self.history_path.unlink()
        if self.reports_dir.exists():
            for path in self.reports_dir.glob("session-report-*-test-job-report*"):
                path.unlink()

    def tearDown(self):
        for manager in self.managers:
            manager.stop_all()
        for pattern in ("test-job.log*", "test-job-*.log*", "rotation-job.log*", "rotation-*.log*", "restart-job.log*", "heartbeat-stop-job.log*"):
            for path in JOB_LOG_DIR.glob(pattern):
                if path.exists():
                    path.unlink()
        for path in JOB_LOG_DIR.glob("*.heartbeat.json"):
            if path.exists():
                path.unlink()
        flag_path = PROJECT_ROOT / "data" / "test-job-restart-flag.txt"
        if flag_path.exists():
            flag_path.unlink()
        stale_flag_path = PROJECT_ROOT / "data" / "test-job-stale-heartbeat-flag.txt"
        if stale_flag_path.exists():
            stale_flag_path.unlink()
        if self.state_path.exists():
            self.state_path.unlink()
        if self.state_backup_path.exists():
            self.state_backup_path.unlink()
        if self.history_path.exists():
            self.history_path.unlink()
        if self.reports_dir.exists():
            for path in self.reports_dir.glob("session-report-*-test-job-report*"):
                path.unlink()

    def build_manager(self, **kwargs):
        kwargs.setdefault("history_path", str(self.history_path))
        manager = BackgroundJobManager(**kwargs)
        self.managers.append(manager)
        return manager

    def _build_runtime_state(self):
        config = load_config(str(self.config_path))
        config.runtime.journal_path = ""
        candles = load_csv_candles(str(self.csv_path))
        runtime = TradingRuntime(config=config, mode="paper", state_path=str(self.state_path))
        minimum_history = runtime.strategy.minimum_history()
        runtime.bootstrap(candles[:minimum_history])
        for candle in candles[minimum_history : minimum_history + 3]:
            runtime.process_candle(candle)
        runtime._save_state()  # noqa: SLF001

    def test_builder_creates_selector_command(self):
        command = build_paper_selector_command(
            config_path="config.example.json",
            selector_state_path="data/selector-state.json",
            poll_seconds=5.0,
            quote_currency="KRW",
            max_markets=12,
        )

        self.assertEqual(command[2], "upbit_auto_trader.main")
        self.assertIn("run-selector", command)
        self.assertIn("paper", command)
        self.assertIn("data/selector-state.json", command)
        self.assertIn("KRW", command)
        self.assertIn("12", command)
        self.assertIn("5.0", command)

    def test_builder_creates_live_supervisor_command(self):
        command = build_live_supervisor_command(
            config_path="config.example.json",
            state_path="data/live-state.json",
            market="KRW-BTC",
            reconcile_every=15,
        )

        self.assertIn("run-live-supervisor", command)
        self.assertIn("data/live-state.json", command)
        self.assertIn("KRW-BTC", command)
        self.assertIn("15", command)

    def test_manager_starts_tracks_and_stops_job(self):
        manager = self.build_manager()
        command = [
            sys.executable,
            "-c",
            "import time; print('job-started'); time.sleep(0.5)",
        ]

        payload = manager.start_job(
            name="test-job",
            kind="test",
            command=command,
            cwd=str(PROJECT_ROOT),
        )
        self.assertTrue(payload["running"])
        time.sleep(0.1)

        jobs = manager.list_jobs()
        self.assertEqual(jobs[0]["name"], "test-job")

        stopped = manager.stop_job("test-job")
        self.assertFalse(stopped["running"])
        self.assertIn("job-started", stopped["log_tail"])
        history = manager.list_history()
        self.assertEqual(history[0]["status"], "stopped")
        self.assertEqual(history[0]["name"], "test-job")

    def test_rotating_log_writer_rotates_when_max_size_is_exceeded(self):
        log_name = "rotation-{0}.log".format(uuid.uuid4().hex)
        log_path = JOB_LOG_DIR / log_name
        writer = RotatingLogWriter(str(log_path), max_bytes=60, backup_count=2)
        try:
            writer.write("A" * 40)
            writer.write("B" * 40)
            writer.write("C" * 40)
        finally:
            writer.close()

        self.assertTrue(log_path.exists())
        self.assertTrue((JOB_LOG_DIR / "{0}.1".format(log_name)).exists())
        self.assertIn(str(JOB_LOG_DIR / "{0}.1".format(log_name)), writer.list_archives())

        for path in [log_path, JOB_LOG_DIR / "{0}.1".format(log_name), JOB_LOG_DIR / "{0}.2".format(log_name)]:
            if path.exists():
                path.unlink()

    def test_manager_exposes_rotated_log_archives(self):
        manager = self.build_manager(log_max_bytes=80, log_backup_count=2)
        command = [
            sys.executable,
            "-c",
            "print('X' * 120); print('Y' * 120)",
        ]

        payload = manager.start_job(
            name="rotation-job",
            kind="test",
            command=command,
            cwd=str(PROJECT_ROOT),
        )
        time.sleep(0.4)
        stopped = manager.stop_job("rotation-job")

        self.assertIn("log_archives", payload)
        self.assertGreaterEqual(len(stopped["log_archives"]), 1)
        self.assertTrue(any(path.endswith(".1") for path in stopped["log_archives"]))

    def test_manager_restarts_failed_job_when_enabled(self):
        manager = self.build_manager(watchdog_interval_seconds=0.05)
        flag_path = PROJECT_ROOT / "data" / "test-job-restart-flag.txt"
        if flag_path.exists():
            flag_path.unlink()
        command = [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "import sys; "
                "path = Path(r'{0}'); "
                "first = not path.exists(); "
                "path.write_text('seen', encoding='utf-8'); "
                "print('attempt-1' if first else 'attempt-2'); "
                "sys.exit(1 if first else 0)"
            ).format(flag_path),
        ]

        manager.start_job(
            name="restart-job",
            kind="test",
            command=command,
            cwd=str(PROJECT_ROOT),
            auto_restart=True,
            max_restarts=1,
            restart_backoff_seconds=0.05,
        )
        time.sleep(0.4)
        payload = manager.get_job("restart-job")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["restart_count"], 1)
        self.assertFalse(payload["running"])
        self.assertEqual(payload["returncode"], 0)
        self.assertIn("attempt-2", payload["log_tail"])

    def test_manager_generates_session_report_when_job_exits(self):
        self._build_runtime_state()
        manager = self.build_manager(watchdog_interval_seconds=0.05)
        command = [
            sys.executable,
            "-c",
            "print('report-job-finished')",
        ]

        manager.start_job(
            name="test-job",
            kind="test",
            command=command,
            cwd=str(PROJECT_ROOT),
            report_on_exit=True,
            report_config_path=str(self.config_path),
            report_state_path=str(self.state_path),
            report_mode="paper",
            report_output_dir=str(self.reports_dir),
            report_label="test-job-report",
        )
        payload = None
        deadline = time.time() + 2.0
        while time.time() < deadline:
            payload = manager.get_job("test-job")
            if payload is not None and payload.get("last_report"):
                break
            time.sleep(0.05)

        self.assertIsNotNone(payload)
        self.assertFalse(payload["running"])
        self.assertIsNotNone(payload["last_report"])
        self.assertTrue(pathlib.Path(payload["last_report"]["json_path"]).exists())
        self.assertTrue(pathlib.Path(payload["last_report"]["html_path"]).exists())
        self.assertIn("test-job-report", payload["last_report"]["json_path"])
        history = list_job_history(history_path=str(self.history_path))
        self.assertEqual(history[0]["status"], "completed")
        self.assertEqual(history[0]["last_report"]["json_path"], payload["last_report"]["json_path"])

    def test_manager_tracks_job_heartbeat(self):
        manager = self.build_manager(watchdog_interval_seconds=0.05)
        command = [
            sys.executable,
            "-c",
            (
                "import json, os, time; "
                "path = os.environ[{0!r}]; "
                "payload = {{'updated_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), 'phase': 'loop', 'stale_after_seconds': 300}}; "
                "json.dump(payload, open(path, 'w', encoding='utf-8')); "
                "time.sleep(0.3)"
            ).format(HEARTBEAT_ENV_VAR),
        ]

        manager.start_job(
            name="test-job",
            kind="test",
            command=command,
            cwd=str(PROJECT_ROOT),
        )
        time.sleep(0.1)
        payload = manager.get_job("test-job")

        self.assertIsNotNone(payload)
        self.assertTrue(payload["running"])
        self.assertTrue(payload["heartbeat_path"].endswith("test-job.heartbeat.json"))
        self.assertEqual(payload["heartbeat"]["phase"], "loop")
        self.assertEqual(payload["heartbeat_status"], "healthy")
        self.assertTrue(payload["heartbeat_healthy"])

    def test_manager_restarts_stale_heartbeat_job_when_enabled(self):
        manager = self.build_manager(watchdog_interval_seconds=0.05)
        flag_path = PROJECT_ROOT / "data" / "test-job-stale-heartbeat-flag.txt"
        if flag_path.exists():
            flag_path.unlink()
        command = [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "import json, os, time, datetime, sys; "
                "flag = Path(r'{0}'); "
                "first = not flag.exists(); "
                "flag.write_text('seen', encoding='utf-8'); "
                "hb = os.environ[{1!r}]; "
                "payload = {{'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'phase': 'loop', 'stale_after_seconds': (0.05 if first else 300)}}; "
                "handle = open(hb, 'w', encoding='utf-8'); "
                "json.dump(payload, handle); "
                "handle.close(); "
                "print('first-run' if first else 'second-run'); "
                "time.sleep(0.6 if first else 0.05); "
                "sys.exit(0)"
            ).format(flag_path, HEARTBEAT_ENV_VAR),
        ]

        manager.start_job(
            name="stale-heartbeat-job",
            kind="test",
            command=command,
            cwd=str(PROJECT_ROOT),
            auto_restart=True,
            max_restarts=1,
            restart_backoff_seconds=0.05,
        )

        payload = None
        deadline = time.time() + 2.0
        while time.time() < deadline:
            payload = manager.get_job("stale-heartbeat-job")
            if payload is not None and not payload["running"] and payload["restart_count"] == 1:
                break
            time.sleep(0.05)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["restart_count"], 1)
        self.assertFalse(payload["running"])
        self.assertEqual(payload["returncode"], 0)
        self.assertIn("second-run", payload["log_tail"])

        history = list_job_history(history_path=str(self.history_path), limit=5)
        self.assertTrue(any(item["status"] == "retrying" and item["exit_reason"] == "stale_heartbeat" for item in history))

    def test_manager_stop_all_returns_stopped_jobs(self):
        manager = self.build_manager()
        command = [
            sys.executable,
            "-c",
            "import time; print('job-a'); time.sleep(1.0)",
        ]
        second_command = [
            sys.executable,
            "-c",
            "import time; print('job-b'); time.sleep(1.0)",
        ]

        manager.start_job(name="test-job-a", kind="test", command=command, cwd=str(PROJECT_ROOT))
        manager.start_job(name="test-job-b", kind="test", command=second_command, cwd=str(PROJECT_ROOT))
        time.sleep(0.1)

        stopped = manager.stop_all()

        self.assertEqual(stopped["requested"], 2)
        self.assertEqual(stopped["stopped"], 2)
        self.assertEqual(len(stopped["items"]), 2)
        self.assertTrue(all(not item["running"] for item in stopped["items"]))

    def test_stop_jobs_by_heartbeat_terminates_running_jobs(self):
        manager = self.build_manager(watchdog_interval_seconds=0.05)
        command = [
            sys.executable,
            "-c",
            "import time; print('heartbeat-stop'); time.sleep(10.0)",
        ]
        manager.start_job(
            name="heartbeat-stop-job",
            kind="test",
            command=command,
            cwd=str(PROJECT_ROOT),
        )
        time.sleep(0.2)

        stopped = stop_jobs_by_heartbeat(log_dir=str(JOB_LOG_DIR), timeout_seconds=2.0)
        time.sleep(0.2)
        payload = manager.get_job("heartbeat-stop-job")

        self.assertEqual(stopped["requested"], 1)
        self.assertEqual(stopped["stopped"], 1)
        self.assertEqual(stopped["items"][0]["job_name"], "heartbeat-stop-job")
        self.assertEqual(stopped["items"][0]["status"], "stopped")
        self.assertIsNotNone(payload)
        self.assertFalse(payload["running"])


if __name__ == "__main__":
    unittest.main()
