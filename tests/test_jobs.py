import pathlib
import sys
import time
import unittest
import uuid


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.jobs import (  # noqa: E402
    BackgroundJobManager,
    JOB_LOG_DIR,
    RotatingLogWriter,
    build_live_supervisor_command,
    build_paper_selector_command,
)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.managers = []

    def tearDown(self):
        for manager in self.managers:
            manager.stop_all()
        for pattern in ("test-job.log*", "rotation-job.log*", "rotation-*.log*", "restart-job.log*"):
            for path in JOB_LOG_DIR.glob(pattern):
                if path.exists():
                    path.unlink()
        flag_path = PROJECT_ROOT / "data" / "test-job-restart-flag.txt"
        if flag_path.exists():
            flag_path.unlink()

    def build_manager(self, **kwargs):
        manager = BackgroundJobManager(**kwargs)
        self.managers.append(manager)
        return manager

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


if __name__ == "__main__":
    unittest.main()
