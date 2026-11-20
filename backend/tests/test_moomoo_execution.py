from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.broker.moomoo_orders import (
    AmbiguousOrderMatchError,
    MoomooOrderTransport,
    MoomooPaperBroker,
    MoomooSimulatedOrderAdapter,
    OrderAdapterError,
    OrderCorrelationError,
    OrderTransportError,
    OrderWritesDisabledError,
    build_correlation_tag,
    build_simulated_order_payload,
    correlate_orders,
    extract_correlation_tag,
    merge_correlated_orders,
    reconcile_unknown_order,
    to_order_record,
)
from app.broker.moomoo_quotes import MoomooQuoteFeed, QuoteFeedError
from app.broker.moomoo_rest import (
    MoomooRestClient,
    MoomooRestReadOnlyError,
    RestOrder,
)
from app.ledger.store import SQLiteLedger
from app.models.contracts import (
    OrderRecord,
    OrderRequest,
    OrderSide,
    OrderStatus,
    PolicyDecision,
)
from app.service import TradingService, build_client_order_key

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1_000)


class FakeAuth:
    def __init__(self) -> None:
        self.token = "token-1"
        self.refresh_calls = 0

    def access_token(self) -> str:
        return self.token

    def refresh(self) -> None:
        self.refresh_calls += 1
        self.token = f"token-{self.refresh_calls + 1}"


def make_client(handler) -> MoomooRestClient:
    return MoomooRestClient(
        FakeAuth(),
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
    )


def quote_row(
    *,
    code: str = "US.QQQ",
    data_time: int = NOW_MS - 5_000,
    price: float = 390.25,
    sec_status: str = "NORMAL",
    suspension: bool = False,
) -> dict:
    return {
        "code": code,
        "data_time": data_time,
        "last_price": price,
        "prev_close_price": 388.0,
        "sec_status": sec_status,
        "suspension": suspension,
    }


def market_row(*, code: str = "US.QQQ", state: str = "AFTERNOON") -> dict:
    return {"code": code, "market_state": state, "time_date": 20261118}


