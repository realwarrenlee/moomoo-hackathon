from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.broker.account_lock import (
    AccountLock,
    AccountLockError,
    fingerprint_account_id,
)
from app.broker.moomoo_rest import (
    COMPETITION_ACCOUNT_TITLE,
    MoomooResponseError,
    MoomooRestBroker,
    MoomooRestClient,
    MoomooRestError,
    MoomooRestPermissionError,
    MoomooRestRateLimitError,
    MoomooRestReadOnlyError,
    RestOrder,
)

ACCOUNT_ID = "0000000000000101"
MASKED_ID = "****0101"
NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
NOW_US = int(NOW.timestamp() * 1_000_000)


def account_row(
    *,
    account_id: str = ACCOUNT_ID,
    title: str = COMPETITION_ACCOUNT_TITLE,
    account_type: int = 2,
    market_id: int = 100,
) -> dict:
    return {
        "account_id": account_id,
        "broker_id": 0,
        "market_id": market_id,
        "intra_account_id": 0,
        "account_type": account_type,
        "account_title": title,
    }


def cash_payload(
    *,
    balance: str = "100000",
    hold: str = "0",
    mv: str = "0",
    long_mv: str | None = None,
    short_mv: str = "0",
    total_asset: str | None = None,
) -> dict:
    long_value = Decimal(mv) if long_mv is None else Decimal(long_mv)
    total = Decimal(balance) + Decimal(mv) if total_asset is None else Decimal(total_asset)
    return {
        "balance": balance,
        "hold": hold,
        "max_power_long": "200000",
        "total_asset": str(total),
        "mv": mv,
        "long_mv": str(long_value),
        "short_mv": short_mv,
        "unrealized_profit": "0",
        "realized_profit": "0",
    }


def position_row(
    *,
    symbol: str = "IWM",
    quantity: str = "100",
    market_value: str = "10000",
    pstn_type: int = 0,
    market: int = 2,
) -> dict:
    return {
        "pstn_id": "1",
        "pstn_type": pstn_type,
        "market": market,
        "symbol": symbol,
        "stock_name": "iShares Russell 2000 ETF",
        "qty": quantity,
        "qty_avbl": quantity,
        "cost_price": "90",
        "buy_avg_price": "90",
        "cur_price": "100",
        "mv": market_value,
        "profit": "1000",
        "profit_ratio": "0.1",
    }


def order_row(
    *,
    order_id: str = "1294505",
    status: int = 5,
    side: int = 1,
    quantity: str = "1",
    filled: str = "0",
    price: str = "100",
    market: int = 2,
    symbol: str = "IWM",
    created: int = NOW_US - 10_000_000,
    updated: int = NOW_US - 5_000_000,
) -> dict:
    return {
        "order_id": order_id,
        "side": side,
        "market": market,
        "symbol": symbol,
        "stock_name": "iShares Russell 2000 ETF",
        "order_type": 1,
        "status": status,
        "qty": quantity,
        "cum_qty": filled,
        "price": price,
        "avg_fill_price": "0",
        "aux_price": None,
        "time_in_force": 0,
        "order_trade_time_type": 1,
        "create_time": str(created),
        "update_time": str(updated),
        "text": "",
    }


def payload(data: dict) -> dict:
    return {"ret_code": 0, "data": data}


class FakeLedger:
    def __init__(self) -> None:
        self.observations: list[dict] = []

    def observe_equity(
        self,
        account_fingerprint: str,
        equity: Decimal,
        observed_at_utc: datetime,
    ) -> tuple[Decimal, Decimal]:
        self.observations.append(
            {
                "account_fingerprint": account_fingerprint,
                "equity": equity,
                "observed_at_utc": observed_at_utc,
            }
        )
        return equity, equity


