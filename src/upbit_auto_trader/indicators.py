from typing import List, Optional, Sequence, Tuple

from .models import Candle


def sma(values: Sequence[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")

    result = [None] * len(values)
    running_total = 0.0

    for index, value in enumerate(values):
        running_total += value
        if index >= period:
            running_total -= values[index - period]

        if index + 1 >= period:
            result[index] = running_total / float(period)

    return result


def ema(values: Sequence[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")

    result = [None] * len(values)
    if len(values) < period:
        return result

    seed = sum(values[:period]) / float(period)
    result[period - 1] = seed
    multiplier = 2.0 / float(period + 1)

    current = seed
    for index in range(period, len(values)):
        current = ((values[index] - current) * multiplier) + current
        result[index] = current

    return result


def rsi(values: Sequence[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")

    result = [None] * len(values)
    if len(values) <= period:
        return result

    gains = []
    losses = []
    for index in range(1, period + 1):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gain = sum(gains) / float(period)
    average_loss = sum(losses) / float(period)
    result[period] = _relative_strength_index(average_gain, average_loss)

    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        average_gain = ((average_gain * (period - 1)) + gain) / float(period)
        average_loss = ((average_loss * (period - 1)) + loss) / float(period)
        result[index] = _relative_strength_index(average_gain, average_loss)

    return result


def _relative_strength_index(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100.0

    rs = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    values: Sequence[float],
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    fast = ema(values, fast_period)
    slow = ema(values, slow_period)

    line = [None] * len(values)
    raw_values = []
    raw_indexes = []

    for index in range(len(values)):
        if fast[index] is None or slow[index] is None:
            continue

        value = fast[index] - slow[index]
        line[index] = value
        raw_values.append(value)
        raw_indexes.append(index)

    signal = [None] * len(values)
    histogram = [None] * len(values)

    if raw_values:
        signal_values = ema(raw_values, signal_period)
        for offset, index in enumerate(raw_indexes):
            signal[index] = signal_values[offset]
            if signal[index] is not None and line[index] is not None:
                histogram[index] = line[index] - signal[index]

    return line, signal, histogram


def atr(candles: Sequence[Candle], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")

    result = [None] * len(candles)
    if len(candles) < period:
        return result

    true_ranges = []
    for index, candle in enumerate(candles):
        if index == 0:
            true_range = candle.high - candle.low
        else:
            previous_close = candles[index - 1].close
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        true_ranges.append(true_range)

    first_average = sum(true_ranges[:period]) / float(period)
    result[period - 1] = first_average
    current = first_average

    for index in range(period, len(candles)):
        current = ((current * (period - 1)) + true_ranges[index]) / float(period)
        result[index] = current

    return result

