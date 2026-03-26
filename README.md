# Upbit Auto Trader Starter

This project is a safe starter for an Upbit-based crypto auto-trading bot.

It includes:

- A chart-driven strategy using EMA, MACD, RSI, ADX, Bollinger band width, breakout, and volume expansion.
- ATR-based position sizing, stop loss, take profit, and trailing stop logic.
- CSV backtesting and replay-based paper trading.
- A stateful runtime with cooldown, daily loss cap, session filter, and trade journal.
- A multi-market scanner that ranks KRW pairs and auto-selects the strongest candidate.
- Live bootstrap safety that syncs exchange balances and blocks starts with unexpected existing coin inventory.
- An Upbit REST adapter for market data, balances, order chance, and authenticated order previews.

## Why live trading is disabled

Live order placement stays off by default through `upbit.live_enabled=false`.

This starter follows the official Upbit API documentation for:

- JWT authentication with `access_key`, `nonce`, `query_hash`, and `query_hash_alg`
- public quotation endpoints such as markets, ticker, and minute candles
- private endpoints such as accounts, order chance, and order creation

Official sources used while building this starter on 2026-03-22:

- https://docs.upbit.com/kr/v1.5.9/reference/authentication
- https://docs.upbit.com/kr/v1.5.9/docs/user-request-guide
- https://docs.upbit.com/kr/v1.5.9/docs/create-authorization-request
- https://docs.upbit.com/kr/v1.5.9/reference/list-trading-pairs
- https://docs.upbit.com/kr/v1.5.9/reference/list-tickers
- https://docs.upbit.com/kr/v1.5.9/reference/list-candles-minutes
- https://docs.upbit.com/kr/v1.5.9/reference/list-tickers
- https://docs.upbit.com/kr/v1.5.9/reference/websocket-trade
- https://docs.upbit.com/kr/v1.5.9/reference/websocket-ticker
- https://docs.upbit.com/kr/v1.5.9/reference/websocket-orderbook
- https://docs.upbit.com/kr/v1.5.9/reference/websocket-candle
- https://docs.upbit.com/kr/v1.5.9/reference/websocket-myorder
- https://docs.upbit.com/kr/v1.5.9/reference/authentication
- https://docs.upbit.com/kr/v1.5.9/reference/get-balance
- https://docs.upbit.com/kr/v1.5.9/reference/available-order-information
- https://docs.upbit.com/kr/v1.5.9/reference/new-order
- https://docs.upbit.com/kr/reference/get-order
- https://docs.upbit.com/kr/reference/list-open-orders
- https://docs.upbit.com/kr/reference/cancel-order
- https://docs.upbit.com/kr/reference/order-cancel-all
- https://docs.upbit.com/kr/reference/cancel-and-new-order

## Project layout

- `src/upbit_auto_trader/strategy.py`: signal logic
- `src/upbit_auto_trader/risk.py`: sizing and stop logic
- `src/upbit_auto_trader/backtest.py`: simulation engine
- `src/upbit_auto_trader/runtime.py`: stateful paper or live loop
- `src/upbit_auto_trader/ui.py`: standard-library web dashboard server
- `src/upbit_auto_trader/jobs.py`: managed background jobs with watchdog restart
- `src/upbit_auto_trader/presets.py`: strategy preset save or apply helpers
- `src/upbit_auto_trader/profiles.py`: one-click launch profile save or load helpers
- `src/upbit_auto_trader/scanner.py`: multi-market ranking
- `src/upbit_auto_trader/selector.py`: rotating best-market selector
- `src/upbit_auto_trader/brokers/upbit.py`: Upbit REST adapter
- `config.example.json`: runtime and API settings
- `data/demo_krw_btc_15m.csv`: demo candle data

## Run

Create a virtual environment with Python 3.12:

```powershell
C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe -m venv .venv
```

Install the package in editable mode:

```powershell
.venv\Scripts\python.exe -m pip install -e .
```

Optional: create `.env` from the example file so API keys and webhook settings load automatically from the project root:

```powershell
Copy-Item .env.example .env
```

Run the demo backtest:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main backtest --config config.example.json --csv data/demo_krw_btc_15m.csv
```

Inspect the latest flat-position signal:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main signal --config config.example.json --csv data/demo_krw_btc_15m.csv
```

