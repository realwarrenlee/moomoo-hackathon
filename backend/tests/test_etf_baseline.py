from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.research.data import DailyBar, MarketHistory, session_close_utc
from app.research.etf_baseline import (
    COST_BPS,
    INITIAL_EQUITY,
    POLICY_MAX_SINGLE_EXPOSURE,
    buy_and_hold_fraction,
    cash_baseline,
    default_period,
    simulate_monthly_trend,
)

FIXTURES = Path(__file__).parent / "fixtures"
BARS = FIXTURES / "moomoo_daily_bars_2026-11-16.json"


@pytest.fixture(scope="module")
def history():
    return MarketHistory.from_file(BARS)


def test_historical_baseline_retains_its_frozen_study_allocation():
    assert POLICY_MAX_SINGLE_EXPOSURE == Decimal("0.10")


def test_default_period_starts_after_month_end_and_sma_warmup(history):
    start, end = default_period(history)
    assert start == date(2026, 4, 1)
    assert end == date(2026, 11, 16)


def test_monthly_trend_is_low_turnover_and_executes_after_signal(history):
    result = simulate_monthly_trend(history)
    assert result.start_date == date(2026, 4, 1)
    assert result.end_date == date(2026, 11, 16)
    assert result.monthly_checks == 7
    assert len(result.trades) == 1
    assert result.turnover < 0.15
    trade = result.trades[0]
    assert trade.signal_date == date(2026, 4, 30)
    assert trade.entry_date == date(2026, 5, 1)
    assert trade.entry_date > trade.signal_date
    assert trade.exit_date is None
    assert result.open_position == "SPY"


def test_entry_notional_does_not_exceed_policy_cap_at_signal(history):
    result = simulate_monthly_trend(history)
    for trade in result.trades:
        assert trade.entry_notional <= INITIAL_EQUITY * POLICY_MAX_SINGLE_EXPOSURE


def test_entry_uses_next_session_open_with_cost(history):
    result = simulate_monthly_trend(history)
    trade = result.trades[0]
    entry_bar = history.bar_on("SPY", trade.entry_date)
    assert entry_bar is not None
    expected_price = entry_bar.open * (Decimal("1") + COST_BPS / Decimal("10000"))
    assert trade.entry_price == expected_price


def test_strategy_rejects_allocation_above_policy_cap(history):
    with pytest.raises(ValueError, match="policy cap"):
        simulate_monthly_trend(history, allocation=Decimal("0.1001"))


def test_monthly_trend_exits_after_filter_turns_negative():
    sessions: list[date] = []
    current = date(2025, 1, 1)
    while current <= date(2025, 12, 31):
        if current.weekday() < 5:
            sessions.append(current)
        current += timedelta(days=1)
    def price(session: date) -> Decimal:
        if session <= date(2025, 9, 30):
            return Decimal("100")
        return Decimal("120") if session <= date(2025, 10, 31) else Decimal("50")

    bars = tuple(
        DailyBar(
            symbol="SPY",
            session_date=session,
            open=price(session),
            high=price(session),
            low=price(session),
            close=price(session),
            volume=1_000_000,
            available_at_utc=session_close_utc(session),
        )
        for session in sessions
    )
    history = MarketHistory({"SPY": bars}, {"test": "synthetic trend reversal"})
    result = simulate_monthly_trend(history)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.signal_date == date(2025, 10, 31)
    assert trade.entry_date == date(2025, 11, 3)
    assert trade.exit_date == date(2025, 12, 1)
    assert trade.exit_date > trade.entry_date
    assert result.open_position is None


def test_matched_benchmarks_use_same_dates(history):
    baseline = simulate_monthly_trend(history)
    spy_ten_percent = buy_and_hold_fraction(
        history,
        baseline.start_date,
        baseline.end_date,
        allocation=Decimal("0.10"),
    )
    spy_full = buy_and_hold_fraction(history, baseline.start_date, baseline.end_date)
    cash = cash_baseline(baseline.start_date, baseline.end_date, history)
    assert spy_ten_percent.start_date == spy_full.start_date == cash.start_date == baseline.start_date
    assert spy_ten_percent.end_date == spy_full.end_date == cash.end_date == baseline.end_date
    assert spy_ten_percent.average_exposure > 0.10
    assert spy_full.average_exposure == 1.0
    assert cash.total_return == 0.0
    assert cash.costs_usd == 0.0
