from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.contracts import Quote
from app.qoder_tools import CurrentMarketContext, QoderToolService
from app.research.data import MarketHistory, session_close_utc
from app.research.dryrun import build_account, find_accepted_example
from app.research.strategy import STRATEGY_VERSION
from scripts.current_market_run import CollectionError, _load_bars

FIXTURES = Path(__file__).parent / "fixtures"
FINGERPRINT = "current-market-test-fingerprint"
STRATEGY = STRATEGY_VERSION


@pytest.fixture(scope="module")
def history():
    return MarketHistory.from_file(FIXTURES / "moomoo_directional_etf_bars_2026-11-17.json")


@pytest.fixture
def accepted(history):
    decision = find_accepted_example(history, STRATEGY, FINGERPRINT)
    assert decision is not None and decision.proposal is not None
    return decision


def _service(history, accepted, quote_price=None, calls=None, fingerprint=FINGERPRINT):
    now = accepted.snapshot.decision_time_utc
    account = build_account(now, FINGERPRINT, "current-account")
    quote = Quote(
        symbol=accepted.proposal.symbol,
        price=quote_price or accepted.quote.price,
        as_of_utc=now,
        regular_session_open=True,
    )
    calls = calls if calls is not None else {"account": 0, "quote": 0}

    def account_provider():
        calls["account"] += 1
        return account

    def quote_provider(symbol):
        calls["quote"] += 1
        assert symbol == accepted.proposal.symbol
        return quote

    service = QoderToolService(
        history,
        fingerprint,
        current=CurrentMarketContext(
            decision_time_utc=now,
            fingerprint=fingerprint,
            account_provider=account_provider,
            quote_provider=quote_provider,
            control=accepted.control.model_copy(
                update={"order_writes_enabled": False, "first_order_approved": False}
            ),
        ),
        clock=lambda: now,
    )
    return service, calls


def test_current_mode_research_uses_supplied_artifact_and_notice(history, accepted):
    service, _ = _service(history, accepted)
    run_id = service.create_run(STRATEGY)
    result = service.research_market({"run_id": run_id, "strategy_version": STRATEGY})
    assert result["ok"] is True
    assert result["mode"] == "CURRENT_MARKET_READ_ONLY"
    assert "Current read-only Moomoo evidence" in result["notice"]
    expected = accepted.proposal.model_copy(update={"run_id": run_id}).model_dump(mode="json")
    assert result["proposal"] == expected
    assert result["snapshot"]["target_symbol"] == "SH"


def test_current_mode_gate_reads_fresh_account_and_quote_and_keeps_writes_disabled(
    history, accepted
):
    service, calls = _service(history, accepted)
    run_id = service.create_run(STRATEGY)
    research = service.research_market({"run_id": run_id, "strategy_version": STRATEGY})
    result = service.evaluate_proposal({"run_id": run_id, "proposal": research["proposal"]})
    assert result["ok"] is True
    assert result["mode"] == "CURRENT_MARKET_READ_ONLY"
    assert calls == {"account": 2, "quote": 2}
    assert result["risk_decision"]["decision"] == "REJECT"
    assert {item["rule_id"] for item in result["risk_decision"]["reasons"]} == {"R010", "R014"}
    assert "Fresh read-only REST" in result["control_context"]
    assert "equity" not in result


def test_current_mode_wrong_account_is_rejected(history, accepted):
    service, _ = _service(history, accepted, fingerprint="different-account")
    run_id = service.create_run(STRATEGY)
    research = service.research_market({"run_id": run_id, "strategy_version": STRATEGY})
    result = service.evaluate_proposal({"run_id": run_id, "proposal": research["proposal"]})
    assert result["risk_decision"]["decision"] == "REJECT"
    assert "R001" in {item["rule_id"] for item in result["risk_decision"]["reasons"]}


def test_current_mode_tampered_proposal_is_rejected_before_gate(history, accepted):
    service, calls = _service(history, accepted)
    run_id = service.create_run(STRATEGY)
    research = service.research_market({"run_id": run_id, "strategy_version": STRATEGY})
    proposal = dict(research["proposal"])
    proposal["thesis"] = "substituted prose"
    result = service.evaluate_proposal({"run_id": run_id, "proposal": proposal})
    assert result["error"]["code"] == "invalid_input"
    assert calls == {"account": 1, "quote": 1}


def test_current_mode_cash_decision_never_calls_the_gate(history, accepted):
    now = session_close_utc(date(2026, 11, 13))
    account = build_account(now, FINGERPRINT, "current-account")
    service = QoderToolService(
        history,
        FINGERPRINT,
        current=CurrentMarketContext(
            decision_time_utc=now,
            fingerprint=FINGERPRINT,
            account_provider=lambda: account,
            quote_provider=lambda symbol: Quote(
                symbol=symbol,
                price=Decimal("500"),
                as_of_utc=now,
                regular_session_open=True,
            ),
            control=accepted.control,
        ),
        clock=lambda: now,
    )
    run_id = service.create_run(STRATEGY)
    research = service.research_market({"run_id": run_id, "strategy_version": STRATEGY})
    assert research["proposal"] is None
    assert research["snapshot"]["action"] == "CASH"
    result = service.evaluate_proposal(
        {"run_id": run_id, "proposal": accepted.proposal.model_dump(mode="json")}
    )
    assert result["error"]["code"] == "no_proposal"


def test_bar_validation_rejects_current_session_and_requires_prior_session(history):
    path = FIXTURES / "moomoo_directional_etf_bars_2026-11-17.json"
    last = history.session_dates()[-1]
    same_day = datetime(last.year, last.month, last.day, 23, 0, tzinfo=UTC)
    with pytest.raises(CollectionError, match="incomplete current-session"):
        _load_bars(path, same_day)

    friday = datetime(2026, 11, 20, 23, 0, tzinfo=UTC)
    with pytest.raises(CollectionError, match="expected the prior completed session"):
        _load_bars(path, friday)
