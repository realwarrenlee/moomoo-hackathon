from datetime import timedelta
from decimal import Decimal

import pytest

from app.models.contracts import (
    ControlState,
    OpenOrder,
    OrderSide,
    PolicyDecision,
    Position,
    ProposalAction,
)
from app.risk.policy import RiskGate
from app.trading_mode import build_auto_paper_activation


def rule_ids(decision):
    return {reason.rule_id for reason in decision.reasons}


@pytest.mark.parametrize("version", ["risk-v1", "risk-v2", ""])
def test_unsupported_policy_cannot_be_selected(version, account):
    with pytest.raises(ValueError, match="unsupported risk policy"):
        RiskGate(account.account_fingerprint, policy_version=version)


def test_v3_floor_rejects_small_strategy_order(proposal, account, quote, control, now):
    decision = RiskGate(account.account_fingerprint).evaluate(
        proposal, account, quote, control, now
    )
    assert "R016" in rule_ids(decision)


def test_v3_declared_target_is_recomputed(proposal, account, quote, control, now):
    proposal = proposal.model_copy(update={
        "requested_quantity": 200,
        "target_exposure_fraction": Decimal("0.60"),
    })
    decision = RiskGate(account.account_fingerprint).evaluate(
        proposal, account, quote, control, now
    )
    assert "R018" in rule_ids(decision)


def test_v3_never_allows_leverage_above_one(proposal, account, quote, control, now):
    gate = RiskGate(account.account_fingerprint, leverage_by_symbol={"SPY": Decimal("4")})
    decision = gate.evaluate(proposal, account, quote, control, now)
    assert "R015" in rule_ids(decision)


