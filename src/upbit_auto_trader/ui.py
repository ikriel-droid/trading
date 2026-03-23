import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from .backtest import Backtester
from .brokers.upbit import UpbitBroker
from .config import load_config
from .datafeed import load_csv_candles
from .datafeed import merge_candles, upbit_candles_to_internal, write_csv_candles
from .jobs import (
    BackgroundJobManager,
    build_live_daemon_command,
    build_live_supervisor_command,
    build_paper_loop_command,
    build_paper_selector_command,
)
from .optimizer import run_grid_search
from .runtime import TradingRuntime
from .scanner import MarketScanner
from .strategy import ProfessionalCryptoStrategy


WEBUI_DIR = Path(__file__).with_name("webui")
JOB_MANAGER = BackgroundJobManager()
EDITABLE_CONFIG_FIELDS = {
    "strategy.buy_threshold": float,
    "strategy.sell_threshold": float,
    "strategy.min_adx": float,
    "strategy.min_bollinger_width_fraction": float,
    "strategy.volume_spike_multiplier": float,
    "runtime.poll_seconds": float,
    "selector.max_markets": int,
}


def _default_selector_state_path(config_path: str) -> str:
    return str(Path(config_path).resolve().parent / "data" / "selector-state-ui.json")


def _resolve_selector_state_path(config_path: str, selector_state_path: Optional[str]) -> str:
    return selector_state_path or _default_selector_state_path(config_path)


def _load_raw_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_raw_config(config_path: str, payload: Dict[str, Any]) -> None:
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _get_nested_value(payload: Dict[str, Any], dotted_path: str) -> Any:
    current = payload
    parts = dotted_path.split(".")
    for part in parts:
        current = current[part]
    return current


def _set_nested_value(payload: Dict[str, Any], dotted_path: str, value: Any) -> None:
    current = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def load_editable_config(config_path: str) -> Dict[str, Any]:
    payload = _load_raw_config(config_path)
    return {
        field_name: _get_nested_value(payload, field_name)
        for field_name in EDITABLE_CONFIG_FIELDS
    }


def update_editable_config(config_path: str, values: Dict[str, Any]) -> Dict[str, Any]:
    payload = _load_raw_config(config_path)
    updated = {}
    for field_name, caster in EDITABLE_CONFIG_FIELDS.items():
        if field_name not in values:
            continue
        typed_value = caster(values[field_name])
        _set_nested_value(payload, field_name, typed_value)
        updated[field_name] = typed_value
    _save_raw_config(config_path, payload)
    return {
        "config_path": config_path,
        "updated": updated,
        "current": load_editable_config(config_path),
    }


def _load_runtime_for_dashboard(config_path: str, state_path: Optional[str], mode: str) -> Optional[TradingRuntime]:
    if not state_path or not Path(state_path).exists():
        return None

    config = load_config(config_path)
    runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
    state = runtime._load_state()  # noqa: SLF001
    if state is None:
        return None
    runtime.state = state
    runtime.mode = mode
    return runtime


def load_runtime_summary(config_path: str, state_path: Optional[str], mode: str) -> Optional[Dict[str, Any]]:
    runtime = _load_runtime_for_dashboard(config_path, state_path, mode)
    if runtime is None:
        return None
    return runtime.summary()


def _serialize_closed_trade(trade: Any) -> Dict[str, Any]:
    return {
        "market": trade.market,
        "entry_timestamp": trade.entry_timestamp,
        "exit_timestamp": trade.exit_timestamp,
        "entry_price": round(trade.entry_price, 8),
        "exit_price": round(trade.exit_price, 8),
        "quantity": round(trade.quantity, 8),
        "gross_pnl": round(trade.gross_pnl, 8),
        "net_pnl": round(trade.net_pnl, 8),
        "return_pct": round(trade.return_pct, 4),
        "exit_reason": trade.exit_reason,
    }


def _build_recent_activity(runtime: Optional[TradingRuntime]) -> Dict[str, Any]:
    if runtime is None or runtime.state is None:
        return {
            "recent_events": [],
            "recent_trades": [],
        }

    recent_trades = [_serialize_closed_trade(item) for item in runtime.state.closed_trades[-10:]]
    recent_trades.reverse()
    recent_events = list(runtime.state.events[-20:])
    recent_events.reverse()
    return {
        "recent_events": recent_events,
        "recent_trades": recent_trades,
    }


