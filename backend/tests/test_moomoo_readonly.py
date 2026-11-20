from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest

from app.broker.account_lock import AccountLock, AccountLockError
from app.broker.moomoo_readonly import (
    ORDER_WRITE_TOOLS,
    READ_ONLY_TOOLS,
    MoomooReadOnlyBroker,
    MoomooResponseError,
    ReadOnlyViolation,
    call_read_only_tool,
)
from app.ledger.store import SQLiteLedger
from app.models.contracts import ControlState, OpenOrder, OrderRequest, OrderSide, Quote
from app.risk.policy import RiskGate

COMPETITION_TITLE = "Moomoo x Qoder AI Paper Trading Agent Challenge"
DECOY_IDS = (
    "0000000000000201",
    "0000000000000202",
    "0000000000000203",
    "0000000000000204",
    "0000000000000205",
    "0000000000000206",
    "0000000000000207",
)


def account_row(account_id, *, title, market_id=100, account_type=1, **extra):
    row = {
        "account_id": account_id,
        "account_title": title,
        "account_type": account_type,
        "broker_id": 0,
        "intra_account_id": 0,
        "market_id": market_id,
    }
    row.update(extra)
    return row


def account_rows(account_id, *, exact_extra=None, include_exact=True):
    rows = [
        account_row(DECOY_IDS[0], title="US Margin Account [Paper Trading]", market_id=100),
        account_row(DECOY_IDS[1], title="HK Stock Paper Trading", market_id=1),
        account_row(DECOY_IDS[2], title="SG Stock Paper Trading", market_id=14),
        account_row(DECOY_IDS[3], title="JP Stock Paper Trading", market_id=16),
        account_row(DECOY_IDS[4], title="US Futures Paper Trading", market_id=11),
        account_row(DECOY_IDS[5], title="SG Futures Paper Trading", market_id=12),
        account_row(DECOY_IDS[6], title="KR Margin Account [Paper Trading]", market_id=102),
    ]
    if include_exact:
        row = account_row(account_id, title=COMPETITION_TITLE, account_type=2)
        row.update(exact_extra or {})
        rows.append(row)
    return rows


def cash_payload(
    *,
    balance="100000",
    hold="0",
    max_power_long="200000",
    total_asset=None,
    mv="0",
    long_mv=None,
    short_mv="0",
):
    long_mv = mv if long_mv is None else long_mv
    total_asset = str(Decimal(balance) + Decimal(mv)) if total_asset is None else total_asset
    return {
        "balance": balance,
        "hold": hold,
        "long_mv": long_mv,
        "max_power_long": max_power_long,
        "mv": mv,
        "realized_profit": None,
        "short_mv": short_mv,
        "total_asset": total_asset,
        "unrealized_profit": None,
    }


def position_row(symbol="QQQ", *, qty="2", mv="200", pstn_type=0):
    return {
        "pstn_id": f"position-{symbol}",
        "pstn_type": pstn_type,
        "market": 2,
        "symbol": symbol,
        "stock_name": symbol,
        "qty": qty,
        "qty_avbl": qty,
        "cost_price": "100",
        "buy_avg_price": "100",
        "cur_price": "100",
        "mv": mv,
        "profit": "0",
        "profit_ratio": "0",
    }


def order_row(
    symbol="QQQ",
    *,
    status="SUBMITTED",
    side="BUY",
    qty="2",
    dealt_qty="0",
    price="100",
    currency="USD",
):
    return {
        "order_id": "broker-order-1",
        "code": f"US.{symbol}",
        "stock_name": symbol,
        "security_type": "STOCK",
        "side": side,
        "order_type": "LIMIT",
        "order_status": status,
        "qty": qty,
        "price": price,
        "aux_price": "0",
        "dealt_qty": dealt_qty,
        "dealt_avg_price": "0",
        "currency": currency,
        "time_in_force": "DAY",
        "session": "RTH",
        "create_time": 0,
        "updated_time": 0,
        "last_err_msg": "",
        "remark": "",
        "trail_type": "NONE",
        "trail_value": "",
        "trail_spread": "",
    }


def page(orders=(), *, has_more=False, next_key="0"):
    return {"orders": list(orders), "pagination": {"has_more": has_more, "next_key": next_key}}


