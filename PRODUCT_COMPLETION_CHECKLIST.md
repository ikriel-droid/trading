# Product Completion Checklist

Current overall completion: `100%`

This file is the product-finish checklist for the Upbit auto-trader.
From this point on, each completed finish task should update this file.

## Required For Product Complete

- [x] Core trading engine implemented
  - Strategy, indicators, risk, backtest, paper runtime

- [x] Upbit integration implemented
  - Public market data, private auth, order helpers, reconcile helpers

- [x] Live operation controls implemented
  - Live daemon, live supervisor, myOrder/myAsset handling, pending-order management

- [x] Control room UI implemented
  - Dashboard, jobs, profiles, presets, reports, release center, doctor, alerts

- [x] Packaging and operational tooling implemented
  - Completion workflow, release pack, support bundle, release status, manual launch scripts

- [x] Long paper soak test completed
  - Goal: run paper loop or selector long enough to confirm restart, heartbeat, report, and recovery behavior stay stable
  - Evidence to save: latest session report + support bundle after the run
  - Completed: `2026-03-30`
  - Evidence:
    `dist/paper-soak/long-paper-soak-evidence.json`
    `data/session-reports/session-report-20260330T1216323064170000-paper-soak-loop.json`
    `dist/upbit-control-room-support-paper-soak.zip`
  - Notes: `paper-soak-loop` auto-restarted after a forced process kill, heartbeat stayed healthy before and after restart, and `data/paper-state-soak.json.bak` was present for state recovery fallback

- [x] Small live validation completed
  - Goal: verify tiny-size live order submit, fill, cancel, reconcile, and state recovery with real Upbit keys
  - Evidence to save: live report + support bundle + release pack status after the run
  - Completed: `2026-03-31`
  - Evidence:
    `data/session-reports/session-report-20260331T1139511808490000-live-market-validation.json`
    `dist/upbit-control-room-support-live-validation.zip`
    `dist/live-validation/live-market-validation-release-status.json`
    `dist/live-validation/live-market-validation-summary.json`
  - Notes: one tiny `KRW-BTC` live market buy was submitted for `10,000 KRW`, partially-filled/canceled on the buy snapshot as expected by Upbit market-buy semantics, then immediately market-sold back out. Final reconcile confirmed `trade_count=1`, `position=null`, `pending_order=null`, `open-orders=[]`, and `release_artifacts.status=ready`.

- [x] Fresh environment deployment validated
  - Goal: prove setup, launch, status, release-status, release-pack, and support-bundle work on a clean machine or clean workspace
  - Evidence to save: release pack + support bundle from the clean run
  - Completed: `2026-03-31`
  - Evidence:
    `dist/fresh-environment-validation/fresh-environment-validation-summary.json`
    `dist/fresh-environment-validation/evidence/fresh-control-room-status.json`
    `dist/fresh-environment-validation/evidence/fresh-release-status.json`
    `dist/fresh-environment-validation/workspace/dist/clean-run-support.zip`
    `dist/fresh-environment-validation/workspace/dist/clean-run-release-pack.zip`
  - Notes: `validate_fresh_environment_deployment.cmd` extracted the generated bundle into a clean workspace, ran `setup_control_room`, created a paper state, launched the hidden control room on port `8876`, captured status, then built and verified both the clean-run support bundle and release pack

- [x] Default operating profile and preset frozen
  - Goal: choose the one paper profile and one strategy preset that become the default operational path
  - Evidence to save: profile name + preset name recorded in this file
  - Completed: `2026-03-31`
  - Default paper profile: `default-paper-selector-krw-auto`
    `data/operator-profiles/default-paper-selector-krw-auto.json`
  - Default strategy preset: `default-krw-auto-v1`
    `data/strategy-presets/default-krw-auto-v1.json`
  - Canonical defaults file:
    `data/operator-defaults.json`
  - Notes: default operation is now the `paper-selector` path that auto-selects KRW markets and applies the frozen `default-krw-auto-v1` strategy preset before start. Live remains manually gated until `Small live validation completed` is intentionally closed.

- [x] Final operator handoff pass completed
  - Goal: confirm the manual operating path is short and consistent
  - Minimum path: `setup -> launch -> doctor -> paper/live start -> status -> release pack -> support bundle`
  - Completed: `2026-03-31`
  - Evidence:
    `dist/operator-handoff/operator-handoff-summary.json`
    `dist/operator-handoff/evidence/control-room-status.json`
    `dist/operator-handoff/evidence/doctor.json`
    `dist/operator-handoff/evidence/profile-start.json`
    `dist/upbit-control-room-support-operator-handoff.zip`
    `dist/operator-handoff/operator-handoff-release-pack.zip`
    `dist/operator-handoff/release-pack/release-pack-verification.json`
  - Notes: validated `setup -> hidden launch -> doctor -> default paper profile start -> status -> release pack -> support bundle` using the frozen `default-paper-selector-krw-auto` profile and `default-krw-auto-v1` preset. `doctor` only surfaced expected paper-path warnings: `discord_webhook_not_configured` and `live_enabled=false`.

## Optional Polish

- [ ] UI visual pass for a more Upbit-like look
- [ ] Optional Windows app packaging or `.exe` packaging

## Completion Rule

The product is considered complete when every item under `Required For Product Complete` is checked.
