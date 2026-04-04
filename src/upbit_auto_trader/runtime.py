import json
import os
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time as datetime_time, timezone
from typing import Any, Dict, List, Optional

from .config import AppConfig
from .indicators import atr
from .models import Action, Candle, ClosedTrade, PendingOrder, Position, Signal
from .notifier import DiscordWebhookNotifier, NotificationError
from .risk import RiskManager
from .strategy import ProfessionalCryptoStrategy


@dataclass
class RuntimeState:
    market: str
    cash: float
    peak_equity: float
    candle_unit: int = 0
    history: List[Candle] = field(default_factory=list)
    position: Optional[Position] = None
    closed_trades: List[ClosedTrade] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    last_processed_timestamp: str = ""
    last_order_timestamp: str = ""
    last_order_action: str = ""
    last_exit_timestamp: str = ""
    last_exit_bar_index: int = -1
    processed_bars: int = 0
    last_signal: Optional[Dict[str, Any]] = None
    last_startup_signal_timestamp: str = ""
    pending_order: Optional[PendingOrder] = None
    asset_snapshot: Dict[str, Dict[str, float]] = field(default_factory=dict)
    last_asset_sync_timestamp: str = ""


class TradingRuntime:
    def __init__(
        self,
        config: AppConfig,
        mode: str,
        state_path: str,
        broker: Any = None,
        notifier: Any = None,
    ) -> None:
        if mode not in ("paper", "live"):
            raise ValueError("mode must be paper or live")

        self.config = config
        self.mode = mode
        self.state_path = os.fspath(state_path)
        self.broker = broker
        self.strategy = ProfessionalCryptoStrategy(config.strategy)
        self.risk = RiskManager(config.risk)
        self.notifier = notifier or DiscordWebhookNotifier(config.notifications)
        self.state = None
        self._state_restore_notice = ""

    def bootstrap(self, warmup_candles: List[Candle]) -> RuntimeState:
        existing = self._load_state()
        if existing is not None:
            self.state = existing
            if self.mode == "live":
                self._prime_live_state_cursor(existing)
                self._sync_live_state(existing, is_new_state=False)
                self._save_state()
            return existing

        minimum_history = self.strategy.minimum_history()
        if len(warmup_candles) < minimum_history:
            raise ValueError(
                "warmup candles are insufficient: need at least {0}, got {1}".format(
                    minimum_history,
                    len(warmup_candles),
                )
            )

        state = RuntimeState(
            market=self.config.market,
            cash=self.config.initial_cash,
            peak_equity=self.config.initial_cash,
            candle_unit=self.config.upbit.candle_unit,
            history=list(warmup_candles)[-self.config.runtime.max_history :],
        )
        if self._state_restore_notice:
            state.events.append(self._state_restore_notice)
            state.events = state.events[-500:]
        if self.mode == "live":
            self._prime_live_state_cursor(state)
            self._sync_live_state(state, is_new_state=True)
        self.state = state
        self._save_state()
        return state

    def _prime_live_state_cursor(self, state: RuntimeState) -> None:
        if self.mode != "live":
            return
        if state.last_processed_timestamp or not state.history:
            return

        state.last_processed_timestamp = state.history[-1].timestamp
        state.processed_bars = max(int(state.processed_bars or 0), len(state.history))
        state.events.append(
            "LIVE CURSOR PRIMED last_processed_timestamp={0}".format(state.last_processed_timestamp)
        )
        state.events = state.events[-500:]

    def recenter_live_state_to_latest_candles(self, candles: List[Candle]) -> Dict[str, Any]:
        if self.state is None:
            raise ValueError("runtime must be bootstrapped before recenter_live_state_to_latest_candles")

        if self.mode != "live" or not candles:
            return {
                "recentered": False,
                "previous_timestamp": self.state.last_processed_timestamp,
                "latest_timestamp": self.state.last_processed_timestamp,
                "skipped_visible_candles": 0,
            }

        latest_history = list(candles)[-self.config.runtime.max_history :]
        latest_timestamp = latest_history[-1].timestamp
        previous_timestamp = self.state.last_processed_timestamp
        if previous_timestamp and latest_timestamp <= previous_timestamp:
            return {
                "recentered": False,
                "previous_timestamp": previous_timestamp,
                "latest_timestamp": latest_timestamp,
                "skipped_visible_candles": 0,
            }

        skipped_visible_candles = 0
        if previous_timestamp:
            skipped_visible_candles = sum(1 for candle in candles if candle.timestamp > previous_timestamp)
        else:
            skipped_visible_candles = len(candles)

        self.state.history = latest_history
        self.state.last_processed_timestamp = latest_timestamp
        self.state.processed_bars = max(
            int(self.state.processed_bars or 0) + max(skipped_visible_candles, 0),
            len(self.state.history),
        )
        event = (
            "LIVE STARTUP RECENTERED {0} from={1} to={2} skipped_visible_candles={3}".format(
                self.config.market,
                previous_timestamp or "<none>",
                latest_timestamp,
                skipped_visible_candles,
            )
        )
        self.state.events.append(event)
        self.state.events = self.state.events[-500:]
        self._save_state()
        return {
            "recentered": True,
            "previous_timestamp": previous_timestamp,
            "latest_timestamp": latest_timestamp,
            "skipped_visible_candles": skipped_visible_candles,
            "event": event,
        }

    def evaluate_startup_latest_candle_once(self, candle: Candle) -> List[str]:
        if self.state is None:
            raise ValueError("runtime must be bootstrapped before evaluate_startup_latest_candle_once")

        if self.mode != "live":
            return []

        if self.state.last_startup_signal_timestamp == candle.timestamp:
            return []

        history = list(self.state.history)
        if not history or history[-1].timestamp != candle.timestamp:
            history = (history + [candle])[-self.config.runtime.max_history :]

        atr_values = atr(history, self.config.risk.atr_period)
        atr_value = atr_values[-1] or (candle.close * self.config.risk.minimum_stop_fraction)
        mark_to_market = self.state.cash + self._position_market_value(self.state.position, candle.close)
        self.state.peak_equity = max(self.state.peak_equity, mark_to_market)
        drawdown_fraction = 0.0
        if self.state.peak_equity > 0:
            drawdown_fraction = (self.state.peak_equity - mark_to_market) / self.state.peak_equity

        current_bar_index = max(int(self.state.processed_bars) - 1, 0)
        signal = self.strategy.evaluate(history, None if self.state.position is None else self.state.position)
        self.state.last_signal = self._serialize_signal(signal, candle.timestamp)

        events: List[str] = []
        if self.state.position is not None:
            extend_event = self._maybe_extend_take_profit(self.state.position, candle, atr_value, signal)
            if extend_event:
                events.append(extend_event)
        if (
            self.state.position is None
            and self.state.pending_order is None
            and signal.action == Action.BUY
            and not self._is_duplicate_order("BUY", candle.timestamp)
            and self.state.last_order_timestamp != candle.timestamp
        ):
            block_reason = self._entry_block_reason(candle, current_bar_index)
            if block_reason:
                event = "{0} BLOCKED {1} reason={2}".format(candle.timestamp, self.config.market, block_reason)
                events.append(event)
                self._append_journal(
                    {
                        "event_type": "blocked",
                        "timestamp": candle.timestamp,
                        "market": self.config.market,
                        "reason": block_reason,
                    }
                )
            else:
                event = self._maybe_enter_position(candle, atr_value, drawdown_fraction, signal)
                if event:
                    events.append(event)

        self.state.last_startup_signal_timestamp = candle.timestamp
        self.state.events.extend(events)
        self.state.events = self.state.events[-500:]
        self._save_state()
        return events

    def process_candle(self, candle: Candle) -> List[str]:
        if self.state is None:
            raise ValueError("runtime must be bootstrapped before process_candle")

        if self.state.last_processed_timestamp and candle.timestamp <= self.state.last_processed_timestamp:
            return []

        current_bar_index = self.state.processed_bars
        history = (self.state.history + [candle])[-self.config.runtime.max_history :]
        atr_values = atr(history, self.config.risk.atr_period)
        atr_value = atr_values[-1] or (candle.close * self.config.risk.minimum_stop_fraction)

        mark_to_market = self.state.cash + self._position_market_value(self.state.position, candle.close)
        self.state.peak_equity = max(self.state.peak_equity, mark_to_market)
        drawdown_fraction = 0.0
        if self.state.peak_equity > 0:
            drawdown_fraction = (self.state.peak_equity - mark_to_market) / self.state.peak_equity

        new_events = []
        had_pending_order = self.state.pending_order is not None
        if self.mode == "live" and had_pending_order:
            new_events.extend(self._reconcile_live_pending_order(candle.timestamp, current_bar_index))

        closed_this_bar = False

        if self.state.position is not None and not had_pending_order:
            signal = self.strategy.evaluate(history, self.state.position)
            self.state.last_signal = self._serialize_signal(signal, candle.timestamp)
            extend_event = self._maybe_extend_take_profit(self.state.position, candle, atr_value, signal)
            if extend_event:
                new_events.append(extend_event)
            self._update_trailing_stop(self.state.position, candle.close, atr_value)
            exit_result = None if self.state.pending_order is not None else self._maybe_exit_position(
                candle,
                history,
                signal=signal,
            )
            if exit_result is not None:
                new_events.append(exit_result)
                closed_this_bar = True

        if self.state.position is None and self.state.pending_order is None and not closed_this_bar and not had_pending_order:
            signal = self.strategy.evaluate(history, None)
            self.state.last_signal = self._serialize_signal(signal, candle.timestamp)
            if signal.action == Action.BUY and not self._is_duplicate_order("BUY", candle.timestamp):
                block_reason = self._entry_block_reason(candle, current_bar_index)
                if block_reason:
                    event = "{0} BLOCKED {1} reason={2}".format(candle.timestamp, self.config.market, block_reason)
                    new_events.append(event)
                    self._append_journal(
                        {
                            "event_type": "blocked",
                            "timestamp": candle.timestamp,
                            "market": self.config.market,
                            "reason": block_reason,
                        }
                    )
                else:
                    event = self._maybe_enter_position(candle, atr_value, drawdown_fraction, signal)
                    if event:
                        new_events.append(event)

        self.state.history = history
        self.state.last_processed_timestamp = candle.timestamp
        self.state.processed_bars += 1
        self.state.events.extend(new_events)
        self.state.events = self.state.events[-500:]
        self._save_state()
        return new_events

    def check_live_market_exit(self, current_price: Optional[float] = None, timestamp: Optional[str] = None) -> List[str]:
        if self.state is None:
            raise ValueError("runtime must be bootstrapped before check_live_market_exit")
        if self.mode != "live":
            return []
        if self.broker is None:
            raise ValueError("live mode requires broker")
        if self.state.position is None or self.state.pending_order is not None:
            return []

        market_price = current_price
        if market_price is None:
            ticker_payload = self.broker.get_ticker([self.config.market])
            if not ticker_payload:
                return []
            market_price = float(ticker_payload[0].get("trade_price", 0.0))
        if market_price <= 0:
            return []

        history = list(self.state.history)
        atr_values = atr(history, self.config.risk.atr_period)
        atr_value = atr_values[-1] or (market_price * self.config.risk.minimum_stop_fraction)
        previous_trailing_stop = float(self.state.position.trailing_stop)
        self._update_trailing_stop(self.state.position, market_price, atr_value)

        event_timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        synthetic_candle = Candle(
            timestamp=event_timestamp,
            open=market_price,
            high=market_price,
            low=market_price,
            close=market_price,
            volume=0.0,
        )
        exit_result = self._maybe_exit_position(synthetic_candle, history, allow_strategy_exit=False)

        changed = exit_result is not None or self.state.position.trailing_stop != previous_trailing_stop
        if not changed:
            return []

        events: List[str] = []
        if exit_result is not None:
            events.append(exit_result)
            self.state.events.append(exit_result)
            self.state.events = self.state.events[-500:]
        self._save_state()
        return events

    def summary(self) -> Dict[str, Any]:
        if self.state is None:
            raise ValueError("runtime must be bootstrapped before summary")

        close_price = self.state.history[-1].close if self.state.history else 0.0
        equity = self.state.cash + self._position_market_value(self.state.position, close_price)
        day_key = self._day_key(self.state.last_processed_timestamp)

        return {
            "market": self.state.market,
            "mode": self.mode,
            "cash": round(self.state.cash, 2),
            "equity": round(equity, 2),
            "trade_count": len(self.state.closed_trades),
            "trades_today": self._trades_started_for_day(day_key),
            "realized_pnl_today": round(self._realized_pnl_for_day(day_key), 2),
            "position": self._serialize_position(self.state.position),
            "pending_order": self._serialize_pending_order(self.state.pending_order),
            "asset_snapshot": self.state.asset_snapshot,
            "last_asset_sync_timestamp": self.state.last_asset_sync_timestamp,
            "last_signal": self.state.last_signal,
            "last_processed_timestamp": self.state.last_processed_timestamp,
            "processed_bars": self.state.processed_bars,
            "state_path": self.state_path,
        }

    def reconcile_live_snapshot(self) -> Dict[str, Any]:
        if self.state is None:
            raise ValueError("runtime must be bootstrapped before reconcile_live_snapshot")
        if self.mode != "live":
            raise ValueError("reconcile_live_snapshot requires live mode")
        if self.broker is None:
            raise ValueError("live mode requires broker")

        event_timestamp = datetime.now(timezone.utc).isoformat()
        events: List[str] = []

        balances = self.broker.get_accounts()
        asset_payload = {
            "type": "myAsset",
            "assets": [
                {
                    "currency": item.currency,
                    "balance": item.balance,
                    "locked": item.locked,
                }
                for item in balances
            ],
            "timestamp": event_timestamp,
        }
        events.extend(self.apply_myasset_event(asset_payload))

        if self.state.pending_order is not None:
            events.extend(self._reconcile_live_pending_order(event_timestamp, self.state.processed_bars))

        open_orders = self.broker.list_open_orders(market=self.config.market, states=["wait", "watch"])
        chance = self._get_live_order_chance()
        report = {
            "summary": self.summary(),
            "open_orders": open_orders,
            "open_order_count": len(open_orders),
            "chance": {
                "bid_balance": round(self._chance_balance(chance, "bid_account"), 8),
                "ask_balance": round(self._chance_balance(chance, "ask_account"), 8),
                "bid_min_total": round(self._chance_min_total(chance, "bid"), 8),
                "ask_min_total": round(self._chance_min_total(chance, "ask"), 8),
            },
            "events": events,
            "reconciled_at": event_timestamp,
        }
        return report

    def apply_myorder_event(self, payload: Dict[str, Any]) -> List[str]:
        if self.state is None:
            raise ValueError("runtime must be bootstrapped before apply_myorder_event")

        if payload.get("type") != "myOrder":
            return []
        if payload.get("code") and payload["code"] != self.config.market:
            return []

        order = self.state.pending_order
        if order is None:
            event = "MYORDER IGNORED {0} reason=no_pending_order".format(payload.get("uuid", ""))
            self.state.events.append(event)
            self.state.events = self.state.events[-500:]
            self._save_state()
            return [event]

        if payload.get("uuid") != order.uuid:
            event = "MYORDER IGNORED {0} reason=pending_uuid_mismatch".format(payload.get("uuid", ""))
            self.state.events.append(event)
            self.state.events = self.state.events[-500:]
            self._save_state()
            return [event]

        event_timestamp = self._event_timestamp(payload)
        state_name = str(payload.get("state", ""))
        executed_volume = self._to_float(payload.get("executed_volume", 0.0))
        executed_funds = self._to_float(payload.get("executed_funds", 0.0))
        paid_fee = self._to_float(payload.get("paid_fee", 0.0))

        delta_volume = max(0.0, executed_volume - order.applied_executed_volume)
        delta_funds = max(0.0, executed_funds - order.applied_executed_funds)
        delta_fee = max(0.0, paid_fee - order.applied_paid_fee)

        new_events: List[str] = []
        if delta_volume > 0.0:
            fill_price = delta_funds / delta_volume if delta_volume > 0 else self._to_float(payload.get("avg_price", 0.0))
            if order.side == "bid":
                new_events.append(self._apply_buy_fill(order, event_timestamp, delta_volume, delta_funds, delta_fee, fill_price))
            elif order.side == "ask":
                new_events.append(self._apply_sell_fill(order, event_timestamp, delta_volume, delta_funds, delta_fee, fill_price))

        order.applied_executed_volume = executed_volume
        order.applied_executed_funds = executed_funds
        order.applied_paid_fee = paid_fee
        order.last_state = state_name
        order.last_update_timestamp = event_timestamp

        if state_name in ("done", "cancel", "prevented"):
            done_event = "MYORDER {0} {1} state={2}".format(order.side.upper(), order.market, state_name)
            new_events.append(done_event)
            self._append_journal(
                {
                    "event_type": "myorder_done",
                    "timestamp": event_timestamp,
                    "market": order.market,
                    "side": order.side,
                    "state": state_name,
                    "uuid": order.uuid,
                }
            )
            self.state.pending_order = None

        self.state.events.extend(new_events)
        self.state.events = self.state.events[-500:]
        self._save_state()
        return new_events

    def apply_myasset_event(self, payload: Dict[str, Any]) -> List[str]:
        if self.state is None:
            raise ValueError("runtime must be bootstrapped before apply_myasset_event")

        if payload.get("type") != "myAsset":
            return []

        assets = payload.get("assets", []) or []
        snapshot = {}
        for item in assets:
            currency = str(item.get("currency", "")).upper()
            if not currency:
                continue
            snapshot[currency] = {
                "balance": self._to_float(item.get("balance", 0.0)),
                "locked": self._to_float(item.get("locked", 0.0)),
            }

        self.state.asset_snapshot = snapshot
        event_timestamp = self._event_timestamp(payload)
        self.state.last_asset_sync_timestamp = event_timestamp

        quote_currency = self._quote_currency()
        base_currency = self._base_currency()
        quote_available = snapshot.get(quote_currency, {}).get("balance", 0.0)
        base_total = (
            snapshot.get(base_currency, {}).get("balance", 0.0)
            + snapshot.get(base_currency, {}).get("locked", 0.0)
        )
        self.state.cash = quote_available

        events = [
            "MYASSET SYNC {0} cash={1:.2f} base_total={2:.8f}".format(
                self.config.market,
                quote_available,
                base_total,
            )
        ]

        mismatch = self._asset_mismatch_event(base_total)
        if mismatch:
            events.append(mismatch)

        self._append_journal(
            {
                "event_type": "myasset_sync",
                "timestamp": event_timestamp,
                "market": self.config.market,
                "quote_currency": quote_currency,
                "base_currency": base_currency,
                "cash": round(quote_available, 8),
                "base_total": round(base_total, 8),
            }
        )
        self.state.events.extend(events)
        self.state.events = self.state.events[-500:]
        self._save_state()
        return events

    def _maybe_enter_position(self, candle: Candle, atr_value: float, drawdown_fraction: float, signal: Signal) -> Optional[str]:
        trade_plan = self.risk.build_trade_plan(
            candle.close,
            atr_value,
            drawdown_fraction,
            signal.reasons,
        )
        if trade_plan.blocked:
            return self._blocked_event(candle.timestamp, trade_plan.block_reason)

        available_cash = self.state.cash
        min_total = 0.0
        if self.mode == "live":
            chance = self._get_live_order_chance()
            available_cash = self._chance_balance(chance, "bid_account")
            min_total = self._chance_min_total(chance, "bid")
            self.state.cash = available_cash

        budget = available_cash * trade_plan.size_fraction
        if min_total > 0 and budget < min_total:
            return self._blocked_event(candle.timestamp, "minimum_order_bid")

        entry_price = self._apply_buy_slippage(candle.close)
        quantity = budget / entry_price
        total_cost = self._buy_total_cost(entry_price, quantity)

        if quantity <= 0 or total_cost > available_cash:
            return self._blocked_event(candle.timestamp, "insufficient_cash")

        if self.mode == "live":
            response = self.broker.create_order(
                market=self.config.market,
                side="bid",
                ord_type="price",
                price=self._format_order_number(budget),
            )
            self.state.pending_order = PendingOrder(
                uuid=response["uuid"],
                market=self.config.market,
                side="bid",
                order_type="price",
                requested_price=budget,
                requested_volume=quantity,
                created_timestamp=candle.timestamp,
                created_bar_index=self.state.processed_bars,
                strategy_score=signal.score,
                stop_loss=trade_plan.stop_loss,
                take_profit=trade_plan.take_profit,
                trailing_stop=entry_price - trade_plan.trailing_gap,
            )
            self.state.last_order_timestamp = candle.timestamp
            self.state.last_order_action = "BUY"
            event = "{0} LIVE ORDER_SUBMITTED BUY {1} uuid={2} budget={3:.2f} score={4:.1f}".format(
                candle.timestamp,
                self.config.market,
                response["uuid"],
                budget,
                signal.score,
            )
            self._append_journal(
                {
                    "event_type": "buy_submitted",
                    "timestamp": candle.timestamp,
                    "market": self.config.market,
                    "uuid": response["uuid"],
                    "budget": round(budget, 2),
                    "score": signal.score,
                    "reasons": signal.reasons,
                }
            )
            return event

        self.state.cash = max(0.0, available_cash - total_cost)
        self.state.position = Position(
            market=self.config.market,
            entry_timestamp=candle.timestamp,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=trade_plan.stop_loss,
            take_profit=trade_plan.take_profit,
            trailing_stop=entry_price - trade_plan.trailing_gap,
            entry_score=signal.score,
        )
        self.state.last_order_timestamp = candle.timestamp
        self.state.last_order_action = "BUY"

        event = "{0} {1} BUY {2} qty={3:.8f} price={4:.2f} score={5:.1f} reasons={6}".format(
            candle.timestamp,
            self.mode.upper(),
            self.config.market,
            quantity,
            entry_price,
            signal.score,
            ",".join(signal.reasons),
        )
        self._append_journal(
            {
                "event_type": "buy",
                "timestamp": candle.timestamp,
                "market": self.config.market,
                "quantity": round(quantity, 8),
                "price": round(entry_price, 2),
                "score": signal.score,
                "reasons": signal.reasons,
            }
        )
        return event

    def _maybe_exit_position(
        self,
        candle: Candle,
        history: List[Candle],
        allow_strategy_exit: bool = True,
        signal: Optional[Signal] = None,
    ) -> Optional[str]:
        position = self.state.position
        if position is None:
            return None

        quantity = position.quantity
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
        elif allow_strategy_exit:
            signal = signal or self.strategy.evaluate(history, position)
            self.state.last_signal = self._serialize_signal(signal, candle.timestamp)
            if signal.action == Action.SELL and not self._is_duplicate_order("SELL", candle.timestamp):
                exit_reason = "strategy_exit"
                raw_exit_price = candle.close

        if exit_reason is None:
            return None

        if self.mode == "live":
            chance = self._get_live_order_chance()
            available_quantity = self._chance_balance(chance, "ask_account")
            min_total = self._chance_min_total(chance, "ask")
            if available_quantity <= 0:
                return self._blocked_event(candle.timestamp, "live_position_mismatch")
            if available_quantity < (position.quantity * 0.9):
                return self._blocked_event(candle.timestamp, "live_position_mismatch")
            quantity = min(position.quantity, available_quantity)
            if min_total > 0 and (raw_exit_price * quantity) < min_total:
                return self._blocked_event(candle.timestamp, "minimum_order_ask")
            response = self.broker.create_order(
                market=self.config.market,
                side="ask",
                ord_type="market",
                volume=self._format_order_number(quantity),
            )
            self.state.pending_order = PendingOrder(
                uuid=response["uuid"],
                market=self.config.market,
                side="ask",
                order_type="market",
                requested_price=raw_exit_price,
                requested_volume=quantity,
                created_timestamp=candle.timestamp,
                created_bar_index=self.state.processed_bars,
                strategy_score=position.entry_score,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
                trailing_stop=position.trailing_stop,
            )
            self.state.last_order_timestamp = candle.timestamp
            self.state.last_order_action = "SELL"
            event = "{0} LIVE ORDER_SUBMITTED SELL {1} uuid={2} qty={3:.8f} reason={4}".format(
                candle.timestamp,
                self.config.market,
                response["uuid"],
                quantity,
                exit_reason,
            )
            self._append_journal(
                {
                    "event_type": "sell_submitted",
                    "timestamp": candle.timestamp,
                    "market": self.config.market,
                    "uuid": response["uuid"],
                    "quantity": round(quantity, 8),
                    "reason": exit_reason,
                }
            )
            return event

        exit_price = self._apply_sell_slippage(raw_exit_price)
        proceeds = self._sell_total_proceeds(exit_price, quantity)
        self.state.cash += proceeds
        trade = self._close_trade(position, candle.timestamp, exit_price, exit_reason, quantity=quantity)
        self.state.closed_trades.append(trade)
        self.state.position = None
        self.state.last_order_timestamp = candle.timestamp
        self.state.last_order_action = "SELL"
        self.state.last_exit_timestamp = candle.timestamp
        self.state.last_exit_bar_index = self.state.processed_bars

        event = "{0} {1} SELL {2} qty={3:.8f} price={4:.2f} reason={5} pnl={6:.2f}".format(
            candle.timestamp,
            self.mode.upper(),
            self.config.market,
            trade.quantity,
            exit_price,
            exit_reason,
            trade.net_pnl,
        )
        self._append_journal(
            {
                "event_type": "sell",
                "timestamp": candle.timestamp,
                "market": self.config.market,
                "quantity": round(trade.quantity, 8),
                "price": round(exit_price, 2),
                "reason": exit_reason,
                "pnl": round(trade.net_pnl, 2),
            }
        )
        return event

    def _close_trade(
        self,
        position: Position,
        exit_timestamp: str,
        exit_price: float,
        exit_reason: str,
        quantity: Optional[float] = None,
    ) -> ClosedTrade:
        trade_quantity = position.quantity if quantity is None else quantity
        gross_pnl = (exit_price - position.entry_price) * trade_quantity
        net_pnl = self._sell_total_proceeds(exit_price, trade_quantity) - self._buy_total_cost(
            position.entry_price,
            trade_quantity,
        )
        return_pct = ((exit_price - position.entry_price) / position.entry_price) * 100.0
        return ClosedTrade(
            market=position.market,
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=exit_timestamp,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=trade_quantity,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            return_pct=return_pct,
            exit_reason=exit_reason,
        )

    def _update_trailing_stop(self, position: Position, close: float, atr_value: float) -> None:
        fallback_gap = close * self.config.risk.minimum_stop_fraction
        trailing_gap = max(fallback_gap, atr_value * self.config.risk.trailing_atr_multiple)
        position.trailing_stop = max(position.trailing_stop, close - trailing_gap)

    def _maybe_extend_take_profit(
        self,
        position: Position,
        candle: Candle,
        atr_value: float,
        signal: Signal,
    ) -> Optional[str]:
        if signal.action == Action.SELL:
            return None

        previous_take_profit = float(position.take_profit)
        next_take_profit = self.risk.extend_take_profit(
            current_price=candle.close,
            current_take_profit=previous_take_profit,
            atr_value=atr_value,
            signal_reasons=signal.reasons,
        )
        if next_take_profit <= previous_take_profit + 1e-12:
            return None

        position.take_profit = next_take_profit
        event = (
            "{0} TAKE_PROFIT_EXTENDED {1} from={2:.2f} to={3:.2f} reasons={4}".format(
                candle.timestamp,
                position.market,
                previous_take_profit,
                next_take_profit,
                ",".join(signal.reasons),
            )
        )
        self._append_journal(
            {
                "event_type": "take_profit_extended",
                "timestamp": candle.timestamp,
                "market": position.market,
                "from_take_profit": round(previous_take_profit, 8),
                "to_take_profit": round(next_take_profit, 8),
                "reasons": signal.reasons,
            }
        )
        return event

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

    def _is_duplicate_order(self, action: str, timestamp: str) -> bool:
        return self.state.last_order_action == action and self.state.last_order_timestamp == timestamp

    def _entry_block_reason(self, candle: Candle, current_bar_index: int) -> str:
        if self.state.pending_order is not None:
            return "pending_order"
        if not self._is_allowed_weekday(candle.timestamp):
            return "weekday_filter"
        if not self._is_within_session(candle.timestamp):
            return "session_filter"
        if self._is_in_cooldown(current_bar_index):
            return "cooldown_after_exit"

        day_key = self._day_key(candle.timestamp)
        if self._trades_started_for_day(day_key) >= self.config.runtime.max_trades_per_day:
            return "max_trades_per_day"

        realized_pnl = self._realized_pnl_for_day(day_key)
        daily_loss_limit = self.config.initial_cash * self.config.runtime.daily_loss_limit_fraction
        if realized_pnl <= -daily_loss_limit:
            return "daily_loss_limit"
        return ""

    def _is_in_cooldown(self, current_bar_index: int) -> bool:
        cooldown_bars = self.config.runtime.cooldown_bars_after_exit
        if cooldown_bars <= 0 or self.state.last_exit_bar_index < 0:
            return False
        return (current_bar_index - self.state.last_exit_bar_index) <= cooldown_bars

    def _trades_started_for_day(self, day_key: str) -> int:
        if not day_key:
            return 0
        count = 0
        for trade in self.state.closed_trades:
            if self._day_key(trade.entry_timestamp) == day_key:
                count += 1
        if self.state.position is not None and self._day_key(self.state.position.entry_timestamp) == day_key:
            count += 1
        return count

    def _realized_pnl_for_day(self, day_key: str) -> float:
        if not day_key:
            return 0.0
        return sum(
            trade.net_pnl for trade in self.state.closed_trades if self._day_key(trade.exit_timestamp) == day_key
        )

    def _is_allowed_weekday(self, timestamp: str) -> bool:
        parsed = self._parse_timestamp(timestamp)
        if parsed is None:
            return True
        return parsed.weekday() in self.config.runtime.allowed_weekdays

    def _is_within_session(self, timestamp: str) -> bool:
        if not self.config.runtime.session_start or not self.config.runtime.session_end:
            return True
        parsed = self._parse_timestamp(timestamp)
        if parsed is None or not self._timestamp_has_time(timestamp):
            return True
        current_time = parsed.timetz().replace(tzinfo=None)
        return self._parse_clock(self.config.runtime.session_start) <= current_time <= self._parse_clock(
            self.config.runtime.session_end
        )

    def _timestamp_has_time(self, timestamp: str) -> bool:
        return "T" in timestamp or ":" in timestamp

    def _day_key(self, timestamp: str) -> str:
        parsed = self._parse_timestamp(timestamp)
        if parsed is not None:
            return parsed.date().isoformat()
        return timestamp.split("T")[0].split(" ")[0] if timestamp else ""

    def _parse_timestamp(self, timestamp: str) -> Optional[datetime]:
        if not timestamp:
            return None
        normalized = timestamp.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(timestamp, fmt)
            except ValueError:
                continue
        return None

    def _parse_clock(self, value: str) -> datetime_time:
        return datetime.strptime(value, "%H:%M").time()

    def _sync_live_state(self, state: RuntimeState, is_new_state: bool) -> None:
        chance = self._get_live_order_chance()
        accounts = self.broker.get_accounts()
        accounts_by_currency = {item.currency.upper(): item for item in accounts}
        quote_account = accounts_by_currency.get(self._quote_currency())
        base_account = accounts_by_currency.get(self._base_currency())

        quote_balance = quote_account.balance if quote_account is not None else self._chance_balance(chance, "bid_account")
        base_balance = 0.0
        base_avg_buy_price = 0.0
        if base_account is not None:
            base_balance = float(base_account.balance) + float(base_account.locked)
            base_avg_buy_price = float(base_account.avg_buy_price)
        else:
            base_balance = self._chance_balance(chance, "ask_account")

        state.cash = quote_balance
        state.peak_equity = quote_balance if is_new_state else max(state.peak_equity, quote_balance)
        state.asset_snapshot = {
            item.currency.upper(): {
                "balance": float(item.balance),
                "locked": float(item.locked),
            }
            for item in accounts
            if item.currency
        }
        state.last_asset_sync_timestamp = datetime.now(timezone.utc).isoformat()

        if is_new_state and base_balance > 0.0:
            raise ValueError(
                "live bootstrap requires empty {0} balance on exchange for {1}".format(
                    self._base_currency(),
                    self.config.market,
                )
            )

        if not is_new_state and state.position is None and base_balance > 0.0:
            if state.pending_order is not None and state.pending_order.side == "bid":
                self._promote_pending_buy_from_exchange_balance(
                    state,
                    base_balance=base_balance,
                    base_avg_buy_price=base_avg_buy_price,
                )
                return
            raise ValueError(
                "live state mismatch: account already holds {0} for {1}".format(
                    self._base_currency(),
                    self.config.market,
                )
            )

        if not is_new_state and state.position is not None and base_balance <= 0.0:
            if state.pending_order is not None and state.pending_order.side == "ask":
                self._finalize_pending_sell_from_exchange_sync(state)
                return
            raise ValueError(
                "live state mismatch: saved position exists but exchange balance is empty for {0}".format(
                    self.config.market,
                )
            )

    def _promote_pending_buy_from_exchange_balance(
        self,
        state: RuntimeState,
        base_balance: float,
        base_avg_buy_price: float,
    ) -> None:
        order = state.pending_order
        if order is None:
            return

        entry_price = base_avg_buy_price
        if entry_price <= 0.0 and order.applied_executed_volume > 0.0:
            entry_price = order.applied_executed_funds / order.applied_executed_volume
        if entry_price <= 0.0 and order.requested_volume > 0.0:
            entry_price = order.requested_price / order.requested_volume

        event_timestamp = datetime.now(timezone.utc).isoformat()
        state.position = Position(
            market=order.market,
            entry_timestamp=order.last_update_timestamp or event_timestamp,
            entry_price=entry_price,
            quantity=base_balance,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            trailing_stop=order.trailing_stop,
            entry_score=order.strategy_score,
        )
        state.pending_order = None
        state.last_order_action = "BUY"
        state.last_order_timestamp = order.last_update_timestamp or order.created_timestamp or event_timestamp
        state.events.append(
            "LIVE SYNC BUY_PROMOTED {0} qty={1:.8f} avg={2:.2f}".format(
                order.market,
                base_balance,
                entry_price,
            )
        )
        state.events = state.events[-500:]

    def _finalize_pending_sell_from_exchange_sync(self, state: RuntimeState) -> None:
        order = state.pending_order
        position = state.position
        if order is None or position is None:
            return

        event_timestamp = datetime.now(timezone.utc).isoformat()
        trade = self._close_trade(
            position,
            event_timestamp,
            order.requested_price,
            "exchange_sync_exit",
            quantity=position.quantity,
        )
        state.closed_trades.append(trade)
        state.position = None
        state.pending_order = None
        state.last_order_action = "SELL"
        state.last_order_timestamp = event_timestamp
        state.last_exit_timestamp = event_timestamp
        state.last_exit_bar_index = int(state.processed_bars or 0)
        state.events.append(
            "LIVE SYNC SELL_FINALIZED {0} qty={1:.8f} price={2:.2f}".format(
                trade.market,
                trade.quantity,
                trade.exit_price,
            )
        )
        state.events = state.events[-500:]

    def _get_live_order_chance(self) -> Dict[str, Any]:
        if self.broker is None:
            raise ValueError("live mode requires broker")
        return self.broker.get_order_chance(self.config.market)

    def _chance_balance(self, chance: Dict[str, Any], field: str) -> float:
        account = chance.get(field, {}) or {}
        return self._to_float(account.get("balance", 0.0))

    def _chance_min_total(self, chance: Dict[str, Any], side: str) -> float:
        market = chance.get("market", {}) or {}
        side_info = market.get(side, {}) or {}
        return self._to_float(side_info.get("min_total", 0.0))

    def _to_float(self, value: Any) -> float:
        if value in (None, ""):
            return 0.0
        return float(value)

    def _base_currency(self) -> str:
        if "-" not in self.config.market:
            return self.config.market
        return self.config.market.split("-", 1)[1]

    def _quote_currency(self) -> str:
        if "-" not in self.config.market:
            return "KRW"
        return self.config.market.split("-", 1)[0]

    def _format_order_number(self, value: float) -> str:
        text = "{0:.8f}".format(value).rstrip("0").rstrip(".")
        return text or "0"

    def _reconcile_live_pending_order(self, event_timestamp: str, current_bar_index: int) -> List[str]:
        if self.mode != "live" or self.state.pending_order is None:
            return []
        if self.broker is None:
            raise ValueError("live mode requires broker")

        order = self.state.pending_order
        snapshot = self.broker.get_order(uuid=order.uuid)
        events = self._apply_order_snapshot(snapshot, fallback_timestamp=event_timestamp)

        order = self.state.pending_order
        if order is None:
            return events

        if not self._should_cancel_pending_order(order, current_bar_index):
            return events

        cancel_response = self.broker.cancel_order(uuid=order.uuid)
        cancel_events = self._apply_order_snapshot(cancel_response, fallback_timestamp=event_timestamp)
        if self.state.pending_order is not None:
            self.state.pending_order.last_state = "cancel_requested"
            self.state.pending_order.last_update_timestamp = event_timestamp
        cancel_event = "LIVE ORDER_CANCEL_REQUESTED {0} uuid={1} age_bars={2}".format(
            order.market,
            order.uuid,
            current_bar_index - order.created_bar_index,
        )
        self._append_journal(
            {
                "event_type": "pending_order_cancel_requested",
                "timestamp": event_timestamp,
                "market": order.market,
                "uuid": order.uuid,
                "age_bars": current_bar_index - order.created_bar_index,
            }
        )
        return events + cancel_events + [cancel_event]

    def _apply_order_snapshot(self, snapshot: Dict[str, Any], fallback_timestamp: str) -> List[str]:
        if self.state.pending_order is None:
            return []
        if snapshot.get("uuid") != self.state.pending_order.uuid:
            return []

        executed_volume = self._to_float(snapshot.get("executed_volume", 0.0))
        executed_funds = self._snapshot_executed_funds(snapshot)
        paid_fee = self._to_float(snapshot.get("paid_fee", 0.0))
        avg_price = executed_funds / executed_volume if executed_volume > 0 else 0.0
        event_timestamp = snapshot.get("created_at") or fallback_timestamp

        payload = {
            "type": "myOrder",
            "code": snapshot.get("market", self.state.pending_order.market),
            "uuid": snapshot["uuid"],
            "ask_bid": str(snapshot.get("side", self.state.pending_order.side)).upper(),
            "state": snapshot.get("state", self.state.pending_order.last_state or "wait"),
            "avg_price": avg_price,
            "executed_volume": executed_volume,
            "executed_funds": executed_funds,
            "paid_fee": paid_fee,
            "timestamp": event_timestamp,
        }
        return self.apply_myorder_event(payload)

    def _snapshot_executed_funds(self, snapshot: Dict[str, Any]) -> float:
        trades = snapshot.get("trades", []) or []
        if trades:
            return sum(self._to_float(item.get("funds", 0.0)) for item in trades)
        return self._to_float(snapshot.get("executed_funds", 0.0))

    def _should_cancel_pending_order(self, order: PendingOrder, current_bar_index: int) -> bool:
        max_bars = self.config.runtime.pending_order_max_bars
        if max_bars <= 0:
            return False
        if order.last_state not in ("", "wait", "watch"):
            return False
        return (current_bar_index - order.created_bar_index) >= max_bars

    def _append_journal(self, payload: Dict[str, Any]) -> None:
        record = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "market": self.config.market,
            "mode": self.mode,
            "cash": round(self.state.cash, 2),
            "position": self._serialize_position(self.state.position),
            "pending_order": self._serialize_pending_order(self.state.pending_order),
            "asset_snapshot": self.state.asset_snapshot,
        }
        record.update(payload)
        self._notify_record(record)

        if not self.config.runtime.journal_path:
            return

        journal_path = os.fspath(self.config.runtime.journal_path)
        directory = os.path.dirname(journal_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(journal_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _notify_record(self, record: Dict[str, Any]) -> None:
        try:
            self.notifier.notify(record)
        except NotificationError as exc:
            if self.state is not None:
                self.state.events.append("NOTIFY ERROR {0}".format(exc))
                self.state.events = self.state.events[-500:]

    def _blocked_event(self, timestamp: str, reason: str) -> str:
        event = "{0} BLOCKED {1} reason={2}".format(timestamp, self.config.market, reason)
        self._append_journal(
            {
                "event_type": "blocked",
                "timestamp": timestamp,
                "market": self.config.market,
                "reason": reason,
            }
        )
        return event

    def _load_state(self) -> Optional[RuntimeState]:
        self._state_restore_notice = ""
        state_candidates = [
            (self.state_path, False),
            (self._backup_state_path(), True),
        ]
        last_error = None
        saw_resettable_mismatch = False

        for candidate_path, is_backup in state_candidates:
            if not os.path.exists(candidate_path):
                continue
            try:
                with open(candidate_path, "r", encoding="utf-8-sig") as handle:
                    payload = json.load(handle)
                state = self._runtime_state_from_payload(payload)
                mismatch_reason = self._state_config_mismatch_reason(state)
                if mismatch_reason:
                    self._state_restore_notice = "STATE RESET reason={0} path={1}".format(
                        mismatch_reason,
                        candidate_path,
                    )
                    last_error = ValueError(mismatch_reason)
                    saw_resettable_mismatch = True
                    continue
                if is_backup:
                    state.events.append("STATE RECOVERED source=backup path={0}".format(candidate_path))
                    state.events = state.events[-500:]
                return state
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                continue

        if last_error is not None:
            if saw_resettable_mismatch:
                return None
            raise ValueError("state restore failed for {0}: {1}".format(self.state_path, last_error))
        return None

    def _runtime_state_from_payload(self, payload: Dict[str, Any]) -> RuntimeState:
        return RuntimeState(
            market=payload["market"],
            cash=float(payload["cash"]),
            peak_equity=float(payload["peak_equity"]),
            candle_unit=int(payload.get("candle_unit", 0)),
            history=[self._deserialize_candle(item) for item in payload.get("history", [])],
            position=self._deserialize_position(payload.get("position")),
            closed_trades=[self._deserialize_trade(item) for item in payload.get("closed_trades", [])],
            events=list(payload.get("events", [])),
            last_processed_timestamp=payload.get("last_processed_timestamp", ""),
            last_order_timestamp=payload.get("last_order_timestamp", ""),
            last_order_action=payload.get("last_order_action", ""),
            last_exit_timestamp=payload.get("last_exit_timestamp", ""),
            last_exit_bar_index=int(payload.get("last_exit_bar_index", -1)),
            processed_bars=int(payload.get("processed_bars", len(payload.get("history", [])))),
            last_signal=payload.get("last_signal"),
            last_startup_signal_timestamp=payload.get("last_startup_signal_timestamp", ""),
            pending_order=self._deserialize_pending_order(payload.get("pending_order")),
            asset_snapshot=payload.get("asset_snapshot", {}),
            last_asset_sync_timestamp=payload.get("last_asset_sync_timestamp", ""),
        )

    def _save_state(self) -> None:
        directory = os.path.dirname(self.state_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        payload = {
            "market": self.state.market,
            "cash": self.state.cash,
            "peak_equity": self.state.peak_equity,
            "candle_unit": self.config.upbit.candle_unit,
            "history": [self._serialize_candle(candle) for candle in self.state.history[-self.config.runtime.max_history :]],
            "position": self._serialize_position(self.state.position),
            "pending_order": self._serialize_pending_order(self.state.pending_order),
            "asset_snapshot": self.state.asset_snapshot,
            "last_asset_sync_timestamp": self.state.last_asset_sync_timestamp,
            "closed_trades": [self._serialize_trade(trade) for trade in self.state.closed_trades],
            "events": self.state.events[-500:],
            "last_processed_timestamp": self.state.last_processed_timestamp,
            "last_order_timestamp": self.state.last_order_timestamp,
            "last_order_action": self.state.last_order_action,
            "last_exit_timestamp": self.state.last_exit_timestamp,
            "last_exit_bar_index": self.state.last_exit_bar_index,
            "processed_bars": self.state.processed_bars,
            "last_signal": self.state.last_signal,
            "last_startup_signal_timestamp": self.state.last_startup_signal_timestamp,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        temp_path = self.state_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        for attempt in range(5):
            try:
                os.replace(temp_path, self.state_path)
                self._write_backup_state()
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)

    def _backup_state_path(self) -> str:
        return self.state_path + ".bak"

    def _state_config_mismatch_reason(self, state: RuntimeState) -> str:
        if state.market != self.config.market:
            return "market_mismatch expected={0} actual={1}".format(self.config.market, state.market)

        state_candle_unit = self._state_candle_unit(state)
        expected_candle_unit = int(self.config.upbit.candle_unit)
        if state_candle_unit and state_candle_unit != expected_candle_unit:
            return "candle_unit_mismatch expected={0} actual={1}".format(
                expected_candle_unit,
                state_candle_unit,
            )
        return ""

    def _state_candle_unit(self, state: RuntimeState) -> int:
        if state.candle_unit > 0:
            return int(state.candle_unit)
        return self._infer_history_candle_unit(state.history)

    def _infer_history_candle_unit(self, history: List[Candle]) -> int:
        if len(history) < 2:
            return 0

        deltas: List[int] = []
        previous_timestamp = None
        for candle in history[-50:]:
            current_timestamp = self._parse_candle_timestamp(candle.timestamp)
            if current_timestamp is None:
                continue
            if previous_timestamp is not None:
                delta_minutes = int(round((current_timestamp - previous_timestamp).total_seconds() / 60.0))
                if delta_minutes > 0:
                    deltas.append(delta_minutes)
            previous_timestamp = current_timestamp

        if not deltas:
            return 0

        return Counter(deltas).most_common(1)[0][0]

    def _parse_candle_timestamp(self, timestamp: str) -> Optional[datetime]:
        if not timestamp:
            return None
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _write_backup_state(self) -> None:
        backup_path = self._backup_state_path()
        try:
            shutil.copyfile(self.state_path, backup_path)
        except OSError:
            return

    def _serialize_signal(self, signal: Signal, timestamp: str) -> Dict[str, Any]:
        return {
            "timestamp": timestamp,
            "action": signal.action.value,
            "score": signal.score,
            "confidence": signal.confidence,
            "reasons": signal.reasons,
        }

    def _serialize_candle(self, candle: Candle) -> Dict[str, Any]:
        return {
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }

    def _deserialize_candle(self, payload: Dict[str, Any]) -> Candle:
        return Candle(
            timestamp=payload["timestamp"],
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=float(payload["volume"]),
        )

    def _serialize_position(self, position: Optional[Position]) -> Optional[Dict[str, Any]]:
        if position is None:
            return None
        return {
            "market": position.market,
            "entry_timestamp": position.entry_timestamp,
            "entry_price": position.entry_price,
            "quantity": position.quantity,
            "stop_loss": position.stop_loss,
            "take_profit": position.take_profit,
            "trailing_stop": position.trailing_stop,
            "entry_score": position.entry_score,
        }

    def _serialize_pending_order(self, order: Optional[PendingOrder]) -> Optional[Dict[str, Any]]:
        if order is None:
            return None
        return {
            "uuid": order.uuid,
            "market": order.market,
            "side": order.side,
            "order_type": order.order_type,
            "requested_price": order.requested_price,
            "requested_volume": order.requested_volume,
            "created_timestamp": order.created_timestamp,
            "created_bar_index": order.created_bar_index,
            "strategy_score": order.strategy_score,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "trailing_stop": order.trailing_stop,
            "applied_executed_volume": order.applied_executed_volume,
            "applied_executed_funds": order.applied_executed_funds,
            "applied_paid_fee": order.applied_paid_fee,
            "last_state": order.last_state,
            "last_update_timestamp": order.last_update_timestamp,
        }

    def _deserialize_position(self, payload: Optional[Dict[str, Any]]) -> Optional[Position]:
        if payload is None:
            return None
        return Position(
            market=payload["market"],
            entry_timestamp=payload["entry_timestamp"],
            entry_price=float(payload["entry_price"]),
            quantity=float(payload["quantity"]),
            stop_loss=float(payload["stop_loss"]),
            take_profit=float(payload["take_profit"]),
            trailing_stop=float(payload["trailing_stop"]),
            entry_score=float(payload["entry_score"]),
        )

    def _deserialize_pending_order(self, payload: Optional[Dict[str, Any]]) -> Optional[PendingOrder]:
        if payload is None:
            return None
        return PendingOrder(
            uuid=payload["uuid"],
            market=payload["market"],
            side=payload["side"],
            order_type=payload["order_type"],
            requested_price=float(payload["requested_price"]),
            requested_volume=float(payload["requested_volume"]),
            created_timestamp=payload["created_timestamp"],
            created_bar_index=int(payload.get("created_bar_index", 0)),
            strategy_score=float(payload["strategy_score"]),
            stop_loss=float(payload.get("stop_loss", 0.0)),
            take_profit=float(payload.get("take_profit", 0.0)),
            trailing_stop=float(payload.get("trailing_stop", 0.0)),
            applied_executed_volume=float(payload.get("applied_executed_volume", 0.0)),
            applied_executed_funds=float(payload.get("applied_executed_funds", 0.0)),
            applied_paid_fee=float(payload.get("applied_paid_fee", 0.0)),
            last_state=payload.get("last_state", ""),
            last_update_timestamp=payload.get("last_update_timestamp", ""),
        )

    def _serialize_trade(self, trade: ClosedTrade) -> Dict[str, Any]:
        return {
            "market": trade.market,
            "entry_timestamp": trade.entry_timestamp,
            "exit_timestamp": trade.exit_timestamp,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "quantity": trade.quantity,
            "gross_pnl": trade.gross_pnl,
            "net_pnl": trade.net_pnl,
            "return_pct": trade.return_pct,
            "exit_reason": trade.exit_reason,
        }

    def _deserialize_trade(self, payload: Dict[str, Any]) -> ClosedTrade:
        return ClosedTrade(
            market=payload["market"],
            entry_timestamp=payload["entry_timestamp"],
            exit_timestamp=payload["exit_timestamp"],
            entry_price=float(payload["entry_price"]),
            exit_price=float(payload["exit_price"]),
            quantity=float(payload["quantity"]),
            gross_pnl=float(payload["gross_pnl"]),
            net_pnl=float(payload["net_pnl"]),
            return_pct=float(payload["return_pct"]),
            exit_reason=payload["exit_reason"],
        )

    def _apply_buy_fill(
        self,
        order: PendingOrder,
        event_timestamp: str,
        delta_volume: float,
        delta_funds: float,
        delta_fee: float,
        fill_price: float,
    ) -> str:
        if self.state.position is None:
            self.state.position = Position(
                market=order.market,
                entry_timestamp=event_timestamp or order.created_timestamp,
                entry_price=fill_price,
                quantity=delta_volume,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                trailing_stop=order.trailing_stop,
                entry_score=order.strategy_score,
            )
        else:
            total_quantity = self.state.position.quantity + delta_volume
            weighted_price = 0.0
            if total_quantity > 0:
                weighted_price = (
                    (self.state.position.entry_price * self.state.position.quantity) + (fill_price * delta_volume)
                ) / total_quantity
            self.state.position.entry_price = weighted_price
            self.state.position.quantity = total_quantity
            self.state.position.stop_loss = order.stop_loss
            self.state.position.take_profit = order.take_profit
            self.state.position.trailing_stop = max(self.state.position.trailing_stop, order.trailing_stop)

        self.state.cash = max(0.0, self.state.cash - delta_funds - delta_fee)
        self.state.last_order_action = "BUY"
        self.state.last_order_timestamp = event_timestamp
        event = "MYORDER BUY_FILL {0} qty={1:.8f} price={2:.2f} fee={3:.2f}".format(
            order.market,
            delta_volume,
            fill_price,
            delta_fee,
        )
        self._append_journal(
            {
                "event_type": "buy_fill",
                "timestamp": event_timestamp,
                "market": order.market,
                "uuid": order.uuid,
                "quantity": round(delta_volume, 8),
                "price": round(fill_price, 8),
                "fee": round(delta_fee, 8),
            }
        )
        return event

    def _apply_sell_fill(
        self,
        order: PendingOrder,
        event_timestamp: str,
        delta_volume: float,
        delta_funds: float,
        delta_fee: float,
        fill_price: float,
    ) -> str:
        if self.state.position is None:
            return "MYORDER SELL_FILL {0} ignored=no_position".format(order.market)

        sell_quantity = min(delta_volume, self.state.position.quantity)
        self.state.cash += max(0.0, delta_funds - delta_fee)
        trade = self._close_trade(
            self.state.position,
            event_timestamp or order.created_timestamp,
            fill_price,
            "myorder_fill",
            quantity=sell_quantity,
        )
        self.state.closed_trades.append(trade)
        self.state.position.quantity -= sell_quantity
        if self.state.position.quantity <= 1e-12:
            self.state.position = None
            self.state.last_exit_timestamp = event_timestamp
            self.state.last_exit_bar_index = self.state.processed_bars
        self.state.last_order_action = "SELL"
        self.state.last_order_timestamp = event_timestamp
        event = "MYORDER SELL_FILL {0} qty={1:.8f} price={2:.2f} pnl={3:.2f}".format(
            order.market,
            sell_quantity,
            fill_price,
            trade.net_pnl,
        )
        self._append_journal(
            {
                "event_type": "sell_fill",
                "timestamp": event_timestamp,
                "market": order.market,
                "uuid": order.uuid,
                "quantity": round(sell_quantity, 8),
                "price": round(fill_price, 8),
                "fee": round(delta_fee, 8),
                "pnl": round(trade.net_pnl, 8),
            }
        )
        return event

    def _event_timestamp(self, payload: Dict[str, Any]) -> str:
        value = payload.get("timestamp") or payload.get("trade_timestamp") or payload.get("order_timestamp")
        return str(value) if value not in (None, "") else ""

    def _asset_mismatch_event(self, base_total: float) -> str:
        tolerance = 1e-12
        if self.state.pending_order is not None:
            pending = self.state.pending_order
            if pending.side == "bid" and base_total > tolerance:
                return "MYASSET NOTICE {0} base_detected_while_buy_pending actual={1:.8f}".format(
                    self.config.market,
                    base_total,
                )
            if pending.side == "ask" and base_total <= tolerance:
                return "MYASSET NOTICE {0} base_cleared_while_sell_pending".format(self.config.market)
            return ""

        if self.state.position is not None:
            expected = self.state.position.quantity
            if expected > tolerance:
                ratio = base_total / expected if expected > 0 else 0.0
                if ratio < 0.9 or ratio > 1.1:
                    return "MYASSET WARNING {0} position_mismatch expected={1:.8f} actual={2:.8f}".format(
                        self.config.market,
                        expected,
                        base_total,
                    )
            return ""

        if base_total > tolerance:
            return "MYASSET WARNING {0} untracked_balance actual={1:.8f}".format(
                self.config.market,
                base_total,
            )
        return ""
