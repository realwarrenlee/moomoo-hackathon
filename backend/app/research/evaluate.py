from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal

from app.models.contracts import AccountSnapshot, Position, ProposalAction, TradeProposal
from app.research.data import MarketHistory, session_close_utc
from app.research.instruments import INSTRUMENTS
from app.research.strategy import EXPOSURE_POLICY_V3, MIN_COMPLETED_SESSIONS, decide, screen

INITIAL_EQUITY = Decimal("100000")
COST_BPS = Decimal("2")


@dataclass(frozen=True)
class Trade:
    symbol: str
    signal_date: date
    entry_date: date
    exit_date: date | None
    entry_price: Decimal
    exit_price: Decimal | None
    return_pct: float | None


@dataclass(frozen=True)
class BacktestResult:
    name: str
    start_date: date
    end_date: date
    equity_curve: tuple[tuple[date, Decimal], ...]
    total_return: float
    cagr: float
    annualized_volatility: float
    sharpe: float | None
    max_drawdown: float
    exposure_pct: float
    signals: int
    trades: tuple[Trade, ...]
    win_rate: float | None
    average_trade_return: float | None
    open_position: str | None
    average_exposure: float = 0.0
    maximum_exposure: float = 0.0


def _metrics(
    name: str,
    curve: tuple[tuple[date, Decimal], ...],
    exposure_days: int,
    signals: int,
    trades: list[Trade],
    open_position: str | None,
    exposures: list[Decimal] | None = None,
) -> BacktestResult:
    initial = float(INITIAL_EQUITY)
    equities = [float(value) for _, value in curve]
    daily = [equities[i] / equities[i - 1] - 1 for i in range(1, len(equities))]
    total_return = equities[-1] / initial - 1
    cagr = (equities[-1] / initial) ** (252 / max(len(equities), 1)) - 1
    volatility = statistics.stdev(daily) * math.sqrt(252) if len(daily) > 1 else 0.0
    sharpe = (
        statistics.mean(daily) / statistics.stdev(daily) * math.sqrt(252)
        if len(daily) > 1 and statistics.stdev(daily) > 0
        else None
    )
    peak = initial
    max_drawdown = 0.0
    for value in equities:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, (peak - value) / peak)
    closed = [trade for trade in trades if trade.exit_date is not None and trade.return_pct is not None]
    return BacktestResult(
        name=name,
        start_date=curve[0][0],
        end_date=curve[-1][0],
        equity_curve=curve,
        total_return=total_return,
        cagr=cagr,
        annualized_volatility=volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        exposure_pct=exposure_days / (len(curve) - 1) if len(curve) > 1 else 0.0,
        signals=signals,
        trades=tuple(trades),
        win_rate=sum(1 for trade in closed if trade.return_pct > 0) / len(closed) if closed else None,
        average_trade_return=(
            sum(trade.return_pct for trade in closed if trade.return_pct is not None) / len(closed)
            if closed
            else None
        ),
        open_position=open_position,
        average_exposure=(
            float(sum(exposures, Decimal("0")) / len(exposures)) if exposures else 0.0
        ),
        maximum_exposure=float(max(exposures)) if exposures else 0.0,
    )