class FakeRestClient:
    def __init__(
        self,
        *,
        accounts: list | None = None,
        cash: dict | None = None,
        positions: list | None = None,
        orders: list | None = None,
        history_pages: list | None = None,
    ) -> None:
        self.accounts = [account_row()] if accounts is None else accounts
        self.cash = cash_payload() if cash is None else cash
        self.positions = [] if positions is None else positions
        self.orders = [] if orders is None else orders
        self.history_pages = (
            [{"orders": [], "pagination": {"has_more": False, "next_key": "0"}}]
            if history_pages is None
            else history_pages
        )
        self.calls: list[tuple[str, dict]] = []
        self.history_index = 0

    def get(self, path: str, params: dict | None = None) -> dict:
        self.calls.append((path, dict(params or {})))
        if path == "/api/v1.0/sim-trade/accounts":
            return payload({"accounts": self.accounts})
        if path.endswith("/cash-info"):
            return payload(self.cash)
        if path.endswith("/positions"):
            return payload({"positions": self.positions})
        if path.endswith("/orders"):
            return payload({"orders": self.orders})
        if path.endswith("/history-orders"):
            page = self.history_pages[min(self.history_index, len(self.history_pages) - 1)]
            self.history_index += 1
            return {
                "ret_code": 0,
                "data": {"orders": page.get("orders", [])},
                "pagination": page.get(
                    "pagination", {"has_more": False, "next_key": "0"}
                ),
            }
        raise AssertionError(f"unexpected REST path: {path}")


def make_lock(*, market_id: int = 100) -> AccountLock:
    return AccountLock(
        expected_masked_id=MASKED_ID,
        expected_fingerprint=fingerprint_account_id(ACCOUNT_ID),
        expected_market_id=market_id,
    )


def make_broker(
    client: FakeRestClient,
    *,
    lock: AccountLock | None = None,
    clock=None,
    max_latency: int = 15,
) -> MoomooRestBroker:
    return MoomooRestBroker(
        client,  # type: ignore[arg-type]
        lock or make_lock(),
        FakeLedger(),
        clock=clock or (lambda: NOW),
        max_observation_latency_seconds=max_latency,
    )


def test_snapshot_and_identity_are_sanitized_and_reconciled():
    client = FakeRestClient(
        orders=[order_row(status=2, quantity="2", price="100", order_id="open-1")]
    )
    broker = make_broker(client)

    identity = broker.account_identity()
    snapshot = broker.get_account_snapshot()

    assert identity.masked_id == MASKED_ID
    assert identity.account_type == 2
    assert identity.market_id == 100
    assert identity.title == COMPETITION_ACCOUNT_TITLE
    assert snapshot.environment == "paper"
    assert snapshot.equity == Decimal("100000")
    assert snapshot.cash == Decimal("100000")
    assert snapshot.buying_power == Decimal("100000")
    assert snapshot.reconciled is True
    assert snapshot.unknown_orders == 0
    assert len(snapshot.open_orders) == 1
    assert snapshot.open_orders[0].symbol == "IWM"
    assert snapshot.open_orders[0].side.value == "BUY"
    assert snapshot.open_orders[0].remaining_quantity == 2
    assert snapshot.open_orders[0].reference_price == Decimal("100")
    assert ACCOUNT_ID not in repr(snapshot)
    assert ACCOUNT_ID not in json.dumps(identity.__dict__)
    assert broker._ledger.observations[0]["account_fingerprint"] == fingerprint_account_id(
        ACCOUNT_ID
    )


def test_snapshot_reads_cash_positions_and_orders_with_market_filter():
    client = FakeRestClient(
        cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
        positions=[position_row()],
    )
    broker = make_broker(client)

    snapshot = broker.get_account_snapshot()

    assert snapshot.equity == Decimal("110000")
    assert snapshot.cash == Decimal("100000")
    assert snapshot.positions[0].symbol == "IWM"
    assert snapshot.positions[0].quantity == 100
    assert snapshot.positions[0].market_value == Decimal("10000")
    cash_call = next(call for call in client.calls if call[0].endswith("/cash-info"))
    positions_call = next(call for call in client.calls if call[0].endswith("/positions"))
    orders_call = next(call for call in client.calls if call[0].endswith("/orders"))
    assert cash_call[1] == {}
    assert positions_call[1] == {"market": 100}
    assert orders_call[1] == {"market": 100}


def test_position_row_accepts_live_us_account_market_id():
    client = FakeRestClient(
        cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
        positions=[position_row(market=100)],
    )
    snapshot = make_broker(client).get_account_snapshot()

    assert snapshot.positions[0].symbol == "IWM"

    with pytest.raises(MoomooResponseError, match="instrument market is not US"):
        make_broker(
            FakeRestClient(
                cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
                positions=[position_row(market=1)],
            )
        ).get_account_snapshot()


