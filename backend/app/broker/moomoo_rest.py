"""Read-only Moomoo REST transport for simulated accounts.

The client exposes GET reads plus two documented POST quote reads. Order
submission is intentionally absent.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.broker.account_lock import AccountLock, AccountLockError, BrokerAccount
from app.models.contracts import (
    AccountSnapshot,
    OpenOrder,
    OrderSide,
    OrderStatus,
    Position,
)

REST_BASE_URL = "https://webapi.moomoo.com"
COMPETITION_ACCOUNT_TITLE = "Moomoo x Qoder AI Paper Trading Agent Challenge"
MAX_HISTORY_PAGES = 10
HISTORY_PAGE_SIZE = 100
MAX_OBSERVATION_LATENCY = 15

_READ_PATH = re.compile(
    r"/api/v1\.0/(?:"
    r"sim-trade/(?:accounts|[A-Za-z0-9_-]+/(?:cash-info|positions|orders|history-orders))"
    r"|quote/trading-days"
    r"|quote/(?:US|HK|SH|SZ|BJ|SG|CA|AU|FX|JP|KR|CC|FT)\.[A-Za-z0-9_.-]+/(?:history-kline|kline-shape|indicator-polarity)"
    r")"
)
_POST_READ_PATHS = frozenset(
    {
        "/api/v1.0/quote/stock-quote",
        "/api/v1.0/quote/market-state",
    }
)
_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_OPEN_STATUSES = {1, 2, 3}
_TERMINAL_STATUSES = {4, 5, 6, 7}
_STATUS_LABELS = {
    1: "PENDING_NEW",
    2: "SUBMITTED",
    3: "PARTIALLY_FILLED",
    4: "FILLED",
    5: "CANCELLED",
    6: "REJECTED",
    7: "PARTIALLY_FILLED_THEN_CANCELLED",
}
_SIDE_MAP = {1: OrderSide.BUY, 2: OrderSide.SELL}


class MoomooRestError(RuntimeError):
    pass


class MoomooRestPermissionError(MoomooRestError):
    pass


class MoomooRestRateLimitError(MoomooRestError):
    pass


class MoomooRestReadOnlyError(MoomooRestError):
    pass


class MoomooResponseError(MoomooRestError):
    pass


class _TokenProvider(Protocol):
    def access_token(self) -> str: ...

    def refresh(self) -> object: ...


@dataclass(frozen=True)
class RestAccountIdentity:
    masked_id: str
    market_id: int
    account_type: int
    title: str


@dataclass(frozen=True)
class RestOrder:
    broker_order_id: str
    symbol: str
    side: OrderSide
    status_code: int
    status_label: str
    quantity: int
    filled_quantity: int
    price: Decimal
    average_fill_price: Decimal
    created_at_utc: datetime
    updated_at_utc: datetime
    order_type: int
    time_in_force: int | None
    trading_session: int | None
    remark: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker_order_id": self.broker_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "status_code": self.status_code,
            "status": self.status_label,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "price": str(self.price),
            "average_fill_price": str(self.average_fill_price),
            "created_at_utc": self.created_at_utc.isoformat(),
            "updated_at_utc": self.updated_at_utc.isoformat(),
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
            "trading_session": self.trading_session,
            "remark": self.remark,
        }


@dataclass(frozen=True)
class _ResolvedAccount:
    account: BrokerAccount
    account_type: int
    title: str


class MoomooRestClient:
    def __init__(
        self,
        auth: _TokenProvider,
        *,
        http: httpx.Client | None = None,
        base_url: str = REST_BASE_URL,
    ) -> None:
        if base_url.rstrip("/") != REST_BASE_URL:
            raise ValueError("Moomoo REST base URL is fixed to the official endpoint")
        self._auth = auth
        self._http = http or httpx.Client(timeout=20, trust_env=False)
        self._base_url = base_url.rstrip("/")

    def get(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> Mapping[str, Any]:
        if not _READ_PATH.fullmatch(path):
            raise MoomooRestReadOnlyError("REST path is not an allowlisted read endpoint")
        return self._request("GET", path, params=params, body=None, allow_refresh=True)

    def post_read(self, path: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        """POST only the documented quote reads; order paths are always refused."""
        if path not in _POST_READ_PATHS:
            raise MoomooRestReadOnlyError("REST path is not an allowlisted read endpoint")
        if not isinstance(body, Mapping):
            raise ValueError("REST request body must be an object")
        return self._request("POST", path, params=None, body=body, allow_refresh=True)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None,
        body: Mapping[str, Any] | None,
        allow_refresh: bool,
    ) -> Mapping[str, Any]:
        token = self._auth.access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            if method == "GET":
                response = self._http.get(
                    f"{self._base_url}{path}", headers=headers, params=params
                )
            else:
                response = self._http.post(
                    f"{self._base_url}{path}", headers=headers, json=dict(body or {})
                )
        except httpx.HTTPError as exc:
            raise MoomooRestError(
                f"Moomoo REST request failed ({type(exc).__name__})"
            ) from None

        payload = _maybe_json(response)
        if response.status_code in {401, 403}:
            if allow_refresh:
                self._auth.refresh()
                return self._request(
                    method, path, params=params, body=body, allow_refresh=False
                )
            raise MoomooRestError(
                f"Moomoo REST authentication failed (HTTP {response.status_code})"
            )
        if response.status_code == 439:
            raise MoomooRestPermissionError("Moomoo REST permission denied (HTTP 439)")
        if response.status_code == 429:
            raise MoomooRestRateLimitError("Moomoo REST rate limited (HTTP 429)")
        if response.status_code != 200:
            raise MoomooRestError(f"Moomoo REST request failed (HTTP {response.status_code})")
        if payload is None:
            raise MoomooRestError("Moomoo REST returned invalid JSON")
        ret_code = payload.get("ret_code")
        if isinstance(ret_code, bool) or not isinstance(ret_code, int):
            raise MoomooRestError("Moomoo REST response has no integer ret_code")
        if ret_code in {-12102, -12006} and allow_refresh:
            self._auth.refresh()
            return self._request(
                method, path, params=params, body=body, allow_refresh=False
            )
        if ret_code != 0:
            raise MoomooRestError(f"Moomoo REST business error (ret_code={ret_code})")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise MoomooRestError("Moomoo REST response has no data object")
        return payload


def _maybe_json(response: httpx.Response) -> Mapping[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, Mapping) else None


def _require_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise MoomooResponseError(f"Moomoo response field {key} is not an object")
    return item


def _require_list(value: Mapping[str, Any], key: str) -> list[Any]:
    item = value.get(key)
    if not isinstance(item, list):
        raise MoomooResponseError(f"Moomoo response field {key} is not a list")
    return item


def _require_str(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise MoomooResponseError(f"Moomoo response field {key} is not a non-empty string")
    return item.strip()


def _require_int(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise MoomooResponseError(f"Moomoo response field {key} is not an integer")
    return item


def _optional_int(value: Mapping[str, Any], key: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int):
        raise MoomooResponseError(f"Moomoo response field {key} is not an integer")
    return item


def _decimal(value: Mapping[str, Any], key: str) -> Decimal:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, (str, int)):
        raise MoomooResponseError(f"Moomoo response field {key} is not numeric")
    try:
        number = Decimal(str(item))
    except InvalidOperation:
        raise MoomooResponseError(f"Moomoo response field {key} is not numeric") from None
    if not number.is_finite():
        raise MoomooResponseError(f"Moomoo response field {key} is not finite")
    return number


def _integral(value: Mapping[str, Any], key: str) -> int:
    number = _decimal(value, key)
    if number != number.to_integral_value() or number < 0:
        raise MoomooResponseError(f"Moomoo response field {key} is not a non-negative integer")
    return int(number)


def _timestamp(value: Mapping[str, Any], key: str, now: datetime) -> datetime:
    raw = _require_str(value, key)
    if not raw.isdigit():
        raise MoomooResponseError(f"Moomoo response field {key} is not a microsecond timestamp")
    microseconds = int(raw)
    if microseconds <= 0:
        raise MoomooResponseError(f"Moomoo response field {key} is not positive")
    result = datetime.fromtimestamp(microseconds / 1_000_000, tz=UTC)
    if result > now + timedelta(minutes=5):
        raise MoomooResponseError(f"Moomoo response field {key} is in the future")
    return result


def _symbol(value: Mapping[str, Any]) -> str:
    raw = _require_str(value, "symbol").upper()
    if raw.startswith("US."):
        raw = raw[3:]
    if not _SYMBOL.fullmatch(raw):
        raise MoomooResponseError("Moomoo response symbol is not an approved US stock symbol")
    return raw


def _remark(value: Mapping[str, Any]) -> str:
    item = value.get("text")
    if not isinstance(item, str):
        raise MoomooResponseError("Moomoo response order remark is not a string")
    if len(item.encode("utf-8")) > 100:
        raise MoomooResponseError("Moomoo response order remark exceeds the documented limit")
    return item


def _market(
    value: Mapping[str, Any], *, required: bool, allow_account_market_id: bool = False
) -> int | None:
    item = value.get("market")
    if item is None and not required:
        return None
    market = _require_int(value, "market")
    # Live position rows return the account market id (100 = US) instead of the
    # documented market enum (2 = US); order rows return the enum.
    if market != 2 and not (allow_account_market_id and market == 100):
        raise MoomooResponseError("Moomoo response instrument market is not US")
    return market


def _order_fields(
    row: Mapping[str, Any], now: datetime, *, require_market: bool
) -> tuple[int, int, str, int, int, Decimal, Decimal, datetime, datetime, int, int | None, int | None]:
    status = _require_int(row, "status")
    if status not in _OPEN_STATUSES and status not in _TERMINAL_STATUSES:
        raise MoomooResponseError("Moomoo response has an unrecognized order status")
    side_code = _require_int(row, "side")
    side = _SIDE_MAP.get(side_code)
    if side is None:
        raise MoomooResponseError("Moomoo response has a short-sell or buy-back side")
    _market(row, required=require_market)
    symbol = _symbol(row)
    quantity = _integral(row, "qty")
    filled = _integral(row, "cum_qty")
    if quantity <= 0 or filled > quantity:
        raise MoomooResponseError("Moomoo response order quantity is inconsistent")
    if status in {1, 2} and filled != 0:
        raise MoomooResponseError("Moomoo response order status does not match its fill quantity")
    if status in {3, 7} and not 0 < filled < quantity:
        raise MoomooResponseError("Moomoo response order status does not match its fill quantity")
    if status == 4 and filled != quantity:
        raise MoomooResponseError("Moomoo response filled order is not fully filled")
    if status == 6 and filled != 0:
        raise MoomooResponseError("Moomoo response rejected order has fills")
    order_type = _require_int(row, "order_type")
    if order_type not in {1, 3}:
        raise MoomooResponseError("Moomoo response order type is not supported")
    time_in_force = _optional_int(row, "time_in_force")
    if time_in_force not in {None, 0, 1}:
        raise MoomooResponseError("Moomoo response time in force is not supported")
    trading_session = _optional_int(row, "order_trade_time_type")
    if trading_session not in {None, 0, 1, 2}:
        raise MoomooResponseError("Moomoo response trading session is not supported")
    created = _timestamp(row, "create_time", now)
    updated = _timestamp(row, "update_time", now)
    if updated < created:
        raise MoomooResponseError("Moomoo response order update precedes creation")
    price = _decimal(row, "price")
    average_fill_price = _decimal(row, "avg_fill_price")
    return (
        status,
        side_code,
        symbol,
        quantity,
        filled,
        price,
        average_fill_price,
        created,
        updated,
        order_type,
        time_in_force,
        trading_session,
    )


class MoomooRestBroker:
    def __init__(
        self,
        client: MoomooRestClient,
        account_lock: AccountLock,
        ledger: Any,
        *,
        clock: Callable[[], datetime] | None = None,
        expected_account_title: str = COMPETITION_ACCOUNT_TITLE,
        max_observation_latency_seconds: int = MAX_OBSERVATION_LATENCY,
    ) -> None:
        if not expected_account_title.strip():
            raise ValueError("expected account title is required")
        if max_observation_latency_seconds <= 0:
            raise ValueError("max observation latency must be positive")
        self._client = client
        self._account_lock = account_lock
        self._ledger = ledger
        self._clock = clock or (lambda: datetime.now(UTC))
        self._expected_account_title = expected_account_title.strip()
        self._max_latency = max_observation_latency_seconds

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None:
            raise MoomooRestError("clock must return a timezone-aware datetime")
        return current

    def _resolve_account(self) -> _ResolvedAccount:
        response = self._client.get("/api/v1.0/sim-trade/accounts")
        data = _require_mapping(response, "data")
        rows = _require_list(data, "accounts")
        parsed: list[_ResolvedAccount] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise MoomooResponseError("Moomoo account list contains a non-object row")
            account_type = _require_int(row, "account_type")
            title = _require_str(row, "account_title")
            account = BrokerAccount.from_provider(
                account_id=_require_str(row, "account_id"),
                market_id=_require_int(row, "market_id"),
                source="simulated",
                account_type=str(account_type),
            )
            parsed.append(
                _ResolvedAccount(account=account, account_type=account_type, title=title)
            )
        resolved = self._account_lock.resolve([item.account for item in parsed])
        match = next(item for item in parsed if item.account is resolved)
        if match.account_type != 2:
            raise AccountLockError("competition account is not the competition account type")
        if match.title != self._expected_account_title:
            raise AccountLockError("competition account title does not match")
        return match

    def account_identity(self) -> RestAccountIdentity:
        match = self._resolve_account()
        return RestAccountIdentity(
            masked_id=match.account.masked_id,
            market_id=match.account.market_id,
            account_type=match.account_type,
            title=match.title,
        )

    def resolved_account_id(self) -> str:
        """Return the locked competition account id for the write transport only."""
        return self._resolve_account().account.account_id

    def _account_path(self, account: BrokerAccount, suffix: str) -> str:
        return f"/api/v1.0/sim-trade/{quote(account.account_id, safe='')}/{suffix}"

    def get_account_snapshot(self) -> AccountSnapshot:
        started = self._now()
        match = self._resolve_account()
        cash_response = self._client.get(
            self._account_path(match.account, "cash-info")
        )
        cash, equity, market_value = _parse_cash(_require_mapping(cash_response, "data"))

        positions_response = self._client.get(
            self._account_path(match.account, "positions"),
            {"market": match.account.market_id},
        )
        positions = _parse_positions(
            _require_mapping(positions_response, "data"), market_value
        )

        orders_response = self._client.get(
            self._account_path(match.account, "orders"),
            {"market": match.account.market_id},
        )
        open_orders = _parse_open_orders(
            _require_mapping(orders_response, "data"), started
        )

        observed = self._now()
        latency = (observed - started).total_seconds()
        if latency < 0 or latency > self._max_latency:
            raise MoomooResponseError("Moomoo observation latency is outside the allowed range")
        day_start_equity, peak_equity = self._ledger.observe_equity(
            account_fingerprint=match.account.fingerprint,
            equity=equity,
            observed_at_utc=observed,
        )
        return AccountSnapshot(
            snapshot_id=_snapshot_id(
                match.account.fingerprint, cash, positions, open_orders
            ),
            account_fingerprint=match.account.fingerprint,
            environment="paper",
            equity=equity,
            day_start_equity=day_start_equity,
            peak_equity=peak_equity,
            cash=cash,
            buying_power=cash,
            positions=positions,
            open_orders=open_orders,
            as_of_utc=observed,
            reconciled=True,
            unknown_orders=0,
        )

    def get_today_orders(self) -> tuple[RestOrder, ...]:
        match = self._resolve_account()
        response = self._client.get(
            self._account_path(match.account, "orders"),
            {"market": match.account.market_id},
        )
        rows = _require_list(_require_mapping(response, "data"), "orders")
        now = self._now()
        parsed: list[RestOrder] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                raise MoomooResponseError("Moomoo order list contains a non-object row")
            order = _parse_rest_order(row, now)
            if order.broker_order_id in seen:
                raise MoomooResponseError("Moomoo order list contains a duplicate order id")
            seen.add(order.broker_order_id)
            parsed.append(order)
        return tuple(parsed)

    def get_order_history(
        self, *, max_pages: int = MAX_HISTORY_PAGES
    ) -> tuple[RestOrder, ...]:
        if not 1 <= max_pages <= MAX_HISTORY_PAGES:
            raise ValueError("max history pages is outside the allowed range")
        match = self._resolve_account()
        path = self._account_path(match.account, "history-orders")
        orders: list[RestOrder] = []
        next_key: str | None = None
        seen: set[str] = set()
        for _ in range(max_pages):
            params: dict[str, str | int] = {
                "market": match.account.market_id,
                "page_size": HISTORY_PAGE_SIZE,
            }
            if next_key is not None:
                params["next_key"] = next_key
            response = self._client.get(path, params)
            data = _require_mapping(response, "data")
            rows = _require_list(data, "orders")
            now = self._now()
            for row in rows:
                if not isinstance(row, Mapping):
                    raise MoomooResponseError("Moomoo order history contains a non-object row")
                orders.append(_parse_rest_order(row, now))
            pagination = response.get("pagination")
            if not isinstance(pagination, Mapping):
                raise MoomooResponseError("Moomoo order history has no pagination object")
            has_more = pagination.get("has_more")
            if not isinstance(has_more, bool):
                raise MoomooResponseError("Moomoo order history has an invalid has_more flag")
            if not has_more:
                return tuple(orders)
            key = pagination.get("next_key")
            if not isinstance(key, str) or not key or key == "0":
                raise MoomooResponseError("Moomoo order history has no usable next key")
            if key in seen:
                raise MoomooResponseError("Moomoo order history pagination repeated")
            seen.add(key)
            next_key = key
        raise MoomooResponseError("Moomoo order history exceeded the page limit")

    def get_order(self, client_order_key: str) -> None:
        raise MoomooRestReadOnlyError("REST adapter is read-only")

    def submit_order(self, request: object, now: datetime) -> None:
        raise MoomooRestReadOnlyError("REST adapter is read-only")


def _parse_cash(data: Mapping[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    balance = _decimal(data, "balance")
    hold = _decimal(data, "hold")
    total_asset = _decimal(data, "total_asset")
    market_value = _decimal(data, "mv")
    long_mv = _decimal(data, "long_mv")
    short_mv = _decimal(data, "short_mv")
    _decimal(data, "max_power_long")
    for value in (balance, hold, total_asset, market_value, long_mv, short_mv):
        if value < 0:
            raise MoomooResponseError("Moomoo cash response contains a negative amount")
    if hold > balance:
        raise MoomooResponseError("Moomoo cash hold exceeds the cash balance")
    if short_mv != 0:
        raise MoomooResponseError("Moomoo cash response reports a short position")
    if market_value != long_mv + short_mv:
        raise MoomooResponseError("Moomoo cash response market values do not reconcile")
    if abs(total_asset - (balance + market_value)) > Decimal("0.01"):
        raise MoomooResponseError("Moomoo cash response total assets do not reconcile")
    return balance - hold, total_asset, market_value


def _parse_positions(
    data: Mapping[str, Any], expected_market_value: Decimal
) -> tuple[Position, ...]:
    rows = _require_list(data, "positions")
    positions: list[Position] = []
    symbols: set[str] = set()
    total = Decimal("0")
    for row in rows:
        if not isinstance(row, Mapping):
            raise MoomooResponseError("Moomoo position list contains a non-object row")
        if _require_int(row, "pstn_type") != 0:
            raise MoomooResponseError("Moomoo position is not a long position")
        _market(row, required=True, allow_account_market_id=True)
        symbol = _symbol(row)
        if symbol in symbols:
            raise MoomooResponseError("Moomoo position list contains a duplicate symbol")
        quantity = _integral(row, "qty")
        market_value = _decimal(row, "mv")
        if market_value < 0:
            raise MoomooResponseError("Moomoo position market value is negative")
        if quantity > 0:
            positions.append(
                Position(symbol=symbol, quantity=quantity, market_value=market_value)
            )
            total += market_value
            symbols.add(symbol)
    # The cash-info and positions endpoints are read in separate calls; the
    # position mark can drift by a few cents between them in a live session.
    tolerance = max(Decimal("0.01"), expected_market_value * Decimal("0.001"))
    if abs(total - expected_market_value) > tolerance:
        raise MoomooResponseError("Moomoo position values do not match cash market value")
    return tuple(positions)


def _parse_open_orders(
    data: Mapping[str, Any], now: datetime
) -> tuple[OpenOrder, ...]:
    rows = _require_list(data, "orders")
    orders: list[OpenOrder] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise MoomooResponseError("Moomoo order list contains a non-object row")
        (
            status,
            _side_code,
            symbol,
            _quantity,
            filled,
            price,
            _average,
            _created,
            _updated,
            _order_type,
            _time_in_force,
            _session,
        ) = _order_fields(row, now, require_market=True)
        order_id = _require_str(row, "order_id")
        if order_id in seen:
            raise MoomooResponseError("Moomoo order list contains a duplicate order id")
        seen.add(order_id)
        if status not in _OPEN_STATUSES:
            continue
        if status in {1, 2} and filled != 0:
            raise MoomooResponseError("Moomoo open order status does not match its fill quantity")
        remaining = _quantity - filled
        if remaining <= 0 or price <= 0:
            raise MoomooResponseError("Moomoo open order has no valid remaining quantity or price")
        orders.append(
            OpenOrder(
                symbol=symbol,
                side=_SIDE_MAP[_side_code],
                remaining_quantity=remaining,
                reference_price=price,
            )
        )
    return tuple(orders)


def _parse_rest_order(row: Mapping[str, Any], now: datetime) -> RestOrder:
    (
        status,
        side_code,
        symbol,
        quantity,
        filled,
        price,
        average_fill_price,
        created,
        updated,
        order_type,
        time_in_force,
        session,
    ) = _order_fields(row, now, require_market=False)
    return RestOrder(
        broker_order_id=_require_str(row, "order_id"),
        symbol=symbol,
        side=_SIDE_MAP[side_code],
        status_code=status,
        status_label=_STATUS_LABELS[status],
        quantity=quantity,
        filled_quantity=filled,
        price=price,
        average_fill_price=average_fill_price,
        created_at_utc=created,
        updated_at_utc=updated,
        order_type=order_type,
        time_in_force=time_in_force,
        trading_session=session,
        remark=_remark(row),
    )


def _snapshot_id(
    fingerprint: str,
    cash: Decimal,
    positions: tuple[Position, ...],
    open_orders: tuple[OpenOrder, ...],
) -> str:
    # Mark-driven values (equity, position market value, order reference price)
    # drift between consecutive reads in a live session; the id tracks state
    # changes only, which R009 uses to reject a changed account.
    payload = {
        "fingerprint": fingerprint,
        "cash": str(cash),
        "positions": [[item.symbol, item.quantity] for item in positions],
        "open_orders": [
            [item.symbol, item.side.value, item.remaining_quantity] for item in open_orders
        ],
    }
    digest = hashlib.sha256(str(payload).encode("utf-8")).hexdigest()
    return f"mm-{digest[:20]}"
