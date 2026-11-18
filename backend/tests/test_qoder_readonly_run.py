import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ledger.store import SQLiteLedger
from app.qoder_tools import QoderToolService
from app.research.data import MarketHistory, NewsArchive
from scripts.qoder_readonly_run import QoderReadonlyRunner, _sanitize_text

FIXTURES = Path(__file__).parent / "fixtures"


def event(event_id, event_type, **kwargs):
    return SimpleNamespace(id=event_id, type=event_type, **kwargs)


def idle(event_id, reason):
    return event(event_id, "session.status_idle", stop_reason=SimpleNamespace(type=reason))


class FakeEvents:
    def __init__(self, malformed=False, fail_custom_send=False, session_error=False):
        self.pages = {}
        self.sent = []
        self.tool_calls = {}
        self.malformed = malformed
        self.fail_custom_send = fail_custom_send
        self.session_error = session_error

    def send(self, session_id, *, events, workspace_id):
        self.sent.append((session_id, events))
        item = events[0]
        if item["type"] == "user.custom_tool_result":
            if self.fail_custom_send:
                raise TimeoutError("ambiguous delivery")
            call = self.tool_calls[session_id]
            self.pages[session_id].append(
                [
                    call,
                    event(
                        f"{call.id}-message",
                        "agent.message",
                        content=[SimpleNamespace(type="text", text="Tool result reviewed")],
                    ),
                    idle(f"{call.id}-done", "end_turn"),
                ]
            )
            return SimpleNamespace(data=events)

        text = item["content"][0]["text"]
        run_id = re.search(r"qoder-[a-f0-9-]+", text).group(0)
        if "Confirm the run boundary" in text:
            self.pages[session_id].append(
                [
                    event(
                        "coordinator-ready-message",
                        "agent.message",
                        content=[
                            SimpleNamespace(
                                type="text",
                                text=f"READY {run_id}\nBearer should-be-redacted\n1234567890123456",
                            )
                        ],
                    ),
                    idle("coordinator-ready-idle", "end_turn"),
                ]
            )
        elif "Call research_market" in text:
            if self.session_error:
                self.pages[session_id].append(
                    [
                        event(
                            "research-error",
                            "session.error",
                            error=SimpleNamespace(message="provider failed"),
                        )
                    ]
                )
                return SimpleNamespace(data=events)
            payload = {"run_id": run_id, "strategy_version": "momentum-v1"}
            if self.malformed:
                payload["path"] = "../../.env"
            call = event(
                "research-custom-call",
                "agent.custom_tool_use",
                name="research_market",
                input=payload,
            )
            self.tool_calls[session_id] = call
            self.pages[session_id].append([call, idle("research-wait", "requires_action")])
        elif "Independently review" in text:
            self.pages[session_id].append(
                [
                    event(
                        "auditor-no-trade",
                        "agent.message",
                        content=[SimpleNamespace(type="text", text="NO TRADE is supported")],
                    ),
                    idle("auditor-no-trade-idle", "end_turn"),
                ]
            )
        elif "Close the same read-only run" in text:
            self.pages[session_id].append(
                [
                    event(
                        "coordinator-final-message",
                        "agent.message",
                        content=[SimpleNamespace(type="text", text="NO TRADE; historical evidence only")],
                    ),
                    idle("coordinator-final-idle", "end_turn"),
                ]
            )
        return SimpleNamespace(data=events)

    def list(self, session_id, *, after_id=None, **kwargs):
        batches = self.pages[session_id]
        if after_id is None:
            return batches[0] if batches else []
        for index, batch in enumerate(batches):
            for position, item in enumerate(batch):
                if item.id == after_id:
                    remaining = batch[position + 1 :]
                    if remaining:
                        return remaining
                    return batches[index + 1] if index + 1 < len(batches) else []
        return []


class FakeSessions:
    def __init__(self, events):
        self.events = events
        self.created = []

    def create(self, **kwargs):
        session_id = f"session-{kwargs['agent']}"
        self.created.append((session_id, kwargs))
        self.events.pages[session_id] = []
        return SimpleNamespace(id=session_id)


class FakeClient:
    def __init__(self, events):
        self.sessions = FakeSessions(events)