def test_invalid_daily_baseline_fails_closed(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(update={"day_start_equity": Decimal("0")})
    decision = risk_gate.evaluate(proposal, account, quote, control, now)
    assert "R007" in rule_ids(decision)


def test_valid_buy_is_approved(risk_gate, proposal, account, quote, control, now):
    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert decision.decision is PolicyDecision.APPROVE
    assert decision.approved_quantity == 2


def test_oversized_order_is_rejected(risk_gate, proposal, account, quote, control, now):
    proposal = proposal.model_copy(update={"requested_quantity": 2000})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert decision.decision is PolicyDecision.REJECT
    assert "R017" in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_stale_quote_is_rejected(risk_gate, proposal, account, quote, control, now):
    quote = quote.model_copy(update={"as_of_utc": now - timedelta(minutes=10)})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R007" in rule_ids(decision)
    messages = [reason.message for reason in decision.reasons if reason.rule_id == "R007"]
    assert messages == ["Quote is stale (older than 300s)"]
    assert "future" not in messages[0].lower()


def test_small_clock_skew_is_not_rejected_as_future(risk_gate, proposal, account, quote, control, now):
    quote = quote.model_copy(update={"as_of_utc": now + timedelta(seconds=2)})
    account = account.model_copy(update={"as_of_utc": now + timedelta(seconds=2)})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert decision.decision is PolicyDecision.APPROVE
    assert not any("future" in reason.message.lower() for reason in decision.reasons)


def test_future_quote_is_rejected_without_stale_wording(risk_gate, proposal, account, quote, control, now):
    quote = quote.model_copy(update={"as_of_utc": now + timedelta(seconds=30)})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    messages = [reason.message for reason in decision.reasons if reason.rule_id == "R007"]
    assert messages == ["Quote is timestamped in the future"]


def test_stale_account_snapshot_is_rejected(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(update={"as_of_utc": now - timedelta(minutes=5)})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    messages = [reason.message for reason in decision.reasons if reason.rule_id == "R007"]
    assert messages == ["Account snapshot is stale (older than 60s)"]


def test_insufficient_unlevered_funds_are_rejected(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(
        update={"cash": Decimal("50"), "buying_power": Decimal("200000")}
    )

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R008" in rule_ids(decision)


def test_drawdown_blocks_new_buying(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(
        update={
            "equity": Decimal("98000"),
            "cash": Decimal("98000"),
            "buying_power": Decimal("98000"),
        }
    )

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R006" in rule_ids(decision)


def test_peak_drawdown_does_not_replace_daily_rule(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(
        update={
            "equity": Decimal("99000"),
            "day_start_equity": Decimal("100000"),
            "peak_equity": Decimal("120000"),
            "cash": Decimal("99000"),
            "buying_power": Decimal("99000"),
        }
    )

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert decision.decision is PolicyDecision.APPROVE


def test_duplicate_proposal_is_rejected(risk_gate, proposal, account, quote, control, now):
    decision = risk_gate.evaluate(proposal, account, quote, control, now, duplicate=True)

    assert "R011" in rule_ids(decision)


def test_reconciliation_mismatch_halts_submission(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(update={"reconciled": False})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R009" in rule_ids(decision)


def test_kill_switch_blocks_submission(risk_gate, proposal, account, quote, control, now):
    control = control.model_copy(update={"kill_switch_engaged": True})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R010" in rule_ids(decision)


def test_closed_regular_session_blocks_submission(risk_gate, proposal, account, quote, control, now):
    quote = quote.model_copy(update={"regular_session_open": False})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R012" in rule_ids(decision)


def test_sell_cannot_create_short_position(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(
        update={
            "cash": Decimal("99800"),
            "buying_power": Decimal("99800"),
            "positions": (Position(symbol="QQQ", quantity=2, market_value=Decimal("200")),),
        }
    )
    proposal = proposal.model_copy(
        update={"action": ProposalAction.SELL, "requested_quantity": 3}
    )

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R003" in rule_ids(decision)


def test_wrong_account_is_rejected(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(update={"account_fingerprint": "another-account"})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R001" in rule_ids(decision)


def test_missing_quote_is_rejected(risk_gate, proposal, account, control, now):
    decision = risk_gate.evaluate(proposal, account, None, control, now)

    assert decision.decision is PolicyDecision.REJECT
    assert "R007" in rule_ids(decision)


def test_symbol_outside_allowlist_is_rejected(risk_gate, proposal, account, quote, control, now):
    proposal = proposal.model_copy(update={"symbol": "DIA"})
    quote = quote.model_copy(update={"symbol": "DIA"})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R002" in rule_ids(decision)


def test_invalid_account_equity_is_rejected(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(update={"equity": Decimal("0")})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R007" in rule_ids(decision)


def test_invalid_quote_price_is_rejected(risk_gate, proposal, account, quote, control, now):
    quote = quote.model_copy(update={"price": Decimal("0")})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R007" in rule_ids(decision)


def test_stale_account_snapshot_is_rejected(risk_gate, proposal, account, quote, control, now):
    account = account.model_copy(update={"as_of_utc": now - timedelta(minutes=5)})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R007" in rule_ids(decision)


def test_fourth_open_position_is_rejected(risk_gate, proposal, account, quote, control, now):
    positions = (
        Position(symbol="SPY", quantity=10, market_value=Decimal("1000")),
        Position(symbol="IWM", quantity=10, market_value=Decimal("1000")),
        Position(symbol="DIA", quantity=10, market_value=Decimal("1000")),
    )
    account = account.model_copy(
        update={
            "equity": Decimal("73000"),
            "day_start_equity": Decimal("73000"),
            "peak_equity": Decimal("73000"),
            "cash": Decimal("70000"),
            "buying_power": Decimal("70000"),
            "positions": positions,
        }
    )
    proposal = proposal.model_copy(update={"symbol": "SH"})
    quote = quote.model_copy(update={"symbol": "SH"})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R013" in rule_ids(decision)


def test_first_paper_order_requires_explicit_approval(risk_gate, proposal, account, quote, control, now):
    control = control.model_copy(update={"first_order_approved": False})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R014" in rule_ids(decision)


def _autonomous_activation(fingerprint, now):
    return build_auto_paper_activation(fingerprint, now - timedelta(days=1))


def _autonomous_proposal(proposal):
    return proposal.model_copy(
        update={"requested_quantity": 100, "target_exposure_fraction": Decimal("0.10")}
    )


def _autonomous_control(activation, *, first_order_approved=False):
    return ControlState(
        order_writes_enabled=True,
        first_order_approved=first_order_approved,
        autonomous_activation=activation,
    )


def test_valid_autonomous_activation_satisfies_r014(account, proposal, quote, now, account_fingerprint):
    activation = _autonomous_activation(account_fingerprint, now)
    decision = RiskGate.from_activation(activation).evaluate(
        _autonomous_proposal(proposal), account, quote, _autonomous_control(activation), now
    )

    assert "R014" not in rule_ids(decision)
    assert decision.decision is PolicyDecision.APPROVE
    assert decision.approved_quantity == 100


def test_autonomous_activation_never_applies_on_the_supervised_gate(account, proposal, quote, now, account_fingerprint):
    activation = _autonomous_activation(account_fingerprint, now)
    decision = RiskGate(
        account.account_fingerprint, enforce_min_exposure=False
    ).evaluate(proposal, account, quote, _autonomous_control(activation), now)

    assert "R014" in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_expired_autonomous_activation_is_rejected(account, proposal, quote, now, account_fingerprint):
    activation = _autonomous_activation(account_fingerprint, now).model_copy(
        update={"expires_at_utc": now - timedelta(seconds=1)}
    )
    decision = RiskGate.from_activation(activation).evaluate(
        _autonomous_proposal(proposal), account, quote, _autonomous_control(activation), now
    )

    assert "R014" in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_future_dated_autonomous_activation_is_rejected(account, proposal, quote, now, account_fingerprint):
    activation = _autonomous_activation(account_fingerprint, now).model_copy(
        update={"activated_at_utc": now + timedelta(days=1)}
    )
    decision = RiskGate.from_activation(activation).evaluate(
        _autonomous_proposal(proposal), account, quote, _autonomous_control(activation), now
    )

    assert "R014" in rule_ids(decision)


def test_autonomous_activation_binds_the_account_fingerprint(account, proposal, quote, now, account_fingerprint):
    activation = _autonomous_activation(account_fingerprint, now)
    gate = RiskGate.from_activation(activation)
    mismatched = activation.model_copy(update={"account_fingerprint": "b" * 64})
    decision = gate.evaluate(
        _autonomous_proposal(proposal), account, quote, _autonomous_control(mismatched), now
    )

    assert "R001" not in rule_ids(decision)
    assert "R014" in rule_ids(decision)


def test_autonomous_activation_binds_the_strategy_version(account, proposal, quote, now, account_fingerprint):
    activation = _autonomous_activation(account_fingerprint, now)
    proposal = _autonomous_proposal(proposal).model_copy(
        update={"strategy_version": "other-strategy"}
    )
    decision = RiskGate.from_activation(activation).evaluate(
        proposal, account, quote, _autonomous_control(activation), now
    )

    assert "R014" in rule_ids(decision)


def test_autonomous_activation_binds_the_pinned_limits(account, proposal, quote, now, account_fingerprint):
    activation = _autonomous_activation(account_fingerprint, now)
    gate = RiskGate.from_activation(activation)
    altered = activation.model_copy(
        update={"max_effective_exposure_fraction": Decimal("0.35")}
    )
    decision = gate.evaluate(
        _autonomous_proposal(proposal), account, quote, _autonomous_control(altered), now
    )

    assert "R014" in rule_ids(decision)


def test_autonomous_activation_binds_the_symbol_allowlist(account, proposal, quote, now, account_fingerprint):
    activation = _autonomous_activation(account_fingerprint, now)
    gate = RiskGate.from_activation(activation)
    altered = activation.model_copy(update={"allowed_symbols": ("SPY",)})
    decision = gate.evaluate(
        _autonomous_proposal(proposal), account, quote, _autonomous_control(altered), now
    )

    assert "R014" in rule_ids(decision)


def _leveraged_gate(fingerprint: str):
    return RiskGate(
        expected_account_fingerprint=fingerprint,
        allowed_symbols=frozenset({"SPY", "UPRO"}),
        leverage_by_symbol={"UPRO": Decimal("3")},
    )


def test_leveraged_instrument_is_rejected_by_default(proposal, account, quote, control, now):
    proposal = proposal.model_copy(update={"symbol": "UPRO", "requested_quantity": 2})
    quote = quote.model_copy(update={"symbol": "UPRO"})

    decision = _leveraged_gate(account.account_fingerprint).evaluate(
        proposal, account, quote, control, now
    )

    assert "R015" in rule_ids(decision)
    assert "R017" not in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_leveraged_instrument_is_rejected_regardless_of_size(
    proposal, account, quote, control, now
):
    """risk-v3 caps daily leverage at 1x: a 3x instrument is rejected with
    R015 whether the order is small or exposes the full account."""
    for quantity in (100, 600):
        proposal = proposal.model_copy(
            update={"symbol": "UPRO", "requested_quantity": quantity}
        )
        quote = quote.model_copy(update={"symbol": "UPRO"})

        decision = _leveraged_gate(account.account_fingerprint).evaluate(
            proposal, account, quote, control, now
        )

        assert "R015" in rule_ids(decision)
        assert decision.approved_quantity == 0


def test_invalid_leverage_metadata_is_rejected(proposal, account, quote, control, now):
    gate = RiskGate(
        expected_account_fingerprint=account.account_fingerprint,
        allowed_symbols=frozenset({"SPY"}),
        leverage_by_symbol={"SPY": Decimal("0")},
    )

    decision = gate.evaluate(proposal, account, quote, control, now)

    assert "R007" in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_entry_above_the_competition_concentration_cap_is_rejected(
    risk_gate, proposal, account, quote, control, now
):
    proposal = proposal.model_copy(update={"requested_quantity": 600})  # $60k > $40k

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R019" in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_entry_at_the_competition_concentration_cap_is_approved(
    risk_gate, proposal, account, quote, control, now
):
    proposal = proposal.model_copy(update={"requested_quantity": 400})  # $40k == 40%

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert decision.decision is PolicyDecision.APPROVE
    assert "R019" not in rule_ids(decision)
    assert decision.approved_quantity == 400


def test_buy_above_the_cap_with_an_existing_holding_is_rejected(
    risk_gate, proposal, account, quote, control, now
):
    account = account.model_copy(
        update={
            "cash": Decimal("80000"),
            "buying_power": Decimal("80000"),
            "positions": (Position(symbol="SPY", quantity=200, market_value=Decimal("20000")),),
        }
    )
    proposal = proposal.model_copy(update={"requested_quantity": 250})  # $20k + $25k > $40k

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R019" in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_pending_buy_for_the_same_symbol_counts_toward_the_cap(
    risk_gate, proposal, account, quote, control, now
):
    account = account.model_copy(
        update={
            "cash": Decimal("80000"),
            "buying_power": Decimal("80000"),
            "open_orders": (
                OpenOrder(symbol="SPY", side=OrderSide.BUY, remaining_quantity=100, reference_price=Decimal("100")),
            ),
        }
    )
    proposal = proposal.model_copy(update={"requested_quantity": 320})  # $10k + $32k > $40k

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R019" in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_pending_buy_for_another_symbol_blocks_a_second_position(
    risk_gate, proposal, account, quote, control, now
):
    """risk-v3 allows one directional position: a pending SH buy blocks a
    SPY entry (R013) even when the SPY size alone fits the 40% cap."""
    account = account.model_copy(
        update={
            "cash": Decimal("60000"),
            "buying_power": Decimal("60000"),
            "open_orders": (
                OpenOrder(symbol="SH", side=OrderSide.BUY, remaining_quantity=100, reference_price=Decimal("100")),
            ),
        }
    )
    proposal = proposal.model_copy(update={"requested_quantity": 400})  # exactly the cap

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert decision.decision is PolicyDecision.REJECT
    assert "R013" in rule_ids(decision)


def test_sell_is_not_subject_to_the_concentration_cap(
    risk_gate, proposal, account, quote, control, now
):
    account = account.model_copy(
        update={
            "cash": Decimal("0"),
            "buying_power": Decimal("0"),
            "positions": (Position(symbol="SPY", quantity=600, market_value=Decimal("60000")),),
        }
    )
    proposal = proposal.model_copy(
        update={"action": ProposalAction.SELL, "requested_quantity": 600}
    )

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert "R019" not in rule_ids(decision)
