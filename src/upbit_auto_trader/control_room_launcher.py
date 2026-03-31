from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, TOP, X, Button, Frame, Label, StringVar, Tk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Dict, Iterable, List


DEFAULT_URL = "http://127.0.0.1:8765"
SCRIPT_NAMES = {
    "launch_hidden": "launch_control_room_hidden.cmd",
    "launch_visible": "launch_control_room.cmd",
    "status": "status_control_room.cmd",
    "stop": "stop_control_room.cmd",
    "helper": "small_live_validation_helper.cmd",
    "checklist": "PRODUCT_COMPLETION_CHECKLIST.md",
    "readme": "README.md",
    "dist": "dist",
}


def _search_roots(base: Path) -> Iterable[Path]:
    if not base:
        return []
    resolved = base.resolve()
    return [resolved, *resolved.parents]


def _dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen: set[str] = set()
    ordered: List[Path] = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def _candidate_roots() -> List[Path]:
    hints = [Path.cwd()]
    try:
        hints.append(Path(__file__).resolve().parents[2])
    except IndexError:
        pass
    hints.append(Path(sys.executable).resolve().parent)
    candidates: List[Path] = []
    for hint in hints:
        candidates.extend(_search_roots(hint))
    return _dedupe_paths(candidates)


def is_project_root(path: Path) -> bool:
    return all((path / marker).exists() for marker in ("launch_control_room_hidden.cmd", "README.md", "PRODUCT_COMPLETION_CHECKLIST.md"))


def find_project_root() -> Path | None:
    for candidate in _candidate_roots():
        if is_project_root(candidate):
            return candidate
    return None


def build_diagnostics(project_root: Path | None) -> Dict[str, Any]:
    root_text = str(project_root) if project_root else ""
    scripts = {}
    if project_root:
        for key, relative_path in SCRIPT_NAMES.items():
            scripts[key] = {
                "path": str(project_root / relative_path),
                "exists": (project_root / relative_path).exists(),
            }
    return {
        "project_root": root_text,
        "found": bool(project_root),
        "default_url": DEFAULT_URL,
        "scripts": scripts,
    }


def build_script_command(project_root: Path, relative_script: str) -> List[str]:
    script_path = project_root / relative_script
    return [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(script_path)]


def run_script(project_root: Path, relative_script: str, *, wait: bool) -> subprocess.Popen[str] | subprocess.CompletedProcess[str]:
    command = build_script_command(project_root, relative_script)
    if wait:
        return subprocess.run(  # noqa: S603
            command,
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
        )
    return subprocess.Popen(command, cwd=project_root)  # noqa: S603


def _open_path(path: Path) -> None:
    os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606


