from typing import List, Optional, Tuple

from .config import AppConfig
from .indicators import atr
from .models import BacktestResult, Candle, ClosedTrade, Position
from .risk import RiskManager
from .strategy import ProfessionalCryptoStrategy


class Backtester:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.strategy = ProfessionalCryptoStrategy(config.strategy)
        self.risk = RiskManager(config.risk)

    def run(self, candles: List[Candle]) -> BacktestResult:
        if not candles:
            raise ValueError("candles are required")

        cash = self.config.initial_cash
        position = None
        peak_equity = cash
        equity_curve = []
        trades = []
        events = []
        atr_values = atr(candles, self.config.risk.atr_period)

        for index, candle in enumerate(candles):
            history = candles[: index + 1]
            mark_to_market = cash + self._position_market_value(position, candle.close)
            peak_equity = max(peak_equity, mark_to_market)
            drawdown_fraction = 0.0 if peak_equity == 0 else (peak_equity - mark_to_market) / peak_equity
            closed_this_bar = False

            if position is not None:
                self._update_trailing_stop(position, candle.close, atr_values[index])
                closed = self._maybe_close_position(position, candle, history)
                if closed is not None:
                    cash_delta, trade, event = closed
                    cash += cash_delta
                    trades.append(trade)
                    events.append(event)
                    position = None
                    closed_this_bar = True

            if position is None and not closed_this_bar:
                signal = self.strategy.evaluate(history, None)
                if signal.action.value == "BUY":
                    atr_value = atr_values[index] or (candle.close * self.config.risk.minimum_stop_fraction)
                    trade_plan = self.risk.build_trade_plan(candle.close, atr_value, drawdown_fraction)
                    if trade_plan.blocked:
                        events.append(
                            "{0} BLOCKED {1} reason={2}".format(
                                candle.timestamp,
                                self.config.market,
                                trade_plan.block_reason,
                            )
                        )
                    else:
                        entry_price = self._apply_buy_slippage(candle.close)
                        budget = cash * trade_plan.size_fraction
                        quantity = budget / entry_price
                        total_cost = self._buy_total_cost(entry_price, quantity)
                        if quantity > 0 and total_cost <= cash:
                            cash -= total_cost
                            position = Position(
                                market=self.config.market,
                                entry_timestamp=candle.timestamp,
                                entry_price=entry_price,
                                quantity=quantity,
                                stop_loss=trade_plan.stop_loss,
                                take_profit=trade_plan.take_profit,
                                trailing_stop=entry_price - trade_plan.trailing_gap,
                                entry_score=signal.score,
                            )
                            events.append(
                                "{0} BUY {1} qty={2:.8f} price={3:.2f} score={4:.1f} reasons={5}".format(
                                    candle.timestamp,
                                    self.config.market,
                                    quantity,
                                    entry_price,
                                    signal.score,
                                    ",".join(signal.reasons),
                                )
                            )

            equity_curve.append(cash + self._position_market_value(position, candle.close))

        if position is not None:
            last_candle = candles[-1]
            exit_price = self._apply_sell_slippage(last_candle.close)
            cash += self._sell_total_proceeds(exit_price, position.quantity)
            trade = self._close_trade(position, last_candle.timestamp, exit_price, "end_of_data")
            trades.append(trade)
            events.append(
                "{0} SELL {1} qty={2:.8f} price={3:.2f} reason=end_of_data pnl={4:.2f}".format(
                    last_candle.timestamp,
                    self.config.market,
                    position.quantity,
                    exit_price,
                    trade.net_pnl,
                )
            )
            equity_curve[-1] = cash

        final_equity = cash
        win_count = len([trade for trade in trades if trade.net_pnl > 0])

        return BacktestResult(
            market=self.config.market,
            initial_cash=self.config.initial_cash,
            final_cash=cash,
            final_equity=final_equity,
            total_return_pct=((final_equity - self.config.initial_cash) / self.config.initial_cash) * 100.0,
            max_drawdown_pct=self._max_drawdown_pct(equity_curve),
            win_rate_pct=(win_count / len(trades) * 100.0) if trades else 0.0,
            trades=trades,
            events=events,
            equity_curve=equity_curve,
        )

    def _maybe_close_position(
        self,
        position: Position,
        candle: Candle,
        history: List[Candle],
    ) -> Optional[Tuple[float, ClosedTrade, str]]:
        exit_reason = None
        raw_exit_price = candle.close

        if candle.low <= position.stop_loss:
            exit_reason = "stop_loss"
            raw_exit_price = position.stop_loss
        elif candle.low <= position.trailing_stop:
            exit_reason = "trailing_stop"
            raw_exit_price = position.trailing_stop
        elif candle.high >= position.take_profit:
            exit_reason = "take_profit"
            raw_exit_price = position.take_profit
        else:
            signal = self.strategy.evaluate(history, position)
            if signal.action.value == "SELL":
                exit_reason = "strategy_exit"
                raw_exit_price = candle.close

        if exit_reason is None:
            return None

        exit_price = self._apply_sell_slippage(raw_exit_price)
        cash_delta = self._sell_total_proceeds(exit_price, position.quantity)
        trade = self._close_trade(position, candle.timestamp, exit_price, exit_reason)
        event = "{0} SELL {1} qty={2:.8f} price={3:.2f} reason={4} pnl={5:.2f}".format(
            candle.timestamp,
            position.market,
            position.quantity,
            exit_price,
            exit_reason,
            trade.net_pnl,
        )
        return cash_delta, trade, event

    def _close_trade(
        self,
        position: Position,
        exit_timestamp: str,
        exit_price: float,
        exit_reason: str,
    ) -> ClosedTrade:
        gross_pnl = (exit_price - position.entry_price) * position.quantity
        net_pnl = self._sell_total_proceeds(exit_price, position.quantity) - self._buy_total_cost(
            position.entry_price,
            position.quantity,
        )
        return_pct = ((exit_price - position.entry_price) / position.entry_price) * 100.0
        return ClosedTrade(
            market=position.market,
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=exit_timestamp,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            return_pct=return_pct,
            exit_reason=exit_reason,
        )

    def _update_trailing_stop(self, position: Position, close: float, atr_value: Optional[float]) -> None:
        fallback_gap = close * self.config.risk.minimum_stop_fraction
        trailing_gap = max(fallback_gap, (atr_value or fallback_gap) * self.config.risk.trailing_atr_multiple)
        position.trailing_stop = max(position.trailing_stop, close - trailing_gap)

    def _position_market_value(self, position: Optional[Position], price: float) -> float:
        if position is None:
            return 0.0
        return position.quantity * price

    def _apply_buy_slippage(self, price: float) -> float:
        return price * (1.0 + self.config.slippage_rate)

    def _apply_sell_slippage(self, price: float) -> float:
        return price * (1.0 - self.config.slippage_rate)

    def _buy_total_cost(self, price: float, quantity: float) -> float:
        notional = price * quantity
        fee = notional * self.config.fee_rate
        return notional + fee

    def _sell_total_proceeds(self, price: float, quantity: float) -> float:
        notional = price * quantity
        fee = notional * self.config.fee_rate
        return notional - fee

    def _max_drawdown_pct(self, equity_curve: List[float]) -> float:
        peak = 0.0
        worst = 0.0
        for equity in equity_curve:
            peak = max(peak, equity)
            if peak == 0:
                continue
            drawdown = ((peak - equity) / peak) * 100.0
            worst = max(worst, drawdown)
        return worst


def format_backtest_report(result: BacktestResult) -> str:
    lines = [
        "market={0}".format(result.market),
        "initial_cash={0:.2f}".format(result.initial_cash),
        "final_equity={0:.2f}".format(result.final_equity),
        "total_return_pct={0:.2f}".format(result.total_return_pct),
        "max_drawdown_pct={0:.2f}".format(result.max_drawdown_pct),
        "win_rate_pct={0:.2f}".format(result.win_rate_pct),
        "trade_count={0}".format(len(result.trades)),
    ]
    return "\n".join(lines)
