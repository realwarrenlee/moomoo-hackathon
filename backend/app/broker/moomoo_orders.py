"""Documented simulated-order payloads, correlation, and the guarded transport.

The transport is disabled by default and only targets the documented simulated
order path. It never retries a submission; an unclear outcome becomes UNKNOWN
and must be reconciled through read-only broker queries.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from urllib.parse import quote

import httpx

from app.broker.moomoo_rest import REST_BASE_URL, MoomooRestBroker, RestOrder
from app.models.contracts import (
    AccountSnapshot,
    Fill,
    OrderRecord,
    OrderRequest,
    OrderSide,
    OrderStatus,
)

ORDER_WRITES_ENABLED = False
CORRELATION_PREFIX = "MTP1-"
MAX_REMARK_BYTES = 100
_ORDER_PATH = re.compile(r"^/api/v1\.0/sim-trade/[A-Za-z0-9_-]{1,64}/orders$")
_KEY_PATTERN = re.compile(r"^mootrade-[0-9a-f]{64}$")
_TAG_PATTERN = re.compile(r"^MTP1-[0-9a-f]{64}$")
_STATUS_TO_ORDER = {
    1: OrderStatus.ACKNOWLEDGED,
    2: OrderStatus.ACKNOWLEDGED,
    3: OrderStatus.PARTIALLY_FILLED,
    4: OrderStatus.FILLED,
    5: OrderStatus.CANCELLED,
    6: OrderStatus.REJECTED,
    7: OrderStatus.CANCELLED,
}


class OrderAdapterError(RuntimeError):
    pass


class OrderWritesDisabledError(OrderAdapterError):
    pass


class OrderTransportError(OrderAdapterError):
    pass


class OrderCorrelationError(OrderAdapterError):
    pass


class AmbiguousOrderMatchError(OrderCorrelationError):
    pass


class OrderReconciliationError(OrderAdapterError):
    pass


def build_correlation_tag(client_order_key: str) -> str:
    if not _KEY_PATTERN.fullmatch(client_order_key):
        raise ValueError("client order key is not a MooTrade key")
    tag = f"{CORRELATION_PREFIX}{client_order_key.removeprefix('mootrade-')}"
    if len(tag.encode("utf-8")) > MAX_REMARK_BYTES:
        raise ValueError("correlation tag exceeds the documented remark limit")
    return tag


def extract_correlation_tag(remark: str) -> str | None:
    candidate = remark.strip()
    return candidate if _TAG_PATTERN.fullmatch(candidate) else None


def build_simulated_order_payload(
    request: OrderRequest, *, account_market_id: int, remark: str
) -> dict[str, Any]:
    if account_market_id <= 0:
        raise ValueError("account market id must be positive")
    if not isinstance(remark, str) or len(remark.encode("utf-8")) > MAX_REMARK_BYTES:
        raise ValueError("order remark exceeds the documented limit")
    if request.order_type != "MARKET" or request.time_in_force != "DAY":
        raise ValueError("only documented market day orders are supported")
    # Price is omitted because the documented contract allows it for market orders.
    return {
        "market": account_market_id,
        "symbol": f"US.{request.symbol}",
        "order_type": 3,
        "order_side": 1 if request.side is OrderSide.BUY else 2,
        "qty": str(request.quantity),
        "text": remark,
        "order_trade_time_type": 1,
    }


@dataclass(frozen=True)
class PreparedOrder:
    client_order_key: str
    correlation_tag: str
    payload: Mapping[str, Any]
    order_writes_enabled: bool


class MoomooOrderTransport:
    """POST only to the documented simulated-order path.

    A submission is never retried. Authentication is refreshed before the
    request only; any HTTP, transport, or malformed-response failure after the
    request is reported as an ambiguous outcome for reconciliation.
    """

    def __init__(
        self,
        auth: Any,
        *,
        http: httpx.Client | None = None,
        order_writes_enabled: bool = ORDER_WRITES_ENABLED,
    ) -> None:
        self._auth = auth
        self._http = http or httpx.Client(timeout=20, trust_env=False)
        self.order_writes_enabled = order_writes_enabled

    def submit(self, account_id: str, payload: Mapping[str, Any]) -> str:
        if not self.order_writes_enabled:
            raise OrderWritesDisabledError("ORDER_WRITES_ENABLED is false; no order was sent")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", account_id):
            raise OrderAdapterError("account id is not usable in the order path")
        path = f"/api/v1.0/sim-trade/{quote(account_id, safe='')}/orders"
        if not _ORDER_PATH.fullmatch(path):
            raise OrderAdapterError("order path is not the documented simulated endpoint")
        token = self._auth.access_token()
        try:
            response = self._http.post(
                f"{REST_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                json=dict(payload),
            )
        except httpx.HTTPError as exc:
            raise OrderTransportError(
                f"order submission outcome is ambiguous ({type(exc).__name__})"
            ) from None
        if response.status_code != 200:
            raise OrderTransportError(
                f"order submission failed (HTTP {response.status_code}); outcome is ambiguous"
            )
        try:
            body = response.json()
        except ValueError:
            raise OrderTransportError("order response is not JSON; outcome is ambiguous") from None
        if not isinstance(body, Mapping):
            raise OrderTransportError("order response is not an object; outcome is ambiguous")
        ret_code = body.get("ret_code")
        if isinstance(ret_code, bool) or not isinstance(ret_code, int):
            raise OrderTransportError("order response has no integer ret_code")
        if ret_code != 0:
            ret_msg = body.get("ret_msg")
            detail = f" (ret_msg={ret_msg!r})" if isinstance(ret_msg, str) and ret_msg else ""
            if not detail:
                detail = f" (body={repr(body)[:200]})"
            raise OrderTransportError(
                f"order submission was refused (ret_code={ret_code}){detail}; outcome is ambiguous"
            )
        data = body.get("data")
        order_id = data.get("order_id") if isinstance(data, Mapping) else None
        if not isinstance(order_id, str) or not order_id.strip():
            raise OrderTransportError("order response has no order id; outcome is ambiguous")
        return order_id.strip()


class MoomooSimulatedOrderAdapter:
    def __init__(
        self,
        expected_account_fingerprint: str,
        account_market_id: int,
        *,
        order_writes_enabled: bool = ORDER_WRITES_ENABLED,
    ) -> None:
        if not expected_account_fingerprint or account_market_id <= 0:
            raise ValueError("account fingerprint and market id are required")
        self.expected_account_fingerprint = expected_account_fingerprint
        self.account_market_id = account_market_id
        self.order_writes_enabled = order_writes_enabled

    def prepare(self, request: OrderRequest, account: AccountSnapshot) -> PreparedOrder:
        if account.environment != "paper":
            raise OrderAdapterError("order adapter accepts paper accounts only")
        if account.account_fingerprint != self.expected_account_fingerprint:
            raise OrderAdapterError("order adapter account fingerprint does not match")
        tag = build_correlation_tag(request.client_order_key)
        return PreparedOrder(
            client_order_key=request.client_order_key,
            correlation_tag=tag,
            payload=build_simulated_order_payload(
                request, account_market_id=self.account_market_id, remark=tag
            ),
            order_writes_enabled=self.order_writes_enabled,
        )

    def submit(self, request: OrderRequest, account: AccountSnapshot) -> None:
        self.prepare(request, account)
        if not self.order_writes_enabled:
            raise OrderWritesDisabledError("ORDER_WRITES_ENABLED is false; no order was sent")
        raise OrderWritesDisabledError(
            "no order execution transport is installed; the prototype cannot submit"
        )


def merge_correlated_orders(
    today: Iterable[RestOrder], history: Iterable[RestOrder]
) -> tuple[RestOrder, ...]:
    merged: dict[str, RestOrder] = {}
    for order in list(today) + list(history):
        existing = merged.get(order.broker_order_id)
        if existing is not None and existing != order:
            raise OrderCorrelationError("broker returned conflicting rows for one order id")
        merged[order.broker_order_id] = order
    return tuple(merged.values())


def correlate_orders(tag: str, orders: Iterable[RestOrder]) -> RestOrder | None:
    matches = [order for order in orders if extract_correlation_tag(order.remark) == tag]
    if len(matches) > 1:
        raise AmbiguousOrderMatchError(
            f"{len(matches)} broker orders carry the same correlation tag"
        )
    return matches[0] if matches else None


def to_order_record(
    order: RestOrder, request: OrderRequest, account_fingerprint: str, now: datetime
) -> OrderRecord:
    if order.symbol != request.symbol:
        raise OrderCorrelationError("correlated broker order symbol does not match")
    if order.side is not request.side:
        raise OrderCorrelationError("correlated broker order side does not match")
    if order.quantity != request.quantity:
        raise OrderCorrelationError("correlated broker order quantity does not match")
    status = _STATUS_TO_ORDER.get(order.status_code)
    if status is None:
        raise OrderCorrelationError("correlated broker order status is not supported")
    fills: tuple[Fill, ...] = ()
    if order.filled_quantity:
        if order.average_fill_price <= 0:
            raise OrderCorrelationError("correlated broker order has fills without a price")
        fills = (
            Fill(
                broker_fill_id=f"{order.broker_order_id}-cumulative",
                quantity=order.filled_quantity,
                price=order.average_fill_price,
                filled_at_utc=order.updated_at_utc,
            ),
        )
    return OrderRecord(
        client_order_key=request.client_order_key,
        proposal_id=request.proposal_id,
        paper_account_fingerprint=account_fingerprint,
        broker_order_id=order.broker_order_id,
        status=status,
        request=request,
        submitted_at_utc=order.created_at_utc,
        last_broker_sync_utc=now,
        fills=fills,
    )


class OrderReconciliationProvider(Protocol):
    def get_today_orders(self) -> tuple[RestOrder, ...]: ...

    def get_order_history(self) -> tuple[RestOrder, ...]: ...

    def get_account_snapshot(self) -> AccountSnapshot: ...


@dataclass(frozen=True)
class ReconciliationResult:
    outcome: Literal["MATCHED", "NO_MATCH", "AMBIGUOUS", "ACCOUNT_MISMATCH"]
    record: OrderRecord | None
    today_orders: int
    history_orders: int
    detail: str


def reconcile_unknown_order(
    local: OrderRecord,
    provider: OrderReconciliationProvider,
    now: datetime,
) -> ReconciliationResult:
    if local.status is not OrderStatus.UNKNOWN:
        raise OrderReconciliationError("only UNKNOWN orders can be reconciled this way")
    tag = build_correlation_tag(local.client_order_key)

    today = provider.get_today_orders()
    history = provider.get_order_history()
    snapshot = provider.get_account_snapshot()
    if (
        snapshot.environment != "paper"
        or snapshot.account_fingerprint != local.paper_account_fingerprint
    ):
        return ReconciliationResult(
            outcome="ACCOUNT_MISMATCH",
            record=None,
            today_orders=len(today),
            history_orders=len(history),
            detail="account snapshot does not match the submission account",
        )
    if not snapshot.reconciled or snapshot.unknown_orders:
        return ReconciliationResult(
            outcome="ACCOUNT_MISMATCH",
            record=None,
            today_orders=len(today),
            history_orders=len(history),
            detail="account snapshot is not cleanly reconciled",
        )

    merged = merge_correlated_orders(today, history)
    try:
        match = correlate_orders(tag, merged)
    except AmbiguousOrderMatchError as exc:
        return ReconciliationResult(
            outcome="AMBIGUOUS",
            record=None,
            today_orders=len(today),
            history_orders=len(history),
            detail=str(exc),
        )
    if match is None:
        return ReconciliationResult(
            outcome="NO_MATCH",
            record=None,
            today_orders=len(today),
            history_orders=len(history),
            detail="no broker order carries the correlation tag",
        )
    record = to_order_record(
        match, local.request, local.paper_account_fingerprint, now
    )
    return ReconciliationResult(
        outcome="MATCHED",
        record=record,
        today_orders=len(today),
        history_orders=len(history),
        detail="exactly one broker order matched the correlation tag",
    )


class MoomooPaperBroker:
    """Guarded paper broker facade for a caller that already passed RiskGate.

    Reads come from the read-only REST adapter. Submission uses the documented
    simulated-order transport, which is disabled unless explicitly enabled.
    """

    source_name = "moomoo_paper"

    def __init__(
        self,
        reads: MoomooRestBroker,
        ledger: Any,
        transport: MoomooOrderTransport,
        *,
        expected_account_fingerprint: str,
        account_market_id: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._reads = reads
        self._ledger = ledger
        self._transport = transport
        self._adapter = MoomooSimulatedOrderAdapter(
            expected_account_fingerprint, account_market_id
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None:
            raise OrderAdapterError("clock must return a timezone-aware datetime")
        return current

    def get_account_snapshot(self) -> AccountSnapshot:
        return self._reads.get_account_snapshot()

    def get_order(self, client_order_key: str) -> OrderRecord | None:
        local = self._ledger.order_for_key(client_order_key)
        if local is None:
            return None
        now = self._now()
        if local.status is OrderStatus.UNKNOWN:
            return reconcile_unknown_order(local, self._reads, now).record
        snapshot = self._reads.get_account_snapshot()
        if (
            snapshot.environment != "paper"
            or snapshot.account_fingerprint != local.paper_account_fingerprint
            or not snapshot.reconciled
            or snapshot.unknown_orders
        ):
            return None
        tag = build_correlation_tag(client_order_key)
        merged = merge_correlated_orders(
            self._reads.get_today_orders(), self._reads.get_order_history()
        )
        try:
            match = correlate_orders(tag, merged)
        except AmbiguousOrderMatchError:
            return None
        if match is None:
            return None
        return to_order_record(
            match, local.request, local.paper_account_fingerprint, now
        )

    def submit_order(self, request: OrderRequest, now: datetime) -> OrderRecord:
        snapshot = self._reads.get_account_snapshot()
        if snapshot.snapshot_id != request.account_snapshot_id:
            raise OrderAdapterError("order approval is bound to a stale account snapshot")
        prepared = self._adapter.prepare(request, snapshot)
        broker_order_id = self._transport.submit(
            self._reads.resolved_account_id(), prepared.payload
        )
        # The documented response contains only an order id; fills require reconciliation.
        return OrderRecord(
            client_order_key=request.client_order_key,
            proposal_id=request.proposal_id,
            paper_account_fingerprint=snapshot.account_fingerprint,
            broker_order_id=broker_order_id,
            status=OrderStatus.ACKNOWLEDGED,
            request=request,
            submitted_at_utc=now,
            last_broker_sync_utc=now,
        )
