import pathlib
import sys
import time
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.jobs import (  # noqa: E402
    BackgroundJobManager,
    build_live_supervisor_command,
    build_paper_selector_command,
)


class JobTests(unittest.TestCase):
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
        manager = BackgroundJobManager()
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


if __name__ == "__main__":
    unittest.main()