Run a small grid search to compare strategy settings on a CSV backtest:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main optimize-grid --config config.example.json --csv data/demo_krw_btc_15m.csv --top 5
```

Run the same grid search and save the best result as a reusable strategy preset:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main optimize-grid --config config.example.json --csv data/demo_krw_btc_15m.csv --top 5 --save-best-preset krw-btc-best
```

List saved strategy presets:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main preset-list --config config.example.json
```

Save the current strategy section as a preset:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main preset-save --config config.example.json --name krw-btc-manual-a --csv data/demo_krw_btc_15m.csv
```

Apply a saved preset back into the config file:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main preset-apply --config config.example.json --preset krw-btc-best
```

List saved launch profiles:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main profile-list --config config.example.json
```

Save a reusable launch profile from the CLI:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main profile-save --config config.example.json --name paper-btc-main --job-type paper-loop --market KRW-BTC --csv data/demo_krw_btc_15m.csv --state data/paper-state.json --auto-restart --max-restarts 2 --restart-backoff-seconds 2 --report-keep-latest 20
```

Show one saved launch profile:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main profile-show --config config.example.json --profile paper-btc-main
```

Delete one saved launch profile:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main profile-delete --config config.example.json --profile paper-btc-main
```

Start one saved launch profile without opening the UI:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main profile-start --config config.example.json --profile paper-btc-main
```

Export the current runtime state into JSON and HTML session reports:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main session-report --config config.example.json --state data/paper-state.json --label paper-btc-main --keep-latest 20
```

Use `--keep-latest` when you want `session-report` to prune older JSON/HTML pairs after each export. For example, `--keep-latest 1` turns the report directory into a rolling single-report snapshot.

List saved session reports:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main report-list --config config.example.json
```

Show one saved session report:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main report-show --config config.example.json --report session-report-20260324T0000000000-paper-btc-main.json
```

Delete one saved session report:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main report-delete --config config.example.json --report session-report-20260324T0000000000-paper-btc-main.json
```

Managed background jobs automatically export a session report when they stop or finish if a runtime `state_path` is available. Those auto-generated exit reports keep the newest `20` files by default, so the report directory does not grow forever. The latest generated report is also surfaced in the web UI job panel and alert center.

List recent managed job runs:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main job-history --config config.example.json --limit 12
```

Emergency-stop all heartbeat-discovered managed jobs from PowerShell:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main job-stop-all --config config.example.json --timeout 5
```

Clean stopped-job heartbeat artifacts from PowerShell:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main job-cleanup --config config.example.json
```

Start the browser-based control room UI:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main web-ui --config config.example.json --state data\paper-state.json --selector-state data\selector-state.json --csv data/demo_krw_btc_15m.csv --mode paper --port 8765
```

Or use the one-click PowerShell launcher:

```powershell
.\start_control_room.ps1
```

Or use the browser-opening launcher:

```powershell
.\launch_control_room.cmd
```

Or use the hidden-window launcher:

```powershell
.\launch_control_room_hidden.cmd
```

Launching the hidden-window command again now reuses the running server on the same host or port instead of opening duplicate control-room instances.

Or double-click the silent launcher:

```text
launch_control_room_silent.vbs
```

To stop a hidden control-room instance cleanly:

```powershell
.\stop_control_room.cmd
```

If the PID file is stale, the stop script now clears it without killing an unrelated reused PID.

Run the remaining completion workflow from Git Bash:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' .\complete_remaining.sh all-safe
```

Or run the same workflow from a Windows-friendly wrapper:

```powershell
.\complete_remaining.cmd all-safe
```

Or call the PowerShell script with execution-policy bypass:

```powershell
powershell -ExecutionPolicy Bypass -File .\complete_remaining.ps1 all-safe
```

The script also supports smaller stages such as `roadmap`, `verify`, `paper-preflight`, `paper-start`, `paper-report`, `live-preflight`, `live-start`, `status`, and `all`. `all-safe` only runs non-live stages. `live-start` is blocked unless `UPBIT_AUTO_TRADER_ALLOW_LIVE=1` is set on purpose.

The browser control room now also exposes a `Completion Workflow` panel so you can preview or run safe finish stages such as `verify`, `paper-preflight`, `live-preflight`, `status`, and `all-safe` without leaving the UI.

The control room also includes an `Operator Checklist` panel that turns current state, live readiness, workflow availability, job health, and notification setup into a small next-step list so you can see what is blocking paper or live operation at a glance.

Run a local preflight check before paper or live operation:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main doctor --config config.example.json --state data\paper-state.json --selector-state data\selector-state.json
```

