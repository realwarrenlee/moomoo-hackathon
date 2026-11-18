from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.contracts import PolicyDecision
from app.research.data import MarketHistory, NewsArchive, NewsItem, session_close_utc
from app.research.dryrun import (
    control_rejection_example,
    find_accepted_example,
    latest_decision,
    oversized_example,
    stale_quote_example,
)
from app.research.evaluate import INITIAL_EQUITY, buy_and_hold, cash_baseline, simulate_strategy
from app.research.strategy import _news_polarity, screen

FIXTURES = Path(__file__).parent / "fixtures"
BARS = FIXTURES / "moomoo_daily_bars_2026-11-16.json"
NEWS = FIXTURES / "moomoo_news_2026-11-17.json"
FINGERPRINT = "test-competition-paper-fingerprint"


@pytest.fixture(scope="module")
def history():
    return MarketHistory.from_file(BARS)


@pytest.fixture(scope="module")
def news():
    return NewsArchive.from_file(NEWS)


def test_bar_fixture_has_expected_completed_session(history):
    assert tuple(sorted(history.symbols)) == ("IWM", "QQQ", "SPY")
    assert len(history.bars("SPY")) == 370
    assert history.last_completed_session().isoformat() == "2026-11-16"
    last = history.bars("SPY")[-1]
    assert last.close == Decimal("739.95")
    assert last.available_at_utc == datetime(2026, 11, 16, 21, 0, tzinfo=UTC)


def test_bar_availability_excludes_future_session(history):
    before_close = datetime(2026, 11, 16, 20, 59, tzinfo=UTC)
    after_close = datetime(2026, 11, 16, 21, 0, tzinfo=UTC)
    assert history.bars_as_of("SPY", before_close)[-1].session_date.isoformat() == "2026-11-13"
    assert history.bars_as_of("SPY", after_close)[-1].session_date.isoformat() == "2026-11-16"


def test_latest_screen_abstains_on_negative_regime(history, news):
    decision_time = session_close_utc(history.last_completed_session())
    snapshot = screen(history, news, decision_time, "momentum-v1")
    assert snapshot.regime_ok is False
    assert snapshot.selected_symbol is None
    assert snapshot.no_trade_reason is not None
    assert all(not candidate.eligible for candidate in snapshot.candidates)


def test_insufficient_history_abstains(history, news):
    decision_time = session_close_utc(history.session_dates()[0])
    snapshot = screen(history, news, decision_time, "momentum-v1")
    assert snapshot.candidates == ()
    assert snapshot.selected_symbol is None
    assert "Insufficient history" in snapshot.no_trade_reason


def test_accepted_example_passes_existing_risk_gate(history, news):
    decision = find_accepted_example(history, news, "momentum-v1", FINGERPRINT)
    assert decision is not None
    assert decision.proposal is not None
    assert decision.risk_decision is not None
    assert decision.risk_decision.decision is PolicyDecision.APPROVE
    assert decision.risk_decision.approved_quantity == decision.proposal.requested_quantity
    assert decision.proposal.requested_quantity > 0
    assert decision.risk_decision.reasons == ()


def test_stale_quote_is_rejected(history, news):
    accepted = find_accepted_example(history, news, "momentum-v1", FINGERPRINT)
    assert accepted is not None
    stale = stale_quote_example(accepted, FINGERPRINT)
    assert stale is not None
    assert stale.risk_decision is not None
    assert stale.risk_decision.decision is PolicyDecision.REJECT
    assert {rule.rule_id for rule in stale.risk_decision.reasons} == {"R007"}


def test_oversized_quantity_is_rejected(history, news):
    accepted = find_accepted_example(history, news, "momentum-v1", FINGERPRINT)
    assert accepted is not None
    oversized = oversized_example(accepted, FINGERPRINT)
    assert oversized is not None
    assert oversized.risk_decision is not None
    assert oversized.risk_decision.decision is PolicyDecision.REJECT
    assert {rule.rule_id for rule in oversized.risk_decision.reasons} == {"R004"}
    assert oversized.proposal is not None
    assert oversized.proposal.requested_quantity > accepted.proposal.requested_quantity


