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
)


class RiskGate:
    def __init__(
        self,
        expected_account_fingerprint: str,
        allowed_symbols: frozenset[str] = frozenset({"SPY", "QQQ", "IWM"}),
        max_single_exposure: Decimal = Decimal("0.10"),
        max_total_exposure: Decimal = Decimal("0.30"),
        max_open_positions: int = 3,
        max_daily_drawdown: Decimal = Decimal("0.02"),
        buying_power_buffer: Decimal = Decimal("5"),
        max_quote_age_seconds: int = 300,
        max_account_age_seconds: int = 60,
        max_clock_skew_seconds: int = 5,
        approval_ttl_seconds: int = 30,
        leverage_by_symbol: Mapping[str, Decimal] | None = None,
        allow_leveraged: bool = False,
    ) -> None:
        self.expected_account_fingerprint = expected_account_fingerprint
        self.allowed_symbols = allowed_symbols
        self.leverage_by_symbol = {
            symbol: Decimal(value)
            for symbol, value in (leverage_by_symbol or {}).items()
        }
        self.allow_leveraged = allow_leveraged
        self.max_single_exposure = max_single_exposure
        self.max_total_exposure = max_total_exposure
        self.max_open_positions = max_open_positions
        self.max_daily_drawdown = max_daily_drawdown
        self.buying_power_buffer = buying_power_buffer
        self.max_quote_age_seconds = max_quote_age_seconds
        self.max_account_age_seconds = max_account_age_seconds
        self.max_clock_skew_seconds = max_clock_skew_seconds
        self.approval_ttl_seconds = approval_ttl_seconds

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
        if leverage > 1 and not self.allow_leveraged:
            reject(
                "R015",
                "Leveraged instruments require separate leverage approval",
                symbol=proposal.symbol,
                leverage=leverage,
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
                # Cash-only: never use broker margin even if buying power is higher.
                available_funds = max(
                    Decimal("0"),
                    min(account.cash, account.buying_power) - self.buying_power_buffer,
                )

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
            policy_version="risk-v1",
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
            policy_version="risk-v1",
            decision=PolicyDecision.REJECT,
            reasons=(RuleRejection(rule_id="R009", message=reason),),
            approved_quantity=0,
            account_snapshot_id=snapshot_id,
            expires_at_utc=now,
        )
