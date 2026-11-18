from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from app.ledger.store import SQLiteLedger
from app.qoder_tools import QoderToolService, StrategyVersion
from app.research.data import MarketHistory
from app.research.strategy import STRATEGY_VERSION

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "backend" / "tests" / "fixtures"


class QoderRunError(RuntimeError):
    pass


@dataclass
class TurnResult:
    message: str
    tool_results: list[dict[str, object]] = field(default_factory=list)


@dataclass
class RunResult:
    status: str
    outcome: str
    run_id: str
    report_path: Path
    json_path: Path


class QoderReadonlyRunner:
    def __init__(
        self,
        client: Any,
        tools: QoderToolService,
        workspace_id: str,
        environment_id: str,
        agent_ids: dict[str, str],
        output_dir: str | Path,
        ledger: SQLiteLedger | None = None,
        timeout_seconds: float = 240,
        poll_interval_seconds: float = 1,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        mode: str = "HISTORICAL_DRY_RUN",
        notice: str | None = None,
        data_collection: dict[str, object] | None = None,
    ) -> None:
        if set(agent_ids) != {"coordinator", "researcher", "auditor"}:
            raise ValueError("exactly three logical agent IDs are required")
        self.client = client
        self.tools = tools
        self.workspace_id = workspace_id
        self.environment_id = environment_id
        self.agent_ids = agent_ids
        self.output_dir = Path(output_dir)
        self.ledger = ledger
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.sleep = sleep
        self.monotonic = monotonic
        self.mode = mode
        self.notice = notice
        self.data_collection = data_collection
        self._cursors: dict[str, str | None] = {}
        self._seen_events: dict[str, set[str]] = {}

    def run(
        self,
        strategy_version: StrategyVersion = STRATEGY_VERSION,
        decision_time_utc: datetime | None = None,
    ) -> RunResult:
        run_id = self.tools.create_run(strategy_version, decision_time_utc)
        sessions: dict[str, str] = {}
        artifact: dict[str, object] = {
            "schema_version": "1",
            "run_id": run_id,
            "mode": self.mode,
            "strategy_version": strategy_version,
            "status": "AGENT_ERROR",
            "outcome": "NO_TRADE",
            "session_ids": sessions,
            "notice": self.notice
            or (
                "Historical evidence only. No current broker snapshot, owner approval or order submission."
                if self.mode == "HISTORICAL_DRY_RUN"
                else "Current read-only market evidence only. No owner approval or order submission."
            ),
        }
        if self.data_collection is not None:
            artifact["data_collection"] = self.data_collection
        if decision_time_utc is not None:
            artifact["decision_time_utc"] = decision_time_utc.isoformat()
        self._record("QODER_RUN_STARTED", run_id, {"strategy_version": strategy_version, "mode": self.mode})
        try:
            sessions["coordinator"] = self._create_session("coordinator", run_id)
            ready = self._run_turn(
                sessions["coordinator"],
                f"Read-only {self.mode} run {run_id}. Strategy allowlist: {STRATEGY_VERSION}. "
                f"Selected strategy: {strategy_version}. Confirm the run boundary without tools. "
                f"Reply READY {run_id} and state the mode {self.mode}; never discuss or place an order.",
                run_id=run_id,
            )
            if "READY" not in ready.message or run_id not in ready.message:
                raise QoderRunError("Coordinator did not validate the run boundary")

            sessions["researcher"] = self._create_session("researcher", run_id)
            research_turn = self._run_turn(
                sessions["researcher"],
                f"Call research_market exactly once with run_id {run_id} and strategy_version "
                f"{strategy_version}. Then use only the tool result to summarize SPY trend, "
                "momentum, volatility, the target ETF or CASH, the current holding and the "
                "action. Preserve HOLD, CASH and NO_TRADE. Never invent market or account data.",
                run_id=run_id,
                expected_tool="research_market",
            )
            research = _only_tool_result(research_turn, "research_market")
            if not research.get("ok"):
                raise QoderRunError("Research tool rejected the request; abstain")

            sessions["auditor"] = self._create_session("auditor", run_id)
            proposal = research.get("proposal")
            risk: dict[str, object] | None = None
            if proposal is None:
                auditor_turn = self._run_turn(
                    sessions["auditor"],
                    "Independently review this sanitized " + self.mode + " SPY research artifact: "
                    + json.dumps(research, separators=(",", ":"))
                    + ". The deterministic action is not an order proposal, so do not call evaluate_proposal. "
                    "Challenge the thesis with contradictory evidence, volatility, leverage, drawdown, "
                    "concentration and invalidation risk. Confirm the action or identify a concrete evidence "
                    "inconsistency. Never create a proposal.",
                    run_id=run_id,
                )
                outcome = "NO_TRADE"
            else:
                auditor_turn = self._run_turn(
                    sessions["auditor"],
                    f"Independently audit run {run_id}. Call evaluate_proposal exactly once with this "
                    "run_id and the unmodified proposal: "
                    + json.dumps(proposal, separators=(",", ":"))
                    + ". Then state the strongest counterargument, downside and invalidation risk. "
                    "Report the deterministic decision and rule IDs; prose cannot override them.",
                    run_id=run_id,
                    expected_tool="evaluate_proposal",
                )
                risk = _only_tool_result(auditor_turn, "evaluate_proposal")
                if not risk.get("ok"):
                    raise QoderRunError("Risk tool rejected the request; abstain")
                decision = risk["risk_decision"]["decision"]  # type: ignore[index]
                outcome = "POLICY_APPROVAL" if decision == "APPROVE" else "POLICY_REJECTED"
            if proposal is None:
                outcome = str(research["snapshot"].get("action", "NO_TRADE"))  # type: ignore[index]

            summary_input = {
                "market_state": research["snapshot"].get("market_state"),  # type: ignore[index]
                "direction": research["snapshot"].get("direction"),  # type: ignore[index]
                "spy_close": research["snapshot"].get("spy_close"),  # type: ignore[index]
                "spy_return_10d": research["snapshot"].get("spy_return_10d"),  # type: ignore[index]
                "spy_sma50": research["snapshot"].get("spy_sma50"),  # type: ignore[index]
                "spy_volatility_20d": research["snapshot"].get("spy_volatility_20d"),  # type: ignore[index]
                "target_symbol": research["snapshot"].get("target_symbol"),  # type: ignore[index]
                "current_symbol": research["snapshot"].get("current_symbol"),  # type: ignore[index]
                "action": research["snapshot"].get("action"),  # type: ignore[index]
                "no_trade_reason": research["snapshot"]["no_trade_reason"],  # type: ignore[index]
                "proposal": proposal,
                "risk_decision": risk.get("risk_decision") if risk else None,
                "auditor_summary": auditor_turn.message,
                "outcome": outcome,
            }
            coordinator_summary = self._run_turn(
                sessions["coordinator"],
                f"Close the same read-only run {run_id} using only this sanitized deterministic artifact: "
                + json.dumps(summary_input, separators=(",", ":"))
                + ". Summarize the outcome and limitations. Do not claim a broker fill, current approval "
                "or live account state, and do not call tools.",
                run_id=run_id,
            )
            artifact.update(
                status="COMPLETED",
                outcome=outcome,
                research=research,
                risk=risk,
                agent_summaries={
                    "coordinator_ready": ready.message,
                    "researcher": research_turn.message,
                    "auditor": auditor_turn.message,
                    "coordinator_final": coordinator_summary.message,
                },
            )
            self._record(
                "QODER_RUN_COMPLETED",
                run_id,
                {"outcome": outcome, "session_ids": dict(sessions), "mode": self.mode},
            )
        except Exception as exc:
            artifact["error"] = _sanitize_text(str(exc) or exc.__class__.__name__)
            self._record("AGENT_ERROR", run_id, {"error": artifact["error"]})
        artifact["completed_at_utc"] = datetime.now(UTC).isoformat()
        json_path, report_path = self._persist(artifact)
        return RunResult(
            status=str(artifact["status"]),
            outcome=str(artifact["outcome"]),
            run_id=run_id,
            report_path=report_path,
            json_path=json_path,
        )

    def _create_session(self, role: str, run_id: str) -> str:
        session = self.client.sessions.create(
            agent=self.agent_ids[role],
            environment_id=self.environment_id,
            workspace_id=self.workspace_id,
            title=f"MooTrade {role} {run_id}",
            resources=[],
            vault_ids=[],
            metadata={"mootrade_mode": self.mode, "mootrade_run_id": run_id},
        )
        if not session.id:
            raise QoderRunError(f"{role} session creation returned no session ID")
        return session.id

    def _run_turn(
        self,
        session_id: str,
        message: str,
        run_id: str,
        expected_tool: str | None = None,
    ) -> TurnResult:
        self.client.sessions.events.send(
            session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": message}]}],
            workspace_id=self.workspace_id,
        )
        deadline = self.monotonic() + self.timeout_seconds
        cursor = self._cursors.get(session_id)
        seen = self._seen_events.setdefault(session_id, set())
        messages: list[str] = []
        tool_results: list[dict[str, object]] = []
        while self.monotonic() <= deadline:
            page = self.client.sessions.events.list(
                session_id,
                after_id=cursor,
                order="asc",
                limit=100,
                workspace_id=self.workspace_id,
            )
            for event in page:
                event_id = event.id
                if event_id:
                    if event_id in seen:
                        continue
                    seen.add(event_id)
                    cursor = event_id
                    self._cursors[session_id] = cursor
                event_type = event.type
                if event_type == "agent.message":
                    text = _message_text(event.content)
                    if text:
                        messages.append(_sanitize_text(text))
                elif event_type == "agent.custom_tool_use":
                    if not event_id:
                        raise QoderRunError("Custom tool call has no event ID; abstain")
                    unexpected = expected_tool is None or event.name != expected_tool or bool(tool_results)
                    if unexpected:
                        result: dict[str, object] = {
                            "ok": False,
                            "error": {"code": "unsupported_tool", "message": "Unexpected custom tool call"},
                        }
                    else:
                        result = self.tools.dispatch(str(event.name), event.input)
                    self._send_tool_result(session_id, event_id, result)
                    tool_results.append(result)
                    self._record(
                        "QODER_TOOL_RESULT",
                        run_id,
                        {"session_id": session_id, "tool_name": str(event.name), "result": result},
                        correlation_id=event_id,
                    )
                    if unexpected:
                        raise QoderRunError("Unexpected custom tool call; abstain")
                elif event_type == "session.error":
                    detail = getattr(event.error, "message", None) or "Cloud Agent session error"
                    raise QoderRunError(_sanitize_text(str(detail)))
                elif event_type == "session.status_idle":
                    reason = event.stop_reason
                    kind = getattr(reason, "type", reason)
                    if kind == "requires_action":
                        continue
                    if kind != "end_turn":
                        raise QoderRunError(f"Cloud Agent turn stopped with {kind or 'unknown'}")
                    if expected_tool is not None and not tool_results:
                        raise QoderRunError(f"{expected_tool} was not called; abstain")
                    return TurnResult("\n".join(messages), tool_results)
            self.sleep(self.poll_interval_seconds)
        raise QoderRunError("Cloud Agent turn deadline exceeded; inspect session state before retrying")

    def _send_tool_result(self, session_id: str, event_id: str, result: dict[str, object]) -> None:
        try:
            self.client.sessions.events.send(
                session_id,
                events=[
                    {
                        "type": "user.custom_tool_result",
                        "custom_tool_use_id": event_id,
                        "is_error": not bool(result.get("ok")),
                        "content": [
                            {"type": "text", "text": json.dumps(result, separators=(",", ":"))}
                        ],
                    }
                ],
                workspace_id=self.workspace_id,
            )
        except Exception as exc:
            raise QoderRunError(
                "Custom tool result delivery is ambiguous; inspect session history before any retry"
            ) from exc

    def _record(
        self,
        event_type: str,
        run_id: str,
        payload: dict[str, object],
        correlation_id: str | None = None,
    ) -> None:
        if self.ledger is not None:
            self.ledger.append_event(
                event_type=event_type,
                occurred_at_utc=datetime.now(UTC),
                run_id=run_id,
                source="qoder_readonly_runner",
                payload=payload,
                correlation_id=correlation_id,
            )

    def _persist(self, artifact: dict[str, object]) -> tuple[Path, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        run_id = str(artifact["run_id"])
        json_path = self.output_dir / f"{run_id}.json"
        report_path = self.output_dir / f"{run_id}.md"
        json_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
        report_path.write_text(_markdown_report(artifact), encoding="utf-8")
        return json_path, report_path


def _only_tool_result(turn: TurnResult, tool_name: str) -> dict[str, object]:
    if len(turn.tool_results) != 1:
        raise QoderRunError(f"Expected exactly one {tool_name} result")
    return turn.tool_results[0]


def _message_text(content: object) -> str:
    if not isinstance(content, Iterable) or isinstance(content, (str, bytes, dict)):
        return ""
    texts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if isinstance(text, str):
            texts.append(text)
    return "\n".join(texts)


def _sanitize_text(value: str) -> str:
    value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]+", "Bearer [REDACTED]", value)
    value = re.sub(
        r"(?i)(access_token|refresh_token|client_secret|api_key)=([^\s&]+)",
        r"\1=[REDACTED]",
        value,
    )
    value = re.sub(r"(?<![\d.])\d{12,}(?!\d|\.\d)", "[REDACTED_NUMBER]", value)
    return value[:4000]