def test_position_total_tolerates_small_mark_drift():
    client = FakeRestClient(
        cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
        positions=[position_row(market_value="9999.50")],
    )
    snapshot = make_broker(client).get_account_snapshot()

    assert snapshot.positions[0].market_value == Decimal("9999.50")

    with pytest.raises(MoomooResponseError, match="position values"):
        make_broker(
            FakeRestClient(
                cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
                positions=[position_row(market_value="9000")],
            )
        ).get_account_snapshot()


@pytest.mark.parametrize(
    ("title", "account_type", "match"),
    [
        ("US Margin Account", 2, "title"),
        (COMPETITION_ACCOUNT_TITLE, 1, "type"),
    ],
)
def test_account_title_and_type_are_enforced(title, account_type, match):
    client = FakeRestClient(
        accounts=[account_row(title=title, account_type=account_type)]
    )
    broker = make_broker(client)

    with pytest.raises(AccountLockError, match=match):
        broker.account_identity()


def test_other_account_and_market_mismatch_fail_closed():
    other = FakeRestClient(accounts=[account_row(account_id="0000000000009999")])
    with pytest.raises(AccountLockError, match="not found"):
        make_broker(other).account_identity()

    with pytest.raises(AccountLockError, match="market"):
        make_broker(FakeRestClient(), lock=make_lock(market_id=1)).account_identity()


def test_empty_account_list_fails_closed():
    with pytest.raises(AccountLockError, match="not found"):
        make_broker(FakeRestClient(accounts=[])).account_identity()


def test_cash_or_position_mismatch_fails_closed():
    bad_cash = FakeRestClient(cash=cash_payload(total_asset="99999.98"))
    with pytest.raises(MoomooResponseError, match="total assets"):
        make_broker(bad_cash).get_account_snapshot()

    bad_positions = FakeRestClient(
        cash=cash_payload(mv="10000", total_asset="110000"),
        positions=[position_row(market_value="9000")],
    )
    with pytest.raises(MoomooResponseError, match="position values"):
        make_broker(bad_positions).get_account_snapshot()


def test_short_position_is_rejected():
    client = FakeRestClient(
        cash=cash_payload(mv="10000", total_asset="110000"),
        positions=[position_row(pstn_type=1)],
    )
    with pytest.raises(MoomooResponseError, match="long position"):
        make_broker(client).get_account_snapshot()


@pytest.mark.parametrize(
    ("status", "quantity", "filled", "expected_open"),
    [
        (1, "2", "0", 1),
        (2, "2", "0", 1),
        (3, "2", "1", 1),
        (4, "2", "2", 0),
        (5, "2", "0", 0),
        (6, "2", "0", 0),
        (7, "2", "1", 0),
    ],
)
def test_order_status_mapping(status, quantity, filled, expected_open):
    client = FakeRestClient(
        orders=[
            order_row(status=status, quantity=quantity, filled=filled, order_id="o-1")
        ]
    )

    snapshot = make_broker(client).get_account_snapshot()

    assert len(snapshot.open_orders) == expected_open


@pytest.mark.parametrize("status", [0, 8, 99])
def test_unrecognized_order_status_is_rejected(status):
    client = FakeRestClient(orders=[order_row(status=status)])

    with pytest.raises(MoomooResponseError, match="unrecognized order status"):
        make_broker(client).get_account_snapshot()


@pytest.mark.parametrize("side", [3, 4])
def test_short_sell_and_buy_back_sides_are_rejected(side):
    client = FakeRestClient(orders=[order_row(status=2, quantity="2", side=side)])

    with pytest.raises(MoomooResponseError, match="side"):
        make_broker(client).get_account_snapshot()


@pytest.mark.parametrize(
    ("row", "match"),
    [
        (order_row(status=2, quantity="2", market=1), "not US"),
        (order_row(status=2, quantity="2", price="0"), "remaining quantity or price"),
        (order_row(status=4, quantity="2", filled="1"), "not fully filled"),
        (order_row(status=2, quantity="2", filled="1"), "fill quantity"),
        (order_row(status=3, quantity="2", filled="0"), "fill quantity"),
        (order_row(status=6, quantity="2", filled="1"), "rejected order has fills"),
        (order_row(status=2, quantity="0"), "quantity is inconsistent"),
    ],
)
def test_open_order_consistency_checks(row, match):
    client = FakeRestClient(orders=[row])

    with pytest.raises(MoomooResponseError, match=match):
        make_broker(client).get_account_snapshot()


