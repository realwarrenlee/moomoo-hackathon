from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.contracts import (
    AccountSnapshot,
    OpenOrder,
    OrderSide,
    PolicyDecision,
    Position,
    ProposalAction,
)
from app.research.data import DailyBar, MarketHistory, session_close_utc
from app.research.dryrun import (
    _gate,
    control_rejection_example,
    decide_at,
    find_accepted_example,
    latest_decision,
    oversized_example,
    stale_quote_example,
)
from app.research.evaluate import INITIAL_EQUITY, buy_and_hold, cash_baseline, simulate_strategy
from app.research.instruments import (
    CANDIDATE_SYMBOLS,
    INSTRUMENTS,
    select_instrument,
    select_instrument_for_exposure,
)
from app.risk.policy import RiskGate
from app.research.strategy import (
    EXPOSURE_POLICY_V1,
    EXPOSURE_POLICY_V2,
    MIN_COMPLETED_SESSIONS,
    STRATEGY_VERSION,
    decide,
    screen,
)

FIXTURES = Path(__file__).parent / "fixtures"
BARS = FIXTURES / "moomoo_directional_etf_bars_2026-11-17.json"
FINGERPRINT = "test-competition-paper-fingerprint"
STRATEGY = STRATEGY_VERSION


@pytest.fixture(scope="module")
def history():
    return MarketHistory.from_file(BARS)


def _sessions(count: int = MIN_COMPLETED_SESSIONS) -> tuple[date, ...]:
    day = date(2026, 1, 5)
    values = []
    while len(values) < count:
        if day.weekday() < 5:
            values.append(day)
        day += timedelta(days=1)
    return tuple(values)


def _bars(symbol: str, closes: tuple[Decimal, ...], dates: tuple[date, ...]) -> tuple[DailyBar, ...]:
    return tuple(
        DailyBar(
            symbol=symbol,
            session_date=session,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000_000,
            available_at_utc=session_close_utc(session),
        )
        for session, close in zip(dates, closes)
    )


def synthetic_history(spy_closes: tuple[Decimal, ...]) -> MarketHistory:
    dates = _sessions(len(spy_closes))
    others = {
        "UPRO": Decimal("50"),
        "SH": Decimal("20"),
        "SPXU": Decimal("10"),
    }
    payload = {"SPY": _bars("SPY", spy_closes, dates)}
    for symbol, close in others.items():
        payload[symbol] = _bars(symbol, tuple(close for _ in dates), dates)
    return MarketHistory(payload, {})


def directional_history(last_close: Decimal) -> MarketHistory:
    return synthetic_history((Decimal("100"),) * 41 + (last_close,) * 10)


def ramped_history(direction: int) -> MarketHistory:
    """A smooth |return_10d| == 8% ramp whose 20-session volatility stays low."""
    steps = tuple(
        Decimal("100") + direction * Decimal(index) * Decimal("0.8")
        for index in range(1, 11)
    )
    return synthetic_history((Decimal("100"),) * 41 + steps)


def flat_account(now: datetime, *, equity: Decimal = Decimal("100000")) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id="test-account",
        account_fingerprint=FINGERPRINT,
        environment="paper",
        equity=equity,
        day_start_equity=equity,
        peak_equity=equity,
        cash=equity,
        buying_power=equity,
        as_of_utc=now,
        reconciled=True,
    )


def test_universe_has_exactly_four_directional_etfs():
    assert CANDIDATE_SYMBOLS == ("SPY", "UPRO", "SH", "SPXU")
    assert INSTRUMENTS["SPY"].effective_exposure == Decimal("1")
    assert INSTRUMENTS["UPRO"].effective_exposure == Decimal("3")
    assert INSTRUMENTS["SH"].effective_exposure == Decimal("-1")
    assert INSTRUMENTS["SPXU"].effective_exposure == Decimal("-3")
    assert not INSTRUMENTS["SPY"].leveraged
    assert not INSTRUMENTS["SH"].leveraged
    assert INSTRUMENTS["UPRO"].leveraged
    assert INSTRUMENTS["SPXU"].leveraged


def test_instrument_mapping_prefers_leverage_only_when_approved():
    assert select_instrument(1, False, False) == "SPY"
    assert select_instrument(1, True, False) == "SPY"
    assert select_instrument(1, True, True) == "UPRO"
    assert select_instrument(-1, False, False) == "SH"
    assert select_instrument(-1, True, False) == "SH"
    assert select_instrument(-1, True, True) == "SPXU"
    assert select_instrument(0, True, True) is None