`doctor` now also inspects managed-job heartbeat files under `data/webui-jobs` and reports stale workers alongside config, state, and exchange readiness.

The UI now includes runtime cards, an alert center for blocked entries, fills, job failures, and live-readiness warnings, a price chart with buy or sell markers, recent trade and event panels, card-based market scan results with focus-market selection, selector state and active-market tracking with its own chart and recent events, focus-market-aware dashboard refresh, signal and backtest actions, candle sync, live reconcile, a session report center with export, reload, and delete actions, a one-click doctor preflight check, key config editing, strategy preset save or apply controls, launch-profile save or load controls, separate selector-state input, start or stop controls for background paper loop, paper selector, live daemon, and live supervisor jobs, plus an `Emergency Stop All` control for all managed jobs and a `Clean Stopped Jobs` action that removes finished heartbeat artifacts. Background job logs are rotated automatically under `data/webui-jobs`, and managed jobs can now auto-restart with a watchdog and bounded retry count.

Managed jobs now also write heartbeat files under `data/webui-jobs/*.heartbeat.json`, and the control room surfaces stale or missing heartbeats as warnings so a hung process is easier to spot.

When watchdog restart is enabled, a stale heartbeat is also treated as a restartable failure, so hung jobs can be recycled automatically instead of only showing up as running forever.

The control room now also shows a `Job Health` summary with healthy, stale, missing, failed, and auto-restart counts so you can see worker health without opening raw job JSON first.

Live background jobs are now preflight-gated. If `doctor` finds blocking issues such as `live_enabled=false`, missing live state, unreadable state, or unresolved API keys, the UI and profile launcher will refuse to start the live job and return the full preflight report instead.

The control-room UI also includes a `Preview Launch` action so you can inspect the exact command, report paths, and any live preflight blockers before starting a background job.

You can preview an ad hoc managed job from PowerShell too:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main job-preview --config config.example.json --job-type paper-loop --state data\paper-state.json --csv data\demo_krw_btc_15m.csv
```

If you already saved a launch profile, you can start it from PowerShell too:

```powershell
.\start_profile.ps1 -Profile paper-btc-main
```

You can preview a saved profile before launching it:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main profile-preview --config config.example.json --profile paper-btc-main
```

Preview a market buy order request:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main order-preview --config config.example.json --side bid --ord-type price --price 100000
```

Send a test Discord webhook notification:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main notify-test --config config.example.json --message "runtime notification test"
```

Show a specific order by UUID or identifier:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main order-show --config config.example.json --uuid your-order-uuid
```

List current open orders:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main open-orders --config config.example.json --market KRW-BTC --states wait,watch --limit 20
```

Cancel one order:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main cancel-order --config config.example.json --uuid your-order-uuid
```

Cancel all open orders for selected pairs:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main cancel-open-orders --config config.example.json --pairs KRW-BTC,KRW-ETH --count 20
```

Cancel and replace one order:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main cancel-and-new --config config.example.json --prev-order-uuid your-order-uuid --new-ord-type limit --new-price 130000000 --new-volume 0.01
```

Listen to private `MyOrder` events and reconcile fills into an existing live state file:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main listen-myorder --config config.example.json --state data\live-state.json --market KRW-BTC --max-events 20
```

Listen to `MyOrder` and `MyAsset` together on the private websocket and double-check live balance sync:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main listen-private --config config.example.json --state data\live-state.json --market KRW-BTC --max-events 20
```

Run a one-shot live reconciliation against the saved state, balances, chance info, and open orders:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main live-reconcile --config config.example.json --state data\live-state.json --market KRW-BTC
```