def quote_handler(*, quote: dict | None = None, market: dict | None = None, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append((request.method, request.url.path, json.loads(request.content)))
        if request.url.path.endswith("/stock-quote"):
            return httpx.Response(
                200, json={"ret_code": 0, "data": {"quote_list": [quote or quote_row()]}}
            )
        if request.url.path.endswith("/market-state"):
            return httpx.Response(
                200,
                json={
                    "ret_code": 0,
                    "data": {"market_state_list": [market or market_row()]},
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    return handler


def test_quote_feed_returns_fresh_regular_session_quote():
    seen = []
    feed = MoomooQuoteFeed(make_client(quote_handler(seen=seen)))

    quote = feed.get_quote("QQQ", NOW)

    assert quote.symbol == "QQQ"
    assert quote.price == Decimal("390.25")
    assert quote.regular_session_open is True
    assert quote.as_of_utc == datetime.fromtimestamp((NOW_MS - 5_000) / 1_000, tz=UTC)
    assert seen[0] == (
        "POST",
        "/api/v1.0/quote/stock-quote",
        {"code_list": ["US.QQQ"]},
    )
    assert seen[1] == (
        "POST",
        "/api/v1.0/quote/market-state",
        {"code_list": ["US.QQQ"], "is_contain_ba": False, "is_contain_overnight": False},
    )


def test_extended_hours_state_is_not_a_regular_session():
    feed = MoomooQuoteFeed(
        make_client(quote_handler(market=market_row(state="PRE_MARKET_BEGIN")))
    )

    quote = feed.get_quote("QQQ", NOW)

    assert quote.regular_session_open is False


@pytest.mark.parametrize(
    ("quote", "match"),
    [
        (quote_row(data_time=NOW_MS - 301_000), "stale"),
        (quote_row(data_time=NOW_MS + 6_000), "future"),
        (quote_row(code="US.SPY"), "does not match"),
        (quote_row(price=0), "not positive"),
        (quote_row(sec_status="SUSPENDED"), "not NORMAL"),
        (quote_row(suspension=True), "suspended"),
    ],
)
def test_bad_quotes_fail_closed(quote, match):
    feed = MoomooQuoteFeed(make_client(quote_handler(quote=quote)))

    with pytest.raises(QuoteFeedError, match=match):
        feed.get_quote("QQQ", NOW)


@pytest.mark.parametrize("symbol", ["qqq", "QQQ!", "", "TOOLONGSYMBOL", "1QQQ"])
def test_invalid_symbols_are_rejected_before_any_request(symbol):
    seen = []
    feed = MoomooQuoteFeed(make_client(quote_handler(seen=seen)))

    with pytest.raises(ValueError, match="approved US ticker"):
        feed.get_quote(symbol, NOW)
    assert seen == []


def test_naive_clock_is_rejected_before_any_request():
    seen = []
    feed = MoomooQuoteFeed(make_client(quote_handler(seen=seen)))

    with pytest.raises(ValueError, match="timezone-aware"):
        feed.get_quote("QQQ", datetime(2026, 11, 18, 15, 0))
    assert seen == []


def test_missing_quote_or_market_state_fails_closed():
    def empty(path: str):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "ret_code": 0,
                    "data": {
                        "quote_list": [] if path == "quote" else [quote_row()],
                        "market_state_list": [] if path == "market" else [market_row()],
                    },
                },
            )

        return handler

    with pytest.raises(QuoteFeedError, match="exactly one"):
        MoomooQuoteFeed(make_client(empty("quote"))).get_quote("QQQ", NOW)
    with pytest.raises(QuoteFeedError, match="exactly one"):
        MoomooQuoteFeed(make_client(empty("market"))).get_quote("QQQ", NOW)


def test_post_read_is_limited_and_refresh_failure_is_fatal():
    client = make_client(
        lambda request: httpx.Response(401, json={"ret_code": -12102})
    )

    for path in [
        "/api/v1.0/sim-trade/123/orders",
        "/api/v1.0/quote/order-book",
        "/api/v1.0/quote/stock-quote/../orders",
    ]:
        with pytest.raises(MoomooRestReadOnlyError):
            client.post_read(path, {})
    assert not hasattr(client, "submit_order")

    with pytest.raises(Exception, match="authentication failed"):
        client.post_read("/api/v1.0/quote/stock-quote", {"code_list": []})
    assert client._auth.refresh_calls == 1


def make_request(
    *, proposal_id: str = "proposal-1", side: OrderSide = OrderSide.BUY, quantity: int = 2
) -> OrderRequest:
    return OrderRequest(
        client_order_key=build_client_order_key("spy-directional", proposal_id),
        proposal_id=proposal_id,
        account_snapshot_id="snapshot-1",
        symbol="SPY",
        side=side,
        quantity=quantity,
        reference_price=Decimal("100"),
    )


def make_rest_order(
    now: datetime,
    *,
    order_id: str = "broker-1",
    symbol: str = "SPY",
    side: OrderSide = OrderSide.BUY,
    status: int = 4,
    quantity: int = 2,
    filled: int = 2,
    avg_price: str = "100",
    remark: str = "",
) -> RestOrder:
    return RestOrder(
        broker_order_id=order_id,
        symbol=symbol,
        side=side,
        status_code=status,
        status_label="TEST",
        quantity=quantity,
        filled_quantity=filled,
        price=Decimal("100"),
        average_fill_price=Decimal(avg_price),
        created_at_utc=now - timedelta(seconds=10),
        updated_at_utc=now - timedelta(seconds=5),
        order_type=1,
        time_in_force=0,
        trading_session=1,
        remark=remark,
    )


def test_correlation_tag_is_bounded_deterministic_and_not_an_idempotency_key():
    first = make_request(proposal_id="proposal-1")
    tag = build_correlation_tag(first.client_order_key)

    assert tag == build_correlation_tag(first.client_order_key)
    assert tag != build_correlation_tag(make_request(proposal_id="proposal-2").client_order_key)
    assert len(tag.encode("utf-8")) <= 100
    assert extract_correlation_tag(tag) == tag
    assert extract_correlation_tag(f"  {tag}\n") == tag
    assert extract_correlation_tag("operator note") is None

    duplicate_rows = [
        make_rest_order(NOW, order_id="broker-1", remark=tag),
        make_rest_order(NOW, order_id="broker-2", remark=tag),
    ]
    with pytest.raises(AmbiguousOrderMatchError, match="same correlation tag"):
        correlate_orders(tag, duplicate_rows)


def test_documented_order_payload_omits_market_order_price():
    request = make_request()
    tag = build_correlation_tag(request.client_order_key)

    payload = build_simulated_order_payload(request, account_market_id=100, remark=tag)

    assert payload == {
        "market": 100,
        "symbol": "US.SPY",
        "order_type": 3,
        "order_side": 1,
        "qty": "2",
        "text": tag,
        "order_trade_time_type": 1,
    }
    sell = build_simulated_order_payload(
        make_request(side=OrderSide.SELL), account_market_id=100, remark=tag
    )
    assert sell["order_side"] == 2


def test_adapter_refuses_writes_and_wrong_account(account):
    request = make_request()
    disabled = MoomooSimulatedOrderAdapter(account.account_fingerprint, 100)
    prepared = disabled.prepare(request, account)

    assert prepared.order_writes_enabled is False
    assert prepared.correlation_tag == build_correlation_tag(request.client_order_key)
    with pytest.raises(OrderWritesDisabledError, match="ORDER_WRITES_ENABLED is false"):
        disabled.submit(request, account)
    assert not hasattr(disabled, "_http")

    enabled_but_uninstalled = MoomooSimulatedOrderAdapter(
        account.account_fingerprint, 100, order_writes_enabled=True
    )
    with pytest.raises(OrderWritesDisabledError, match="transport is installed"):
        enabled_but_uninstalled.submit(request, account)

    wrong = account.model_copy(
        update={"account_fingerprint": "a" * 64, "environment": "paper"}
    )
    with pytest.raises(OrderAdapterError, match="fingerprint"):
        disabled.prepare(request, wrong)


@pytest.mark.parametrize(
    ("status", "filled", "expected_status", "fill_count"),
    [
        (1, 0, OrderStatus.ACKNOWLEDGED, 0),
        (2, 0, OrderStatus.ACKNOWLEDGED, 0),
        (3, 1, OrderStatus.PARTIALLY_FILLED, 1),
        (4, 2, OrderStatus.FILLED, 1),
        (5, 0, OrderStatus.CANCELLED, 0),
        (6, 0, OrderStatus.REJECTED, 0),
        (7, 1, OrderStatus.CANCELLED, 1),
    ],
)
def test_provider_statuses_map_strictly(
    now, account, status, filled, expected_status, fill_count
):
    request = make_request()
    order = make_rest_order(now, status=status, filled=filled, avg_price="101.5")

    record = to_order_record(order, request, account.account_fingerprint, now)

    assert record.status is expected_status
    assert len(record.fills) == fill_count
    if filled:
        assert record.fills[0].quantity == filled
        assert record.fills[0].price == Decimal("101.5")


def test_correlated_order_must_match_the_local_request(now, account):
    request = make_request()

    for order in [
        make_rest_order(now, symbol="SH"),
        make_rest_order(now, side=OrderSide.SELL),
        make_rest_order(now, quantity=3, filled=3),
    ]:
        with pytest.raises(OrderCorrelationError):
            to_order_record(order, request, account.account_fingerprint, now)


def test_merge_deduplicates_identical_history_rows_and_rejects_conflicts(now):
    first = make_rest_order(now, order_id="broker-1")
    duplicate = make_rest_order(now, order_id="broker-1")

    assert merge_correlated_orders([first], [duplicate]) == (first,)
    with pytest.raises(OrderCorrelationError, match="conflicting"):
        merge_correlated_orders([first], [make_rest_order(now, order_id="broker-1", filled=1, avg_price="99")])


class FakeProvider:
    def __init__(self, *, today, history, snapshot) -> None:
        self.today = today
        self.history = history
        self.snapshot = snapshot
        self.calls: list[str] = []

    def get_today_orders(self):
        self.calls.append("today")
        return tuple(self.today)

    def get_order_history(self):
        self.calls.append("history")
        return tuple(self.history)

    def get_account_snapshot(self):
        self.calls.append("positions")
        return self.snapshot


def make_unknown(account) -> OrderRecord:
    request = make_request()
    return OrderRecord(
        client_order_key=request.client_order_key,
        proposal_id=request.proposal_id,
        paper_account_fingerprint=account.account_fingerprint,
        broker_order_id=None,
        status=OrderStatus.UNKNOWN,
        request=request,
        submitted_at_utc=NOW,
    )


def test_unknown_reconciliation_uses_today_history_and_positions(now, account):
    local = make_unknown(account)
    tag = build_correlation_tag(local.client_order_key)
    match = make_rest_order(now, remark=tag)
    provider = FakeProvider(today=[], history=[match], snapshot=account)

    result = reconcile_unknown_order(local, provider, now)

    assert provider.calls == ["today", "history", "positions"]
    assert result.outcome == "MATCHED"
    assert result.record is not None
    assert result.record.status is OrderStatus.FILLED
    assert result.record.broker_order_id == "broker-1"


def test_unknown_reconciliation_keeps_no_match_and_ambiguous_unknown(now, account):
    local = make_unknown(account)
    tag = build_correlation_tag(local.client_order_key)

    no_match = reconcile_unknown_order(
        local, FakeProvider(today=[], history=[], snapshot=account), now
    )
    assert no_match.outcome == "NO_MATCH"
    assert no_match.record is None

    ambiguous = reconcile_unknown_order(
        local,
        FakeProvider(
            today=[make_rest_order(now, order_id="broker-1", remark=tag)],
            history=[make_rest_order(now, order_id="broker-2", remark=tag)],
            snapshot=account,
        ),
        now,
    )
    assert ambiguous.outcome == "AMBIGUOUS"
    assert ambiguous.record is None

    wrong_account = account.model_copy(
        update={"account_fingerprint": "b" * 64, "environment": "paper"}
    )
    mismatch = reconcile_unknown_order(
        local,
        FakeProvider(
            today=[make_rest_order(now, remark=tag)],
            history=[],
            snapshot=wrong_account,
        ),
        now,
    )
    assert mismatch.outcome == "ACCOUNT_MISMATCH"
    assert mismatch.record is None


def test_observation_allows_stale_display_but_not_execution():
    stale = quote_row(data_time=NOW_MS - 6_000_000)
    feed = MoomooQuoteFeed(make_client(quote_handler(quote=stale)))

    observation = feed.observe_quote("QQQ", NOW)

    assert observation.symbol == "QQQ"
    assert observation.price == Decimal("390.25")
    assert observation.age_seconds > 300
    assert observation.regular_session_open is True
    with pytest.raises(QuoteFeedError, match="stale"):
        feed.get_quote("QQQ", NOW)


def test_sub_second_provider_clock_skew_is_accepted():
    skewed = quote_row(data_time=NOW_MS + 1_000)
    execution_feed = MoomooQuoteFeed(make_client(quote_handler(quote=skewed)))

    quote = execution_feed.get_quote("QQQ", NOW)

    assert quote.symbol == "QQQ"
    assert quote.regular_session_open is True

    observation = MoomooQuoteFeed(
        make_client(quote_handler(quote=skewed))
    ).observe_quote("QQQ", NOW)
    assert observation.age_seconds == 0


def test_observation_rejects_future_timestamps_and_bad_status_flags():
    future = MoomooQuoteFeed(
        make_client(quote_handler(quote=quote_row(data_time=NOW_MS + 6_000)))
    )
    with pytest.raises(QuoteFeedError, match="future"):
        future.observe_quote("QQQ", NOW)

    bad = MoomooQuoteFeed(
        make_client(quote_handler(quote=quote_row(suspension="false")))
    )
    with pytest.raises(QuoteFeedError, match="suspension flag"):
        bad.observe_quote("QQQ", NOW)


class FakeReads:
    def __init__(self, snapshot, account_id: str, *, today=(), history=()):
        self.snapshot = snapshot
        self.account_id = account_id
        self.today = list(today)
        self.history = list(history)

    def get_account_snapshot(self):
        return self.snapshot

    def resolved_account_id(self) -> str:
        return self.account_id

    def get_today_orders(self):
        return tuple(self.today)

    def get_order_history(self):
        return tuple(self.history)


def make_paper_service(
    tmp_path,
    account,
    account_id,
    risk_gate,
    proposal,
    now,
    handler,
    *,
    order_writes_enabled=True,
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    key = build_client_order_key(proposal.strategy_version, proposal.proposal_id)
    ledger.approve_first_order(key, proposal.proposal_id, now, "test-owner")
    client = httpx.Client(
        transport=httpx.MockTransport(handler), trust_env=False
    )
    transport = MoomooOrderTransport(
        FakeAuth(), http=client, order_writes_enabled=order_writes_enabled
    )
    reads = FakeReads(account, account_id)
    broker = MoomooPaperBroker(
        reads,
        ledger,
        transport,
        expected_account_fingerprint=account.account_fingerprint,
        account_market_id=100,
        clock=lambda: now,
    )
    service = TradingService(
        broker=broker,
        risk_gate=risk_gate,
        ledger=ledger,
        order_writes_enabled=order_writes_enabled,
    )
    return ledger, reads, service


def acknowledged_handler(calls, *, order_id="broker-1"):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/v1.0/sim-trade/0000000000000101/orders"
        assert request.headers["authorization"] == "Bearer token-1"
        return httpx.Response(200, json={"ret_code": 0, "data": {"order_id": order_id}})

    return handler


def test_order_transport_is_disabled_by_default():
    calls = []
    transport = MoomooOrderTransport(
        FakeAuth(),
        http=httpx.Client(
            transport=httpx.MockTransport(lambda request: calls.append(request)),
            trust_env=False,
        ),
    )

    with pytest.raises(OrderWritesDisabledError, match="ORDER_WRITES_ENABLED is false"):
        transport.submit("0000000000000101", build_simulated_order_payload(
            make_request(), account_market_id=100, remark="MTP1-" + "0" * 64
        ))
    assert calls == []


def test_order_transport_never_retries_an_ambiguous_response():
    calls = []
    auth = FakeAuth()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, json={"ret_code": -1})

    transport = MoomooOrderTransport(
        auth,
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        order_writes_enabled=True,
    )

    with pytest.raises(OrderTransportError, match="ambiguous"):
        transport.submit("0000000000000101", {"market": 100, "symbol": "US.QQQ"})
    assert len(calls) == 1
    assert auth.refresh_calls == 0


def test_order_transport_refusal_reports_the_broker_message():
    handler = lambda request: httpx.Response(
        200, json={"ret_code": -5, "ret_msg": "market does not match the account"}
    )
    transport = MoomooOrderTransport(
        FakeAuth(),
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        order_writes_enabled=True,
    )

    with pytest.raises(
        OrderTransportError, match=r"ret_code=-5\) \(ret_msg='market does not match the account'\)"
    ):
        transport.submit("0000000000000101", {"market": 100, "symbol": "US.SH"})


def test_order_transport_refusal_without_ret_msg_reports_the_body():
    handler = lambda request: httpx.Response(200, json={"ret_code": -5, "data": {"err": "x"}})
    transport = MoomooOrderTransport(
        FakeAuth(),
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        order_writes_enabled=True,
    )

    with pytest.raises(OrderTransportError, match=r"ret_code=-5\) \(body=\{"):
        transport.submit("0000000000000101", {"market": 100, "symbol": "US.SH"})


def test_order_transport_rejects_an_unbound_account_path():
    calls = []
    transport = MoomooOrderTransport(
        FakeAuth(),
        http=httpx.Client(
            transport=httpx.MockTransport(lambda request: calls.append(request)),
            trust_env=False,
        ),
        order_writes_enabled=True,
    )

    with pytest.raises(OrderAdapterError, match="account id"):
        transport.submit("../accounts", {"market": 100})
    assert calls == []


def test_paper_broker_acknowledges_and_blocks_a_duplicate(
    tmp_path, account, account_id, risk_gate, proposal, quote, now
):
    calls = []
    ledger, _, service = make_paper_service(
        tmp_path, account, account_id, risk_gate, proposal, now,
        acknowledged_handler(calls),
    )

    first = service.execute(proposal, quote, now)
    second = service.execute(proposal, quote, now)

    assert first.decision.decision is PolicyDecision.APPROVE
    assert first.order.status is OrderStatus.ACKNOWLEDGED
    assert first.order.broker_order_id == "broker-1"
    assert first.order.fills == ()
    assert second.decision.decision is PolicyDecision.REJECT
    assert "R011" in {reason.rule_id for reason in second.decision.reasons}
    assert len(calls) == 1
    assert json.loads(calls[0].content) == {
        "market": 100,
        "symbol": "US.SPY",
        "order_type": 3,
        "order_side": 1,
        "qty": "2",
        "text": build_correlation_tag(first.order.client_order_key),
        "order_trade_time_type": 1,
    }
    ack = next(
        event for event in ledger.list_events() if event["event_type"] == "ORDER_ACKNOWLEDGED"
    )
    assert ack["source"] == "moomoo_paper"


def test_reconciliation_updates_a_partial_fill(
    tmp_path, account, account_id, risk_gate, proposal, quote, now
):
    calls = []
    ledger, reads, service = make_paper_service(
        tmp_path, account, account_id, risk_gate, proposal, now,
        acknowledged_handler(calls),
    )
    first = service.execute(proposal, quote, now)
    tag = build_correlation_tag(first.order.client_order_key)
    reads.today = [
        make_rest_order(now, symbol="SPY", status=3, filled=1, avg_price="100", remark=tag)
    ]

    reconciled = service.reconcile(first.order.client_order_key, now)

    assert reconciled is not None
    assert reconciled.status is OrderStatus.PARTIALLY_FILLED
    assert reconciled.fills[0].quantity == 1
    assert len(calls) == 1


def test_reconciliation_records_a_broker_rejection(
    tmp_path, account, account_id, risk_gate, proposal, quote, now
):
    calls = []
    _, reads, service = make_paper_service(
        tmp_path, account, account_id, risk_gate, proposal, now,
        acknowledged_handler(calls),
    )
    first = service.execute(proposal, quote, now)
    tag = build_correlation_tag(first.order.client_order_key)
    reads.today = [make_rest_order(now, symbol="SPY", status=6, filled=0, remark=tag)]

    reconciled = service.reconcile(first.order.client_order_key, now)

    assert reconciled is not None
    assert reconciled.status is OrderStatus.REJECTED
    assert reconciled.fills == ()


def test_transport_timeout_becomes_unknown_and_is_not_retried(
    tmp_path, account, account_id, risk_gate, proposal, quote, now
):
    calls = []

    def timeout(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("simulated ambiguous timeout")

    ledger, _, service = make_paper_service(
        tmp_path, account, account_id, risk_gate, proposal, now, timeout
    )

    first = service.execute(proposal, quote, now)
    second = service.execute(proposal, quote, now)

    assert first.order.status is OrderStatus.UNKNOWN
    assert ledger.has_unknown_submissions() is True
    assert second.decision.decision is PolicyDecision.REJECT
    assert len(calls) == 1


def test_malformed_acknowledgement_becomes_unknown(
    tmp_path, account, account_id, risk_gate, proposal, quote, now
):
    calls = []

    def malformed(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ret_code": 0, "data": {}})

    ledger, _, service = make_paper_service(
        tmp_path, account, account_id, risk_gate, proposal, now, malformed
    )

    result = service.execute(proposal, quote, now)

    assert result.order.status is OrderStatus.UNKNOWN
    assert ledger.has_unknown_submissions() is True
    assert len(calls) == 1
    assert "ORDER_UNKNOWN" in {event["event_type"] for event in ledger.list_events()}