class FakeCaller:
    def __init__(
        self,
        *,
        accounts,
        cash=None,
        positions=None,
        pages=None,
        overrides=None,
    ):
        self.accounts = accounts
        self.cash = cash if cash is not None else cash_payload()
        self.positions = positions if positions is not None else []
        self.pages = pages if pages is not None else [page()]
        self.overrides = overrides or {}
        self.calls = []
        self.history_page = 0

    def __call__(self, tool_name, arguments):
        self.calls.append((tool_name, deepcopy(dict(arguments))))
        if tool_name in self.overrides:
            value = self.overrides[tool_name]
            if callable(value):
                return value()
            return deepcopy(value)
        if tool_name == "sim_trade_account_list":
            return {"ret_code": 0, "ret_msg": "success", "data": {"accounts": deepcopy(self.accounts)}}
        if tool_name == "sim_trade_cash_info":
            return {"ret_code": 0, "ret_msg": "success", "data": deepcopy(self.cash)}
        if tool_name == "sim_trade_position_list":
            return {"ret_code": 0, "ret_msg": "success", "data": {"positions": deepcopy(self.positions)}}
        if tool_name == "sim_trade_history_order_list":
            current = self.pages[min(self.history_page, len(self.pages) - 1)]
            self.history_page += 1
            return {
                "ret_code": 0,
                "ret_msg": "success",
                "data": {"orders": deepcopy(current["orders"])},
                "pagination": deepcopy(current["pagination"]),
            }
        raise AssertionError(f"unexpected tool {tool_name}")


def make_lock(account_fingerprint, *, masked_id="****0101", market_id=100):
    return AccountLock(
        expected_masked_id=masked_id,
        expected_fingerprint=account_fingerprint,
        expected_market_id=market_id,
    )


def make_broker(caller, tmp_path, account_fingerprint, clock, *, max_latency=15):
    return MoomooReadOnlyBroker(
        caller=caller,
        account_lock=make_lock(account_fingerprint),
        ledger=SQLiteLedger(tmp_path / "audit.db"),
        clock=clock,
        max_observation_latency_seconds=max_latency,
    )


def test_exact_competition_account_is_selected_and_converted(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(accounts=account_rows(account_id))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    snapshot = broker.get_account_snapshot()

    assert snapshot.account_fingerprint == account_fingerprint
    assert snapshot.environment == "paper"
    assert snapshot.equity == Decimal("100000")
    assert snapshot.day_start_equity == Decimal("100000")
    assert snapshot.peak_equity == Decimal("100000")
    assert snapshot.cash == Decimal("100000")
    assert snapshot.buying_power == Decimal("100000")
    assert snapshot.positions == ()
    assert snapshot.open_orders == ()
    assert snapshot.reconciled is True
    assert snapshot.unknown_orders == 0
    assert snapshot.snapshot_id.startswith("mm-")
    assert account_id not in snapshot.model_dump_json()
    assert [name for name, _ in caller.calls] == [
        "sim_trade_account_list",
        "sim_trade_cash_info",
        "sim_trade_position_list",
        "sim_trade_history_order_list",
    ]
    assert caller.calls[0][1] == {}
    assert caller.calls[1][1] == {"acc_id": account_id}
    assert caller.calls[2][1] == {"acc_id": account_id, "market": 100}
    assert caller.calls[3][1]["page_size"] == 100


def test_margin_buying_power_is_not_propagated_and_risk_gate_uses_cash(
    tmp_path, now, account_id, account_fingerprint, proposal
):
    caller = FakeCaller(accounts=account_rows(account_id))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)
    snapshot = broker.get_account_snapshot()

    assert snapshot.cash == Decimal("100000")
    assert snapshot.buying_power == Decimal("100000")
    assert snapshot.buying_power != Decimal("200000")

    quote = Quote(
        symbol="QQQ",
        price=Decimal("1000"),
        as_of_utc=now,
        regular_session_open=True,
    )
    gate = RiskGate(
        expected_account_fingerprint=account_fingerprint,
        max_effective_exposure_fraction=Decimal("1.50"),
    )
    control = ControlState(order_writes_enabled=True, first_order_approved=True)
    decision = gate.evaluate(
        proposal.model_copy(update={"requested_quantity": 150}),
        snapshot,
        quote,
        control,
        now,
    )

    assert "R008" in {reason.rule_id for reason in decision.reasons}