Run a live supervisor that performs an initial reconcile, listens to `myOrder` and `myAsset`, and periodically re-runs reconciliation:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main run-live-supervisor --config config.example.json --state data\live-state.json --market KRW-BTC --reconcile-every 10
```

Run a single-process live daemon that polls minute candles, executes the live runtime, and performs scheduled reconcile snapshots:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main run-live-daemon --config config.example.json --state data\live-state.json --max-loops 3 --reconcile-every-loops 1
```

Download recent candle data from Upbit into a CSV:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main sync-candles --config config.example.json --csv data\krw-btc-15m.csv --count 200
```

Scan multiple KRW markets and rank the best signals:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main scan-markets --config config.example.json --max-markets 10
```

Run the stateful loop in replay mode:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main run-loop --config config.example.json --mode paper --state data\paper-state.json --replay-csv data/demo_krw_btc_15m.csv
```

Run the stateful loop against live Upbit candles in paper mode:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main run-loop --config config.example.json --mode paper --state data\paper-state.json --max-steps 3
```

Run the rotating selector in paper mode so it scans many markets and only trades the strongest one:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main run-selector --config config.example.json --mode paper --selector-state data\selector-state.json --max-markets 10 --max-steps 3
```

Run the selector from Upbit's real-time candle websocket:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main run-selector-stream --config config.example.json --mode paper --selector-state data\selector-state.json --max-markets 10 --max-events 20
```

The browser control room can now save launch profiles that capture the selected job type, market, CSV path, state paths, quote currency, selected strategy preset, watchdog restart settings, exit-report retention count, and a short operator note. Saved profiles also track `start_count` and `last_started_at`, so the control room can show which launch setup was used most recently.

Show the saved runtime state:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main state-show --config config.example.json --state data\paper-state.json
```

Show the selector state:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main selector-state-show --config config.example.json --state data\selector-state.json
```

