"""Deterministic daily SPY directional policy.

The signal is evaluated only on completed SPY daily bars. A decision made after
the close is eligible for the next open. Leveraged products require a strong,
controlled-volatility signal plus separate leverage approval.
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
)

STRATEGY_VERSION = "spy-directional"
RETURN_LOOKBACK = 10
TREND_WINDOW = 50
VOLATILITY_WINDOW = 20
MIN_COMPLETED_SESSIONS = TREND_WINDOW + 1
DIRECTION_THRESHOLD = Decimal("0.015")
STRONG_RETURN_THRESHOLD = Decimal("0.03")
MAX_VOLATILITY_FOR_DIRECTION = Decimal("0.40")
MAX_VOLATILITY_FOR_LEVERAGE = Decimal("0.30")
POSITION_FRACTION = Decimal("0.05")

BULLISH_STATES = frozenset({"BULLISH", "STRONG_BULLISH"})
BEARISH_STATES = frozenset({"BEARISH", "STRONG_BEARISH"})


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


def _candidate(
    symbol: str,
    direction: int,
    leverage: Decimal,
    close: Decimal | None,
    allow_leveraged: bool,
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
        reasons.append("Daily 3x execution requires separate leverage approval")
    eligible = close is not None and instrument.direction == direction and (
        not instrument.leveraged or allow_leveraged
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
    allow_leveraged: bool = False,
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
    elif return_10d >= DIRECTION_THRESHOLD and close > sma50:
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

    strong = market_state.startswith("STRONG_")
    target = select_instrument(direction, strong, allow_leveraged)
    candidates = tuple(
        replace(
            _candidate(
                symbol,
                direction,
                INSTRUMENTS[symbol].leverage,
                history.bar_on(symbol, spy_bars[-1].session_date).close
                if history.bar_on(symbol, spy_bars[-1].session_date) is not None
                else None,
                allow_leveraged,
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
    else:
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
    )


def decide(
    snapshot: ResearchSnapshot,
    history: MarketHistory,
    account: AccountSnapshot,
    *,
    position_fraction: Decimal = POSITION_FRACTION,
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

    if current_symbol is not None:
        if target == current_symbol:
            return (
                replace(
                    base,
                    action="HOLD",
                    decision_reason=f"{target} already matches the target; hold and re-evaluate next session.",
                ),
                None,
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
        return (
            replace(base, action="NO_TRADE", decision_reason=failure, no_trade_reason=failure),
            None,
        )
    leverage = INSTRUMENTS[target].leverage
    quantity = int(
        (account.equity * position_fraction / (bar.close * leverage)).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    if quantity < 1:
        failure = f"5% effective exposure does not fund one {target} share"
        return (
            replace(base, action="NO_TRADE", decision_reason=failure, no_trade_reason=failure),
            None,
        )
    proposal = _proposal(
        base,
        target,
        ProposalAction.BUY,
        quantity,
        history,
        account,
        reentry_symbol=None,
    )
    return (
        replace(
            base,
            action="BUY",
            decision_reason=(
                f"{snapshot.market_state} target {target}; buy {quantity} shares for "
                f"{position_fraction:.1%} effective exposure."
            ),
        ),
        proposal,
    )
