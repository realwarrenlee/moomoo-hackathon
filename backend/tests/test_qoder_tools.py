import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.qoder_tools import EVALUATE_TOOL_SCHEMA, RESEARCH_TOOL_SCHEMA, QoderToolService
from app.research.data import MarketHistory, NewsArchive
from app.research.dryrun import VERIFIED_EQUITY, find_accepted_example

FIXTURES = Path(__file__).parent / "fixtures"
FINGERPRINT = "test-competition-paper-fingerprint"


@pytest.fixture(scope="module")
def history():
    return MarketHistory.from_file(FIXTURES / "moomoo_daily_bars_2026-11-16.json")


@pytest.fixture(scope="module")
def news():
    return NewsArchive.from_file(FIXTURES / "moomoo_news_2026-11-17.json")


@pytest.fixture
def service(history, news):
    return QoderToolService(history, news, FINGERPRINT)


def _accepted_run(service, history, news, **kwargs):
    accepted = find_accepted_example(history, news, "momentum-v1", FINGERPRINT)
    assert accepted is not None
    run_id = service.create_run(
        "momentum-v1",
        decision_time_utc=accepted.snapshot.decision_time_utc,
        **kwargs,
    )
    research = service.research_market({"run_id": run_id, "strategy_version": "momentum-v1"})
    assert research["ok"] is True
    assert research["proposal"] is not None
    return run_id, research


def test_tool_schemas_are_closed_and_allowlisted():
    assert RESEARCH_TOOL_SCHEMA["additionalProperties"] is False
    assert EVALUATE_TOOL_SCHEMA["additionalProperties"] is False
    assert set(RESEARCH_TOOL_SCHEMA["properties"]) == {"run_id", "strategy_version"}
    assert set(EVALUATE_TOOL_SCHEMA["properties"]) == {"run_id", "proposal"}


def test_latest_no_trade_path(service):
    run_id = service.create_run("momentum-v1")
    result = service.dispatch(
        "research_market", {"run_id": run_id, "strategy_version": "momentum-v1"}
    )
    assert result["ok"] is True
    assert result["mode"] == "HISTORICAL_DRY_RUN"
    assert result["proposal"] is None
    assert result["snapshot"]["selected_symbol"] is None
    assert result["snapshot"]["no_trade_reason"] is not None
    assert service.evaluate_proposal({"run_id": run_id, "proposal": {}})["ok"] is False


def test_accepted_proposal_uses_real_risk_gate(service, history, news):
    run_id, research = _accepted_run(service, history, news)
    result = service.evaluate_proposal({"run_id": run_id, "proposal": research["proposal"]})
    assert result["ok"] is True
    assert result["risk_decision"]["decision"] == "APPROVE"
    assert result["risk_decision"]["approved_quantity"] == research["proposal"]["requested_quantity"]
    assert result["risk_decision"]["policy_version"] == "risk-v1"


def test_stale_quote_is_rejected(service, history, news):
    accepted = find_accepted_example(history, news, "momentum-v1", FINGERPRINT)
    assert accepted is not None
    run_id, research = _accepted_run(
        service,
        history,
        news,
        evaluation_now=accepted.snapshot.decision_time_utc + timedelta(minutes=10),
    )
    result = service.evaluate_proposal({"run_id": run_id, "proposal": research["proposal"]})
    assert result["risk_decision"]["decision"] == "REJECT"
    assert {rule["rule_id"] for rule in result["risk_decision"]["reasons"]} == {"R007"}


def test_oversized_proposal_is_rejected(service, history, news):
    run_id, research = _accepted_run(service, history, news)
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
    run_id = service.create_run("momentum-v1")
    cases = [
        ("research_market", {"run_id": run_id, "strategy_version": "momentum-v1", "path": "../../.env"}),
        ("research_market", {"run_id": run_id, "strategy_version": "momentum-v1; rm -rf /"}),
        ("research_market", {"run_id": "unknown-run", "strategy_version": "momentum-v1"}),
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


def test_tampered_proposal_is_rejected_before_gate(service, history, news):
    run_id, research = _accepted_run(service, history, news)
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


def test_input_bounds_and_internal_errors_abstain(service, monkeypatch):
    run_id = service.create_run("momentum-v1")
    oversized_input = {"run_id": run_id, "strategy_version": "momentum-v1", "padding": "x" * 20_000}
    assert service.research_market(oversized_input)["error"]["code"] == "invalid_input"

    def fail(*args, **kwargs):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr("app.qoder_tools.latest_decision", fail)
    result = service.dispatch(
        "research_market", {"run_id": run_id, "strategy_version": "momentum-v1"}
    )
    assert result["error"]["code"] == "tool_error"
    assert "sensitive" not in json.dumps(result)


def test_outputs_exclude_account_fingerprint(service, history, news):
    run_id, research = _accepted_run(service, history, news)
    evaluated = service.evaluate_proposal({"run_id": run_id, "proposal": research["proposal"]})
    combined = json.dumps([research, evaluated])
    assert FINGERPRINT not in combined
    assert "account_fingerprint" not in combined
    assert "equity" not in evaluated
