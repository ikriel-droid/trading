import math
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


def rolling_stddev(values: Sequence[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")

    result = [None] * len(values)
    if len(values) < period:
        return result

    for index in range(period - 1, len(values)):
        window = values[index - period + 1 : index + 1]
        mean = sum(window) / float(period)
        variance = sum((value - mean) ** 2 for value in window) / float(period)
        result[index] = math.sqrt(variance)

    return result


def bollinger_bands(
    values: Sequence[float],
    period: int,
    stddev_multiplier: float,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    middle = sma(values, period)
    deviations = rolling_stddev(values, period)
    upper = [None] * len(values)
    lower = [None] * len(values)
    width_fraction = [None] * len(values)

    for index in range(len(values)):
        if middle[index] is None or deviations[index] is None:
            continue
        upper[index] = middle[index] + (deviations[index] * stddev_multiplier)
        lower[index] = middle[index] - (deviations[index] * stddev_multiplier)
        if middle[index] and middle[index] != 0:
            width_fraction[index] = (upper[index] - lower[index]) / middle[index]

    return middle, upper, lower, width_fraction


def adx(candles: Sequence[Candle], period: int) -> List[Optional[float]]:
    if period <= 0:
        raise ValueError("period must be positive")

    result = [None] * len(candles)
    if len(candles) < (period * 2):
        return result

    plus_dm = [0.0] * len(candles)
    minus_dm = [0.0] * len(candles)
    true_ranges = [0.0] * len(candles)

    for index in range(1, len(candles)):
        up_move = candles[index].high - candles[index - 1].high
        down_move = candles[index - 1].low - candles[index].low
        plus_dm[index] = up_move if (up_move > down_move and up_move > 0.0) else 0.0
        minus_dm[index] = down_move if (down_move > up_move and down_move > 0.0) else 0.0
        true_ranges[index] = max(
            candles[index].high - candles[index].low,
            abs(candles[index].high - candles[index - 1].close),
            abs(candles[index].low - candles[index - 1].close),
        )

    smoothed_tr = sum(true_ranges[1 : period + 1])
    smoothed_plus_dm = sum(plus_dm[1 : period + 1])
    smoothed_minus_dm = sum(minus_dm[1 : period + 1])
    dx_values: List[float] = []

    for index in range(period, len(candles)):
        if index > period:
            smoothed_tr = smoothed_tr - (smoothed_tr / period) + true_ranges[index]
            smoothed_plus_dm = smoothed_plus_dm - (smoothed_plus_dm / period) + plus_dm[index]
            smoothed_minus_dm = smoothed_minus_dm - (smoothed_minus_dm / period) + minus_dm[index]

        if smoothed_tr <= 0:
            dx_values.append(0.0)
            continue

        plus_di = 100.0 * (smoothed_plus_dm / smoothed_tr)
        minus_di = 100.0 * (smoothed_minus_dm / smoothed_tr)
        di_sum = plus_di + minus_di
        dx = 0.0 if di_sum == 0 else 100.0 * abs(plus_di - minus_di) / di_sum
        dx_values.append(dx)

        if len(dx_values) == period:
            result[index] = sum(dx_values) / float(period)
        elif len(dx_values) > period:
            previous = result[index - 1]
            if previous is None:
                previous = sum(dx_values[-period:]) / float(period)
            result[index] = ((previous * (period - 1)) + dx) / float(period)

    return result
