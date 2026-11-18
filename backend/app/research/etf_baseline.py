from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.research.data import DailyBar, MarketHistory
from app.risk.policy import RiskGate

BASELINE_VERSION = "etf-trend-baseline-v1"
INITIAL_EQUITY = Decimal("100000")
COST_BPS = Decimal("2")
SMA_WINDOW = 200
POLICY_MAX_SINGLE_EXPOSURE = RiskGate(
    expected_account_fingerprint="baseline-study"
).max_single_exposure


@dataclass(frozen=True)
class BaselineTrade:
    symbol: str
    signal_date: date
    entry_date: date
    exit_date: date | None
    entry_price: Decimal
    exit_price: Decimal
    entry_notional: Decimal
    exit_notional: Decimal
    return_pct: float


@dataclass(frozen=True)
class BaselineResult:
    name: str
    start_date: date
    end_date: date
    initial_equity: Decimal
    final_equity: Decimal
    total_return: float
    cagr: float
    annualized_volatility: float
    sharpe: float | None
    max_drawdown: float
    average_exposure: float
    maximum_exposure: float
    monthly_checks: int
    turnover: float
    costs_usd: float
    trades: tuple[BaselineTrade, ...]
    open_position: str | None
    equity_curve: tuple[tuple[date, Decimal], ...]


def _is_month_end(dates: tuple[date, ...], index: int) -> bool:
    return index + 1 < len(dates) and dates[index + 1].month != dates[index].month


def _sma(closes: tuple[Decimal, ...], window: int) -> Decimal:
    return sum(closes[-window:], Decimal("0")) / Decimal(window)


def _result(
    name: str,
    curve: list[tuple[date, Decimal]],
    exposures: list[Decimal],
    monthly_checks: int,
    gross_notional: Decimal,
    costs: Decimal,
    trades: list[BaselineTrade],
    open_position: str | None,
) -> BaselineResult:
    values = [float(value) for _, value in curve]
    initial = float(INITIAL_EQUITY)
    daily = [values[0] / initial - 1] + [
        values[index] / values[index - 1] - 1 for index in range(1, len(values))
    ]
    peak = initial
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak)
    deviations = statistics.stdev(daily) if len(daily) > 1 else 0.0
    average_equity = sum(values) / len(values)
    return BaselineResult(
        name=name,
        start_date=curve[0][0],
        end_date=curve[-1][0],
        initial_equity=INITIAL_EQUITY,
        final_equity=curve[-1][1],
        total_return=values[-1] / initial - 1,
        cagr=(values[-1] / initial) ** (252 / max(len(daily), 1)) - 1,
        annualized_volatility=deviations * math.sqrt(252),
        sharpe=(
            statistics.mean(daily) / deviations * math.sqrt(252)
            if len(daily) > 1 and deviations > 0
            else None
        ),
        max_drawdown=drawdown,
        average_exposure=float(sum(exposures, Decimal("0")) / len(exposures)),
        maximum_exposure=float(max(exposures)),
        monthly_checks=monthly_checks,
        turnover=float(gross_notional / Decimal(str(average_equity))),
        costs_usd=float(costs),
        trades=tuple(trades),
        open_position=open_position,
        equity_curve=tuple(curve),
    )


def default_period(history: MarketHistory, sma_window: int = SMA_WINDOW) -> tuple[date, date]:
    dates = history.session_dates()
    first_signal = next(
        (
            index
            for index in range(sma_window - 1, len(dates) - 1)
            if _is_month_end(dates, index)
        ),
        None,
    )
    if first_signal is None:
        raise ValueError("history has no completed month-end after SMA warmup")
    return dates[first_signal + 1], dates[-1]


