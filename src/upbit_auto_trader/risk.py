from dataclasses import dataclass
from typing import Iterable, Optional

from .config import RiskConfig


@dataclass
class TradePlan:
    size_fraction: float
    stop_loss: float
    take_profit: float
    trailing_gap: float
    blocked: bool = False
    block_reason: str = ""


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def build_trade_plan(
        self,
        price: float,
        atr_value: float,
        drawdown_fraction: float,
        signal_reasons: Optional[Iterable[str]] = None,
    ) -> TradePlan:
        if drawdown_fraction >= self.config.max_portfolio_drawdown_fraction:
            return TradePlan(
                size_fraction=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                trailing_gap=0.0,
                blocked=True,
                block_reason="portfolio_drawdown_limit",
            )

        stop_gap = self._stop_gap(price, atr_value)
        take_profit_gap = self._take_profit_gap(stop_gap, atr_value, signal_reasons)
        trailing_gap = self._trailing_gap(price, atr_value)

        risk_fraction = stop_gap / price
        raw_size_fraction = self.config.risk_per_trade_fraction / max(risk_fraction, 0.0001)
        size_fraction = min(self.config.max_position_fraction, raw_size_fraction)

        return TradePlan(
            size_fraction=size_fraction,
            stop_loss=price - stop_gap,
            take_profit=price + take_profit_gap,
            trailing_gap=trailing_gap,
        )

    def extend_take_profit(
        self,
        current_price: float,
        current_take_profit: float,
        atr_value: float,
        signal_reasons: Optional[Iterable[str]] = None,
    ) -> float:
        if not self._is_strong_uptrend(signal_reasons):
            return current_take_profit

        stop_gap = self._stop_gap(current_price, atr_value)
        trend_take_profit_gap = self._take_profit_gap(stop_gap, atr_value, signal_reasons)
        return max(current_take_profit, current_price + trend_take_profit_gap)

    def _is_strong_uptrend(self, signal_reasons: Optional[Iterable[str]]) -> bool:
        if not signal_reasons:
            return False

        reasons = {str(item) for item in signal_reasons}
        has_core_trend = {
            "ema_uptrend",
            "macd_bullish",
            "adx_trend",
        }.issubset(reasons)
        has_follow_through = "volatility_expansion_up" in reasons or "breakout" in reasons
        return has_core_trend and has_follow_through

    def _stop_gap(self, price: float, atr_value: float) -> float:
        return max(price * self.config.minimum_stop_fraction, atr_value * self.config.stop_atr_multiple)

    def _take_profit_gap(
        self,
        stop_gap: float,
        atr_value: float,
        signal_reasons: Optional[Iterable[str]] = None,
    ) -> float:
        take_profit_gap = max(stop_gap * 1.1, atr_value * self.config.take_profit_atr_multiple)
        if self._is_strong_uptrend(signal_reasons):
            return max(
                take_profit_gap,
                stop_gap * self.config.trend_take_profit_stop_multiple,
                atr_value * self.config.trend_take_profit_atr_multiple,
            )
        return take_profit_gap

    def _trailing_gap(self, price: float, atr_value: float) -> float:
        fallback_gap = price * self.config.minimum_stop_fraction
        return max(fallback_gap, atr_value * self.config.trailing_atr_multiple)
