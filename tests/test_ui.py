import shutil
import pathlib
import sys
import json
import hashlib
import unittest
from unittest import mock


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.brokers.upbit import UpbitError  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402
from upbit_auto_trader.jobs import BackgroundJobManager  # noqa: E402
from upbit_auto_trader.models import Balance, ClosedTrade  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402
from upbit_auto_trader.ui import (  # noqa: E402
    build_dashboard_payload,
    cleanup_managed_jobs,
    load_editable_config,
    run_apply_preset_action,
    run_backtest_action,
    run_doctor_action,
    run_delete_report_action,
    run_delete_profile_action,
    run_live_reconcile_action,
    run_show_report_action,
    preview_completion_workflow_action,
    run_load_profile_action,
    run_preview_profile_action,
    run_scan_action,
    run_save_profile_action,
    run_save_current_preset_action,
    run_prune_reports_action,
    run_session_report_action,
    run_live_toggle_action,
    run_live_easy_prep_action,
    run_live_market_validation_action,
    start_completion_workflow_action,
    run_start_profile_action,
    run_sync_candles_action,
    run_optimize_action,
    run_signal_action,
    preview_managed_job,
    start_managed_job,
    stop_all_managed_jobs,
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
        self.stop_all_calls = 0
        self.cleanup_calls = []

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
        report_keep_latest=None,
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
            "report_keep_latest": report_keep_latest,
        }
        self.calls.append(payload)
        return payload

    def stop_all(self):
        self.stop_all_calls += 1
        return {
            "requested": len(self.calls),
            "stopped": len(self.calls),
            "items": list(self.calls),
        }

    def cleanup_stopped(self, remove_logs=False):
        self.cleanup_calls.append(remove_logs)
        return {
            "removed_jobs": len(self.calls),
            "removed_heartbeats": len(self.calls),
            "removed_logs": len(self.calls) if remove_logs else 0,
            "skipped_running": 0,
            "items": list(self.calls),
        }