def simulate_monthly_trend(
    history: MarketHistory,
    start_date: date | None = None,
    end_date: date | None = None,
    symbol: str = "SPY",
    sma_window: int = SMA_WINDOW,
    allocation: Decimal = POLICY_MAX_SINGLE_EXPOSURE,
    cost_bps: Decimal = COST_BPS,
) -> BaselineResult:
    if sma_window < 2:
        raise ValueError("sma_window must be at least 2 sessions")
    if not Decimal("0") < allocation <= POLICY_MAX_SINGLE_EXPOSURE:
        raise ValueError("allocation must be positive and no greater than the policy cap")
    dates = history.session_dates()
    default_start, default_end = default_period(history, sma_window)
    start = start_date or default_start
    end = end_date or default_end
    if start not in dates or end not in dates or start > end:
        raise ValueError("start and end must be ordered sessions in the history")
    start_index = dates.index(start)
    end_index = dates.index(end)
    bars = {bar.session_date: bar for bar in history.bars(symbol)}
    closes = [bars[day].close for day in dates]
    cost = cost_bps / Decimal("10000")

    cash = INITIAL_EQUITY
    shares = Decimal("0")
    entry_price = Decimal("0")
    entry_notional = Decimal("0")
    entry_signal_date: date | None = None
    entry_date: date | None = None
    pending: tuple[str, date, Decimal | None] | None = None
    trades: list[BaselineTrade] = []
    curve: list[tuple[date, Decimal]] = []
    exposures: list[Decimal] = []
    gross_notional = Decimal("0")
    costs = Decimal("0")
    monthly_checks = 0

    signal_index = start_index - 1
    while signal_index >= 0 and not _is_month_end(dates, signal_index):
        signal_index -= 1
    if signal_index >= sma_window - 1 and closes[signal_index] > _sma(
        tuple(closes[: signal_index + 1]), sma_window
    ):
        pending = ("BUY", dates[signal_index], INITIAL_EQUITY * allocation)

    for index in range(start_index, end_index + 1):
        session = dates[index]
        bar = bars[session]
        if pending is not None:
            action, signal_date, target = pending
            if action == "BUY" and shares == 0 and target is not None:
                entry_price = bar.open * (Decimal("1") + cost)
                shares = target / entry_price
                entry_notional = shares * bar.open
                cash -= shares * entry_price
                costs += entry_notional * cost
                gross_notional += entry_notional
                entry_signal_date = signal_date
                entry_date = session
            elif action == "SELL" and shares > 0:
                assert entry_signal_date is not None and entry_date is not None
                exit_price = bar.open * (Decimal("1") - cost)
                costs += shares * bar.open * cost
                gross_notional += shares * bar.open
                cash += shares * exit_price
                trades.append(
                    BaselineTrade(
                        symbol=symbol,
                        signal_date=entry_signal_date,
                        entry_date=entry_date,
                        exit_date=session,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        entry_notional=entry_notional,
                        exit_notional=shares * bar.open,
                        return_pct=float(exit_price / entry_price - 1),
                    )
                )
                shares = Decimal("0")
                entry_price = Decimal("0")
                entry_notional = Decimal("0")
                entry_signal_date = None
                entry_date = None
            pending = None

        market_value = shares * bar.close
        equity = cash + market_value
        curve.append((session, equity))
        exposures.append(market_value / equity)

        if _is_month_end(dates, index):
            monthly_checks += 1
            target_asset = closes[index] > _sma(tuple(closes[: index + 1]), sma_window)
            if target_asset and shares == 0:
                pending = ("BUY", session, equity * allocation)
            elif not target_asset and shares > 0:
                pending = ("SELL", session, None)

    if shares > 0 and entry_signal_date is not None and entry_date is not None:
        last_close = bars[dates[end_index]].close
        trades.append(
            BaselineTrade(
                symbol=symbol,
                signal_date=entry_signal_date,
                entry_date=entry_date,
                exit_date=None,
                entry_price=entry_price,
                exit_price=last_close,
                entry_notional=entry_notional,
                exit_notional=shares * last_close,
                return_pct=float(last_close / entry_price - 1),
            )
        )
    return _result(
        f"{BASELINE_VERSION}-{symbol}",
        curve,
        exposures,
        monthly_checks,
        gross_notional,
        costs,
        trades,
        symbol if shares > 0 else None,
    )


def buy_and_hold_fraction(
    history: MarketHistory,
    start_date: date,
    end_date: date,
    symbol: str = "SPY",
    allocation: Decimal = Decimal("1"),
    cost_bps: Decimal = COST_BPS,
) -> BaselineResult:
    if not Decimal("0") < allocation <= Decimal("1"):
        raise ValueError("allocation must be in (0, 1]")
    dates = history.session_dates()
    if start_date not in dates or end_date not in dates or start_date > end_date:
        raise ValueError("start and end must be ordered sessions in the history")
    start_index = dates.index(start_date)
    end_index = dates.index(end_date)
    bars = {bar.session_date: bar for bar in history.bars(symbol)}
    cost = cost_bps / Decimal("10000")
    entry_bar: DailyBar = bars[start_date]
    entry_price = entry_bar.open * (Decimal("1") + cost)
    shares = INITIAL_EQUITY * allocation / entry_price
    cash = INITIAL_EQUITY - shares * entry_price
    gross_notional = shares * entry_bar.open
    costs = shares * entry_bar.open * cost
    curve: list[tuple[date, Decimal]] = []
    exposures: list[Decimal] = []
    for day in dates[start_index : end_index + 1]:
        market_value = shares * bars[day].close
        equity = cash + market_value
        curve.append((day, equity))
        exposures.append(market_value / equity)
    last_close = bars[end_date].close
    trade = BaselineTrade(
        symbol=symbol,
        signal_date=start_date,
        entry_date=start_date,
        exit_date=None,
        entry_price=entry_price,
        exit_price=last_close,
        entry_notional=shares * entry_bar.open,
        exit_notional=shares * last_close,
        return_pct=float(last_close / entry_price - 1),
    )
    return _result(
        f"{symbol}-buy-hold-{allocation}",
        curve,
        exposures,
        0,
        gross_notional,
        costs,
        [trade],
        symbol,
    )


def cash_baseline(start_date: date, end_date: date, history: MarketHistory) -> BaselineResult:
    dates = history.session_dates()
    if start_date not in dates or end_date not in dates or start_date > end_date:
        raise ValueError("start and end must be ordered sessions in the history")
    curve = [
        (day, INITIAL_EQUITY)
        for day in dates[dates.index(start_date) : dates.index(end_date) + 1]
    ]
    return _result(
        "cash",
        curve,
        [Decimal("0")] * len(curve),
        0,
        Decimal("0"),
        Decimal("0"),
        [],
        None,
    )