def test_order_timestamps_are_validated():
    assert isinstance(
        make_broker(FakeRestClient(orders=[order_row(status=2, quantity="2")]))
        .get_account_snapshot()
        .as_of_utc,
        datetime,
    )

    future = order_row(
        status=2,
        quantity="2",
        created=NOW_US + 3_600_000_000,
        updated=NOW_US + 3_600_000_000,
    )
    with pytest.raises(MoomooResponseError, match="future"):
        make_broker(FakeRestClient(orders=[future])).get_account_snapshot()

    backwards = order_row(
        status=2,
        quantity="2",
        created=NOW_US - 1_000_000,
        updated=NOW_US - 2_000_000,
    )
    with pytest.raises(MoomooResponseError, match="precedes creation"):
        make_broker(FakeRestClient(orders=[backwards])).get_account_snapshot()


def test_history_paginates_and_maps_statuses():
    first = order_row(
        order_id="h-1", status=4, quantity="2", filled="2", symbol="QQQ"
    )
    first["avg_fill_price"] = "101.5"
    second = order_row(order_id="h-2", status=5, quantity="3", symbol="SPY")
    client = FakeRestClient(
        history_pages=[
            {
                "orders": [first],
                "pagination": {"has_more": True, "next_key": "cursor-1"},
            },
            {
                "orders": [second],
                "pagination": {"has_more": False, "next_key": "0"},
            },
        ]
    )

    history = make_broker(client).get_order_history()

    assert len(history) == 2
    assert history[0].status_label == "FILLED"
    assert history[0].average_fill_price == Decimal("101.5")
    assert history[1].status_label == "CANCELLED"
    history_calls = [call for call in client.calls if call[0].endswith("/history-orders")]
    assert history_calls[0][1] == {"market": 100, "page_size": 100}
    assert history_calls[1][1] == {
        "market": 100,
        "page_size": 100,
        "next_key": "cursor-1",
    }


def test_history_allows_missing_instrument_market():
    row = order_row(status=5)
    row["market"] = None
    client = FakeRestClient(
        history_pages=[
            {"orders": [row], "pagination": {"has_more": False, "next_key": "0"}}
        ]
    )

    history = make_broker(client).get_order_history()

    assert history[0].symbol == "IWM"


def test_history_rejects_missing_pagination_and_repeated_cursor():
    missing = FakeRestClient(
        history_pages=[{"orders": [], "pagination": None}]
    )
    with pytest.raises(MoomooRestError, match="pagination"):
        make_broker(missing).get_order_history()

    repeated = FakeRestClient(
        history_pages=[
            {"orders": [], "pagination": {"has_more": True, "next_key": "same"}},
            {"orders": [], "pagination": {"has_more": True, "next_key": "same"}},
        ]
    )
    with pytest.raises(MoomooRestError, match="repeated"):
        make_broker(repeated).get_order_history()


def test_history_rejects_missing_or_non_bool_pagination():
    missing_key = FakeRestClient(
        history_pages=[
            {"orders": [], "pagination": {"has_more": True, "next_key": ""}}
        ]
    )
    with pytest.raises(MoomooRestError, match="next key"):
        make_broker(missing_key).get_order_history()

    bad_flag = FakeRestClient(
        history_pages=[
            {"orders": [], "pagination": {"has_more": "false", "next_key": "0"}}
        ]
    )
    with pytest.raises(MoomooRestError, match="has_more"):
        make_broker(bad_flag).get_order_history()


def test_history_page_limit_is_enforced():
    pages = [
        {
            "orders": [],
            "pagination": {"has_more": True, "next_key": f"cursor-{index}"},
        }
        for index in range(11)
    ]
    client = FakeRestClient(history_pages=pages)

    with pytest.raises(MoomooRestError, match="page limit"):
        make_broker(client).get_order_history()


def test_observation_latency_is_bounded():
    clock = iter([NOW, NOW + timedelta(seconds=16)])

    with pytest.raises(MoomooResponseError, match="latency"):
        make_broker(FakeRestClient(), clock=lambda: next(clock)).get_account_snapshot()


