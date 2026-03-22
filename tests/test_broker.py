import base64
import json
import pathlib
import sys
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from upbit_auto_trader.brokers.upbit import UpbitBroker, UpbitConfigurationError  # noqa: E402
from upbit_auto_trader.config import UpbitConfig  # noqa: E402


def _decode_segment(token: str, index: int) -> dict:
    segment = token.split(".")[index]
    padded = segment + "=" * ((4 - len(segment) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


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


if __name__ == "__main__":
    unittest.main()