def test_other_paper_accounts_are_rejected(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(accounts=account_rows(account_id, include_exact=False))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(AccountLockError, match="not found"):
        broker.get_account_snapshot()
    assert [name for name, _ in caller.calls] == ["sim_trade_account_list"]


def test_live_account_with_matching_identity_is_rejected(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(
        accounts=account_rows(account_id, exact_extra={"trd_env": "LIVE"})
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(AccountLockError, match="live account"):
        broker.get_account_snapshot()
    assert [name for name, _ in caller.calls] == ["sim_trade_account_list"]


def test_duplicate_competition_identity_is_rejected(
    tmp_path, now, account_id, account_fingerprint
):
    rows = account_rows(account_id)
    rows.append(account_row(account_id, title=COMPETITION_TITLE, account_type=2))
    caller = FakeCaller(accounts=rows)
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(AccountLockError, match="multiple"):
        broker.get_account_snapshot()


def test_market_mismatch_is_rejected(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(accounts=account_rows(account_id, exact_extra={"market_id": 1}))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(AccountLockError, match="market"):
        broker.get_account_snapshot()


def test_malformed_account_list_fails_closed(tmp_path, now, account_fingerprint):
    caller = FakeCaller(
        accounts=[],
        overrides={"sim_trade_account_list": {"ret_code": 0, "data": {"accounts": "bad"}}},
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="accounts"):
        broker.get_account_snapshot()


def test_provider_error_fails_closed(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        overrides={"sim_trade_cash_info": {"ret_code": -1, "ret_msg": "unauthorized"}},
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="ret_code=-1"):
        broker.get_account_snapshot()


def test_provider_exception_is_wrapped_without_account_id(
    tmp_path, now, account_id, account_fingerprint
):
    def fail():
        raise RuntimeError(f"upstream rejected {account_id}")

    caller = FakeCaller(
        accounts=account_rows(account_id),
        overrides={"sim_trade_cash_info": fail},
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError) as excinfo:
        broker.get_account_snapshot()

    assert account_id not in str(excinfo.value)


def test_missing_cash_field_fails_closed(tmp_path, now, account_id, account_fingerprint):
    cash = cash_payload()
    del cash["total_asset"]
    caller = FakeCaller(accounts=account_rows(account_id), cash=cash)
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="total_asset"):
        broker.get_account_snapshot()


def test_invalid_decimal_fails_closed(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        cash=cash_payload(balance="not-a-number", total_asset="100000"),
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="balance"):
        broker.get_account_snapshot()


def test_short_market_value_fails_closed(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        cash=cash_payload(mv="100", short_mv="100", long_mv="0"),
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="short market value"):
        broker.get_account_snapshot()


def test_mismatched_total_assets_fails_closed(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        cash=cash_payload(total_asset="100001"),
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="total assets"):
        broker.get_account_snapshot()


def test_short_position_fails_closed(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        cash=cash_payload(mv="100", long_mv="100"),
        positions=[position_row(pstn_type=1)],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="short positions"):
        broker.get_account_snapshot()


def test_position_total_mismatch_fails_closed(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        positions=[position_row(qty="1", mv="100")],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="position totals"):
        broker.get_account_snapshot()


def test_open_and_partially_filled_orders_are_preserved(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        pages=[
            page(
                [
                    order_row("QQQ", status="SUBMITTED", qty="2"),
                    order_row("SPY", status="FILLED_PART", qty="3", dealt_qty="1"),
                    order_row("IWM", status="FILLED_ALL", qty="1", dealt_qty="1"),
                ]
            )
        ],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    snapshot = broker.get_account_snapshot()

    assert snapshot.reconciled is True
    assert snapshot.open_orders == (
        OpenOrder(
            symbol="QQQ",
            side=OrderSide.BUY,
            remaining_quantity=2,
            reference_price=Decimal("100"),
        ),
        OpenOrder(
            symbol="SPY",
            side=OrderSide.BUY,
            remaining_quantity=2,
            reference_price=Decimal("100"),
        ),
    )


def test_unknown_order_status_blocks_reconciliation(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        pages=[page([order_row(status="UNKNOWN")])],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    snapshot = broker.get_account_snapshot()

    assert snapshot.unknown_orders == 1
    assert snapshot.reconciled is False


def test_short_order_fails_closed(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        pages=[page([order_row(side="SELL_SHORT")])],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="short-selling"):
        broker.get_account_snapshot()


def test_unrecognized_order_status_fails_closed(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        pages=[page([order_row(status="MYSTERY_STATUS")])],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="unrecognized"):
        broker.get_account_snapshot()


def test_non_usd_open_order_fails_closed(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        pages=[page([order_row(currency="HKD")])],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="currency"):
        broker.get_account_snapshot()


def test_order_history_paginates(tmp_path, now, account_id, account_fingerprint):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        pages=[
            page([order_row("QQQ")], has_more=True, next_key="page-2"),
            page([order_row("SPY", qty="1")]),
        ],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    snapshot = broker.get_account_snapshot()

    history_calls = [args for name, args in caller.calls if name == "sim_trade_history_order_list"]
    assert len(history_calls) == 2
    assert history_calls[1]["next_key"] == "page-2"
    assert tuple(item.symbol for item in snapshot.open_orders) == ("QQQ", "SPY")


def test_repeated_pagination_cursor_fails_closed(
    tmp_path, now, account_id, account_fingerprint
):
    repeated = page([], has_more=True, next_key="same")
    caller = FakeCaller(accounts=account_rows(account_id), pages=[repeated, repeated])
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="cursor repeated"):
        broker.get_account_snapshot()


def test_missing_pagination_cursor_fails_closed(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        pages=[page([], has_more=True, next_key="")],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(MoomooResponseError, match="next_key"):
        broker.get_account_snapshot()


def test_stale_observation_fails_closed(tmp_path, now, account_id, account_fingerprint):
    times = iter([now, now + timedelta(seconds=16)])
    caller = FakeCaller(accounts=account_rows(account_id))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: next(times), max_latency=15)

    with pytest.raises(MoomooResponseError, match="stale"):
        broker.get_account_snapshot()


def test_backwards_observation_time_fails_closed(
    tmp_path, now, account_id, account_fingerprint
):
    times = iter([now, now - timedelta(seconds=1)])
    caller = FakeCaller(accounts=account_rows(account_id))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: next(times))

    with pytest.raises(MoomooResponseError, match="stale"):
        broker.get_account_snapshot()


def test_snapshot_id_is_stable_for_unchanged_data(
    tmp_path, now, account_id, account_fingerprint
):
    times = iter([now, now, now + timedelta(seconds=1), now + timedelta(seconds=1)])
    caller = FakeCaller(accounts=account_rows(account_id))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: next(times))

    first = broker.get_account_snapshot()
    second = broker.get_account_snapshot()

    assert first.snapshot_id == second.snapshot_id
    assert first.as_of_utc != second.as_of_utc


def test_snapshot_id_changes_when_account_data_changes(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(accounts=account_rows(account_id))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)
    first = broker.get_account_snapshot()
    caller.cash = cash_payload(balance="99000")

    second = broker.get_account_snapshot()

    assert first.snapshot_id != second.snapshot_id


def test_equity_baseline_persists_across_observations(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(accounts=account_rows(account_id))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)
    first = broker.get_account_snapshot()

    caller.cash = cash_payload(balance="98000")
    second = broker.get_account_snapshot()
    caller.cash = cash_payload(balance="101000")
    third = broker.get_account_snapshot()

    next_day = now + timedelta(days=1)
    caller.cash = cash_payload(balance="99000")
    restarted = make_broker(caller, tmp_path, account_fingerprint, lambda: next_day)
    fourth = restarted.get_account_snapshot()

    assert (first.day_start_equity, first.peak_equity) == (Decimal("100000"), Decimal("100000"))
    assert (second.day_start_equity, second.peak_equity) == (Decimal("100000"), Decimal("100000"))
    assert (third.day_start_equity, third.peak_equity) == (Decimal("100000"), Decimal("101000"))
    assert (fourth.day_start_equity, fourth.peak_equity) == (Decimal("99000"), Decimal("99000"))


def test_cash_uses_balance_minus_frozen_funds(
    tmp_path, now, account_id, account_fingerprint
):
    caller = FakeCaller(
        accounts=account_rows(account_id),
        cash=cash_payload(balance="100000", hold="100", mv="100", long_mv="100"),
        positions=[position_row(qty="1", mv="100")],
    )
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    snapshot = broker.get_account_snapshot()

    assert snapshot.cash == Decimal("99900")
    assert snapshot.buying_power == Decimal("99900")
    assert snapshot.equity == Decimal("100100")


def test_order_write_tool_names_are_not_in_read_only_allowlist():
    assert ORDER_WRITE_TOOLS.isdisjoint(READ_ONLY_TOOLS)
    assert len(ORDER_WRITE_TOOLS) == 10
    assert ORDER_WRITE_TOOLS == {
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


def test_order_tool_call_is_rejected_before_the_caller(
    tmp_path, account_id
):
    caller = FakeCaller(accounts=account_rows(account_id))

    with pytest.raises(ReadOnlyViolation, match="read-only allowlist"):
        call_read_only_tool(caller, "sim_trade_input_order", {})

    assert caller.calls == []


def test_adapter_has_no_order_submission_path(
    tmp_path, now, account_id, account_fingerprint, proposal, quote
):
    caller = FakeCaller(accounts=account_rows(account_id))
    broker = make_broker(caller, tmp_path, account_fingerprint, lambda: now)

    with pytest.raises(ReadOnlyViolation, match="cannot submit"):
        broker.submit_order(
            request=OrderRequest(
                client_order_key="key-1",
                proposal_id=proposal.proposal_id,
                account_snapshot_id="snapshot-1",
                symbol="QQQ",
                side=OrderSide.BUY,
                quantity=1,
                reference_price=quote.price,
            ),
            now=now,
        )
    with pytest.raises(ReadOnlyViolation, match="cannot read"):
        broker.get_order("key-1")

    assert caller.calls == []
