from app.broker.mock import MockPaperBroker
from app.ledger.store import SQLiteLedger
from app.models.contracts import OrderStatus, PolicyDecision
from app.service import TradingService, build_client_order_key


def approve_first(ledger, proposal, now):
    ledger.approve_first_order(
        build_client_order_key(proposal.strategy_version, proposal.proposal_id),
        proposal.proposal_id,
        now,
        "test-owner",
    )


def make_service(account, risk_gate, ledger, proposal, now, **broker_options):
    approve_first(ledger, proposal, now)
    broker = MockPaperBroker(account, **broker_options)
    service = TradingService(
        broker=broker,
        risk_gate=risk_gate,
        ledger=ledger,
        order_writes_enabled=True,
    )
    return broker, service


def test_order_writes_are_disabled_by_default(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker = MockPaperBroker(account)
    service = TradingService(broker=broker, risk_gate=risk_gate, ledger=ledger)

    result = service.execute(proposal, quote, now)

    assert result.decision.decision is PolicyDecision.REJECT
    assert "R010" in {reason.rule_id for reason in result.decision.reasons}
    assert broker.submission_calls == 0


def test_approved_order_is_filled_reconciled_and_logged(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(account, risk_gate, ledger, proposal, now)

    result = service.execute(proposal, quote, now)

    assert result.decision.decision is PolicyDecision.APPROVE
    assert result.order.status is OrderStatus.FILLED
    assert broker.get_account_snapshot().positions[0].quantity == 2
    event_types = {event["event_type"] for event in ledger.list_events()}
    assert {"POLICY_APPROVED", "FILL_CONFIRMED", "RECONCILIATION_OK"} <= event_types


def test_oversized_order_never_reaches_broker(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(account, risk_gate, ledger, proposal, now)
    proposal = proposal.model_copy(update={"requested_quantity": 1000})

    result = service.execute(proposal, quote, now)

    assert result.decision.decision is PolicyDecision.REJECT
    assert result.order is None
    assert broker.submission_calls == 0


def test_duplicate_run_creates_at_most_one_order(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(account, risk_gate, ledger, proposal, now)

    first = service.execute(proposal, quote, now)
    second = service.execute(proposal, quote, now)

    assert first.order.status is OrderStatus.FILLED
    assert second.decision.decision is PolicyDecision.REJECT
    assert "R011" in {reason.rule_id for reason in second.decision.reasons}
    assert broker.submission_calls == 1
    assert broker.get_account_snapshot().positions[0].quantity == 2


def test_unknown_submission_is_not_blindly_retried(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(account, risk_gate, ledger, proposal, now)
    broker.fail_next_submission = True

    first = service.execute(proposal, quote, now)
    second = service.execute(proposal, quote, now)

    assert first.order.status is OrderStatus.UNKNOWN
    assert second.order.status is OrderStatus.UNKNOWN
    assert broker.submission_calls == 1


def test_unknown_submission_blocks_different_new_orders(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(account, risk_gate, ledger, proposal, now)
    broker.fail_next_submission = True

    first = service.execute(proposal, quote, now)
    second_proposal = proposal.model_copy(
        update={"proposal_id": "proposal-2", "run_id": "run-2"}
    )
    second = service.execute(second_proposal, quote, now)

    assert first.order.status is OrderStatus.UNKNOWN
    assert second.decision.decision is PolicyDecision.REJECT
    assert "R009" in {reason.rule_id for reason in second.decision.reasons}
    assert second.order is None
    assert broker.submission_calls == 1


def test_idempotency_survives_ledger_restart(
    tmp_path, account, risk_gate, proposal, quote, now
):
    path = tmp_path / "audit.db"
    ledger = SQLiteLedger(path)
    broker, service = make_service(account, risk_gate, ledger, proposal, now)
    first = service.execute(proposal, quote, now)
    restarted_service = TradingService(
        broker=broker,
        risk_gate=risk_gate,
        ledger=SQLiteLedger(path),
        order_writes_enabled=True,
    )

    second = restarted_service.execute(proposal, quote, now)

    assert first.order.status is OrderStatus.FILLED
    assert second.decision.decision is PolicyDecision.REJECT
    assert "R011" in {reason.rule_id for reason in second.decision.reasons}
    assert broker.submission_calls == 1


def test_kill_switch_persists_across_ledger_restart(
    tmp_path, account, risk_gate, proposal, quote, now
):
    path = tmp_path / "audit.db"
    ledger = SQLiteLedger(path)
    ledger.set_kill_switch(True)
    restarted_ledger = SQLiteLedger(path)
    broker, service = make_service(account, risk_gate, restarted_ledger, proposal, now)

    result = service.execute(proposal, quote, now)

    assert restarted_ledger.kill_switch_engaged() is True
    assert result.decision.decision is PolicyDecision.REJECT
    assert "R010" in {reason.rule_id for reason in result.decision.reasons}
    assert broker.submission_calls == 0


def test_partial_fill_preserves_pending_remainder(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(account, risk_gate, ledger, proposal, now, fill_quantity=1)

    result = service.execute(proposal, quote, now)

    account_after = broker.get_account_snapshot()
    assert result.order.status is OrderStatus.PARTIALLY_FILLED
    assert account_after.positions[0].quantity == 1
    assert account_after.open_orders[0].remaining_quantity == 1


def test_acknowledgement_is_not_reported_as_a_fill(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(account, risk_gate, ledger, proposal, now, auto_fill=False)

    result = service.execute(proposal, quote, now)

    assert result.order.status is OrderStatus.ACKNOWLEDGED
    assert result.order.fills == ()
    assert broker.get_account_snapshot().positions == ()
    assert "FILL_CONFIRMED" not in {event["event_type"] for event in ledger.list_events()}


def test_first_order_requires_explicit_owner_approval(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker = MockPaperBroker(account)
    service = TradingService(
        broker=broker,
        risk_gate=risk_gate,
        ledger=ledger,
        order_writes_enabled=True,
    )

    blocked = service.execute(proposal, quote, now)

    assert blocked.decision.decision is PolicyDecision.REJECT
    assert "R014" in {reason.rule_id for reason in blocked.decision.reasons}
    assert broker.submission_calls == 0

    approve_first(ledger, proposal, now)
    approved = service.execute(proposal, quote, now)

    assert approved.decision.decision is PolicyDecision.APPROVE
    assert approved.order.status is OrderStatus.FILLED
    assert broker.submission_calls == 1


def test_approval_for_another_proposal_does_not_unlock(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    ledger.approve_first_order("mootrade-" + "0" * 64, "other-proposal", now, "test-owner")
    broker = MockPaperBroker(account)
    service = TradingService(
        broker=broker,
        risk_gate=risk_gate,
        ledger=ledger,
        order_writes_enabled=True,
    )

    result = service.execute(proposal, quote, now)

    assert result.decision.decision is PolicyDecision.REJECT
    assert "R014" in {reason.rule_id for reason in result.decision.reasons}
    assert broker.submission_calls == 0


def test_missing_quote_never_reaches_broker(
    tmp_path, account, risk_gate, proposal, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(account, risk_gate, ledger, proposal, now)

    result = service.execute(proposal, None, now)

    assert result.decision.decision is PolicyDecision.REJECT
    assert "R007" in {reason.rule_id for reason in result.decision.reasons}
    assert broker.submission_calls == 0


def test_account_read_failure_fails_closed(
    tmp_path, account, risk_gate, proposal, quote, now
):
    class FailingReadBroker(MockPaperBroker):
        def get_account_snapshot(self):
            raise RuntimeError("simulated read failure")

    ledger = SQLiteLedger(tmp_path / "audit.db")
    approve_first(ledger, proposal, now)
    broker = FailingReadBroker(account)
    service = TradingService(
        broker=broker,
        risk_gate=risk_gate,
        ledger=ledger,
        order_writes_enabled=True,
    )

    result = service.execute(proposal, quote, now)

    assert result.decision.decision is PolicyDecision.REJECT
    assert "R009" in {reason.rule_id for reason in result.decision.reasons}
    assert broker.submission_calls == 0
    assert "EXECUTION_BLOCKED" in {event["event_type"] for event in ledger.list_events()}


def test_account_change_between_gate_and_write_fails_closed(
    tmp_path, account, risk_gate, proposal, quote, now
):
    class ChangingSnapshotBroker(MockPaperBroker):
        reads = 0

        def get_account_snapshot(self):
            self.reads += 1
            snapshot = super().get_account_snapshot()
            if self.reads == 2:
                return snapshot.model_copy(update={"snapshot_id": "changed-snapshot"})
            return snapshot

    ledger = SQLiteLedger(tmp_path / "audit.db")
    approve_first(ledger, proposal, now)
    broker = ChangingSnapshotBroker(account)
    service = TradingService(
        broker=broker,
        risk_gate=risk_gate,
        ledger=ledger,
        order_writes_enabled=True,
    )

    result = service.execute(proposal, quote, now)

    assert result.decision.decision is PolicyDecision.REJECT
    assert "R009" in {reason.rule_id for reason in result.decision.reasons}
    assert broker.submission_calls == 0


def test_accepted_but_timed_out_order_stays_unknown_until_reconciled(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(
        account, risk_gate, ledger, proposal, now, accept_then_timeout=True
    )

    first = service.execute(proposal, quote, now)
    other = proposal.model_copy(
        update={"proposal_id": "proposal-2", "run_id": "run-2"}
    )
    blocked = service.execute(other, quote, now)

    assert first.order.status is OrderStatus.UNKNOWN
    assert ledger.has_unknown_submissions() is True
    assert blocked.decision.decision is PolicyDecision.REJECT
    assert "R009" in {reason.rule_id for reason in blocked.decision.reasons}
    assert broker.submission_calls == 1

    reconciled = service.reconcile(first.order.client_order_key, now)

    assert reconciled.status is OrderStatus.FILLED
    assert ledger.has_unknown_submissions() is False
    assert broker.submission_calls == 1

    retried = service.execute(other, quote, now)

    assert retried.decision.decision is PolicyDecision.APPROVE
    assert retried.order.status is OrderStatus.FILLED
    assert broker.submission_calls == 2


def test_unexpected_broker_response_is_unknown_and_not_retried(
    tmp_path, account, risk_gate, proposal, quote, now
):
    class UnexpectedResponseBroker(MockPaperBroker):
        def submit_order(self, request, now):
            self.submission_calls += 1
            return {"order_id": "broker-1"}

    ledger = SQLiteLedger(tmp_path / "audit.db")
    approve_first(ledger, proposal, now)
    broker = UnexpectedResponseBroker(account)
    service = TradingService(
        broker=broker,
        risk_gate=risk_gate,
        ledger=ledger,
        order_writes_enabled=True,
    )

    first = service.execute(proposal, quote, now)
    second = service.execute(proposal, quote, now)

    assert first.order.status is OrderStatus.UNKNOWN
    assert ledger.has_unknown_submissions() is True
    assert second.decision.decision is PolicyDecision.REJECT
    assert broker.submission_calls == 1
    assert "ORDER_RESPONSE_INVALID" in {
        event["event_type"] for event in ledger.list_events()
    }


def test_submitted_order_reconciles_with_broker(
    tmp_path, account, risk_gate, proposal, quote, now
):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker, service = make_service(account, risk_gate, ledger, proposal, now)
    result = service.execute(proposal, quote, now)

    reconciled = service.reconcile(result.order.client_order_key, now)

    assert reconciled.status is OrderStatus.FILLED
    assert "RECONCILIATION_OK" in {event["event_type"] for event in ledger.list_events()}