def _markdown_report(artifact: dict[str, object]) -> str:
    sessions = artifact.get("session_ids", {})
    research = artifact.get("research")
    risk = artifact.get("risk")
    summaries = artifact.get("agent_summaries", {})
    mode = str(artifact.get("mode", "HISTORICAL_DRY_RUN"))
    current = mode == "CURRENT_MARKET_READ_ONLY"
    lines = [
        "# Qoder read-only decision report",
        "",
        "**PAPER / READ-ONLY — NO ORDER SUBMITTED OR APPROVED**",
        "",
        f"- Run ID: `{artifact['run_id']}`",
        f"- Mode: `{mode}`",
        f"- Status: `{artifact['status']}`",
        f"- Outcome: `{artifact['outcome']}`",
        f"- Strategy: `{artifact['strategy_version']}`",
        (
            "- Evidence: current read-only Moomoo REST quotes/account plus a completed daily-bar snapshot."
            if current
            else "- Evidence: pinned timestamped Moomoo historical fixtures, not a current broker snapshot."
        ),
        "- Authority: deterministic Python research and `RiskGate`; agent prose is non-authoritative.",
        "",
        "## Genuine Cloud Agent sessions",
        "",
    ]
    for role, session_id in sessions.items():  # type: ignore[union-attr]
        lines.append(f"- {role}: `{session_id}`")
    lines.extend(["", "## Deterministic artifacts", ""])
    if artifact.get("data_collection") is not None:
        lines.extend(
            [
                "### Data collection",
                "",
                "```json",
                json.dumps(artifact["data_collection"], indent=2),
                "```",
                "",
            ]
        )
    if research is not None:
        lines.extend(["### Research", "", "```json", json.dumps(research, indent=2), "```", ""])
    if risk is not None:
        lines.extend(["### Risk", "", "```json", json.dumps(risk, indent=2), "```", ""])
    if artifact.get("error"):
        lines.extend(["## Error / abstention", "", str(artifact["error"]), ""])
    if summaries:
        lines.extend(["## Sanitized agent summaries", ""])
        for role, summary in summaries.items():  # type: ignore[union-attr]
            lines.extend([f"### {role}", "", str(summary), ""])
    lines.extend(
        [
            "## Limitations",
            "",
            (
                "A current read-only policy evaluation is not owner authorization. It does not "
                "submit, approve or fill an order. Supervised paper execution remains blocked by "
                "disabled writes, outstanding first-order approval and unverified account-exclusive "
                "trade:write scope."
                if current
                else "A historical policy approval is not owner authorization. Fresh trusted quote, "
                "account, position and order data, exact competition-account verification, durable "
                "idempotency and explicit first-order approval remain mandatory before any broker write."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _load_local_qoder_credentials() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"QODER_ACCESS_TOKEN", "QODER_PAT"} and value.strip():
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the read-only three-agent Qoder workflow")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--coordinator-agent-id", required=True)
    parser.add_argument("--researcher-agent-id", required=True)
    parser.add_argument("--auditor-agent-id", required=True)
    parser.add_argument("--strategy", choices=[STRATEGY_VERSION], default=STRATEGY_VERSION)
    parser.add_argument(
        "--decision-time",
        help="Optional ISO-8601 UTC decision cutoff for a pinned historical session (demo/evidence only)",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence" / "qoder")
    args = parser.parse_args()
    decision_time = None
    if args.decision_time:
        decision_time = datetime.fromisoformat(args.decision_time.replace("Z", "+00:00"))
        if decision_time.tzinfo is None:
            parser.error("--decision-time must include a UTC offset")

    _load_local_qoder_credentials()
    import httpx
    from qca import Managed

    history = MarketHistory.from_file(FIXTURES / "moomoo_directional_etf_bars_2026-11-17.json")
    runner = QoderReadonlyRunner(
        client=Managed(
            http_client=httpx.Client(follow_redirects=False, trust_env=False),
            max_retries=0,
        ),
        tools=QoderToolService(history),
        workspace_id=args.workspace_id,
        environment_id=args.environment_id,
        agent_ids={
            "coordinator": args.coordinator_agent_id,
            "researcher": args.researcher_agent_id,
            "auditor": args.auditor_agent_id,
        },
        output_dir=args.output_dir,
        ledger=SQLiteLedger(ROOT / "data" / "mootrade.db"),
    )
    result = runner.run(args.strategy, decision_time)
    print(f"Run ID: {result.run_id}")
    print(f"Status: {result.status}; outcome: {result.outcome}")
    print(f"Report: {result.report_path}")
    return 0 if result.status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