def test_read_only_methods_cannot_submit_or_fetch_an_order():
    broker = make_broker(FakeRestClient())

    with pytest.raises(MoomooRestReadOnlyError):
        broker.get_order("key")
    with pytest.raises(MoomooRestReadOnlyError):
        broker.submit_order(object(), NOW)


def test_snapshot_id_is_stable_for_identical_state():
    client = FakeRestClient(
        orders=[order_row(status=2, quantity="2", price="100", order_id="open-1")]
    )
    broker = make_broker(client)

    first = broker.get_account_snapshot()
    second = broker.get_account_snapshot()

    assert first.snapshot_id == second.snapshot_id


def test_snapshot_id_ignores_mark_drift_but_tracks_state_changes():
    positions = [position_row(market_value="10000")]
    cash = cash_payload(balance="100000", mv="10000", total_asset="110000")
    broker = make_broker(FakeRestClient(cash=cash, positions=positions))

    baseline = broker.get_account_snapshot().snapshot_id

    drifted = make_broker(
        FakeRestClient(
            cash=cash_payload(balance="100000", mv="10001", total_asset="110001"),
            positions=[position_row(market_value="10001")],
        )
    ).get_account_snapshot()
    assert drifted.snapshot_id == baseline

    state_changed = make_broker(
        FakeRestClient(
            cash=cash_payload(balance="99999", mv="10000", total_asset="109999"),
            positions=positions,
        )
    ).get_account_snapshot()
    assert state_changed.snapshot_id != baseline


@pytest.mark.parametrize(
    "changed_client",
    [
        pytest.param(
            FakeRestClient(
                cash=cash_payload(balance="100000", mv="10100", total_asset="110100"),
                positions=[position_row(quantity="101", market_value="10100")],
            ),
            id="position-quantity-change",
        ),
        pytest.param(
            FakeRestClient(
                cash=cash_payload(balance="100000", mv="0", total_asset="100000"),
                positions=[],
            ),
            id="position-removed",
        ),
        pytest.param(
            FakeRestClient(
                cash=cash_payload(balance="100000", mv="15000", total_asset="115000"),
                positions=[
                    position_row(market_value="10000"),
                    position_row(symbol="SPY", quantity="10", market_value="5000"),
                ],
            ),
            id="position-added",
        ),
        pytest.param(
            FakeRestClient(
                cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
                positions=[position_row(market_value="10000")],
                orders=[
                    order_row(
                        status=2, quantity="3", price="100", order_id="open-1"
                    )
                ],
            ),
            id="pending-order-quantity-change",
        ),
        pytest.param(
            FakeRestClient(
                cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
                positions=[position_row(market_value="10000")],
                orders=[],
            ),
            id="pending-order-removed",
        ),
        pytest.param(
            FakeRestClient(
                cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
                positions=[position_row(market_value="10000")],
                orders=[
                    order_row(status=2, quantity="2", price="100", order_id="open-1"),
                    order_row(
                        status=2,
                        quantity="1",
                        price="90",
                        order_id="open-2",
                        symbol="SPY",
                    ),
                ],
            ),
            id="pending-order-added",
        ),
        pytest.param(
            FakeRestClient(
                cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
                positions=[position_row(market_value="10000")],
                orders=[
                    order_row(
                        status=2,
                        quantity="2",
                        price="100",
                        order_id="open-1",
                        side=2,
                    )
                ],
            ),
            id="pending-order-side-change",
        ),
    ],
)
def test_snapshot_id_changes_for_each_state_change_class(changed_client):
    baseline = make_broker(
        FakeRestClient(
            cash=cash_payload(balance="100000", mv="10000", total_asset="110000"),
            positions=[position_row(market_value="10000")],
            orders=[order_row(status=2, quantity="2", price="100", order_id="open-1")],
        )
    ).get_account_snapshot().snapshot_id

    changed = make_broker(changed_client).get_account_snapshot()

    assert changed.snapshot_id != baseline


class FakeAuth:
    def __init__(self) -> None:
        self.token = "token-1"
        self.refresh_calls = 0

    def access_token(self) -> str:
        return self.token

    def refresh(self) -> None:
        self.refresh_calls += 1
        self.token = f"token-{self.refresh_calls + 1}"


def make_rest_client(handler, auth: FakeAuth | None = None) -> MoomooRestClient:
    return MoomooRestClient(
        auth or FakeAuth(),
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
    )


