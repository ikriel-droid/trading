from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    action: Action
    score: float
    confidence: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class Position:
    market: str
    entry_timestamp: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    trailing_stop: float
    entry_score: float


@dataclass
class ClosedTrade:
    market: str
    entry_timestamp: str
    exit_timestamp: str
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    exit_reason: str


@dataclass
class PendingOrder:
    uuid: str
    market: str
    side: str
    order_type: str
    requested_price: float
    requested_volume: float
    created_timestamp: str
    created_bar_index: int
    strategy_score: float
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop: float = 0.0
    applied_executed_volume: float = 0.0
    applied_executed_funds: float = 0.0
    applied_paid_fee: float = 0.0
    last_state: str = ""
    last_update_timestamp: str = ""


@dataclass
class BacktestResult:
    market: str
    initial_cash: float
    final_cash: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    trades: List[ClosedTrade] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)


@dataclass
class Balance:
    currency: str
    balance: float
    locked: float
    avg_buy_price: float
    unit_currency: str
