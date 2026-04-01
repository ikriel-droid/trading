import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOB_LOG_DIR = PROJECT_ROOT / "data" / "webui-jobs"
JOB_HISTORY_PATH = PROJECT_ROOT / "data" / "webui-job-history.jsonl"
DEFAULT_LOG_MAX_BYTES = 1_000_000
DEFAULT_LOG_BACKUP_COUNT = 3
DEFAULT_WATCHDOG_INTERVAL_SECONDS = 0.5
DEFAULT_HISTORY_LIMIT = 12
DEFAULT_HISTORY_MAX_ENTRIES = 200
DEFAULT_HEARTBEAT_STALE_SECONDS = 45.0
HEARTBEAT_ENV_VAR = "UPBIT_AUTO_TRADER_HEARTBEAT_PATH"


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
        try:
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
        except OSError:
            # On Windows a concurrent reader can temporarily lock the file.
            # In that case keep appending to the active log instead of crashing
            # the background output thread.
            pass

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
    report_on_exit: bool
    report_config_path: str
    report_state_path: str
    report_mode: str
    report_output_dir: str
    report_label: str
    report_keep_latest: Optional[int]
    report_generated: bool
    last_report: Optional[Dict[str, Any]]
    heartbeat_path: str
    termination_reason: str


class BackgroundJobManager:
    def __init__(
        self,
        log_max_bytes: int = DEFAULT_LOG_MAX_BYTES,
        log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
        watchdog_interval_seconds: float = DEFAULT_WATCHDOG_INTERVAL_SECONDS,
        history_path: Optional[str] = None,
        history_max_entries: int = DEFAULT_HISTORY_MAX_ENTRIES,
    ) -> None:
        self._jobs: Dict[str, ManagedJob] = {}
        self._lock = threading.Lock()
        self._log_max_bytes = log_max_bytes
        self._log_backup_count = log_backup_count
        self._watchdog_interval_seconds = max(0.1, watchdog_interval_seconds)
        self._history_path = Path(history_path) if history_path else JOB_HISTORY_PATH
        self._history_max_entries = max(1, int(history_max_entries))
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
        report_on_exit: bool = False,
        report_config_path: str = "",
        report_state_path: str = "",
        report_mode: str = "paper",
        report_output_dir: str = "",
        report_label: str = "",
        report_keep_latest: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            self._refresh_jobs_locked()
            current = self._jobs.get(name)
            if current is not None and current.process.poll() is None:
                return self._serialize_job(current)
            if current is not None:
                self._finalize_job_resources(current)

            JOB_LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = str(JOB_LOG_DIR / "{0}.log".format(name))
            heartbeat_path = default_job_heartbeat_path(name)
            log_writer = RotatingLogWriter(
                log_path=log_path,
                max_bytes=self._log_max_bytes,
                backup_count=self._log_backup_count,
            )
            log_writer.write("\n[{0}] starting {1}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(command)))
            _seed_job_heartbeat(heartbeat_path, name=name, kind=kind, phase="starting")
            process, output_thread = self._spawn_process(
                command=command,
                cwd=cwd or str(PROJECT_ROOT),
                log_writer=log_writer,
                heartbeat_path=heartbeat_path,
            )
            _merge_job_heartbeat(heartbeat_path, pid=process.pid)
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
                report_on_exit=bool(report_on_exit),
                report_config_path=report_config_path,
                report_state_path=report_state_path,
                report_mode=report_mode,
                report_output_dir=report_output_dir,
                report_label=report_label,
                report_keep_latest=report_keep_latest,
                report_generated=False,
                last_report=None,
                heartbeat_path=heartbeat_path,
                termination_reason="",
            )
            self._jobs[name] = job
            return self._serialize_job(job)

    def stop_job(self, name: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(name)
            if job is None:
                return {"name": name, "running": False, "found": False}
            if job.process.poll() is not None and job.exit_processed:
                self._finalize_job_resources(job)
                return self._serialize_job(job)

            job.manual_stop = True
            job.next_restart_at = 0.0
            job.termination_reason = "manual_stop"
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
            self._maybe_generate_exit_report(job)
            job.log_writer.write("\n[{0}] stopped\n".format(time.strftime("%Y-%m-%d %H:%M:%S")))
            self._append_history_entry(job, status="stopped", will_restart=False)
            self._finalize_job_resources(job)
            return self._serialize_job(job)

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._refresh_jobs_locked()
            return [self._serialize_job(job) for job in self._jobs.values()]

    def list_history(self, limit: int = DEFAULT_HISTORY_LIMIT) -> List[Dict[str, Any]]:
        return list_job_history(history_path=str(self._history_path), limit=limit)

    def get_job(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._refresh_jobs_locked()
            job = self._jobs.get(name)
            return self._serialize_job(job) if job is not None else None

    def stop_all(self) -> Dict[str, Any]:
        with self._lock:
            names = list(self._jobs.keys())
        items = [self.stop_job(name) for name in names]
        return {
            "requested": len(names),
            "stopped": sum(1 for item in items if item.get("found", True) and not item.get("running", False)),
            "items": items,
        }

    def cleanup_stopped(self, remove_logs: bool = False) -> Dict[str, Any]:
        with self._lock:
            self._refresh_jobs_locked()
            names = list(self._jobs.keys())
            items: List[Dict[str, Any]] = []
            removed_logs = 0
            skipped_running = 0
            for name in names:
                job = self._jobs.get(name)
                if job is None:
                    continue
                if job.process.poll() is None:
                    skipped_running += 1
                    continue

                self._finalize_job_resources(job)
                removed_heartbeat = _remove_file_if_exists(Path(job.heartbeat_path))
                log_paths = _job_log_paths(Path(job.log_path))
                cleaned_logs = 0
                if remove_logs:
                    for path in log_paths:
                        if _remove_file_if_exists(path):
                            cleaned_logs += 1
                    removed_logs += cleaned_logs

                items.append(
                    {
                        "name": job.name,
                        "kind": job.kind,
                        "heartbeat_path": job.heartbeat_path,
                        "removed_heartbeat": removed_heartbeat,
                        "removed_logs": cleaned_logs,
                        "running": False,
                    }
                )
                self._jobs.pop(name, None)

        return {
            "removed_jobs": len(items),
            "removed_heartbeats": sum(1 for item in items if item.get("removed_heartbeat")),
            "removed_logs": removed_logs,
            "skipped_running": skipped_running,
            "items": items,
        }

    def _serialize_job(self, job: ManagedJob) -> Dict[str, Any]:
        running = job.process.poll() is None
        heartbeat = _load_json_record(Path(job.heartbeat_path))
        heartbeat_age_seconds = _heartbeat_age_seconds(heartbeat)
        heartbeat_status = _heartbeat_status(heartbeat, running=running)
        return {
            "name": job.name,
            "kind": job.kind,
            "pid": job.process.pid,
            "running": running,
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
            "report_on_exit": job.report_on_exit,
            "report_keep_latest": job.report_keep_latest,
            "last_report": job.last_report,
            "heartbeat_path": job.heartbeat_path,
            "heartbeat": heartbeat,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "heartbeat_status": heartbeat_status,
            "heartbeat_healthy": heartbeat_status == "healthy",
            "termination_reason": job.termination_reason,
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
        heartbeat_path: str,
    ) -> tuple[subprocess.Popen, threading.Thread]:
        env = os.environ.copy()
        env[HEARTBEAT_ENV_VAR] = heartbeat_path
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
            env=env,
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
                heartbeat = _load_json_record(Path(job.heartbeat_path))
                if (
                    job.auto_restart
                    and not job.manual_stop
                    and not job.termination_reason
                    and _heartbeat_status(heartbeat, running=True) == "stale"
                ):
                    heartbeat_age_seconds = _heartbeat_age_seconds(heartbeat)
                    job.termination_reason = "stale_heartbeat"
                    job.log_writer.write(
                        "\n[{0}] stale heartbeat detected age={1}s; terminating for restart\n".format(
                            time.strftime("%Y-%m-%d %H:%M:%S"),
                            "{0:.3f}".format(heartbeat_age_seconds) if heartbeat_age_seconds is not None else "unknown",
                        )
                    )
                    job.process.terminate()
                continue

            if not job.exit_processed:
                self._join_output_thread(job)
                job.last_returncode = returncode
                job.last_exit_at = now
                job.exit_processed = True
                restartable_failure = returncode != 0 or job.termination_reason == "stale_heartbeat"
                job.log_writer.write(
                    "\n[{0}] exited rc={1}{2}\n".format(
                        time.strftime("%Y-%m-%d %H:%M:%S"),
                        returncode,
                        " reason={0}".format(job.termination_reason) if job.termination_reason else "",
                    )
                )
                if (
                    not job.manual_stop
                    and job.auto_restart
                    and restartable_failure
                    and job.restart_count < job.max_restarts
                ):
                    will_restart = True
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
                else:
                    will_restart = False
                    self._maybe_generate_exit_report(job)
                status = "retrying" if will_restart else ("completed" if returncode == 0 and not job.termination_reason else "failed")
                self._append_history_entry(job, status=status, will_restart=will_restart)

            if (
                job.exit_processed
                and not job.manual_stop
                and job.auto_restart
                and returncode != 0
                and job.restart_count < job.max_restarts
                and job.next_restart_at > 0
                and now >= job.next_restart_at
            ):
                _seed_job_heartbeat(job.heartbeat_path, name=job.name, kind=job.kind, phase="restarting")
                process, output_thread = self._spawn_process(
                    command=job.command,
                    cwd=job.cwd,
                    log_writer=job.log_writer,
                    heartbeat_path=job.heartbeat_path,
                )
                _merge_job_heartbeat(job.heartbeat_path, pid=process.pid)
                job.process = process
                job.output_thread = output_thread
                job.started_at = now
                job.restart_count += 1
                job.next_restart_at = 0.0
                job.last_exit_at = 0.0
                job.last_returncode = None
                job.exit_processed = False
                job.report_generated = False
                job.last_report = None
                job.termination_reason = ""
                job.log_writer.write(
                    "[{0}] restarted ({1}/{2})\n".format(
                        time.strftime("%Y-%m-%d %H:%M:%S"),
                        job.restart_count,
                        job.max_restarts,
                    )
                )

    def _maybe_generate_exit_report(self, job: ManagedJob) -> None:
        if job.report_generated or not job.report_on_exit:
            return
        if not job.report_config_path or not job.report_state_path:
            return

        try:
            from .reporting import write_runtime_report

            job.last_report = write_runtime_report(
                config_path=job.report_config_path,
                state_path=job.report_state_path,
                mode=job.report_mode,
                output_dir=job.report_output_dir or None,
                label=job.report_label or job.name,
                keep_latest=job.report_keep_latest,
            )
            if job.last_report and job.last_report.get("json_path"):
                job.log_writer.write(
                    "[{0}] session report {1}\n".format(
                        time.strftime("%Y-%m-%d %H:%M:%S"),
                        job.last_report["json_path"],
                    )
                )
        except Exception as exc:  # noqa: BLE001
            job.last_report = {"error": str(exc)}
            job.log_writer.write(
                "[{0}] session report failed: {1}\n".format(
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    exc,
                )
            )
        finally:
            job.report_generated = True

    def _append_history_entry(self, job: ManagedJob, status: str, will_restart: bool) -> None:
        finished_at = job.last_exit_at or time.time()
        heartbeat = _load_json_record(Path(job.heartbeat_path))
        payload = {
            "recorded_at": _iso_utc(time.time()),
            "name": job.name,
            "kind": job.kind,
            "status": status,
            "manual_stop": job.manual_stop,
            "will_restart": will_restart,
            "restart_count": job.restart_count,
            "max_restarts": job.max_restarts,
            "returncode": job.last_returncode,
            "started_at": _iso_utc(job.started_at),
            "finished_at": _iso_utc(finished_at),
            "duration_seconds": round(max(0.0, finished_at - job.started_at), 4),
            "command": list(job.command),
            "cwd": job.cwd,
            "log_path": job.log_path,
            "last_report": job.last_report,
            "heartbeat_path": job.heartbeat_path,
            "heartbeat": heartbeat,
            "heartbeat_phase": str(heartbeat.get("phase", "")) if heartbeat else "",
            "heartbeat_age_seconds": _heartbeat_age_seconds(heartbeat, now=finished_at),
            "exit_reason": job.termination_reason or ("completed" if job.last_returncode == 0 else "process_exit"),
        }
        _append_job_history_record(
            history_path=self._history_path,
            payload=payload,
            max_entries=self._history_max_entries,
        )


def _iso_utc(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def default_job_heartbeat_path(name: str) -> str:
    return str(JOB_LOG_DIR / "{0}.heartbeat.json".format(name))


def _write_json_record(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp_path.replace(path)


def _load_json_record(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _seed_job_heartbeat(path: str, name: str, kind: str, phase: str) -> None:
    _write_json_record(
        Path(path),
        {
            "updated_at": _iso_utc(time.time()),
            "job_name": name,
            "job_kind": kind,
            "phase": phase,
            "stale_after_seconds": DEFAULT_HEARTBEAT_STALE_SECONDS,
        },
    )


def _merge_job_heartbeat(path: str, **fields: Any) -> None:
    current = _load_json_record(Path(path)) or {}
    current.update(fields)
    if "updated_at" not in current:
        current["updated_at"] = _iso_utc(time.time())
    _write_json_record(Path(path), current)


def _heartbeat_age_seconds(heartbeat: Optional[Dict[str, Any]], now: Optional[float] = None) -> Optional[float]:
    if not heartbeat:
        return None
    updated_at = str(heartbeat.get("updated_at", "")).strip()
    if not updated_at:
        return None
    try:
        timestamp = datetime.fromisoformat(updated_at)
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    current = now if now is not None else time.time()
    return round(max(0.0, current - timestamp.timestamp()), 3)


def _heartbeat_status(heartbeat: Optional[Dict[str, Any]], running: bool) -> str:
    if not running:
        return "stopped"
    if not heartbeat:
        return "missing"
    heartbeat_age_seconds = _heartbeat_age_seconds(heartbeat)
    if heartbeat_age_seconds is None:
        return "unknown"
    try:
        stale_after_seconds = max(0.05, float(heartbeat.get("stale_after_seconds", DEFAULT_HEARTBEAT_STALE_SECONDS)))
    except (TypeError, ValueError):
        stale_after_seconds = DEFAULT_HEARTBEAT_STALE_SECONDS
    if heartbeat_age_seconds > stale_after_seconds:
        return "stale"
    return "healthy"


def _append_job_history_record(history_path: Path, payload: Dict[str, Any], max_entries: int) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    records = list_job_history(history_path=str(history_path), limit=max_entries)
    records.insert(0, payload)
    records = records[: max(1, max_entries)]
    with open(history_path, "w", encoding="utf-8") as handle:
        for record in reversed(records):
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")


def list_job_history(history_path: Optional[str] = None, limit: int = DEFAULT_HISTORY_LIMIT) -> List[Dict[str, Any]]:
    path = Path(history_path) if history_path else JOB_HISTORY_PATH
    if not path.exists():
        return []

    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for raw_line in reversed(handle.readlines()):
            line = raw_line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(items) >= max(1, limit):
                break
    return items


def list_job_heartbeats(log_dir: Optional[str] = None, limit: int = DEFAULT_HISTORY_LIMIT) -> List[Dict[str, Any]]:
    path = Path(log_dir) if log_dir else JOB_LOG_DIR
    if not path.exists():
        return []

    items: List[Dict[str, Any]] = []
    for heartbeat_path in path.glob("*.heartbeat.json"):
        payload = _load_json_record(heartbeat_path)
        if not payload:
            continue

        updated_at = str(payload.get("updated_at", "")).strip()
        age_seconds = _heartbeat_age_seconds(payload)
        phase = str(payload.get("phase", "")).strip()
        if phase == "completed":
            status = "completed"
            running = False
        else:
            pid_value = payload.get("pid")
            try:
                pid = int(pid_value)
            except (TypeError, ValueError):
                pid = None
            running = _process_exists(pid) if pid is not None else None
            status = "stopped" if running is False else _heartbeat_status(payload, running=True)

        items.append(
            {
                "job_name": str(payload.get("job_name") or heartbeat_path.name.replace(".heartbeat.json", "")),
                "job_kind": str(payload.get("job_kind") or payload.get("kind") or ""),
                "pid": payload.get("pid"),
                "path": str(heartbeat_path),
                "updated_at": updated_at,
                "phase": phase,
                "stale_after_seconds": payload.get("stale_after_seconds", DEFAULT_HEARTBEAT_STALE_SECONDS),
                "age_seconds": age_seconds,
                "status": status,
                "running": running,
            }
        )

    items.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return items[: max(1, limit)]


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


def build_live_selector_command(
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
        "live",
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


def _process_exists(pid: int) -> bool:
    if pid is None:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return int(exit_code.value) == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _terminate_pid(pid: int, timeout_seconds: float = 5.0) -> Dict[str, Any]:
    if pid <= 0:
        return {"ok": False, "status": "invalid_pid", "pid": pid}

    if not _process_exists(pid):
        return {"ok": False, "status": "not_running", "pid": pid}

    term_requested = False
    try:
        os.kill(pid, signal.SIGTERM)
        term_requested = True
    except PermissionError:
        if os.name != "nt":
            return {"ok": False, "status": "access_denied", "pid": pid}

    deadline = time.time() + max(0.1, timeout_seconds)
    while term_requested and time.time() < deadline and _process_exists(pid):
        time.sleep(0.05)

    if _process_exists(pid) and os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        taskkill_deadline = time.time() + min(max(0.2, timeout_seconds), 1.0)
        while time.time() < taskkill_deadline and _process_exists(pid):
            time.sleep(0.05)
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        running_after_taskkill = _process_exists(pid)
        return {
            "ok": not running_after_taskkill,
            "status": "stopped" if not running_after_taskkill else "timeout",
            "pid": pid,
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    if _process_exists(pid):
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.05)
    return {
        "ok": not _process_exists(pid),
        "status": "stopped" if not _process_exists(pid) else "timeout",
        "pid": pid,
    }


def stop_jobs_by_heartbeat(log_dir: Optional[str] = None, timeout_seconds: float = 5.0) -> Dict[str, Any]:
    items = []
    for heartbeat in list_job_heartbeats(log_dir=log_dir, limit=1000):
        if heartbeat.get("status") == "completed":
            items.append(
                {
                    "job_name": heartbeat.get("job_name", ""),
                    "job_kind": heartbeat.get("job_kind", ""),
                    "heartbeat_path": heartbeat.get("path", ""),
                    "pid": heartbeat.get("pid"),
                    "status": "completed",
                    "ok": False,
                }
            )
            continue

        pid_value = heartbeat.get("pid")
        try:
            pid = int(pid_value)
        except (TypeError, ValueError):
            items.append(
                {
                    "job_name": heartbeat.get("job_name", ""),
                    "job_kind": heartbeat.get("job_kind", ""),
                    "heartbeat_path": heartbeat.get("path", ""),
                    "pid": pid_value,
                    "status": "missing_pid",
                    "ok": False,
                }
            )
            continue

        result = _terminate_pid(pid, timeout_seconds=timeout_seconds)
        items.append(
            {
                "job_name": heartbeat.get("job_name", ""),
                "job_kind": heartbeat.get("job_kind", ""),
                "heartbeat_path": heartbeat.get("path", ""),
                **result,
            }
        )

    return {
        "requested": len(items),
        "stopped": sum(1 for item in items if item.get("status") == "stopped"),
        "items": items,
    }


def _remove_file_if_exists(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        path.unlink()
        return True
    except OSError:
        return False


def _job_log_paths(log_path: Path) -> List[Path]:
    parent = log_path.parent
    return [log_path, *sorted(parent.glob("{0}.*".format(log_path.name)))]


def cleanup_job_artifacts(log_dir: Optional[str] = None, remove_logs: bool = False) -> Dict[str, Any]:
    path = Path(log_dir) if log_dir else JOB_LOG_DIR
    if not path.exists():
        return {
            "removed_jobs": 0,
            "removed_heartbeats": 0,
            "removed_logs": 0,
            "skipped_running": 0,
            "items": [],
        }

    items: List[Dict[str, Any]] = []
    removed_logs = 0
    skipped_running = 0
    for heartbeat in list_job_heartbeats(log_dir=str(path), limit=1000):
        if heartbeat.get("running") is True:
            skipped_running += 1
            continue
        if heartbeat.get("status") not in {"completed", "stopped"}:
            continue

        heartbeat_path = Path(str(heartbeat.get("path", "")))
        removed_heartbeat = _remove_file_if_exists(heartbeat_path)
        cleaned_logs = 0
        if remove_logs:
            log_paths = _job_log_paths(path / "{0}.log".format(str(heartbeat.get("job_name", ""))))
            for log_path in log_paths:
                if _remove_file_if_exists(log_path):
                    cleaned_logs += 1
            removed_logs += cleaned_logs

        items.append(
            {
                "name": str(heartbeat.get("job_name", "")),
                "kind": str(heartbeat.get("job_kind", "")),
                "heartbeat_path": str(heartbeat_path),
                "removed_heartbeat": removed_heartbeat,
                "removed_logs": cleaned_logs,
                "running": False,
                "status": str(heartbeat.get("status", "")),
            }
        )

    return {
        "removed_jobs": len(items),
        "removed_heartbeats": sum(1 for item in items if item.get("removed_heartbeat")),
        "removed_logs": removed_logs,
        "skipped_running": skipped_running,
        "items": items,
    }
