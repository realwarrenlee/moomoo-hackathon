import sqlite3
from decimal import Decimal

import pytest

from app.ledger.store import SQLiteLedger
from app.models.contracts import OrderRecord, OrderRequest, OrderSide, OrderStatus


def test_events_are_append_only(tmp_path, now):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    ledger.append_event("TEST_EVENT", now, "run-1", "test", {"value": 1})

    with pytest.raises(sqlite3.IntegrityError):
        with sqlite3.connect(ledger.path) as connection:
            connection.execute("UPDATE events SET event_type = 'CHANGED'")
    with pytest.raises(sqlite3.IntegrityError):
        with sqlite3.connect(ledger.path) as connection:
            connection.execute("DELETE FROM events")

    assert len(ledger.list_events()) == 1


def test_first_order_approval_persists_across_restart(tmp_path, now):
    path = tmp_path / "audit.db"
    ledger = SQLiteLedger(path)
    ledger.approve_first_order("key-1", "proposal-1", now, "owner")

    restarted = SQLiteLedger(path)

    assert restarted.is_first_order_approved("key-1", "proposal-1") is True
    assert restarted.is_first_order_approved("key-1", "proposal-2") is False
    assert restarted.is_first_order_approved("key-2", "proposal-1") is False


def test_illegal_order_transition_is_rejected(tmp_path):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    request = OrderRequest(
        client_order_key="key-1",
        proposal_id="proposal-1",
        account_snapshot_id="snapshot-1",
        symbol="QQQ",
        side=OrderSide.BUY,
        quantity=1,
        reference_price=Decimal("100"),
    )
    assert ledger.reserve_submission(request)
    filled = OrderRecord(
        client_order_key="key-1",
        proposal_id="proposal-1",
        paper_account_fingerprint="fingerprint",
        status=OrderStatus.FILLED,
        request=request,
    )
    ledger.record_order(filled)

    with pytest.raises(ValueError, match="illegal order transition"):
        ledger.record_order(filled.model_copy(update={"status": OrderStatus.SUBMITTING}))


def test_order_cannot_be_recorded_before_reservation(tmp_path):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    request = OrderRequest(
        client_order_key="key-1",
        proposal_id="proposal-1",
        account_snapshot_id="snapshot-1",
        symbol="QQQ",
        side=OrderSide.BUY,
        quantity=1,
        reference_price=Decimal("100"),
    )
    order = OrderRecord(
        client_order_key="key-1",
        proposal_id="proposal-1",
        paper_account_fingerprint="fingerprint",
        status=OrderStatus.SUBMITTING,
        request=request,
    )

    with pytest.raises(RuntimeError, match="reserved"):
        ledger.record_order(order)
