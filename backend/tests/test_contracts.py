from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.contracts import (
    AccountSnapshot,
    PolicyDecision,
    ProposalAction,
    RiskDecision,
    TradeProposal,
)


NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)


def make_proposal(**overrides):
    values = {
        "proposal_id": "proposal-1",
        "run_id": "run-1",
        "strategy_version": "spy-directional",
        "decision_time_utc": NOW,
        "data_as_of_utc": NOW,
        "symbol": "QQQ",
        "action": ProposalAction.BUY,
        "requested_quantity": 2,
        "thesis": "Predefined conditions passed",
        "invalidation": "Regime filter fails",
        "evidence_ids": ("evidence-1",),
    }
    values.update(overrides)
    return TradeProposal(**values)


def test_valid_trade_proposal():
    proposal = make_proposal()

    assert proposal.symbol == "QQQ"
    assert proposal.requested_quantity == 2


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValidationError):
        make_proposal(decision_time_utc=datetime(2026, 11, 18, 15, 0))


def test_no_trade_cannot_request_quantity():
    with pytest.raises(ValidationError):
        make_proposal(action=ProposalAction.NO_TRADE, requested_quantity=1)


def test_live_account_is_not_a_valid_account_contract():
    values = {
        "snapshot_id": "snapshot-1",
        "account_fingerprint": "competition-paper",
        "environment": "live",
        "equity": Decimal("100000"),
        "day_start_equity": Decimal("100000"),
        "peak_equity": Decimal("100000"),
        "cash": Decimal("100000"),
        "buying_power": Decimal("100000"),
        "as_of_utc": NOW,
        "reconciled": True,
    }

    with pytest.raises(ValidationError):
        AccountSnapshot(**values)


def test_rejection_cannot_approve_quantity():
    with pytest.raises(ValidationError):
        RiskDecision(
            proposal_id="proposal-1",
            policy_version="risk-v1",
            decision=PolicyDecision.REJECT,
            approved_quantity=1,
            account_snapshot_id="snapshot-1",
            expires_at_utc=NOW,
        )


def test_account_snapshot_requires_day_start_equity():
    with pytest.raises(ValidationError):
        AccountSnapshot(
            snapshot_id="snapshot-1",
            account_fingerprint="competition-paper",
            environment="paper",
            equity=Decimal("100000"),
            peak_equity=Decimal("100000"),
            cash=Decimal("100000"),
            buying_power=Decimal("100000"),
            as_of_utc=NOW,
            reconciled=True,
        )
