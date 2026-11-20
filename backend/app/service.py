import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.ledger.store import SQLiteLedger
from app.models.contracts import (
    AccountSnapshot,
    ControlState,
    OrderRecord,
    OrderRequest,
    OrderSide,
    OrderStatus,
    PolicyDecision,
    Quote,
    RiskDecision,
    TradeProposal,
    TradingActivation,
    can_transition,
)
from app.risk.policy import RiskGate


@dataclass(frozen=True)
class ExecutionResult:
    decision: RiskDecision
    order: OrderRecord | None


class ExecutionBroker(Protocol):
    def get_account_snapshot(self) -> AccountSnapshot: ...

    def get_order(self, client_order_key: str) -> OrderRecord | None: ...

    def submit_order(self, request: OrderRequest, now: datetime) -> OrderRecord: ...


def build_client_order_key(strategy_version: str, proposal_id: str) -> str:
    key_material = f"{strategy_version}:{proposal_id}".encode()
    return f"mootrade-{hashlib.sha256(key_material).hexdigest()}"


class TradingService:
    def __init__(
        self,
        broker: ExecutionBroker,
        risk_gate: RiskGate,
        ledger: SQLiteLedger,
        order_writes_enabled: bool = False,
    ) -> None:
        self.broker = broker
        self.risk_gate = risk_gate
        self.ledger = ledger
        self.order_writes_enabled = order_writes_enabled
        self._source = getattr(broker, "source_name", "mock_broker")

    def execute(
        self,
        proposal: TradeProposal,
        quote: Quote | None,
        now: datetime,
        *,
        autonomous_activation: TradingActivation | None = None,
    ) -> ExecutionResult:
        try:
            account = self.broker.get_account_snapshot()
        except Exception as exc:
            return self._fail_closed(proposal, now, f"Account read failed ({type(exc).__name__})")

        existing = self.ledger.submission_for_proposal(proposal.proposal_id)
        client_order_key = build_client_order_key(proposal.strategy_version, proposal.proposal_id)
        approval_ok = self.ledger.is_first_order_approved(
            client_order_key, proposal.proposal_id
        )
        control = ControlState(
            order_writes_enabled=self.order_writes_enabled,
            kill_switch_engaged=self.ledger.kill_switch_engaged(),
            first_order_approved=approval_ok,
            autonomous_activation=autonomous_activation,
        )
        decision = self.risk_gate.evaluate(
            proposal=proposal,
            account=account,
            quote=quote,
            control=control,
            now=now,
            duplicate=existing is not None,
            unknown_submission=self.ledger.has_unknown_submissions(),
        )
        self.ledger.append_event(
            "PROPOSAL_CREATED",
            now,
            proposal.run_id,
            "trading_service",
            proposal.model_dump(mode="json"),
            proposal.proposal_id,
        )
        self.ledger.append_event(
            "POLICY_APPROVED" if decision.decision is PolicyDecision.APPROVE else "POLICY_REJECTED",
            now,
            proposal.run_id,
            "risk_gate",
            decision.model_dump(mode="json"),
            proposal.proposal_id,
        )
        if decision.decision is PolicyDecision.REJECT:
            return ExecutionResult(decision, self.ledger.order_for_proposal(proposal.proposal_id))

        try:
            latest = self.broker.get_account_snapshot()
        except Exception as exc:
            return self._fail_closed(
                proposal, now, f"Account re-read failed ({type(exc).__name__})", account.snapshot_id
            )
        if latest.snapshot_id != account.snapshot_id:
            return self._fail_closed(
                proposal, now, "Account snapshot changed after policy approval", account.snapshot_id
            )
        if quote is None:
            return self._fail_closed(proposal, now, "Approved proposal is missing a quote", account.snapshot_id)

        request = OrderRequest(
            client_order_key=client_order_key,
            proposal_id=proposal.proposal_id,
            account_snapshot_id=account.snapshot_id,
            symbol=proposal.symbol,
            side=OrderSide(proposal.action.value),
            quantity=decision.approved_quantity,
            reference_price=quote.price,
        )
        if not self.ledger.reserve_submission(request):
            return ExecutionResult(decision, self.ledger.order_for_proposal(proposal.proposal_id))

        pending = OrderRecord(
            client_order_key=client_order_key,
            proposal_id=proposal.proposal_id,
            paper_account_fingerprint=account.account_fingerprint,
            status=OrderStatus.SUBMITTING,
            request=request,
            submitted_at_utc=now,
        )
        self.ledger.record_order(pending)
        self.ledger.append_event(
            "ORDER_SUBMISSION_STARTED",
            now,
            proposal.run_id,
            "execution_service",
            {"client_order_key": client_order_key},
            proposal.proposal_id,
        )
        try:
            order = self.broker.submit_order(request, now)
        except Exception as exc:
            return self._mark_unknown(
                pending,
                decision,
                proposal,
                now,
                "ORDER_UNKNOWN",
                f"{type(exc).__name__}: {exc}",
            )
        try:
            order = self._validate_broker_order(pending, order)
        except Exception as exc:
            return self._mark_unknown(
                pending, decision, proposal, now, "ORDER_RESPONSE_INVALID", str(exc)
            )

        self.ledger.record_order(order)
        self.ledger.append_event(
            "ORDER_ACKNOWLEDGED",
            now,
            proposal.run_id,
            self._source,
            {
                "client_order_key": client_order_key,
                "broker_order_id": order.broker_order_id,
                "status": order.status.value,
            },
            proposal.proposal_id,
        )
        for fill in order.fills:
            self.ledger.append_event(
                "FILL_CONFIRMED",
                fill.filled_at_utc,
                proposal.run_id,
                self._source,
                fill.model_dump(mode="json"),
                proposal.proposal_id,
            )
        try:
            reconciled = self.broker.get_account_snapshot()
        except Exception as exc:
            self.ledger.append_event(
                "RECONCILIATION_MISMATCH",
                now,
                proposal.run_id,
                "reconciler",
                {"client_order_key": client_order_key, "error_type": type(exc).__name__},
                proposal.proposal_id,
            )
            return ExecutionResult(decision, order)
        self.ledger.append_event(
            "RECONCILIATION_OK",
            reconciled.as_of_utc,
            proposal.run_id,
            "reconciler",
            {"snapshot_id": reconciled.snapshot_id, "order_status": order.status.value},
            proposal.proposal_id,
        )
        return ExecutionResult(decision, order)

    def reconcile(self, client_order_key: str, now: datetime) -> OrderRecord | None:
        local = self.ledger.order_for_key(client_order_key)
        if local is None:
            return None
        try:
            broker_order = self.broker.get_order(client_order_key)
        except Exception as exc:
            self.ledger.append_event(
                "RECONCILIATION_MISMATCH",
                now,
                None,
                "reconciler",
                {"client_order_key": client_order_key, "error_type": type(exc).__name__},
                local.proposal_id,
            )
            return local
        if broker_order is None:
            self.ledger.append_event(
                "RECONCILIATION_MISMATCH",
                now,
                None,
                "reconciler",
                {"client_order_key": client_order_key, "reason": "order_not_found"},
                local.proposal_id,
            )
            return local
        try:
            broker_order = self._validate_broker_order(local, broker_order)
        except Exception as exc:
            self.ledger.append_event(
                "RECONCILIATION_MISMATCH",
                now,
                None,
                "reconciler",
                {"client_order_key": client_order_key, "reason": str(exc)},
                local.proposal_id,
            )
            return local
        if broker_order.status is not local.status or broker_order.fills != local.fills:
            try:
                self.ledger.record_order(broker_order)
            except ValueError as exc:
                self.ledger.append_event(
                    "RECONCILIATION_MISMATCH",
                    now,
                    None,
                    "reconciler",
                    {"client_order_key": client_order_key, "reason": str(exc)},
                    local.proposal_id,
                )
                return local
            self.ledger.append_event(
                "RECONCILIATION_OK",
                now,
                None,
                "reconciler",
                {
                    "client_order_key": client_order_key,
                    "previous_status": local.status.value,
                    "order_status": broker_order.status.value,
                },
                local.proposal_id,
            )
            return broker_order
        self.ledger.append_event(
            "RECONCILIATION_OK",
            now,
            None,
            "reconciler",
            {"client_order_key": client_order_key, "order_status": local.status.value},
            local.proposal_id,
        )
        return local

    def _mark_unknown(
        self,
        pending: OrderRecord,
        decision: RiskDecision,
        proposal: TradeProposal,
        now: datetime,
        event_type: str,
        reason: str,
    ) -> ExecutionResult:
        order = pending.model_copy(update={"status": OrderStatus.UNKNOWN})
        self.ledger.record_order(order)
        self.ledger.append_event(
            event_type,
            now,
            proposal.run_id,
            "execution_service",
            {"client_order_key": pending.client_order_key, "reason": reason},
            proposal.proposal_id,
        )
        return ExecutionResult(decision, order)

    def _validate_broker_order(
        self, expected: OrderRecord, order: object
    ) -> OrderRecord:
        if not isinstance(order, OrderRecord):
            raise ValueError("broker returned an unexpected order object")
        if order.client_order_key != expected.client_order_key:
            raise ValueError("broker order key does not match the submission")
        if order.proposal_id != expected.proposal_id:
            raise ValueError("broker order proposal does not match the submission")
        if order.paper_account_fingerprint != expected.paper_account_fingerprint:
            raise ValueError("broker order account does not match the submission")
        if order.request != expected.request:
            raise ValueError("broker order request does not match the submission")
        if order.status not in {
            OrderStatus.ACKNOWLEDGED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.UNKNOWN,
        }:
            raise ValueError("broker returned a non-terminal acknowledgement status")
        if not can_transition(expected.status, order.status):
            raise ValueError("broker order status transition is illegal")
        if order.status is not OrderStatus.REJECTED and not order.broker_order_id:
            raise ValueError("broker order is missing its order id")
        filled = sum(item.quantity for item in order.fills)
        if filled > order.request.quantity:
            raise ValueError("broker fills exceed the requested quantity")
        if order.status is OrderStatus.FILLED and filled != order.request.quantity:
            raise ValueError("broker filled status does not match its fills")
        if order.status is OrderStatus.PARTIALLY_FILLED and not 0 < filled < order.request.quantity:
            raise ValueError("broker partial status does not match its fills")
        if order.status in {OrderStatus.ACKNOWLEDGED, OrderStatus.REJECTED} and filled:
            raise ValueError("broker unfilled status carries fills")
        return order

    def _fail_closed(
        self,
        proposal: TradeProposal,
        now: datetime,
        reason: str,
        snapshot_id: str = "unavailable",
    ) -> ExecutionResult:
        decision = self.risk_gate.fail_closed(proposal, now, reason, snapshot_id)
        self.ledger.append_event(
            "EXECUTION_BLOCKED",
            now,
            proposal.run_id,
            "trading_service",
            {"reason": reason},
            proposal.proposal_id,
        )
        self.ledger.append_event(
            "POLICY_REJECTED",
            now,
            proposal.run_id,
            "risk_gate",
            decision.model_dump(mode="json"),
            proposal.proposal_id,
        )
        return ExecutionResult(decision, self.ledger.order_for_proposal(proposal.proposal_id))
