import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOB_LOG_DIR = PROJECT_ROOT / "data" / "webui-jobs"
DEFAULT_LOG_MAX_BYTES = 1_000_000
DEFAULT_LOG_BACKUP_COUNT = 3
DEFAULT_WATCHDOG_INTERVAL_SECONDS = 0.5


class RotatingLogWriter:
    def __init__(self, log_path: str, max_bytes: int = DEFAULT_LOG_MAX_BYTES, backup_count: int = DEFAULT_LOG_BACKUP_COUNT) -> None:
        self.path = Path(log_path)
        self.max_bytes = max(0, int(max_bytes))
        self.backup_count = max(0, int(backup_count))
        self._lock = threading.Lock()
        self._handle = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._open_handle()

    def write(self, text: str) -> None:
        if not text:
            return
        encoded = text.encode("utf-8", errors="replace")
        with self._lock:
            self._rotate_if_needed(len(encoded))
            if self._handle is None or self._handle.closed:
                self._open_handle()
            self._handle.write(text)
            self._handle.flush()

    def close(self) -> None:
        with self._lock:
            if self._handle is not None and not self._handle.closed:
                self._handle.flush()
                self._handle.close()
            self._handle = None

    def list_archives(self) -> List[str]:
        archives = []
        for index in range(1, self.backup_count + 1):
            archive_path = self.path.with_name("{0}.{1}".format(self.path.name, index))
            if archive_path.exists():
                archives.append(str(archive_path))
        return archives

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        if self.max_bytes <= 0:
            return

        current_size = self.path.stat().st_size if self.path.exists() else 0
        if current_size + incoming_bytes <= self.max_bytes:
            return

        if self._handle is not None and not self._handle.closed:
            self._handle.flush()
            self._handle.close()

        if self.backup_count > 0:
            oldest = self.path.with_name("{0}.{1}".format(self.path.name, self.backup_count))
            if oldest.exists():
                oldest.unlink()

            for index in range(self.backup_count - 1, 0, -1):
                source = self.path.with_name("{0}.{1}".format(self.path.name, index))
                target = self.path.with_name("{0}.{1}".format(self.path.name, index + 1))
                if source.exists():
                    source.replace(target)

            if self.path.exists():
                self.path.replace(self.path.with_name("{0}.1".format(self.path.name)))
        elif self.path.exists():
            self.path.unlink()

        self._open_handle()

    def _open_handle(self) -> None:
        self._handle = open(self.path, "a", encoding="utf-8")


@dataclass
class ManagedJob:
    name: str
    kind: str
    command: List[str]
    cwd: str
    log_path: str
    process: subprocess.Popen
    log_writer: RotatingLogWriter
    output_thread: threading.Thread
    started_at: float
    auto_restart: bool
    max_restarts: int
    restart_backoff_seconds: float
    restart_count: int
    next_restart_at: float
    last_exit_at: float
    last_returncode: Optional[int]
    manual_stop: bool
    exit_processed: bool


