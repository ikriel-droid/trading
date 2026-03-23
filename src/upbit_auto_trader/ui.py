import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from .backtest import Backtester
from .brokers.upbit import UpbitBroker
from .config import load_config
from .datafeed import load_csv_candles
from .optimizer import run_grid_search
from .runtime import TradingRuntime
from .scanner import MarketScanner
from .strategy import ProfessionalCryptoStrategy


WEBUI_DIR = Path(__file__).with_name("webui")


def load_runtime_summary(config_path: str, state_path: Optional[str], mode: str) -> Optional[Dict[str, Any]]:
    if not state_path or not Path(state_path).exists():
        return None

    config = load_config(config_path)
    runtime = TradingRuntime(config=config, mode="paper", state_path=state_path)
    state = runtime._load_state()  # noqa: SLF001
    if state is None:
        return None
    runtime.state = state
    runtime.mode = mode
    return runtime.summary()


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
    csv_path: Optional[str],
    mode: str,
) -> Dict[str, Any]:
    config = load_config(config_path)
    broker = UpbitBroker(config.upbit)
    payload: Dict[str, Any] = {
        "paths": {
            "config_path": config_path,
            "state_path": state_path or "",
            "csv_path": csv_path or "",
        },
        "app": {
            "market": config.market,
            "mode": mode,
            "poll_seconds": config.runtime.poll_seconds,
            "selector_max_markets": config.selector.max_markets,
        },
        "broker_readiness": broker.readiness_report(),
        "state_summary": load_runtime_summary(config_path, state_path, mode),
        "ui_defaults": {
            "refresh_seconds": 5,
            "optimize_top": 5,
            "scan_max_markets": min(10, config.selector.max_markets),
            "quote_currency": config.selector.quote_currency,
        },
    }

    if csv_path and Path(csv_path).exists():
        candles = load_csv_candles(csv_path)
        payload["csv_info"] = {
            "rows": len(candles),
            "first_timestamp": candles[0].timestamp if candles else "",
            "last_timestamp": candles[-1].timestamp if candles else "",
        }
        payload["chart"] = {
            "points": [
                {
                    "timestamp": candle.timestamp,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in candles[-120:]
            ],
        }
        payload["latest_signal"] = run_signal_action(config_path, csv_path)
    else:
        payload["csv_info"] = None
        payload["chart"] = None
        payload["latest_signal"] = None

    return payload


def _build_handler(
    config_path: str,
    state_path: Optional[str],
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
                        csv_path=csv_path,
                        mode=mode,
                    )
                )
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
    csv_path: Optional[str],
    mode: str,
    host: str,
    port: int,
) -> None:
    handler = _build_handler(config_path=config_path, state_path=state_path, csv_path=csv_path, mode=mode)
    server = ThreadingHTTPServer((host, port), handler)
    print("Web UI listening on http://{0}:{1}".format(host, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
