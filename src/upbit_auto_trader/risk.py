from dataclasses import dataclass

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

    def build_trade_plan(self, price: float, atr_value: float, drawdown_fraction: float) -> TradePlan:
        if drawdown_fraction >= self.config.max_portfolio_drawdown_fraction:
            return TradePlan(
                size_fraction=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                trailing_gap=0.0,
                blocked=True,
                block_reason="portfolio_drawdown_limit",
            )

        stop_gap = max(price * self.config.minimum_stop_fraction, atr_value * self.config.stop_atr_multiple)
        take_profit_gap = max(stop_gap * 1.1, atr_value * self.config.take_profit_atr_multiple)
        trailing_gap = max(stop_gap * 0.75, atr_value * self.config.trailing_atr_multiple)

        risk_fraction = stop_gap / price
        raw_size_fraction = self.config.risk_per_trade_fraction / max(risk_fraction, 0.0001)
        size_fraction = min(self.config.max_position_fraction, raw_size_fraction)

        return TradePlan(
            size_fraction=size_fraction,
            stop_loss=price - stop_gap,
            take_profit=price + take_profit_gap,
            trailing_gap=trailing_gap,
        )

