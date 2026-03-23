import pathlib
import sys
import time
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.jobs import BackgroundJobManager  # noqa: E402


class JobTests(unittest.TestCase):
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