class BackgroundJobManager:
    def __init__(
        self,
        log_max_bytes: int = DEFAULT_LOG_MAX_BYTES,
        log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
        watchdog_interval_seconds: float = DEFAULT_WATCHDOG_INTERVAL_SECONDS,
    ) -> None:
        self._jobs: Dict[str, ManagedJob] = {}
        self._lock = threading.Lock()
        self._log_max_bytes = log_max_bytes
        self._log_backup_count = log_backup_count
        self._watchdog_interval_seconds = max(0.1, watchdog_interval_seconds)
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def start_job(
        self,
        name: str,
        kind: str,
        command: List[str],
        cwd: Optional[str] = None,
        auto_restart: bool = False,
        max_restarts: int = 0,
        restart_backoff_seconds: float = 1.0,
    ) -> Dict[str, Any]:
        with self._lock:
            current = self._jobs.get(name)
            if current is not None and current.process.poll() is None:
                return self._serialize_job(current)
            if current is not None:
                self._finalize_job_resources(current)

            JOB_LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = str(JOB_LOG_DIR / "{0}.log".format(name))
            log_writer = RotatingLogWriter(
                log_path=log_path,
                max_bytes=self._log_max_bytes,
                backup_count=self._log_backup_count,
            )
            log_writer.write("\n[{0}] starting {1}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(command)))
            process, output_thread = self._spawn_process(
                command=command,
                cwd=cwd or str(PROJECT_ROOT),
                log_writer=log_writer,
            )
            job = ManagedJob(
                name=name,
                kind=kind,
                command=command,
                cwd=cwd or str(PROJECT_ROOT),
                log_path=log_path,
                process=process,
                log_writer=log_writer,
                output_thread=output_thread,
                started_at=time.time(),
                auto_restart=bool(auto_restart),
                max_restarts=max(0, int(max_restarts)),
                restart_backoff_seconds=max(0.0, float(restart_backoff_seconds)),
                restart_count=0,
                next_restart_at=0.0,
                last_exit_at=0.0,
                last_returncode=None,
                manual_stop=False,
                exit_processed=False,
            )
            self._jobs[name] = job
            return self._serialize_job(job)

    def stop_job(self, name: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(name)
            if job is None:
                return {"name": name, "running": False, "found": False}

            job.manual_stop = True
            job.next_restart_at = 0.0
            if job.process.poll() is None:
                job.process.terminate()
                try:
                    job.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    job.process.kill()
                    job.process.wait(timeout=5)

            self._join_output_thread(job)
            job.last_returncode = job.process.poll()
            job.last_exit_at = time.time()
            job.exit_processed = True
            job.log_writer.write("\n[{0}] stopped\n".format(time.strftime("%Y-%m-%d %H:%M:%S")))
            self._finalize_job_resources(job)
            return self._serialize_job(job)

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._refresh_jobs_locked()
            return [self._serialize_job(job) for job in self._jobs.values()]

    def get_job(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._refresh_jobs_locked()
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
            "log_archives": job.log_writer.list_archives(),
            "log_tail": self._tail_log(job.log_path),
            "auto_restart": job.auto_restart,
            "max_restarts": job.max_restarts,
            "restart_count": job.restart_count,
            "restart_backoff_seconds": job.restart_backoff_seconds,
            "next_restart_at": job.next_restart_at,
            "last_exit_at": job.last_exit_at,
            "last_returncode": job.last_returncode,
        }

    def _tail_log(self, log_path: str, max_lines: int = 40) -> str:
        path = Path(log_path)
        if not path.exists():
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        return "".join(lines[-max_lines:])

    def _pump_process_output(self, process: subprocess.Popen, log_writer: RotatingLogWriter) -> None:
        if process.stdout is None:
            return
        try:
            for chunk in process.stdout:
                if not chunk:
                    continue
                log_writer.write(chunk)
        finally:
            process.stdout.close()

    def _finalize_job_resources(self, job: ManagedJob) -> None:
        self._join_output_thread(job)
        job.log_writer.close()

    def _join_output_thread(self, job: ManagedJob) -> None:
        if job.output_thread.is_alive():
            job.output_thread.join(timeout=2)

    def _spawn_process(
        self,
        command: List[str],
        cwd: str,
        log_writer: RotatingLogWriter,
    ) -> tuple[subprocess.Popen, threading.Thread]:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output_thread = threading.Thread(
            target=self._pump_process_output,
            args=(process, log_writer),
            daemon=True,
        )
        output_thread.start()
        return process, output_thread

    def _watchdog_loop(self) -> None:
        while True:
            time.sleep(self._watchdog_interval_seconds)
            with self._lock:
                self._refresh_jobs_locked()

    def _refresh_jobs_locked(self) -> None:
        now = time.time()
        for job in self._jobs.values():
            returncode = job.process.poll()
            if returncode is None:
                continue

            if not job.exit_processed:
                self._join_output_thread(job)
                job.last_returncode = returncode
                job.last_exit_at = now
                job.exit_processed = True
                job.log_writer.write(
                    "\n[{0}] exited rc={1}\n".format(
                        time.strftime("%Y-%m-%d %H:%M:%S"),
                        returncode,
                    )
                )
                if (
                    not job.manual_stop
                    and job.auto_restart
                    and returncode != 0
                    and job.restart_count < job.max_restarts
                ):
                    delay = max(0.0, job.restart_backoff_seconds) * (job.restart_count + 1)
                    job.next_restart_at = now + delay
                    job.log_writer.write(
                        "[{0}] restart scheduled in {1:.2f}s ({2}/{3})\n".format(
                            time.strftime("%Y-%m-%d %H:%M:%S"),
                            delay,
                            job.restart_count + 1,
                            job.max_restarts,
                        )
                    )

            if (
                job.exit_processed
                and not job.manual_stop
                and job.auto_restart
                and returncode != 0
                and job.restart_count < job.max_restarts
                and job.next_restart_at > 0
                and now >= job.next_restart_at
            ):
                process, output_thread = self._spawn_process(
                    command=job.command,
                    cwd=job.cwd,
                    log_writer=job.log_writer,
                )
                job.process = process
                job.output_thread = output_thread
                job.started_at = now
                job.restart_count += 1
                job.next_restart_at = 0.0
                job.last_exit_at = 0.0
                job.last_returncode = None
                job.exit_processed = False
                job.log_writer.write(
                    "[{0}] restarted ({1}/{2})\n".format(
                        time.strftime("%Y-%m-%d %H:%M:%S"),
                        job.restart_count,
                        job.max_restarts,
                    )
                )


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


def build_paper_selector_command(
    config_path: str,
    selector_state_path: str,
    poll_seconds: Optional[float] = None,
    quote_currency: Optional[str] = None,
    max_markets: Optional[int] = None,
) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "upbit_auto_trader.main",
        "run-selector",
        "--config",
        config_path,
        "--mode",
        "paper",
        "--selector-state",
        selector_state_path,
    ]
    if quote_currency:
        command.extend(["--quote-currency", quote_currency])
    if max_markets is not None:
        command.extend(["--max-markets", str(max_markets)])
    if poll_seconds is not None:
        command.extend(["--poll-seconds", str(poll_seconds)])
    return command


def build_live_supervisor_command(
    config_path: str,
    state_path: str,
    market: Optional[str] = None,
    reconcile_every: Optional[int] = None,
) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "upbit_auto_trader.main",
        "run-live-supervisor",
        "--config",
        config_path,
        "--state",
        state_path,
    ]
    if market:
        command.extend(["--market", market])
    if reconcile_every is not None:
        command.extend(["--reconcile-every", str(reconcile_every)])
    return command
