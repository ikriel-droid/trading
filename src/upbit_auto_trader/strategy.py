from typing import List, Optional

from .config import StrategyConfig
from .indicators import ema, macd, rsi, sma
from .models import Action, Candle, Position, Signal


class ProfessionalCryptoStrategy:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    def minimum_history(self) -> int:
        return max(
            self.config.slow_ema,
            self.config.rsi_period + 1,
            self.config.volume_sma_period,
            self.config.breakout_lookback + 1,
            self.config.macd_slow + self.config.macd_signal,
        )

    def evaluate(self, candles: List[Candle], position: Optional[Position]) -> Signal:
        if len(candles) < self.minimum_history():
            return Signal(action=Action.HOLD, score=50.0, confidence=0.0, reasons=["warmup"])

        closes = [candle.close for candle in candles]
        volumes = [candle.volume for candle in candles]
        index = len(candles) - 1
        current = candles[index]

        fast_ema = ema(closes, self.config.fast_ema)
        slow_ema = ema(closes, self.config.slow_ema)
        rsi_values = rsi(closes, self.config.rsi_period)
        macd_line, macd_signal, macd_hist = macd(
            closes,
            self.config.macd_fast,
            self.config.macd_slow,
            self.config.macd_signal,
        )
        volume_ma = sma(volumes, self.config.volume_sma_period)

        score = 50.0
        reasons = []

        if (
            fast_ema[index] is not None
            and slow_ema[index] is not None
            and current.close > fast_ema[index] > slow_ema[index]
        ):
            score += 20.0
            reasons.append("ema_uptrend")
        elif (
            fast_ema[index] is not None
            and slow_ema[index] is not None
            and current.close < fast_ema[index] < slow_ema[index]
        ):
            score -= 20.0
            reasons.append("ema_downtrend")

        if macd_line[index] is not None and macd_signal[index] is not None:
            if macd_line[index] > macd_signal[index]:
                score += 15.0
                reasons.append("macd_bullish")
            else:
                score -= 15.0
                reasons.append("macd_bearish")

        if (
            index > 0
            and macd_hist[index] is not None
            and macd_hist[index - 1] is not None
        ):
            if macd_hist[index] > macd_hist[index - 1]:
                score += 10.0
                reasons.append("macd_hist_rising")
            else:
                score -= 10.0
                reasons.append("macd_hist_falling")

        if rsi_values[index] is not None:
            if 52.0 <= rsi_values[index] <= 68.0:
                score += 10.0
                reasons.append("rsi_constructive")
            elif rsi_values[index] >= 76.0:
                score -= 12.0
                reasons.append("rsi_overheated")
            elif rsi_values[index] <= 40.0:
                score -= 15.0
                reasons.append("rsi_weak")

        if (
            volume_ma[index] is not None
            and volume_ma[index] > 0
            and current.volume > volume_ma[index] * self.config.volume_spike_multiplier
        ):
            score += 10.0
            reasons.append("volume_spike")

        breakout_window = closes[index - self.config.breakout_lookback : index]
        if len(breakout_window) == self.config.breakout_lookback:
            if current.close > max(breakout_window):
                score += 15.0
                reasons.append("breakout")
            elif current.close < min(breakout_window[-5:]):
                score -= 10.0
                reasons.append("short_term_breakdown")

        score = max(0.0, min(100.0, score))
        confidence = abs(score - 50.0) / 50.0

        if position is None and score >= self.config.buy_threshold:
            return Signal(action=Action.BUY, score=score, confidence=confidence, reasons=reasons or ["buy_threshold"])

        if position is not None:
            if score <= self.config.sell_threshold:
                return Signal(
                    action=Action.SELL,
                    score=score,
                    confidence=confidence,
                    reasons=reasons or ["sell_threshold"],
                )

            if (
                rsi_values[index] is not None
                and rsi_values[index] >= 74.0
                and "macd_hist_falling" in reasons
            ):
                return Signal(
                    action=Action.SELL,
                    score=score,
                    confidence=confidence,
                    reasons=reasons + ["momentum_rollover"],
                )

        return Signal(action=Action.HOLD, score=score, confidence=confidence, reasons=reasons or ["neutral"])