def test_control_rejections_fail_closed(history, news):
    accepted = find_accepted_example(history, news, "momentum-v1", FINGERPRINT)
    assert accepted is not None
    writes_disabled = control_rejection_example(
        accepted,
        FINGERPRINT,
        "writes disabled",
        order_writes_enabled=False,
        first_order_approved=True,
    )
    approval_missing = control_rejection_example(
        accepted,
        FINGERPRINT,
        "approval missing",
        order_writes_enabled=True,
        first_order_approved=False,
    )
    assert writes_disabled is not None and writes_disabled.risk_decision is not None
    assert approval_missing is not None and approval_missing.risk_decision is not None
    assert {rule.rule_id for rule in writes_disabled.risk_decision.reasons} == {"R010"}
    assert {rule.rule_id for rule in approval_missing.risk_decision.reasons} == {"R014"}


def test_news_catalyst_requires_positive_headline(history, news):
    decision_time = session_close_utc(history.last_completed_session())
    momentum = screen(history, news, decision_time, "momentum-v1")
    news_screen = screen(history, news, decision_time, "news-catalyst-v1")
    assert momentum.selected_symbol is None
    assert news_screen.selected_symbol is None
    assert all(not candidate.eligible for candidate in news_screen.candidates)


def test_hypothetical_news_proposal_passes_gate(history, news):
    decision = find_accepted_example(history, news, "news-catalyst-v1", FINGERPRINT)
    assert decision is not None
    assert decision.proposal is not None
    assert decision.risk_decision is not None
    assert decision.risk_decision.decision is PolicyDecision.APPROVE
    assert decision.proposal.strategy_version == "news-catalyst-v1"


def test_news_polarity_is_deterministic():
    published = datetime(2026, 11, 16, 20, 0, tzinfo=UTC)
    positive = NewsItem(
        symbol="QQQ",
        news_id="p1",
        published_at_utc=published,
        title="QQQ rallies to a record high on strong inflows",
        abstract="Investors upgrade the ETF.",
        source="test",
        url="",
    )
    negative = NewsItem(
        symbol="QQQ",
        news_id="n1",
        published_at_utc=published,
        title="QQQ falls as selloff pressure mounts",
        abstract="Investors downgrade the ETF.",
        source="test",
        url="",
    )
    assert _news_polarity(positive) == 1
    assert _news_polarity(negative) == -1


def test_backtest_enters_after_signal(history, news):
    result = simulate_strategy(history, news, "momentum-v1")
    assert result.trades
    for trade in result.trades:
        assert trade.entry_date > trade.signal_date
        if trade.exit_date is not None:
            assert trade.exit_date > trade.entry_date
    first = result.trades[0]
    assert first.signal_date.isoformat() == "2025-06-27"
    assert first.entry_date.isoformat() == "2025-06-30"


def test_news_backtest_enters_after_signal(history, news):
    result = simulate_strategy(history, news, "news-catalyst-v1")
    assert result.trades
    for trade in result.trades:
        assert trade.entry_date > trade.signal_date


def test_buy_and_hold_baseline_uses_next_open(history):
    result = buy_and_hold(history, "SPY")
    assert result.start_date.isoformat() == "2025-06-27"
    assert result.signals == 1
    assert result.total_return > 0
    assert result.trades == ()
    assert result.equity_curve[1][0].isoformat() == "2025-06-30"


def test_returns_are_measured_from_initial_equity(history, news):
    results = (
        simulate_strategy(history, news, "momentum-v1"),
        buy_and_hold(history, "SPY"),
        cash_baseline(history),
    )

    for result in results:
        assert result.equity_curve[0][1] == INITIAL_EQUITY
        final_equity = float(result.equity_curve[-1][1])
        expected_return = final_equity / float(INITIAL_EQUITY) - 1
        expected_cagr = (final_equity / float(INITIAL_EQUITY)) ** (
            252 / len(result.equity_curve)
        ) - 1
        assert result.total_return == pytest.approx(expected_return, rel=1e-12)
        assert result.cagr == pytest.approx(expected_cagr, rel=1e-12)
        assert result.end_date == result.equity_curve[-1][0]


def test_cash_baseline_is_flat_and_has_zero_return(history):
    result = cash_baseline(history)

    assert result.equity_curve[0][1] == INITIAL_EQUITY
    assert all(value == INITIAL_EQUITY for _, value in result.equity_curve)
    assert result.total_return == 0.0
    assert result.cagr == 0.0
    assert result.max_drawdown == 0.0
    assert result.exposure_pct == 0.0


def test_drawdown_includes_the_initial_equity_peak(history, news):
    result = simulate_strategy(history, news, "momentum-v1")

    peak = float(INITIAL_EQUITY)
    expected = 0.0
    for _, value in result.equity_curve:
        equity = float(value)
        peak = max(peak, equity)
        expected = max(expected, (peak - equity) / peak)
    assert result.max_drawdown == pytest.approx(expected, rel=1e-12)
