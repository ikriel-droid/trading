import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_PROFILE_DIR = "data/operator-profiles"
PROFILE_NAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")
SUPPORTED_JOB_TYPES = {
    "paper-loop",
    "paper-selector",
    "live-daemon",
    "live-supervisor",
}


def default_profile_dir(config_path: str) -> str:
    return str(Path(config_path).resolve().parent / DEFAULT_PROFILE_DIR)


def _config_root(config_path: str) -> Path:
    return Path(config_path).resolve().parent


def _slugify_profile_name(name: str) -> str:
    slug = PROFILE_NAME_SANITIZER.sub("-", str(name or "").strip()).strip("-._")
    if not slug:
        raise ValueError("profile name is required")
    return slug.lower()


def _profile_path_for_name(config_path: str, name: str) -> Path:
    return Path(default_profile_dir(config_path)) / "{0}.json".format(_slugify_profile_name(name))


def _looks_like_path(value: str) -> bool:
    return value.endswith(".json") or "/" in value or "\\" in value


def _resolve_profile_path(config_path: str, profile_ref: str) -> Path:
    candidate = Path(str(profile_ref or "").strip())
    if not str(candidate):
        raise ValueError("profile reference is required")

    if candidate.is_absolute():
        if candidate.exists():
            return candidate
        raise ValueError("profile not found: {0}".format(candidate))

    if _looks_like_path(str(candidate)):
        resolved = _config_root(config_path) / candidate
        if resolved.exists():
            return resolved
        raise ValueError("profile not found: {0}".format(resolved))

    resolved = _profile_path_for_name(config_path, str(candidate))
    if resolved.exists():
        return resolved
    raise ValueError("profile not found: {0}".format(resolved))


def _normalize_profile_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    job_type = str(payload.get("job_type") or "").strip()
    if job_type not in SUPPORTED_JOB_TYPES:
        raise ValueError("unsupported job type: {0}".format(job_type or ""))

    return {
        "job_type": job_type,
        "market": str(payload.get("market") or ""),
        "csv_path": str(payload.get("csv_path") or ""),
        "state_path": str(payload.get("state_path") or ""),
        "selector_state_path": str(payload.get("selector_state_path") or ""),
        "quote_currency": str(payload.get("quote_currency") or ""),
        "max_markets": int(payload.get("max_markets", 0) or 0),
        "poll_seconds": float(payload.get("poll_seconds", 0.0) or 0.0),
        "reconcile_every": int(payload.get("reconcile_every", 0) or 0),
        "reconcile_every_loops": int(payload.get("reconcile_every_loops", 0) or 0),
        "preset": str(payload.get("preset") or ""),
        "auto_restart": bool(payload.get("auto_restart", False)),
        "max_restarts": int(payload.get("max_restarts", 0) or 0),
        "restart_backoff_seconds": float(payload.get("restart_backoff_seconds", 0.0) or 0.0),
        "report_keep_latest": int(payload.get("report_keep_latest", 0) or 0),
    }


def _profile_summary(profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_type": profile["job_type"],
        "market": profile["market"],
        "preset": profile["preset"],
        "auto_restart": profile["auto_restart"],
        "max_restarts": profile["max_restarts"],
        "report_keep_latest": profile["report_keep_latest"],
    }


def list_operator_profiles(config_path: str) -> List[Dict[str, Any]]:
    profile_dir = Path(default_profile_dir(config_path))
    if not profile_dir.exists():
        return []

    items: List[Dict[str, Any]] = []
    for path in profile_dir.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            profile = _normalize_profile_payload(payload.get("profile", {}))
        except (OSError, json.JSONDecodeError, ValueError):
            continue

        items.append(
            {
                "name": str(payload.get("name") or path.stem),
                "slug": str(payload.get("slug") or path.stem),
                "path": str(path),
                "created_at": str(payload.get("created_at") or ""),
                "notes": str(payload.get("notes") or ""),
                "summary": _profile_summary(profile),
            }
        )

    items.sort(
        key=lambda item: (
            str(item.get("created_at", "")),
            str(item.get("name", "")),
        ),
        reverse=True,
    )
    return items


def load_operator_profile(config_path: str, profile_ref: str) -> Dict[str, Any]:
    path = _resolve_profile_path(config_path, profile_ref)
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    profile = _normalize_profile_payload(payload.get("profile", {}))
    return {
        "name": str(payload.get("name") or path.stem),
        "slug": str(payload.get("slug") or path.stem),
        "path": str(path),
        "created_at": str(payload.get("created_at") or ""),
        "notes": str(payload.get("notes") or ""),
        "profile": profile,
        "summary": _profile_summary(profile),
    }


def save_operator_profile(
    config_path: str,
    name: str,
    profile_payload: Dict[str, Any],
    notes: str = "",
) -> Dict[str, Any]:
    profile = _normalize_profile_payload(profile_payload)
    path = _profile_path_for_name(config_path, name)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "name": str(name).strip(),
        "slug": _slugify_profile_name(name),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
        "profile": profile,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return load_operator_profile(config_path, str(path))


def delete_operator_profile(config_path: str, profile_ref: str) -> Dict[str, Any]:
    loaded = load_operator_profile(config_path, profile_ref)
    path = Path(loaded["path"])
    removed = False
    try:
        if path.exists():
            path.unlink()
            removed = True
    except OSError as exc:
        raise ValueError("profile delete failed: {0}".format(exc)) from exc

    return {
        "name": loaded["name"],
        "slug": loaded["slug"],
        "path": str(path),
        "removed": removed,
    }
