import json
from typing import Dict, Iterable, Iterator, List, Optional


def build_subscription(
    type_name: str,
    codes: List[str],
    is_only_realtime: bool = True,
) -> Dict[str, object]:
    return {
        "type": type_name,
        "codes": [code.upper() for code in codes],
        "is_only_realtime": is_only_realtime,
    }


def build_candle_subscription(
    unit: int,
    codes: List[str],
    ticket: str = "upbit-auto-trader",
    is_only_realtime: bool = True,
    fmt: str = "DEFAULT",
) -> List[Dict[str, object]]:
    return [
        {"ticket": ticket},
        build_subscription("candle.{0}m".format(unit), codes, is_only_realtime=is_only_realtime),
        {"format": fmt},
    ]


def build_ticker_subscription(
    codes: List[str],
    ticket: str = "upbit-auto-trader",
    is_only_realtime: bool = True,
    fmt: str = "DEFAULT",
) -> List[Dict[str, object]]:
    return [
        {"ticket": ticket},
        build_subscription("ticker", codes, is_only_realtime=is_only_realtime),
        {"format": fmt},
    ]


def build_trade_subscription(
    codes: List[str],
    ticket: str = "upbit-auto-trader",
    is_only_realtime: bool = True,
    fmt: str = "DEFAULT",
) -> List[Dict[str, object]]:
    return [
        {"ticket": ticket},
        build_subscription("trade", codes, is_only_realtime=is_only_realtime),
        {"format": fmt},
    ]


def build_selector_stream_subscription(
    unit: int,
    codes: List[str],
    ticket: str = "upbit-auto-trader",
    is_only_realtime: bool = True,
    fmt: str = "DEFAULT",
) -> List[Dict[str, object]]:
    return [
        {"ticket": ticket},
        build_subscription("ticker", codes, is_only_realtime=is_only_realtime),
        build_subscription("trade", codes, is_only_realtime=is_only_realtime),
        build_subscription("orderbook", codes, is_only_realtime=is_only_realtime),
        build_subscription("candle.{0}m".format(unit), codes, is_only_realtime=is_only_realtime),
        {"format": fmt},
    ]


def build_myorder_subscription(
    codes: Optional[List[str]] = None,
    ticket: str = "upbit-auto-trader-myorder",
    fmt: str = "DEFAULT",
) -> List[Dict[str, object]]:
    payload = [{"ticket": ticket}, {"type": "myOrder"}]
    if codes is not None:
        payload[1]["codes"] = [code.upper() for code in codes]
    payload.append({"format": fmt})
    return payload


def build_myasset_subscription(
    ticket: str = "upbit-auto-trader-myasset",
    fmt: str = "DEFAULT",
) -> List[Dict[str, object]]:
    return [{"ticket": ticket}, {"type": "myAsset"}, {"format": fmt}]


def build_private_account_subscription(
    codes: Optional[List[str]] = None,
    ticket: str = "upbit-auto-trader-private",
    fmt: str = "DEFAULT",
) -> List[Dict[str, object]]:
    payload = [{"ticket": ticket}, {"type": "myOrder"}, {"type": "myAsset"}, {"format": fmt}]
    if codes is not None:
        payload[1]["codes"] = [code.upper() for code in codes]
    return payload


class UpbitWebSocketClient:
    def __init__(
        self,
        url: str = "wss://api.upbit.com/websocket/v1",
        private_url: str = "wss://api.upbit.com/websocket/v1/private",
    ) -> None:
        self.url = url
        self.private_url = private_url

    def iter_messages(
        self,
        subscription: List[Dict[str, object]],
        max_messages: Optional[int] = None,
        message_source: Optional[Iterable[dict]] = None,
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Iterator[dict]:
        if message_source is not None:
            yield from self._iter_message_source(message_source, max_messages=max_messages)
            return

        websocket = self._import_websocket_module()
        ws = websocket.create_connection(
            url or self.url,
            timeout=30,
            header=self._format_headers(headers),
        )
        try:
            ws.send(json.dumps(subscription))
            count = 0
            while True:
                raw = ws.recv()
                if not raw:
                    continue
                payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
                yield payload
                count += 1
                if max_messages is not None and count >= max_messages:
                    return
        finally:
            ws.close()

    def iter_private_messages(
        self,
        subscription: List[Dict[str, object]],
        headers: Dict[str, str],
        max_messages: Optional[int] = None,
        message_source: Optional[Iterable[dict]] = None,
    ) -> Iterator[dict]:
        yield from self.iter_messages(
            subscription=subscription,
            max_messages=max_messages,
            message_source=message_source,
            url=self.private_url,
            headers=headers,
        )

    def _iter_message_source(self, message_source: Iterable[dict], max_messages: Optional[int]) -> Iterator[dict]:
        count = 0
        for payload in message_source:
            yield payload
            count += 1
            if max_messages is not None and count >= max_messages:
                return

    def _import_websocket_module(self):
        try:
            import websocket  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "websocket-client package is required for streaming mode; run pip install -e . again"
            ) from exc
        return websocket

    def _format_headers(self, headers: Optional[Dict[str, str]]) -> Optional[List[str]]:
        if not headers:
            return None
        return ["{0}: {1}".format(key, value) for key, value in headers.items()]
