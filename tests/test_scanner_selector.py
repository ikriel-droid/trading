import json
import pathlib
import shutil
import sys
import unittest
from datetime import datetime, timedelta


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.scanner import MarketScanner  # noqa: E402
from upbit_auto_trader.selector import RotatingMarketSelector, StreamingMarketSelector  # noqa: E402
from upbit_auto_trader.websocket_client import build_selector_stream_subscription  # noqa: E402


def build_upbit_candle_payload(closes, volumes):
    base_time = datetime(2026, 3, 26, 0, 0)
    payload = []
    previous_close = closes[0]
    for index, close in enumerate(closes):
        timestamp = (base_time + timedelta(minutes=15 * index)).isoformat(timespec="seconds")
        opening_price = previous_close
        high_price = max(opening_price, close) + 0.3
        low_price = min(opening_price, close) - 0.3
        payload.append(
            {
                "candle_date_time_kst": timestamp,
                "opening_price": opening_price,
                "high_price": high_price,
                "low_price": low_price,
                "trade_price": close,
                "candle_acc_trade_volume": volumes[index],
            }
        )
        previous_close = close
    return list(reversed(payload))


def build_realtime_candle_message(market, timestamp, open_price, high_price, low_price, trade_price, volume):
    return {
        "type": "candle.15m",
        "code": market,
        "candle_date_time_kst": timestamp,
        "opening_price": open_price,
        "high_price": high_price,
        "low_price": low_price,
        "trade_price": trade_price,
        "candle_acc_trade_volume": volume,
        "stream_type": "REALTIME",
    }


def build_realtime_orderbook_message(
    market,
    ask_price,
    bid_price,
    ask_size,
    bid_size,
    total_ask_size,
    total_bid_size,
):
    return {
        "type": "orderbook",
        "code": market,
        "total_ask_size": total_ask_size,
        "total_bid_size": total_bid_size,
        "orderbook_units": [
            {
                "ask_price": ask_price,
                "bid_price": bid_price,
                "ask_size": ask_size,
                "bid_size": bid_size,
            }
        ],
        "stream_type": "REALTIME",
    }


class FakeBroker:
    def __init__(self):
        self.markets = [
            {"market": "KRW-BTC", "market_warning": "NONE"},
            {"market": "KRW-XRP", "market_warning": "NONE"},
            {"market": "KRW-CAUTION", "market_warning": "CAUTION"},
            {"market": "BTC-ETH", "market_warning": "NONE"},
        ]
        self.candles = {
            "KRW-BTC": build_upbit_candle_payload(
                [100.0 + (index * 0.55) for index in range(35)] + [121.8],
                [120.0 + (index % 6) for index in range(35)] + [320.0],
            ),
            "KRW-XRP": build_upbit_candle_payload(
                [100.0 - (index * 0.12) for index in range(36)],
                [100.0 for _ in range(36)],
            ),
            "KRW-CAUTION": build_upbit_candle_payload(
                [100.0 + (index * 0.2) for index in range(36)],
                [100.0 for _ in range(36)],
            ),
        }
        self.tickers = {
            "KRW-BTC": {"market": "KRW-BTC", "acc_trade_price_24h": 15000000000.0},
            "KRW-XRP": {"market": "KRW-XRP", "acc_trade_price_24h": 300000000.0},
            "KRW-CAUTION": {"market": "KRW-CAUTION", "acc_trade_price_24h": 9000000000.0},
        }

    def list_markets(self, is_details=True):
        return list(self.markets)

    def get_minute_candles(self, market, unit, count=200, to=None):
        return self.candles[market][:count]

    def get_ticker(self, markets):
        return [self.tickers[market] for market in markets]


class ScannerSelectorTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(str(PROJECT_ROOT / "config.example.json"))
        self.config.runtime.journal_path = ""
        self.config.runtime.max_trades_per_day = 50
        self.config.selector.include_markets = []
        self.config.selector.exclude_markets = []
        self.config.selector.max_markets = 5
        self.config.selector.states_dir = str(PROJECT_ROOT / "data" / "test-selector-states")
        self.config.selector.min_score = 65.0
        self.config.selector.min_acc_trade_price_24h = 1000000000.0
        self.config.selector.use_trade_flow_filter = True
        self.config.selector.min_recent_bid_ratio = 0.55
        self.config.selector.min_recent_trade_notional = 50000.0
        self.config.selector.recent_trade_window = 5
        self.config.selector.use_orderbook_filter = True
        self.config.selector.max_spread_bps = 15.0
        self.config.selector.min_top_bid_ask_ratio = 0.8
        self.config.selector.min_total_bid_ask_ratio = 0.9
        self.config.strategy.sell_threshold = 0.0
        self.config.risk.take_profit_atr_multiple = 100.0
        self.broker = FakeBroker()
        self.selector_state = PROJECT_ROOT / "data" / "test-selector-state.json"
        if self.selector_state.exists():
            self.selector_state.unlink()
        states_dir = pathlib.Path(self.config.selector.states_dir)
        if states_dir.exists():
            shutil.rmtree(states_dir)

    def tearDown(self):
        if self.selector_state.exists():
            self.selector_state.unlink()
        states_dir = pathlib.Path(self.config.selector.states_dir)
        if states_dir.exists():
            shutil.rmtree(states_dir)

    def test_scanner_discovers_krw_markets_and_ranks_buy_first(self):
        scanner = MarketScanner(self.config, self.broker)

        markets = scanner.discover_markets()
        results = scanner.scan_markets(markets)

        self.assertEqual(markets, ["KRW-BTC", "KRW-XRP"])
        self.assertEqual(results[0].market, "KRW-BTC")
        self.assertEqual(results[0].action, "BUY")
        self.assertGreater(results[0].score, results[1].score)
        self.assertTrue(results[0].liquidity_ok)
        self.assertFalse(results[1].liquidity_ok)

    def test_selector_opens_active_market_on_best_candidate(self):
        self.config.selector.include_markets = ["KRW-BTC", "KRW-XRP"]
        self.config.selector.use_trade_flow_filter = False
        selector = RotatingMarketSelector(
            config=self.config,
            mode="paper",
            selector_state_path=str(self.selector_state),
            broker=self.broker,
        )

        result = selector.run_cycle()

        self.assertEqual(result["active_market"], "KRW-BTC")
        self.assertEqual(result["last_selected_market"], "KRW-BTC")
        self.assertTrue(any("PAPER BUY KRW-BTC" in event for event in result["events"]))
        self.assertIsNotNone(result["active_summary"])
        self.assertIsNotNone(result["active_summary"]["position"])
        self.assertTrue((pathlib.Path(self.config.selector.states_dir) / "KRW_BTC.json").exists())

    def test_selector_stays_flat_when_threshold_is_above_candidates(self):
        self.config.selector.include_markets = ["KRW-BTC", "KRW-XRP"]
        self.config.selector.use_trade_flow_filter = False
        self.config.selector.min_score = 101.0
        selector = RotatingMarketSelector(
            config=self.config,
            mode="paper",
            selector_state_path=str(self.selector_state),
            broker=self.broker,
        )

        result = selector.run_cycle()

        self.assertEqual(result["active_market"], "")
        self.assertEqual(result["last_selected_market"], "")
        self.assertGreaterEqual(len(result["scan_results"]), 2)

    def test_selector_resets_state_when_candle_unit_mismatches(self):
        self.config.selector.include_markets = ["KRW-BTC", "KRW-XRP"]
        self.config.selector.use_trade_flow_filter = False
        with open(self.selector_state, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "candle_unit": 15,
                    "active_market": "KRW-BTC",
                    "cycle_count": 3,
                    "last_selected_market": "KRW-BTC",
                    "last_selected_score": 81.0,
                    "last_scan_timestamp": "2026-03-26T06:45:00",
                    "last_scan_results": [{"market": "KRW-BTC", "score": 81.0}],
                },
                handle,
                indent=2,
            )

        selector = RotatingMarketSelector(
            config=self.config,
            mode="paper",
            selector_state_path=str(self.selector_state),
            broker=self.broker,
        )

        self.assertEqual(selector.state.candle_unit, self.config.upbit.candle_unit)
        self.assertEqual(selector.state.active_market, "")
        self.assertEqual(selector.state.last_selected_market, "")
        self.assertIn("candle_unit_mismatch", selector._state_restore_notice)

    def test_selector_recovers_from_stale_market_runtime_state(self):
        self.config.selector.include_markets = ["KRW-BTC", "KRW-XRP"]
        self.config.selector.use_trade_flow_filter = False
        states_dir = pathlib.Path(self.config.selector.states_dir)
        states_dir.mkdir(parents=True, exist_ok=True)
        stale_market_state = states_dir / "KRW_BTC.json"
        with open(stale_market_state, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "market": "KRW-BTC",
                    "cash": 100000.0,
                    "peak_equity": 100000.0,
                    "history": [
                        {
                            "timestamp": "2026-03-26T00:00:00",
                            "open": 100.0,
                            "high": 100.0,
                            "low": 100.0,
                            "close": 100.0,
                            "volume": 1000.0,
                        },
                        {
                            "timestamp": "2026-03-26T00:15:00",
                            "open": 101.0,
                            "high": 101.0,
                            "low": 101.0,
                            "close": 101.0,
                            "volume": 1000.0,
                        },
                    ],
                    "last_processed_timestamp": "2026-03-26T00:15:00",
                    "processed_bars": 2,
                    "position": None,
                    "pending_order": None,
                },
                handle,
                indent=2,
            )

        selector = RotatingMarketSelector(
            config=self.config,
            mode="paper",
            selector_state_path=str(self.selector_state),
            broker=self.broker,
        )

        result = selector.run_cycle()

        self.assertEqual(result["active_market"], "KRW-BTC")
        self.assertIsNotNone(result["active_summary"])
        with open(stale_market_state, "r", encoding="utf-8") as handle:
            restored_payload = json.load(handle)
        self.assertEqual(restored_payload["candle_unit"], self.config.upbit.candle_unit)
        self.assertTrue(any("PAPER BUY KRW-BTC" in event for event in result["events"]))

    def test_streaming_selector_activates_best_market_from_realtime_message(self):
        self.config.selector.include_markets = ["KRW-BTC", "KRW-XRP"]
        selector = StreamingMarketSelector(
            config=self.config,
            mode="paper",
            selector_state_path=str(self.selector_state),
            broker=self.broker,
        )
        selector.bootstrap_markets()
        selector.process_stream_message(
            build_realtime_orderbook_message(
                "KRW-BTC",
                ask_price=114.0,
                bid_price=113.9,
                ask_size=80.0,
                bid_size=100.0,
                total_ask_size=300.0,
                total_bid_size=360.0,
            )
        )
        for trade_price, trade_volume, ask_bid, sequence in [
            (112.8, 500.0, "BID", 1),
            (112.8, 300.0, "BID", 2),
            (112.8, 100.0, "ASK", 3),
        ]:
            selector.process_stream_message(
                {
                    "type": "trade",
                    "code": "KRW-BTC",
                    "trade_price": trade_price,
                    "trade_volume": trade_volume,
                    "ask_bid": ask_bid,
                    "sequential_id": sequence,
                    "trade_timestamp": 1730000000000 + sequence,
                    "stream_type": "REALTIME",
                }
            )
        message = build_realtime_candle_message(
            "KRW-BTC",
            "2026-03-26T06:45:00",
            112.8,
            114.0,
            112.7,
            113.9,
            280.0,
        )

        result = selector.process_stream_message(message)

        self.assertEqual(result["active_market"], "KRW-BTC")
        self.assertTrue(any("PAPER BUY KRW-BTC" in event for event in result["events"]))
        self.assertEqual(result["event_market"], "KRW-BTC")
        self.assertEqual(result["payload_type"], "candle.15m")

    def test_streaming_selector_blocks_when_trade_flow_is_ask_dominant(self):
        self.config.selector.include_markets = ["KRW-BTC"]
        selector = StreamingMarketSelector(
            config=self.config,
            mode="paper",
            selector_state_path=str(self.selector_state),
            broker=self.broker,
        )
        selector.bootstrap_markets()
        selector.process_stream_message(
            build_realtime_orderbook_message(
                "KRW-BTC",
                ask_price=114.0,
                bid_price=113.9,
                ask_size=80.0,
                bid_size=100.0,
                total_ask_size=300.0,
                total_bid_size=360.0,
            )
        )
        for trade_price, trade_volume, ask_bid, sequence in [
            (112.8, 100.0, "ASK", 11),
            (112.8, 100.0, "ASK", 12),
            (112.8, 50.0, "BID", 13),
        ]:
            selector.process_stream_message(
                {
                    "type": "trade",
                    "code": "KRW-BTC",
                    "trade_price": trade_price,
                    "trade_volume": trade_volume,
                    "ask_bid": ask_bid,
                    "sequential_id": sequence,
                    "trade_timestamp": 1730000001000 + sequence,
                    "stream_type": "REALTIME",
                }
            )
        message = build_realtime_candle_message(
            "KRW-BTC",
            "2026-03-26T06:45:00",
            112.8,
            113.0,
            112.1,
            112.4,
            180.0,
        )

        result = selector.process_stream_message(message)

        self.assertEqual(result["active_market"], "")
        self.assertFalse(result["scan_results"][0]["trade_flow_ok"])

    def test_streaming_selector_blocks_when_orderbook_is_too_ask_heavy(self):
        self.config.selector.include_markets = ["KRW-BTC"]
        self.config.selector.use_trade_flow_filter = False
        selector = StreamingMarketSelector(
            config=self.config,
            mode="paper",
            selector_state_path=str(self.selector_state),
            broker=self.broker,
        )
        selector.bootstrap_markets()
        selector.process_stream_message(
            build_realtime_orderbook_message(
                "KRW-BTC",
                ask_price=114.5,
                bid_price=113.7,
                ask_size=140.0,
                bid_size=60.0,
                total_ask_size=500.0,
                total_bid_size=200.0,
            )
        )
        message = build_realtime_candle_message(
            "KRW-BTC",
            "2026-03-26T06:45:00",
            112.8,
            114.0,
            112.7,
            113.9,
            280.0,
        )

        result = selector.process_stream_message(message)

        self.assertEqual(result["active_market"], "")
        self.assertFalse(result["scan_results"][0]["orderbook_ok"])
        self.assertGreater(result["scan_results"][0]["spread_bps"], 0.0)

    def test_build_selector_stream_subscription_contains_ticker_trade_orderbook_and_candle(self):
        payload = build_selector_stream_subscription(15, ["krw-btc", "KRW-ETH"])

        self.assertEqual(payload[1]["type"], "ticker")
        self.assertEqual(payload[2]["type"], "trade")
        self.assertEqual(payload[3]["type"], "orderbook")
        self.assertEqual(payload[4]["type"], "candle.15m")
        self.assertEqual(payload[4]["codes"], ["KRW-BTC", "KRW-ETH"])
        self.assertTrue(payload[4]["is_only_realtime"])


if __name__ == "__main__":
    unittest.main()
