import copy
from dataclasses import dataclass
from itertools import product
from typing import Iterable, List

from .backtest import Backtester
from .config import AppConfig
from .models import Candle


@dataclass
class GridSearchResult:
    buy_threshold: float
    sell_threshold: float
    min_adx: float
    min_bollinger_width_fraction: float
    volume_spike_multiplier: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int


def run_grid_search(
    config: AppConfig,
    candles: List[Candle],
    buy_thresholds: Iterable[float],
    sell_thresholds: Iterable[float],
    min_adx_values: Iterable[float],
    min_bollinger_width_values: Iterable[float],
    volume_spike_multipliers: Iterable[float],
) -> List[GridSearchResult]:
    results: List[GridSearchResult] = []

    for buy_threshold, sell_threshold, min_adx, min_bollinger_width, volume_spike_multiplier in product(
        buy_thresholds,
        sell_thresholds,
        min_adx_values,
        min_bollinger_width_values,
        volume_spike_multipliers,
    ):
        candidate = copy.deepcopy(config)
        candidate.strategy.buy_threshold = float(buy_threshold)
        candidate.strategy.sell_threshold = float(sell_threshold)
        candidate.strategy.min_adx = float(min_adx)
        candidate.strategy.min_bollinger_width_fraction = float(min_bollinger_width)
        candidate.strategy.volume_spike_multiplier = float(volume_spike_multiplier)

        backtest = Backtester(candidate).run(candles)
        results.append(
            GridSearchResult(
                buy_threshold=float(buy_threshold),
                sell_threshold=float(sell_threshold),
                min_adx=float(min_adx),
                min_bollinger_width_fraction=float(min_bollinger_width),
                volume_spike_multiplier=float(volume_spike_multiplier),
                final_equity=backtest.final_equity,
                total_return_pct=backtest.total_return_pct,
                max_drawdown_pct=backtest.max_drawdown_pct,
                win_rate_pct=backtest.win_rate_pct,
                trade_count=len(backtest.trades),
            )
        )

    results.sort(
        key=lambda item: (
            item.final_equity,
            item.total_return_pct,
            -item.max_drawdown_pct,
            item.win_rate_pct,
            item.trade_count,
        ),
        reverse=True,
    )
    return results
