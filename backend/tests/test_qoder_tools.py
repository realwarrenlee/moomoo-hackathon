import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.qoder_tools import EVALUATE_TOOL_SCHEMA, RESEARCH_TOOL_SCHEMA, QoderToolService
from app.research.data import MarketHistory, session_close_utc
from app.research.dryrun import VERIFIED_EQUITY, find_accepted_example
from app.research.strategy import STRATEGY_VERSION

FIXTURES = Path(__file__).parent / "fixtures"
FINGERPRINT = "test-competition-paper-fingerprint"
STRATEGY = STRATEGY_VERSION


@pytest.fixture(scope="module")
def history():
    return MarketHistory.from_file(FIXTURES / "moomoo_directional_etf_bars_2026-11-17.json")


@pytest.fixture
def service(history):
    return QoderToolService(history, FINGERPRINT)


def _accepted_run(service, history, **kwargs):
    accepted = find_accepted_example(history, STRATEGY, FINGERPRINT)
    assert accepted is not None and accepted.proposal is not None
    run_id = service.create_run(
        STRATEGY,
        decision_time_utc=accepted.snapshot.decision_time_utc,
        **kwargs,
    )
    research = service.research_market({"run_id": run_id, "strategy_version": STRATEGY})
    assert research["ok"] is True
    assert research["proposal"] is not None
    return run_id, research


def test_tool_schemas_are_closed_and_allowlisted():
    assert RESEARCH_TOOL_SCHEMA["additionalProperties"] is False
    assert EVALUATE_TOOL_SCHEMA["additionalProperties"] is False
    assert set(RESEARCH_TOOL_SCHEMA["properties"]) == {"run_id", "strategy_version"}
    assert set(EVALUATE_TOOL_SCHEMA["properties"]) == {"run_id", "proposal"}
    assert RESEARCH_TOOL_SCHEMA["properties"]["strategy_version"]["enum"] == [STRATEGY]


def test_neutral_pinned_session_returns_cash_without_a_proposal(service):
    run_id = service.create_run(
        STRATEGY, decision_time_utc=session_close_utc(date(2026, 11, 13))
    )
    result = service.dispatch(
        "research_market", {"run_id": run_id, "strategy_version": STRATEGY}
    )
    assert result["ok"] is True
    assert result["mode"] == "HISTORICAL_DRY_RUN"
    assert result["proposal"] is None
    assert result["snapshot"]["selected_symbol"] is None
    assert result["snapshot"]["action"] == "CASH"
    assert service.evaluate_proposal({"run_id": run_id, "proposal": {}})["ok"] is False


def test_latest_real_session_returns_a_policy_rejected_sh_proposal(service):
    run_id = service.create_run(STRATEGY)
    research = service.research_market({"run_id": run_id, "strategy_version": STRATEGY})
    assert research["ok"] is True
    assert research["proposal"]["symbol"] == "SH"
    assert research["snapshot"]["market_state"] == "BEARISH"
    evaluated = service.evaluate_proposal(
        {"run_id": run_id, "proposal": research["proposal"]}
    )
    assert evaluated["ok"] is True
    assert evaluated["risk_decision"]["decision"] == "REJECT"
    assert {rule["rule_id"] for rule in evaluated["risk_decision"]["reasons"]} == {"R002"}


def test_accepted_proposal_uses_real_risk_gate(service, history):
    run_id, research = _accepted_run(service, history)
    assert research["proposal"]["run_id"] == run_id
    result = service.evaluate_proposal({"run_id": run_id, "proposal": research["proposal"]})
    assert result["ok"] is True
    assert result["risk_decision"]["decision"] == "APPROVE"
    assert result["risk_decision"]["approved_quantity"] == research["proposal"]["requested_quantity"]
    assert result["risk_decision"]["policy_version"] == "risk-v1"


