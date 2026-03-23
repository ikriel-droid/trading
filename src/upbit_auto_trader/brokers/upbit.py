import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional
from urllib import error, parse, request

from ..config import UpbitConfig
from ..models import Balance


class UpbitError(Exception):
    pass


class UpbitConfigurationError(UpbitError):
    pass


class LiveTradingDisabledError(UpbitError):
    pass


class UpbitRateLimitError(UpbitError):
    pass


class UpbitBroker:
    def __init__(self, config: UpbitConfig) -> None:
        self.config = config
        self.last_rate_limit: Dict[str, Any] = {}

    def readiness_report(self) -> Dict[str, Any]:
        public_issues = []
        private_issues = []

        if not self.config.base_url:
            public_issues.append("base_url_missing")
        if not self.config.market:
            public_issues.append("market_missing")
        if not self.config.access_key:
            private_issues.append("access_key_missing")
        if not self.config.secret_key:
            private_issues.append("secret_key_missing")
        if not self.config.live_enabled:
            private_issues.append("live_enabled=false")

        return {
            "public_ready": len(public_issues) == 0,
            "private_ready": len(public_issues) == 0 and len(private_issues) == 0,
            "public_issues": public_issues,
            "private_issues": private_issues,
            "request_timeout_seconds": self.config.request_timeout_seconds,
            "max_retries": self.config.max_retries,
            "retry_backoff_seconds": self.config.retry_backoff_seconds,
            "last_rate_limit": self.last_rate_limit,
        }

    def list_markets(self, is_details: bool = True) -> List[dict]:
        params = {"is_details": str(is_details).lower()}
        return self._public_request("GET", "/market/all", params=params)

    def get_ticker(self, markets: Iterable[str]) -> List[dict]:
        params = {"markets": ",".join(markets)}
        return self._public_request("GET", "/ticker", params=params)

    def get_minute_candles(
        self,
        market: str,
        unit: int,
        count: int = 200,
        to: Optional[str] = None,
    ) -> List[dict]:
        params = {"market": market, "count": count}
        if to:
            params["to"] = to
        return self._public_request("GET", "/candles/minutes/{0}".format(unit), params=params)

    def get_accounts(self) -> List[Balance]:
        payload = self._private_request("GET", "/accounts")
        balances = []
        for item in payload:
            balances.append(
                Balance(
                    currency=item["currency"],
                    balance=float(item["balance"]),
                    locked=float(item["locked"]),
                    avg_buy_price=float(item["avg_buy_price"]),
                    unit_currency=item["unit_currency"],
                )
            )
        return balances

    def get_order_chance(self, market: str) -> Dict[str, Any]:
        return self._private_request("GET", "/orders/chance", params={"market": market})

    def get_order(self, uuid: Optional[str] = None, identifier: Optional[str] = None) -> Dict[str, Any]:
        params = self._require_uuid_or_identifier(uuid=uuid, identifier=identifier)
        return self._private_request("GET", "/order", params=params)

    def list_open_orders(
        self,
        market: Optional[str] = None,
        state: Optional[str] = None,
        states: Optional[List[str]] = None,
        page: Optional[int] = None,
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> List[dict]:
        params: Dict[str, Any] = {}
        if market is not None:
            params["market"] = market
        if state is not None:
            params["state"] = state
        if states:
            params["states[]"] = states
        if page is not None:
            params["page"] = page
        if limit is not None:
            params["limit"] = limit
        if order_by is not None:
            params["order_by"] = order_by
        return self._private_request("GET", "/orders/open", params=params or None)

    def create_order(
        self,
        market: str,
        side: str,
        ord_type: str,
        volume: Optional[str] = None,
        price: Optional[str] = None,
        time_in_force: Optional[str] = None,
        identifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate_live_trading_enabled()
        body = {"market": market, "side": side, "ord_type": ord_type}
        if volume is not None:
            body["volume"] = volume
        if price is not None:
            body["price"] = price
        if time_in_force is not None:
            body["time_in_force"] = time_in_force
        if identifier is not None:
            body["identifier"] = identifier
        return self._private_request("POST", "/orders", body=body)

    def cancel_order(self, uuid: Optional[str] = None, identifier: Optional[str] = None) -> Dict[str, Any]:
        self._validate_live_trading_enabled()
        params = self._require_uuid_or_identifier(uuid=uuid, identifier=identifier)
        return self._private_request("DELETE", "/order", params=params)

    def cancel_orders(
        self,
        uuids: Optional[List[str]] = None,
        identifiers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self._validate_live_trading_enabled()
        params: Dict[str, Any] = {}
        if uuids:
            params["uuids[]"] = uuids
        if identifiers:
            params["identifiers[]"] = identifiers
        if not params or ("uuids[]" in params and "identifiers[]" in params):
            raise UpbitConfigurationError("provide exactly one of uuids or identifiers")
        return self._private_request("DELETE", "/orders/uuids", params=params)

    def cancel_open_orders(
        self,
        cancel_side: str = "all",
        pairs: Optional[str] = None,
        excluded_pairs: Optional[str] = None,
        count: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate_live_trading_enabled()
        params: Dict[str, Any] = {"cancel_side": cancel_side}
        if pairs is not None:
            params["pairs"] = pairs
        if excluded_pairs is not None:
            params["excluded_pairs"] = excluded_pairs
        if count is not None:
            params["count"] = count
        if order_by is not None:
            params["order_by"] = order_by
        return self._private_request("DELETE", "/orders/open", params=params)

    def cancel_and_new(
        self,
        new_ord_type: str,
        prev_order_uuid: Optional[str] = None,
        prev_order_identifier: Optional[str] = None,
        new_volume: Optional[str] = None,
        new_price: Optional[str] = None,
        new_time_in_force: Optional[str] = None,
        new_smp_type: Optional[str] = None,
        new_identifier: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate_live_trading_enabled()
        body = self._require_prev_uuid_or_identifier(
            prev_order_uuid=prev_order_uuid,
            prev_order_identifier=prev_order_identifier,
        )
        body["new_ord_type"] = new_ord_type
        if new_volume is not None:
            body["new_volume"] = new_volume
        if new_price is not None:
            body["new_price"] = new_price
        if new_time_in_force is not None:
            body["new_time_in_force"] = new_time_in_force
        if new_smp_type is not None:
            body["new_smp_type"] = new_smp_type
        if new_identifier is not None:
            body["new_identifier"] = new_identifier
        return self._private_request("POST", "/orders/cancel_and_new", body=body)

    def preview_order_request(
        self,
        market: str,
        side: str,
        ord_type: str,
        volume: Optional[str] = None,
        price: Optional[str] = None,
    ) -> Dict[str, Any]:
        body = {"market": market, "side": side, "ord_type": ord_type}
        if volume is not None:
            body["volume"] = volume
        if price is not None:
            body["price"] = price
        token = self._create_jwt_token(body)
        return {
            "method": "POST",
            "url": self._build_url("/orders"),
            "headers": {
                "Authorization": self.build_authorization_header(body),
                "Content-Type": "application/json; charset=utf-8",
            },
            "body": body,
        }

    def build_authorization_header(self, payload_source: Optional[Dict[str, Any]] = None) -> str:
        return "Bearer {0}".format(self._create_jwt_token(payload_source))

    def websocket_private_headers(self) -> Dict[str, str]:
        if not self.config.access_key or not self.config.secret_key:
            raise UpbitConfigurationError("access_key and secret_key are required")
        return {"Authorization": self.build_authorization_header(None)}

    def _public_request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request(method=method, path=path, params=params, body=None, authenticated=False)

    def _private_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not self.config.access_key or not self.config.secret_key:
            raise UpbitConfigurationError("access_key and secret_key are required")
        return self._request(method=method, path=path, params=params, body=body, authenticated=True)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]],
        body: Optional[Dict[str, Any]],
        authenticated: bool,
    ) -> Any:
        method = method.upper()
        query_string = self._build_query_string(params or body)
        url = self._build_url(path)

        if params:
            url += "?" + query_string

        headers = {"Accept": "application/json"}
        raw_body = None

        if body is not None:
            raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        if authenticated:
            headers["Authorization"] = self.build_authorization_header(params or body)

        req = request.Request(url=url, data=raw_body, method=method, headers=headers)
        retryable = self._is_retryable_request(method=method, body=body)
        max_attempts = 1 + max(0, int(self.config.max_retries))

        for attempt in range(max_attempts):
            try:
                with request.urlopen(req, timeout=self.config.request_timeout_seconds) as response:
                    self.last_rate_limit = self._parse_remaining_req(response.headers)
                    raw = response.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                headers = getattr(exc, "headers", {}) or {}
                self.last_rate_limit = self._parse_remaining_req(headers)
                is_rate_limited = exc.code == 429
                can_retry = retryable and self._is_retryable_status(exc.code) and attempt < (max_attempts - 1)
                if can_retry:
                    time.sleep(self._retry_delay(attempt, headers))
                    continue
                if is_rate_limited:
                    raise UpbitRateLimitError(
                        "upbit rate limited: retry_after={0} detail={1}".format(
                            self._retry_after(headers),
                            detail or exc.reason,
                        )
                    )
                raise UpbitError("upbit http error: {0} {1} {2}".format(exc.code, exc.reason, detail))
            except error.URLError as exc:
                if retryable and attempt < (max_attempts - 1):
                    time.sleep(self._retry_delay(attempt, None))
                    continue
                raise UpbitError("upbit url error: {0}".format(exc.reason))

    def _build_url(self, path: str) -> str:
        if not self.config.base_url:
            raise UpbitConfigurationError("base_url is required")
        return self.config.base_url.rstrip("/") + path

    def _create_jwt_token(self, payload_source: Optional[Dict[str, Any]]) -> str:
        if not self.config.access_key or not self.config.secret_key:
            raise UpbitConfigurationError("access_key and secret_key are required")

        payload = {
            "access_key": self.config.access_key,
            "nonce": str(uuid.uuid4()),
        }
        if payload_source:
            query_string = self._build_query_string(payload_source)
            query_hash = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
            payload["query_hash"] = query_hash
            payload["query_hash_alg"] = "SHA512"

        header = {"alg": "HS256", "typ": "JWT"}
        header_segment = self._base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        payload_segment = self._base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = "{0}.{1}".format(header_segment, payload_segment)
        signature = hmac.new(
            self.config.secret_key.encode("utf-8"),
            signing_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return "{0}.{1}".format(signing_input, self._base64url_encode(signature))

    def _build_query_string(self, payload: Optional[Dict[str, Any]]) -> str:
        if not payload:
            return ""

        items = []
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, list):
                list_key = key if key.endswith("[]") else key + "[]"
                for item in value:
                    items.append((list_key, str(item)))
            else:
                items.append((key, str(value)))
        return parse.urlencode(items, doseq=False, safe="[],:")

    def _base64url_encode(self, value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def _is_retryable_request(self, method: str, body: Optional[Dict[str, Any]]) -> bool:
        return method.upper() == "GET" and body is None

    def _is_retryable_status(self, status_code: int) -> bool:
        return status_code in (429, 500, 502, 503, 504)

    def _retry_delay(self, attempt: int, headers: Optional[Any]) -> float:
        retry_after = self._retry_after(headers or {})
        if retry_after is not None:
            return max(0.0, retry_after)
        base = max(0.0, float(self.config.retry_backoff_seconds))
        return base * (2**attempt)

    def _retry_after(self, headers: Any) -> Optional[float]:
        value = ""
        if hasattr(headers, "get"):
            value = str(headers.get("Retry-After", "")).strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _parse_remaining_req(self, headers: Any) -> Dict[str, Any]:
        if not hasattr(headers, "get"):
            return {}

        raw_value = str(headers.get("Remaining-Req", "")).strip()
        if not raw_value:
            return {}

        parsed: Dict[str, Any] = {"raw": raw_value}
        for segment in raw_value.split(";"):
            part = segment.strip()
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in ("min", "sec"):
                try:
                    parsed[key] = int(value)
                except ValueError:
                    parsed[key] = value
            else:
                parsed[key] = value
        return parsed

    def _validate_live_trading_enabled(self) -> None:
        if not self.config.live_enabled:
            raise LiveTradingDisabledError("live trading is disabled in config")

    def _require_uuid_or_identifier(self, uuid: Optional[str], identifier: Optional[str]) -> Dict[str, str]:
        if uuid:
            return {"uuid": uuid}
        if identifier:
            return {"identifier": identifier}
        raise UpbitConfigurationError("uuid or identifier is required")

    def _require_prev_uuid_or_identifier(
        self,
        prev_order_uuid: Optional[str],
        prev_order_identifier: Optional[str],
    ) -> Dict[str, str]:
        if prev_order_uuid:
            return {"prev_order_uuid": prev_order_uuid}
        if prev_order_identifier:
            return {"prev_order_identifier": prev_order_identifier}
        raise UpbitConfigurationError("prev_order_uuid or prev_order_identifier is required")
