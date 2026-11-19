from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_FLOOR, Decimal

from app.research.data import MarketHistory, session_close_utc
from app.research.instruments import INSTRUMENTS
from app.research.strategy import (
    EXPOSURE_POLICY_V1,
    EXPOSURE_POLICY_V2,
    MIN_COMPLETED_SESSIONS,
    screen,
)

INITIAL_EQUITY = Decimal("100000")
COST_BPS = Decimal("2")
CASH_TARGET = "CASH"


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
    allocation: Decimal = Decimal("0.05"),
    whole_shares: bool = True,
    allow_leveraged: bool = False,
) -> BacktestResult:
    dates = history.session_dates()
    if start_index < MIN_COMPLETED_SESSIONS:
        raise ValueError(f"start_index must provide {MIN_COMPLETED_SESSIONS} completed sessions")
    if not Decimal("0") < allocation <= Decimal("1"):
        raise ValueError("allocation must be in (0, 1]")
    cost = cost_bps / Decimal("10000")
    cash = INITIAL_EQUITY
    shares = Decimal("0")
    position_symbol: str | None = None
    position_leverage = Decimal("1")
    entry_price = Decimal("0")
    entry_signal_date: date | None = None
    entry_date: date | None = None
    pending_target: str | None = None
    pending_signal_date: date | None = None
    trades: list[Trade] = []
    curve: list[tuple[date, Decimal]] = [(dates[start_index - 1], INITIAL_EQUITY)]
    exposures: list[Decimal] = [Decimal("0")]
    exposure_days = 0
    signals = 0
    exposure_policy = EXPOSURE_POLICY_V2 if allow_leveraged else EXPOSURE_POLICY_V1

    initial_signal = screen(
        history,
        session_close_utc(dates[start_index - 1]),
        strategy_version,
        exposure_policy=exposure_policy,
    )
    pending_target = initial_signal.selected_symbol or CASH_TARGET
    pending_signal_date = dates[start_index - 1]

    for index in range(start_index, len(dates)):
        session = dates[index]
        bar_by_symbol = {symbol: history.bar_on(symbol, session) for symbol in INSTRUMENTS}

        if pending_target is not None:
            if position_symbol is not None:
                if pending_target != position_symbol:
                    exit_bar = bar_by_symbol.get(position_symbol)
                    if exit_bar is not None:
                        exit_price = exit_bar.open * (1 - cost)
                        cash += shares * exit_price
                        assert entry_signal_date is not None and entry_date is not None
                        trades.append(
                            Trade(
                                symbol=position_symbol,
                                signal_date=entry_signal_date,
                                entry_date=entry_date,
                                exit_date=session,
                                entry_price=entry_price,
                                exit_price=exit_price,
                                return_pct=float(exit_price / entry_price - 1),
                            )
                        )
                        shares = Decimal("0")
                        position_symbol = None
                        entry_price = Decimal("0")
                        entry_signal_date = None
                        entry_date = None
            elif pending_target != CASH_TARGET:
                entry_bar = bar_by_symbol.get(pending_target)
                if entry_bar is not None:
                    entry_price = entry_bar.open * (1 + cost)
                    leverage = INSTRUMENTS[pending_target].leverage
                    raw_quantity = cash * allocation / (entry_price * leverage)
                    quantity = (
                        raw_quantity.to_integral_value(rounding=ROUND_FLOOR)
                        if whole_shares
                        else raw_quantity
                    )
                    if quantity > 0:
                        shares = quantity
                        cash -= shares * entry_price
                        position_symbol = pending_target
                        position_leverage = leverage
                        entry_signal_date = pending_signal_date
                        entry_date = session
                        signals += 1
            pending_target = None
            pending_signal_date = None

        close_prices = {
            symbol: bar.close for symbol, bar in bar_by_symbol.items() if bar is not None
        }
        market_value = (
            shares * close_prices[position_symbol]
            if position_symbol is not None and position_symbol in close_prices
            else Decimal("0")
        )
        if position_symbol is not None:
            exposure_days += 1
        equity = cash + market_value
        exposures.append(
            market_value * position_leverage / equity if equity else Decimal("0")
        )
        curve.append((session, equity))

        if index < len(dates) - 1:
            snapshot = screen(
                history,
                session_close_utc(session),
                strategy_version,
                exposure_policy=exposure_policy,
            )
            target = snapshot.selected_symbol or CASH_TARGET
            if position_symbol is None and target != CASH_TARGET:
                pending_target = target
                pending_signal_date = session
            elif position_symbol is not None and target != position_symbol:
                pending_target = target
                pending_signal_date = session

    open_position = position_symbol
    if position_symbol is not None and entry_signal_date is not None and entry_date is not None:
        last_close = history.bar_on(position_symbol, dates[-1])
        assert last_close is not None
        trades.append(
            Trade(
                symbol=position_symbol,
                signal_date=entry_signal_date,
                entry_date=entry_date,
                exit_date=None,
                entry_price=entry_price,
                exit_price=last_close.close,
                return_pct=float(last_close.close / entry_price - 1),
            )
        )
    return _metrics(
        strategy_version,
        tuple(curve),
        exposure_days,
        signals,
        trades,
        open_position,
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
