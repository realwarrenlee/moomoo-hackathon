"""Read-only Moomoo paper-account adapter.

The caller is supplied by the MCP host; it receives only the four simulated
account read tools below. This module has no order-write path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Protocol

from app.broker.account_lock import AccountLock, BrokerAccount
from app.ledger.store import SQLiteLedger
from app.models.contracts import (
    AccountSnapshot,
    OpenOrder,
    OrderRecord,
    OrderRequest,
    OrderSide,
    Position,
)

READ_ONLY_TOOLS = frozenset(
    {
        "sim_trade_account_list",
        "sim_trade_cash_info",
        "sim_trade_position_list",
        "sim_trade_history_order_list",
    }
)

ORDER_WRITE_TOOLS = frozenset(
    {
        "trading_order_place",
        "trading_order_replace",
        "trading_order_cancel",
        "trading_order_confirm",
        "sim_trade_input_order",
        "sim_trade_cancel_order",
        "sim_trade_modify_order",
        "crypto_account_create_order",
        "crypto_account_cancel_order",
        "crypto_account_modify_order",
    }
)

TERMINAL_ORDER_STATUSES = frozenset(
    {
        "FILLED",
        "FILLED_ALL",
        "CANCELLED",
        "CANCELLED_ALL",
        "CANCELLED_PART",
        "REJECTED",
        "FAILED",
        "DISABLED",
        "DELETED",
        "TIMEOUT",
        "EXPIRED",
    }
)

OPEN_ORDER_STATUSES = frozenset(
    {
        "WAITING_SUBMIT",
        "SUBMITTING",
        "SUBMITTED",
        "PENDING",
        "NEW",
        "ACKNOWLEDGED",
        "OPEN",
        "FILLED_PART",
        "PARTIALLY_FILLED",
    }
)

_AMOUNT_TOLERANCE = Decimal("0.01")
_MAX_HISTORY_PAGES = 10


class MoomooReadOnlyError(RuntimeError):
    pass


class ReadOnlyViolation(MoomooReadOnlyError):
    pass


class MoomooResponseError(MoomooReadOnlyError):
    pass


class ToolCaller(Protocol):
    def __call__(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


def call_read_only_tool(
    caller: ToolCaller,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    if tool_name not in READ_ONLY_TOOLS:
        raise ReadOnlyViolation(f"tool {tool_name!r} is not in the read-only allowlist")
    try:
        response = caller(tool_name, arguments)
    except Exception as exc:
        # Provider error text may contain the account id; keep the type only.
        raise MoomooResponseError(f"{tool_name} failed ({type(exc).__name__})") from None
    if not isinstance(response, Mapping):
        raise MoomooResponseError(f"{tool_name} returned a non-object response")
    return response


def _data_object(tool_name: str, response: Mapping[str, Any]) -> Mapping[str, Any]:
    ret_code = response.get("ret_code")
    if ret_code != 0:
        raise MoomooResponseError(f"{tool_name} returned ret_code={ret_code!r}")
    data = response.get("data")
    if not isinstance(data, Mapping):
        raise MoomooResponseError(f"{tool_name} returned no data object")
    return data


def _require_list(data: Mapping[str, Any], field_name: str) -> list[Any]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise MoomooResponseError(f"response field {field_name!r} must be a list")
    return value


def _require_mapping(row: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    value = row.get(field_name)
    if not isinstance(value, Mapping):
        raise MoomooResponseError(f"response field {field_name!r} must be an object")
    return value


def _require_str(row: Mapping[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise MoomooResponseError(f"response field {field_name!r} must be a non-empty string")
    return value.strip()


def _require_int(row: Mapping[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MoomooResponseError(f"response field {field_name!r} must be an integer")
    return value


def _decimal(row: Mapping[str, Any], field_name: str) -> Decimal:
    value = row.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise MoomooResponseError(f"response field {field_name!r} must be a decimal string")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        raise MoomooResponseError(f"response field {field_name!r} is not a decimal") from None
    if not result.is_finite():
        raise MoomooResponseError(f"response field {field_name!r} is not finite")
    return result


def _integral_decimal(row: Mapping[str, Any], field_name: str) -> int:
    value = _decimal(row, field_name)
    if value != value.to_integral_value():
        raise MoomooResponseError(f"response field {field_name!r} must be a whole number")
    return int(value)


def _account_source(row: Mapping[str, Any]) -> str:
    for field_name in ("trd_env", "source"):
        value = row.get(field_name)
        if value is None:
            continue
        normalized = str(value).strip().lower()
        if normalized in {"simulate", "simulated", "paper", "demo"}:
            return "simulated"
        if normalized in {"live", "real"}:
            return "live"
        raise MoomooResponseError(f"response field {field_name!r} has an unknown environment")
    return "simulated"


def _parse_accounts(data: Mapping[str, Any]) -> list[BrokerAccount]:
    accounts = []
    for row in _require_list(data, "accounts"):
        if not isinstance(row, Mapping):
            raise MoomooResponseError("account row must be an object")
        accounts.append(
            BrokerAccount.from_provider(
                account_id=_require_str(row, "account_id"),
                market_id=_require_int(row, "market_id"),
                source=_account_source(row),
                account_type=str(row.get("account_type", "unknown")),
            )
        )
    if not accounts:
        raise MoomooResponseError("account list is empty")
    return accounts


def _parse_cash(data: Mapping[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    balance = _decimal(data, "balance")
    hold = _decimal(data, "hold")
    total_asset = _decimal(data, "total_asset")
    market_value = _decimal(data, "mv")
    long_mv = _decimal(data, "long_mv")
    short_mv = _decimal(data, "short_mv")
    # max_power_long is margin buying power; validate it but never propagate it.
    _decimal(data, "max_power_long")

    if min(balance, hold, total_asset, market_value, long_mv, short_mv) < 0:
        raise MoomooResponseError("cash response contains a negative amount")
    if hold > balance:
        raise MoomooResponseError("frozen funds exceed the cash balance")
    if short_mv != 0:
        raise MoomooResponseError("short market value is not permitted")
    if market_value != long_mv + short_mv:
        raise MoomooResponseError("market value totals are inconsistent")
    cash = balance - hold
    if total_asset <= 0:
        raise MoomooResponseError("total assets must be positive")
    if abs(total_asset - (balance + market_value)) > _AMOUNT_TOLERANCE:
        raise MoomooResponseError("total assets do not match cash plus market value")
    return cash, total_asset, market_value


def _normalize_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if "." in symbol:
        market, code = symbol.split(".", 1)
        if market != "US" or not code:
            raise MoomooResponseError("position or order is outside the US market")
        symbol = code
    return symbol


def _order_symbol(row: Mapping[str, Any]) -> str:
    value = row.get("code", row.get("symbol"))
    if not isinstance(value, str) or not value.strip():
        raise MoomooResponseError("order has no security code")
    return _normalize_symbol(value)


def _parse_positions(data: Mapping[str, Any], expected_market_value: Decimal) -> tuple[Position, ...]:
    positions: list[Position] = []
    seen: set[str] = set()
    total_market_value = Decimal("0")
    for row in _require_list(data, "positions"):
        if not isinstance(row, Mapping):
            raise MoomooResponseError("position row must be an object")
        if _require_int(row, "pstn_type") != 0:
            raise MoomooResponseError("short positions are not permitted")
        symbol = _normalize_symbol(_require_str(row, "symbol"))
        quantity = _integral_decimal(row, "qty")
        market_value = _decimal(row, "mv")
        if quantity < 0 or market_value < 0:
            raise MoomooResponseError("position quantity and market value cannot be negative")
        if quantity == 0:
            if market_value != 0:
                raise MoomooResponseError("zero-quantity position has market value")
            continue
        if symbol in seen:
            raise MoomooResponseError("duplicate position symbol")
        seen.add(symbol)
        total_market_value += market_value
        positions.append(
            Position(symbol=symbol, quantity=quantity, market_value=market_value)
        )
    if abs(total_market_value - expected_market_value) > _AMOUNT_TOLERANCE:
        raise MoomooResponseError("position totals do not match account market value")
    return tuple(positions)


def _parse_order_row(
    row: Mapping[str, Any],
    open_orders: list[OpenOrder],
    seen: set[str],
) -> int:
    status = _require_str(row, "order_status").upper()
    if status == "UNKNOWN":
        return 1
    if status in TERMINAL_ORDER_STATUSES:
        return 0
    if status not in OPEN_ORDER_STATUSES:
        raise MoomooResponseError(f"unrecognized open order status {status!r}")

    side_text = _require_str(row, "side").upper()
    if side_text not in {"BUY", "SELL"}:
        raise MoomooResponseError("short-selling or buy-to-cover orders are not permitted")
    symbol = _order_symbol(row)
    quantity = _integral_decimal(row, "qty")
    dealt_quantity = _integral_decimal(row, "dealt_qty")
    price = _decimal(row, "price")
    currency = row.get("currency")
    if quantity <= 0 or dealt_quantity < 0 or dealt_quantity > quantity:
        raise MoomooResponseError("order quantities are inconsistent")
    if price <= 0:
        raise MoomooResponseError("open order price must be positive")
    if currency not in (None, "", "USD"):
        raise MoomooResponseError("open order currency must be USD")

    remaining = quantity - dealt_quantity
    if remaining <= 0:
        raise MoomooResponseError("open order has no remaining quantity")
    key = f"{symbol}:{side_text}:{quantity}:{dealt_quantity}:{price}"
    if key in seen:
        raise MoomooResponseError("duplicate open order")
    seen.add(key)
    open_orders.append(
        OpenOrder(
            symbol=symbol,
            side=OrderSide(side_text),
            remaining_quantity=remaining,
            reference_price=price,
        )
    )
    return 0


def _snapshot_id(
    account_fingerprint: str,
    equity: Decimal,
    cash: Decimal,
    positions: tuple[Position, ...],
    open_orders: tuple[OpenOrder, ...],
    unknown_orders: int,
) -> str:
    material = [
        account_fingerprint,
        str(equity),
        str(cash),
        str(unknown_orders),
    ]
    material.extend(
        f"{item.symbol}:{item.quantity}:{item.market_value}"
        for item in sorted(positions, key=lambda item: item.symbol)
    )
    material.extend(
        f"{item.symbol}:{item.side.value}:{item.remaining_quantity}:{item.reference_price}"
        for item in sorted(
            open_orders,
            key=lambda item: (item.symbol, item.side.value, item.reference_price, item.remaining_quantity),
        )
    )
    digest = sha256("|".join(material).encode("utf-8")).hexdigest()
    return f"mm-{digest[:20]}"


class MoomooReadOnlyBroker:
    def __init__(
        self,
        caller: ToolCaller,
        account_lock: AccountLock,
        ledger: SQLiteLedger,
        clock: Callable[[], datetime] | None = None,
        max_observation_latency_seconds: int = 15,
    ) -> None:
        if max_observation_latency_seconds <= 0:
            raise ValueError("max observation latency must be positive")
        self._caller = caller
        self._account_lock = account_lock
        self._ledger = ledger
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_observation_latency_seconds = max_observation_latency_seconds

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None:
            raise MoomooReadOnlyError("clock must return a timezone-aware datetime")
        return current

    def get_account_snapshot(self) -> AccountSnapshot:
        started_at = self._now()

        accounts_response = call_read_only_tool(
            self._caller, "sim_trade_account_list", {}
        )
        accounts = _parse_accounts(_data_object("sim_trade_account_list", accounts_response))
        account = self._account_lock.resolve(accounts)
        account_arguments = {"acc_id": account.account_id}
        market_arguments = {**account_arguments, "market": account.market_id}

        cash_response = call_read_only_tool(
            self._caller, "sim_trade_cash_info", account_arguments
        )
        cash, equity, market_value = _parse_cash(
            _data_object("sim_trade_cash_info", cash_response)
        )

        positions_response = call_read_only_tool(
            self._caller, "sim_trade_position_list", market_arguments
        )
        positions = _parse_positions(
            _data_object("sim_trade_position_list", positions_response), market_value
        )

        open_orders: list[OpenOrder] = []
        seen_orders: set[str] = set()
        unknown_orders = 0
        history_arguments: dict[str, Any] = {**market_arguments, "page_size": 100}
        seen_cursors: set[str] = set()
        for _ in range(_MAX_HISTORY_PAGES):
            history_response = call_read_only_tool(
                self._caller, "sim_trade_history_order_list", history_arguments
            )
            history_data = _data_object("sim_trade_history_order_list", history_response)
            for row in _require_list(history_data, "orders"):
                if not isinstance(row, Mapping):
                    raise MoomooResponseError("order row must be an object")
                unknown_orders += _parse_order_row(row, open_orders, seen_orders)
            pagination = _require_mapping(history_response, "pagination")
            has_more = pagination.get("has_more")
            if not isinstance(has_more, bool):
                raise MoomooResponseError("pagination.has_more must be a boolean")
            if not has_more:
                break
            next_key = pagination.get("next_key")
            if not isinstance(next_key, str) or not next_key or next_key == "0":
                raise MoomooResponseError("pagination has more pages but no next_key")
            if next_key in seen_cursors:
                raise MoomooResponseError("pagination cursor repeated")
            seen_cursors.add(next_key)
            history_arguments["next_key"] = next_key
        else:
            raise MoomooResponseError("order history exceeded the page limit")

        observed_at = self._now()
        elapsed = (observed_at - started_at).total_seconds()
        if elapsed < 0 or elapsed > self._max_observation_latency_seconds:
            raise MoomooResponseError("account observation is stale or time moved backwards")

        open_orders_tuple = tuple(open_orders)
        day_start_equity, peak_equity = self._ledger.observe_equity(
            account.fingerprint, equity, observed_at
        )
        return AccountSnapshot(
            snapshot_id=_snapshot_id(
                account.fingerprint,
                equity,
                cash,
                positions,
                open_orders_tuple,
                unknown_orders,
            ),
            account_fingerprint=account.fingerprint,
            environment="paper",
            equity=equity,
            day_start_equity=day_start_equity,
            peak_equity=peak_equity,
            cash=cash,
            # max_power_long includes margin, so the broker's leverage is ignored.
            buying_power=cash,
            positions=positions,
            open_orders=open_orders_tuple,
            as_of_utc=observed_at,
            reconciled=unknown_orders == 0,
            unknown_orders=unknown_orders,
        )

    def get_order(self, client_order_key: str) -> OrderRecord | None:
        raise ReadOnlyViolation("read-only Moomoo adapter cannot read broker order state")

    def submit_order(self, request: OrderRequest, now: datetime) -> OrderRecord:
        raise ReadOnlyViolation("read-only Moomoo adapter cannot submit orders")
