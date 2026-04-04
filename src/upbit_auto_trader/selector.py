import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import AppConfig
from .datafeed import merge_candles, upbit_candles_to_internal, upbit_websocket_candle_to_internal
from .runtime import TradingRuntime
from .scanner import MarketScanResult, MarketScanner


@dataclass
class SelectorState:
    candle_unit: int = 0
    active_market: str = ""
    cycle_count: int = 0
    last_selected_market: str = ""
    last_selected_score: float = 0.0
    last_scan_timestamp: str = ""
    last_scan_results: List[Dict[str, Any]] = field(default_factory=list)


class RotatingMarketSelector:
    def __init__(self, config: AppConfig, mode: str, selector_state_path: str, broker) -> None:
        if mode not in ("paper", "live"):
            raise ValueError("mode must be paper or live")

        self.config = config
        self.mode = mode
        self.selector_state_path = os.fspath(selector_state_path)
        self.broker = broker
        self.scanner = MarketScanner(config, broker)
        self._state_restore_notice = ""
        self.state = self._load_state()

    def run_cycle(self, markets: Optional[List[str]] = None) -> Dict[str, Any]:
        results: List[MarketScanResult] = []
        active_summary = None
        events: List[str] = self._consume_state_restore_notice()

        if self.state.active_market:
            active_summary, events = self._update_market_runtime(self.state.active_market)
            if active_summary["position"] is None:
                self.state.active_market = ""

        if not self.state.active_market:
            candidate_markets = markets or self.scanner.discover_markets()
            results = self.scanner.scan_markets(candidate_markets)
            self.state.last_scan_results = [self._serialize_scan_result(item) for item in results[:10]]
            self.state.last_scan_timestamp = results[0].timestamp if results else ""

            selected = self._pick_candidate(results)
            if selected is not None:
                self.state.last_selected_market = selected.market
                self.state.last_selected_score = selected.score
                active_summary, new_events = self._update_market_runtime(selected.market)
                events.extend(new_events)
                if active_summary["position"] is not None:
                    self.state.active_market = selected.market
                else:
                    self.state.active_market = ""

        self.state.cycle_count += 1
        self._save_state()
        return {
            "mode": self.mode,
            "active_market": self.state.active_market,
            "active_summary": active_summary,
            "events": events,
            "cycle_count": self.state.cycle_count,
            "last_selected_market": self.state.last_selected_market,
            "last_selected_score": self.state.last_selected_score,
            "candle_unit": self.state.candle_unit,
            "scan_results": self.state.last_scan_results,
            "selector_state_path": self.selector_state_path,
        }

    def _pick_candidate(self, results: List[MarketScanResult]) -> Optional[MarketScanResult]:
        for item in results:
            if not self._passes_selector_filters(item):
                continue
            return item
        return None

    def _passes_selector_filters(self, item: MarketScanResult) -> bool:
        if self.config.selector.require_buy_action and item.action != "BUY":
            return False
        if item.score < self.config.selector.min_score:
            return False
        if not item.liquidity_ok:
            return False
        return True

    def _update_market_runtime(self, market: str) -> tuple[Dict[str, Any], List[str]]:
        candles = self._fetch_market_candles(market)
        return self._update_market_runtime_from_history(market, candles)

    def _update_market_runtime_from_history(self, market: str, candles) -> tuple[Dict[str, Any], List[str]]:
        market_config = self._market_config(market)
        state_path = self._market_state_path(market)
        runtime = TradingRuntime(config=market_config, mode=self.mode, state_path=state_path, broker=self.broker)
        minimum_history = runtime.strategy.minimum_history()

        if len(candles) < minimum_history:
            raise ValueError(
                "market {0} has insufficient candles: need {1}, got {2}".format(
                    market,
                    minimum_history,
                    len(candles),
                )
            )

        # Always pass warmup candles. If the saved runtime state is still valid,
        # TradingRuntime.bootstrap will restore it and ignore the warmup data.
        # If the saved state is stale (for example an older candle unit), the
        # same warmup data lets the runtime recover immediately instead of
        # failing with an empty bootstrap.
        runtime.bootstrap(candles[:minimum_history])

        events = []
        last_timestamp = runtime.state.last_processed_timestamp
        for candle in candles:
            if last_timestamp and candle.timestamp <= last_timestamp:
                continue
            events.extend(runtime.process_candle(candle))
            last_timestamp = runtime.state.last_processed_timestamp
        return runtime.summary(), events

    def _fetch_market_candles(self, market: str):
        fetch_count = max(self.config.upbit.candle_count, self.scanner.strategy.minimum_history() + 5)
        payload = self.broker.get_minute_candles(
            market=market,
            unit=self.config.upbit.candle_unit,
            count=fetch_count,
        )
        return upbit_candles_to_internal(payload)

    def _market_config(self, market: str) -> AppConfig:
        market_config = copy.deepcopy(self.config)
        market_config.market = market
        market_config.upbit.market = market
        return market_config

    def _market_state_path(self, market: str) -> str:
        states_dir = os.fspath(self.config.selector.states_dir)
        os.makedirs(states_dir, exist_ok=True)
        filename = market.replace("-", "_") + ".json"
        return os.path.join(states_dir, filename)

    def _load_state(self) -> SelectorState:
        if not os.path.exists(self.selector_state_path):
            return SelectorState(candle_unit=int(self.config.upbit.candle_unit))
        with open(self.selector_state_path, "r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        state_candle_unit = int(payload.get("candle_unit", 0) or 0)
        expected_candle_unit = int(self.config.upbit.candle_unit)
        if state_candle_unit != expected_candle_unit:
            self._state_restore_notice = "SELECTOR STATE RESET reason=candle_unit_mismatch expected={0} actual={1}".format(
                expected_candle_unit,
                state_candle_unit or "<missing>",
            )
            return SelectorState(candle_unit=expected_candle_unit)
        return SelectorState(
            candle_unit=state_candle_unit,
            active_market=payload.get("active_market", ""),
            cycle_count=int(payload.get("cycle_count", 0)),
            last_selected_market=payload.get("last_selected_market", ""),
            last_selected_score=float(payload.get("last_selected_score", 0.0)),
            last_scan_timestamp=payload.get("last_scan_timestamp", ""),
            last_scan_results=list(payload.get("last_scan_results", [])),
        )

    def _save_state(self) -> None:
        directory = os.path.dirname(self.selector_state_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.selector_state_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "candle_unit": int(self.config.upbit.candle_unit),
                    "active_market": self.state.active_market,
                    "cycle_count": self.state.cycle_count,
                    "last_selected_market": self.state.last_selected_market,
                    "last_selected_score": self.state.last_selected_score,
                    "last_scan_timestamp": self.state.last_scan_timestamp,
                    "last_scan_results": self.state.last_scan_results,
                },
                handle,
                indent=2,
            )

    def _serialize_scan_result(self, item: MarketScanResult) -> Dict[str, Any]:
        return {
            "market": item.market,
            "action": item.action,
            "score": item.score,
            "confidence": item.confidence,
            "candle_unit": item.candle_unit,
            "reasons": item.reasons,
            "timestamp": item.timestamp,
            "close": item.close,
            "candle_count": item.candle_count,
            "market_warning": item.market_warning,
            "liquidity_24h": item.liquidity_24h,
            "recent_bid_ratio": item.recent_bid_ratio,
            "recent_trade_notional": item.recent_trade_notional,
            "liquidity_ok": item.liquidity_ok,
            "trade_flow_ok": item.trade_flow_ok,
            "spread_bps": item.spread_bps,
            "top_bid_ask_ratio": item.top_bid_ask_ratio,
            "total_bid_ask_ratio": item.total_bid_ask_ratio,
            "orderbook_ok": item.orderbook_ok,
        }

    def _consume_state_restore_notice(self) -> List[str]:
        if not self._state_restore_notice:
            return []
        notice = self._state_restore_notice
        self._state_restore_notice = ""
        return [notice]


