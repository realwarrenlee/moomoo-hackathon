from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.contracts import AccountSnapshot, ControlState, Quote, TradeProposal
from app.research.data import UNIVERSE, MarketHistory
from app.research.dryrun import (
    DryRunDecision,
    build_account,
    decide_at,
    dry_run_control,
    latest_decision,
)
from app.research.instruments import INSTRUMENTS
from app.research.strategy import (
    EXPOSURE_POLICY_V3,
    STRATEGY_VERSION,
    ExposurePolicy,
    decide,
    screen,
)
from app.risk.policy import RiskGate
from app.trading_mode import SUPERVISED_EXECUTION_SYMBOLS

StrategyVersion = Literal["spy-directional"]
MAX_INPUT_BYTES = 16_384
MAX_PROPOSAL_QUANTITY = 10_000

HISTORICAL_NOTICE = "Historical Moomoo evidence only; not a current broker snapshot or order authorization."
CURRENT_NOTICE = (
    "Current read-only Moomoo evidence captured during the regular session; "
    "not an order, owner approval or fill."
)


@dataclass(frozen=True)
class CurrentMarketContext:
    """Fresh read-only inputs used by the current-market research/risk tools."""

    decision_time_utc: datetime
    fingerprint: str
    account_provider: Callable[[], AccountSnapshot]
    quote_provider: Callable[[str], Quote]
    control: ControlState


RESEARCH_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string", "minLength": 8, "maxLength": 80},
        "strategy_version": {"type": "string", "enum": [STRATEGY_VERSION]},
    },
    "required": ["run_id", "strategy_version"],
    "additionalProperties": False,
}
EVALUATE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string", "minLength": 8, "maxLength": 80},
        "proposal": {"type": "object"},
    },
    "required": ["run_id", "proposal"],
    "additionalProperties": False,
}


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResearchInput(ToolInput):
    run_id: str = Field(min_length=8, max_length=80)
    strategy_version: StrategyVersion


class EvaluateInput(ToolInput):
    run_id: str = Field(min_length=8, max_length=80)
    proposal: TradeProposal


@dataclass
class _RunState:
    strategy_version: StrategyVersion
    decision_time_utc: datetime | None = None
    decision: DryRunDecision | None = None
    evaluation_now: datetime | None = None


