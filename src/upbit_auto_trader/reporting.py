import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .config import load_config
from .runtime import TradingRuntime


DEFAULT_REPORTS_DIR = "data/session-reports"
DEFAULT_REPORT_KEEP_LATEST = 20


def default_reports_dir(config_path: str) -> str:
    return str(Path(config_path).resolve().parent / DEFAULT_REPORTS_DIR)


def _resolve_reports_dir(config_path: str, output_dir: str | None = None) -> Path:
    return Path(output_dir or default_reports_dir(config_path))


def _report_slug(timestamp: str, label: str) -> str:
    safe_label = "".join(character if character.isalnum() or character in ("-", "_") else "-" for character in label.strip())
    safe_label = safe_label.strip("-_")
    base = timestamp.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return "{0}-{1}".format(base, safe_label) if safe_label else base


def _resolve_report_path(config_path: str, report_ref: str, output_dir: str | None = None) -> Path:
    candidate = Path(str(report_ref or "").strip())
    if not str(candidate):
        raise ValueError("report reference is required")

    if candidate.is_absolute():
        if candidate.exists():
            return candidate
        raise ValueError("report not found: {0}".format(candidate))

    reports_dir = _resolve_reports_dir(config_path, output_dir)
    if candidate.suffix == ".json":
        direct_path = reports_dir / candidate
        if direct_path.exists():
            return direct_path

    if "/" in str(candidate) or "\\" in str(candidate):
        direct_path = Path(config_path).resolve().parent / candidate
        if direct_path.exists():
            return direct_path

    for path in reports_dir.glob("session-report-*.json"):
        if path.stem == candidate.stem or path.name == str(candidate):
            return path

    raise ValueError("report not found: {0}".format(report_ref))


def _serialize_trade(trade: Any) -> Dict[str, Any]:
    return {
        "market": trade.market,
        "entry_timestamp": trade.entry_timestamp,
        "exit_timestamp": trade.exit_timestamp,
        "entry_price": round(trade.entry_price, 8),
        "exit_price": round(trade.exit_price, 8),
        "quantity": round(trade.quantity, 8),
        "net_pnl": round(trade.net_pnl, 8),
        "return_pct": round(trade.return_pct, 4),
        "exit_reason": trade.exit_reason,
    }


def build_runtime_report(config_path: str, state_path: str, mode: str = "paper") -> Dict[str, Any]:
    config = load_config(config_path)
    runtime_mode = "paper" if mode == "live" else mode
    runtime = TradingRuntime(config=config, mode=runtime_mode, state_path=state_path)
    runtime.bootstrap([])
    summary = runtime.summary()
    summary["mode"] = mode
    closed_trades = runtime.state.closed_trades if runtime.state is not None else []
    history = runtime.state.history if runtime.state is not None else []
    recent_events = list(runtime.state.events[-40:]) if runtime.state is not None else []

    total_net_pnl = sum(trade.net_pnl for trade in closed_trades)
    winning = [trade for trade in closed_trades if trade.net_pnl > 0]
    losing = [trade for trade in closed_trades if trade.net_pnl < 0]
    average_return_pct = sum(trade.return_pct for trade in closed_trades) / len(closed_trades) if closed_trades else 0.0
    best_trade = max((trade.net_pnl for trade in closed_trades), default=0.0)
    worst_trade = min((trade.net_pnl for trade in closed_trades), default=0.0)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(Path(config_path).resolve()),
        "state_path": str(Path(state_path).resolve()),
        "summary": summary,
        "metrics": {
            "closed_trade_count": len(closed_trades),
            "winning_trade_count": len(winning),
            "losing_trade_count": len(losing),
            "total_net_pnl": round(total_net_pnl, 8),
            "average_trade_return_pct": round(average_return_pct, 4),
            "best_trade_net_pnl": round(best_trade, 8),
            "worst_trade_net_pnl": round(worst_trade, 8),
        },
        "recent_trades": [_serialize_trade(trade) for trade in closed_trades[-20:]],
        "recent_events": recent_events,
        "chart": [
            {
                "timestamp": candle.timestamp,
                "close": candle.close,
                "volume": candle.volume,
            }
            for candle in history[-200:]
        ],
    }


