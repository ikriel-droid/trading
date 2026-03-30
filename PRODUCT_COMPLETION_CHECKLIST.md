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

- [ ] Long paper soak test completed
  - Goal: run paper loop or selector long enough to confirm restart, heartbeat, report, and recovery behavior stay stable
  - Evidence to save: latest session report + support bundle after the run

- [ ] Small live validation completed
  - Goal: verify tiny-size live order submit, fill, cancel, reconcile, and state recovery with real Upbit keys
  - Evidence to save: live report + support bundle + release pack status after the run

- [ ] Fresh environment deployment validated
  - Goal: prove setup, launch, status, release-status, release-pack, and support-bundle work on a clean machine or clean workspace
  - Evidence to save: release pack + support bundle from the clean run

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