class QoderToolService:
    def __init__(
        self,
        history: MarketHistory,
        fingerprint: str = "historical-dry-run-paper",
        *,
        current: CurrentMarketContext | None = None,
        clock: Callable[[], datetime] | None = None,
        exposure_policy: ExposurePolicy = EXPOSURE_POLICY_V3,
    ) -> None:
        self.history = history
        self.fingerprint = fingerprint
        self.current = current
        self.exposure_policy = exposure_policy
        self.mode = "CURRENT_MARKET_READ_ONLY" if current is not None else "HISTORICAL_DRY_RUN"
        self.notice = CURRENT_NOTICE if current is not None else HISTORICAL_NOTICE
        self._clock = clock or (lambda: datetime.now(UTC))
        self._runs: dict[str, _RunState] = {}

    def create_run(
        self,
        strategy_version: StrategyVersion,
        decision_time_utc: datetime | None = None,
        evaluation_now: datetime | None = None,
    ) -> str:
        if strategy_version != STRATEGY_VERSION:
            raise ValueError("unsupported strategy")
        run_id = f"qoder-{uuid4()}"
        self._runs[run_id] = _RunState(
            strategy_version=strategy_version,
            decision_time_utc=decision_time_utc,
            evaluation_now=evaluation_now,
        )
        return run_id

    def dispatch(self, tool_name: str, payload: object) -> dict[str, object]:
        try:
            if tool_name == "research_market":
                return self.research_market(payload)
            if tool_name == "evaluate_proposal":
                return self.evaluate_proposal(payload)
            return _error("unsupported_tool", "Tool is not allowlisted")
        except Exception:
            return _error("tool_error", "Read-only tool execution failed; abstain")

    def research_market(self, payload: object) -> dict[str, object]:
        validated = _validate(ResearchInput, payload)
        if isinstance(validated, dict):
            return validated
        state = self._runs.get(validated.run_id)
        if state is None or state.strategy_version != validated.strategy_version:
            return _error("unknown_run", "Run ID or strategy is not registered")
        if state.decision is None:
            decision_time = state.decision_time_utc
            if self.current is not None:
                state.decision = self._current_decision(state.strategy_version, decision_time)
            else:
                state.decision = (
                    latest_decision(self.history, validated.strategy_version, self.fingerprint)
                    if decision_time is None
                    else decide_at(
                        self.history,
                        validated.strategy_version,
                        self.fingerprint,
                        decision_time,
                        scenario="pinned historical session",
                    )
                )
        decision = state.decision
        if decision.proposal is not None and decision.proposal.run_id != validated.run_id:
            decision = replace(
                decision,
                proposal=decision.proposal.model_copy(update={"run_id": validated.run_id}),
            )
            state.decision = decision
        return {
            "ok": True,
            "mode": self.mode,
            "run_id": validated.run_id,
            "snapshot": _json_value(decision.snapshot),
            "proposal": (
                decision.proposal.model_dump(mode="json") if decision.proposal is not None else None
            ),
            "notice": self.notice,
        }

    def _current_decision(
        self,
        strategy_version: StrategyVersion,
        decision_time_utc: datetime | None,
    ) -> DryRunDecision:
        assert self.current is not None
        decision_time = decision_time_utc or self.current.decision_time_utc
        snapshot = screen(
            self.history,
            decision_time,
            strategy_version,
            exposure_policy=self.exposure_policy,
        )
        account = self.current.account_provider()
        snapshot, proposal = decide(
            snapshot, self.history, account, exposure_policy=self.exposure_policy
        )
        quote = self.current.quote_provider(proposal.symbol) if proposal is not None else None
        return DryRunDecision(
            scenario="current market read-only",
            snapshot=snapshot,
            proposal=proposal,
            quote=quote,
            account=account,
            control=self.current.control,
            risk_decision=None,
        )

    def evaluate_proposal(self, payload: object) -> dict[str, object]:
        validated = _validate(EvaluateInput, payload)
        if isinstance(validated, dict):
            return validated
        state = self._runs.get(validated.run_id)
        if state is None or state.decision is None:
            return _error("unknown_run", "Run ID has no pinned research artifact")
        original = state.decision.proposal
        if original is None:
            return _error("no_proposal", "The pinned research artifact is not an order proposal")
        proposal = validated.proposal
        if proposal.requested_quantity > MAX_PROPOSAL_QUANTITY:
            return _error("invalid_input", "Proposal quantity exceeds the tool input bound")
        expected = original.model_copy(update={"requested_quantity": proposal.requested_quantity})
        if proposal != expected:
            return _error("invalid_input", "Proposal does not match the pinned research artifact")

        now = state.evaluation_now or state.decision.snapshot.decision_time_utc
        if self.current is not None:
            now = state.evaluation_now or self._clock()
            account = self.current.account_provider()
            quote = self.current.quote_provider(proposal.symbol)
            control = self.current.control
            control_context = (
                "Fresh read-only REST account and quote inputs with writes disabled; "
                "an APPROVE is not owner authorization."
            )
        else:
            account = build_account(now, self.fingerprint, f"qoder-dryrun-{validated.run_id}")
            quote = state.decision.quote
            control = dry_run_control()
            control_context = (
                "Hypothetical policy controls only; no owner approval, broker write or live account state."
            )
        gate = RiskGate(
            expected_account_fingerprint=self.fingerprint,
            allowed_symbols=(
                frozenset(SUPERVISED_EXECUTION_SYMBOLS)
                if self.current
                else frozenset(UNIVERSE)
            ),
            leverage_by_symbol={symbol: item.leverage for symbol, item in INSTRUMENTS.items()},
            policy_version=self.exposure_policy.version,
        )
        decision = gate.evaluate(
            proposal=proposal,
            account=account,
            quote=quote,
            control=control,
            now=now,
        )
        return {
            "ok": True,
            "mode": self.mode,
            "run_id": validated.run_id,
            "risk_decision": decision.model_dump(mode="json"),
            "evaluated_at_utc": now.isoformat(),
            "control_context": control_context,
            "notice": "An APPROVE result is a policy evaluation, never an order authorization.",
        }


def _validate(model: type[ToolInput], payload: object) -> ToolInput | dict[str, object]:
    try:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return _error("invalid_input", "Tool input must be a JSON object")
    if len(encoded) > MAX_INPUT_BYTES:
        return _error("invalid_input", "Tool input exceeds the size bound")
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        details = [
            {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return {
            "ok": False,
            "error": {"code": "invalid_input", "message": "Tool input validation failed", "details": details},
        }


def _error(code: str, message: str) -> dict[str, object]:
    return {"ok": False, "error": {"code": code, "message": message}}


def _json_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (datetime, Decimal)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, Enum):
        return value.value
    return value
