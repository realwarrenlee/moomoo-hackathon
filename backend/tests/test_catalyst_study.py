from datetime import date, datetime, timedelta
from decimal import Decimal

from app.research.data import DailyBar, MarketHistory
from scripts.catalyst_study import close_time, simulate_catalyst

D = Decimal


def make_history(symbols: tuple[str, ...] = ("AAPL",)) -> tuple[MarketHistory, list[date]]:
    dates = [date(2025, 1, 1) + timedelta(days=index) for index in range(45)]
    bars = {}
    for symbol in ("SPY", *symbols):
        rows = []
        for index, session_date in enumerate(dates):
            if symbol == "SPY":
                close = D("99") + D("0.01") * index
            else:
                close = D("100") if index < 20 else D("110")
            rows.append(DailyBar(
                symbol=symbol,
                session_date=session_date,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1000,
                available_at_utc=close_time(session_date),
            ))
        bars[symbol] = tuple(rows)
    return MarketHistory(bars, {"test": True}), dates


def event(symbol: str, accepted: datetime, accession: str = "0000000000-25-000001", form: str = "8-K") -> dict:
    return {
        "symbol": symbol,
        "form": form,
        "accession": accession,
        "accepted_at_utc": accepted.isoformat().replace("+00:00", "Z"),
    }


def test_entry_uses_next_open_and_ten_session_exit() -> None:
    history, dates = make_history()
    accepted = close_time(dates[20]) - timedelta(minutes=1)
    result = simulate_catalyst(history, [event("AAPL", accepted)], dates[21], dates[40])
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade["signal_date"] == dates[20].isoformat()
    assert trade["entry_date"] == dates[21].isoformat()
    assert trade["entry_raw_notional"] == 10000.0
    assert trade["entry_cost"] == 2.0
    assert trade["exit_date"] == dates[31].isoformat()
    assert trade["exit_reason"] == "maximum_hold"


def test_post_close_filing_waits_for_following_signal() -> None:
    history, dates = make_history()
    accepted = close_time(dates[20]) + timedelta(minutes=1)
    result = simulate_catalyst(history, [event("AAPL", accepted)], dates[21], dates[40])
    assert result.trades[0]["signal_date"] == dates[21].isoformat()
    assert result.trades[0]["entry_date"] == dates[22].isoformat()


def test_three_position_cap_and_deterministic_tie_break() -> None:
    symbols = ("NVDA", "MSFT", "AAPL", "AMZN")
    history, dates = make_history(symbols)
    events = [
        event(symbol, close_time(dates[20]) - timedelta(minutes=1), f"0000000000-25-00000{index}")
        for index, symbol in enumerate(symbols, start=1)
    ]
    result = simulate_catalyst(history, events, dates[21], dates[40])
    entered = {trade["symbol"] for trade in result.trades}
    assert len(result.trades) == 3
    assert entered == {"AAPL", "AMZN", "MSFT"}
    assert result.metrics["maximum_exposure_pct"] <= 31


def test_new_amendment_schedules_next_open_exit() -> None:
    history, dates = make_history()
    original = event("AAPL", close_time(dates[20]) - timedelta(minutes=1))
    amendment = event(
        "AAPL",
        close_time(dates[21]) - timedelta(minutes=1),
        "0000000000-25-000002",
        "8-K/A",
    )
    result = simulate_catalyst(history, [original, amendment], dates[21], dates[40])
    assert len(result.trades) == 1
    assert result.trades[0]["entry_date"] == dates[21].isoformat()
    assert result.trades[0]["exit_date"] == dates[22].isoformat()
    assert result.trades[0]["exit_reason"] == "amendment"
