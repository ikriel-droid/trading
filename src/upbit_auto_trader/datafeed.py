import csv
import os
from typing import Iterable, List

from .models import Candle


def load_csv_candles(path: str) -> List[Candle]:
    candles = []
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            candles.append(
                Candle(
                    timestamp=row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
    return candles


def write_csv_candles(path: str, candles: Iterable[Candle]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for candle in candles:
            writer.writerow(
                {
                    "timestamp": candle.timestamp,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
            )


def upbit_candles_to_internal(payload: List[dict]) -> List[Candle]:
    candles = []
    for item in reversed(payload):
        candles.append(
            Candle(
                timestamp=item["candle_date_time_kst"],
                open=float(item["opening_price"]),
                high=float(item["high_price"]),
                low=float(item["low_price"]),
                close=float(item["trade_price"]),
                volume=float(item["candle_acc_trade_volume"]),
            )
        )
    return candles


def upbit_websocket_candle_to_internal(payload: dict) -> Candle:
    return Candle(
        timestamp=payload["candle_date_time_kst"],
        open=float(payload["opening_price"]),
        high=float(payload["high_price"]),
        low=float(payload["low_price"]),
        close=float(payload["trade_price"]),
        volume=float(payload["candle_acc_trade_volume"]),
    )


def merge_candles(existing: List[Candle], incoming: List[Candle], max_history: int) -> List[Candle]:
    by_timestamp = {candle.timestamp: candle for candle in existing}
    for candle in incoming:
        by_timestamp[candle.timestamp] = candle
    merged = [by_timestamp[key] for key in sorted(by_timestamp.keys())]
    return merged[-max_history:]
