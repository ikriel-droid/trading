from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from upbit_auto_trader.jobs import BackgroundJobManager, build_paper_loop_command, default_job_heartbeat_path
from upbit_auto_trader.reporting import default_reports_dir


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def _wait_for_job(
    manager: BackgroundJobManager,
    job_name: str,
    predicate,
    timeout_seconds: float,
    pause_seconds: float = 0.5,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] | None = None
    while time.time() < deadline:
        latest = manager.get_job(job_name)
        if latest and predicate(latest):
            return latest
        time.sleep(pause_seconds)
    raise TimeoutError("timed out waiting for job condition: {0}".format(job_name))


def _state_snapshot(path: Path) -> dict[str, Any]:
    payload = _load_json(path) or {}
    return {
        "exists": path.exists(),
        "path": str(path),
        "last_processed_timestamp": str(payload.get("last_processed_timestamp", "")),
        "processed_bars": int(payload.get("processed_bars", 0) or 0),
        "last_order_action": str(payload.get("last_order_action", "")),
        "saved_at": str(payload.get("saved_at", "")),
        "event_count": len(payload.get("events", [])) if isinstance(payload.get("events"), list) else 0,
    }


def _run_powershell(project_root: Path, script_name: str, *extra_args: str) -> subprocess.CompletedProcess[str]:
    powershell_exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    command = [
        str(powershell_exe),
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(project_root / script_name),
        *extra_args,
    ]
    return subprocess.run(command, cwd=str(project_root), check=True, text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the long paper soak test and save evidence.")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--csv", default="data/demo_krw_btc_15m.csv")
    parser.add_argument("--state", default="data/paper-state-soak.json")
    parser.add_argument("--job-name", default="paper-soak-loop")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--warmup-wait", type=float, default=8.0)
    parser.add_argument("--restart-wait", type=float, default=8.0)
    parser.add_argument("--restart-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--report-keep-latest", type=int, default=20)
    parser.add_argument("--support-output", default="dist/upbit-control-room-support-paper-soak")
    parser.add_argument("--support-zip", default="dist/upbit-control-room-support-paper-soak.zip")
    parser.add_argument("--evidence-json", default="dist/paper-soak/long-paper-soak-evidence.json")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    config_path = (project_root / args.config).resolve()
    csv_path = (project_root / args.csv).resolve()
    state_path = (project_root / args.state).resolve()
    backup_state_path = Path(str(state_path) + ".bak")
    evidence_path = (project_root / args.evidence_json).resolve()
    support_output = (project_root / args.support_output).resolve()
    support_zip = (project_root / args.support_zip).resolve()
    reports_dir = Path(default_reports_dir(str(config_path))).resolve()
    heartbeat_path = Path(default_job_heartbeat_path(args.job_name)).resolve()
    job_history_path = project_root / "data" / "webui-job-history.jsonl"
    webui_jobs_dir = project_root / "data" / "webui-jobs"

    state_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    webui_jobs_dir.mkdir(parents=True, exist_ok=True)

    prior_job_history = job_history_path.read_text(encoding="utf-8") if job_history_path.exists() else None
    prior_job_artifacts = {
        path.name: path.read_bytes()
        for path in webui_jobs_dir.glob("{0}*".format(args.job_name))
        if path.is_file()
    }
    for path in webui_jobs_dir.glob("{0}*".format(args.job_name)):
        if path.is_file():
            path.unlink()

    command = build_paper_loop_command(
        config_path=str(config_path),
        state_path=str(state_path),
        warmup_csv=str(csv_path),
        poll_seconds=args.poll_seconds,
    )

    manager = BackgroundJobManager()
    started_at = _iso_now()

    try:
        initial_job = manager.start_job(
            name=args.job_name,
            kind="paper-loop",
            command=command,
            cwd=str(project_root),
            auto_restart=True,
            max_restarts=1,
            restart_backoff_seconds=args.restart_backoff_seconds,
            report_on_exit=True,
            report_config_path=str(config_path),
            report_state_path=str(state_path),
            report_mode="paper",
            report_output_dir=str(reports_dir),
            report_label=args.job_name,
            report_keep_latest=args.report_keep_latest,
        )

        _wait_for_job(
            manager,
            args.job_name,
            lambda job: bool(job.get("running")) and str(job.get("heartbeat_status")) == "healthy",
            timeout_seconds=args.timeout_seconds,
        )
        time.sleep(max(1.0, args.warmup_wait))
        before_restart = _wait_for_job(
            manager,
            args.job_name,
            lambda job: bool(job.get("running"))
            and str(job.get("heartbeat_status")) == "healthy"
            and int((job.get("heartbeat") or {}).get("cycle", 0) or 0) >= 2,
            timeout_seconds=args.timeout_seconds,
        )

        first_pid = int(before_restart["pid"])
        first_heartbeat = before_restart.get("heartbeat") or {}
        first_state = _state_snapshot(state_path)

        subprocess.run(["taskkill", "/PID", str(first_pid), "/F", "/T"], check=True, text=True, capture_output=True)

        _wait_for_job(
            manager,
            args.job_name,
            lambda job: bool(job.get("running"))
            and int(job.get("restart_count", 0) or 0) >= 1
            and int(job.get("pid", 0) or 0) != first_pid
            and str(job.get("heartbeat_status")) == "healthy",
            timeout_seconds=args.timeout_seconds,
        )
        time.sleep(max(1.0, args.restart_wait))
        after_restart = _wait_for_job(
            manager,
            args.job_name,
            lambda job: bool(job.get("running"))
            and int(job.get("restart_count", 0) or 0) >= 1
            and str(job.get("heartbeat_status")) == "healthy"
            and int((job.get("heartbeat") or {}).get("cycle", 0) or 0) >= 1,
            timeout_seconds=args.timeout_seconds,
        )

        second_pid = int(after_restart["pid"])
        second_heartbeat = after_restart.get("heartbeat") or {}
        second_state = _state_snapshot(state_path)

        stop_result = manager.stop_job(args.job_name)
        final_report = stop_result.get("last_report") or {}

        support_build = _run_powershell(
            project_root,
            "build_control_room_support_bundle.ps1",
            "-ConfigPath",
            str(config_path),
            "-StatePath",
            str(state_path),
            "-OutputDirectory",
            str(support_output),
            "-CreateZip",
            "-ZipPath",
            str(support_zip),
        )
        support_verify = _run_powershell(
            project_root,
            "verify_control_room_support_bundle.ps1",
            "-BundleDirectory",
            str(support_output),
            "-ZipPath",
            str(support_zip),
            "-RequireZip",
        )

        finished_at = _iso_now()
        evidence = {
            "started_at": started_at,
            "finished_at": finished_at,
            "job_name": args.job_name,
            "job_kind": "paper-loop",
            "config_path": str(config_path),
            "csv_path": str(csv_path),
            "state_path": str(state_path),
            "backup_state_path": str(backup_state_path),
            "reports_dir": str(reports_dir),
            "heartbeat_path": str(heartbeat_path),
            "job_log_path": str(Path(initial_job["log_path"]).resolve()),
            "initial_run": {
                "pid": first_pid,
                "heartbeat_status": before_restart.get("heartbeat_status"),
                "heartbeat_cycle": first_heartbeat.get("cycle"),
                "heartbeat_updated_at": first_heartbeat.get("updated_at"),
                "state": first_state,
            },
            "restart_run": {
                "observed": second_pid != first_pid,
                "first_pid": first_pid,
                "second_pid": second_pid,
                "restart_count": after_restart.get("restart_count"),
                "heartbeat_status": after_restart.get("heartbeat_status"),
                "heartbeat_cycle": second_heartbeat.get("cycle"),
                "heartbeat_updated_at": second_heartbeat.get("updated_at"),
                "state": second_state,
            },
            "manual_stop": {
                "returncode": stop_result.get("returncode"),
                "termination_reason": stop_result.get("termination_reason"),
                "last_report": final_report,
            },
            "support_bundle": {
                "output_dir": str(support_output),
                "zip_path": str(support_zip),
                "build_stdout": support_build.stdout.strip(),
                "verify_stdout": support_verify.stdout.strip(),
            },
            "checks": {
                "initial_heartbeat_healthy": str(before_restart.get("heartbeat_status")) == "healthy",
                "restart_observed": second_pid != first_pid,
                "post_restart_heartbeat_healthy": str(after_restart.get("heartbeat_status")) == "healthy",
                "state_file_exists": state_path.exists(),
                "backup_state_exists": backup_state_path.exists(),
                "report_generated": bool(final_report.get("json_path")),
                "support_bundle_created": support_output.exists() and support_zip.exists(),
            },
        }

        with open(evidence_path, "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0
    finally:
        for path in webui_jobs_dir.glob("{0}*".format(args.job_name)):
            if path.is_file():
                path.unlink()
        for name, content in prior_job_artifacts.items():
            (webui_jobs_dir / name).write_bytes(content)
        if prior_job_history is None:
            if job_history_path.exists():
                job_history_path.unlink()
        else:
            job_history_path.write_text(prior_job_history, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
