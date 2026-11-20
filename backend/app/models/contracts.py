from decimal import Decimal
from enum import Enum
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProposalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PolicyDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class TradingMode(str, Enum):
    READ_ONLY = "READ_ONLY"
    SUPERVISED_PAPER = "SUPERVISED_PAPER"
    AUTO_PAPER = "AUTO_PAPER"


class OrderStatus(str, Enum):
    PROPOSED = "PROPOSED"
    POLICY_REJECTED = "POLICY_REJECTED"
    POLICY_APPROVED = "POLICY_APPROVED"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class TradeProposal(ContractModel):
    schema_version: Literal["1"] = "1"
    proposal_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    decision_time_utc: AwareDatetime
    data_as_of_utc: AwareDatetime
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,9}$")
    action: ProposalAction
    requested_quantity: int = Field(ge=0)
    thesis: str = Field(min_length=1)
    invalidation: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()
    target_exposure_fraction: Decimal | None = Field(
        default=None,
        description="Signed S&P 500 exposure as a fraction of equity that the quantity is sized to express",
    )

    @model_validator(mode="after")
    def validate_action_and_timestamps(self) -> Self:
        if self.action is ProposalAction.NO_TRADE:
            if self.requested_quantity != 0:
                raise ValueError("NO_TRADE must have zero quantity")
        elif self.requested_quantity < 1:
            raise ValueError("BUY and SELL proposals require positive quantity")
        if self.data_as_of_utc > self.decision_time_utc:
            raise ValueError("data timestamp cannot be after decision time")
        if self.target_exposure_fraction is not None and self.target_exposure_fraction == 0:
            raise ValueError("declared target exposure must not be zero")
        return self


class Quote(ContractModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,9}$")
    price: Decimal = Field(gt=0)
    currency: Literal["USD"] = "USD"
    as_of_utc: AwareDatetime
    regular_session_open: bool


class Position(ContractModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,9}$")
    quantity: int = Field(ge=0)
    market_value: Decimal = Field(ge=0)


class OpenOrder(ContractModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,9}$")
    side: OrderSide
    remaining_quantity: int = Field(gt=0)
    reference_price: Decimal = Field(gt=0)


class AccountSnapshot(ContractModel):
    snapshot_id: str = Field(min_length=1)
    account_fingerprint: str = Field(min_length=1)
    environment: Literal["paper"]
    currency: Literal["USD"] = "USD"
    equity: Decimal = Field(gt=0)
    day_start_equity: Decimal = Field(gt=0)
    peak_equity: Decimal = Field(gt=0)
    cash: Decimal = Field(ge=0)
    buying_power: Decimal = Field(ge=0)
    positions: tuple[Position, ...] = ()
    open_orders: tuple[OpenOrder, ...] = ()
    as_of_utc: AwareDatetime
    reconciled: bool
    unknown_orders: int = Field(ge=0, default=0)


class ControlState(ContractModel):
    order_writes_enabled: bool = False
    kill_switch_engaged: bool = False
    circuit_breaker_open: bool = False
    first_order_approved: bool = False
    # Mode-aware R014: a valid, unexpired autonomous policy activation replaces
    # exact-order approval. The risk gate re-validates it deterministically.
    autonomous_activation: "TradingActivation | None" = None


class TradingActivation(ContractModel):
    schema_version: Literal["1"] = "1"
    activated_at_utc: AwareDatetime
    activated_by: str = Field(min_length=1)
    account_fingerprint: str = Field(min_length=64, max_length=64)
    strategy_version: str = Field(min_length=1)
    allowed_symbols: tuple[str, ...]
    risk_policy_version: Literal["risk-v3"]
    min_effective_exposure_fraction: Decimal = Field(gt=0, le=1)
    max_effective_exposure_fraction: Decimal = Field(gt=0)
    max_daily_drawdown: Decimal
    paper_only: Literal[True] = True
    order_writes_enabled: Literal[True] = True
    expires_at_utc: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        if self.min_effective_exposure_fraction >= self.max_effective_exposure_fraction:
            raise ValueError("minimum exposure must be below the maximum")
        if self.max_daily_drawdown <= 0 or self.max_daily_drawdown > 1:
            raise ValueError("max daily drawdown must be within (0, 1]")
        if len(self.allowed_symbols) == 0 or len(set(self.allowed_symbols)) != len(self.allowed_symbols):
            raise ValueError("allowed symbols must be a non-empty tuple of unique symbols")
        if (
            self.expires_at_utc is not None
            and self.expires_at_utc <= self.activated_at_utc
        ):
            raise ValueError("activation expiry must be after the activation time")
        return self


class RuleRejection(ContractModel):
    rule_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, str] = Field(default_factory=dict)


class RiskDecision(ContractModel):
    proposal_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    decision: PolicyDecision
    reasons: tuple[RuleRejection, ...] = ()
    approved_quantity: int = Field(ge=0)
    account_snapshot_id: str = Field(min_length=1)
    expires_at_utc: AwareDatetime

    @model_validator(mode="after")
    def validate_approval(self) -> Self:
        if self.decision is PolicyDecision.APPROVE and self.approved_quantity < 1:
            raise ValueError("an approval requires positive quantity")
        if self.decision is PolicyDecision.REJECT and self.approved_quantity != 0:
            raise ValueError("a rejection cannot approve quantity")
        return self


class OrderRequest(ContractModel):
    client_order_key: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    account_snapshot_id: str = Field(min_length=1)
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,9}$")
    side: OrderSide
    quantity: int = Field(gt=0)
    reference_price: Decimal = Field(gt=0)
    order_type: Literal["MARKET"] = "MARKET"
    time_in_force: Literal["DAY"] = "DAY"


class Fill(ContractModel):
    broker_fill_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0)
    filled_at_utc: AwareDatetime


class OrderRecord(ContractModel):
    client_order_key: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    paper_account_fingerprint: str = Field(min_length=1)
    broker_order_id: str | None = None
    status: OrderStatus
    request: OrderRequest
    submitted_at_utc: AwareDatetime | None = None
    last_broker_sync_utc: AwareDatetime | None = None
    fills: tuple[Fill, ...] = ()


ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PROPOSED: frozenset({OrderStatus.POLICY_APPROVED, OrderStatus.POLICY_REJECTED}),
    OrderStatus.POLICY_APPROVED: frozenset({OrderStatus.SUBMITTING, OrderStatus.POLICY_REJECTED}),
    OrderStatus.POLICY_REJECTED: frozenset(),
    OrderStatus.SUBMITTING: frozenset(
        {
            OrderStatus.ACKNOWLEDGED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.ACKNOWLEDGED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.UNKNOWN}
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.UNKNOWN: frozenset(
        {
            OrderStatus.ACKNOWLEDGED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        }
    ),
}


def can_transition(current: OrderStatus, next_status: OrderStatus) -> bool:
    return current is next_status or next_status in ORDER_TRANSITIONS[current]
