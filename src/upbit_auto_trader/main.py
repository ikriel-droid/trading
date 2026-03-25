import argparse
import copy
import json
import os
import sys
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional

from .backtest import Backtester, format_backtest_report
from .brokers.upbit import UpbitBroker, UpbitError
from .config import AppConfig, load_config
from .datafeed import (
    load_csv_candles,
    merge_candles,
    upbit_candles_to_internal,
    write_csv_candles,
)
from .doctor import build_doctor_report
from .jobs import HEARTBEAT_ENV_VAR, list_job_history
from .optimizer import run_grid_search
from .notifier import DiscordWebhookNotifier, NotificationError
from .presets import (
    apply_strategy_preset,
    default_preset_dir,
    list_strategy_presets,
    save_current_strategy_preset,
    save_grid_search_best_preset,
)
from .profiles import default_profile_dir, list_operator_profiles
from .reporting import default_reports_dir, list_session_reports, load_session_report, write_runtime_report
from .runtime import TradingRuntime
from .scanner import MarketScanner
from .selector import RotatingMarketSelector, StreamingMarketSelector
from .strategy import ProfessionalCryptoStrategy
from .ui import (
    preview_managed_job,
    run_load_profile_action,
    run_preview_profile_action,
    run_save_profile_action,
    run_start_profile_action,
    run_web_ui_server,
)
from .websocket_client import (
    UpbitWebSocketClient,
    build_myorder_subscription,
    build_private_account_subscription,
    build_selector_stream_subscription,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upbit auto trader starter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    csv_parser = subparsers.add_parser("backtest")
    csv_parser.add_argument("--config", required=True)
    csv_parser.add_argument("--csv", required=True)

    signal_parser = subparsers.add_parser("signal")
    signal_parser.add_argument("--config", required=True)
    signal_parser.add_argument("--csv", required=True)

    optimize_parser = subparsers.add_parser("optimize-grid")
    optimize_parser.add_argument("--config", required=True)
    optimize_parser.add_argument("--csv", required=True)
    optimize_parser.add_argument("--buy-thresholds")
    optimize_parser.add_argument("--sell-thresholds")
    optimize_parser.add_argument("--min-adx-values")
    optimize_parser.add_argument("--min-bollinger-width-values")
    optimize_parser.add_argument("--volume-spike-multipliers")
    optimize_parser.add_argument("--top", type=int, default=10)
    optimize_parser.add_argument("--save-best-preset")

    preset_list_parser = subparsers.add_parser("preset-list")
    preset_list_parser.add_argument("--config", required=True)

    preset_save_parser = subparsers.add_parser("preset-save")
    preset_save_parser.add_argument("--config", required=True)
    preset_save_parser.add_argument("--name", required=True)
    preset_save_parser.add_argument("--market")
    preset_save_parser.add_argument("--csv")

    preset_apply_parser = subparsers.add_parser("preset-apply")
    preset_apply_parser.add_argument("--config", required=True)
    preset_apply_parser.add_argument("--preset", required=True)

    profile_list_parser = subparsers.add_parser("profile-list")
    profile_list_parser.add_argument("--config", required=True)

    profile_show_parser = subparsers.add_parser("profile-show")
    profile_show_parser.add_argument("--config", required=True)
    profile_show_parser.add_argument("--profile", required=True)

    profile_preview_parser = subparsers.add_parser("profile-preview")
    profile_preview_parser.add_argument("--config", required=True)
    profile_preview_parser.add_argument("--profile", required=True)

    profile_save_parser = subparsers.add_parser("profile-save")
    profile_save_parser.add_argument("--config", required=True)
    profile_save_parser.add_argument("--name", required=True)
    profile_save_parser.add_argument("--job-type", required=True)
    profile_save_parser.add_argument("--market")
    profile_save_parser.add_argument("--csv")
    profile_save_parser.add_argument("--state")
    profile_save_parser.add_argument("--selector-state")
    profile_save_parser.add_argument("--quote-currency")
    profile_save_parser.add_argument("--max-markets", type=int)
    profile_save_parser.add_argument("--poll-seconds", type=float)
    profile_save_parser.add_argument("--reconcile-every", type=int)
    profile_save_parser.add_argument("--reconcile-every-loops", type=int, default=3)
    profile_save_parser.add_argument("--preset")
    profile_save_parser.add_argument("--auto-restart", action="store_true")
    profile_save_parser.add_argument("--max-restarts", type=int, default=0)
    profile_save_parser.add_argument("--restart-backoff-seconds", type=float, default=0.0)
    profile_save_parser.add_argument("--notes", default="")

    profile_start_parser = subparsers.add_parser("profile-start")
    profile_start_parser.add_argument("--config", required=True)
    profile_start_parser.add_argument("--profile", required=True)

    report_parser = subparsers.add_parser("session-report")
    report_parser.add_argument("--config", required=True)
    report_parser.add_argument("--state", required=True)
    report_parser.add_argument("--mode", choices=("paper", "live"), default="paper")
    report_parser.add_argument("--output-dir")
    report_parser.add_argument("--label", default="")

    report_list_parser = subparsers.add_parser("report-list")
    report_list_parser.add_argument("--config", required=True)
    report_list_parser.add_argument("--output-dir")

    report_show_parser = subparsers.add_parser("report-show")
    report_show_parser.add_argument("--config", required=True)
    report_show_parser.add_argument("--report", required=True)
    report_show_parser.add_argument("--output-dir")

    job_history_parser = subparsers.add_parser("job-history")
    job_history_parser.add_argument("--config", required=True)
    job_history_parser.add_argument("--limit", type=int, default=12)

    job_preview_parser = subparsers.add_parser("job-preview")
    job_preview_parser.add_argument("--config", required=True)
    job_preview_parser.add_argument("--job-type", required=True)
    job_preview_parser.add_argument("--market")
    job_preview_parser.add_argument("--csv")
    job_preview_parser.add_argument("--state")
    job_preview_parser.add_argument("--selector-state")
    job_preview_parser.add_argument("--quote-currency")
    job_preview_parser.add_argument("--max-markets", type=int)
    job_preview_parser.add_argument("--poll-seconds", type=float)
    job_preview_parser.add_argument("--reconcile-every", type=int)
    job_preview_parser.add_argument("--reconcile-every-loops", type=int, default=3)
    job_preview_parser.add_argument("--auto-restart", action="store_true")
    job_preview_parser.add_argument("--max-restarts", type=int, default=0)
    job_preview_parser.add_argument("--restart-backoff-seconds", type=float, default=0.0)

    web_ui_parser = subparsers.add_parser("web-ui")
    web_ui_parser.add_argument("--config", required=True)
    web_ui_parser.add_argument("--state")
    web_ui_parser.add_argument("--selector-state")
    web_ui_parser.add_argument("--csv")
    web_ui_parser.add_argument("--mode", choices=("paper", "live"), default="paper")
    web_ui_parser.add_argument("--host", default="127.0.0.1")
    web_ui_parser.add_argument("--port", type=int, default=8765)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--config", required=True)
    doctor_parser.add_argument("--state")
    doctor_parser.add_argument("--selector-state")

    markets_parser = subparsers.add_parser("markets")
    markets_parser.add_argument("--config", required=True)
    markets_parser.add_argument("--details", action="store_true")

    ticker_parser = subparsers.add_parser("ticker")
    ticker_parser.add_argument("--config", required=True)
    ticker_parser.add_argument("--market")

    sync_parser = subparsers.add_parser("sync-candles")
    sync_parser.add_argument("--config", required=True)
    sync_parser.add_argument("--csv", required=True)
    sync_parser.add_argument("--market")
    sync_parser.add_argument("--count", type=int)
    sync_parser.add_argument("--to")

    scan_parser = subparsers.add_parser("scan-markets")
    scan_parser.add_argument("--config", required=True)
    scan_parser.add_argument("--markets")
    scan_parser.add_argument("--exclude")
    scan_parser.add_argument("--quote-currency")
    scan_parser.add_argument("--max-markets", type=int)

    balances_parser = subparsers.add_parser("balances")
    balances_parser.add_argument("--config", required=True)

    chance_parser = subparsers.add_parser("chance")
    chance_parser.add_argument("--config", required=True)
    chance_parser.add_argument("--market")

    notify_parser = subparsers.add_parser("notify-test")
    notify_parser.add_argument("--config", required=True)
    notify_parser.add_argument("--message", default="manual notification test")

    reconcile_parser = subparsers.add_parser("live-reconcile")
    reconcile_parser.add_argument("--config", required=True)
    reconcile_parser.add_argument("--state", required=True)
    reconcile_parser.add_argument("--market")

    order_show_parser = subparsers.add_parser("order-show")
    order_show_parser.add_argument("--config", required=True)
    order_show_parser.add_argument("--uuid")
    order_show_parser.add_argument("--identifier")

    open_orders_parser = subparsers.add_parser("open-orders")
    open_orders_parser.add_argument("--config", required=True)
    open_orders_parser.add_argument("--market")
    open_orders_parser.add_argument("--state")
    open_orders_parser.add_argument("--states")
    open_orders_parser.add_argument("--page", type=int)
    open_orders_parser.add_argument("--limit", type=int)
    open_orders_parser.add_argument("--order-by")

    preview_parser = subparsers.add_parser("order-preview")
    preview_parser.add_argument("--config", required=True)
    preview_parser.add_argument("--market")
    preview_parser.add_argument("--side", choices=("bid", "ask"), required=True)
    preview_parser.add_argument("--ord-type", choices=("limit", "price", "market"), required=True)
    preview_parser.add_argument("--volume")
    preview_parser.add_argument("--price")

    cancel_parser = subparsers.add_parser("cancel-order")
    cancel_parser.add_argument("--config", required=True)
    cancel_parser.add_argument("--uuid")
    cancel_parser.add_argument("--identifier")

    cancel_open_parser = subparsers.add_parser("cancel-open-orders")
    cancel_open_parser.add_argument("--config", required=True)
    cancel_open_parser.add_argument("--cancel-side", default="all")
    cancel_open_parser.add_argument("--pairs")
    cancel_open_parser.add_argument("--excluded-pairs")
    cancel_open_parser.add_argument("--count", type=int)
    cancel_open_parser.add_argument("--order-by")

    cancel_and_new_parser = subparsers.add_parser("cancel-and-new")
    cancel_and_new_parser.add_argument("--config", required=True)
    cancel_and_new_parser.add_argument("--prev-order-uuid")
    cancel_and_new_parser.add_argument("--prev-order-identifier")
    cancel_and_new_parser.add_argument("--new-ord-type", required=True)
    cancel_and_new_parser.add_argument("--new-volume")
    cancel_and_new_parser.add_argument("--new-price")
    cancel_and_new_parser.add_argument("--new-time-in-force")
    cancel_and_new_parser.add_argument("--new-smp-type")
    cancel_and_new_parser.add_argument("--new-identifier")

    myorder_parser = subparsers.add_parser("listen-myorder")
    myorder_parser.add_argument("--config", required=True)
    myorder_parser.add_argument("--state", required=True)
    myorder_parser.add_argument("--market")
    myorder_parser.add_argument("--max-events", type=int)

    private_parser = subparsers.add_parser("listen-private")
    private_parser.add_argument("--config", required=True)
    private_parser.add_argument("--state", required=True)
    private_parser.add_argument("--market")
    private_parser.add_argument("--max-events", type=int)

    supervisor_parser = subparsers.add_parser("run-live-supervisor")
    supervisor_parser.add_argument("--config", required=True)
    supervisor_parser.add_argument("--state", required=True)
    supervisor_parser.add_argument("--market")
    supervisor_parser.add_argument("--max-events", type=int)
    supervisor_parser.add_argument("--reconcile-every", type=int, default=10)
    supervisor_parser.add_argument("--skip-initial-reconcile", action="store_true")

    loop_parser = subparsers.add_parser("run-loop")
    loop_parser.add_argument("--config", required=True)
    loop_parser.add_argument("--mode", choices=("paper", "live"), default="paper")
    loop_parser.add_argument("--state", required=True)
    loop_parser.add_argument("--replay-csv")
    loop_parser.add_argument("--warmup-csv")
    loop_parser.add_argument("--max-steps", type=int)
    loop_parser.add_argument("--poll-seconds", type=float)

    live_daemon_parser = subparsers.add_parser("run-live-daemon")
    live_daemon_parser.add_argument("--config", required=True)
    live_daemon_parser.add_argument("--state", required=True)
    live_daemon_parser.add_argument("--warmup-csv")
    live_daemon_parser.add_argument("--max-loops", type=int)
    live_daemon_parser.add_argument("--poll-seconds", type=float)
    live_daemon_parser.add_argument("--reconcile-every-loops", type=int, default=3)

    selector_parser = subparsers.add_parser("run-selector")
    selector_parser.add_argument("--config", required=True)
    selector_parser.add_argument("--mode", choices=("paper", "live"), default="paper")
    selector_parser.add_argument("--selector-state", required=True)
    selector_parser.add_argument("--markets")
    selector_parser.add_argument("--exclude")
    selector_parser.add_argument("--quote-currency")
    selector_parser.add_argument("--max-markets", type=int)
    selector_parser.add_argument("--max-steps", type=int)
    selector_parser.add_argument("--poll-seconds", type=float)

    stream_parser = subparsers.add_parser("run-selector-stream")
    stream_parser.add_argument("--config", required=True)
    stream_parser.add_argument("--mode", choices=("paper", "live"), default="paper")
    stream_parser.add_argument("--selector-state", required=True)
    stream_parser.add_argument("--markets")
    stream_parser.add_argument("--exclude")
    stream_parser.add_argument("--quote-currency")
    stream_parser.add_argument("--max-markets", type=int)
    stream_parser.add_argument("--max-events", type=int)

    state_parser = subparsers.add_parser("state-show")
    state_parser.add_argument("--config", required=True)
    state_parser.add_argument("--state", required=True)

    selector_state_parser = subparsers.add_parser("selector-state-show")
    selector_state_parser.add_argument("--config", required=True)
    selector_state_parser.add_argument("--state", required=True)

    return parser


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return value.__dict__
    raise TypeError("unsupported value: {0}".format(type(value).__name__))


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default))