def test_instrument_selection_follows_the_signed_exposure_target():
    assert select_instrument_for_exposure(1, Decimal("0")) is None
    assert select_instrument_for_exposure(1, Decimal("0.40")) == "SPY"
    assert select_instrument_for_exposure(1, Decimal("1.00")) == "SPY"
    assert select_instrument_for_exposure(1, Decimal("1.50")) == "UPRO"
    assert select_instrument_for_exposure(-1, Decimal("-0.60")) == "SH"
    assert select_instrument_for_exposure(-1, Decimal("-1.00")) == "SH"
    assert select_instrument_for_exposure(-1, Decimal("-1.50")) == "SPXU"
    assert select_instrument_for_exposure(0, Decimal("0.5")) is None


def test_bullish_and_bearish_signals_select_matching_unleveraged_etf():
    bullish = screen(directional_history(Decimal("101.7")), datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert bullish.market_state == "BULLISH"
    assert bullish.selected_symbol == "SPY"
    assert bullish.action == "BUY"

    bearish = screen(directional_history(Decimal("98.2")), datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert bearish.market_state == "BEARISH"
    assert bearish.selected_symbol == "SH"
    assert bearish.action == "BUY"


def test_v1_policy_keeps_strong_signals_in_one_x_etfs():
    strong = directional_history(Decimal("103.2"))
    snapshot = screen(
        strong,
        datetime(2026, 3, 20, 21, 0, tzinfo=UTC),
        exposure_policy=EXPOSURE_POLICY_V1,
    )
    assert snapshot.market_state == "STRONG_BULLISH"
    assert snapshot.selected_symbol == "SPY"
    assert snapshot.target_exposure_fraction is None

    bearish = directional_history(Decimal("96.5"))
    snapshot = screen(
        bearish,
        datetime(2026, 3, 20, 21, 0, tzinfo=UTC),
        exposure_policy=EXPOSURE_POLICY_V1,
    )
    assert snapshot.market_state == "STRONG_BEARISH"
    assert snapshot.selected_symbol == "SH"


def test_v2_strong_signal_maps_to_the_moderate_tier_and_one_x_etf():
    strong = directional_history(Decimal("103.2"))  # 3.2% 10-session return
    snapshot = screen(strong, datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert snapshot.market_state == "STRONG_BULLISH"
    assert snapshot.exposure_tier == "MODERATE"
    assert snapshot.target_exposure_fraction == Decimal("0.60")
    assert snapshot.selected_symbol == "SPY"


def test_v2_exceptional_signals_select_the_three_x_etf():
    bullish = ramped_history(1)  # +8% smooth ramp, low volatility
    snapshot = screen(bullish, datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert snapshot.exposure_tier == "EXCEPTIONAL"
    assert snapshot.target_exposure_fraction == Decimal("1.50")
    assert snapshot.selected_symbol == "UPRO"

    bearish = ramped_history(-1)
    snapshot = screen(bearish, datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert snapshot.exposure_tier == "EXCEPTIONAL"
    assert snapshot.target_exposure_fraction == Decimal("-1.50")
    assert snapshot.selected_symbol == "SPXU"


def test_v2_high_volatility_caps_the_target_at_one_hundred_percent():
    downs = tuple(Decimal("100") * (Decimal("0.987") ** index) for index in range(1, 11))
    ups = tuple(
        downs[-1] * (Decimal("1.034") ** index) for index in range(1, 11)
    )
    closes = (Decimal("100"),) * 31 + downs + ups
    snapshot = screen(synthetic_history(closes), datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert Decimal("0.30") < snapshot.spy_volatility_20d <= Decimal("0.40")
    assert snapshot.exposure_tier == "EXCEPTIONAL"
    assert snapshot.target_exposure_fraction == Decimal("1.00")
    assert snapshot.selected_symbol == "SPY"


def test_neutral_signal_targets_cash():
    snapshot = screen(
        synthetic_history((Decimal("100"),) * MIN_COMPLETED_SESSIONS),
        datetime(2026, 3, 20, 21, 0, tzinfo=UTC),
    )
    assert snapshot.market_state == "NEUTRAL"
    assert snapshot.selected_symbol is None
    assert snapshot.action == "CASH"


def test_high_volatility_forces_cash_even_with_a_directional_return():
    closes = (Decimal("100"),) * 41 + (Decimal("100"), Decimal("120")) * 5
    snapshot = screen(synthetic_history(closes), datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert snapshot.spy_volatility_20d > Decimal("0.40")
    assert snapshot.selected_symbol is None
    assert snapshot.action == "CASH"


def test_insufficient_history_abstains_without_a_proposal():
    history = synthetic_history((Decimal("100"),) * (MIN_COMPLETED_SESSIONS - 1))
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    assert snapshot.action == "NO_TRADE"
    assert snapshot.selected_symbol is None
    proposal = decide(snapshot, history, flat_account(now))[1]
    assert proposal is None


def test_missing_target_bar_blocks_sizing():
    strong = ramped_history(1)
    now = session_close_utc(strong.session_dates()[-1])
    snapshot = screen(strong, now)
    assert snapshot.selected_symbol == "UPRO"
    without_upro = MarketHistory(
        {"SPY": strong.bars("SPY"), "SH": strong.bars("SH"), "SPXU": strong.bars("SPXU")},
        {},
    )
    adjusted, proposal = decide(snapshot, without_upro, flat_account(now))
    assert adjusted.action == "NO_TRADE"
    assert proposal is None


def test_v1_flat_account_sizes_the_legacy_five_percent_position():
    history = directional_history(Decimal("101.7"))
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now, exposure_policy=EXPOSURE_POLICY_V1)
    adjusted, proposal = decide(
        snapshot, history, flat_account(now), exposure_policy=EXPOSURE_POLICY_V1
    )
    assert adjusted.action == "BUY"
    assert proposal is not None
    assert proposal.symbol == "SPY"
    assert proposal.action is ProposalAction.BUY
    assert proposal.requested_quantity == 49
    assert proposal.run_id.startswith("dryrun-")


def test_v2_bullish_flat_account_sizes_the_tier_target():
    history = directional_history(Decimal("101.7"))  # WEAK tier: 20% target
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    assert snapshot.exposure_tier == "WEAK"
    adjusted, proposal = decide(snapshot, history, flat_account(now))
    assert adjusted.action == "BUY"
    assert proposal is not None
    assert proposal.symbol == "SPY"
    assert proposal.action is ProposalAction.BUY
    assert proposal.requested_quantity == 196  # floor(20% * 100k / 101.7)
    assert proposal.target_exposure_fraction == Decimal("0.20")


def test_v2_exceptional_quantity_uses_leverage_aware_sizing():
    history = ramped_history(1)  # EXCEPTIONAL tier: 150% via UPRO at 3x
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    adjusted, proposal = decide(snapshot, history, flat_account(now))
    assert adjusted.target_symbol == "UPRO"
    assert proposal is not None
    assert proposal.symbol == "UPRO"
    assert proposal.requested_quantity == 1000  # floor(150% * 100k / (50 * 3))
    assert proposal.target_exposure_fraction == Decimal("1.50")
    assert (
        Decimal(proposal.requested_quantity) * Decimal("50") * Decimal("3")
        == Decimal("150000")
    )


def test_v1_matching_holding_is_hold_without_an_order():
    history = directional_history(Decimal("101.7"))
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now, exposure_policy=EXPOSURE_POLICY_V1)
    account = flat_account(now).model_copy(
        update={"positions": (Position(symbol="SPY", quantity=50, market_value=Decimal("5000")),)}
    )
    adjusted, proposal = decide(snapshot, history, account, exposure_policy=EXPOSURE_POLICY_V1)
    assert adjusted.action == "HOLD"
    assert adjusted.current_symbol == "SPY"
    assert proposal is None


def test_v2_holding_within_tolerance_is_hold_and_moves_resize():
    history = directional_history(Decimal("101.7"))  # WEAK: 20% -> 196 SPY
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    account = flat_account(now).model_copy(
        update={"positions": (Position(symbol="SPY", quantity=196, market_value=Decimal("19933")),)}
    )
    adjusted, proposal = decide(snapshot, history, account)
    assert adjusted.action == "HOLD"
    assert proposal is None

    smaller = flat_account(now).model_copy(
        update={"positions": (Position(symbol="SPY", quantity=150, market_value=Decimal("15255")),)}
    )
    adjusted, proposal = decide(snapshot, history, smaller)
    assert adjusted.action == "BUY"
    assert proposal is not None
    assert proposal.symbol == "SPY"
    assert proposal.requested_quantity == 46  # top-up to the tier target


def test_neutral_flat_account_remains_in_cash():
    history = synthetic_history((Decimal("100"),) * MIN_COMPLETED_SESSIONS)
    now = session_close_utc(history.session_dates()[-1])
    adjusted, proposal = decide(screen(history, now), history, flat_account(now))
    assert adjusted.action == "CASH"
    assert proposal is None


def test_opposite_target_exits_the_holding_before_any_entry():
    history = directional_history(Decimal("98.2"))
    now = session_close_utc(history.session_dates()[-1])
    account = flat_account(now).model_copy(
        update={"positions": (Position(symbol="SPY", quantity=50, market_value=Decimal("5000")),)}
    )
    adjusted, proposal = decide(screen(history, now), history, account)
    assert adjusted.action == "SELL"
    assert adjusted.reentry_symbol == "SH"
    assert proposal is not None
    assert proposal.symbol == "SPY"
    assert proposal.action is ProposalAction.SELL
    assert proposal.requested_quantity == 50

    confirmed_flat = flat_account(now)
    reentered, buy = decide(screen(history, now), history, confirmed_flat)
    assert reentered.action == "BUY"
    assert buy is not None and buy.symbol == "SH"


def test_working_order_defers_decision_and_unreconciled_account_abstains():
    history = directional_history(Decimal("101.7"))
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    working = flat_account(now).model_copy(
        update={
            "open_orders": (
                OpenOrder(
                    symbol="SPY",
                    side=OrderSide.BUY,
                    remaining_quantity=1,
                    reference_price=Decimal("100"),
                ),
            )
        }
    )
    assert decide(snapshot, history, working)[0].action == "HOLD"
    unreconciled = flat_account(now).model_copy(update={"reconciled": False})
    assert decide(snapshot, history, unreconciled)[0].action == "NO_TRADE"


def test_latest_real_spy_signal_is_bearish_and_targets_sh(history):
    decision = latest_decision(history, STRATEGY, FINGERPRINT)
    assert decision.snapshot.spy_session_date == "2026-11-17"
    assert decision.snapshot.market_state == "BEARISH"
    assert decision.snapshot.exposure_tier == "WEAK"
    assert decision.snapshot.target_exposure_fraction == Decimal("-0.20")
    assert decision.snapshot.selected_symbol == "SH"
    assert decision.proposal is not None
    assert decision.proposal.symbol == "SH"
    assert decision.proposal.target_exposure_fraction == Decimal("-0.20")
    assert decision.risk_decision is not None
    assert decision.risk_decision.decision is PolicyDecision.APPROVE
    assert decision.risk_decision.reasons == ()


def test_historical_accepted_example_passes_the_existing_gate(history):
    decision = find_accepted_example(history, STRATEGY, FINGERPRINT)
    assert decision is not None
    assert decision.proposal is not None
    assert decision.proposal.symbol == "SH"
    assert decision.risk_decision is not None
    assert decision.risk_decision.decision is PolicyDecision.APPROVE
    assert decision.risk_decision.approved_quantity == decision.proposal.requested_quantity


def test_stale_quote_and_oversized_quantity_are_rejected(history):
    accepted = find_accepted_example(history, STRATEGY, FINGERPRINT)
    assert accepted is not None
    stale = stale_quote_example(accepted, FINGERPRINT)
    assert stale is not None and stale.risk_decision is not None
    assert stale.risk_decision.decision is PolicyDecision.REJECT
    assert {rule.rule_id for rule in stale.risk_decision.reasons} == {"R007"}

    oversized = oversized_example(accepted, FINGERPRINT)
    assert oversized is not None and oversized.risk_decision is not None
    assert oversized.risk_decision.decision is PolicyDecision.REJECT
    assert {rule.rule_id for rule in oversized.risk_decision.reasons} == {"R017", "R008"}


def test_control_rejections_fail_closed(history):
    accepted = find_accepted_example(history, STRATEGY, FINGERPRINT)
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


def test_incumbent_v1_gate_rejects_a_three_x_proposal(history):
    from app.research.dryrun import dry_run_control, judge

    strong = ramped_history(1)
    now = session_close_utc(strong.session_dates()[-1])
    snapshot, proposal = decide(screen(strong, now), strong, flat_account(now))
    assert proposal is not None and proposal.symbol == "UPRO"
    proposal = proposal.model_copy(update={"requested_quantity": 30})
    quote = strong.quote("UPRO", now)
    assert quote is not None
    gate = RiskGate(
        expected_account_fingerprint=FINGERPRINT,
        allowed_symbols=frozenset(CANDIDATE_SYMBOLS),
        leverage_by_symbol={
            symbol: item.leverage for symbol, item in INSTRUMENTS.items()
        },
    )
    decision = judge(gate, proposal, quote, flat_account(now), dry_run_control(), now)
    assert decision.decision is PolicyDecision.REJECT
    assert {rule.rule_id for rule in decision.reasons} == {"R015"}


def test_three_x_exposure_is_measured_effectively(history):
    from app.research.dryrun import dry_run_control, judge

    strong = ramped_history(1)
    now = session_close_utc(strong.session_dates()[-1])
    snapshot, proposal = decide(screen(strong, now), strong, flat_account(now))
    assert proposal is not None
    oversized = proposal.model_copy(
        update={"requested_quantity": 1200, "target_exposure_fraction": None}
    )
    quote = strong.quote("UPRO", now)
    assert quote is not None
    gate = RiskGate(
        expected_account_fingerprint=FINGERPRINT,
        allowed_symbols=frozenset(CANDIDATE_SYMBOLS),
        leverage_by_symbol={
            symbol: item.leverage for symbol, item in INSTRUMENTS.items()
        },
        policy_version="risk-v2",
        allow_leveraged=True,
        enforce_min_exposure=True,
    )
    decision = judge(gate, oversized, quote, flat_account(now), dry_run_control(), now)
    assert decision.decision is PolicyDecision.REJECT
    assert {rule.rule_id for rule in decision.reasons} == {"R017"}

    approved = judge(
        gate,
        proposal,
        quote,
        flat_account(now),
        dry_run_control(),
        now,
    )
    assert approved.decision is PolicyDecision.APPROVE
    assert approved.approved_quantity == proposal.requested_quantity


def test_wrong_account_and_duplicate_submission_fail_closed(history):
    accepted = find_accepted_example(history, STRATEGY, FINGERPRINT)
    assert accepted is not None and accepted.proposal is not None and accepted.quote is not None
    gate = _gate(FINGERPRINT)
    wrong = accepted.account.model_copy(update={"account_fingerprint": "someone-else"})
    rejected = gate.evaluate(
        proposal=accepted.proposal,
        account=wrong,
        quote=accepted.quote,
        control=accepted.control,
        now=accepted.account.as_of_utc,
    )
    assert {rule.rule_id for rule in rejected.reasons} == {"R001"}

    duplicate = gate.evaluate(
        proposal=accepted.proposal,
        account=accepted.account,
        quote=accepted.quote,
        control=accepted.control,
        now=accepted.account.as_of_utc,
        duplicate=True,
    )
    assert {rule.rule_id for rule in duplicate.reasons} == {"R011"}


def test_backtest_enters_after_the_signal_and_tracks_effective_exposure(history):
    result = simulate_strategy(history, STRATEGY)
    assert result.trades
    for trade in result.trades:
        assert trade.entry_date > trade.signal_date
        if trade.exit_date is not None:
            assert trade.exit_date > trade.entry_date
    assert any(trade.symbol in {"SPY", "UPRO"} for trade in result.trades)
    assert any(trade.symbol in {"SH", "SPXU"} for trade in result.trades)
    assert result.average_exposure <= 0.06
    assert result.maximum_exposure <= 0.08


def test_buy_and_hold_starts_after_the_minimum_history(history):
    dates = history.session_dates()
    result = buy_and_hold(history, "SPY")
    assert result.start_date == dates[MIN_COMPLETED_SESSIONS]
    assert result.signals == 1
    assert result.trades == ()
    assert result.equity_curve[1][0] == dates[MIN_COMPLETED_SESSIONS + 1]


def test_returns_are_measured_from_initial_equity(history):
    results = (
        simulate_strategy(history, STRATEGY),
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


def test_cash_baseline_is_flat(history):
    result = cash_baseline(history)
    assert all(value == INITIAL_EQUITY for _, value in result.equity_curve)
    assert result.total_return == 0.0
    assert result.cagr == 0.0
    assert result.max_drawdown == 0.0
    assert result.exposure_pct == 0.0