def perform_action(project_root: Path, action: str) -> Dict[str, Any]:
    if action == "diagnose":
        return build_diagnostics(project_root)
    if action == "launch_hidden":
        run_script(project_root, SCRIPT_NAMES["launch_hidden"], wait=False)
        return {"ok": True, "action": action, "message": "Started hidden control room launcher."}
    if action == "launch_visible":
        run_script(project_root, SCRIPT_NAMES["launch_visible"], wait=False)
        return {"ok": True, "action": action, "message": "Started visible control room launcher."}
    if action == "status":
        result = run_script(project_root, SCRIPT_NAMES["status"], wait=True)
        return {
            "ok": result.returncode == 0,
            "action": action,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    if action == "stop":
        result = run_script(project_root, SCRIPT_NAMES["stop"], wait=True)
        return {
            "ok": result.returncode == 0,
            "action": action,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    if action == "helper":
        run_script(project_root, SCRIPT_NAMES["helper"], wait=False)
        return {"ok": True, "action": action, "message": "Opened small live helper."}
    if action == "checklist":
        _open_path(project_root / SCRIPT_NAMES["checklist"])
        return {"ok": True, "action": action, "message": "Opened product completion checklist."}
    if action == "readme":
        _open_path(project_root / SCRIPT_NAMES["readme"])
        return {"ok": True, "action": action, "message": "Opened README."}
    if action == "dist":
        _open_path(project_root / SCRIPT_NAMES["dist"])
        return {"ok": True, "action": action, "message": "Opened dist folder."}
    if action == "browser":
        webbrowser.open(DEFAULT_URL)
        return {"ok": True, "action": action, "message": f"Opened {DEFAULT_URL}."}
    raise ValueError(f"Unsupported action: {action}")


class LauncherApp:
    def __init__(self, project_root: Path | None) -> None:
        self.project_root = project_root
        self.root = Tk()
        self.root.title("Upbit Control Room Launcher")
        self.root.geometry("880x620")
        self.root.minsize(760, 520)
        self.status_var = StringVar()
        self.status_var.set("Project root detected." if project_root else "Project root not found. Place this launcher inside the project or bundle.")
        self._build()
        self.write(build_diagnostics(project_root))

    def _build(self) -> None:
        shell = Frame(self.root, padx=18, pady=18)
        shell.pack(fill=BOTH, expand=True)

        title = Label(shell, text="Upbit Control Room Launcher", font=("Segoe UI", 20, "bold"))
        title.pack(anchor="w")

        subtitle = Label(
            shell,
            text="Start or stop the control room, open the helper, and keep the operator docs close by.",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(4, 10))

        root_text = str(self.project_root) if self.project_root else "project root not detected"
        root_label = Label(shell, text=f"Project: {root_text}", font=("Consolas", 10))
        root_label.pack(anchor="w", pady=(0, 10))

        status_label = Label(shell, textvariable=self.status_var, font=("Segoe UI", 10, "bold"))
        status_label.pack(anchor="w", pady=(0, 12))

        row_one = Frame(shell)
        row_one.pack(fill=X, pady=(0, 8))
        self._make_button(row_one, "Start Hidden", "launch_hidden").pack(side=LEFT, padx=(0, 8))
        self._make_button(row_one, "Start Visible", "launch_visible").pack(side=LEFT, padx=(0, 8))
        self._make_button(row_one, "Open Browser", "browser").pack(side=LEFT, padx=(0, 8))
        self._make_button(row_one, "Status", "status").pack(side=LEFT, padx=(0, 8))
        self._make_button(row_one, "Stop", "stop").pack(side=LEFT)

        row_two = Frame(shell)
        row_two.pack(fill=X, pady=(0, 12))
        self._make_button(row_two, "Open Live Helper", "helper").pack(side=LEFT, padx=(0, 8))
        self._make_button(row_two, "Open Checklist", "checklist").pack(side=LEFT, padx=(0, 8))
        self._make_button(row_two, "Open README", "readme").pack(side=LEFT, padx=(0, 8))
        self._make_button(row_two, "Open Dist", "dist").pack(side=LEFT)

        self.output = ScrolledText(shell, wrap="word", font=("Consolas", 10))
        self.output.pack(fill=BOTH, expand=True)

    def _make_button(self, parent: Frame, label: str, action: str) -> Button:
        state = "normal" if self.project_root else "disabled"
        return Button(parent, text=label, width=18, state=state, command=lambda: self.handle(action))

    def write(self, payload: Dict[str, Any] | str) -> None:
        message = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
        self.output.insert(END, f"{message}\n\n")
        self.output.see(END)

    def handle(self, action: str) -> None:
        if not self.project_root:
            self.status_var.set("Project root not found.")
            return
        result = perform_action(self.project_root, action)
        self.status_var.set(result.get("message", f"Ran {action}."))
        self.write(result)

    def run(self) -> int:
        self.root.mainloop()
        return 0


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Desktop launcher for the Upbit control room")
    parser.add_argument("--diagnose", action="store_true", help="Print project-root diagnostics as JSON and exit.")
    parser.add_argument("--diagnose-write", help="Write project-root diagnostics to a JSON file and exit.")
    parser.add_argument(
        "--action",
        choices=["launch_hidden", "launch_visible", "status", "stop", "helper", "checklist", "readme", "dist", "browser"],
        help="Run one launcher action and exit.",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = find_project_root()
    if args.diagnose_write:
        diagnostics = build_diagnostics(project_root)
        output_path = Path(args.diagnose_write).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
        return 0 if project_root else 1
    if args.diagnose:
        print(json.dumps(build_diagnostics(project_root), indent=2))
        return 0 if project_root else 1
    if args.action:
        if not project_root:
            print(json.dumps({"ok": False, "error": "project_root_not_found"}, indent=2))
            return 1
        print(json.dumps(perform_action(project_root, args.action), indent=2))
        return 0
    app = LauncherApp(project_root)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
