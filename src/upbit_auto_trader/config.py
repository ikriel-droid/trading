import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


ENV_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


@dataclass
class StrategyConfig:
    fast_ema: int = 8
    slow_ema: int = 21
    rsi_period: int = 14
    macd_fast: int = 8
    macd_slow: int = 21
    macd_signal: int = 5
    adx_period: int = 14
    min_adx: float = 18.0
    bollinger_period: int = 20
    bollinger_stddev: float = 2.0
    min_bollinger_width_fraction: float = 0.015
    breakout_lookback: int = 20
    volume_sma_period: int = 20
    volume_spike_multiplier: float = 1.3
    buy_threshold: float = 65.0
    sell_threshold: float = 40.0


@dataclass
class RiskConfig:
    risk_per_trade_fraction: float = 0.01
    max_position_fraction: float = 0.35
    stop_atr_multiple: float = 2.2
    take_profit_atr_multiple: float = 3.5
    trailing_atr_multiple: float = 1.8
    atr_period: int = 14
    minimum_stop_fraction: float = 0.015
    max_portfolio_drawdown_fraction: float = 0.2


@dataclass
class RuntimeConfig:
    cooldown_bars_after_exit: int = 1
    max_trades_per_day: int = 5
    daily_loss_limit_fraction: float = 0.03
    session_start: str = ""
    session_end: str = ""
    allowed_weekdays: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    journal_path: str = ""
    poll_seconds: float = 10.0
    max_history: int = 300
    pending_order_max_bars: int = 3


@dataclass
class SelectorConfig:
    quote_currency: str = "KRW"
    include_markets: List[str] = field(default_factory=list)
    exclude_markets: List[str] = field(default_factory=list)
    max_markets: int = 10
    min_score: float = 65.0
    min_acc_trade_price_24h: float = 0.0
    use_trade_flow_filter: bool = False
    min_recent_bid_ratio: float = 0.5
    min_recent_trade_notional: float = 0.0
    recent_trade_window: int = 30
    use_orderbook_filter: bool = False
    max_spread_bps: float = 15.0
    min_top_bid_ask_ratio: float = 0.8
    min_total_bid_ask_ratio: float = 0.9
    require_buy_action: bool = True
    skip_warning_markets: bool = True
    states_dir: str = "data/selector-states"


@dataclass
class UpbitConfig:
    base_url: str = "https://api.upbit.com/v1"
    market: str = "KRW-BTC"
    access_key: str = ""
    secret_key: str = ""
    candle_unit: int = 15
    candle_count: int = 200
    request_timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    live_enabled: bool = False


@dataclass
class NotificationConfig:
    discord_webhook_url: str = ""
    enabled_levels: List[str] = field(default_factory=lambda: ["error", "warning", "success"])
    enabled_event_types: List[str] = field(
        default_factory=lambda: [
            "blocked",
            "buy",
            "sell",
            "buy_submitted",
            "buy_fill",
            "sell_fill",
            "myorder_done",
            "pending_order_cancel_requested",
        ]
    )
    cooldown_seconds: float = 5.0
    timeout_seconds: float = 5.0


@dataclass
class AppConfig:
    market: str
    initial_cash: float = 1000000.0
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0007
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    selector: SelectorConfig = field(default_factory=SelectorConfig)
    upbit: UpbitConfig = field(default_factory=UpbitConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)


def _resolve_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_env(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_resolve_env(item) for item in value]

    if isinstance(value, str):
        match = ENV_PATTERN.fullmatch(value)
        if not match:
            return value

        env_name = match.group(1)
        return os.environ.get(env_name, value)

    return value


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)

    raw = _resolve_env(raw)

    upbit = UpbitConfig(**raw.get("upbit", {}))
    market = raw.get("market", upbit.market)
    upbit.market = market

    return AppConfig(
        market=market,
        initial_cash=float(raw.get("initial_cash", 1000000.0)),
        fee_rate=float(raw.get("fee_rate", 0.0005)),
        slippage_rate=float(raw.get("slippage_rate", 0.0007)),
        strategy=StrategyConfig(**raw.get("strategy", {})),
        risk=RiskConfig(**raw.get("risk", {})),
        runtime=RuntimeConfig(**raw.get("runtime", {})),
        selector=SelectorConfig(**raw.get("selector", {})),
        upbit=upbit,
        notifications=NotificationConfig(**raw.get("notifications", {})),
    )