def test_client_only_permits_documented_read_paths():
    client = make_rest_client(
        lambda request: httpx.Response(200, json=payload({"accounts": []}))
    )

    assert client.get("/api/v1.0/sim-trade/accounts")["ret_code"] == 0
    for path in [
        "/api/v1.0/sim-trade/123/cash-info",
        "/api/v1.0/sim-trade/123/positions",
        "/api/v1.0/sim-trade/123/orders",
        "/api/v1.0/sim-trade/123/history-orders",
    ]:
        assert client.get(path)["ret_code"] == 0

    for path in [
        "/api/v1.0/sim-trade/123/orders/../cancel",
        "/api/v1.0/sim-trade/123/cancel-order",
        "/api/v1.0/sim-trade/123/orders?market=100",
        "/api/v1.0/trade/accounts",
        "/api/v1.0/sim-trade/accounts/",
    ]:
        with pytest.raises(MoomooRestReadOnlyError):
            client.get(path)

    assert not hasattr(client, "post")


def test_client_refreshes_once_on_401_and_uses_new_token():
    auth = FakeAuth()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers["authorization"])
        if len(calls) == 1:
            return httpx.Response(401, json={"ret_code": -12102})
        return httpx.Response(200, json=payload({"accounts": []}))

    client = make_rest_client(handler, auth)
    result = client.get("/api/v1.0/sim-trade/accounts")

    assert result["ret_code"] == 0
    assert auth.refresh_calls == 1
    assert calls == ["Bearer token-1", "Bearer token-2"]


def test_client_refreshes_once_on_business_expiry():
    auth = FakeAuth()
    responses = iter(
        [
            httpx.Response(200, json={"ret_code": -12102}),
            httpx.Response(200, json=payload({"accounts": []})),
        ]
    )

    client = make_rest_client(lambda request: next(responses), auth)
    result = client.get("/api/v1.0/sim-trade/accounts")

    assert result["ret_code"] == 0
    assert auth.refresh_calls == 1


def test_client_second_401_is_fatal():
    auth = FakeAuth()
    client = make_rest_client(
        lambda request: httpx.Response(401, json={"ret_code": -12006}), auth
    )

    with pytest.raises(MoomooRestError, match="authentication failed"):
        client.get("/api/v1.0/sim-trade/accounts")
    assert auth.refresh_calls == 1


def test_client_permission_and_rate_limit_errors_do_not_retry():
    auth = FakeAuth()
    permission = make_rest_client(
        lambda request: httpx.Response(439, json={"ret_code": -12009}), auth
    )
    with pytest.raises(MoomooRestPermissionError):
        permission.get("/api/v1.0/sim-trade/accounts")
    assert auth.refresh_calls == 0

    rate_limit = make_rest_client(
        lambda request: httpx.Response(429, json={"ret_code": -12011}), auth
    )
    with pytest.raises(MoomooRestRateLimitError):
        rate_limit.get("/api/v1.0/sim-trade/accounts")
    assert auth.refresh_calls == 0


def test_client_business_error_does_not_leak_request_path():
    auth = FakeAuth()
    client = make_rest_client(
        lambda request: httpx.Response(200, json={"ret_code": -5}), auth
    )

    with pytest.raises(MoomooRestError) as excinfo:
        client.get("/api/v1.0/sim-trade/987654321/orders")

    assert "987654321" not in str(excinfo.value)
    assert auth.refresh_calls == 0


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"data": {"accounts": []}}',
        b'{"ret_code": "0", "data": {"accounts": []}}',
        b'{"ret_code": true, "data": {"accounts": []}}',
        b'{"ret_code": 0, "data": []}',
    ],
)
def test_client_rejects_malformed_responses(body):
    client = make_rest_client(lambda request: httpx.Response(200, content=body))

    with pytest.raises(MoomooRestError):
        client.get("/api/v1.0/sim-trade/accounts")


def test_client_rejects_a_non_official_base_url():
    with pytest.raises(ValueError):
        MoomooRestClient(FakeAuth(), base_url="https://example.com")


def test_client_passes_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=payload({"orders": []}))

    client = make_rest_client(handler)
    client.get("/api/v1.0/sim-trade/123/orders", {"market": 100})

    assert seen["params"] == {"market": "100"}
