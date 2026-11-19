from datetime import timedelta
from decimal import Decimal

from app.models.contracts import PolicyDecision, Position, ProposalAction
from app.risk.policy import RiskGate


def rule_ids(decision):
    return {reason.rule_id for reason in decision.reasons}


def test_valid_buy_is_approved(risk_gate, proposal, account, quote, control, now):
    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert decision.decision is PolicyDecision.APPROVE
    assert decision.approved_quantity == 2


def test_oversized_order_is_rejected(risk_gate, proposal, account, quote, control, now):
    proposal = proposal.model_copy(update={"requested_quantity": 1000})

    decision = risk_gate.evaluate(proposal, account, quote, control, now)

    assert decision.decision is PolicyDecision.REJECT
    assert "R004" in rule_ids(decision)
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


def _leveraged_gate(fingerprint: str, allow_leveraged: bool):
    return RiskGate(
        expected_account_fingerprint=fingerprint,
        allowed_symbols=frozenset({"SPY", "UPRO"}),
        leverage_by_symbol={"UPRO": Decimal("3")},
        allow_leveraged=allow_leveraged,
    )


def test_leveraged_instrument_is_rejected_by_default(proposal, account, quote, control, now):
    proposal = proposal.model_copy(update={"symbol": "UPRO", "requested_quantity": 2})
    quote = quote.model_copy(update={"symbol": "UPRO"})

    decision = _leveraged_gate(account.account_fingerprint, allow_leveraged=False).evaluate(
        proposal, account, quote, control, now
    )

    assert "R015" in rule_ids(decision)
    assert "R004" not in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_leveraged_instrument_is_exposure_checked_when_opted_in(
    proposal, account, quote, control, now
):
    proposal = proposal.model_copy(update={"symbol": "UPRO", "requested_quantity": 100})
    quote = quote.model_copy(update={"symbol": "UPRO"})

    decision = _leveraged_gate(account.account_fingerprint, allow_leveraged=True).evaluate(
        proposal, account, quote, control, now
    )

    assert "R015" not in rule_ids(decision)
    assert "R004" in rule_ids(decision)
    assert decision.approved_quantity == 0


def test_small_leveraged_order_passes_exposure_limits_when_opted_in(
    proposal, account, quote, control, now
):
    proposal = proposal.model_copy(update={"symbol": "UPRO", "requested_quantity": 20})
    quote = quote.model_copy(update={"symbol": "UPRO"})

    decision = _leveraged_gate(account.account_fingerprint, allow_leveraged=True).evaluate(
        proposal, account, quote, control, now
    )

    assert decision.decision is PolicyDecision.APPROVE
    assert decision.approved_quantity == 20


def test_invalid_leverage_metadata_is_rejected(proposal, account, quote, control, now):
    gate = RiskGate(
        expected_account_fingerprint=account.account_fingerprint,
        allowed_symbols=frozenset({"SPY"}),
        leverage_by_symbol={"SPY": Decimal("0")},
    )

    decision = gate.evaluate(proposal, account, quote, control, now)

    assert "R007" in rule_ids(decision)
    assert decision.approved_quantity == 0
