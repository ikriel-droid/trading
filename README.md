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

Start the browser-based control room UI:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main web-ui --config config.example.json --state data\paper-state.json --selector-state data\selector-state.json --csv data/demo_krw_btc_15m.csv --mode paper --port 8765
```

Run a local preflight check before paper or live operation:

```powershell
.venv\Scripts\python.exe -m upbit_auto_trader.main doctor --config config.example.json --state data\paper-state.json --selector-state data\selector-state.json
```

The UI now includes runtime cards, an alert center for blocked entries, fills, job failures, and live-readiness warnings, a price chart with buy or sell markers, recent trade and event panels, card-based market scan results with focus-market selection, selector state and active-market tracking with its own chart and recent events, focus-market-aware dashboard refresh, signal and backtest actions, candle sync, live reconcile, key config editing, separate selector-state input, and start or stop controls for background paper loop, paper selector, live daemon, and live supervisor jobs. Background job logs are rotated automatically under `data/webui-jobs` so repeated runs do not keep one file growing forever.

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
