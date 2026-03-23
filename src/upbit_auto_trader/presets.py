import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .config import StrategyConfig, load_config
from .optimizer import GridSearchResult


DEFAULT_PRESET_DIR = "data/strategy-presets"
PRESET_NAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")
STRATEGY_FIELD_NAMES = tuple(StrategyConfig.__dataclass_fields__.keys())
STRATEGY_SUMMARY_FIELDS = (
    "buy_threshold",
    "sell_threshold",
    "min_adx",
    "min_bollinger_width_fraction",
    "volume_spike_multiplier",
)


def default_preset_dir(config_path: str) -> str:
    return str(Path(config_path).resolve().parent / DEFAULT_PRESET_DIR)


def _config_root(config_path: str) -> Path:
    return Path(config_path).resolve().parent


def _slugify_preset_name(name: str) -> str:
    slug = PRESET_NAME_SANITIZER.sub("-", str(name or "").strip()).strip("-._")
    if not slug:
        raise ValueError("preset name is required")
    return slug.lower()


def _preset_path_for_name(config_path: str, name: str) -> Path:
    return Path(default_preset_dir(config_path)) / "{0}.json".format(_slugify_preset_name(name))


def _filter_strategy_values(strategy_values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: strategy_values[key]
        for key in STRATEGY_FIELD_NAMES
        if key in strategy_values
    }


def _strategy_summary(strategy_values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: strategy_values[key]
        for key in STRATEGY_SUMMARY_FIELDS
        if key in strategy_values
    }


def _looks_like_path(value: str) -> bool:
    return value.endswith(".json") or "/" in value or "\\" in value


def _resolve_preset_path(config_path: str, preset_ref: str) -> Path:
    candidate = Path(str(preset_ref or "").strip())
    if not str(candidate):
        raise ValueError("preset reference is required")

    if candidate.is_absolute():
        if candidate.exists():
            return candidate
        raise ValueError("preset not found: {0}".format(candidate))

    if _looks_like_path(str(candidate)):
        resolved = _config_root(config_path) / candidate
        if resolved.exists():
            return resolved
        raise ValueError("preset not found: {0}".format(resolved))

    resolved = _preset_path_for_name(config_path, str(candidate))
    if resolved.exists():
        return resolved
    raise ValueError("preset not found: {0}".format(resolved))


def list_strategy_presets(config_path: str) -> List[Dict[str, Any]]:
    preset_dir = Path(default_preset_dir(config_path))
    if not preset_dir.exists():
        return []

    items: List[Dict[str, Any]] = []
    for path in preset_dir.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue

        strategy = _filter_strategy_values(payload.get("strategy", {}))
        if not strategy:
            continue

        items.append(
            {
                "name": str(payload.get("name") or path.stem),
                "slug": str(payload.get("slug") or path.stem),
                "path": str(path),
                "created_at": str(payload.get("created_at") or ""),
                "source": str(payload.get("source") or "manual"),
                "market": str(payload.get("market") or ""),
                "csv_path": str(payload.get("csv_path") or ""),
                "summary": _strategy_summary(strategy),
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


def load_strategy_preset(config_path: str, preset_ref: str) -> Dict[str, Any]:
    path = _resolve_preset_path(config_path, preset_ref)
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    strategy = _filter_strategy_values(payload.get("strategy", {}))
    if not strategy:
        raise ValueError("preset has no strategy values: {0}".format(path))

    return {
        "name": str(payload.get("name") or path.stem),
        "slug": str(payload.get("slug") or path.stem),
        "path": str(path),
        "created_at": str(payload.get("created_at") or ""),
        "source": str(payload.get("source") or "manual"),
        "market": str(payload.get("market") or ""),
        "csv_path": str(payload.get("csv_path") or ""),
        "notes": str(payload.get("notes") or ""),
        "strategy": strategy,
        "summary": _strategy_summary(strategy),
    }


def save_strategy_preset(
    config_path: str,
    name: str,
    strategy_values: Dict[str, Any],
    source: str,
    market: str = "",
    csv_path: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    filtered = _filter_strategy_values(strategy_values)
    if not filtered:
        raise ValueError("strategy preset requires at least one strategy value")

    path = _preset_path_for_name(config_path, name)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "name": str(name).strip(),
        "slug": _slugify_preset_name(name),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "market": market,
        "csv_path": csv_path,
        "notes": notes,
        "strategy": filtered,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return load_strategy_preset(config_path, str(path))


def save_current_strategy_preset(
    config_path: str,
    name: str,
    market: str = "",
    csv_path: str = "",
) -> Dict[str, Any]:
    config = load_config(config_path)
    return save_strategy_preset(
        config_path=config_path,
        name=name,
        strategy_values=asdict(config.strategy),
        source="current_config",
        market=market or config.market,
        csv_path=csv_path,
    )


def save_grid_search_best_preset(
    config_path: str,
    name: str,
    result: GridSearchResult,
    market: str = "",
    csv_path: str = "",
) -> Dict[str, Any]:
    config = load_config(config_path)
    strategy_values = asdict(config.strategy)
    strategy_values.update(
        {
            "buy_threshold": float(result.buy_threshold),
            "sell_threshold": float(result.sell_threshold),
            "min_adx": float(result.min_adx),
            "min_bollinger_width_fraction": float(result.min_bollinger_width_fraction),
            "volume_spike_multiplier": float(result.volume_spike_multiplier),
        }
    )
    notes = "final_equity={0:.2f} total_return_pct={1:.4f} trade_count={2}".format(
        result.final_equity,
        result.total_return_pct,
        result.trade_count,
    )
    return save_strategy_preset(
        config_path=config_path,
        name=name,
        strategy_values=strategy_values,
        source="grid_search_best",
        market=market or config.market,
        csv_path=csv_path,
        notes=notes,
    )


def apply_strategy_preset(config_path: str, preset_ref: str) -> Dict[str, Any]:
    preset = load_strategy_preset(config_path, preset_ref)

    with open(config_path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    current_strategy = dict(raw.get("strategy", {}))
    current_strategy.update(preset["strategy"])
    raw["strategy"] = current_strategy

    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(raw, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return {
        "config_path": config_path,
        "preset": {
            "name": preset["name"],
            "slug": preset["slug"],
            "path": preset["path"],
            "created_at": preset["created_at"],
            "source": preset["source"],
            "market": preset["market"],
            "csv_path": preset["csv_path"],
            "summary": preset["summary"],
        },
        "applied_fields": list(preset["strategy"].keys()),
        "current_strategy": _filter_strategy_values(current_strategy),
    }
