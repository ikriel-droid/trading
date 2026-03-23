import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOB_LOG_DIR = PROJECT_ROOT / "data" / "webui-jobs"


@dataclass
class ManagedJob:
    name: str
    kind: str
    command: List[str]
    cwd: str
    log_path: str
    process: subprocess.Popen
    log_handle: Any
    started_at: float


class BackgroundJobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, ManagedJob] = {}
        self._lock = threading.Lock()

    def start_job(self, name: str, kind: str, command: List[str], cwd: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            current = self._jobs.get(name)
            if current is not None and current.process.poll() is None:
                return self._serialize_job(current)

            JOB_LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = str(JOB_LOG_DIR / "{0}.log".format(name))
            log_handle = open(log_path, "a", encoding="utf-8")
            log_handle.write("\n[{0}] starting {1}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(command)))
            log_handle.flush()

            process = subprocess.Popen(
                command,
                cwd=cwd or str(PROJECT_ROOT),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            job = ManagedJob(
                name=name,
                kind=kind,
                command=command,
                cwd=cwd or str(PROJECT_ROOT),
                log_path=log_path,
                process=process,
                log_handle=log_handle,
                started_at=time.time(),
            )
            self._jobs[name] = job
            return self._serialize_job(job)

    def stop_job(self, name: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(name)
            if job is None:
                return {"name": name, "running": False, "found": False}

            if job.process.poll() is None:
                job.process.terminate()
                try:
                    job.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    job.process.kill()
                    job.process.wait(timeout=5)

            if not job.log_handle.closed:
                job.log_handle.write("\n[{0}] stopped\n".format(time.strftime("%Y-%m-%d %H:%M:%S")))
                job.log_handle.flush()
                job.log_handle.close()
            return self._serialize_job(job)

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._serialize_job(job) for job in self._jobs.values()]

    def get_job(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(name)
            return self._serialize_job(job) if job is not None else None

    def stop_all(self) -> None:
        with self._lock:
            names = list(self._jobs.keys())
        for name in names:
            self.stop_job(name)

    def _serialize_job(self, job: ManagedJob) -> Dict[str, Any]:
        return {
            "name": job.name,
            "kind": job.kind,
            "pid": job.process.pid,
            "running": job.process.poll() is None,
            "returncode": job.process.poll(),
            "started_at": job.started_at,
            "command": job.command,
            "cwd": job.cwd,
            "log_path": job.log_path,
            "log_tail": self._tail_log(job.log_path),
        }

    def _tail_log(self, log_path: str, max_lines: int = 40) -> str:
        path = Path(log_path)
        if not path.exists():
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        return "".join(lines[-max_lines:])


def build_paper_loop_command(
    config_path: str,
    state_path: str,
    warmup_csv: Optional[str],
    poll_seconds: Optional[float] = None,
) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "upbit_auto_trader.main",
        "run-loop",
        "--config",
        config_path,
        "--mode",
        "paper",
        "--state",
        state_path,
    ]
    if warmup_csv:
        command.extend(["--warmup-csv", warmup_csv])
    if poll_seconds is not None:
        command.extend(["--poll-seconds", str(poll_seconds)])
    return command


def build_live_daemon_command(
    config_path: str,
    state_path: str,
    warmup_csv: Optional[str],
    poll_seconds: Optional[float] = None,
    reconcile_every_loops: Optional[int] = None,
) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "upbit_auto_trader.main",
        "run-live-daemon",
        "--config",
        config_path,
        "--state",
        state_path,
    ]
    if warmup_csv:
        command.extend(["--warmup-csv", warmup_csv])
    if poll_seconds is not None:
        command.extend(["--poll-seconds", str(poll_seconds)])
    if reconcile_every_loops is not None:
        command.extend(["--reconcile-every-loops", str(reconcile_every_loops)])
    return command
