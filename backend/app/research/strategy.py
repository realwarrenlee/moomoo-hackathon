"""Deterministic daily SPY directional policy.

The signal is evaluated only on completed SPY daily bars; a decision made after
the close is eligible for the next open. Two exposure policies coexist:

- ``risk-v1`` (incumbent activation): fixed 5% effective exposure, 1x ETFs only.
- ``risk-v2`` (corrected model): a deterministic tier table maps the SPY
  10-session return, 50-session trend and 20-session volatility to a signed
  target S&P 500 exposure fraction (20% floor, 150% exceptional ceiling). The
  instrument is chosen AFTER the target: |target| <= 100% uses SPY/SH, larger
  targets use UPRO/SPXU. Leverage is an instrument for scaling exposure, not
  the strategy itself.

The tier table:

    |return| band   trend not confirming   trend confirming        notes
    < 1.5%          0% (CASH)              0% (CASH)
    1.5% - 3%       20%                    20%                     WEAK
    3% - 5%         40%                    60%                     MODERATE
    5% - 8%         80%                    100%                    STRONG
    >= 8%           100%                   150%                    EXCEPTIONAL

Volatility gates: annualized 20-session volatility above 40% forces CASH;
above 30% caps the target at 100% (no 3x instruments). For risk-v2 the
direction is taken from the 10-session return alone, and trend confirmation
selects the higher value inside each band; the risk-v1 direction detection is
unchanged.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal

from app.models.contracts import AccountSnapshot, ProposalAction, TradeProposal
from app.research.data import MarketHistory
from app.research.instruments import (
    CANDIDATE_SYMBOLS,
    INSTRUMENTS,
    Instrument,
    select_instrument,
    select_instrument_for_exposure,
)
from app.risk.policy import DEFAULT_BUYING_POWER_BUFFER, POLICY_VERSION_V1

STRATEGY_VERSION = "spy-directional"
RETURN_LOOKBACK = 10
TREND_WINDOW = 50
VOLATILITY_WINDOW = 20
MIN_COMPLETED_SESSIONS = TREND_WINDOW + 1
DIRECTION_THRESHOLD = Decimal("0.015")
STRONG_RETURN_THRESHOLD = Decimal("0.03")
MAX_VOLATILITY_FOR_DIRECTION = Decimal("0.40")
MAX_VOLATILITY_FOR_LEVERAGE = Decimal("0.30")

# risk-v1 fixed allocation (incumbent activation, unchanged)
POSITION_FRACTION = Decimal("0.05")
# risk-v2 tier boundaries
MIN_EXPOSURE_FRACTION = Decimal("0.20")
MAX_EXPOSURE_FRACTION = Decimal("1.50")
RESIZE_MIN_RELATIVE_CHANGE = Decimal("0.05")
DEFAULT_MAX_LEVERAGED_HOLDING_SESSIONS = 5

BULLISH_STATES = frozenset({"BULLISH", "STRONG_BULLISH"})
BEARISH_STATES = frozenset({"BEARISH", "STRONG_BEARISH"})


@dataclass(frozen=True)
class ExposureBand:
    tier: str
    min_return: Decimal
    max_return: Decimal | None
    base_fraction: Decimal
    trend_fraction: Decimal | None


@dataclass(frozen=True)
class ExposurePolicy:
    version: str
    fixed_fraction: Decimal | None
    allow_leveraged: bool
    bands: tuple[ExposureBand, ...] = ()
    max_leveraged_holding_sessions: int | None = None


EXPOSURE_POLICY_V1 = ExposurePolicy(
    version=POLICY_VERSION_V1,
    fixed_fraction=POSITION_FRACTION,
    allow_leveraged=False,
)

EXPOSURE_POLICY_V2 = ExposurePolicy(
    version="risk-v2",
    fixed_fraction=None,
    allow_leveraged=True,
    bands=(
        ExposureBand("WEAK", Decimal("0.015"), Decimal("0.03"), Decimal("0.20"), None),
        ExposureBand(
            "MODERATE", Decimal("0.03"), Decimal("0.05"), Decimal("0.40"), Decimal("0.60")
        ),
        ExposureBand(
            "STRONG", Decimal("0.05"), Decimal("0.08"), Decimal("0.80"), Decimal("1.00")
        ),
        ExposureBand("EXCEPTIONAL", Decimal("0.08"), None, Decimal("1.00"), Decimal("1.50")),
    ),
    max_leveraged_holding_sessions=DEFAULT_MAX_LEVERAGED_HOLDING_SESSIONS,
)


@dataclass(frozen=True)
class Candidate:
    symbol: str
    direction: int
    leverage: Decimal
    effective_exposure: Decimal
    close: Decimal | None
    eligible: bool
    selected: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ResearchSnapshot:
    strategy_version: str
    decision_time_utc: datetime
    data_as_of_utc: datetime
    spy_session_date: str | None
    spy_close: Decimal | None
    spy_return_10d: Decimal | None
    spy_sma50: Decimal | None
    spy_trend_pct: Decimal | None
    spy_volatility_20d: Decimal | None
    market_state: str
    direction: str | None
    target_symbol: str | None
    target_effective_exposure: Decimal
    current_symbol: str | None
    current_quantity: int
    action: str
    reentry_symbol: str | None
    candidates: tuple[Candidate, ...]
    selected_symbol: str | None
    decision_reason: str
    no_trade_reason: str | None
    target_exposure_fraction: Decimal | None = None
    exposure_tier: str | None = None
    duration_exit: bool = False


def _empty_snapshot(
    decision_time_utc: datetime,
    reason: str,
    *,
    market_state: str = "INSUFFICIENT_DATA",
) -> ResearchSnapshot:
    return ResearchSnapshot(
        strategy_version=STRATEGY_VERSION,
        decision_time_utc=decision_time_utc,
        data_as_of_utc=decision_time_utc,
        spy_session_date=None,
        spy_close=None,
        spy_return_10d=None,
        spy_sma50=None,
        spy_trend_pct=None,
        spy_volatility_20d=None,
        market_state=market_state,
        direction=None,
        target_symbol=None,
        target_effective_exposure=Decimal("0"),
        current_symbol=None,
        current_quantity=0,
        action="NO_TRADE",
        reentry_symbol=None,
        candidates=(),
        selected_symbol=None,
        decision_reason=reason,
        no_trade_reason=reason,
    )


def _volatility(closes: tuple[Decimal, ...]) -> Decimal:
    returns = [
        float(closes[index] / closes[index - 1] - 1)
        for index in range(len(closes) - VOLATILITY_WINDOW, len(closes))
    ]
    return Decimal(str(statistics.stdev(returns) * math.sqrt(252)))


def _target_exposure_fraction(
    direction: int,
    return_10d: Decimal,
    trend_pct: Decimal,
    volatility: Decimal,
    policy: ExposurePolicy,
) -> tuple[Decimal, str | None]:
    """Map SPY measurements to a signed exposure fraction and tier name."""
    if direction == 0 or volatility > MAX_VOLATILITY_FOR_DIRECTION:
        return Decimal("0"), "NEUTRAL"
    magnitude = abs(return_10d)
    trend_confirms = trend_pct * direction > 0
    fraction = Decimal("0")
    tier = "NEUTRAL"
    for band in policy.bands:
        if magnitude >= band.min_return and (
            band.max_return is None or magnitude < band.max_return
        ):
            fraction = (
                band.trend_fraction
                if trend_confirms and band.trend_fraction is not None
                else band.base_fraction
            )
            tier = band.tier
            break
    if fraction > Decimal("1") and volatility > MAX_VOLATILITY_FOR_LEVERAGE:
        fraction = Decimal("1")
    return Decimal(direction) * fraction, tier


def _candidate(
    symbol: str,
    direction: int,
    leverage: Decimal,
    close: Decimal | None,
    allow_leveraged: bool,
    volatility: Decimal | None,
) -> Candidate:
    instrument: Instrument = INSTRUMENTS[symbol]
    reasons: list[str] = []
    if close is None:
        reasons.append(f"No completed bar is available for {symbol}")
    if direction == 0:
        reasons.append("The SPY signal is neutral")
    elif instrument.direction != direction:
        reasons.append("Instrument direction does not match the SPY signal")
    if instrument.leveraged and not allow_leveraged:
        reasons.append("3x instruments are excluded from this evaluation")
    elif (
        instrument.leveraged
        and allow_leveraged
        and volatility is not None
        and volatility > MAX_VOLATILITY_FOR_LEVERAGE
    ):
        reasons.append(
            f"Volatility exceeds the {MAX_VOLATILITY_FOR_LEVERAGE:.0%} leverage ceiling"
        )
    eligible = close is not None and instrument.direction == direction and (
        not instrument.leveraged
        or (
            allow_leveraged
            and (volatility is None or volatility <= MAX_VOLATILITY_FOR_LEVERAGE)
        )
    )
    return Candidate(
        symbol=symbol,
        direction=instrument.direction,
        leverage=instrument.leverage,
        effective_exposure=instrument.effective_exposure,
        close=close,
        eligible=eligible,
        selected=False,
        reasons=tuple(reasons),
    )


def screen(
    history: MarketHistory,
    decision_time_utc: datetime,
    strategy_version: str = STRATEGY_VERSION,
    *,
    exposure_policy: ExposurePolicy = EXPOSURE_POLICY_V2,
) -> ResearchSnapshot:
    if strategy_version != STRATEGY_VERSION:
        raise ValueError(f"unknown strategy {strategy_version!r}")
    if decision_time_utc.tzinfo is None:
        raise ValueError("decision time must be timezone-aware")
    if "SPY" not in history.symbols:
        return _empty_snapshot(decision_time_utc, "SPY history is unavailable")
    spy_bars = history.bars_as_of("SPY", decision_time_utc)
    if len(spy_bars) < MIN_COMPLETED_SESSIONS:
        return _empty_snapshot(
            decision_time_utc,
            f"SPY requires {MIN_COMPLETED_SESSIONS} completed sessions",
        )

    closes = tuple(bar.close for bar in spy_bars)
    close = closes[-1]
    return_10d = close / closes[-1 - RETURN_LOOKBACK] - 1
    sma50 = sum(closes[-TREND_WINDOW:], Decimal("0")) / TREND_WINDOW
    trend_pct = close / sma50 - 1
    volatility = _volatility(closes)

    direction = 0
    market_state = "NEUTRAL"
    reason = (
        f"SPY 10-session return {return_10d:.2%}, close {close} versus "
        f"50-session SMA {sma50:.2f}, annualized 20-session volatility {volatility:.2%}."
    )
    if volatility > MAX_VOLATILITY_FOR_DIRECTION:
        reason += f" Volatility exceeds the {MAX_VOLATILITY_FOR_DIRECTION:.0%} directional ceiling; hold cash."
    elif exposure_policy.version == POLICY_VERSION_V1:
        # Incumbent detection: return AND trend must agree.
        if return_10d >= DIRECTION_THRESHOLD and close > sma50:
            direction = 1
            market_state = "BULLISH"
            if (
                return_10d >= STRONG_RETURN_THRESHOLD
                and volatility <= MAX_VOLATILITY_FOR_LEVERAGE
            ):
                market_state = "STRONG_BULLISH"
            reason += f" Direction is {market_state.replace('_', ' ').lower()}; target long S&P 500 exposure."
        elif return_10d <= -DIRECTION_THRESHOLD and close < sma50:
            direction = -1
            market_state = "BEARISH"
            if (
                return_10d <= -STRONG_RETURN_THRESHOLD
                and volatility <= MAX_VOLATILITY_FOR_LEVERAGE
            ):
                market_state = "STRONG_BEARISH"
            reason += f" Direction is {market_state.replace('_', ' ').lower()}; target inverse S&P 500 exposure."
        else:
            reason += " Direction is neutral; remain in cash."
    else:
        # risk-v2 detection: direction comes from the return alone; trend
        # confirmation raises the target inside each exposure band.
        if return_10d >= DIRECTION_THRESHOLD:
            direction = 1
            market_state = "BULLISH"
            if (
                return_10d >= STRONG_RETURN_THRESHOLD
                and volatility <= MAX_VOLATILITY_FOR_LEVERAGE
            ):
                market_state = "STRONG_BULLISH"
            reason += f" Direction is {market_state.replace('_', ' ').lower()}; target long S&P 500 exposure."
        elif return_10d <= -DIRECTION_THRESHOLD:
            direction = -1
            market_state = "BEARISH"
            if (
                return_10d <= -STRONG_RETURN_THRESHOLD
                and volatility <= MAX_VOLATILITY_FOR_LEVERAGE
            ):
                market_state = "STRONG_BEARISH"
            reason += f" Direction is {market_state.replace('_', ' ').lower()}; target inverse S&P 500 exposure."
        else:
            reason += " Direction is neutral; remain in cash."

    strong = market_state.startswith("STRONG_")
    if exposure_policy.version == POLICY_VERSION_V1:
        target = select_instrument(direction, strong, allow_leveraged=False)
        target_fraction = None
        tier = None
        candidate_allow = False
    else:
        target_fraction, tier = _target_exposure_fraction(
            direction, return_10d, trend_pct, volatility, exposure_policy
        )
        target = select_instrument_for_exposure(direction, target_fraction)
        candidate_allow = True
        reason += (
            f" Exposure tier {tier} targets {target_fraction:+.0%} of equity"
            f"{f' via {target}' if target else '; hold cash'}."
        )
    candidates = tuple(
        replace(
            _candidate(
                symbol,
                direction,
                INSTRUMENTS[symbol].leverage,
                history.bar_on(symbol, spy_bars[-1].session_date).close
                if history.bar_on(symbol, spy_bars[-1].session_date) is not None
                else None,
                candidate_allow,
                volatility,
            ),
            selected=symbol == target,
        )
        for symbol in CANDIDATE_SYMBOLS
    )
    target_bar = history.bar_on(target, spy_bars[-1].session_date) if target else None
    data_as_of = spy_bars[-1].available_at_utc
    if target_bar is not None:
        data_as_of = max(data_as_of, target_bar.available_at_utc)
    target_exposure = (
        INSTRUMENTS[target].effective_exposure if target is not None else Decimal("0")
    )
    return ResearchSnapshot(
        strategy_version=strategy_version,
        decision_time_utc=decision_time_utc,
        data_as_of_utc=data_as_of,
        spy_session_date=spy_bars[-1].session_date.isoformat(),
        spy_close=close,
        spy_return_10d=return_10d,
        spy_sma50=sma50,
        spy_trend_pct=trend_pct,
        spy_volatility_20d=volatility,
        market_state=market_state,
        direction="BULLISH" if direction > 0 else ("BEARISH" if direction < 0 else None),
        target_symbol=target,
        target_effective_exposure=target_exposure,
        current_symbol=None,
        current_quantity=0,
        action="CASH" if target is None else "BUY",
        reentry_symbol=None,
        candidates=candidates,
        selected_symbol=target,
        decision_reason=reason,
        no_trade_reason=None,
        target_exposure_fraction=target_fraction,
        exposure_tier=tier,
    )


def _proposal(
    snapshot: ResearchSnapshot,
    symbol: str,
    action: ProposalAction,
    quantity: int,
    history: MarketHistory,
    account: AccountSnapshot,
    *,
    reentry_symbol: str | None,
    target_exposure_fraction: Decimal | None = None,
) -> TradeProposal:
    instrument = INSTRUMENTS[symbol]
    bar = history.bar_on(symbol, datetime.fromisoformat(str(snapshot.spy_session_date)).date())
    evidence = (f"bar:SPY:{snapshot.spy_session_date}",)
    if bar is not None:
        evidence += (bar.evidence_id,)
    exposure = instrument.effective_exposure
    if action is ProposalAction.SELL:
        thesis = (
            f"Exit {symbol} because the completed {snapshot.spy_session_date} SPY signal is "
            f"{snapshot.market_state.lower()} and the target is "
            f"{reentry_symbol or 'CASH'}. {snapshot.decision_reason}"
        )
        invalidation = (
            "The exit must fill and reconcile before any opposite position is considered. "
            "The next run re-reads broker holdings and the SPY signal."
        )
    elif snapshot.exposure_tier is None:
        thesis = (
            f"SPY closed at {snapshot.spy_close} with a 10-session return of "
            f"{snapshot.spy_return_10d:.2%}, a 50-session SMA of {snapshot.spy_sma50:.2f} "
            f"and {snapshot.spy_volatility_20d:.2%} annualized volatility. "
            f"{snapshot.market_state} targets {symbol} at {instrument.leverage}x daily "
            f"leverage ({exposure:+} effective exposure), sized to 5% effective exposure."
        )
        invalidation = (
            "Exit at the next open after a neutral, opposite or volatility-ceiling signal. "
            "A leverage approval is required for UPRO or SPXU."
        )
    else:
        declared = snapshot.target_exposure_fraction
        thesis = (
            f"SPY closed at {snapshot.spy_close} with a 10-session return of "
            f"{snapshot.spy_return_10d:.2%}, a 50-session SMA of {snapshot.spy_sma50:.2f} "
            f"and {snapshot.spy_volatility_20d:.2%} annualized volatility. "
            f"The {snapshot.exposure_tier} tier sets a target of "
            f"{declared:+.0%} of equity in S&P 500 exposure; {symbol} at "
            f"{instrument.leverage}x daily leverage expresses it with about "
            f"{abs(declared or Decimal('0')) / instrument.leverage:.0%} of equity in cash."
        )
        invalidation = (
            "The tier is re-evaluated on every completed session: exit or reduce when the "
            "tier drops or the direction flips, and 3x holdings exit after the "
            "holding-duration limit. Overnight gaps can move the position beyond the 2% "
            "daily drawdown brake."
        )
    return TradeProposal(
        proposal_id=f"{STRATEGY_VERSION}-{snapshot.spy_session_date}-{symbol}-{action.value}",
        run_id=f"dryrun-{snapshot.decision_time_utc:%Y%m%dT%H%M%SZ}-{STRATEGY_VERSION}",
        strategy_version=STRATEGY_VERSION,
        decision_time_utc=snapshot.decision_time_utc,
        data_as_of_utc=snapshot.data_as_of_utc,
        symbol=symbol,
        action=action,
        requested_quantity=quantity,
        thesis=thesis,
        invalidation=invalidation,
        evidence_ids=evidence,
        target_exposure_fraction=target_exposure_fraction,
    )


def _target_quantity(
    account: AccountSnapshot,
    fraction: Decimal,
    leverage: Decimal,
    close: Decimal,
) -> int:
    return int(
        (account.equity * fraction / (close * leverage)).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )


def _no_trade(snapshot: ResearchSnapshot, failure: str) -> tuple[ResearchSnapshot, None]:
    return (
        replace(
            snapshot,
            action="NO_TRADE",
            decision_reason=failure,
            no_trade_reason=failure,
        ),
        None,
    )


def _sessions_since(
    history: MarketHistory,
    entry_session: str,
    current_session: str | None,
) -> int:
    if current_session is None:
        return 0
    return sum(
        1
        for session in history.session_dates()
        if entry_session < session <= current_session
    )


def decide(
    snapshot: ResearchSnapshot,
    history: MarketHistory,
    account: AccountSnapshot,
    *,
    exposure_policy: ExposurePolicy = EXPOSURE_POLICY_V2,
    holding_entry_session: str | None = None,
    leveraged_reentry_blocked_through: str | None = None,
) -> tuple[ResearchSnapshot, TradeProposal | None]:
    """Compare the target with broker holdings and produce one aggregate action."""
    if not account.reconciled or account.unknown_orders:
        failure = "Broker positions and open orders are not reconciled; no new decision"
        return (
            replace(
                snapshot,
                action="NO_TRADE",
                current_symbol=None,
                current_quantity=0,
                decision_reason=failure,
                no_trade_reason=failure,
            ),
            None,
        )

    held = [
        position
        for position in account.positions
        if position.quantity > 0 and position.symbol in CANDIDATE_SYMBOLS
    ]
    pending = [
        order for order in account.open_orders if order.symbol in CANDIDATE_SYMBOLS
    ]
    if len(held) > 1:
        failure = "More than one strategy ETF is held; close the conflict manually before trading"
        return (
            replace(snapshot, action="NO_TRADE", decision_reason=failure, no_trade_reason=failure),
            None,
        )
    if pending:
        failure = "A strategy order is still working; defer the next decision until it reconciles"
        return (
            replace(snapshot, action="HOLD", decision_reason=failure, no_trade_reason=None),
            None,
        )

    current = held[0] if held else None
    current_symbol = current.symbol if current else None
    current_quantity = current.quantity if current else 0
    target = snapshot.selected_symbol
    base = replace(
        snapshot,
        current_symbol=current_symbol,
        current_quantity=current_quantity,
        reentry_symbol=None,
    )

    # risk-v2: after a leveraged holding-duration exit, 3x instruments are
    # downgraded to the 1x equivalent for the following session.
    if exposure_policy.version != POLICY_VERSION_V1 and leveraged_reentry_blocked_through is not None:
        if (
            target is not None
            and INSTRUMENTS[target].leveraged
            and str(snapshot.spy_session_date) <= leveraged_reentry_blocked_through
        ):
            capped = (
                Decimal("1")
                if (snapshot.target_exposure_fraction or Decimal("0")) > 0
                else Decimal("-1")
            )
            downgraded = select_instrument_for_exposure(int(capped), capped)
            base = replace(
                base,
                target_symbol=downgraded,
                selected_symbol=downgraded,
                target_exposure_fraction=capped,
            )
            target = downgraded

    if current_symbol is not None:
        # risk-v2: 3x holdings exit once the holding-duration limit is reached.
        if (
            exposure_policy.version != POLICY_VERSION_V1
            and INSTRUMENTS[current_symbol].leveraged
            and holding_entry_session is not None
            and exposure_policy.max_leveraged_holding_sessions is not None
        ):
            elapsed = _sessions_since(
                history, holding_entry_session, str(snapshot.spy_session_date)
            )
            if elapsed >= exposure_policy.max_leveraged_holding_sessions:
                proposal = _proposal(
                    base,
                    current_symbol,
                    ProposalAction.SELL,
                    current_quantity,
                    history,
                    account,
                    reentry_symbol=None,
                )
                return (
                    replace(
                        base,
                        action="SELL",
                        duration_exit=True,
                        reentry_symbol=None,
                        decision_reason=(
                            f"{current_symbol} has been held for {elapsed} sessions; the "
                            "3x holding-duration limit forces a full exit."
                        ),
                    ),
                    proposal,
                )
        if target == current_symbol:
            if exposure_policy.version == POLICY_VERSION_V1:
                return (
                    replace(
                        base,
                        action="HOLD",
                        decision_reason=f"{target} already matches the target; hold and re-evaluate next session.",
                    ),
                    None,
                )
            # risk-v2: resize toward the current tier target when it moves
            # outside the tolerance band.
            if snapshot.target_exposure_fraction is None:
                return (
                    replace(
                        base,
                        action="HOLD",
                        decision_reason="No exposure target is recorded; hold and re-evaluate next session.",
                    ),
                    None,
                )
            bar = history.bar_on(
                target, datetime.fromisoformat(str(snapshot.spy_session_date)).date()
            )
            if bar is None or bar.close <= 0:
                return (
                    replace(
                        base,
                        action="HOLD",
                        decision_reason=f"No completed bar is available for {target}; hold.",
                    ),
                    None,
                )
            target_quantity = _target_quantity(
                account,
                abs(snapshot.target_exposure_fraction),
                INSTRUMENTS[target].leverage,
                bar.close,
            )
            difference = target_quantity - current_quantity
            relative = abs(Decimal(difference)) / Decimal(max(current_quantity, 1))
            if abs(difference) < 1 or relative < RESIZE_MIN_RELATIVE_CHANGE:
                return (
                    replace(
                        base,
                        action="HOLD",
                        decision_reason=(
                            f"{target} holding of {current_quantity} shares is within the "
                            f"resize band of the {target_quantity}-share target; hold."
                        ),
                    ),
                    None,
                )
            if difference < 0:
                proposal = _proposal(
                    base,
                    current_symbol,
                    ProposalAction.SELL,
                    -difference,
                    history,
                    account,
                    reentry_symbol=None,
                )
                return (
                    replace(
                        base,
                        action="SELL",
                        decision_reason=(
                            f"Tier target dropped; reduce {current_symbol} from "
                            f"{current_quantity} to {target_quantity} shares."
                        ),
                    ),
                    proposal,
                )
            proposal = _proposal(
                base,
                current_symbol,
                ProposalAction.BUY,
                difference,
                history,
                account,
                reentry_symbol=None,
            )
            return (
                replace(
                    base,
                    action="BUY",
                    decision_reason=(
                        f"Tier target rose; increase {current_symbol} from "
                        f"{current_quantity} to {target_quantity} shares."
                    ),
                ),
                proposal,
            )
        proposal = _proposal(
            base,
            current_symbol,
            ProposalAction.SELL,
            current_quantity,
            history,
            account,
            reentry_symbol=target,
        )
        return (
            replace(
                base,
                action="SELL",
                reentry_symbol=target,
                decision_reason=(
                    f"Target is {target or 'CASH'} but {current_symbol} is held. Exit first; "
                    "re-entry is considered only after the broker confirms the exit."
                ),
            ),
            proposal,
        )

    if target is None:
        return (
            replace(
                base,
                action="CASH",
                decision_reason="No directional target; remain in cash with no order.",
            ),
            None,
        )

    bar = history.bar_on(
        target, datetime.fromisoformat(str(snapshot.spy_session_date)).date()
    )
    if bar is None or bar.close <= 0:
        failure = f"No completed bar is available for {target}; cannot size an order"
        return _no_trade(base, failure)
    leverage = INSTRUMENTS[target].leverage
    if exposure_policy.version == POLICY_VERSION_V1:
        assert exposure_policy.fixed_fraction is not None
        quantity = _target_quantity(account, exposure_policy.fixed_fraction, leverage, bar.close)
        if quantity < 1:
            failure = (
                f"{exposure_policy.fixed_fraction:.0%} effective exposure does not "
                f"fund one {target} share"
            )
            return _no_trade(base, failure)
        declared = None
        sizing_note = f"{exposure_policy.fixed_fraction:.1%} effective exposure"
    else:
        fraction = snapshot.target_exposure_fraction
        if fraction is None or fraction == 0:
            return _no_trade(base, f"No exposure target is recorded for {target}")
        quantity = _target_quantity(account, abs(fraction), leverage, bar.close)
        if quantity < 1:
            failure = f"{abs(fraction):.0%} effective exposure does not fund one {target} share"
            return _no_trade(base, failure)
        declared = fraction
        sizing_note = (
            f"{snapshot.exposure_tier} tier target of {fraction:+.0%} effective exposure"
        )
    proposal = _proposal(
        base,
        target,
        ProposalAction.BUY,
        quantity,
        history,
        account,
        reentry_symbol=None,
        target_exposure_fraction=declared,
    )
    return (
        replace(
            base,
            action="BUY",
            decision_reason=(
                f"{snapshot.market_state} target {target}; buy {quantity} shares "
                f"({sizing_note})."
            ),
        ),
        proposal,
    )