@pytest.fixture
def tools():
    history = MarketHistory.from_file(FIXTURES / "moomoo_daily_bars_2026-11-16.json")
    news = NewsArchive.from_file(FIXTURES / "moomoo_news_2026-11-17.json")
    return QoderToolService(history, news, "private-test-fingerprint")


def make_runner(tmp_path, tools, events, ledger=None):
    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds

    return QoderReadonlyRunner(
        client=FakeClient(events),
        tools=tools,
        workspace_id="workspace-test",
        environment_id="environment-test",
        agent_ids={
            "coordinator": "coordinator-agent",
            "researcher": "researcher-agent",
            "auditor": "auditor-agent",
        },
        output_dir=tmp_path,
        ledger=ledger,
        timeout_seconds=5,
        poll_interval_seconds=0.1,
        sleep=sleep,
        monotonic=lambda: clock[0],
    )


def test_genuine_protocol_shape_no_trade_and_duplicate_event(tmp_path, tools):
    events = FakeEvents()
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    runner = make_runner(tmp_path, tools, events, ledger)
    result = runner.run()
    assert result.status == "COMPLETED"
    assert result.outcome == "NO_TRADE"
    assert result.report_path.exists() and result.json_path.exists()

    created = runner.client.sessions.created
    assert len(created) == 3
    assert all(kwargs["vault_ids"] == [] for _, kwargs in created)
    assert all(kwargs["resources"] == [] for _, kwargs in created)
    assert all("environment_variables" not in kwargs for _, kwargs in created)
    custom_results = [
        item
        for _, sent_events in events.sent
        for item in sent_events
        if item["type"] == "user.custom_tool_result"
    ]
    assert len(custom_results) == 1
    assert custom_results[0]["custom_tool_use_id"] == "research-custom-call"

    artifact = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert set(artifact["session_ids"]) == {"coordinator", "researcher", "auditor"}
    assert artifact["research"]["proposal"] is None
    assert artifact["risk"] is None
    assert artifact["agent_summaries"]["coordinator_final"] == "NO TRADE; historical evidence only"
    report = result.report_path.read_text(encoding="utf-8")
    assert "NO ORDER SUBMITTED" in report
    assert "should-be-redacted" not in report
    assert "1234567890123456" not in report
    assert "private-test-fingerprint" not in report

    ledger_events = ledger.list_events()
    tool_events = [row for row in ledger_events if row["event_type"] == "QODER_TOOL_RESULT"]
    assert len(tool_events) == 1
    assert ledger.submission_count() == 0


def test_sanitize_preserves_decimal_fractions_and_redacts_identifiers():
    text = (
        "score 0.4093679063481789 return -0.0338749070829351173409790804 "
        "account 1234567890123456."
    )
    sanitized = _sanitize_text(text)
    assert "0.4093679063481789" in sanitized
    assert "-0.0338749070829351173409790804" in sanitized
    assert "1234567890123456" not in sanitized
    assert "[REDACTED_NUMBER]" in sanitized


def test_malformed_custom_tool_input_fails_closed(tmp_path, tools):
    events = FakeEvents(malformed=True)
    result = make_runner(tmp_path, tools, events).run()
    assert result.status == "AGENT_ERROR"
    assert result.outcome == "NO_TRADE"
    custom = [item for _, sent in events.sent for item in sent if item["type"] == "user.custom_tool_result"]
    assert len(custom) == 1
    assert custom[0]["is_error"] is True
    artifact = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert "auditor" not in artifact["session_ids"]


def test_session_error_does_not_retry_paid_turn(tmp_path, tools):
    events = FakeEvents(session_error=True)
    result = make_runner(tmp_path, tools, events).run()
    assert result.status == "AGENT_ERROR"
    researcher_messages = [
        item
        for session_id, sent in events.sent
        if session_id == "session-researcher-agent"
        for item in sent
        if item["type"] == "user.message"
    ]
    assert len(researcher_messages) == 1
    assert "provider failed" in result.json_path.read_text(encoding="utf-8")


def test_ambiguous_tool_result_send_is_not_retried(tmp_path, tools):
    events = FakeEvents(fail_custom_send=True)
    result = make_runner(tmp_path, tools, events).run()
    assert result.status == "AGENT_ERROR"
    custom = [item for _, sent in events.sent for item in sent if item["type"] == "user.custom_tool_result"]
    assert len(custom) == 1
    artifact = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert "inspect session history before any retry" in artifact["error"]
