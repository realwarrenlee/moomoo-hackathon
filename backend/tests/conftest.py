from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.broker.account_lock import fingerprint_account_id
from app.models.contracts import (
    AccountSnapshot,
    ControlState,
    ProposalAction,
    Quote,
    TradeProposal,
)
from app.risk.policy import RiskGate

TEST_ACCOUNT_ID = "0000000000000101"
TEST_ACCOUNT_FINGERPRINT = fingerprint_account_id(TEST_ACCOUNT_ID)


@pytest.fixture
def now():
    return datetime(2026, 11, 18, 15, 0, tzinfo=UTC)


@pytest.fixture
def account_id():
    return TEST_ACCOUNT_ID


@pytest.fixture
def account_fingerprint():
    return TEST_ACCOUNT_FINGERPRINT


@pytest.fixture
def account(now):
    return AccountSnapshot(
        snapshot_id="snapshot-1",
        account_fingerprint=TEST_ACCOUNT_FINGERPRINT,
        environment="paper",
        equity=Decimal("100000"),
        day_start_equity=Decimal("100000"),
        peak_equity=Decimal("100000"),
        cash=Decimal("100000"),
        buying_power=Decimal("100000"),
        as_of_utc=now,
        reconciled=True,
    )


@pytest.fixture
def quote(now):
    return Quote(
        symbol="SPY",
        price=Decimal("100"),
        as_of_utc=now,
        regular_session_open=True,
    )


@pytest.fixture
def proposal(now):
    return TradeProposal(
        proposal_id="proposal-1",
        run_id="run-1",
        strategy_version="spy-directional",
        decision_time_utc=now,
        data_as_of_utc=now,
        symbol="SPY",
        action=ProposalAction.BUY,
        requested_quantity=2,
        thesis="Predefined conditions passed",
        invalidation="Regime filter fails",
        evidence_ids=("evidence-1",),
    )


@pytest.fixture
def control():
    return ControlState(order_writes_enabled=True, first_order_approved=True)


@pytest.fixture
def risk_gate():
    return RiskGate(expected_account_fingerprint=TEST_ACCOUNT_FINGERPRINT)
