"""Versioned deterministic risk gate for MooTrade.

Two policy versions coexist deliberately:

- ``risk-v1`` is the incumbent activation's policy: fixed 5% effective-exposure
  sizing with 10% single-instrument and 30% gross effective-exposure caps and
  no leveraged instruments. The running AUTO_PAPER activation remains bound to
  this version until the owner authorises a replacement activation.
- ``risk-v2`` is the corrected exposure model: the strategy selects a signed
  target S&P 500 exposure tier (20% floor, 150% exceptional ceiling) and the
  gate enforces the floor, the ceiling, leverage <= 3x, declared-target
  consistency and cash-only purchases.

The activation pin recorded in the ledger selects the version for autonomous
execution; supervised orders use the default risk-v2 gate without the
autonomous floor requirement.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.contracts import (
    AccountSnapshot,
    ControlState,
    OrderSide,
    PolicyDecision,
    Position,
    ProposalAction,
    Quote,
    RiskDecision,
    RuleRejection,
    TradeProposal,
    TradingActivation,
)
from app.research.instruments import CANDIDATE_SYMBOLS, INSTRUMENTS

POLICY_VERSION_V1 = "risk-v1"
POLICY_VERSION_V2 = "risk-v2"
SUPPORTED_POLICY_VERSIONS = (POLICY_VERSION_V1, POLICY_VERSION_V2)

# risk-v1 exposure limits (unchanged from the incumbent activation)
DEFAULT_MAX_SINGLE_EXPOSURE = Decimal("0.10")
DEFAULT_MAX_TOTAL_EXPOSURE = Decimal("0.30")

# risk-v2 exposure limits
DEFAULT_MIN_EFFECTIVE_EXPOSURE_FRACTION = Decimal("0.20")
DEFAULT_MAX_EFFECTIVE_EXPOSURE_FRACTION = Decimal("1.50")
MAX_APPROVED_LEVERAGE = Decimal("3")
EXPOSURE_CONSISTENCY_TOLERANCE = Decimal("0.05")

DEFAULT_MAX_DAILY_DRAWDOWN = Decimal("0.02")
DEFAULT_BUYING_POWER_BUFFER = Decimal("5")

DEFAULT_ALLOWED_SYMBOLS = frozenset(CANDIDATE_SYMBOLS)
DEFAULT_LEVERAGE_BY_SYMBOL: dict[str, Decimal] = {
    symbol: instrument.leverage for symbol, instrument in INSTRUMENTS.items()
}


class RiskGate:
    def __init__(
        self,
        expected_account_fingerprint: str,
        *,
        policy_version: str = POLICY_VERSION_V1,
        allowed_symbols: frozenset[str] = DEFAULT_ALLOWED_SYMBOLS,
        max_single_exposure: Decimal = DEFAULT_MAX_SINGLE_EXPOSURE,
        max_total_exposure: Decimal = DEFAULT_MAX_TOTAL_EXPOSURE,
        min_effective_exposure_fraction: Decimal = DEFAULT_MIN_EFFECTIVE_EXPOSURE_FRACTION,
        max_effective_exposure_fraction: Decimal = DEFAULT_MAX_EFFECTIVE_EXPOSURE_FRACTION,
        max_open_positions: int = 3,
        max_daily_drawdown: Decimal = DEFAULT_MAX_DAILY_DRAWDOWN,
        buying_power_buffer: Decimal = DEFAULT_BUYING_POWER_BUFFER,
        max_quote_age_seconds: int = 300,
        max_account_age_seconds: int = 60,
        max_clock_skew_seconds: int = 5,
        approval_ttl_seconds: int = 30,
        leverage_by_symbol: Mapping[str, Decimal] | None = None,
        allow_leveraged: bool = False,
        enforce_min_exposure: bool = True,
    ) -> None:
        if policy_version not in SUPPORTED_POLICY_VERSIONS:
            raise ValueError(f"unsupported risk policy version {policy_version!r}")
        self.policy_version = policy_version
        self.expected_account_fingerprint = expected_account_fingerprint
        self.allowed_symbols = allowed_symbols
        self.leverage_by_symbol = {
            symbol: Decimal(value)
            for symbol, value in (leverage_by_symbol or DEFAULT_LEVERAGE_BY_SYMBOL).items()
        }
        self.max_single_exposure = max_single_exposure
        self.max_total_exposure = max_total_exposure
        self.min_effective_exposure_fraction = min_effective_exposure_fraction
        self.max_effective_exposure_fraction = max_effective_exposure_fraction
        self.max_open_positions = max_open_positions
        self.max_daily_drawdown = max_daily_drawdown
        self.buying_power_buffer = buying_power_buffer
        self.max_quote_age_seconds = max_quote_age_seconds
        self.max_account_age_seconds = max_account_age_seconds
        self.max_clock_skew_seconds = max_clock_skew_seconds
        self.approval_ttl_seconds = approval_ttl_seconds
        self.allow_leveraged = allow_leveraged
        self.enforce_min_exposure = enforce_min_exposure

    @classmethod
    def from_activation(cls, activation: TradingActivation) -> "RiskGate":
        """Build the gate that a recorded activation pin actually authorises."""
        common = {
            "expected_account_fingerprint": activation.account_fingerprint,
            "allowed_symbols": frozenset(activation.allowed_symbols),
            "max_daily_drawdown": activation.max_daily_drawdown,
            "leverage_by_symbol": DEFAULT_LEVERAGE_BY_SYMBOL,
        }
        if activation.risk_policy_version == POLICY_VERSION_V1:
            assert activation.max_single_exposure is not None
            assert activation.max_total_exposure is not None
            return cls(
                policy_version=POLICY_VERSION_V1,
                max_single_exposure=activation.max_single_exposure,
                max_total_exposure=activation.max_total_exposure,
                allow_leveraged=False,
                **common,
            )
        assert activation.min_effective_exposure_fraction is not None
        assert activation.max_effective_exposure_fraction is not None
        return cls(
            policy_version=POLICY_VERSION_V2,
            min_effective_exposure_fraction=activation.min_effective_exposure_fraction,
            max_effective_exposure_fraction=activation.max_effective_exposure_fraction,
            allow_leveraged=True,
            enforce_min_exposure=True,
            **common,
        )

    def evaluate(
        self,
        proposal: TradeProposal,
        account: AccountSnapshot,
        quote: Quote | None,
        control: ControlState,
        now: datetime,
        duplicate: bool = False,
        unknown_submission: bool = False,
    ) -> RiskDecision:
        reasons: list[RuleRejection] = []

        def reject(rule_id: str, message: str, **details: object) -> None:
            reasons.append(
                RuleRejection(
                    rule_id=rule_id,
                    message=message,
                    details={key: str(value) for key, value in details.items()},
                )
            )

        if account.environment != "paper" or account.account_fingerprint != self.expected_account_fingerprint:
            reject("R001", "Competition paper account is not verified")
        if account.equity <= 0 or account.day_start_equity <= 0 or account.cash < 0 or account.buying_power < 0:
            reject("R007", "Account data is invalid")

        if proposal.symbol not in self.allowed_symbols:
            reject("R002", "Symbol is outside the approved allowlist", symbol=proposal.symbol)
        leverage = self.leverage_by_symbol.get(proposal.symbol, Decimal("1"))
        if leverage <= 0:
            reject("R007", "Instrument leverage metadata is invalid", symbol=proposal.symbol)
        if self.policy_version == POLICY_VERSION_V1:
            if leverage > 1 and not self.allow_leveraged:
                reject(
                    "R015",
                    "Leveraged instruments require separate leverage approval",
                    symbol=proposal.symbol,
                    leverage=leverage,
                )
        else:
            if leverage > MAX_APPROVED_LEVERAGE:
                reject(
                    "R015",
                    "Leverage exceeds the approved 3x daily maximum",
                    symbol=proposal.symbol,
                    leverage=leverage,
                    maximum=MAX_APPROVED_LEVERAGE,
                )

        position = next(
            (item for item in account.positions if item.symbol == proposal.symbol),
            Position(symbol=proposal.symbol, quantity=0, market_value=Decimal("0")),
        )
        if proposal.action is ProposalAction.NO_TRADE:
            reject("R003", "NO_TRADE is not an order submission")
        elif proposal.action is ProposalAction.SELL and proposal.requested_quantity > position.quantity:
            reject(
                "R003",
                "Sell quantity would create a short position",
                held=position.quantity,
                requested=proposal.requested_quantity,
            )

        quote_valid = quote is not None and quote.price > 0 and quote.currency == "USD"
        if quote is None:
            reject("R007", "Quote is unavailable")
        else:
            if not quote_valid:
                reject("R007", "Quote price or currency is invalid")
            if quote.symbol != proposal.symbol:
                reject("R007", "Quote symbol does not match proposal")
            quote_age = (now - quote.as_of_utc).total_seconds()
            if quote_age < -self.max_clock_skew_seconds:
                reject("R007", "Quote is timestamped in the future", age_seconds=quote_age)
            elif quote_age > self.max_quote_age_seconds:
                reject(
                    "R007",
                    f"Quote is stale (older than {self.max_quote_age_seconds}s)",
                    age_seconds=quote_age,
                )
            if not quote.regular_session_open:
                reject("R012", "Orders are limited to the regular exchange session")

        account_age = (now - account.as_of_utc).total_seconds()
        if account_age < -self.max_clock_skew_seconds:
            reject(
                "R007",
                "Account snapshot is timestamped in the future",
                age_seconds=account_age,
            )
        elif account_age > self.max_account_age_seconds:
            reject(
                "R007",
                f"Account snapshot is stale (older than {self.max_account_age_seconds}s)",
                age_seconds=account_age,
            )
        if not account.reconciled or account.unknown_orders or unknown_submission:
            reject(
                "R009",
                "Account reconciliation is not clean",
                reconciled=account.reconciled,
                unknown_orders=account.unknown_orders,
                local_unknown_submission=unknown_submission,
            )
        if control.order_writes_enabled is False or control.kill_switch_engaged or control.circuit_breaker_open:
            reject(
                "R010",
                "Order writes are disabled by control state",
                writes_enabled=control.order_writes_enabled,
                kill_switch=control.kill_switch_engaged,
                circuit_breaker=control.circuit_breaker_open,
            )
        if proposal.action is not ProposalAction.NO_TRADE and not control.first_order_approved:
            reject("R014", "First paper order requires explicit owner approval")
        if duplicate:
            reject("R011", "Proposal already has a durable submission record")

        if proposal.action is ProposalAction.BUY:
            drawdown = (account.day_start_equity - account.equity) / account.day_start_equity
            if drawdown >= self.max_daily_drawdown:
                reject(
                    "R006",
                    "Daily drawdown threshold blocks new buying",
                    drawdown=drawdown,
                    limit=self.max_daily_drawdown,
                )

            held_symbols = {item.symbol for item in account.positions if item.quantity > 0}
            pending_symbols = {
                order.symbol
                for order in account.open_orders
                if order.side is OrderSide.BUY and order.remaining_quantity > 0
            }
            post_symbols = held_symbols | pending_symbols | {proposal.symbol}
            if len(post_symbols) > self.max_open_positions:
                reject(
                    "R013",
                    "Post-order open position count exceeds limit",
                    positions=len(post_symbols),
                    limit=self.max_open_positions,
                )

            if quote_valid and quote is not None:
                requested_notional = quote.price * proposal.requested_quantity
                effective_requested = requested_notional * leverage
                if self.policy_version == POLICY_VERSION_V1:
                    pending_single = sum(
                        (
                            order.reference_price
                            * order.remaining_quantity
                            * self.leverage_by_symbol.get(order.symbol, Decimal("1"))
                            for order in account.open_orders
                            if order.symbol == proposal.symbol and order.side is OrderSide.BUY
                        ),
                        Decimal("0"),
                    )
                    pending_total = sum(
                        (
                            order.reference_price
                            * order.remaining_quantity
                            * self.leverage_by_symbol.get(order.symbol, Decimal("1"))
                            for order in account.open_orders
                            if order.side is OrderSide.BUY
                        ),
                        Decimal("0"),
                    )
                    current_total = sum(
                        (
                            item.market_value
                            * self.leverage_by_symbol.get(item.symbol, Decimal("1"))
                            for item in account.positions
                        ),
                        Decimal("0"),
                    )
                    single_limit = account.equity * self.max_single_exposure
                    total_limit = account.equity * self.max_total_exposure
                    effective_position = position.market_value * leverage
                    post_single = effective_position + pending_single + effective_requested
                    post_total = current_total + pending_total + effective_requested
                    if post_single > single_limit:
                        reject(
                            "R004",
                            "Post-order instrument exposure exceeds limit",
                            actual=post_single,
                            limit=single_limit,
                        )
                    if post_total > total_limit:
                        reject(
                            "R005",
                            "Post-order gross exposure exceeds limit",
                            actual=post_total,
                            limit=total_limit,
                        )
                else:
                    direction = (
                        INSTRUMENTS[proposal.symbol].direction
                        if proposal.symbol in INSTRUMENTS
                        else Decimal("1")
                    )
                    equity_fraction = (
                        effective_requested * direction / account.equity
                    )
                    if (
                        self.enforce_min_exposure
                        and abs(equity_fraction)
                        < self.min_effective_exposure_fraction - EXPOSURE_CONSISTENCY_TOLERANCE
                    ):
                        reject(
                            "R016",
                            "Effective exposure is below the minimum floor",
                            effective_fraction=equity_fraction,
                            minimum=self.min_effective_exposure_fraction,
                        )
                    pending_effective = sum(
                        (
                            order.reference_price
                            * order.remaining_quantity
                            * self.leverage_by_symbol.get(order.symbol, Decimal("1"))
                            * (
                                INSTRUMENTS[order.symbol].direction
                                if order.symbol in INSTRUMENTS
                                else Decimal("1")
                            )
                            for order in account.open_orders
                            if order.side is OrderSide.BUY
                        ),
                        Decimal("0"),
                    )
                    current_effective = sum(
                        (
                            item.market_value
                            * self.leverage_by_symbol.get(item.symbol, Decimal("1"))
                            * (
                                INSTRUMENTS[item.symbol].direction
                                if item.symbol in INSTRUMENTS
                                else Decimal("1")
                            )
                            for item in account.positions
                        ),
                        Decimal("0"),
                    )
                    post_total_effective = (
                        current_effective + pending_effective + effective_requested * direction
                    )
                    if (
                        abs(post_total_effective)
                        > account.equity
                        * (self.max_effective_exposure_fraction + EXPOSURE_CONSISTENCY_TOLERANCE)
                    ):
                        reject(
                            "R017",
                            "Post-order effective exposure exceeds the policy maximum",
                            effective_fraction=post_total_effective / account.equity,
                            maximum=self.max_effective_exposure_fraction,
                        )
                    if proposal.target_exposure_fraction is not None:
                        declared = proposal.target_exposure_fraction
                        if (
                            abs(equity_fraction - declared)
                            > EXPOSURE_CONSISTENCY_TOLERANCE
                        ):
                            reject(
                                "R018",
                                "Order quantity does not match the declared target exposure",
                                effective_fraction=equity_fraction,
                                declared=declared,
                                tolerance=EXPOSURE_CONSISTENCY_TOLERANCE,
                            )
                # Cash-only: never use broker margin even if buying power is higher.
                available_funds = max(
                    Decimal("0"),
                    min(account.cash, account.buying_power) - self.buying_power_buffer,
                )
                if requested_notional > available_funds:
                    reject(
                        "R008",
                        "Insufficient unlevered buying power after buffer",
                        required=requested_notional,
                        available=available_funds,
                    )

        approved = not reasons and proposal.action is not ProposalAction.NO_TRADE
        return RiskDecision(
            proposal_id=proposal.proposal_id,
            policy_version=self.policy_version,
            decision=PolicyDecision.APPROVE if approved else PolicyDecision.REJECT,
            reasons=tuple(reasons),
            approved_quantity=proposal.requested_quantity if approved else 0,
            account_snapshot_id=account.snapshot_id,
            expires_at_utc=now + timedelta(seconds=self.approval_ttl_seconds),
        )

    def fail_closed(
        self,
        proposal: TradeProposal,
        now: datetime,
        reason: str,
        snapshot_id: str = "unavailable",
    ) -> RiskDecision:
        return RiskDecision(
            proposal_id=proposal.proposal_id,
            policy_version=self.policy_version,
            decision=PolicyDecision.REJECT,
            reasons=(RuleRejection(rule_id="R009", message=reason),),
            approved_quantity=0,
            account_snapshot_id=snapshot_id,
            expires_at_utc=now,
        )