def _chart_points_from_candles(candles: list[Any], limit: int = 120) -> list[Dict[str, Any]]:
    return [
        {
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles[-limit:]
    ]


def _build_chart_markers(chart_points: list[Dict[str, Any]], runtime: Optional[TradingRuntime]) -> list[Dict[str, Any]]:
    if runtime is None or runtime.state is None:
        return []

    visible_timestamps = {point["timestamp"] for point in chart_points}
    markers = []

    for trade in runtime.state.closed_trades[-40:]:
        if trade.entry_timestamp in visible_timestamps:
            markers.append(
                {
                    "timestamp": trade.entry_timestamp,
                    "price": round(trade.entry_price, 8),
                    "side": "buy",
                    "kind": "entry",
                    "label": "B",
                    "note": "trade entry",
                }
            )
        if trade.exit_timestamp in visible_timestamps:
            markers.append(
                {
                    "timestamp": trade.exit_timestamp,
                    "price": round(trade.exit_price, 8),
                    "side": "sell",
                    "kind": "exit",
                    "label": "S",
                    "note": trade.exit_reason,
                    "net_pnl": round(trade.net_pnl, 8),
                }
            )

    if runtime.state.position is not None and runtime.state.position.entry_timestamp in visible_timestamps:
        markers.append(
            {
                "timestamp": runtime.state.position.entry_timestamp,
                "price": round(runtime.state.position.entry_price, 8),
                "side": "buy",
                "kind": "open_position",
                "label": "O",
                "note": "open position",
            }
        )

    markers.sort(key=lambda item: (item["timestamp"], item["kind"], item["price"]))
    return markers


def _build_runtime_chart(runtime: Optional[TradingRuntime]) -> Dict[str, Any]:
    if runtime is None or runtime.state is None:
        return {"points": [], "markers": []}
    chart_points = _chart_points_from_candles(runtime.state.history)
    return {
        "points": chart_points,
        "markers": _build_chart_markers(chart_points, runtime),
    }


def _selector_market_state_path(config_path: str, selector_state_path: str, market: str) -> str:
    config = load_config(config_path)
    project_root = Path(config_path).resolve().parent
    states_dir = Path(config.selector.states_dir)
    if not states_dir.is_absolute():
        states_dir = project_root / states_dir
    return str(states_dir / (market.replace("-", "_") + ".json"))


def load_selector_summary(config_path: str, selector_state_path: Optional[str]) -> Dict[str, Any]:
    resolved_state_path = _resolve_selector_state_path(config_path, selector_state_path)
    if not Path(resolved_state_path).exists():
        return {
            "selector_state_path": resolved_state_path,
            "exists": False,
            "active_market": "",
            "cycle_count": 0,
            "last_selected_market": "",
            "last_selected_score": 0.0,
            "last_scan_timestamp": "",
            "last_scan_results": [],
            "active_market_summary": None,
        }

    with open(resolved_state_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    active_market = payload.get("active_market", "")
    active_market_summary = None
    if active_market:
        active_state_path = _selector_market_state_path(config_path, resolved_state_path, active_market)
        active_runtime = _load_runtime_for_dashboard(config_path, active_state_path, mode="paper")
        active_market_summary = active_runtime.summary() if active_runtime is not None else None
    else:
        active_state_path = ""
        active_runtime = None

    return {
        "selector_state_path": resolved_state_path,
        "exists": True,
        "active_market": active_market,
        "active_market_state_path": active_state_path,
        "cycle_count": int(payload.get("cycle_count", 0)),
        "last_selected_market": payload.get("last_selected_market", ""),
        "last_selected_score": float(payload.get("last_selected_score", 0.0)),
        "last_scan_timestamp": payload.get("last_scan_timestamp", ""),
        "last_scan_results": list(payload.get("last_scan_results", []))[:6],
        "active_market_summary": active_market_summary,
        "active_market_activity": _build_recent_activity(active_runtime),
        "active_market_chart": _build_runtime_chart(active_runtime),
    }


def run_signal_action(config_path: str, csv_path: str) -> Dict[str, Any]:
    config = load_config(config_path)
    candles = load_csv_candles(csv_path)
    signal = ProfessionalCryptoStrategy(config.strategy).evaluate(candles, None)
    return {
        "market": config.market,
        "action": signal.action.value,
        "score": signal.score,
        "confidence": signal.confidence,
        "reasons": signal.reasons,
        "csv_path": csv_path,
    }


def run_scan_action(
    config_path: str,
    max_markets: int = 10,
    quote_currency: Optional[str] = None,
    broker: Optional[UpbitBroker] = None,
) -> Dict[str, Any]:
    config = load_config(config_path)
    if quote_currency:
        config.selector.quote_currency = quote_currency
    config.selector.max_markets = max(1, max_markets)
    broker = broker or UpbitBroker(config.upbit)
    scanner = MarketScanner(config, broker)
    markets = scanner.discover_markets()
    results = scanner.scan_markets(markets)
    return {
        "market": config.market,
        "quote_currency": config.selector.quote_currency,
        "scanned_market_count": len(markets),
        "scan_results": [
            {
                "market": item.market,
                "action": item.action,
                "score": item.score,
                "confidence": item.confidence,
                "reasons": item.reasons,
                "timestamp": item.timestamp,
                "close": item.close,
                "liquidity_24h": item.liquidity_24h,
                "liquidity_ok": item.liquidity_ok,
            }
            for item in results[: max_markets]
        ],
    }


def run_sync_candles_action(
    config_path: str,
    csv_path: str,
    count: Optional[int] = None,
    market: Optional[str] = None,
    broker: Optional[UpbitBroker] = None,
) -> Dict[str, Any]:
    config = load_config(config_path)
    if market:
        config.market = market
        config.upbit.market = market
    broker = broker or UpbitBroker(config.upbit)
    fetch_count = count or config.upbit.candle_count
    payload = broker.get_minute_candles(
        market=config.market,
        unit=config.upbit.candle_unit,
        count=fetch_count,
    )
    incoming = upbit_candles_to_internal(payload)
    existing = load_csv_candles(csv_path) if Path(csv_path).exists() else []
    keep_rows = max(config.runtime.max_history, len(existing) + len(incoming), fetch_count)
    merged = merge_candles(existing, incoming, max_history=keep_rows)
    write_csv_candles(csv_path, merged)
    return {
        "market": config.market,
        "csv_path": csv_path,
        "rows_written": len(merged),
        "first_timestamp": merged[0].timestamp if merged else "",
        "last_timestamp": merged[-1].timestamp if merged else "",
    }


def run_backtest_action(config_path: str, csv_path: str) -> Dict[str, Any]:
    config = load_config(config_path)
    candles = load_csv_candles(csv_path)
    result = Backtester(config).run(candles)
    return {
        "market": config.market,
        "csv_path": csv_path,
        "final_equity": round(result.final_equity, 2),
        "total_return_pct": round(result.total_return_pct, 4),
        "max_drawdown_pct": round(result.max_drawdown_pct, 4),
        "win_rate_pct": round(result.win_rate_pct, 4),
        "trade_count": len(result.trades),
        "recent_events": result.events[-10:],
    }


def run_optimize_action(config_path: str, csv_path: str, top: int = 5) -> Dict[str, Any]:
    config = load_config(config_path)
    candles = load_csv_candles(csv_path)
    results = run_grid_search(
        config=config,
        candles=candles,
        buy_thresholds=[62.0, 65.0, 68.0],
        sell_thresholds=[35.0, 40.0, 45.0],
        min_adx_values=[16.0, 18.0, 20.0],
        min_bollinger_width_values=[0.012, 0.015, 0.018],
        volume_spike_multipliers=[1.2, 1.3, 1.4],
    )
    return {
        "market": config.market,
        "csv_path": csv_path,
        "tested": len(results),
        "top": [
            {
                "rank": index + 1,
                "buy_threshold": item.buy_threshold,
                "sell_threshold": item.sell_threshold,
                "min_adx": item.min_adx,
                "min_bollinger_width_fraction": item.min_bollinger_width_fraction,
                "volume_spike_multiplier": item.volume_spike_multiplier,
                "final_equity": round(item.final_equity, 2),
                "total_return_pct": round(item.total_return_pct, 4),
                "max_drawdown_pct": round(item.max_drawdown_pct, 4),
                "trade_count": item.trade_count,
            }
            for index, item in enumerate(results[: max(1, top)])
        ],
    }


def run_live_reconcile_action(
    config_path: str,
    state_path: Optional[str],
    mode: str,
    market: Optional[str] = None,
    broker: Optional[UpbitBroker] = None,
) -> Dict[str, Any]:
    if not state_path or not Path(state_path).exists():
        return {
            "error": "state file not found",
            "state_path": state_path or "",
        }

    config = load_config(config_path)
    if market:
        config.market = market
        config.upbit.market = market
    broker = broker or UpbitBroker(config.upbit)
    runtime = TradingRuntime(config=config, mode="live", state_path=state_path, broker=broker)
    runtime.bootstrap([])
    return runtime.reconcile_live_snapshot()


def build_dashboard_payload(
    config_path: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    csv_path: Optional[str],
    mode: str,
    job_manager: Optional[BackgroundJobManager] = None,
) -> Dict[str, Any]:
    config = load_config(config_path)
    broker = UpbitBroker(config.upbit)
    job_manager = job_manager or JOB_MANAGER
    runtime = _load_runtime_for_dashboard(config_path, state_path, mode)
    resolved_selector_state_path = _resolve_selector_state_path(config_path, selector_state_path)
    payload: Dict[str, Any] = {
        "paths": {
            "config_path": config_path,
            "state_path": state_path or "",
            "selector_state_path": resolved_selector_state_path,
            "csv_path": csv_path or "",
        },
        "app": {
            "market": config.market,
            "mode": mode,
            "poll_seconds": config.runtime.poll_seconds,
            "selector_max_markets": config.selector.max_markets,
        },
        "broker_readiness": broker.readiness_report(),
        "state_summary": runtime.summary() if runtime is not None else None,
        "selector_summary": load_selector_summary(config_path, resolved_selector_state_path),
        "activity": _build_recent_activity(runtime),
        "editable_config": load_editable_config(config_path),
        "jobs": job_manager.list_jobs(),
        "ui_defaults": {
            "refresh_seconds": 5,
            "optimize_top": 5,
            "scan_max_markets": min(10, config.selector.max_markets),
            "quote_currency": config.selector.quote_currency,
            "reconcile_every": 10,
        },
    }

    if csv_path and Path(csv_path).exists():
        candles = load_csv_candles(csv_path)
        chart_points = _chart_points_from_candles(candles)
        payload["csv_info"] = {
            "rows": len(candles),
            "first_timestamp": candles[0].timestamp if candles else "",
            "last_timestamp": candles[-1].timestamp if candles else "",
        }
        payload["chart"] = {
            "points": chart_points,
            "markers": _build_chart_markers(chart_points, runtime),
        }
        payload["latest_signal"] = run_signal_action(config_path, csv_path)
    else:
        payload["csv_info"] = None
        payload["chart"] = {"points": [], "markers": []}
        payload["latest_signal"] = None

    return payload


def start_managed_job(
    config_path: str,
    job_type: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    csv_path: Optional[str],
    poll_seconds: Optional[float],
    reconcile_every_loops: Optional[int],
    reconcile_every: Optional[int],
    market: Optional[str],
    quote_currency: Optional[str],
    max_markets: Optional[int],
    job_manager: Optional[BackgroundJobManager] = None,
) -> Dict[str, Any]:
    job_manager = job_manager or JOB_MANAGER
    project_root = str(Path(config_path).resolve().parent)
    resolved_selector_state_path = _resolve_selector_state_path(config_path, selector_state_path)

    if job_type == "paper-loop":
        command = build_paper_loop_command(
            config_path=config_path,
            state_path=state_path or "data/paper-state-ui.json",
            warmup_csv=csv_path,
            poll_seconds=poll_seconds,
        )
    elif job_type == "paper-selector":
        command = build_paper_selector_command(
            config_path=config_path,
            selector_state_path=resolved_selector_state_path,
            poll_seconds=poll_seconds,
            quote_currency=quote_currency,
            max_markets=max_markets,
        )
    elif job_type == "live-daemon":
        command = build_live_daemon_command(
            config_path=config_path,
            state_path=state_path or "data/live-state-ui.json",
            warmup_csv=csv_path,
            poll_seconds=poll_seconds,
            reconcile_every_loops=reconcile_every_loops,
        )
    elif job_type == "live-supervisor":
        command = build_live_supervisor_command(
            config_path=config_path,
            state_path=state_path or "data/live-state-ui.json",
            market=market,
            reconcile_every=reconcile_every,
        )
    else:
        return {"error": "unsupported job type", "job_type": job_type}

    return job_manager.start_job(
        name=job_type,
        kind=job_type,
        command=command,
        cwd=project_root,
    )


def stop_managed_job(job_name: str, job_manager: Optional[BackgroundJobManager] = None) -> Dict[str, Any]:
    job_manager = job_manager or JOB_MANAGER
    return job_manager.stop_job(job_name)


def _build_handler(
    config_path: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    csv_path: Optional[str],
    mode: str,
):
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._serve_asset("index.html", "text/html; charset=utf-8")
                return
            if self.path == "/styles.css":
                self._serve_asset("styles.css", "text/css; charset=utf-8")
                return
            if self.path == "/app.js":
                self._serve_asset("app.js", "application/javascript; charset=utf-8")
                return
            if self.path == "/api/dashboard":
                self._write_json(
                    build_dashboard_payload(
                        config_path=config_path,
                        state_path=state_path,
                        selector_state_path=selector_state_path,
                        csv_path=csv_path,
                        mode=mode,
                        job_manager=JOB_MANAGER,
                    )
                )
                return
            if self.path == "/api/jobs":
                self._write_json({"jobs": JOB_MANAGER.list_jobs()})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            body = self._read_json_body()
            if self.path == "/api/signal":
                self._write_json(run_signal_action(config_path, body.get("csv_path") or csv_path or ""))
                return
            if self.path == "/api/backtest":
                self._write_json(run_backtest_action(config_path, body.get("csv_path") or csv_path or ""))
                return
            if self.path == "/api/optimize":
                self._write_json(
                    run_optimize_action(
                        config_path,
                        body.get("csv_path") or csv_path or "",
                        top=int(body.get("top", 5)),
                    )
                )
                return
            if self.path == "/api/scan":
                self._write_json(
                    run_scan_action(
                        config_path=config_path,
                        max_markets=int(body.get("max_markets", 10)),
                        quote_currency=body.get("quote_currency"),
                    )
                )
                return
            if self.path == "/api/reconcile":
                self._write_json(
                    run_live_reconcile_action(
                        config_path=config_path,
                        state_path=body.get("state_path") or state_path,
                        mode=body.get("mode") or mode,
                        market=body.get("market"),
                    )
                )
                return
            if self.path == "/api/sync-candles":
                self._write_json(
                    run_sync_candles_action(
                        config_path=config_path,
                        csv_path=body.get("csv_path") or csv_path or "",
                        count=int(body.get("count", 0)) or None,
                        market=body.get("market"),
                    )
                )
                return
            if self.path == "/api/config-save":
                self._write_json(update_editable_config(config_path, body))
                return
            if self.path == "/api/jobs-start":
                self._write_json(
                    start_managed_job(
                        config_path=config_path,
                        job_type=body.get("job_type", ""),
                        state_path=body.get("state_path") or state_path,
                        selector_state_path=body.get("selector_state_path") or selector_state_path,
                        csv_path=body.get("csv_path") or csv_path,
                        poll_seconds=float(body["poll_seconds"]) if body.get("poll_seconds") not in (None, "") else None,
                        reconcile_every_loops=(
                            int(body["reconcile_every_loops"])
                            if body.get("reconcile_every_loops") not in (None, "")
                            else None
                        ),
                        reconcile_every=(
                            int(body["reconcile_every"])
                            if body.get("reconcile_every") not in (None, "")
                            else None
                        ),
                        market=body.get("market"),
                        quote_currency=body.get("quote_currency"),
                        max_markets=int(body["max_markets"]) if body.get("max_markets") not in (None, "") else None,
                    )
                )
                return
            if self.path == "/api/jobs-stop":
                self._write_json(stop_managed_job(body.get("job_name", "")))
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _serve_asset(self, name: str, content_type: str) -> None:
            data = (WEBUI_DIR / name).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw) if raw else {}

        def _write_json(self, payload: Dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return RequestHandler


def run_web_ui_server(
    config_path: str,
    state_path: Optional[str],
    selector_state_path: Optional[str],
    csv_path: Optional[str],
    mode: str,
    host: str,
    port: int,
) -> None:
    handler = _build_handler(
        config_path=config_path,
        state_path=state_path,
        selector_state_path=selector_state_path,
        csv_path=csv_path,
        mode=mode,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print("Web UI listening on http://{0}:{1}".format(host, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
