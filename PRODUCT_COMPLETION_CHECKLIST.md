# Product Completion Checklist

Current overall completion: `99%`

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

- [ ] Small live validation completed
  - Goal: verify tiny-size live order submit, fill, cancel, reconcile, and state recovery with real Upbit keys
  - Evidence to save: live report + support bundle + release pack status after the run
  - Current prep status: `2026-03-30` readiness captured, but live run is still blocked until real Upbit keys and a real operator-run micro-order are available
  - Current blockers: `live_enabled=false`, `access_key_missing`, `secret_key_missing`, `live_state_missing`
  - Prep evidence:
    `dist/live-validation/small-live-validation-readiness.json`
    `dist/upbit-control-room-support-live-preflight.zip`
    `SMALL_LIVE_VALIDATION_RUNBOOK.md`

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

- [ ] Default operating profile and preset frozen
  - Goal: choose the one paper profile and one strategy preset that become the default operational path
  - Evidence to save: profile name + preset name recorded in this file

- [ ] Final operator handoff pass completed
  - Goal: confirm the manual operating path is short and consistent
  - Minimum path: `setup -> launch -> doctor -> paper/live start -> status -> release pack -> support bundle`

## Optional Polish

- [ ] UI visual pass for a more Upbit-like look
- [ ] Optional Windows app packaging or `.exe` packaging

## Completion Rule

The product is considered complete when every item under `Required For Product Complete` is checked.
