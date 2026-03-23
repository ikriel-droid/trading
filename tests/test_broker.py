import base64
import io
import json
import pathlib
import sys
import unittest
from urllib import error
from unittest import mock


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.brokers.upbit import (  # noqa: E402
    UpbitBroker,
    UpbitConfigurationError,
    UpbitError,
    UpbitRateLimitError,
)
from upbit_auto_trader.config import UpbitConfig  # noqa: E402


def _decode_segment(token: str, index: int) -> dict:
    segment = token.split(".")[index]
    padded = segment + "=" * ((4 - len(segment) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


class FakeHttpResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return str(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class BrokerTests(unittest.TestCase):
    def build_broker(self) -> UpbitBroker:
        config = UpbitConfig(
            base_url="https://api.upbit.com/v1",
            market="KRW-BTC",
            access_key="access-key",
            secret_key="secret-key",
            candle_unit=15,
            candle_count=200,
            live_enabled=False,
        )
        return UpbitBroker(config)

    def build_live_broker(self) -> UpbitBroker:
        config = UpbitConfig(
            base_url="https://api.upbit.com/v1",
            market="KRW-BTC",
            access_key="access-key",
            secret_key="secret-key",
            candle_unit=15,
            candle_count=200,
            live_enabled=True,
        )
        return UpbitBroker(config)

    def test_readiness_for_preview_only_config(self) -> None:
        broker = self.build_broker()
        readiness = broker.readiness_report()
        self.assertTrue(readiness["public_ready"])
        self.assertFalse(readiness["private_ready"])
        self.assertIn("live_enabled=false", readiness["private_issues"])

    def test_order_preview_contains_jwt_with_query_hash(self) -> None:
        broker = self.build_broker()
        preview = broker.preview_order_request(
            market="KRW-BTC",
            side="bid",
            ord_type="price",
            price="100000",
        )

        self.assertEqual(preview["method"], "POST")
        self.assertEqual(preview["url"], "https://api.upbit.com/v1/orders")
        self.assertEqual(preview["body"]["ord_type"], "price")
        self.assertEqual(preview["headers"]["Content-Type"], "application/json; charset=utf-8")

        token = preview["headers"]["Authorization"].split(" ", 1)[1]
        header = _decode_segment(token, 0)
        payload = _decode_segment(token, 1)

        self.assertEqual(header["alg"], "HS256")
        self.assertEqual(payload["access_key"], "access-key")
        self.assertEqual(payload["query_hash_alg"], "SHA512")
        self.assertTrue(payload["query_hash"])

    def test_private_websocket_headers_use_bearer_token_without_query_hash(self) -> None:
        broker = self.build_broker()

        headers = broker.websocket_private_headers()
        token = headers["Authorization"].split(" ", 1)[1]
        payload = _decode_segment(token, 1)

        self.assertEqual(payload["access_key"], "access-key")
        self.assertIn("nonce", payload)
        self.assertNotIn("query_hash", payload)

    def test_list_open_orders_passes_states_array(self) -> None:
        broker = self.build_broker()
        calls = []

        def fake_private_request(method, path, params=None, body=None):
            calls.append({"method": method, "path": path, "params": params, "body": body})
            return [{"uuid": "order-1"}]

        broker._private_request = fake_private_request  # type: ignore[method-assign]

        payload = broker.list_open_orders(
            market="KRW-BTC",
            states=["wait", "watch"],
            page=2,
            limit=50,
            order_by="asc",
        )

        self.assertEqual(payload[0]["uuid"], "order-1")
        self.assertEqual(calls[0]["method"], "GET")
        self.assertEqual(calls[0]["path"], "/orders/open")
        self.assertEqual(calls[0]["params"]["states[]"], ["wait", "watch"])
        self.assertEqual(calls[0]["params"]["page"], 2)

    def test_cancel_order_requires_uuid_or_identifier(self) -> None:
        broker = self.build_live_broker()

        with self.assertRaises(UpbitConfigurationError):
            broker.cancel_order()

    def test_cancel_and_new_uses_prev_uuid(self) -> None:
        broker = self.build_live_broker()
        calls = []

        def fake_private_request(method, path, params=None, body=None):
            calls.append({"method": method, "path": path, "params": params, "body": body})
            return {"new_order_uuid": "order-2"}

        broker._private_request = fake_private_request  # type: ignore[method-assign]

        payload = broker.cancel_and_new(
            prev_order_uuid="order-1",
            new_ord_type="limit",
            new_volume="0.01",
            new_price="130000000",
            new_time_in_force="ioc",
        )

        self.assertEqual(payload["new_order_uuid"], "order-2")
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["path"], "/orders/cancel_and_new")
        self.assertEqual(calls[0]["body"]["prev_order_uuid"], "order-1")
        self.assertEqual(calls[0]["body"]["new_ord_type"], "limit")

    def test_public_get_retries_after_urlerror_then_succeeds(self) -> None:
        broker = self.build_broker()
        responses = [
            error.URLError("temporary network issue"),
            FakeHttpResponse(
                '[{"market":"KRW-BTC"}]',
                headers={"Remaining-Req": "group=default; min=1800; sec=29"},
            ),
        ]

        with mock.patch("upbit_auto_trader.brokers.upbit.time.sleep", return_value=None), mock.patch(
            "upbit_auto_trader.brokers.upbit.request.urlopen",
            side_effect=responses,
        ) as mocked:
            payload = broker.list_markets()

        self.assertEqual(payload[0]["market"], "KRW-BTC")
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(broker.last_rate_limit["sec"], 29)

    def test_private_get_retries_after_429_then_succeeds(self) -> None:
        broker = self.build_broker()
        first_error = error.HTTPError(
            url="https://api.upbit.com/v1/orders/chance",
            code=429,
            msg="Too Many Requests",
            hdrs={"Retry-After": "0", "Remaining-Req": "group=default; min=1800; sec=0"},
            fp=io.BytesIO(b'{"error":{"message":"too many requests"}}'),
        )
        second_response = FakeHttpResponse(
            '{"market":{"bid":{"min_total":"5000"},"ask":{"min_total":"5000"}}}',
            headers={"Remaining-Req": "group=default; min=1800; sec=28"},
        )

        with mock.patch("upbit_auto_trader.brokers.upbit.time.sleep", return_value=None), mock.patch(
            "upbit_auto_trader.brokers.upbit.request.urlopen",
            side_effect=[first_error, second_response],
        ) as mocked:
            payload = broker.get_order_chance("KRW-BTC")

        self.assertIn("market", payload)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(broker.last_rate_limit["sec"], 28)

    def test_rate_limit_error_is_raised_after_exhausted_get_retries(self) -> None:
        broker = self.build_broker()
        first_error = error.HTTPError(
            url="https://api.upbit.com/v1/orders/chance",
            code=429,
            msg="Too Many Requests",
            hdrs={"Retry-After": "0", "Remaining-Req": "group=default; min=1800; sec=0"},
            fp=io.BytesIO(b'{"error":{"message":"still limited"}}'),
        )

        with mock.patch("upbit_auto_trader.brokers.upbit.time.sleep", return_value=None), mock.patch(
            "upbit_auto_trader.brokers.upbit.request.urlopen",
            side_effect=[first_error, first_error, first_error],
        ):
            with self.assertRaises(UpbitRateLimitError):
                broker.get_order_chance("KRW-BTC")

    def test_create_order_does_not_retry_non_idempotent_request(self) -> None:
        broker = self.build_live_broker()

        with mock.patch("upbit_auto_trader.brokers.upbit.request.urlopen", side_effect=error.URLError("down")) as mocked:
            with self.assertRaises(UpbitError):
                broker.create_order(
                    market="KRW-BTC",
                    side="bid",
                    ord_type="price",
                    price="100000",
                )

        self.assertEqual(mocked.call_count, 1)


if __name__ == "__main__":
    unittest.main()
