import shutil
import pathlib
import sys
import json
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402
from upbit_auto_trader.jobs import BackgroundJobManager  # noqa: E402
from upbit_auto_trader.models import Balance, ClosedTrade  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402
from upbit_auto_trader.ui import (  # noqa: E402
    build_dashboard_payload,
    load_editable_config,
    run_apply_preset_action,
    run_backtest_action,
    run_live_reconcile_action,
    run_show_report_action,
    run_load_profile_action,
    run_scan_action,
    run_save_profile_action,
    run_save_current_preset_action,
    run_session_report_action,
    run_start_profile_action,
    run_sync_candles_action,
    run_optimize_action,
    run_signal_action,
    start_managed_job,
    update_editable_config,
)


class FakeUiBroker:
    def __init__(self):
        self.markets = [
            {"market": "KRW-BTC", "market_warning": "NONE"},
            {"market": "KRW-XRP", "market_warning": "NONE"},
        ]
        self.base_balance = 0.01

    def list_markets(self, is_details=True):
        return list(self.markets)

    def get_ticker(self, markets):
        return [
            {"market": "KRW-BTC", "acc_trade_price_24h": 15000000000.0},
            {"market": "KRW-XRP", "acc_trade_price_24h": 3000000000.0},
        ]

    def get_minute_candles(self, market, unit, count=200, to=None):
        candles = load_csv_candles(str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv"))
        mapped = []
        for candle in candles[-count:]:
            mapped.append(
                {
                    "candle_date_time_kst": candle.timestamp,
                    "opening_price": candle.open,
                    "high_price": candle.high,
                    "low_price": candle.low,
                    "trade_price": candle.close,
                    "candle_acc_trade_volume": candle.volume,
                }
            )
        return list(reversed(mapped))

    def get_order_chance(self, market):
        return {
            "bid_account": {"balance": "700000"},
            "ask_account": {"balance": str(self.base_balance)},
            "market": {"bid": {"min_total": "5000"}, "ask": {"min_total": "5000"}},
        }

    def get_accounts(self):
        return [
            Balance(currency="KRW", balance=700000.0, locked=0.0, avg_buy_price=0.0, unit_currency="KRW"),
            Balance(currency="BTC", balance=self.base_balance, locked=0.0, avg_buy_price=0.0, unit_currency="KRW"),
        ]

    def list_open_orders(self, market=None, state=None, states=None, page=None, limit=None, order_by=None):
        return [{"uuid": "open-1", "market": "KRW-BTC", "state": "wait"}]


class RecordingJobManager:
    def __init__(self):
        self.calls = []

    def start_job(
        self,
        name,
        kind,
        command,
        cwd=None,
        auto_restart=False,
        max_restarts=0,
        restart_backoff_seconds=0.0,
        report_on_exit=False,
        report_config_path="",
        report_state_path="",
        report_mode="paper",
        report_output_dir="",
        report_label="",
    ):
        payload = {
            "name": name,
            "kind": kind,
            "command": command,
            "cwd": cwd,
            "auto_restart": auto_restart,
            "max_restarts": max_restarts,
            "restart_backoff_seconds": restart_backoff_seconds,
            "report_on_exit": report_on_exit,
            "report_config_path": report_config_path,
            "report_state_path": report_state_path,
            "report_mode": report_mode,
            "report_output_dir": report_output_dir,
            "report_label": report_label,
        }
        self.calls.append(payload)
        return payload


class StaticJobManager:
    def __init__(self, jobs):
        self.jobs = list(jobs)

    def list_jobs(self):
        return list(self.jobs)


class UiTests(unittest.TestCase):
    def setUp(self):
        self.config_path = str(PROJECT_ROOT / "config.example.json")
        self.temp_config_path = PROJECT_ROOT / "test-ui-config.json"
        self.temp_csv_path = PROJECT_ROOT / "data" / "test-ui-candles.csv"
        self.alert_journal_path = PROJECT_ROOT / "data" / "test-ui-alerts.jsonl"
        self.csv_path = str(PROJECT_ROOT / "data" / "demo_krw_btc_15m.csv")
        self.state_path = PROJECT_ROOT / "data" / "test-ui-state.json"
        self.state_backup_path = pathlib.Path(str(self.state_path) + ".bak")
        self.selector_state_path = PROJECT_ROOT / "data" / "test-ui-selector-state.json"
        self.selector_market_state_path = PROJECT_ROOT / "data" / "selector-states" / "KRW_BTC.json"
        self.preset_dir = PROJECT_ROOT / "data" / "strategy-presets"
        self.profile_dir = PROJECT_ROOT / "data" / "operator-profiles"
        self.reports_dir = PROJECT_ROOT / "data" / "session-reports"
        if self.state_path.exists():
            self.state_path.unlink()
        if self.state_backup_path.exists():
            self.state_backup_path.unlink()
        if self.selector_state_path.exists():
            self.selector_state_path.unlink()
        if self.selector_market_state_path.exists():
            self.selector_market_state_path.unlink()
        if self.temp_config_path.exists():
            self.temp_config_path.unlink()
        if self.temp_csv_path.exists():
            self.temp_csv_path.unlink()
        if self.alert_journal_path.exists():
            self.alert_journal_path.unlink()
        if self.preset_dir.exists():
            for preset_path in self.preset_dir.glob("test-ui-*.json"):
                preset_path.unlink()
        if self.profile_dir.exists():
            for profile_path in self.profile_dir.glob("test-ui-*.json"):
                profile_path.unlink()
        if self.reports_dir.exists():
            for report_path in self.reports_dir.glob("session-report-*-test-ui-report*"):
                report_path.unlink()
        shutil.copyfile(self.config_path, self.temp_config_path)
        with open(self.temp_config_path, "r", encoding="utf-8") as handle:
            temp_config = json.load(handle)
        temp_config["runtime"]["journal_path"] = "data/test-ui-alerts.jsonl"
        with open(self.temp_config_path, "w", encoding="utf-8") as handle:
            json.dump(temp_config, handle, indent=2)
            handle.write("\n")

        config = load_config(self.config_path)
        config.runtime.journal_path = ""
        candles = load_csv_candles(self.csv_path)
        runtime = TradingRuntime(config=config, mode="paper", state_path=self.state_path)
        minimum_history = runtime.strategy.minimum_history()
        runtime.bootstrap(candles[:minimum_history])
        for candle in candles[minimum_history : minimum_history + 3]:
            runtime.process_candle(candle)
        runtime.state.closed_trades.append(
            ClosedTrade(
                market="KRW-BTC",
                entry_timestamp=candles[-3].timestamp,
                exit_timestamp=candles[-2].timestamp,
                entry_price=candles[-3].close,
                exit_price=candles[-2].close,
                quantity=0.01,
                gross_pnl=1200.0,
                net_pnl=1000.0,
                return_pct=1.25,
                exit_reason="strategy_exit",
            )
        )
        runtime.state.events.extend(
            [
                "{0} PAPER BUY KRW-BTC qty=0.01000000 price={1:.2f} score=66.0".format(
                    candles[-3].timestamp,
                    candles[-3].close,
                ),
                "{0} PAPER SELL KRW-BTC qty=0.01000000 price={1:.2f} reason=strategy_exit pnl=1000.00".format(
                    candles[-2].timestamp,
                    candles[-2].close,
                ),
                "{0} BLOCKED KRW-BTC reason=minimum_order_bid".format(candles[-1].timestamp),
            ]
        )
        runtime._save_state()  # noqa: SLF001
        self.selector_market_state_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.state_path, self.selector_market_state_path)
        with open(self.selector_state_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "active_market": "KRW-BTC",
                    "cycle_count": 7,
                    "last_selected_market": "KRW-BTC",
                    "last_selected_score": 72.5,
                    "last_scan_timestamp": candles[-1].timestamp,
                    "last_scan_results": [
                        {
                            "market": "KRW-BTC",
                            "action": "BUY",
                            "score": 72.5,
                            "confidence": 0.82,
                            "reasons": ["ema_trend", "volume_spike"],
                            "timestamp": candles[-1].timestamp,
                            "close": candles[-1].close,
                            "market_warning": "NONE",
                            "liquidity_24h": 15000000000.0,
                            "liquidity_ok": True,
                        },
                        {
                            "market": "KRW-XRP",
                            "action": "HOLD",
                            "score": 58.0,
                            "confidence": 0.55,
                            "reasons": ["macd_flat"],
                            "timestamp": candles[-1].timestamp,
                            "close": 850.0,
                            "market_warning": "NONE",
                            "liquidity_24h": 3000000000.0,
                            "liquidity_ok": True,
                        },
                    ],
                },
                handle,
                indent=2,
            )

    def tearDown(self):
        if self.state_path.exists():
            self.state_path.unlink()
        if self.state_backup_path.exists():
            self.state_backup_path.unlink()
        if self.selector_state_path.exists():
            self.selector_state_path.unlink()
        if self.selector_market_state_path.exists():
            self.selector_market_state_path.unlink()
        if self.temp_config_path.exists():
            self.temp_config_path.unlink()
        if self.temp_csv_path.exists():
            self.temp_csv_path.unlink()
        if self.alert_journal_path.exists():
            self.alert_journal_path.unlink()
        if self.preset_dir.exists():
            for preset_path in self.preset_dir.glob("test-ui-*.json"):
                preset_path.unlink()
        if self.profile_dir.exists():
            for profile_path in self.profile_dir.glob("test-ui-*.json"):
                profile_path.unlink()
        if self.reports_dir.exists():
            for report_path in self.reports_dir.glob("session-report-*-test-ui-report*"):
                report_path.unlink()

    def test_build_dashboard_payload_contains_summary_and_signal(self):
        payload = build_dashboard_payload(
            config_path=self.config_path,
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="paper",
            job_manager=BackgroundJobManager(),
        )

        self.assertEqual(payload["app"]["market"], "KRW-BTC")
        self.assertIsNotNone(payload["state_summary"])
        self.assertIsNotNone(payload["latest_signal"])
        self.assertTrue(payload["csv_info"]["rows"] > 0)
        self.assertEqual(payload["ui_defaults"]["scan_max_markets"], 10)
        self.assertEqual(payload["paths"]["selector_state_path"], str(self.selector_state_path))
        self.assertTrue(len(payload["chart"]["points"]) > 0)
        self.assertGreaterEqual(len(payload["chart"]["markers"]), 2)
        self.assertGreaterEqual(len(payload["activity"]["recent_trades"]), 1)
        self.assertGreaterEqual(len(payload["activity"]["recent_events"]), 1)
        self.assertEqual(payload["selector_summary"]["active_market"], "KRW-BTC")
        self.assertEqual(payload["selector_summary"]["cycle_count"], 7)
        self.assertIsNotNone(payload["selector_summary"]["active_market_summary"])
        self.assertGreaterEqual(len(payload["selector_summary"]["active_market_chart"]["points"]), 1)
        self.assertGreaterEqual(len(payload["selector_summary"]["active_market_activity"]["recent_events"]), 1)
        self.assertGreaterEqual(len(payload["selector_summary"]["last_scan_results"]), 2)
        self.assertEqual(payload["jobs"], [])

    def test_build_dashboard_payload_supports_focus_market(self):
        payload = build_dashboard_payload(
            config_path=self.config_path,
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=None,
            mode="paper",
            focus_market="KRW-XRP",
            job_manager=BackgroundJobManager(),
        )

        self.assertEqual(payload["app"]["market"], "KRW-XRP")
        self.assertTrue(payload["paths"]["suggested_market_csv_path"].endswith("krw_xrp_15m.csv"))
        self.assertIsNone(payload["latest_signal"])
        self.assertEqual(payload["chart"]["points"], [])

    def test_build_dashboard_payload_exposes_strategy_presets(self):
        run_save_current_preset_action(
            config_path=str(self.temp_config_path),
            preset_name="test-ui-current",
            csv_path=self.csv_path,
            market="KRW-BTC",
        )

        payload = build_dashboard_payload(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="paper",
            job_manager=BackgroundJobManager(),
        )

        self.assertTrue(payload["strategy_presets"]["dir"].endswith("data\\strategy-presets"))
        self.assertTrue(any(item["name"] == "test-ui-current" for item in payload["strategy_presets"]["items"]))

    def test_build_dashboard_payload_exposes_operator_profiles(self):
        run_save_profile_action(
            config_path=str(self.temp_config_path),
            profile_name="test-ui-paper",
            profile_payload={
                "job_type": "paper-loop",
                "market": "KRW-BTC",
                "csv_path": self.csv_path,
                "state_path": str(self.state_path),
                "selector_state_path": str(self.selector_state_path),
                "quote_currency": "KRW",
                "max_markets": 10,
                "poll_seconds": 6.0,
                "reconcile_every": 11,
                "reconcile_every_loops": 3,
                "preset": "",
                "auto_restart": True,
                "max_restarts": 2,
                "restart_backoff_seconds": 1.5,
            },
        )

        payload = build_dashboard_payload(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="paper",
            job_manager=BackgroundJobManager(),
        )

        self.assertTrue(payload["operator_profiles"]["dir"].endswith("data\\operator-profiles"))
        self.assertTrue(any(item["name"] == "test-ui-paper" for item in payload["operator_profiles"]["items"]))

    def test_build_dashboard_payload_exposes_session_reports(self):
        run_session_report_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            mode="paper",
            label="test-ui-report",
        )

        payload = build_dashboard_payload(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="paper",
            job_manager=BackgroundJobManager(),
        )

        self.assertTrue(payload["paths"]["reports_dir"].endswith("data\\session-reports"))
        self.assertTrue(any("test-ui-report" in item["name"] for item in payload["session_reports"]["items"]))

    def test_build_dashboard_payload_exposes_alerts(self):
        with open(self.alert_journal_path, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "event_type": "blocked",
                        "timestamp": "2026-03-23T00:00:00+00:00",
                        "market": "KRW-BTC",
                        "reason": "daily_loss_limit",
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            handle.write(
                json.dumps(
                    {
                        "event_type": "buy_fill",
                        "timestamp": "2026-03-23T00:05:00+00:00",
                        "market": "KRW-BTC",
                        "quantity": 0.01,
                        "price": 100000000.0,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        payload = build_dashboard_payload(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="live",
            job_manager=StaticJobManager(
                [
                    {
                        "name": "live-daemon",
                        "kind": "live-daemon",
                        "pid": 4321,
                        "running": False,
                        "returncode": 1,
                        "started_at": 1760000000.0,
                        "command": ["python", "-m", "upbit_auto_trader.main"],
                        "cwd": str(PROJECT_ROOT),
                        "log_path": "data/webui-jobs/live-daemon.log",
                        "log_tail": "boom",
                        "last_report": {
                            "generated_at": "2026-03-23T00:06:00+00:00",
                            "json_path": str(self.reports_dir / "session-report-test-ui-report.json"),
                            "summary": {"market": "KRW-BTC"},
                        },
                    }
                ]
            ),
        )

        self.assertGreaterEqual(payload["alerts"]["summary"]["requires_attention"], 1)
        self.assertGreaterEqual(payload["alerts"]["summary"]["error"], 1)
        self.assertGreaterEqual(payload["alerts"]["summary"]["warning"], 1)
        self.assertTrue(any(item["headline"] == "Job Failed" for item in payload["alerts"]["items"]))
        self.assertTrue(any(item["headline"] == "Session Report Ready" for item in payload["alerts"]["items"]))
        self.assertTrue(any(item["headline"] == "Blocked Entry" for item in payload["alerts"]["items"]))
        self.assertTrue(any(item["source"] == "journal" for item in payload["alerts"]["items"]))

    def test_backtest_signal_and_optimize_actions_return_expected_keys(self):
        signal = run_signal_action(self.config_path, self.csv_path, market="KRW-BTC")
        backtest = run_backtest_action(self.config_path, self.csv_path, market="KRW-BTC")
        optimize = run_optimize_action(self.config_path, self.csv_path, top=3, market="KRW-BTC")

        self.assertIn("action", signal)
        self.assertEqual(signal["market"], "KRW-BTC")
        self.assertIn("final_equity", backtest)
        self.assertEqual(backtest["market"], "KRW-BTC")
        self.assertEqual(len(optimize["top"]), 3)

    def test_optimize_action_can_save_best_preset(self):
        optimize = run_optimize_action(
            str(self.temp_config_path),
            self.csv_path,
            top=3,
            market="KRW-BTC",
            save_best_preset_name="test-ui-best",
        )

        self.assertIsNotNone(optimize["saved_preset"])
        self.assertEqual(optimize["saved_preset"]["name"], "test-ui-best")
        self.assertEqual(
            optimize["saved_preset"]["summary"]["buy_threshold"],
            optimize["top"][0]["buy_threshold"],
        )

    def test_strategy_preset_can_be_saved_and_applied(self):
        saved = run_save_current_preset_action(
            config_path=str(self.temp_config_path),
            preset_name="test-ui-apply",
            csv_path=self.csv_path,
            market="KRW-BTC",
        )
        update_editable_config(
            str(self.temp_config_path),
            {
                "strategy.buy_threshold": 71.0,
                "strategy.sell_threshold": 44.0,
            },
        )

        applied = run_apply_preset_action(str(self.temp_config_path), saved["path"])
        updated = load_config(str(self.temp_config_path))

        self.assertEqual(applied["preset"]["name"], "test-ui-apply")
        self.assertEqual(updated.strategy.buy_threshold, saved["strategy"]["buy_threshold"])
        self.assertEqual(updated.strategy.sell_threshold, saved["strategy"]["sell_threshold"])

    def test_operator_profile_can_be_saved_loaded_and_started(self):
        preset = run_save_current_preset_action(
            config_path=str(self.temp_config_path),
            preset_name="test-ui-profile-preset",
            csv_path=self.csv_path,
            market="KRW-BTC",
        )
        update_editable_config(
            str(self.temp_config_path),
            {
                "strategy.buy_threshold": 71.0,
            },
        )

        saved_profile = run_save_profile_action(
            config_path=str(self.temp_config_path),
            profile_name="test-ui-profile",
            profile_payload={
                "job_type": "paper-loop",
                "market": "KRW-BTC",
                "csv_path": self.csv_path,
                "state_path": str(self.state_path),
                "selector_state_path": str(self.selector_state_path),
                "quote_currency": "KRW",
                "max_markets": 8,
                "poll_seconds": 6.0,
                "reconcile_every": 11,
                "reconcile_every_loops": 3,
                "preset": preset["path"],
                "auto_restart": True,
                "max_restarts": 4,
                "restart_backoff_seconds": 1.5,
            },
        )
        loaded_profile = run_load_profile_action(str(self.temp_config_path), saved_profile["path"])
        manager = RecordingJobManager()
        started = run_start_profile_action(
            config_path=str(self.temp_config_path),
            profile_ref=saved_profile["path"],
            job_manager=manager,
        )
        updated = load_config(str(self.temp_config_path))

        self.assertEqual(loaded_profile["profile"]["job_type"], "paper-loop")
        self.assertEqual(started["profile"]["name"], "test-ui-profile")
        self.assertEqual(updated.strategy.buy_threshold, preset["strategy"]["buy_threshold"])
        self.assertTrue(started["job"]["auto_restart"])
        self.assertEqual(started["job"]["max_restarts"], 4)
        self.assertEqual(started["job"]["restart_backoff_seconds"], 1.5)
        self.assertIn("run-loop", started["job"]["command"])
        self.assertTrue(started["job"]["report_on_exit"])
        self.assertEqual(started["job"]["report_mode"], "paper")
        self.assertEqual(started["job"]["report_state_path"], str(self.state_path))

    def test_session_report_can_be_exported_and_loaded(self):
        exported = run_session_report_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            mode="paper",
            label="test-ui-report",
        )
        loaded = run_show_report_action(
            config_path=str(self.temp_config_path),
            report_ref=exported["json_path"],
        )

        self.assertTrue(pathlib.Path(exported["json_path"]).exists())
        self.assertTrue(pathlib.Path(exported["html_path"]).exists())
        self.assertEqual(loaded["json_path"], exported["json_path"])
        self.assertIn("recent_events", loaded)

    def test_scan_and_reconcile_actions_return_expected_keys(self):
        broker = FakeUiBroker()
        scan = run_scan_action(self.config_path, max_markets=2, quote_currency="KRW", broker=broker)
        reconcile = run_live_reconcile_action(
            self.config_path,
            str(self.state_path),
            mode="live",
            broker=broker,
        )

        self.assertEqual(scan["scanned_market_count"], 2)
        self.assertTrue(len(scan["scan_results"]) >= 1)
        self.assertEqual(reconcile["open_order_count"], 1)
        self.assertIn("summary", reconcile)

    def test_editable_config_can_be_loaded_and_saved(self):
        before = load_editable_config(str(self.temp_config_path))
        result = update_editable_config(
            str(self.temp_config_path),
            {
                "strategy.buy_threshold": 70.0,
                "strategy.sell_threshold": 42.0,
                "selector.max_markets": 7,
            },
        )
        after = load_editable_config(str(self.temp_config_path))

        self.assertNotEqual(before["strategy.buy_threshold"], after["strategy.buy_threshold"])
        self.assertEqual(result["current"]["strategy.buy_threshold"], 70.0)
        self.assertEqual(result["current"]["selector.max_markets"], 7)

    def test_sync_candles_action_writes_csv(self):
        broker = FakeUiBroker()
        result = run_sync_candles_action(
            config_path=self.config_path,
            csv_path=str(self.temp_csv_path),
            count=50,
            broker=broker,
        )

        self.assertTrue(self.temp_csv_path.exists())
        self.assertEqual(result["rows_written"], 44)

    def test_start_managed_job_supports_selector_and_supervisor(self):
        manager = RecordingJobManager()

        selector_job = start_managed_job(
            config_path=self.config_path,
            job_type="paper-selector",
            state_path=str(self.state_path),
            selector_state_path="data/test-selector-state.json",
            csv_path=self.csv_path,
            poll_seconds=6.0,
            reconcile_every_loops=3,
            reconcile_every=11,
            market="KRW-BTC",
            quote_currency="KRW",
            max_markets=9,
            auto_restart=True,
            max_restarts=3,
            restart_backoff_seconds=1.5,
            job_manager=manager,
        )
        supervisor_job = start_managed_job(
            config_path=self.config_path,
            job_type="live-supervisor",
            state_path=str(self.state_path),
            selector_state_path="data/test-selector-state.json",
            csv_path=self.csv_path,
            poll_seconds=6.0,
            reconcile_every_loops=3,
            reconcile_every=11,
            market="KRW-BTC",
            quote_currency="KRW",
            max_markets=9,
            auto_restart=False,
            max_restarts=0,
            restart_backoff_seconds=0.0,
            job_manager=manager,
        )

        self.assertIn("run-selector", selector_job["command"])
        self.assertIn("data/test-selector-state.json", selector_job["command"])
        self.assertIn("9", selector_job["command"])
        self.assertTrue(selector_job["auto_restart"])
        self.assertTrue(selector_job["report_on_exit"])
        self.assertEqual(selector_job["report_mode"], "paper")
        self.assertIn("run-live-supervisor", supervisor_job["command"])
        self.assertIn("11", supervisor_job["command"])
        self.assertTrue(supervisor_job["report_on_exit"])
        self.assertEqual(supervisor_job["report_mode"], "live")

    def test_start_managed_job_uses_default_state_path_for_reports(self):
        manager = RecordingJobManager()

        started = start_managed_job(
            config_path=self.config_path,
            job_type="paper-loop",
            state_path=None,
            selector_state_path=None,
            csv_path=self.csv_path,
            poll_seconds=5.0,
            reconcile_every_loops=None,
            reconcile_every=None,
            market="KRW-BTC",
            quote_currency="KRW",
            max_markets=5,
            auto_restart=False,
            max_restarts=0,
            restart_backoff_seconds=0.0,
            job_manager=manager,
        )

        self.assertTrue(started["report_on_exit"])
        self.assertTrue(started["report_state_path"].endswith("data\\paper-state-ui.json"))


if __name__ == "__main__":
    unittest.main()