class StreamingMarketSelector(RotatingMarketSelector):
    def __init__(self, config: AppConfig, mode: str, selector_state_path: str, broker) -> None:
        super().__init__(config=config, mode=mode, selector_state_path=selector_state_path, broker=broker)
        self.histories: Dict[str, list] = {}
        self.market_warnings: Dict[str, str] = {}
        self.market_liquidity_24h: Dict[str, float] = {}
        self.recent_trades: Dict[str, List[Dict[str, float]]] = {}
        self.last_trade_ids: Dict[str, int] = {}
        self.market_orderbooks: Dict[str, Dict[str, float]] = {}

    def bootstrap_markets(self, markets: Optional[List[str]] = None) -> List[str]:
        selected_markets = markets or self.scanner.discover_markets()
        market_details = self.broker.list_markets(is_details=True)
        self.market_warnings = {
            item.get("market", ""): (item.get("market_warning") or "").upper() for item in market_details
        }
        if hasattr(self.broker, "get_ticker"):
            for item in self.broker.get_ticker(selected_markets):
                market = item.get("market") or item.get("code")
                self.market_liquidity_24h[market] = float(item.get("acc_trade_price_24h", 0.0))
        for market in selected_markets:
            self.histories[market] = self._fetch_market_candles(market)
            self.recent_trades.setdefault(market, [])
        return selected_markets

    def process_stream_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload_type = payload.get("type", "")
        market = payload["code"]
        candle_timestamp = ""
        updated_bar = False

        if payload_type == "ticker":
            self.market_liquidity_24h[market] = float(payload.get("acc_trade_price_24h", 0.0))
        elif payload_type == "trade":
            self._append_trade_event(market, payload)
        elif payload_type == "orderbook":
            self._update_orderbook(market, payload)
        elif payload_type.startswith("candle."):
            candle = upbit_websocket_candle_to_internal(payload)
            candle_timestamp = candle.timestamp
            current_history = self.histories.get(market, [])
            previous_timestamp = current_history[-1].timestamp if current_history else ""
            self.histories[market] = merge_candles(
                current_history,
                [candle],
                max_history=max(self.config.runtime.max_history, self.config.upbit.candle_count),
            )
            updated_bar = candle.timestamp != previous_timestamp

        active_summary = None
        events: List[str] = self._consume_state_restore_notice()

        if self.state.active_market and market == self.state.active_market and payload_type.startswith("candle.") and updated_bar:
            active_summary, new_events = self._update_market_runtime_from_history(market, self.histories[market])
            events.extend(new_events)
            if active_summary["position"] is None:
                self.state.active_market = ""

        if not self.state.active_market and payload_type.startswith("candle.") and updated_bar:
            scan_results = self._scan_from_histories()
            self.state.last_scan_results = [self._serialize_scan_result(item) for item in scan_results[:10]]
            self.state.last_scan_timestamp = scan_results[0].timestamp if scan_results else ""
            selected = self._pick_candidate(scan_results)
            if selected is not None:
                self.state.last_selected_market = selected.market
                self.state.last_selected_score = selected.score
                active_summary, new_events = self._update_market_runtime_from_history(
                    selected.market,
                    self.histories[selected.market],
                )
                events.extend(new_events)
                if active_summary["position"] is not None:
                    self.state.active_market = selected.market
                else:
                    self.state.active_market = ""

        self.state.cycle_count += 1
        self._save_state()
        return {
            "mode": self.mode,
            "active_market": self.state.active_market,
            "active_summary": active_summary,
            "events": events,
            "cycle_count": self.state.cycle_count,
            "last_selected_market": self.state.last_selected_market,
            "last_selected_score": self.state.last_selected_score,
            "candle_unit": self.state.candle_unit,
            "scan_results": self.state.last_scan_results,
            "selector_state_path": self.selector_state_path,
            "event_market": market,
            "event_timestamp": candle_timestamp or payload.get("trade_timestamp") or payload.get("timestamp", ""),
            "payload_type": payload_type,
            "stream_type": payload.get("stream_type", ""),
        }

    def _scan_from_histories(self) -> List[MarketScanResult]:
        results = []
        for market, candles in self.histories.items():
            bid_ratio, recent_trade_notional, trade_flow_ok = self._trade_flow_metrics(market)
            spread_bps, top_bid_ask_ratio, total_bid_ask_ratio, orderbook_ok = self._orderbook_metrics(market)
            result = self.scanner.evaluate_candles(
                market,
                candles,
                market_warning=self.market_warnings.get(market, ""),
                liquidity_24h=self.market_liquidity_24h.get(market, 0.0),
                recent_bid_ratio=bid_ratio,
                recent_trade_notional=recent_trade_notional,
                trade_flow_ok=trade_flow_ok,
            )
            if result is not None:
                result.spread_bps = spread_bps
                result.top_bid_ask_ratio = top_bid_ask_ratio
                result.total_bid_ask_ratio = total_bid_ask_ratio
                result.orderbook_ok = orderbook_ok
                results.append(result)
        results.sort(
            key=lambda item: (
                1 if item.action == "BUY" else 0,
                1 if item.liquidity_ok else 0,
                1 if item.trade_flow_ok else 0,
                1 if item.orderbook_ok else 0,
                item.score,
                item.confidence,
                item.recent_bid_ratio,
                item.total_bid_ask_ratio,
                item.liquidity_24h,
                item.close,
                item.market,
            ),
            reverse=True,
        )
        return results

    def _pick_candidate(self, results: List[MarketScanResult]) -> Optional[MarketScanResult]:
        for item in results:
            if not super()._passes_selector_filters(item):
                continue
            if self.config.selector.use_trade_flow_filter and not item.trade_flow_ok:
                continue
            if self.config.selector.use_orderbook_filter and not item.orderbook_ok:
                continue
            return item
        return None

    def _append_trade_event(self, market: str, payload: Dict[str, Any]) -> None:
        sequential_id = int(payload.get("sequential_id", 0))
        if sequential_id and self.last_trade_ids.get(market) == sequential_id:
            return
        if sequential_id:
            self.last_trade_ids[market] = sequential_id

        notional = float(payload.get("trade_price", 0.0)) * float(payload.get("trade_volume", 0.0))
        side = (payload.get("ask_bid") or "").upper()
        events = self.recent_trades.setdefault(market, [])
        events.append({"notional": notional, "is_bid": 1.0 if side == "BID" else 0.0})
        window = max(1, self.config.selector.recent_trade_window)
        self.recent_trades[market] = events[-window:]

    def _trade_flow_metrics(self, market: str) -> tuple[float, float, bool]:
        events = self.recent_trades.get(market, [])
        if not events:
            return 0.0, 0.0, not self.config.selector.use_trade_flow_filter

        total_notional = sum(item["notional"] for item in events)
        bid_notional = sum(item["notional"] for item in events if item["is_bid"] > 0)
        bid_ratio = 0.0 if total_notional <= 0 else bid_notional / total_notional
        threshold_notional = self.config.selector.min_recent_trade_notional
        threshold_ratio = self.config.selector.min_recent_bid_ratio
        trade_flow_ok = True
        if self.config.selector.use_trade_flow_filter:
            trade_flow_ok = total_notional >= threshold_notional and bid_ratio >= threshold_ratio
        return bid_ratio, total_notional, trade_flow_ok

    def _update_orderbook(self, market: str, payload: Dict[str, Any]) -> None:
        units = payload.get("orderbook_units", []) or []
        if not units:
            return
        best = units[0]
        ask_price = float(best.get("ask_price", 0.0))
        bid_price = float(best.get("bid_price", 0.0))
        ask_size = float(best.get("ask_size", 0.0))
        bid_size = float(best.get("bid_size", 0.0))
        total_ask_size = float(payload.get("total_ask_size", 0.0))
        total_bid_size = float(payload.get("total_bid_size", 0.0))
        self.market_orderbooks[market] = {
            "ask_price": ask_price,
            "bid_price": bid_price,
            "ask_size": ask_size,
            "bid_size": bid_size,
            "total_ask_size": total_ask_size,
            "total_bid_size": total_bid_size,
        }

    def _orderbook_metrics(self, market: str) -> tuple[float, float, float, bool]:
        snapshot = self.market_orderbooks.get(market)
        if not snapshot:
            return 0.0, 0.0, 0.0, not self.config.selector.use_orderbook_filter

        ask_price = snapshot["ask_price"]
        bid_price = snapshot["bid_price"]
        ask_size = snapshot["ask_size"]
        bid_size = snapshot["bid_size"]
        total_ask_size = snapshot["total_ask_size"]
        total_bid_size = snapshot["total_bid_size"]

        mid = (ask_price + bid_price) / 2.0 if ask_price > 0 and bid_price > 0 else 0.0
        spread_bps = 0.0 if mid <= 0 else ((ask_price - bid_price) / mid) * 10000.0
        top_ratio = bid_size / ask_size if ask_size > 0 else 0.0
        total_ratio = total_bid_size / total_ask_size if total_ask_size > 0 else 0.0

        orderbook_ok = True
        if self.config.selector.use_orderbook_filter:
            orderbook_ok = (
                spread_bps <= self.config.selector.max_spread_bps
                and top_ratio >= self.config.selector.min_top_bid_ask_ratio
                and total_ratio >= self.config.selector.min_total_bid_ask_ratio
            )
        return spread_bps, top_ratio, total_ratio, orderbook_ok