def _market_arg(args: argparse.Namespace, config: AppConfig) -> str:
    return args.market or config.market


def _build_broker(config: AppConfig) -> UpbitBroker:
    return UpbitBroker(config.upbit)


def _build_doctor_report(config_path: str, config: AppConfig, state_path: Optional[str], selector_state_path: Optional[str]) -> dict:
    return build_doctor_report(
        config_path=config_path,
        config=config,
        state_path=state_path,
        selector_state_path=selector_state_path,
    )


def _write_heartbeat(kind: str, phase: str, stale_after_seconds: float, **payload: Any) -> None:
    heartbeat_path = os.environ.get(HEARTBEAT_ENV_VAR, "").strip()
    if not heartbeat_path:
        return

    heartbeat = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "phase": phase,
        "stale_after_seconds": round(max(0.05, float(stale_after_seconds)), 3),
    }
    for key, value in payload.items():
        if value is None:
            continue
        heartbeat[key] = value

    temp_path = heartbeat_path + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(heartbeat, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, heartbeat_path)
    except OSError:
        return


def _parse_markets(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_float_values(value: Optional[str], default: List[float]) -> List[float]:
    if not value:
        return list(default)
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _selector_config_from_args(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    updated = copy.deepcopy(config)
    if getattr(args, "quote_currency", None):
        updated.selector.quote_currency = args.quote_currency
    if getattr(args, "markets", None):
        updated.selector.include_markets = _parse_markets(args.markets)
    if getattr(args, "exclude", None):
        updated.selector.exclude_markets = _parse_markets(args.exclude)
    if getattr(args, "max_markets", None):
        updated.selector.max_markets = args.max_markets
    return updated


def _load_or_fetch_warmup(
    runtime: TradingRuntime,
    config: AppConfig,
    broker: UpbitBroker,
    warmup_csv: Optional[str],
) -> List[Any]:
    if warmup_csv:
        return load_csv_candles(warmup_csv)

    fetch_count = max(config.upbit.candle_count, runtime.strategy.minimum_history() + 5)
    payload = broker.get_minute_candles(
        market=config.market,
        unit=config.upbit.candle_unit,
        count=fetch_count,
    )
    return upbit_candles_to_internal(payload)


def _run_replay_loop(
    runtime: TradingRuntime,
    replay_csv: str,
    warmup_csv: Optional[str],
    max_steps: Optional[int],
) -> int:
    replay_candles = load_csv_candles(replay_csv)
    if not replay_candles:
        raise ValueError("replay csv is empty")

    state_exists = os.path.exists(runtime.state_path)
    if state_exists:
        runtime.bootstrap([])
        candles_to_process = replay_candles
    else:
        if warmup_csv:
            runtime.bootstrap(load_csv_candles(warmup_csv))
            candles_to_process = replay_candles
        else:
            minimum_history = runtime.strategy.minimum_history()
            if len(replay_candles) < minimum_history:
                raise ValueError(
                    "replay csv needs at least {0} candles, got {1}".format(
                        minimum_history,
                        len(replay_candles),
                    )
                )
            runtime.bootstrap(replay_candles[:minimum_history])
            candles_to_process = replay_candles[minimum_history:]

    processed = 0
    last_timestamp = runtime.state.last_processed_timestamp
    _write_heartbeat(
        kind="replay-loop",
        phase="bootstrapped",
        stale_after_seconds=30.0,
        market=runtime.config.market,
        mode=runtime.mode,
        processed=processed,
        last_processed_timestamp=last_timestamp,
    )
    for candle in candles_to_process:
        if last_timestamp and candle.timestamp <= last_timestamp:
            continue
        for event in runtime.process_candle(candle):
            print(event)
        processed += 1
        _write_heartbeat(
            kind="replay-loop",
            phase="processing",
            stale_after_seconds=30.0,
            market=runtime.config.market,
            mode=runtime.mode,
            processed=processed,
            last_processed_timestamp=runtime.state.last_processed_timestamp,
        )
        if max_steps is not None and processed >= max_steps:
            break

    _write_heartbeat(
        kind="replay-loop",
        phase="completed",
        stale_after_seconds=30.0,
        market=runtime.config.market,
        mode=runtime.mode,
        processed=processed,
        last_processed_timestamp=runtime.state.last_processed_timestamp,
    )
    _print_json(runtime.summary())
    return 0


def _run_broker_loop(
    runtime: TradingRuntime,
    broker: UpbitBroker,
    warmup_csv: Optional[str],
    poll_seconds: Optional[float],
    max_steps: Optional[int],
) -> int:
    runtime.broker = broker
    if os.path.exists(runtime.state_path):
        runtime.bootstrap([])
    else:
        runtime.bootstrap(_load_or_fetch_warmup(runtime, runtime.config, broker, warmup_csv))

    poll_interval = poll_seconds if poll_seconds is not None else runtime.config.runtime.poll_seconds
    fetch_count = max(runtime.config.upbit.candle_count, runtime.strategy.minimum_history() + 5)
    loops = 0
    heartbeat_kind = "{0}-loop".format(runtime.mode)
    heartbeat_stale_after = max(30.0, float(poll_interval or 0.0) * 3.0)

    _write_heartbeat(
        kind=heartbeat_kind,
        phase="bootstrapped",
        stale_after_seconds=heartbeat_stale_after,
        market=runtime.config.market,
        mode=runtime.mode,
        cycle=loops,
        last_processed_timestamp=runtime.state.last_processed_timestamp,
    )

    while True:
        payload = broker.get_minute_candles(
            market=runtime.config.market,
            unit=runtime.config.upbit.candle_unit,
            count=fetch_count,
        )
        new_candles = upbit_candles_to_internal(payload)
        last_timestamp = runtime.state.last_processed_timestamp
        processed_candles = 0
        for candle in new_candles:
            if last_timestamp and candle.timestamp <= last_timestamp:
                continue
            for event in runtime.process_candle(candle):
                print(event)
            last_timestamp = runtime.state.last_processed_timestamp
            processed_candles += 1

        loops += 1
        _write_heartbeat(
            kind=heartbeat_kind,
            phase="loop",
            stale_after_seconds=heartbeat_stale_after,
            market=runtime.config.market,
            mode=runtime.mode,
            cycle=loops,
            processed_candles=processed_candles,
            last_processed_timestamp=runtime.state.last_processed_timestamp,
        )
        if max_steps is not None and loops >= max_steps:
            break
        time.sleep(max(poll_interval, 1.0))

    _write_heartbeat(
        kind=heartbeat_kind,
        phase="completed",
        stale_after_seconds=heartbeat_stale_after,
        market=runtime.config.market,
        mode=runtime.mode,
        cycle=loops,
        last_processed_timestamp=runtime.state.last_processed_timestamp,
    )
    _print_json(runtime.summary())
    return 0


def _run_live_daemon(
    config: AppConfig,
    broker: UpbitBroker,
    state_path: str,
    warmup_csv: Optional[str],
    poll_seconds: Optional[float],
    max_loops: Optional[int],
    reconcile_every_loops: int,
) -> int:
    runtime = TradingRuntime(config=config, mode="live", state_path=state_path, broker=broker)
    if os.path.exists(state_path):
        runtime.bootstrap([])
    else:
        runtime.bootstrap(_load_or_fetch_warmup(runtime, config, broker, warmup_csv))

    _print_json({"kind": "reconcile", "data": runtime.reconcile_live_snapshot()})

    poll_interval = poll_seconds if poll_seconds is not None else config.runtime.poll_seconds
    fetch_count = max(config.upbit.candle_count, runtime.strategy.minimum_history() + 5)
    loops = 0
    heartbeat_stale_after = max(30.0, float(poll_interval or 0.0) * 3.0)
    _write_heartbeat(
        kind="live-daemon",
        phase="bootstrapped",
        stale_after_seconds=heartbeat_stale_after,
        market=config.market,
        mode="live",
        cycle=loops,
        last_processed_timestamp=runtime.state.last_processed_timestamp,
    )

    while True:
        payload = broker.get_minute_candles(
            market=config.market,
            unit=config.upbit.candle_unit,
            count=fetch_count,
        )
        new_candles = upbit_candles_to_internal(payload)
        last_timestamp = runtime.state.last_processed_timestamp
        cycle_events: List[str] = []
        processed_candles = 0

        for candle in new_candles:
            if last_timestamp and candle.timestamp <= last_timestamp:
                continue
            cycle_events.extend(runtime.process_candle(candle))
            processed_candles += 1
            last_timestamp = runtime.state.last_processed_timestamp

        loops += 1
        _print_json(
            {
                "kind": "loop",
                "cycle": loops,
                "processed_candles": processed_candles,
                "events": cycle_events,
                "summary": runtime.summary(),
            }
        )
        _write_heartbeat(
            kind="live-daemon",
            phase="loop",
            stale_after_seconds=heartbeat_stale_after,
            market=config.market,
            mode="live",
            cycle=loops,
            processed_candles=processed_candles,
            event_count=len(cycle_events),
            last_processed_timestamp=runtime.state.last_processed_timestamp,
        )

        if reconcile_every_loops > 0 and (loops % reconcile_every_loops) == 0:
            _write_heartbeat(
                kind="live-daemon",
                phase="reconcile",
                stale_after_seconds=heartbeat_stale_after,
                market=config.market,
                mode="live",
                cycle=loops,
                last_processed_timestamp=runtime.state.last_processed_timestamp,
            )
            _print_json({"kind": "reconcile", "data": runtime.reconcile_live_snapshot()})

        if max_loops is not None and loops >= max_loops:
            break
        time.sleep(max(poll_interval, 1.0))

    _write_heartbeat(
        kind="live-daemon",
        phase="completed",
        stale_after_seconds=heartbeat_stale_after,
        market=config.market,
        mode="live",
        cycle=loops,
        last_processed_timestamp=runtime.state.last_processed_timestamp,
    )
    _print_json({"kind": "final", "summary": runtime.summary()})
    return 0


def _run_selector_loop(
    config: AppConfig,
    broker: UpbitBroker,
    mode: str,
    selector_state_path: str,
    explicit_markets: List[str],
    poll_seconds: Optional[float],
    max_steps: Optional[int],
) -> int:
    selector = RotatingMarketSelector(
        config=config,
        mode=mode,
        selector_state_path=selector_state_path,
        broker=broker,
    )
    cycles = 0
    interval = poll_seconds if poll_seconds is not None else config.runtime.poll_seconds
    heartbeat_kind = "{0}-selector".format(mode)
    heartbeat_stale_after = max(30.0, float(interval or 0.0) * 3.0)

    _write_heartbeat(
        kind=heartbeat_kind,
        phase="bootstrapped",
        stale_after_seconds=heartbeat_stale_after,
        market=config.market,
        mode=mode,
        cycle=cycles,
    )

    while True:
        result = selector.run_cycle(markets=explicit_markets or None)
        for event in result["events"]:
            print(event)
        _print_json(result)

        cycles += 1
        _write_heartbeat(
            kind=heartbeat_kind,
            phase="cycle",
            stale_after_seconds=heartbeat_stale_after,
            market=config.market,
            mode=mode,
            cycle=cycles,
            active_market=result.get("active_market") or result.get("selected_market"),
            event_count=len(result.get("events", [])),
        )
        if max_steps is not None and cycles >= max_steps:
            break
        time.sleep(max(interval, 1.0))
    _write_heartbeat(
        kind=heartbeat_kind,
        phase="completed",
        stale_after_seconds=heartbeat_stale_after,
        market=config.market,
        mode=mode,
        cycle=cycles,
    )
    return 0


def _run_selector_stream(
    config: AppConfig,
    broker: UpbitBroker,
    mode: str,
    selector_state_path: str,
    explicit_markets: List[str],
    max_events: Optional[int],
) -> int:
    selector = StreamingMarketSelector(
        config=config,
        mode=mode,
        selector_state_path=selector_state_path,
        broker=broker,
    )
    markets = selector.bootstrap_markets(markets=explicit_markets or None)
    client = UpbitWebSocketClient()
    subscription = build_selector_stream_subscription(config.upbit.candle_unit, markets)
    processed = 0
    _write_heartbeat(
        kind="selector-stream",
        phase="listening",
        stale_after_seconds=120.0,
        market=config.market,
        mode=mode,
        event_count=processed,
    )

    for result in client.iter_messages(subscription, max_messages=max_events):
        payload = selector.process_stream_message(result)
        for event in payload["events"]:
            print(event)
        _print_json(payload)
        processed += 1
        _write_heartbeat(
            kind="selector-stream",
            phase="stream",
            stale_after_seconds=120.0,
            market=config.market,
            mode=mode,
            event_count=processed,
            active_market=payload.get("active_market") or payload.get("selected_market"),
        )
    _write_heartbeat(
        kind="selector-stream",
        phase="completed",
        stale_after_seconds=120.0,
        market=config.market,
        mode=mode,
        event_count=processed,
    )
    return 0


def _run_myorder_listener(
    config: AppConfig,
    broker: UpbitBroker,
    state_path: str,
    market: str,
    max_events: Optional[int],
) -> int:
    runtime = _build_live_runtime(config=config, broker=broker, state_path=state_path, market=market)

    client = UpbitWebSocketClient()
    subscription = build_myorder_subscription([market])
    headers = broker.websocket_private_headers()
    processed = 0
    _write_heartbeat(
        kind="myorder-listener",
        phase="listening",
        stale_after_seconds=180.0,
        market=market,
        mode="live",
        event_count=processed,
    )

    for payload in client.iter_private_messages(subscription, headers=headers, max_messages=max_events):
        for event in runtime.apply_myorder_event(payload):
            print(event)
        _print_json(runtime.summary())
        processed += 1
        _write_heartbeat(
            kind="myorder-listener",
            phase="event",
            stale_after_seconds=180.0,
            market=market,
            mode="live",
            event_count=processed,
            message_type=payload.get("type"),
        )
    _write_heartbeat(
        kind="myorder-listener",
        phase="completed",
        stale_after_seconds=180.0,
        market=market,
        mode="live",
        event_count=processed,
    )
    return 0


def _run_private_listener(
    config: AppConfig,
    broker: UpbitBroker,
    state_path: str,
    market: str,
    max_events: Optional[int],
) -> int:
    runtime = _build_live_runtime(config=config, broker=broker, state_path=state_path, market=market)

    client = UpbitWebSocketClient()
    subscription = build_private_account_subscription([market])
    headers = broker.websocket_private_headers()
    processed = 0
    _write_heartbeat(
        kind="private-listener",
        phase="listening",
        stale_after_seconds=180.0,
        market=market,
        mode="live",
        event_count=processed,
    )

    for payload in client.iter_private_messages(subscription, headers=headers, max_messages=max_events):
        result = _dispatch_private_payload(runtime, payload)
        for event in result["events"]:
            print(event)
        _print_json(runtime.summary())
        processed += 1
        _write_heartbeat(
            kind="private-listener",
            phase="event",
            stale_after_seconds=180.0,
            market=market,
            mode="live",
            event_count=processed,
            message_type=payload.get("type"),
        )
    _write_heartbeat(
        kind="private-listener",
        phase="completed",
        stale_after_seconds=180.0,
        market=market,
        mode="live",
        event_count=processed,
    )
    return 0


def _build_live_runtime(
    config: AppConfig,
    broker: UpbitBroker,
    state_path: str,
    market: str,
) -> TradingRuntime:
    if not os.path.exists(state_path):
        raise ValueError("state file not found: {0}".format(state_path))

    live_config = copy.deepcopy(config)
    live_config.market = market
    live_config.upbit.market = market
    runtime = TradingRuntime(config=live_config, mode="live", state_path=state_path, broker=broker)
    runtime.bootstrap([])
    return runtime


def _dispatch_private_payload(runtime: TradingRuntime, payload: dict) -> dict:
    payload_type = payload.get("type", "")
    if payload_type == "myOrder":
        events = runtime.apply_myorder_event(payload)
    elif payload_type == "myAsset":
        events = runtime.apply_myasset_event(payload)
    else:
        events = []
    return {
        "message_type": payload_type,
        "events": events,
        "summary": runtime.summary(),
    }


def _run_live_supervisor(
    config: AppConfig,
    broker: UpbitBroker,
    state_path: str,
    market: str,
    max_events: Optional[int],
    reconcile_every: int,
    skip_initial_reconcile: bool,
    client: Optional[UpbitWebSocketClient] = None,
    message_source: Optional[Iterable[dict]] = None,
) -> int:
    runtime = _build_live_runtime(config=config, broker=broker, state_path=state_path, market=market)
    client = client or UpbitWebSocketClient()
    subscription = build_private_account_subscription([market])
    headers = broker.websocket_private_headers()

    if not skip_initial_reconcile:
        _print_json(runtime.reconcile_live_snapshot())

    processed = 0
    _write_heartbeat(
        kind="live-supervisor",
        phase="listening",
        stale_after_seconds=180.0,
        market=market,
        mode="live",
        event_count=processed,
        last_processed_timestamp=runtime.state.last_processed_timestamp,
    )
    for payload in client.iter_private_messages(
        subscription,
        headers=headers,
        max_messages=max_events,
        message_source=message_source,
    ):
        result = _dispatch_private_payload(runtime, payload)
        _print_json(result)
        processed += 1
        _write_heartbeat(
            kind="live-supervisor",
            phase="event",
            stale_after_seconds=180.0,
            market=market,
            mode="live",
            event_count=processed,
            message_type=payload.get("type"),
            last_processed_timestamp=runtime.state.last_processed_timestamp,
        )
        if reconcile_every > 0 and (processed % reconcile_every) == 0:
            _write_heartbeat(
                kind="live-supervisor",
                phase="reconcile",
                stale_after_seconds=180.0,
                market=market,
                mode="live",
                event_count=processed,
                last_processed_timestamp=runtime.state.last_processed_timestamp,
            )
            _print_json(runtime.reconcile_live_snapshot())
    _write_heartbeat(
        kind="live-supervisor",
        phase="completed",
        stale_after_seconds=180.0,
        market=market,
        mode="live",
        event_count=processed,
        last_processed_timestamp=runtime.state.last_processed_timestamp,
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)

    try:
        if args.command == "backtest":
            candles = load_csv_candles(args.csv)
            result = Backtester(config).run(candles)
            print(format_backtest_report(result))
            print("events:")
            for event in result.events:
                print(event)
            return 0

        if args.command == "signal":
            candles = load_csv_candles(args.csv)
            signal = ProfessionalCryptoStrategy(config.strategy).evaluate(candles, None)
            _print_json(
                {
                    "market": config.market,
                    "action": signal.action.value,
                    "score": signal.score,
                    "confidence": signal.confidence,
                    "reasons": signal.reasons,
                }
            )
            return 0

        if args.command == "optimize-grid":
            candles = load_csv_candles(args.csv)
            results = run_grid_search(
                config=config,
                candles=candles,
                buy_thresholds=_parse_float_values(args.buy_thresholds, [62.0, 65.0, 68.0]),
                sell_thresholds=_parse_float_values(args.sell_thresholds, [35.0, 40.0, 45.0]),
                min_adx_values=_parse_float_values(args.min_adx_values, [16.0, 18.0, 20.0]),
                min_bollinger_width_values=_parse_float_values(
                    args.min_bollinger_width_values,
                    [0.012, 0.015, 0.018],
                ),
                volume_spike_multipliers=_parse_float_values(
                    args.volume_spike_multipliers,
                    [1.2, 1.3, 1.4],
                ),
            )
            saved_preset = None
            if args.save_best_preset and results:
                saved_preset = save_grid_search_best_preset(
                    config_path=args.config,
                    name=args.save_best_preset,
                    result=results[0],
                    market=config.market,
                    csv_path=args.csv,
                )
            _print_json(
                {
                    "market": config.market,
                    "tested": len(results),
                    "top": [
                        {
                            "rank": index + 1,
                            "buy_threshold": item.buy_threshold,
                            "sell_threshold": item.sell_threshold,
                            "min_adx": item.min_adx,
                            "min_bollinger_width_fraction": item.min_bollinger_width_fraction,
                            "volume_spike_multiplier": item.volume_spike_multiplier,
                            "final_equity": round(item.final_equity, 2),
                            "total_return_pct": round(item.total_return_pct, 4),
                            "max_drawdown_pct": round(item.max_drawdown_pct, 4),
                            "win_rate_pct": round(item.win_rate_pct, 4),
                            "trade_count": item.trade_count,
                        }
                        for index, item in enumerate(results[: max(1, args.top)])
                    ],
                    "saved_preset": saved_preset,
                }
            )
            return 0

        if args.command == "preset-list":
            _print_json(
                {
                    "dir": default_preset_dir(args.config),
                    "items": list_strategy_presets(args.config),
                }
            )
            return 0

        if args.command == "preset-save":
            _print_json(
                save_current_strategy_preset(
                    config_path=args.config,
                    name=args.name,
                    market=args.market or config.market,
                    csv_path=args.csv or "",
                )
            )
            return 0

        if args.command == "preset-apply":
            _print_json(apply_strategy_preset(args.config, args.preset))
            return 0

        if args.command == "profile-list":
            _print_json(
                {
                    "dir": default_profile_dir(args.config),
                    "items": list_operator_profiles(args.config),
                }
            )
            return 0

        if args.command == "profile-show":
            _print_json(run_load_profile_action(args.config, args.profile))
            return 0

        if args.command == "profile-preview":
            _print_json(run_preview_profile_action(args.config, args.profile))
            return 0

        if args.command == "profile-save":
            _print_json(
                run_save_profile_action(
                    config_path=args.config,
                    profile_name=args.name,
                    profile_payload={
                        "job_type": args.job_type,
                        "market": args.market or config.market,
                        "csv_path": args.csv or "",
                        "state_path": args.state or "",
                        "selector_state_path": args.selector_state or "",
                        "quote_currency": args.quote_currency or "",
                        "max_markets": args.max_markets or 0,
                        "poll_seconds": args.poll_seconds or 0.0,
                        "reconcile_every": args.reconcile_every or 0,
                        "reconcile_every_loops": args.reconcile_every_loops or 0,
                        "preset": args.preset or "",
                        "auto_restart": args.auto_restart,
                        "max_restarts": args.max_restarts,
                        "restart_backoff_seconds": args.restart_backoff_seconds,
                    },
                    notes=args.notes,
                )
            )
            return 0

        if args.command == "profile-start":
            _print_json(run_start_profile_action(args.config, args.profile))
            return 0

        if args.command == "session-report":
            _print_json(
                {
                    "reports_dir": default_reports_dir(args.config),
                    **write_runtime_report(
                        config_path=args.config,
                        state_path=args.state,
                        mode=args.mode,
                        output_dir=args.output_dir,
                        label=args.label,
                    ),
                }
            )
            return 0

        if args.command == "report-list":
            _print_json(
                {
                    "reports_dir": default_reports_dir(args.config),
                    "items": list_session_reports(args.config, output_dir=args.output_dir),
                }
            )
            return 0

        if args.command == "report-show":
            _print_json(load_session_report(args.config, args.report, output_dir=args.output_dir))
            return 0

        if args.command == "job-history":
            _print_json({"items": list_job_history(limit=args.limit)})
            return 0

        if args.command == "job-preview":
            _print_json(
                preview_managed_job(
                    config_path=args.config,
                    job_type=args.job_type,
                    state_path=args.state,
                    selector_state_path=args.selector_state,
                    csv_path=args.csv,
                    poll_seconds=args.poll_seconds,
                    reconcile_every_loops=args.reconcile_every_loops,
                    reconcile_every=args.reconcile_every,
                    market=args.market or config.market,
                    quote_currency=args.quote_currency,
                    max_markets=args.max_markets,
                    auto_restart=args.auto_restart,
                    max_restarts=args.max_restarts,
                    restart_backoff_seconds=args.restart_backoff_seconds,
                )
            )
            return 0

        if args.command == "web-ui":
            run_web_ui_server(
                config_path=args.config,
                state_path=args.state,
                selector_state_path=args.selector_state,
                csv_path=args.csv,
                mode=args.mode,
                host=args.host,
                port=args.port,
            )
            return 0

        if args.command == "doctor":
            _print_json(
                _build_doctor_report(
                    config_path=args.config,
                    config=config,
                    state_path=args.state,
                    selector_state_path=args.selector_state,
                )
            )
            return 0

        broker = _build_broker(config)

        if args.command == "scan-markets":
            scan_config = _selector_config_from_args(config, args)
            scanner = MarketScanner(scan_config, broker)
            markets = scanner.discover_markets(scan_config.selector)
            results = scanner.scan_markets(markets)
            _print_json(
                [
                    {
                        "market": item.market,
                        "action": item.action,
                        "score": item.score,
                        "confidence": item.confidence,
                        "reasons": item.reasons,
                        "timestamp": item.timestamp,
                        "close": item.close,
                        "candle_count": item.candle_count,
                        "market_warning": item.market_warning,
                        "liquidity_24h": item.liquidity_24h,
                        "liquidity_ok": item.liquidity_ok,
                        "recent_bid_ratio": item.recent_bid_ratio,
                        "recent_trade_notional": item.recent_trade_notional,
                        "trade_flow_ok": item.trade_flow_ok,
                        "spread_bps": item.spread_bps,
                        "top_bid_ask_ratio": item.top_bid_ask_ratio,
                        "total_bid_ask_ratio": item.total_bid_ask_ratio,
                        "orderbook_ok": item.orderbook_ok,
                    }
                    for item in results
                ]
            )
            return 0

        if args.command == "markets":
            _print_json(broker.list_markets(is_details=args.details))
            return 0

        if args.command == "ticker":
            _print_json(broker.get_ticker([_market_arg(args, config)]))
            return 0

        if args.command == "sync-candles":
            market = _market_arg(args, config)
            count = args.count or config.upbit.candle_count
            payload = broker.get_minute_candles(
                market=market,
                unit=config.upbit.candle_unit,
                count=count,
                to=args.to,
            )
            incoming = upbit_candles_to_internal(payload)
            existing = load_csv_candles(args.csv) if os.path.exists(args.csv) else []
            keep_rows = max(config.runtime.max_history, len(existing) + len(incoming), count)
            merged = merge_candles(existing, incoming, max_history=keep_rows)
            write_csv_candles(args.csv, merged)
            _print_json(
                {
                    "market": market,
                    "rows_written": len(merged),
                    "first_timestamp": merged[0].timestamp if merged else "",
                    "last_timestamp": merged[-1].timestamp if merged else "",
                    "csv": args.csv,
                }
            )
            return 0

        if args.command == "balances":
            _print_json(broker.get_accounts())
            return 0

        if args.command == "chance":
            _print_json(broker.get_order_chance(_market_arg(args, config)))
            return 0

        if args.command == "notify-test":
            notifier = DiscordWebhookNotifier(config.notifications)
            sent = notifier.send_test(args.message)
            _print_json(
                {
                    "sent": sent,
                    "message": args.message,
                    "webhook_configured": bool(config.notifications.discord_webhook_url),
                }
            )
            return 0

        if args.command == "live-reconcile":
            if not os.path.exists(args.state):
                print("state file not found: {0}".format(args.state), file=sys.stderr)
                return 2
            live_config = copy.deepcopy(config)
            live_config.market = _market_arg(args, config)
            live_config.upbit.market = live_config.market
            runtime = TradingRuntime(config=live_config, mode="live", state_path=args.state, broker=broker)
            runtime.bootstrap([])
            _print_json(runtime.reconcile_live_snapshot())
            return 0

        if args.command == "order-show":
            _print_json(broker.get_order(uuid=args.uuid, identifier=args.identifier))
            return 0

        if args.command == "open-orders":
            _print_json(
                broker.list_open_orders(
                    market=_market_arg(args, config) if args.market else None,
                    state=args.state,
                    states=_parse_markets(args.states),
                    page=args.page,
                    limit=args.limit,
                    order_by=args.order_by,
                )
            )
            return 0

        if args.command == "order-preview":
            _print_json(
                broker.preview_order_request(
                    market=_market_arg(args, config),
                    side=args.side,
                    ord_type=args.ord_type,
                    volume=args.volume,
                    price=args.price,
                )
            )
            return 0

        if args.command == "cancel-order":
            _print_json(broker.cancel_order(uuid=args.uuid, identifier=args.identifier))
            return 0

        if args.command == "cancel-open-orders":
            _print_json(
                broker.cancel_open_orders(
                    cancel_side=args.cancel_side,
                    pairs=args.pairs,
                    excluded_pairs=args.excluded_pairs,
                    count=args.count,
                    order_by=args.order_by,
                )
            )
            return 0

        if args.command == "cancel-and-new":
            _print_json(
                broker.cancel_and_new(
                    new_ord_type=args.new_ord_type,
                    prev_order_uuid=args.prev_order_uuid,
                    prev_order_identifier=args.prev_order_identifier,
                    new_volume=args.new_volume,
                    new_price=args.new_price,
                    new_time_in_force=args.new_time_in_force,
                    new_smp_type=args.new_smp_type,
                    new_identifier=args.new_identifier,
                )
            )
            return 0

        if args.command == "listen-myorder":
            return _run_myorder_listener(
                config=config,
                broker=broker,
                state_path=args.state,
                market=_market_arg(args, config),
                max_events=args.max_events,
            )

        if args.command == "listen-private":
            return _run_private_listener(
                config=config,
                broker=broker,
                state_path=args.state,
                market=_market_arg(args, config),
                max_events=args.max_events,
            )

        if args.command == "run-live-supervisor":
            return _run_live_supervisor(
                config=config,
                broker=broker,
                state_path=args.state,
                market=_market_arg(args, config),
                max_events=args.max_events,
                reconcile_every=args.reconcile_every,
                skip_initial_reconcile=args.skip_initial_reconcile,
            )

        if args.command == "run-loop":
            runtime = TradingRuntime(config=config, mode=args.mode, state_path=args.state)
            if args.mode == "live" and not config.upbit.live_enabled:
                print("live mode requires upbit.live_enabled=true", file=sys.stderr)
                return 2

            if args.replay_csv:
                return _run_replay_loop(
                    runtime=runtime,
                    replay_csv=args.replay_csv,
                    warmup_csv=args.warmup_csv,
                    max_steps=args.max_steps,
                )

            return _run_broker_loop(
                runtime=runtime,
                broker=broker,
                warmup_csv=args.warmup_csv,
                poll_seconds=args.poll_seconds,
                max_steps=args.max_steps,
            )

        if args.command == "run-live-daemon":
            if not config.upbit.live_enabled:
                print("run-live-daemon requires upbit.live_enabled=true", file=sys.stderr)
                return 2
            return _run_live_daemon(
                config=config,
                broker=broker,
                state_path=args.state,
                warmup_csv=args.warmup_csv,
                poll_seconds=args.poll_seconds,
                max_loops=args.max_loops,
                reconcile_every_loops=args.reconcile_every_loops,
            )

        if args.command == "run-selector":
            selector_config = _selector_config_from_args(config, args)
            if args.mode == "live" and not selector_config.upbit.live_enabled:
                print("live mode requires upbit.live_enabled=true", file=sys.stderr)
                return 2
            return _run_selector_loop(
                config=selector_config,
                broker=broker,
                mode=args.mode,
                selector_state_path=args.selector_state,
                explicit_markets=_parse_markets(args.markets),
                poll_seconds=args.poll_seconds,
                max_steps=args.max_steps,
            )

        if args.command == "run-selector-stream":
            selector_config = _selector_config_from_args(config, args)
            if args.mode == "live" and not selector_config.upbit.live_enabled:
                print("live mode requires upbit.live_enabled=true", file=sys.stderr)
                return 2
            return _run_selector_stream(
                config=selector_config,
                broker=broker,
                mode=args.mode,
                selector_state_path=args.selector_state,
                explicit_markets=_parse_markets(args.markets),
                max_events=args.max_events,
            )

        if args.command == "state-show":
            if not os.path.exists(args.state):
                print("state file not found: {0}".format(args.state), file=sys.stderr)
                return 2
            runtime = TradingRuntime(config=config, mode="paper", state_path=args.state)
            runtime.bootstrap([])
            _print_json(runtime.summary())
            return 0

        if args.command == "selector-state-show":
            if not os.path.exists(args.state):
                print("state file not found: {0}".format(args.state), file=sys.stderr)
                return 2
            with open(args.state, "r", encoding="utf-8") as handle:
                _print_json(json.load(handle))
            return 0
    except (NotificationError, UpbitError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
