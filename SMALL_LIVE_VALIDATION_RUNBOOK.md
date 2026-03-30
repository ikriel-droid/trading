# Small Live Validation Runbook

This runbook is the manual operator path for completing the checklist item:
`Small live validation completed`

The goal is to verify all of the following with a tiny real-money order on Upbit:

1. live order submit
2. fill or cancel behavior
3. reconcile
4. state persistence
5. state recovery after restart

## Before You Start

Run the readiness capture first:

```powershell
.\prepare_small_live_validation.cmd
```

If you already created a live config and only want the simplest prep path, run this instead:

```powershell
.\bootstrap_small_live_validation.cmd -ConfigPath config.live.micro.json -Market KRW-BTC
```

That single command refreshes candles, creates or syncs `data/live-state.json`, and rebuilds the readiness snapshot.

Read the generated evidence snapshot here:

`dist/live-validation/small-live-validation-readiness.json`

That file tells you whether the environment is still blocked by:

- missing Upbit API keys
- `upbit.live_enabled=false`
- missing or unreadable `data/live-state.json`
- release pack state

## Manual Validation Path

1. Put real `UPBIT_ACCESS_KEY` and `UPBIT_SECRET_KEY` in `.env`.
2. Enable live mode in the active config that you actually plan to use.
3. Run:

```powershell
.\complete_remaining.cmd live-preflight
```

4. Confirm the live profile preview is unblocked:

```powershell
.\.venv\Scripts\python.exe -m upbit_auto_trader.main profile-preview --config config.example.json --profile autofinish-live-main
```

5. Start the live process manually from the control room or CLI.
6. Submit one tiny live order only after checking market, size, and risk by hand.
7. Confirm one of these paths:
   - order fills and updates state
   - order remains open, then cancel it and confirm the cancel path
8. Run live reconcile and confirm account state matches runtime state:

```powershell
.\.venv\Scripts\python.exe -m upbit_auto_trader.main live-reconcile --config config.example.json --state data\live-state.json --market KRW-BTC
```

9. Stop the live process and restart it once to confirm state recovery.
10. Export the final evidence:

```powershell
.\.venv\Scripts\python.exe -m upbit_auto_trader.main session-report --config config.example.json --state data\live-state.json --mode live --label live-micro-validation --keep-latest 20
.\build_control_room_support_bundle.cmd -StatePath data\live-state.json -CreateZip -ZipPath dist\upbit-control-room-support-live-validation.zip
.\.venv\Scripts\python.exe -m upbit_auto_trader.main release-status --config config.example.json
```

## Completion Evidence

Do not check the checklist item until all three are saved:

- final live session report path
- support bundle zip path
- release status or release pack verification state after the run

After the live run is complete, record those paths under:

`PRODUCT_COMPLETION_CHECKLIST.md`