def test_stale_quote_is_rejected(service, history):
    accepted = find_accepted_example(history, STRATEGY, FINGERPRINT)
    assert accepted is not None
    run_id, research = _accepted_run(
        service,
        history,
        evaluation_now=accepted.snapshot.decision_time_utc + timedelta(minutes=10),
    )
    result = service.evaluate_proposal({"run_id": run_id, "proposal": research["proposal"]})
    assert result["risk_decision"]["decision"] == "REJECT"
    assert {rule["rule_id"] for rule in result["risk_decision"]["reasons"]} == {"R007"}


def test_oversized_proposal_is_rejected(service, history):
    run_id, research = _accepted_run(service, history)
    proposal = dict(research["proposal"])
    quote = service.history.quote(
        proposal["symbol"], datetime.fromisoformat(proposal["decision_time_utc"])
    )
    assert quote is not None
    proposal["requested_quantity"] = int(VERIFIED_EQUITY * Decimal("0.20") / quote.price)
    result = service.evaluate_proposal({"run_id": run_id, "proposal": proposal})
    assert result["risk_decision"]["decision"] == "REJECT"
    assert "R004" in {rule["rule_id"] for rule in result["risk_decision"]["reasons"]}


def test_malformed_and_untrusted_inputs_fail_closed(service):
    run_id = service.create_run(STRATEGY)
    cases = [
        ("research_market", {"run_id": run_id, "strategy_version": STRATEGY, "path": "../../.env"}),
        ("research_market", {"run_id": run_id, "strategy_version": "spy-directional; rm -rf /"}),
        ("research_market", {"run_id": "unknown-run", "strategy_version": STRATEGY}),
        ("research_market", {"run_id": run_id, "strategy_version": "retired-strategy-v1"}),
        ("sim_trade_input_order", {"run_id": run_id}),
        ("evaluate_proposal", {"run_id": run_id, "proposal": {"thesis": "not-a-proposal"}}),
    ]
    for tool_name, payload in cases:
        result = service.dispatch(tool_name, payload)
        assert result["ok"] is False
        assert result["error"]["code"] in {"invalid_input", "unknown_run", "unsupported_tool"}


def test_validation_error_does_not_echo_proposal_content(service):
    secret_like_text = "do-not-echo-this-prose"
    result = service.evaluate_proposal(
        {"run_id": "unknown-run", "proposal": {"thesis": secret_like_text}}
    )
    assert result["ok"] is False
    assert secret_like_text not in json.dumps(result)


def test_tampered_proposal_is_rejected_before_gate(service, history):
    run_id, research = _accepted_run(service, history)
    proposal = dict(research["proposal"])
    proposal["thesis"] = "Agent substituted its own thesis"
    result = service.evaluate_proposal({"run_id": run_id, "proposal": proposal})
    assert result == {
        "ok": False,
        "error": {
            "code": "invalid_input",
            "message": "Proposal does not match the pinned research artifact",
        },
    }

    rebound = dict(research["proposal"])
    rebound["run_id"] = "dryrun-20260817T210000Z-spy-directional"
    result = service.evaluate_proposal({"run_id": run_id, "proposal": rebound})
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_input"


def test_input_bounds_and_internal_errors_abstain(service, monkeypatch):
    run_id = service.create_run(STRATEGY)
    oversized_input = {"run_id": run_id, "strategy_version": STRATEGY, "padding": "x" * 20_000}
    assert service.research_market(oversized_input)["error"]["code"] == "invalid_input"

    def fail(*args, **kwargs):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr("app.qoder_tools.latest_decision", fail)
    result = service.dispatch(
        "research_market", {"run_id": run_id, "strategy_version": STRATEGY}
    )
    assert result["error"]["code"] == "tool_error"
    assert "sensitive" not in json.dumps(result)


def test_outputs_exclude_account_fingerprint(service, history):
    run_id, research = _accepted_run(service, history)
    evaluated = service.evaluate_proposal({"run_id": run_id, "proposal": research["proposal"]})
    combined = json.dumps([research, evaluated])
    assert FINGERPRINT not in combined
    assert "account_fingerprint" not in combined
    assert "equity" not in evaluated
    assert research["snapshot"]["spy_session_date"] == "2026-10-13"
    assert research["snapshot"]["target_symbol"] == "SPY"
    assert research["snapshot"]["action"] == "BUY"