Run tests:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```

## Runtime controls

The `runtime` section in `config.example.json` controls operational rules:

- `cooldown_bars_after_exit`: bars to wait before re-entry after a sell
- `max_trades_per_day`: maximum new positions per day
- `daily_loss_limit_fraction`: block new entries after realized daily loss reaches this fraction of initial cash
- `session_start`, `session_end`: optional entry window using candle timestamps like `2026-03-22T09:15:00`
- `allowed_weekdays`: allowed entry weekdays using Python numbering where `0=Monday`
- `journal_path`: JSONL audit log path for buy, sell, and blocked-entry events
- `pending_order_max_bars`: in live mode, cancel a still-open order after this many processed bars

Runtime state files are now mirrored to `<state>.bak` after each successful save. If the main JSON state file is missing or corrupted on restart, the runtime automatically falls back to the backup snapshot and records a `STATE RECOVERED source=backup` event.

The `selector` section controls multi-market behavior:

- `quote_currency`: market prefix to scan such as `KRW`
- `include_markets`: explicit watchlist override
- `exclude_markets`: blacklist
- `max_markets`: maximum symbols to scan each cycle
- `min_score`: minimum strategy score required before selection
- `min_acc_trade_price_24h`: minimum 24h traded KRW amount required for selection
- `use_trade_flow_filter`: only for `run-selector-stream`, require recent trade flow confirmation
- `min_recent_bid_ratio`: minimum buy-side notional ratio across recent streamed trades
- `min_recent_trade_notional`: minimum summed notional across the recent trade window
- `recent_trade_window`: number of recent streamed trades to evaluate
- `use_orderbook_filter`: only for `run-selector-stream`, require healthy best bid or ask structure
- `max_spread_bps`: maximum allowed best ask or bid spread in basis points
- `min_top_bid_ask_ratio`: minimum ratio of top bid size to top ask size
- `min_total_bid_ask_ratio`: minimum ratio of total bid size to total ask size
- `require_buy_action`: only select symbols with a `BUY` signal
- `skip_warning_markets`: skip Upbit warning-marked symbols
- `states_dir`: per-market runtime state directory used by `run-selector`

The `upbit` section also includes request-layer safety controls:

- `request_timeout_seconds`: per-request timeout for REST calls
- `max_retries`: automatic retry count for transient `GET` failures such as `429`, `500`, `502`, `503`, `504`, or network timeouts
- `retry_backoff_seconds`: exponential backoff base between retry attempts

The broker only auto-retries `GET` requests. It does not auto-retry `POST` or `DELETE` order-changing calls because that would risk duplicate submissions or repeated cancels after an ambiguous network failure.

Managed background jobs in the web UI now have a separate watchdog layer:

- `auto_restart`: automatically restart a failed background job
- `max_restarts`: maximum restart attempts before leaving the job stopped
- `restart_backoff_seconds`: base delay before each retry; later retries wait longer

Config loading also reads `.env` from the project root before resolving `${ENV_NAME}` placeholders in `config.example.json`. Existing environment variables still win over `.env` values.

The `notifications` section controls optional external alerts:

- `discord_webhook_url`: Discord incoming webhook URL
- `enabled_levels`: which severity levels can be sent
- `enabled_event_types`: which runtime event types can trigger a webhook
- `cooldown_seconds`: minimum gap before repeating the same event class for the same market
- `timeout_seconds`: webhook delivery timeout

If the webhook is configured, runtime journal events such as `blocked`, `buy`, `sell`, `buy_fill`, `sell_fill`, and pending-order cancellation warnings can be forwarded to Discord without changing the rest of the trading loop.

In `live` mode, the runtime now checks `주문 가능 정보 조회` before placing orders:

The runtime uses Upbit available order information and order polling before new live submissions.

- buy size is based on actual available quote balance from Upbit
- sell size is validated against actual base-asset balance from Upbit
- orders below the exchange `min_total` threshold are blocked before submission
- a fresh live bootstrap is blocked if the exchange already holds that coin outside the bot state
- pending orders are polled through `get-order`, partial fills are reconciled into runtime state, and stale wait orders are auto-cancelled after `pending_order_max_bars`

The selector trades only one active market at a time. It scans while flat, opens the highest-ranked candidate above the threshold, and then keeps managing only that market until the position is closed.

`run-selector-stream` uses Upbit's `ticker`, `trade`, `orderbook`, and `candle` websocket streams together. `ticker` provides 24h traded amount, `trade` provides recent bid or ask flow, `orderbook` filters out wide spreads and ask-heavy books, and `candle` is used as the bar-close trigger for runtime advancement. The websocket candle feed is marked beta in the official docs, and the same `candle_date_time_kst` can arrive multiple times. This starter treats websocket updates as trigger events and only advances the runtime on newer candle timestamps.

`listen-myorder` uses Upbit's private websocket endpoint and updates the runtime state only when the exchange confirms order events. This is the safer path for live fills because order submission and actual execution are not always the same moment.

`listen-private` combines `myOrder` and `myAsset`. `myOrder` updates actual fills, and `myAsset` stores a live asset snapshot plus mismatch warnings when account balances and bot state drift apart.

`order-show`, `open-orders`, `cancel-order`, `cancel-open-orders`, and `cancel-and-new` are direct helpers around Upbit's authenticated order-management endpoints. They are useful for live troubleshooting and manual cleanup while the runtime keeps its own JSON state file.

`live-reconcile` is a one-shot audit command. It loads the saved live state, syncs balances through `accounts`, reconciles the current pending order through `get-order`, and reports current `open-orders` plus `chance` balances in one JSON payload.

`run-live-supervisor` is the longer-running operational form of the same idea. It starts with `live-reconcile`, then keeps consuming the private websocket, and re-runs reconciliation every N events so exchange state and local JSON state stay aligned.

`run-live-daemon` is the polling-based operational command. It is useful when you want one process to handle candle polling, strategy execution, pending-order reconciliation, and periodic balance or open-order snapshots without depending on a second terminal session.

## Live-trading checklist

1. Generate Upbit API keys with trading permission.
2. Set `UPBIT_ACCESS_KEY` and `UPBIT_SECRET_KEY` in your environment.
3. Keep `upbit.live_enabled=false` until candle sync, balances, and order previews are verified.
4. Validate `order-preview` output against the official Upbit docs.
5. Run `run-loop` in `paper` mode first.
6. Only then switch to `mode=live` and set `upbit.live_enabled=true`.