def _render_report_html(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    metrics = report["metrics"]
    trades_rows = "\n".join(
        "<tr><td>{market}</td><td>{entry_timestamp}</td><td>{exit_timestamp}</td><td>{net_pnl}</td><td>{return_pct}</td><td>{exit_reason}</td></tr>".format(
            **trade
        )
        for trade in report["recent_trades"]
    ) or "<tr><td colspan='6'>No closed trades</td></tr>"
    events_rows = "\n".join("<li>{0}</li>".format(event) for event in report["recent_events"]) or "<li>No recent events</li>"

    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Session Report</title>
    <style>
      body {{ font-family: Segoe UI, sans-serif; margin: 32px; background: #f5f1e8; color: #241f1a; }}
      .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .card {{ background: #fffaf2; border: 1px solid #dccfb8; border-radius: 16px; padding: 18px; }}
      h1, h2 {{ margin: 0 0 12px; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #eadfcf; }}
      ul {{ padding-left: 18px; }}
      pre {{ white-space: pre-wrap; word-break: break-word; }}
    </style>
  </head>
  <body>
    <h1>Session Report</h1>
    <p>Generated at {generated_at}</p>
    <div class="grid">
      <section class="card"><h2>Summary</h2><pre>{summary_json}</pre></section>
      <section class="card"><h2>Metrics</h2><pre>{metrics_json}</pre></section>
      <section class="card"><h2>Paths</h2><pre>{paths_json}</pre></section>
    </div>
    <section class="card" style="margin-top: 16px;">
      <h2>Recent Trades</h2>
      <table>
        <thead>
          <tr><th>Market</th><th>Entry</th><th>Exit</th><th>Net PnL</th><th>Return %</th><th>Reason</th></tr>
        </thead>
        <tbody>{trades_rows}</tbody>
      </table>
    </section>
    <section class="card" style="margin-top: 16px;">
      <h2>Recent Events</h2>
      <ul>{events_rows}</ul>
    </section>
  </body>
</html>""".format(
        generated_at=report["generated_at"],
        summary_json=json.dumps(summary, indent=2, ensure_ascii=False),
        metrics_json=json.dumps(metrics, indent=2, ensure_ascii=False),
        paths_json=json.dumps(
            {
                "config_path": report["config_path"],
                "state_path": report["state_path"],
            },
            indent=2,
            ensure_ascii=False,
        ),
        trades_rows=trades_rows,
        events_rows=events_rows,
    )


def _report_summary_item(path: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    html_path = path.with_suffix(".html")
    summary = payload.get("summary", {})
    metrics = payload.get("metrics", {})
    return {
        "name": path.stem,
        "json_path": str(path),
        "html_path": str(html_path) if html_path.exists() else "",
        "generated_at": str(payload.get("generated_at", "")),
        "market": str(summary.get("market", "")),
        "mode": str(summary.get("mode", "")),
        "equity": round(float(summary.get("equity", 0.0) or 0.0), 2),
        "trade_count": int(metrics.get("closed_trade_count", 0) or 0),
        "total_net_pnl": round(float(metrics.get("total_net_pnl", 0.0) or 0.0), 8),
    }


def list_session_reports(config_path: str, output_dir: str | None = None, limit: int = 12) -> List[Dict[str, Any]]:
    reports_dir = _resolve_reports_dir(config_path, output_dir)
    if not reports_dir.exists():
        return []

    items: List[Dict[str, Any]] = []
    for path in reports_dir.glob("session-report-*.json"):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        items.append(_report_summary_item(path, payload))

    items.sort(key=lambda item: str(item.get("generated_at", "")), reverse=True)
    return items[: max(1, limit)]


def load_session_report(config_path: str, report_ref: str, output_dir: str | None = None) -> Dict[str, Any]:
    path = _resolve_report_path(config_path, report_ref, output_dir)
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    return {
        "name": path.stem,
        "json_path": str(path),
        "html_path": str(path.with_suffix(".html")),
        **payload,
    }


def delete_session_report(config_path: str, report_ref: str, output_dir: str | None = None) -> Dict[str, Any]:
    path = _resolve_report_path(config_path, report_ref, output_dir)
    html_path = path.with_suffix(".html")

    removed_json = False
    removed_html = False
    try:
        if path.exists():
            path.unlink()
            removed_json = True
        if html_path.exists():
            html_path.unlink()
            removed_html = True
    except OSError as exc:
        raise ValueError("report delete failed: {0}".format(exc)) from exc

    return {
        "name": path.stem,
        "json_path": str(path),
        "html_path": str(html_path),
        "removed_json": removed_json,
        "removed_html": removed_html,
    }


def prune_session_reports(config_path: str, output_dir: str | None = None, keep: int = 10) -> Dict[str, Any]:
    keep = max(0, int(keep))
    reports_dir = _resolve_reports_dir(config_path, output_dir)
    items = list_session_reports(config_path, output_dir=output_dir, limit=1000)
    kept = items[:keep]
    removed = []
    for item in items[keep:]:
        removed.append(
            delete_session_report(
                config_path=config_path,
                report_ref=str(item.get("json_path", "")),
                output_dir=output_dir,
            )
        )

    return {
        "reports_dir": str(reports_dir),
        "keep": keep,
        "kept_count": len(kept),
        "removed_count": len(removed),
        "removed": removed,
    }


def write_runtime_report(
    config_path: str,
    state_path: str,
    mode: str = "paper",
    output_dir: str | None = None,
    label: str = "",
    keep_latest: int | None = None,
) -> Dict[str, Any]:
    report = build_runtime_report(config_path=config_path, state_path=state_path, mode=mode)
    reports_dir = _resolve_reports_dir(config_path, output_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    slug = _report_slug(report["generated_at"], label)
    json_path = reports_dir / "session-report-{0}.json".format(slug)
    html_path = reports_dir / "session-report-{0}.html".format(slug)

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(_render_report_html(report))

    retention = None
    if keep_latest is not None:
        retention = prune_session_reports(
            config_path=config_path,
            output_dir=output_dir,
            keep=max(1, int(keep_latest)),
        )

    return {
        "generated_at": report["generated_at"],
        "summary": report["summary"],
        "metrics": report["metrics"],
        "json_path": str(json_path),
        "html_path": str(html_path),
        "retention": retention,
    }
