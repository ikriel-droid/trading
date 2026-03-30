from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from upbit_auto_trader.brokers.upbit import UpbitBroker  # noqa: E402
from upbit_auto_trader.config import load_config  # noqa: E402
from upbit_auto_trader.datafeed import load_csv_candles  # noqa: E402
from upbit_auto_trader.runtime import TradingRuntime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the live state used for small live validation.")
    parser.add_argument("--config", default="config.live.micro.json")
    parser.add_argument("--state", default="data/live-state.json")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--market")
    args = parser.parse_args()

    config_path = (PROJECT_ROOT / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    state_path = (PROJECT_ROOT / args.state).resolve() if not Path(args.state).is_absolute() else Path(args.state)
    csv_path = (PROJECT_ROOT / args.csv).resolve() if not Path(args.csv).is_absolute() else Path(args.csv)

    if not config_path.exists():
        raise SystemExit("config file not found: {0}".format(config_path))
    if not csv_path.exists():
        raise SystemExit("csv file not found: {0}".format(csv_path))

    config = load_config(str(config_path))
    if args.market:
        config = copy.deepcopy(config)
        config.market = args.market
        config.upbit.market = args.market

    candles = load_csv_candles(str(csv_path))
    broker = UpbitBroker(config.upbit)
    runtime = TradingRuntime(config=config, mode="live", state_path=str(state_path), broker=broker)
    state = runtime.bootstrap(candles)

    print(
        json.dumps(
            {
                "market": config.market,
                "state_path": str(state_path),
                "csv_path": str(csv_path),
                "history_count": len(state.history),
                "last_processed_timestamp": state.last_processed_timestamp,
                "summary": runtime.summary(),
                "hint": "If bootstrap fails, check live_enabled, API keys, and whether you already hold the base asset for this market.",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