def simulate_strategy(
    history: MarketHistory,
    strategy_version: str,
    start_index: int = MIN_COMPLETED_SESSIONS,
    cost_bps: Decimal = COST_BPS,
) -> BacktestResult:
    """Historical-only v2 replay, not a RiskGate or broker execution simulation.

    The deterministic decision sizes whole shares at the completed close. Fills
    occur at the next open, with per-side costs and a cash-only affordability cap.
    A reversal cannot enter until a later close observes the simulated exit.
    Resizes remain one holding episode; trade prices are quantity-weighted over
    its buys and sells (including the final mark for an open episode).
    """
    dates = history.session_dates()
    if start_index < MIN_COMPLETED_SESSIONS:
        raise ValueError(f"start_index must provide {MIN_COMPLETED_SESSIONS} completed sessions")
    if start_index >= len(dates):
        raise ValueError("start_index must leave at least one execution session")
    if not cost_bps.is_finite() or not Decimal("0") <= cost_bps < Decimal("10000"):
        raise ValueError("cost_bps must be finite and in [0, 10000)")
    cost = cost_bps / Decimal("10000")
    cash = INITIAL_EQUITY
    shares = 0
    position_symbol: str | None = None
    bought_shares = 0
    entry_cost = Decimal("0")
    exit_proceeds = Decimal("0")
    entry_signal_date: date | None = None
    entry_date: date | None = None
    pending: TradeProposal | None = None
    pending_duration_exit = False
    leveraged_reentry_blocked_through: str | None = None
    trades: list[Trade] = []
    curve: list[tuple[date, Decimal]] = []
    exposures: list[Decimal] = []
    exposure_days = 0
    signals = 0

    for index in range(start_index - 1, len(dates)):
        session = dates[index]
        now = session_close_utc(session)
        bar_by_symbol = {symbol: history.bar_on(symbol, session) for symbol in INSTRUMENTS}

        if pending is not None:
            fill_bar = bar_by_symbol[pending.symbol]
            if fill_bar is not None:
                if pending.action is ProposalAction.BUY:
                    fill_price = fill_bar.open * (1 + cost)
                    affordable = int((cash / fill_price).to_integral_value(rounding=ROUND_FLOOR))
                    quantity = min(pending.requested_quantity, affordable)
                    if quantity > 0:
                        if position_symbol is None:
                            position_symbol = pending.symbol
                            entry_signal_date = pending.decision_time_utc.date()
                            entry_date = session
                            bought_shares = 0
                            entry_cost = Decimal("0")
                            exit_proceeds = Decimal("0")
                            signals += 1
                        shares += quantity
                        bought_shares += quantity
                        entry_cost += quantity * fill_price
                        cash -= quantity * fill_price
                else:
                    quantity = min(pending.requested_quantity, shares)
                    proceeds = quantity * fill_bar.open * (1 - cost)
                    cash += proceeds
                    exit_proceeds += proceeds
                    shares -= quantity
                    if shares == 0:
                        assert position_symbol is not None
                        assert entry_signal_date is not None and entry_date is not None
                        trades.append(
                            Trade(
                                symbol=position_symbol,
                                signal_date=entry_signal_date,
                                entry_date=entry_date,
                                exit_date=session,
                                entry_price=entry_cost / bought_shares,
                                exit_price=exit_proceeds / bought_shares,
                                return_pct=float(exit_proceeds / entry_cost - 1),
                            )
                        )
                        if pending_duration_exit:
                            # Cap the first post-exit close's entry proposal at 1x.
                            leveraged_reentry_blocked_through = session.isoformat()
                        position_symbol = None
                        entry_signal_date = None
                        entry_date = None
            pending = None
            pending_duration_exit = False

        market_value = Decimal("0")
        positions = ()
        if position_symbol is not None:
            held_bar = bar_by_symbol[position_symbol]
            if held_bar is None or held_bar.available_at_utc > now:
                raise ValueError(f"unavailable {position_symbol} valuation bar on {session}")
            market_value = shares * held_bar.close
            positions = (Position(symbol=position_symbol, quantity=shares, market_value=market_value),)
            exposure_days += 1
        equity = cash + market_value
        leverage = INSTRUMENTS[position_symbol].leverage if position_symbol else Decimal("1")
        exposures.append(market_value * leverage / equity if equity else Decimal("0"))
        curve.append((session, equity))

        if index < len(dates) - 1:
            # Truncate every symbol, not just SPY, to keep unavailable ETF bars
            # out of both selection and sizing.
            known_history = MarketHistory(
                {symbol: history.bars_as_of(symbol, now) for symbol in history.symbols},
                history.source,
            )
            account = AccountSnapshot(
                snapshot_id=f"historical-replay-{session}",
                account_fingerprint="historical-replay-only",
                environment="paper",
                equity=equity,
                day_start_equity=equity,
                peak_equity=equity,
                cash=cash,
                buying_power=cash,
                positions=positions,
                as_of_utc=now,
                reconciled=True,
            )
            snapshot, pending = decide(
                screen(known_history, now, strategy_version, exposure_policy=EXPOSURE_POLICY_V3),
                known_history,
                account,
                exposure_policy=EXPOSURE_POLICY_V3,
                holding_entry_session=entry_date.isoformat() if entry_date else None,
                leveraged_reentry_blocked_through=leveraged_reentry_blocked_through,
            )
            pending_duration_exit = snapshot.duration_exit

    if position_symbol is not None and entry_signal_date is not None and entry_date is not None:
        marked_proceeds = exit_proceeds + market_value
        trades.append(
            Trade(
                symbol=position_symbol,
                signal_date=entry_signal_date,
                entry_date=entry_date,
                exit_date=None,
                entry_price=entry_cost / bought_shares,
                exit_price=marked_proceeds / bought_shares,
                return_pct=float(marked_proceeds / entry_cost - 1),
            )
        )
    return _metrics(
        strategy_version,
        tuple(curve),
        exposure_days,
        signals,
        trades,
        position_symbol,
        exposures,
    )


def buy_and_hold(
    history: MarketHistory,
    symbol: str,
    start_index: int = MIN_COMPLETED_SESSIONS,
    cost_bps: Decimal = COST_BPS,
) -> BacktestResult:
    dates = history.session_dates()
    if start_index < 1:
        raise ValueError("start_index must provide a prior session for the opening trade")
    cost = cost_bps / Decimal("10000")
    entry = history.bar_on(symbol, dates[start_index + 1])
    if entry is None:
        raise ValueError(f"no entry bar for {symbol}")
    shares = INITIAL_EQUITY / (entry.open * (1 + cost))
    curve: list[tuple[date, Decimal]] = [(dates[start_index], INITIAL_EQUITY)]
    exposures: list[Decimal] = [Decimal("0")]
    for session in dates[start_index + 1 :]:
        bar = history.bar_on(symbol, session)
        if bar is None:
            continue
        curve.append((session, shares * bar.close))
        exposures.append(Decimal("1"))
    return _metrics(
        f"{symbol}-buy-hold",
        tuple(curve),
        len(curve) - 1,
        1,
        [],
        symbol,
        exposures,
    )


def cash_baseline(history: MarketHistory, start_index: int = MIN_COMPLETED_SESSIONS) -> BacktestResult:
    dates = history.session_dates()
    curve = tuple((session, INITIAL_EQUITY) for session in dates[start_index:])
    return _metrics("cash", curve, 0, 0, [], None, [Decimal("0")] * len(curve))
