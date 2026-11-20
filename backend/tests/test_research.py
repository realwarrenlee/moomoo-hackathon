from dataclasses import replace
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
    select_instrument_for_exposure,
)
from app.risk.policy import RiskGate
from app.research.strategy import (
    EXPOSURE_POLICY_V3,
    ExposurePolicy,
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


def test_universe_has_exactly_two_directional_etfs():
    assert CANDIDATE_SYMBOLS == ("SPY", "SH")
    assert INSTRUMENTS["SPY"].effective_exposure == Decimal("1")
    assert INSTRUMENTS["SH"].effective_exposure == Decimal("-1")
    assert not INSTRUMENTS["SPY"].leveraged
    assert not INSTRUMENTS["SH"].leveraged
    assert "UPRO" not in INSTRUMENTS
    assert "SPXU" not in INSTRUMENTS


def test_instrument_selection_follows_the_signed_exposure_target():
    assert select_instrument_for_exposure(1, Decimal("0")) is None
    assert select_instrument_for_exposure(1, Decimal("0.10")) == "SPY"
    assert select_instrument_for_exposure(1, Decimal("0.40")) == "SPY"
    assert select_instrument_for_exposure(1, Decimal("1.50")) == "SPY"
    assert select_instrument_for_exposure(-1, Decimal("-0.10")) == "SH"
    assert select_instrument_for_exposure(-1, Decimal("-0.40")) == "SH"
    assert select_instrument_for_exposure(-1, Decimal("-1.50")) == "SH"
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


@pytest.mark.parametrize("version", ["risk-v1", "risk-v2", ""])
def test_exposure_policy_rejects_unsupported_versions(version):
    with pytest.raises(ValueError, match="unsupported exposure policy"):
        replace(EXPOSURE_POLICY_V3, version=version)
    with pytest.raises(ValueError, match="unsupported exposure policy"):
        ExposurePolicy(version=version, allow_leveraged=True)


def test_v3_strong_signal_maps_to_the_moderate_tier_and_one_x_etf():
    strong = directional_history(Decimal("103.2"))  # 3.2% 10-session return
    snapshot = screen(strong, datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert snapshot.market_state == "STRONG_BULLISH"
    assert snapshot.exposure_tier == "MODERATE"
    assert snapshot.target_exposure_fraction == Decimal("0.40")
    assert snapshot.selected_symbol == "SPY"


def test_v3_exceptional_signals_stay_within_the_forty_percent_ceiling():
    bullish = ramped_history(1)  # +8% smooth ramp, low volatility
    snapshot = screen(bullish, datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert snapshot.exposure_tier == "EXCEPTIONAL"
    assert snapshot.target_exposure_fraction == Decimal("0.40")
    assert snapshot.selected_symbol == "SPY"

    bearish = ramped_history(-1)
    snapshot = screen(bearish, datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert snapshot.exposure_tier == "EXCEPTIONAL"
    assert snapshot.target_exposure_fraction == Decimal("-0.40")
    assert snapshot.selected_symbol == "SH"


def test_v3_high_volatility_below_the_directional_ceiling_keeps_the_forty_percent_target():
    downs = tuple(Decimal("100") * (Decimal("0.987") ** index) for index in range(1, 11))
    ups = tuple(
        downs[-1] * (Decimal("1.034") ** index) for index in range(1, 11)
    )
    closes = (Decimal("100"),) * 31 + downs + ups
    snapshot = screen(synthetic_history(closes), datetime(2026, 3, 20, 21, 0, tzinfo=UTC))
    assert Decimal("0.30") < snapshot.spy_volatility_20d <= Decimal("0.40")
    assert snapshot.exposure_tier == "EXCEPTIONAL"
    assert snapshot.target_exposure_fraction == Decimal("0.40")
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
    assert snapshot.selected_symbol == "SPY"
    without_spy = MarketHistory({"SH": strong.bars("SH")}, {})
    adjusted, proposal = decide(snapshot, without_spy, flat_account(now))
    assert adjusted.action == "NO_TRADE"
    assert proposal is None


def test_v3_bearish_flat_account_sizes_the_tier_target():
    history = directional_history(Decimal("98.2"))  # WEAK tier: -10% target
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    adjusted, proposal = decide(snapshot, history, flat_account(now))
    assert adjusted.action == "BUY"
    assert proposal is not None
    assert proposal.symbol == "SH"
    assert proposal.action is ProposalAction.BUY
    assert proposal.requested_quantity == 500  # floor(10% * 100k / 20)
    assert proposal.target_exposure_fraction == Decimal("-0.10")
    assert proposal.run_id.startswith("dryrun-")


def test_v3_bullish_flat_account_sizes_the_tier_target():
    history = directional_history(Decimal("101.7"))  # WEAK tier: 10% target
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    assert snapshot.exposure_tier == "WEAK"
    adjusted, proposal = decide(snapshot, history, flat_account(now))
    assert adjusted.action == "BUY"
    assert proposal is not None
    assert proposal.symbol == "SPY"
    assert proposal.action is ProposalAction.BUY
    assert proposal.requested_quantity == 98  # floor(10% * 100k / 101.7)
    assert proposal.target_exposure_fraction == Decimal("0.10")


def test_v3_exceptional_quantity_caps_at_the_forty_percent_ceiling():
    history = ramped_history(1)  # EXCEPTIONAL tier: 40% via SPY at 1x
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    adjusted, proposal = decide(snapshot, history, flat_account(now))
    assert adjusted.target_symbol == "SPY"
    assert proposal is not None
    assert proposal.symbol == "SPY"
    assert proposal.requested_quantity == 370  # floor(40% * 100k / 108)
    assert proposal.target_exposure_fraction == Decimal("0.4000")
    assert Decimal(proposal.requested_quantity) * Decimal("108") == Decimal("39960")


def test_v3_matching_holding_with_small_drift_is_hold_without_an_order():
    history = directional_history(Decimal("101.7"))  # WEAK: 10% -> 98 SPY
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    account = flat_account(now).model_copy(
        update={"positions": (Position(symbol="SPY", quantity=100, market_value=Decimal("10170")),)}
    )
    adjusted, proposal = decide(snapshot, history, account)
    assert adjusted.action == "HOLD"
    assert adjusted.current_symbol == "SPY"
    assert proposal is None


def test_v3_holding_within_tolerance_is_hold_and_moves_resize():
    history = directional_history(Decimal("101.7"))  # WEAK: 10% -> 98 SPY
    now = session_close_utc(history.session_dates()[-1])
    snapshot = screen(history, now)
    account = flat_account(now).model_copy(
        update={"positions": (Position(symbol="SPY", quantity=98, market_value=Decimal("9967")),)}
    )
    adjusted, proposal = decide(snapshot, history, account)
    assert adjusted.action == "HOLD"
    assert proposal is None

    smaller = flat_account(now).model_copy(
        update={"positions": (Position(symbol="SPY", quantity=80, market_value=Decimal("8136")),)}
    )
    adjusted, proposal = decide(snapshot, history, smaller)
    assert adjusted.action == "BUY"
    assert proposal is not None
    assert proposal.symbol == "SPY"
    assert proposal.requested_quantity == 18  # top-up to the tier target
    assert proposal.target_exposure_fraction is None

    larger = flat_account(now).model_copy(
        update={"positions": (Position(symbol="SPY", quantity=120, market_value=Decimal("12204")),)}
    )
    adjusted, proposal = decide(snapshot, history, larger)
    assert adjusted.action == "SELL"
    assert proposal is not None
    assert proposal.symbol == "SPY"
    assert proposal.requested_quantity == 22  # reduce to the tier target
    assert proposal.target_exposure_fraction is None


@pytest.mark.parametrize("direction, symbol", [(1, "SPY"), (-1, "SH")])
@pytest.mark.parametrize("holding_sessions", [4, 5, 9])
def test_v3_one_x_holding_is_not_subject_to_the_leveraged_duration_limit(
    direction, symbol, holding_sessions
):
    history = ramped_history(direction)
    sessions = history.session_dates()
    now = session_close_utc(sessions[-1])
    snapshot = screen(history, now)
    _, entry = decide(snapshot, history, flat_account(now))
    assert entry is not None and entry.symbol == symbol
    bar = history.bar_on(symbol, sessions[-1])
    assert bar is not None
    account = flat_account(now).model_copy(
        update={
            "positions": (
                Position(
                    symbol=symbol,
                    quantity=entry.requested_quantity,
                    market_value=bar.close * entry.requested_quantity,
                ),
            )
        }
    )
    adjusted, proposal = decide(
        snapshot,
        history,
        account,
        holding_entry_session=sessions[-1 - holding_sessions].isoformat(),
    )
    assert adjusted.action == "HOLD"
    assert not adjusted.duration_exit
    assert proposal is None


def test_moderate_bearish_sh_entry_hits_the_forty_percent_ceiling():
    history = directional_history(Decimal("97"))  # -3% 10-session return, trend confirms
    session = history.session_dates()[-1]
    now = session_close_utc(session)
    snapshot = screen(history, now)
    assert snapshot.target_exposure_fraction == Decimal("-0.40")

    adjusted, proposal = decide(snapshot, history, flat_account(now))

    assert adjusted.action == "BUY"
    assert proposal is not None and proposal.symbol == "SH"
    price = history.bar_on("SH", session).close
    expected = int(INITIAL_EQUITY * Decimal("0.40") / price)
    assert proposal.requested_quantity == expected
    assert proposal.target_exposure_fraction == Decimal("-0.4000")


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
    assert decision.snapshot.target_exposure_fraction == Decimal("-0.10")
    assert decision.snapshot.selected_symbol == "SH"
    assert decision.proposal is not None
    assert decision.proposal.symbol == "SH"
    assert decision.proposal.target_exposure_fraction == Decimal("-0.10")
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
    assert {rule.rule_id for rule in oversized.risk_decision.reasons} == {"R017", "R008", "R019"}


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


def test_v3_gate_rejects_upro_and_spxu_as_outside_the_universe():
    from app.models.contracts import Quote
    from app.research.dryrun import dry_run_control, judge

    now = datetime(2026, 3, 20, 21, 0, tzinfo=UTC)
    history = directional_history(Decimal("103.2"))
    _, base = decide(screen(history, now), history, flat_account(now))
    assert base is not None and base.symbol == "SPY"
    gate = _gate(FINGERPRINT)
    for symbol, price in (("UPRO", Decimal("50")), ("SPXU", Decimal("10"))):
        proposal = base.model_copy(
            update={"symbol": symbol, "target_exposure_fraction": None}
        )
        quote = Quote(
            symbol=symbol,
            price=price,
            currency="USD",
            as_of_utc=now,
            regular_session_open=True,
        )
        decision = judge(gate, proposal, quote, flat_account(now), dry_run_control(), now)
        assert decision.decision is PolicyDecision.REJECT
        assert "R002" in {rule.rule_id for rule in decision.reasons}


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
    assert 0 < result.average_exposure <= result.maximum_exposure
    assert result.maximum_exposure > 0.09  # tier sizing, not a fixed 5% allocation


@pytest.mark.parametrize("direction", [1, -1])
@pytest.mark.parametrize(
    "move, trend_confirmed, fraction",
    [
        ("2", True, "0.10"),
        ("2", False, "0.10"),
        ("4", False, "0.25"),
        ("4", True, "0.40"),
        ("6", False, "0.40"),
        ("6", True, "0.40"),
        ("8", True, "0.40"),
    ],
)
def test_backtest_sizes_current_v2_tiers(direction, move, trend_confirmed, fraction):
    early_close = Decimal("100") if trend_confirmed else Decimal("140" if direction > 0 else "60")
    steps = tuple(
        Decimal("100") + direction * Decimal(move) * index / 10
        for index in range(1, 11)
    )
    history = synthetic_history(
        (early_close,) * 30 + (Decimal("100"),) * 11 + steps + (steps[-1],)
    )
    dates = history.session_dates()
    snapshot = screen(history, session_close_utc(dates[50]))
    assert snapshot.target_exposure_fraction == direction * Decimal(fraction)
    symbol = snapshot.selected_symbol
    assert symbol is not None
    price = history.bar_on(symbol, dates[50]).close
    leverage = INSTRUMENTS[symbol].leverage
    quantity = min(
        int(INITIAL_EQUITY * Decimal(fraction) / (price * leverage)),
        int(INITIAL_EQUITY * Decimal("0.40") / price),
    )

    result = simulate_strategy(history, STRATEGY, cost_bps=Decimal("0"))

    assert result.signals == 1
    assert result.open_position == symbol
    assert result.trades[0].signal_date == dates[50]
    assert result.trades[0].entry_date == dates[51]
    assert result.maximum_exposure == pytest.approx(float(quantity * price * leverage / INITIAL_EQUITY))
    assert result.maximum_exposure > 0.09  # never the retired fixed 5% allocation
    assert result.total_return == 0


@pytest.mark.parametrize("future_close", [Decimal("80"), Decimal("150")])
def test_backtest_sizes_at_signal_close_and_fills_only_at_next_open(future_close):
    history = synthetic_history(
        (Decimal("100"),) * 41 + (Decimal("101.7"),) * 10 + (future_close,)
    )
    bars = history.bars("SPY")
    history = MarketHistory(
        {
            **{symbol: history.bars(symbol) for symbol in history.symbols},
            "SPY": bars[:-1] + (replace(bars[-1], open=Decimal("95")),),
        },
        {},
    )
    result = simulate_strategy(history, STRATEGY)
    trade = result.trades[0]
    quantity = 98  # floor(100k * 10% / 101.7), independent of the next bar
    fill_price = Decimal("95") * Decimal("1.0002")
    assert trade.entry_price == fill_price
    assert trade.entry_date == history.session_dates()[-1]
    assert trade.entry_date > trade.signal_date
    assert result.equity_curve[-1][1] == INITIAL_EQUITY + quantity * (future_close - fill_price)


def test_backtest_never_executes_a_final_close_signal():
    history = synthetic_history((Decimal("100"),) * 51 + (Decimal("102"),))
    result = simulate_strategy(history, STRATEGY)
    assert result.trades == ()
    assert result.open_position is None
    assert result.signals == 0
    assert result.total_return == 0


def test_backtest_unavailable_target_bar_cannot_size_an_entry():
    history = synthetic_history(
        (Decimal("100"),) * 41 + (Decimal("98.2"),) * 11
    )
    bars = history.bars("SH")
    delayed = replace(bars[-2], available_at_utc=bars[-1].available_at_utc + timedelta(days=1))
    history = MarketHistory(
        {
            **{symbol: history.bars(symbol) for symbol in history.symbols},
            "SH": bars[:-2] + (delayed, bars[-1]),
        },
        {},
    )
    result = simulate_strategy(history, STRATEGY)
    assert result.trades == ()
    assert result.total_return == 0


@pytest.mark.parametrize("missing", [False, True])
def test_backtest_unavailable_holding_valuation_fails_closed(missing):
    steps = tuple(Decimal("100") - Decimal("0.2") * index for index in range(1, 11))
    history = synthetic_history(
        (Decimal("100"),) * 41 + steps + (Decimal("97.9"), Decimal("97.8"))
    )
    bars = history.bars("SH")
    delayed = replace(bars[-1], available_at_utc=bars[-1].available_at_utc + timedelta(days=1))
    history = MarketHistory(
        {
            **{symbol: history.bars(symbol) for symbol in history.symbols},
            "SH": bars[:-1] if missing else bars[:-1] + (delayed,),
        },
        {},
    )
    with pytest.raises(ValueError, match="unavailable SH valuation bar"):
        simulate_strategy(history, STRATEGY)


def test_backtest_resizes_at_next_open_and_accounts_for_the_whole_episode():
    steps = tuple(Decimal("100") + Decimal("0.2") * index for index in range(1, 11))
    history = synthetic_history(
        (Decimal("100"),) * 41 + steps + tuple(map(Decimal, ("104", "102", "102", "102")))
    )
    bars = history.bars("SPY")
    history = MarketHistory(
        {
            **{symbol: history.bars(symbol) for symbol in history.symbols},
            "SPY": bars[:51] + tuple(
                replace(bar, open=price)
                for bar, price in zip(bars[51:], map(Decimal, ("102", "104", "102", "102")))
            ),
        },
        {},
    )
    result = simulate_strategy(history, STRATEGY, cost_bps=Decimal("0"))
    # Enter 98 at 102 (WEAK 10%); top up 287 at 104 (MODERATE trend-confirmed
    # 40% cap, 385 total); reduce 288 at 102 (WEAK again); liquidate 97 at 102.
    assert tuple(value for _, value in result.equity_curve) == tuple(
        map(Decimal, ("100000", "100196", "99426", "99426", "99426"))
    )
    assert result.signals == 1
    assert len(result.trades) == 1
    assert result.open_position is None
    trade = result.trades[0]
    assert trade.entry_date == history.session_dates()[51]
    assert trade.exit_date == history.session_dates()[54]
    assert trade.entry_price == Decimal("39844") / 385
    assert trade.exit_price == Decimal("102")
    assert trade.return_pct == pytest.approx(float(Decimal("39270") / Decimal("39844") - 1))


def test_backtest_reversal_waits_for_an_exit_and_later_decision():
    steps = tuple(Decimal("100") + Decimal("0.2") * index for index in range(1, 11))
    history = synthetic_history((Decimal("100"),) * 41 + steps + (Decimal("98"),) * 3)
    result = simulate_strategy(history, STRATEGY, cost_bps=Decimal("0"))
    first, second = result.trades
    dates = history.session_dates()
    assert first.symbol == "SPY"
    assert first.entry_date == dates[51]
    assert first.exit_date == dates[52]
    assert second.symbol == "SH"
    assert second.signal_date == first.exit_date
    assert second.entry_date == dates[53]
    assert result.open_position == "SH"
    assert result.signals == 2
    truncated = MarketHistory(
        {symbol: history.bars(symbol)[:-1] for symbol in history.symbols}, {}
    )
    prefix = simulate_strategy(truncated, STRATEGY, cost_bps=Decimal("0"))
    assert prefix.equity_curve == result.equity_curve[:-1]
    assert prefix.trades == (first,)


@pytest.mark.parametrize("growth, symbol", [("1.01", "SPY"), ("0.99", "SH")])
def test_backtest_exceptional_episode_stays_in_the_one_x_instrument(growth, symbol):
    history = synthetic_history(
        tuple(Decimal("100") * Decimal(growth) ** index for index in range(53))
    )
    result = simulate_strategy(history, STRATEGY, cost_bps=Decimal("0"))
    (trade,) = result.trades
    dates = history.session_dates()
    assert trade.symbol == symbol
    assert trade.entry_date == dates[51]
    # 1x holdings are never forced out by the leveraged duration limit.
    assert trade.exit_date is None
    assert result.open_position == symbol
    assert result.signals == 1
    assert result.maximum_exposure == pytest.approx(0.40, abs=0.01)


def test_backtest_costs_and_opening_gaps_never_spend_more_than_cash():
    steps = tuple(Decimal("100") + Decimal("0.6") * index for index in range(1, 11))
    history = synthetic_history((Decimal("100"),) * 41 + steps + (Decimal("120"),))
    result = simulate_strategy(history, STRATEGY)
    fill_price = Decimal("120") * Decimal("1.0002")
    signal_close = steps[-1]
    quantity = int(INITIAL_EQUITY * Decimal("0.40") / signal_close)
    cash = INITIAL_EQUITY - quantity * fill_price
    assert cash >= 0
    assert result.trades[0].entry_price == fill_price
    assert result.equity_curve[-1][1] == cash + quantity * Decimal("120")
    assert result.maximum_exposure <= 1


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
