from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.contracts import AccountSnapshot, ControlState, PolicyDecision, Quote, RiskDecision, TradeProposal
from app.research.data import UNIVERSE, MarketHistory, NewsArchive, session_close_utc
from app.research.strategy import ResearchSnapshot, build_proposal, screen
from app.risk.policy import RiskGate

VERIFIED_EQUITY = Decimal("100000")
STRATEGIES = ("momentum-v1", "news-catalyst-v1")


@dataclass(frozen=True)
class DryRunDecision:
    scenario: str
    snapshot: ResearchSnapshot
    proposal: TradeProposal | None
    quote: Quote | None
    account: AccountSnapshot
    control: ControlState
    risk_decision: RiskDecision | None

    @property
    def approved(self) -> bool:
        return self.risk_decision is not None and self.risk_decision.decision is PolicyDecision.APPROVE


def build_account(
    decision_time_utc: datetime,
    fingerprint: str,
    snapshot_id: str,
    equity: Decimal = VERIFIED_EQUITY,
) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id=snapshot_id,
        account_fingerprint=fingerprint,
        environment="paper",
        equity=equity,
        day_start_equity=equity,
        peak_equity=equity,
        cash=equity,
        buying_power=equity,
        positions=(),
        open_orders=(),
        as_of_utc=decision_time_utc,
        reconciled=True,
        unknown_orders=0,
    )


def dry_run_control(order_writes_enabled: bool = True, first_order_approved: bool = True) -> ControlState:
    return ControlState(
        order_writes_enabled=order_writes_enabled,
        kill_switch_engaged=False,
        circuit_breaker_open=False,
        first_order_approved=first_order_approved,
    )


def judge(
    gate: RiskGate,
    proposal: TradeProposal,
    quote: Quote | None,
    account: AccountSnapshot,
    control: ControlState,
    now: datetime,
) -> RiskDecision:
    return gate.evaluate(
        proposal=proposal,
        account=account,
        quote=quote,
        control=control,
        now=now,
        duplicate=False,
        unknown_submission=False,
    )


def latest_decision(
    history: MarketHistory,
    news: NewsArchive,
    strategy_version: str,
    fingerprint: str,
    now: datetime | None = None,
) -> DryRunDecision:
    session = history.last_completed_session()
    decision_time = session_close_utc(session)
    return decide_at(
        history,
        news,
        strategy_version,
        fingerprint,
        decision_time,
        scenario="latest completed session",
        now=now or decision_time,
    )


def decide_at(
    history: MarketHistory,
    news: NewsArchive,
    strategy_version: str,
    fingerprint: str,
    decision_time: datetime,
    scenario: str,
    now: datetime | None = None,
    control: ControlState | None = None,
) -> DryRunDecision:
    gate = RiskGate(
        expected_account_fingerprint=fingerprint,
        allowed_symbols=frozenset(UNIVERSE),
    )
    snapshot = screen(history, news, decision_time, strategy_version)
    proposal = build_proposal(snapshot, history, VERIFIED_EQUITY)
    quote = history.quote(snapshot.selected_symbol or "SPY", decision_time) if proposal is not None else None
    effective_now = now or decision_time
    account = build_account(decision_time, fingerprint, f"dryrun-{decision_time:%Y%m%dT%H%M%SZ}")
    effective_control = control or dry_run_control()
    decision = (
        judge(gate, proposal, quote, account, effective_control, effective_now)
        if proposal is not None
        else None
    )
    return DryRunDecision(
        scenario=scenario,
        snapshot=snapshot,
        proposal=proposal,
        quote=quote,
        account=account,
        control=effective_control,
        risk_decision=decision,
    )


def find_accepted_example(
    history: MarketHistory,
    news: NewsArchive,
    strategy_version: str,
    fingerprint: str,
) -> DryRunDecision | None:
    dates = history.session_dates()
    for session in reversed(dates[21:-1]):
        decision = decide_at(
            history,
            news,
            strategy_version,
            fingerprint,
            session_close_utc(session),
            scenario="historical accepted example",
        )
        if decision.approved:
            return decision
    return None


def stale_quote_example(
    accepted: DryRunDecision,
    fingerprint: str,
) -> DryRunDecision | None:
    if accepted.proposal is None or accepted.quote is None:
        return None
    now = accepted.snapshot.decision_time_utc + timedelta(minutes=10)
    quote = accepted.quote
    account = build_account(now, fingerprint, f"dryrun-stale-{now:%Y%m%dT%H%M%SZ}")
    gate = RiskGate(expected_account_fingerprint=fingerprint, allowed_symbols=frozenset(UNIVERSE))
    decision = judge(
        gate,
        accepted.proposal,
        quote,
        account,
        dry_run_control(),
        now,
    )
    return DryRunDecision(
        scenario="stale quote (10-minute-old decision input)",
        snapshot=accepted.snapshot,
        proposal=accepted.proposal,
        quote=quote,
        account=account,
        control=dry_run_control(),
        risk_decision=decision,
    )


def oversized_example(
    accepted: DryRunDecision,
    fingerprint: str,
) -> DryRunDecision | None:
    if accepted.quote is None or accepted.proposal is None:
        return None
    quantity = int(VERIFIED_EQUITY * Decimal("0.20") / accepted.quote.price)
    proposal = accepted.proposal.model_copy(update={"requested_quantity": quantity})
    gate = RiskGate(expected_account_fingerprint=fingerprint, allowed_symbols=frozenset(UNIVERSE))
    decision = judge(
        gate,
        proposal,
        accepted.quote,
        accepted.account,
        dry_run_control(),
        accepted.account.as_of_utc,
    )
    return DryRunDecision(
        scenario="oversized quantity (20% of equity versus 10% limit)",
        snapshot=accepted.snapshot,
        proposal=proposal,
        quote=accepted.quote,
        account=accepted.account,
        control=dry_run_control(),
        risk_decision=decision,
    )


def control_rejection_example(
    accepted: DryRunDecision,
    fingerprint: str,
    scenario: str,
    order_writes_enabled: bool,
    first_order_approved: bool,
) -> DryRunDecision | None:
    if accepted.proposal is None or accepted.quote is None:
        return None
    control = dry_run_control(
        order_writes_enabled=order_writes_enabled,
        first_order_approved=first_order_approved,
    )
    gate = RiskGate(expected_account_fingerprint=fingerprint, allowed_symbols=frozenset(UNIVERSE))
    decision = judge(
        gate,
        accepted.proposal,
        accepted.quote,
        accepted.account,
        control,
        accepted.account.as_of_utc,
    )
    return DryRunDecision(
        scenario=scenario,
        snapshot=accepted.snapshot,
        proposal=accepted.proposal,
        quote=accepted.quote,
        account=accepted.account,
        control=control,
        risk_decision=decision,
    )