class StaticJobManager:
    def __init__(self, jobs, history=None):
        self.jobs = list(jobs)
        self.history = list(history or [])

    def list_jobs(self):
        return list(self.jobs)

    def list_history(self):
        return list(self.history)


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
        self.selector_state_bom_path = PROJECT_ROOT / "data" / "test-ui-selector-state-bom.json"
        self.selector_market_state_path = PROJECT_ROOT / "data" / "selector-states" / "KRW_BTC.json"
        self.preset_dir = PROJECT_ROOT / "data" / "strategy-presets"
        self.profile_dir = PROJECT_ROOT / "data" / "operator-profiles"
        self.reports_dir = PROJECT_ROOT / "data" / "session-reports"
        self.temp_reports_dir = PROJECT_ROOT / "data" / "test-ui-session-reports"
        self.job_heartbeat_path = PROJECT_ROOT / "data" / "webui-jobs" / "test-ui-heartbeat.heartbeat.json"
        self.release_pack_dir = PROJECT_ROOT / "data" / "test-ui-release-pack"
        self.release_pack_zip_path = PROJECT_ROOT / "data" / "test-ui-release-pack.zip"
        self.live_readiness_path = PROJECT_ROOT / "data" / "test-ui-live-readiness.json"
        self.live_validation_summary_path = PROJECT_ROOT / "data" / "test-ui-live-validation-summary.json"
        self.release_pack_dir_patcher = mock.patch(
            "upbit_auto_trader.ui._default_release_pack_directory",
            return_value=str(self.release_pack_dir),
        )
        self.release_pack_zip_patcher = mock.patch(
            "upbit_auto_trader.ui._default_release_pack_zip_path",
            return_value=str(self.release_pack_zip_path),
        )
        self.live_readiness_patcher = mock.patch(
            "upbit_auto_trader.ui._resolve_live_readiness_path",
            return_value=str(self.live_readiness_path),
        )
        self.live_validation_summary_patcher = mock.patch(
            "upbit_auto_trader.ui._resolve_live_market_validation_summary_path",
            return_value=str(self.live_validation_summary_path),
        )
        self.release_pack_dir_patcher.start()
        self.release_pack_zip_patcher.start()
        self.live_readiness_patcher.start()
        self.live_validation_summary_patcher.start()
        if self.state_path.exists():
            self.state_path.unlink()
        if self.state_backup_path.exists():
            self.state_backup_path.unlink()
        if self.selector_state_path.exists():
            self.selector_state_path.unlink()
        if self.selector_state_bom_path.exists():
            self.selector_state_bom_path.unlink()
        if self.selector_market_state_path.exists():
            self.selector_market_state_path.unlink()
        if self.temp_config_path.exists():
            self.temp_config_path.unlink()
        if self.temp_csv_path.exists():
            self.temp_csv_path.unlink()
        if self.alert_journal_path.exists():
            self.alert_journal_path.unlink()
        if self.job_heartbeat_path.exists():
            self.job_heartbeat_path.unlink()
        if self.live_readiness_path.exists():
            self.live_readiness_path.unlink()
        if self.live_validation_summary_path.exists():
            self.live_validation_summary_path.unlink()
        self._cleanup_release_pack_artifacts()
        if self.temp_reports_dir.exists():
            for report_path in self.temp_reports_dir.glob("*"):
                report_path.unlink()
            self.temp_reports_dir.rmdir()
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
        self.release_pack_dir_patcher.stop()
        self.release_pack_zip_patcher.stop()
        self.live_readiness_patcher.stop()
        self.live_validation_summary_patcher.stop()
        if self.state_path.exists():
            self.state_path.unlink()
        if self.state_backup_path.exists():
            self.state_backup_path.unlink()
        if self.selector_state_path.exists():
            self.selector_state_path.unlink()
        if self.selector_state_bom_path.exists():
            self.selector_state_bom_path.unlink()
        if self.selector_market_state_path.exists():
            self.selector_market_state_path.unlink()
        if self.temp_config_path.exists():
            self.temp_config_path.unlink()
        if self.temp_csv_path.exists():
            self.temp_csv_path.unlink()
        if self.alert_journal_path.exists():
            self.alert_journal_path.unlink()
        if self.job_heartbeat_path.exists():
            self.job_heartbeat_path.unlink()
        if self.live_readiness_path.exists():
            self.live_readiness_path.unlink()
        if self.live_validation_summary_path.exists():
            self.live_validation_summary_path.unlink()
        self._cleanup_release_pack_artifacts()
        if self.temp_reports_dir.exists():
            for report_path in self.temp_reports_dir.glob("*"):
                report_path.unlink()
            self.temp_reports_dir.rmdir()
        if self.preset_dir.exists():
            for preset_path in self.preset_dir.glob("test-ui-*.json"):
                preset_path.unlink()
        if self.profile_dir.exists():
            for profile_path in self.profile_dir.glob("test-ui-*.json"):
                profile_path.unlink()
        if self.reports_dir.exists():
            for report_path in self.reports_dir.glob("session-report-*-test-ui-report*"):
                report_path.unlink()

    def _cleanup_release_pack_artifacts(self):
        if self.release_pack_dir.exists():
            shutil.rmtree(self.release_pack_dir)
        if self.release_pack_zip_path.exists():
            self.release_pack_zip_path.unlink()

    def _write_release_pack_artifacts(self, corrupt_entry: str = "", verified: bool = False):
        self.release_pack_dir.mkdir(parents=True, exist_ok=True)
        release_files = {
            "release-metadata.json": json.dumps({"version": "test-ui"}, indent=2),
            "release-notes.md": "# Test UI release\n",
            "release-bundle.zip": "bundle-bytes\n",
            "support-bundle.zip": "support-bytes\n",
        }
        for relative_path, contents in release_files.items():
            target_path = self.release_pack_dir / relative_path
            target_path.write_text(contents, encoding="utf-8")

        self.release_pack_zip_path.write_text("pack-zip\n", encoding="utf-8")

        manifest_entries = []
        for relative_path in ("release-metadata.json", "release-notes.md", "release-bundle.zip", "support-bundle.zip"):
            digest = hashlib.sha256((self.release_pack_dir / relative_path).read_bytes()).hexdigest().upper()
            manifest_entries.append({"path": relative_path, "sha256": digest})

        manifest = {
            "generated_at": "2026-03-29T00:00:00+09:00",
            "output_directory": str(self.release_pack_dir),
            "includes_support_bundle": True,
            "files": manifest_entries,
        }
        (self.release_pack_dir / "release-pack-manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        if verified:
            manifest_sha256 = hashlib.sha256((self.release_pack_dir / "release-pack-manifest.json").read_bytes()).hexdigest().upper()
            (self.release_pack_dir / "release-pack-verification.json").write_text(
                json.dumps(
                    {
                        "status": "verified",
                        "verified_at": "2026-03-29T01:23:45+09:00",
                        "manifest_sha256": manifest_sha256,
                        "manifest_file_count": len(manifest_entries),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        if corrupt_entry:
            (self.release_pack_dir / corrupt_entry).write_text("corrupted\n", encoding="utf-8")

    def _release_pack_path_patches(self):
        return (
            mock.patch(
                "upbit_auto_trader.ui._default_release_pack_directory",
                return_value=str(self.release_pack_dir),
            ),
            mock.patch(
                "upbit_auto_trader.ui._default_release_pack_zip_path",
                return_value=str(self.release_pack_zip_path),
            ),
        )

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
        self.assertEqual(payload["ui_defaults"]["scan_max_markets"], 5)
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
        self.assertEqual(payload["completion_workflow"]["default_stage"], "verify")
        self.assertTrue(any(item["stage"] == "all-safe" for item in payload["completion_workflow"]["items"]))
        self.assertTrue(any(item["stage"] == "release-pack" for item in payload["completion_workflow"]["items"]))
        self.assertTrue(any(item["stage"] == "release-verify" for item in payload["completion_workflow"]["items"]))
        self.assertEqual(payload["release_artifacts"]["status"], "missing")
        self.assertIn("operator_checklist", payload)
        self.assertIn(payload["operator_checklist"]["summary"]["overall_status"], {"ready", "paper_ready", "needs_setup"})
        self.assertTrue(any(item["key"] == "release_artifacts" for item in payload["operator_checklist"]["items"]))
        self.assertEqual(payload["jobs"], [])
        self.assertEqual(payload["job_health"]["summary"]["total"], 0)
        self.assertEqual(payload["job_health"]["summary"]["requires_attention"], 0)
        self.assertIsInstance(payload["job_history"]["items"], list)

    def test_build_dashboard_payload_uses_live_mode_for_selector_runtime(self):
        payload = build_dashboard_payload(
            config_path=self.config_path,
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="live",
            job_manager=BackgroundJobManager(),
        )

        self.assertEqual(payload["app"]["mode"], "live")
        self.assertIsNotNone(payload["selector_summary"]["active_market_summary"])
        self.assertEqual(payload["selector_summary"]["active_market_summary"]["mode"], "live")

    def test_build_dashboard_payload_reads_selector_state_with_bom(self):
        bom_selector_state_path = self.selector_state_bom_path
        bom_selector_runtime_path = self.selector_market_state_path
        bom_selector_state_path.write_text(
            self.selector_state_path.read_text(encoding="utf-8"),
            encoding="utf-8-sig",
        )
        bom_selector_runtime_path.write_text(
            self.selector_market_state_path.read_text(encoding="utf-8"),
            encoding="utf-8-sig",
        )

        payload = build_dashboard_payload(
            config_path=self.config_path,
            state_path=str(self.state_path),
            selector_state_path=str(bom_selector_state_path),
            csv_path=self.csv_path,
            mode="live",
            job_manager=BackgroundJobManager(),
        )

        self.assertEqual(payload["selector_summary"]["active_market"], "KRW-BTC")
        self.assertIsNotNone(payload["selector_summary"]["active_market_summary"])

    def test_build_dashboard_payload_filters_selector_results_to_include_markets(self):
        with open(self.temp_config_path, "r", encoding="utf-8") as handle:
            temp_config = json.load(handle)
        temp_config["selector"]["include_markets"] = ["KRW-BTC"]
        with open(self.temp_config_path, "w", encoding="utf-8") as handle:
            json.dump(temp_config, handle, indent=2)
            handle.write("\n")

        payload = build_dashboard_payload(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="live",
            job_manager=BackgroundJobManager(),
        )

        self.assertEqual(
            [item["market"] for item in payload["selector_summary"]["last_scan_results"]],
            ["KRW-BTC"],
        )

    def test_build_dashboard_payload_includes_live_control(self):
        self.live_readiness_path.write_text(
            json.dumps({"blockers": ["access_key_missing"]}, indent=2),
            encoding="utf-8",
        )

        payload = build_dashboard_payload(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="live",
            job_manager=BackgroundJobManager(),
        )

        self.assertIn("live_control", payload)
        self.assertEqual(payload["live_control"]["market"], "KRW-BTC")
        self.assertIn("access_key_missing", payload["live_control"]["readiness_blockers"])
        self.assertFalse(payload["live_control"]["live_enabled"])
        self.assertEqual(payload["ui_defaults"]["live_validation_buy_krw"], 6000)

    def test_run_live_toggle_action_updates_live_enabled_and_market(self):
        result = run_live_toggle_action(
            config_path=str(self.temp_config_path),
            enabled=True,
            market="KRW-ETH",
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["live_enabled"])

        updated = load_config(str(self.temp_config_path))
        self.assertTrue(updated.upbit.live_enabled)
        self.assertEqual(updated.market, "KRW-ETH")
        self.assertEqual(updated.upbit.market, "KRW-ETH")

    @mock.patch("upbit_auto_trader.ui._run_powershell_script")
    @mock.patch("upbit_auto_trader.ui.UpbitBroker")
    def test_run_live_easy_prep_action_returns_readiness_and_live_control(self, broker_cls, run_script):
        readiness = {
            "blockers": [],
            "release_status": {"release_artifacts": {"status": "ready"}},
        }
        self.live_readiness_path.write_text(json.dumps(readiness, indent=2), encoding="utf-8")
        run_script.return_value = {
            "stdout": "ok",
            "stderr": "",
            "returncode": 0,
            "command": ["powershell.exe"],
        }
        broker = broker_cls.return_value
        broker.readiness_report.return_value = {"private_ready": True, "private_issues": []}

        result = run_live_easy_prep_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            market="KRW-BTC",
            csv_path=self.csv_path,
            count=120,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["readiness"]["blockers"], [])
        self.assertTrue(result["live_control"]["private_ready"])
        run_script.assert_called_once()

    @mock.patch("upbit_auto_trader.ui._run_powershell_script")
    @mock.patch("upbit_auto_trader.ui.UpbitBroker")
    def test_run_live_market_validation_action_returns_summary_and_live_control(self, broker_cls, run_script):
        summary = {
            "market": "KRW-BTC",
            "buy_krw": 6000,
            "status": "completed",
        }
        self.live_validation_summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        run_script.return_value = {
            "stdout": "ok",
            "stderr": "",
            "returncode": 0,
            "command": ["powershell.exe"],
        }
        broker = broker_cls.return_value
        broker.readiness_report.return_value = {"private_ready": True, "private_issues": []}

        result = run_live_market_validation_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            market="KRW-BTC",
            buy_krw=6000,
            confirm="LIVE",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["status"], "completed")
        self.assertTrue(result["live_control"]["private_ready"])
        run_script.assert_called_once()

    def test_build_dashboard_payload_exposes_operator_checklist(self):
        payload = build_dashboard_payload(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="paper",
            job_manager=BackgroundJobManager(),
        )

        checklist = payload["operator_checklist"]
        self.assertTrue(any(item["key"] == "workflow_script" and item["status"] == "success" for item in checklist["items"]))
        self.assertTrue(any(item["key"] == "release_artifacts" and item["status"] == "warning" for item in checklist["items"]))
        self.assertTrue(any(item["key"] == "live_api" and item["status"] == "error" for item in checklist["items"]))
        self.assertTrue(any("Upbit access/secret key" in item for item in checklist["next_steps"]))

    def test_build_dashboard_payload_marks_unverified_release_artifacts_as_warning(self):
        self._write_release_pack_artifacts()
        patch_directory, patch_zip = self._release_pack_path_patches()
        with patch_directory, patch_zip:
            payload = build_dashboard_payload(
                config_path=str(self.temp_config_path),
                state_path=str(self.state_path),
                selector_state_path=str(self.selector_state_path),
                csv_path=self.csv_path,
                mode="paper",
                job_manager=BackgroundJobManager(),
            )

        self.assertEqual(payload["release_artifacts"]["status"], "ready")
        self.assertTrue(payload["release_artifacts"]["checksum_ok"])
        self.assertFalse(payload["release_artifacts"]["verification_current"])
        release_item = next(item for item in payload["operator_checklist"]["items"] if item["key"] == "release_artifacts")
        self.assertEqual(release_item["status"], "warning")
        self.assertIn("release-verify", release_item["detail"])

    def test_build_dashboard_payload_marks_verified_release_artifacts_as_success(self):
        self._write_release_pack_artifacts(verified=True)
        patch_directory, patch_zip = self._release_pack_path_patches()
        with patch_directory, patch_zip:
            payload = build_dashboard_payload(
                config_path=str(self.temp_config_path),
                state_path=str(self.state_path),
                selector_state_path=str(self.selector_state_path),
                csv_path=self.csv_path,
                mode="paper",
                job_manager=BackgroundJobManager(),
            )

        self.assertEqual(payload["release_artifacts"]["status"], "ready")
        self.assertTrue(payload["release_artifacts"]["verification_current"])
        self.assertEqual(payload["release_artifacts"]["verification_status"], "verified")
        release_item = next(item for item in payload["operator_checklist"]["items"] if item["key"] == "release_artifacts")
        self.assertEqual(release_item["status"], "success")
        self.assertIn("release-verify completed", release_item["detail"])

    def test_build_dashboard_payload_marks_invalid_release_artifacts(self):
        self._write_release_pack_artifacts(corrupt_entry="release-bundle.zip")
        patch_directory, patch_zip = self._release_pack_path_patches()
        with patch_directory, patch_zip:
            payload = build_dashboard_payload(
                config_path=str(self.temp_config_path),
                state_path=str(self.state_path),
                selector_state_path=str(self.selector_state_path),
                csv_path=self.csv_path,
                mode="paper",
                job_manager=BackgroundJobManager(),
            )

        self.assertEqual(payload["release_artifacts"]["status"], "invalid")
        self.assertIn("checksum:release-bundle.zip", payload["release_artifacts"]["issues"])
        release_item = next(item for item in payload["operator_checklist"]["items"] if item["key"] == "release_artifacts")
        self.assertEqual(release_item["status"], "error")
        self.assertIn("invalid", release_item["detail"])
        self.assertTrue(any("release-pack" in item for item in payload["operator_checklist"]["next_steps"]))

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
        self.assertTrue(payload["paths"]["suggested_market_csv_path"].endswith("krw_xrp_240m.csv"))
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
                "report_keep_latest": 15,
            },
            notes="ui dashboard profile",
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
        self.assertTrue(any(item["notes"] == "ui dashboard profile" for item in payload["operator_profiles"]["items"]))
        self.assertTrue(any(item["start_count"] == 0 for item in payload["operator_profiles"]["items"] if item["name"] == "test-ui-paper"))

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
                ],
                history=[
                    {
                        "name": "live-daemon",
                        "status": "failed",
                        "returncode": 1,
                    }
                ],
            ),
        )

        self.assertGreaterEqual(payload["alerts"]["summary"]["requires_attention"], 1)
        self.assertGreaterEqual(payload["alerts"]["summary"]["error"], 1)
        self.assertGreaterEqual(payload["alerts"]["summary"]["warning"], 1)
        self.assertTrue(any(item["headline"] == "Job Failed" for item in payload["alerts"]["items"]))
        self.assertTrue(any(item["headline"] == "Session Report Ready" for item in payload["alerts"]["items"]))
        self.assertTrue(any(item["headline"] == "Blocked Entry" for item in payload["alerts"]["items"]))
        self.assertTrue(any(item["source"] == "journal" for item in payload["alerts"]["items"]))
        self.assertEqual(payload["job_history"]["items"][0]["name"], "live-daemon")

    def test_build_dashboard_payload_flags_stale_running_job_heartbeat(self):
        payload = build_dashboard_payload(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
            csv_path=self.csv_path,
            mode="paper",
            job_manager=StaticJobManager(
                [
                    {
                        "name": "paper-loop",
                        "kind": "paper-loop",
                        "pid": 1234,
                        "running": True,
                        "returncode": None,
                        "started_at": 1760000000.0,
                        "command": ["python", "-m", "upbit_auto_trader.main"],
                        "cwd": str(PROJECT_ROOT),
                        "log_path": "data/webui-jobs/paper-loop.log",
                        "log_tail": "still alive",
                        "heartbeat": {
                            "updated_at": "2026-03-23T00:00:00+00:00",
                            "phase": "loop",
                            "stale_after_seconds": 10,
                        },
                        "heartbeat_path": "data/webui-jobs/paper-loop.heartbeat.json",
                        "heartbeat_age_seconds": 120.0,
                        "heartbeat_status": "stale",
                        "heartbeat_healthy": False,
                        "last_report": None,
                    }
                ]
            ),
        )

        self.assertTrue(any(item["headline"] == "Job Heartbeat Stale" for item in payload["alerts"]["items"]))
        self.assertEqual(payload["job_health"]["summary"]["stale"], 1)
        self.assertEqual(payload["job_health"]["summary"]["requires_attention"], 1)
        self.assertEqual(payload["job_health"]["items"][0]["status"], "stale")

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
                "report_keep_latest": 12,
            },
            notes="paper main profile",
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
        self.assertEqual(loaded_profile["notes"], "paper main profile")
        self.assertEqual(loaded_profile["start_count"], 0)
        self.assertEqual(started["profile"]["name"], "test-ui-profile")
        self.assertEqual(started["profile"]["start_count"], 1)
        self.assertTrue(started["profile"]["last_started_at"])
        self.assertEqual(updated.strategy.buy_threshold, preset["strategy"]["buy_threshold"])
        self.assertTrue(started["job"]["auto_restart"])
        self.assertEqual(started["job"]["max_restarts"], 4)
        self.assertEqual(started["job"]["restart_backoff_seconds"], 1.5)
        self.assertEqual(loaded_profile["profile"]["report_keep_latest"], 12)
        self.assertIn("run-loop", started["job"]["command"])
        self.assertTrue(started["job"]["report_on_exit"])
        self.assertEqual(started["job"]["report_mode"], "paper")
        self.assertEqual(started["job"]["report_state_path"], str(self.state_path))
        self.assertEqual(started["job"]["report_keep_latest"], 12)

    def test_operator_profile_can_be_previewed(self):
        saved_profile = run_save_profile_action(
            config_path=str(self.temp_config_path),
            profile_name="test-ui-preview-profile",
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
                "preset": "",
                "auto_restart": True,
                "max_restarts": 2,
                "restart_backoff_seconds": 1.5,
                "report_keep_latest": 9,
            },
            notes="preview profile note",
        )

        preview = run_preview_profile_action(str(self.temp_config_path), saved_profile["path"])

        self.assertEqual(preview["profile"]["name"], "test-ui-preview-profile")
        self.assertEqual(preview["profile"]["notes"], "preview profile note")
        self.assertTrue(preview["job_preview"]["can_start"])
        self.assertIn("run-loop", preview["job_preview"]["command"])
        self.assertEqual(preview["job_preview"]["report_keep_latest"], 9)

    def test_operator_profile_can_be_deleted(self):
        saved_profile = run_save_profile_action(
            config_path=str(self.temp_config_path),
            profile_name="test-ui-delete-profile",
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
                "preset": "",
                "auto_restart": False,
                "max_restarts": 0,
                "restart_backoff_seconds": 0.0,
                "report_keep_latest": 5,
            },
        )

        deleted = run_delete_profile_action(str(self.temp_config_path), saved_profile["path"])

        self.assertEqual(deleted["name"], "test-ui-delete-profile")
        self.assertTrue(deleted["removed"])
        self.assertFalse(pathlib.Path(saved_profile["path"]).exists())

    def test_session_report_can_be_exported_and_loaded(self):
        exported = run_session_report_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            mode="paper",
            label="test-ui-report",
            output_dir=str(self.temp_reports_dir),
        )
        loaded = run_show_report_action(
            config_path=str(self.temp_config_path),
            report_ref=exported["json_path"],
            output_dir=str(self.temp_reports_dir),
        )

        self.assertTrue(pathlib.Path(exported["json_path"]).exists())
        self.assertTrue(pathlib.Path(exported["html_path"]).exists())
        self.assertEqual(loaded["json_path"], exported["json_path"])
        self.assertIn("recent_events", loaded)

    def test_session_report_action_applies_retention_policy(self):
        first = run_session_report_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            mode="paper",
            label="test-ui-retention-a",
            keep_latest=1,
            output_dir=str(self.temp_reports_dir),
        )
        second = run_session_report_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            mode="paper",
            label="test-ui-retention-b",
            keep_latest=1,
            output_dir=str(self.temp_reports_dir),
        )

        self.assertEqual(second["retention"]["keep"], 1)
        self.assertEqual(second["retention"]["removed_count"], 1)
        self.assertFalse(pathlib.Path(first["json_path"]).exists())
        self.assertFalse(pathlib.Path(first["html_path"]).exists())
        self.assertTrue(pathlib.Path(second["json_path"]).exists())

    def test_session_report_can_be_deleted(self):
        exported = run_session_report_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            mode="paper",
            label="test-ui-report-delete",
            output_dir=str(self.temp_reports_dir),
        )

        deleted = run_delete_report_action(
            config_path=str(self.temp_config_path),
            report_ref=exported["json_path"],
            output_dir=str(self.temp_reports_dir),
        )

        self.assertTrue(deleted["removed_json"])
        self.assertTrue(deleted["removed_html"])
        self.assertFalse(pathlib.Path(exported["json_path"]).exists())
        self.assertFalse(pathlib.Path(exported["html_path"]).exists())

    def test_session_reports_can_be_pruned(self):
        first = run_session_report_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            mode="paper",
            label="test-ui-prune-a",
            output_dir=str(self.temp_reports_dir),
        )
        second = run_session_report_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            mode="paper",
            label="test-ui-prune-b",
            output_dir=str(self.temp_reports_dir),
        )

        pruned = run_prune_reports_action(
            config_path=str(self.temp_config_path),
            keep=1,
            output_dir=str(self.temp_reports_dir),
        )

        self.assertEqual(pruned["keep"], 1)
        self.assertEqual(pruned["removed_count"], 1)
        self.assertFalse(pathlib.Path(first["json_path"]).exists())
        self.assertFalse(pathlib.Path(first["html_path"]).exists())
        self.assertTrue(pathlib.Path(second["json_path"]).exists())

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

    def test_doctor_action_returns_expected_keys(self):
        report = run_doctor_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
        )

        self.assertIn("ok", report)
        self.assertTrue(report["state"]["load_ok"])
        self.assertTrue(report["selector_state"]["exists"])

    def test_doctor_action_flags_placeholder_live_keys(self):
        with open(self.temp_config_path, "r", encoding="utf-8") as handle:
            temp_config = json.load(handle)
        temp_config["upbit"]["live_enabled"] = True
        temp_config["upbit"]["access_key"] = ""
        temp_config["upbit"]["secret_key"] = ""
        with open(self.temp_config_path, "w", encoding="utf-8") as handle:
            json.dump(temp_config, handle, indent=2)
            handle.write("\n")

        report = run_doctor_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
        )

        self.assertIn("access_key_missing", report["upbit"]["private_issues"])
        self.assertIn("secret_key_missing", report["upbit"]["private_issues"])

    def test_doctor_action_reports_stale_job_heartbeats(self):
        self.job_heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.job_heartbeat_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "updated_at": "2026-03-01T00:00:00+00:00",
                    "job_name": "test-ui-heartbeat",
                    "job_kind": "paper-loop",
                    "phase": "loop",
                    "stale_after_seconds": 10,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")

        report = run_doctor_action(
            config_path=str(self.temp_config_path),
            state_path=str(self.state_path),
            selector_state_path=str(self.selector_state_path),
        )

        self.assertEqual(report["managed_jobs"]["summary"]["stale"], 1)
        self.assertTrue(any(item["job_name"] == "test-ui-heartbeat" for item in report["managed_jobs"]["items"]))
        self.assertIn("job_heartbeat_stale:test-ui-heartbeat", report["issues"])

    def test_editable_config_can_be_loaded_and_saved(self):
        before = load_editable_config(str(self.temp_config_path))
        result = update_editable_config(
            str(self.temp_config_path),
            {
                "strategy.buy_threshold": 70.0,
                "strategy.sell_threshold": 42.0,
                "risk.max_position_fraction": 0.08,
                "runtime.max_trades_per_day": 3,
                "selector.include_markets": "KRW-BTC, KRW-ETH, KRW-SOL",
                "selector.max_markets": 7,
            },
        )
        after = load_editable_config(str(self.temp_config_path))

        self.assertNotEqual(before["strategy.buy_threshold"], after["strategy.buy_threshold"])
        self.assertEqual(result["current"]["strategy.buy_threshold"], 70.0)
        self.assertEqual(result["current"]["risk.max_position_fraction"], 0.08)
        self.assertEqual(result["current"]["runtime.max_trades_per_day"], 3)
        self.assertEqual(
            result["current"]["selector.include_markets"],
            ["KRW-BTC", "KRW-ETH", "KRW-SOL"],
        )
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
        with open(self.temp_config_path, "r", encoding="utf-8") as handle:
            temp_config = json.load(handle)
        temp_config["upbit"]["live_enabled"] = True
        temp_config["upbit"]["access_key"] = "test-access"
        temp_config["upbit"]["secret_key"] = "test-secret"
        with open(self.temp_config_path, "w", encoding="utf-8") as handle:
            json.dump(temp_config, handle, indent=2)
            handle.write("\n")

        selector_job = start_managed_job(
            config_path=str(self.temp_config_path),
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
        live_selector_job = start_managed_job(
            config_path=str(self.temp_config_path),
            job_type="live-selector",
            state_path=str(self.state_path),
            selector_state_path="data/test-selector-state.json",
            csv_path=self.csv_path,
            poll_seconds=6.0,
            reconcile_every_loops=3,
            reconcile_every=11,
            market="KRW-BTC",
            quote_currency="KRW",
            max_markets=5,
            auto_restart=True,
            max_restarts=3,
            restart_backoff_seconds=1.5,
            job_manager=manager,
        )
        supervisor_job = start_managed_job(
            config_path=str(self.temp_config_path),
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
        self.assertEqual(selector_job["report_keep_latest"], 20)
        self.assertIn("run-selector", live_selector_job["command"])
        self.assertIn("--mode", live_selector_job["command"])
        self.assertIn("live", live_selector_job["command"])
        self.assertIn("5", live_selector_job["command"])
        self.assertFalse(live_selector_job["report_on_exit"])
        self.assertEqual(live_selector_job["report_mode"], "live")
        self.assertIn("run-live-supervisor", supervisor_job["command"])
        self.assertIn("11", supervisor_job["command"])
        self.assertTrue(supervisor_job["report_on_exit"])
        self.assertEqual(supervisor_job["report_mode"], "live")

    @mock.patch("upbit_auto_trader.ui.build_doctor_report")
    def test_preview_managed_job_supports_live_selector(self, build_doctor_report_mock):
        with open(self.temp_config_path, "r", encoding="utf-8") as handle:
            temp_config = json.load(handle)
        temp_config["upbit"]["live_enabled"] = True
        temp_config["upbit"]["access_key"] = "test-access"
        temp_config["upbit"]["secret_key"] = "test-secret"
        with open(self.temp_config_path, "w", encoding="utf-8") as handle:
            json.dump(temp_config, handle, indent=2)
            handle.write("\n")
        build_doctor_report_mock.return_value = {
            "issues": [],
            "upbit": {"private_ready": True, "private_issues": []},
            "state": {"load_ok": True},
        }

        preview = preview_managed_job(
            config_path=str(self.temp_config_path),
            job_type="live-selector",
            state_path=str(self.state_path),
            selector_state_path="data/test-selector-state.json",
            csv_path=self.csv_path,
            poll_seconds=6.0,
            reconcile_every_loops=3,
            reconcile_every=11,
            market="KRW-BTC",
            quote_currency="KRW",
            max_markets=5,
            auto_restart=True,
            max_restarts=3,
            restart_backoff_seconds=1.5,
        )

        self.assertEqual(preview["job_type"], "live-selector")
        self.assertIn("run-selector", preview["command"])
        self.assertIn("live", preview["command"])
        self.assertTrue(preview["can_start"])
        self.assertFalse(preview["report_on_exit"])
        self.assertEqual(preview["report_mode"], "live")

    def test_start_managed_job_blocks_live_when_preflight_fails(self):
        manager = RecordingJobManager()

        started = start_managed_job(
            config_path=self.config_path,
            job_type="live-daemon",
            state_path=str(self.state_path),
            selector_state_path=None,
            csv_path=self.csv_path,
            poll_seconds=5.0,
            reconcile_every_loops=3,
            reconcile_every=None,
            market="KRW-BTC",
            quote_currency="KRW",
            max_markets=5,
            auto_restart=False,
            max_restarts=0,
            restart_backoff_seconds=0.0,
            job_manager=manager,
        )

        self.assertEqual(started["error"], "live_preflight_failed")
        self.assertIn("live_enabled=false", started["blocking_issues"])
        self.assertEqual(manager.calls, [])

    def test_preview_managed_job_returns_paper_command_without_starting(self):
        preview = preview_managed_job(
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
        )

        self.assertTrue(preview["can_start"])
        self.assertIn("run-loop", preview["command"])
        self.assertTrue(preview["report_state_path"].endswith("data\\paper-state-ui.json"))
        self.assertEqual(preview["report_keep_latest"], 20)
        self.assertTrue(preview["heartbeat_path"].endswith("data\\webui-jobs\\paper-loop.heartbeat.json"))

    def test_preview_managed_job_exposes_live_blocking_issues(self):
        preview = preview_managed_job(
            config_path=self.config_path,
            job_type="live-daemon",
            state_path=str(self.state_path),
            selector_state_path=None,
            csv_path=self.csv_path,
            poll_seconds=5.0,
            reconcile_every_loops=3,
            reconcile_every=None,
            market="KRW-BTC",
            quote_currency="KRW",
            max_markets=5,
            auto_restart=False,
            max_restarts=0,
            restart_backoff_seconds=0.0,
        )

        self.assertFalse(preview["can_start"])
        self.assertIn("live_enabled=false", preview["blocking_issues"])
        self.assertIsNotNone(preview["preflight"])

    def test_preview_managed_job_blocks_live_when_open_orders_scope_is_missing(self):
        with open(self.temp_config_path, "r", encoding="utf-8") as handle:
            temp_config = json.load(handle)
        temp_config["upbit"]["live_enabled"] = True
        temp_config["upbit"]["access_key"] = "real-access"
        temp_config["upbit"]["secret_key"] = "real-secret"
        with open(self.temp_config_path, "w", encoding="utf-8") as handle:
            json.dump(temp_config, handle, indent=2)
            handle.write("\n")

        class FakeScopedBroker:
            def __init__(self, upbit_config):
                self.config = upbit_config

            def readiness_report(self):
                return {
                    "public_ready": True,
                    "private_ready": True,
                    "public_issues": [],
                    "private_issues": [],
                    "request_timeout_seconds": 5.0,
                    "max_retries": 0,
                    "retry_backoff_seconds": 0.0,
                    "last_rate_limit": {},
                }

            def get_accounts(self):
                return []

            def get_order_chance(self, market):
                return {"market": market}

            def list_open_orders(self, market=None, states=None):
                raise UpbitError('upbit http error: 403 Forbidden {"error":{"name":"out_of_scope","message":"권한이 부족합니다."}}')

        with mock.patch("upbit_auto_trader.doctor.UpbitBroker", FakeScopedBroker):
            preview = preview_managed_job(
                config_path=str(self.temp_config_path),
                job_type="live-daemon",
                state_path=str(self.state_path),
                selector_state_path=None,
                csv_path=self.csv_path,
                poll_seconds=5.0,
                reconcile_every_loops=3,
                reconcile_every=None,
                market="KRW-BTC",
                quote_currency="KRW",
                max_markets=5,
                auto_restart=False,
                max_restarts=0,
                restart_backoff_seconds=0.0,
            )

        self.assertFalse(preview["can_start"])
        self.assertIn("open_orders_scope_missing", preview["blocking_issues"])
        self.assertEqual(preview["preflight"]["live_api_validation"]["items"][-1]["issue"], "open_orders_scope_missing")

    def test_preview_completion_workflow_returns_windows_wrapper_command(self):
        preview = preview_completion_workflow_action(
            config_path=self.config_path,
            stage="verify",
        )

        self.assertEqual(preview["job_type"], "completion-workflow")
        self.assertEqual(preview["stage"], "verify")
        self.assertEqual(preview["command"][:3], ["cmd.exe", "/c", "complete_remaining.cmd"])
        self.assertEqual(preview["command"][-1], "verify")
        self.assertTrue(preview["script_path"].endswith("complete_remaining.cmd"))
        self.assertTrue(preview["can_start"])

    def test_preview_completion_workflow_marks_all_safe_as_job_starting(self):
        preview = preview_completion_workflow_action(
            config_path=self.config_path,
            stage="all-safe",
        )

        self.assertIn("starts_managed_jobs", preview["warnings"])

    def test_preview_completion_workflow_supports_release_pack(self):
        preview = preview_completion_workflow_action(
            config_path=self.config_path,
            stage="release-pack",
        )

        self.assertEqual(preview["stage"], "release-pack")
        self.assertEqual(preview["command"][-1], "release-pack")
        self.assertEqual(preview["warnings"], [])

    def test_preview_completion_workflow_supports_release_verify(self):
        preview = preview_completion_workflow_action(
            config_path=self.config_path,
            stage="release-verify",
        )

        self.assertEqual(preview["stage"], "release-verify")
        self.assertEqual(preview["command"][-1], "release-verify")
        self.assertEqual(preview["warnings"], [])

    def test_start_completion_workflow_uses_job_manager(self):
        manager = RecordingJobManager()

        started = start_completion_workflow_action(
            config_path=self.config_path,
            stage="paper-preflight",
            job_manager=manager,
        )

        self.assertEqual(started["workflow"]["stage"], "paper-preflight")
        self.assertEqual(started["job"]["name"], "workflow-paper-preflight")
        self.assertEqual(started["job"]["kind"], "completion-workflow")
        self.assertEqual(started["job"]["command"][-1], "paper-preflight")
        self.assertFalse(started["job"]["report_on_exit"])

    def test_preview_completion_workflow_rejects_unknown_stage(self):
        preview = preview_completion_workflow_action(
            config_path=self.config_path,
            stage="live-start",
        )

        self.assertEqual(preview["error"], "unsupported_workflow_stage")
        self.assertIn("verify", preview["supported_stages"])

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

    def test_stop_all_managed_jobs_returns_manager_payload(self):
        manager = RecordingJobManager()
        manager.start_job(
            name="paper-loop",
            kind="paper-loop",
            command=["python", "-m", "upbit_auto_trader.main", "run-loop"],
        )
        manager.start_job(
            name="paper-selector",
            kind="paper-selector",
            command=["python", "-m", "upbit_auto_trader.main", "run-selector"],
        )

        stopped = stop_all_managed_jobs(job_manager=manager)

        self.assertEqual(manager.stop_all_calls, 1)
        self.assertEqual(stopped["requested"], 2)
        self.assertEqual(stopped["stopped"], 2)

    def test_cleanup_managed_jobs_returns_manager_payload(self):
        manager = RecordingJobManager()
        manager.start_job(
            name="paper-loop",
            kind="paper-loop",
            command=["python", "-m", "upbit_auto_trader.main", "run-loop"],
        )

        with mock.patch(
            "upbit_auto_trader.ui.cleanup_job_artifacts",
            return_value={
                "removed_jobs": 0,
                "removed_heartbeats": 0,
                "removed_logs": 0,
                "skipped_running": 0,
                "items": [],
            },
        ):
            cleaned = cleanup_managed_jobs(job_manager=manager, remove_logs=False)

        self.assertEqual(manager.cleanup_calls, [False])
        self.assertEqual(cleaned["removed_jobs"], 1)
        self.assertEqual(cleaned["removed_heartbeats"], 1)


if __name__ == "__main__":
    unittest.main()
