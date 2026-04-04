from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import AppConfig, SelectorConfig
from .datafeed import upbit_candles_to_internal
from .strategy import ProfessionalCryptoStrategy


@dataclass
class MarketScanResult:
    market: str
    action: str
    score: float
    confidence: float
    candle_unit: int = 0
    reasons: List[str] = field(default_factory=list)
    timestamp: str = ""
    close: float = 0.0
    candle_count: int = 0
    market_warning: str = ""
    liquidity_24h: float = 0.0
    recent_bid_ratio: float = 0.0
    recent_trade_notional: float = 0.0
    liquidity_ok: bool = True
    trade_flow_ok: bool = True
    spread_bps: float = 0.0
    top_bid_ask_ratio: float = 0.0
    total_bid_ask_ratio: float = 0.0
    orderbook_ok: bool = True


class MarketScanner:
    def __init__(self, config: AppConfig, broker) -> None:
        self.config = config
        self.broker = broker
        self.strategy = ProfessionalCryptoStrategy(config.strategy)

    def discover_markets(self, selector_config: Optional[SelectorConfig] = None) -> List[str]:
        selector = selector_config or self.config.selector
        include_markets = selector.include_markets
        exclude_markets = set(selector.exclude_markets)

        if include_markets:
            return [market for market in include_markets if market not in exclude_markets][: selector.max_markets]

        markets_payload = self.broker.list_markets(is_details=True)
        selected = []
        for item in markets_payload:
            market = item.get("market", "")
            if not market.startswith(selector.quote_currency + "-"):
                continue
            if market in exclude_markets:
                continue
            market_warning = (item.get("market_warning") or "").upper()
            if selector.skip_warning_markets and market_warning not in ("", "NONE"):
                continue
            selected.append(market)
            if len(selected) >= selector.max_markets:
                break
        return selected

    def scan_markets(self, markets: List[str]) -> List[MarketScanResult]:
        ticker_metrics = self._load_ticker_metrics(markets)
        results = []
        for market in markets:
            result = self.scan_market(market, ticker_metrics=ticker_metrics.get(market))
            if result is not None:
                results.append(result)
        results.sort(
            key=lambda item: (
                1 if item.action == "BUY" else 0,
                item.score,
                item.confidence,
                item.liquidity_24h,
                item.close,
                item.market,
            ),
            reverse=True,
        )
        return results

    def scan_market(self, market: str, ticker_metrics: Optional[Dict[str, float]] = None) -> Optional[MarketScanResult]:
        fetch_count = max(self.config.upbit.candle_count, self.strategy.minimum_history() + 5)
        payload = self.broker.get_minute_candles(
            market=market,
            unit=self.config.upbit.candle_unit,
            count=fetch_count,
        )
        candles = upbit_candles_to_internal(payload)
        return self.evaluate_candles(
            market,
            candles,
            market_warning=self._lookup_warning(market),
            liquidity_24h=(ticker_metrics or {}).get("acc_trade_price_24h", 0.0),
        )

    def evaluate_candles(
        self,
        market: str,
        candles: List,
        market_warning: str = "",
        liquidity_24h: float = 0.0,
        recent_bid_ratio: float = 0.0,
        recent_trade_notional: float = 0.0,
        trade_flow_ok: bool = True,
    ) -> Optional[MarketScanResult]:
        if len(candles) < self.strategy.minimum_history():
            return None

        signal = self.strategy.evaluate(candles, None)
        last_candle = candles[-1]
        liquidity_ok = (
            True
            if self.config.selector.min_acc_trade_price_24h <= 0
            else liquidity_24h >= self.config.selector.min_acc_trade_price_24h
        )
        return MarketScanResult(
            market=market,
            action=signal.action.value,
            score=signal.score,
            confidence=signal.confidence,
            candle_unit=int(self.config.upbit.candle_unit),
            reasons=signal.reasons,
            timestamp=last_candle.timestamp,
            close=last_candle.close,
            candle_count=len(candles),
            market_warning=market_warning,
            liquidity_24h=liquidity_24h,
            recent_bid_ratio=recent_bid_ratio,
            recent_trade_notional=recent_trade_notional,
            liquidity_ok=liquidity_ok,
            trade_flow_ok=trade_flow_ok,
        )

    def _lookup_warning(self, market: str) -> str:
        if not hasattr(self, "_warning_cache"):
            self._warning_cache = {}
        cache: Dict[str, str] = self._warning_cache
        if market in cache:
            return cache[market]

        for item in self.broker.list_markets(is_details=True):
            cache[item.get("market", "")] = (item.get("market_warning") or "").upper()
        return cache.get(market, "")

    def _load_ticker_metrics(self, markets: List[str]) -> Dict[str, Dict[str, float]]:
        if not markets or not hasattr(self.broker, "get_ticker"):
            return {}

        payload = self.broker.get_ticker(markets)
        metrics = {}
        for item in payload:
            metrics[item.get("market") or item.get("code")] = {
                "acc_trade_price_24h": float(item.get("acc_trade_price_24h", 0.0)),
            }
        return metrics
