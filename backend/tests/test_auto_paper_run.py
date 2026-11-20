import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.ledger.store import SQLiteLedger
from app.models.contracts import (
    AccountSnapshot,
    OrderRecord,
    OrderRequest,
    OrderSide,
    OrderStatus,
    PolicyDecision,
    Position,
    Quote,
    RiskDecision,
    RuleRejection,
)
from app.research.strategy import STRATEGY_VERSION
from app.service import ExecutionResult, build_client_order_key
from app.supervised import SupervisedExecution
from app.trading_mode import build_auto_paper_activation
from scripts import auto_paper_run
from scripts.auto_paper_run import run_execution

FINGERPRINT = "a" * 64
NOW = datetime(2026, 11, 18, 14, 35, tzinfo=UTC)  # Wednesday 09:35 ET
SESSION = date(2026, 11, 17)  # Tuesday: the prior completed session
PROPOSAL_ID = "spy-directional-risk-v3-2026-11-17-SPY-BUY"
CLIENT_KEY = "mootrade-test-key"
BULLISH_ARTIFACT_SNAPSHOT = {
    "strategy_version": STRATEGY_VERSION,
    "spy_session_date": SESSION.isoformat(),
    "market_state": "STRONG_BULLISH",
    "direction": "BULLISH",
    "target_symbol": "SPY",
    "target_exposure_fraction": "0.40",
    "exposure_tier": "MODERATE",
    "action": "BUY",
}


def _environ(**overrides: str) -> dict[str, str]:
    env = {
        "TRADING_MODE": "AUTO_PAPER",
        "ORDER_WRITES_ENABLED": "true",
        "COMPETITION_ACCOUNT_FINGERPRINT": FINGERPRINT,
    }
    env.update(overrides)
    return env


def _write_bars(path: Path, *, last_session: date = SESSION, bullish: bool = True) -> None:
    dates: list[date] = []
    day = last_session
    while len(dates) < 55:
        if day.weekday() < 5:
            dates.append(day)
        day -= timedelta(days=1)
    dates.reverse()
    rows = []
    for index, session in enumerate(dates):
        close = Decimal("103") if bullish and index >= len(dates) - 10 else Decimal("100")
        rows.append(
            {
                "date": session.strftime("%Y%m%d"),
                "open": str(close),
                "high": str(close),
                "low": str(close),
                "close": str(close),
                "volume": 1_000_000,
            }
        )
    payload = {
        "schema_version": "1",
        "source": {"provider": "test-fixture", "fetched_at_utc": (NOW - timedelta(hours=1)).isoformat()},
        "symbols": {"SPY": rows, "SH": rows, "UPRO": rows, "SPXU": rows},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_duration_exit_reentry_block_uses_serialized_session_dates(tmp_path):
    bars = tmp_path / "bars.json"
    _write_bars(bars)
    history, _ = auto_paper_run._load_bars(bars, NOW, "session")
    sessions = history.session_dates()
    ledger = SQLiteLedger(tmp_path / "audit.db")
    ledger.append_event(
        "LEVERAGED_DURATION_EXIT", NOW, None, "test",
        {"symbol": "UPRO", "session": sessions[-2].isoformat()},
    )
    assert auto_paper_run._leveraged_reentry_blocked_through(
        ledger, history, SESSION.isoformat()
    ) == SESSION.isoformat()


def _write_artifact(path: Path, **overrides: object) -> None:
    artifact = {
        "schema_version": "1",
        "run_id": "qoder-test-run",
        "mode": "CURRENT_MARKET_READ_ONLY",
        "strategy_version": STRATEGY_VERSION,
        "status": "COMPLETED",
        "outcome": "BUY",
        "completed_at_utc": (NOW - timedelta(hours=10)).isoformat(),
        "research": {"ok": True, "snapshot": dict(BULLISH_ARTIFACT_SNAPSHOT)},
    }
    for key, value in overrides.items():
        if key == "snapshot":
            artifact["research"]["snapshot"] = value
        else:
            artifact[key] = value
    path.write_text(json.dumps(artifact), encoding="utf-8")


def _account(
    *,
    now: datetime = NOW,
    reconciled: bool = True,
    fingerprint: str = FINGERPRINT,
    positions: tuple[Position, ...] = (),
    unknown_orders: int = 0,
) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id="test-snapshot",
        account_fingerprint=fingerprint,
        environment="paper",
        equity=Decimal("100000"),
        day_start_equity=Decimal("100000"),
        peak_equity=Decimal("100000"),
        cash=Decimal("100000"),
        buying_power=Decimal("100000"),
        positions=positions,
        as_of_utc=now,
        reconciled=reconciled,
        unknown_orders=unknown_orders,
    )


def _quote(symbol: str = "SPY") -> Quote:
    return Quote(
        symbol=symbol,
        price=Decimal("104.5"),
        as_of_utc=NOW - timedelta(seconds=5),
        regular_session_open=True,
    )


def _request(quantity: int, symbol: str = "SPY", proposal_id: str = PROPOSAL_ID) -> OrderRequest:
    return OrderRequest(
        client_order_key=CLIENT_KEY,
        proposal_id=proposal_id,
        account_snapshot_id="test-snapshot",
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        reference_price=Decimal("104.5"),
    )


def _order(status: OrderStatus) -> OrderRecord:
    return OrderRecord(
        client_order_key=CLIENT_KEY,
        proposal_id=PROPOSAL_ID,
        paper_account_fingerprint=FINGERPRINT,
        broker_order_id="broker-123" if status is not OrderStatus.UNKNOWN else None,
        status=status,
        request=_request(388),
        submitted_at_utc=NOW,
    )


def _decision(
    decision: PolicyDecision, *, approved_quantity: int = 388
) -> RiskDecision:
    return RiskDecision(
        proposal_id=PROPOSAL_ID,
        policy_version="risk-v3",
        decision=decision,
        reasons=()
        if decision is PolicyDecision.APPROVE
        else (RuleRejection(rule_id="R002", message="symbol is not allowed"),),
        approved_quantity=approved_quantity if decision is PolicyDecision.APPROVE else 0,
        account_snapshot_id="test-snapshot",
        expires_at_utc=NOW + timedelta(seconds=30),
    )


class FakeReads:
    def __init__(self, account: AccountSnapshot) -> None:
        self.account = account

    def get_account_snapshot(self) -> AccountSnapshot:
        return self.account


class FakeQuotes:
    def __init__(self, quote: Quote | None = None, error: Exception | None = None) -> None:
        self.quote = quote
        self.error = error

    def get_quote(self, symbol: str, now: datetime) -> Quote:
        if self.error is not None:
            raise self.error
        assert self.quote is not None
        return self.quote


class FakeService:
    def __init__(
        self,
        decision: RiskDecision,
        order: OrderRecord | None,
        reconcile_order: OrderRecord | None = None,
    ) -> None:
        self.decision = decision
        self.order = order
        self.reconcile_order = reconcile_order
        self.execute_calls: list[tuple[object, object]] = []
        self.reconcile_calls: list[str] = []
        self.activation_seen: object | None = None

    def execute(
        self, proposal: object, quote: object, now: datetime, *, autonomous_activation: object = None
    ) -> ExecutionResult:
        self.execute_calls.append((proposal, quote))
        self.activation_seen = autonomous_activation
        return ExecutionResult(self.decision, self.order)

    def reconcile(self, client_order_key: str, now: datetime) -> OrderRecord | None:
        self.reconcile_calls.append(client_order_key)
        return self.reconcile_order


def _stack(
    ledger: SQLiteLedger,
    service: FakeService,
    quotes: FakeQuotes,
    account: AccountSnapshot,
    *,
    writes: bool = True,
) -> SupervisedExecution:
    return SupervisedExecution(
        service=service,
        quote_feed=quotes,
        broker=None,
        reads=FakeReads(account),
        ledger=ledger,
        risk_gate=None,
        order_writes_enabled=writes,
    )


def _harness(
    tmp_path: Path,
    *,
    service: FakeService | None = None,
    account: AccountSnapshot | None = None,
    quote: Quote | None = None,
    writes: bool = True,
    bullish: bool = True,
    artifact_overrides: dict[str, object] | None = None,
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, dict[str, object], SQLiteLedger, FakeService]:
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars, bullish=bullish)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    _write_artifact(artifact_dir / "qoder-test-run.json", **(artifact_overrides or {}))
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    activation = build_auto_paper_activation(FINGERPRINT, NOW - timedelta(days=1))
    ledger.record_trading_activation(activation)
    service = service or FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(
        ledger,
        service,
        FakeQuotes(quote or _quote()),
        account or _account(),
        writes=writes,
    )
    exit_code, report = run_execution(
        now=NOW,
        environ=_environ(**(env_overrides or {})),
        bars_path=bars,
        artifact_dir=artifact_dir,
        output_dir=tmp_path / "reports",
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    return exit_code, report, ledger, service


@pytest.mark.parametrize("version", ["risk-v1", "risk-v2"])
def test_activation_block_rejects_supplied_non_v3_pin(version):
    activation = build_auto_paper_activation(FINGERPRINT, NOW).model_copy(
        update={"risk_policy_version": version}
    )
    assert auto_paper_run._auto_paper_block(_environ(), activation, FINGERPRINT) == (
        f"activation pin binds unsupported risk policy {version}"
    )


@pytest.mark.parametrize("historical_version", [None, "risk-v1", "risk-v2"])
def test_abstains_without_executable_activation_pin(tmp_path, historical_version):
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    _write_artifact(artifact_dir / "qoder-test-run.json")
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    if historical_version is not None:
        with ledger._connect() as connection:
            connection.execute(
                """
                INSERT INTO trading_activations (
                    activation_id, activated_at_utc, activated_by, account_fingerprint,
                    strategy_version, allowed_symbols_json, risk_policy_version,
                    max_single_exposure, max_total_exposure, position_fraction,
                    max_daily_drawdown, paper_only, order_writes_enabled, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("historical-pin", NOW.isoformat(), "owner", FINGERPRINT,
                 STRATEGY_VERSION, '["SPY", "SH"]', historical_version,
                 "0.10", "0.30", "0.05", "0.02", 1, 1, "1"),
            )
    service = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(ledger, service, FakeQuotes(_quote()), _account())
    exit_code, report = run_execution(
        now=NOW,
        environ=_environ(),
        bars_path=bars,
        artifact_dir=artifact_dir,
        output_dir=tmp_path / "reports",
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert report["status"] == "ABSTAINED"
    assert "no AUTO_PAPER activation pin" in report["reason"]
    assert report["submission_performed"] is False
    assert service.execute_calls == []
    assert ledger.list_events() == []
    with ledger._connect() as connection:
        rows = connection.execute("SELECT risk_policy_version FROM trading_activations").fetchall()
        assert [row["risk_policy_version"] for row in rows] == (
            [historical_version] if historical_version else []
        )


def test_abstains_when_the_activation_pin_has_expired(tmp_path):
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    _write_artifact(artifact_dir / "qoder-test-run.json")
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    ledger.record_trading_activation(
        build_auto_paper_activation(
            FINGERPRINT, NOW - timedelta(days=2), expires_at_utc=NOW - timedelta(days=1)
        )
    )
    service = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(ledger, service, FakeQuotes(_quote()), _account())
    exit_code, report = run_execution(
        now=NOW,
        environ=_environ(),
        bars_path=bars,
        artifact_dir=artifact_dir,
        output_dir=tmp_path / "reports",
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert report["status"] == "ABSTAINED"
    assert "has expired" in report["reason"]
    assert service.execute_calls == []


def test_abstains_in_read_only_mode(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path, env_overrides={"TRADING_MODE": "READ_ONLY"}
    )
    assert exit_code == 1
    assert report["status"] == "ABSTAINED"
    assert "TRADING_MODE=READ_ONLY" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_order_writes_disabled(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path, env_overrides={"ORDER_WRITES_ENABLED": "false"}
    )
    assert exit_code == 1
    assert "ORDER_WRITES_ENABLED is not true" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_stack_lacks_writes(tmp_path):
    exit_code, report, _ledger, service = _harness(tmp_path, writes=False)
    assert exit_code == 1
    assert "without order writes" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_kill_switch_engaged(tmp_path):
    exit_code, report, ledger, service = _harness(tmp_path)
    assert exit_code == 0  # first run proceeded; engage the switch afterwards
    ledger.set_kill_switch(True)
    bars = tmp_path / "daily-bars.json"
    artifact_dir = tmp_path / "artifacts"
    service2 = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(ledger, service2, FakeQuotes(_quote()), _account())
    exit_code, report = run_execution(
        now=NOW,
        environ=_environ(),
        bars_path=bars,
        artifact_dir=artifact_dir,
        output_dir=tmp_path / "reports",
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert report["status"] == "ABSTAINED"
    assert "kill switch" in report["reason"]
    assert service2.execute_calls == []


def test_abstains_on_unknown_submission(tmp_path):
    exit_code, _report, ledger, _service = _harness(tmp_path)
    assert exit_code == 0
    ledger.reserve_submission(_request(1))
    ledger.record_order(_order(OrderStatus.UNKNOWN))
    bars = tmp_path / "daily-bars.json"
    artifact_dir = tmp_path / "artifacts"
    service2 = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(ledger, service2, FakeQuotes(_quote()), _account())
    exit_code, report = run_execution(
        now=NOW,
        environ=_environ(),
        bars_path=bars,
        artifact_dir=artifact_dir,
        output_dir=tmp_path / "reports",
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert "UNKNOWN submission" in report["reason"]
    assert service2.execute_calls == []


def test_abstains_when_decision_artifact_missing(tmp_path):
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars)
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    ledger.record_trading_activation(
        build_auto_paper_activation(FINGERPRINT, NOW - timedelta(days=1))
    )
    service = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(ledger, service, FakeQuotes(_quote()), _account())
    exit_code, report = run_execution(
        now=NOW,
        environ=_environ(),
        bars_path=bars,
        artifact_dir=empty_dir,
        output_dir=tmp_path / "reports",
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert "no COMPLETED" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_artifact_run_failed(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path, artifact_overrides={"status": "AGENT_ERROR"}
    )
    assert exit_code == 1
    assert "no COMPLETED" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_artifact_covers_another_session(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path,
        artifact_overrides={
            "snapshot": {**BULLISH_ARTIFACT_SNAPSHOT, "spy_session_date": "2026-11-16"}
        },
    )
    assert exit_code == 1
    assert "no COMPLETED" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_artifact_signal_disagrees_with_recomputed_signal(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path,
        artifact_overrides={
            "snapshot": {**BULLISH_ARTIFACT_SNAPSHOT, "target_symbol": "SH", "direction": "BEARISH"}
        },
    )
    assert exit_code == 1
    assert "does not match the recomputed" in report["reason"]
    assert service.execute_calls == []


@pytest.mark.parametrize("field", ["target_exposure_fraction", "exposure_tier"])
@pytest.mark.parametrize("missing", [True, False])
def test_abstains_when_artifact_omits_or_changes_v3_exposure(field, missing, tmp_path):
    snapshot = dict(BULLISH_ARTIFACT_SNAPSHOT)
    if missing:
        del snapshot[field]
    else:
        snapshot[field] = "0.05" if field == "target_exposure_fraction" else "WEAK"
    exit_code, report, ledger, service = _harness(
        tmp_path, artifact_overrides={"snapshot": snapshot}
    )
    assert exit_code == 1
    assert report["submission_performed"] is False
    assert field in report["reason"]
    assert "does not match the recomputed" in report["reason"]
    assert service.execute_calls == []
    assert ledger.list_events() == []


def test_neutral_signal_records_cash_without_submission(tmp_path):
    exit_code, report, ledger, service = _harness(
        tmp_path,
        bullish=False,
        artifact_overrides={
            "snapshot": {
                "strategy_version": STRATEGY_VERSION,
                "spy_session_date": SESSION.isoformat(),
                "market_state": "NEUTRAL",
                "direction": None,
                "target_symbol": None,
                "target_exposure_fraction": "0",
                "exposure_tier": "NEUTRAL",
                "action": "CASH",
            }
        },
    )
    assert exit_code == 0
    assert report["status"] == "COMPLETED"
    assert report["outcome"] == "CASH"
    assert report["submission_performed"] is False
    assert service.execute_calls == []
    events = ledger.list_events()
    assert any(item["event_type"] == "AUTO_PAPER_DECISION" for item in events)
    assert not any(item["event_type"] == "AUTO_PAPER_EXECUTION_RUN" for item in events)


def test_bullish_signal_submits_buy_and_reconciles(tmp_path):
    exit_code, report, ledger, service = _harness(
        tmp_path,
        service=FakeService(
            _decision(PolicyDecision.APPROVE),
            _order(OrderStatus.ACKNOWLEDGED),
            reconcile_order=_order(OrderStatus.FILLED),
        ),
    )
    assert exit_code == 0
    assert report["status"] == "COMPLETED"
    assert report["submission_performed"] is True
    assert report["symbol"] == "SPY"
    assert report["requested_quantity"] == 388  # 0.40 trend-confirmed MODERATE tier
    assert report["policy_version"] == "risk-v3"
    assert report["target_exposure_fraction"] == "0.40"
    assert report["exposure_tier"] == "MODERATE"
    assert report["order"]["status"] == "FILLED"
    assert report["reconciled"] is True
    assert len(service.execute_calls) == 1
    proposal, quote = service.execute_calls[0]
    assert proposal.symbol == "SPY"
    assert proposal.action.value == "BUY"
    assert proposal.requested_quantity == 388
    assert quote.symbol == "SPY"
    assert service.activation_seen is not None
    assert service.activation_seen.risk_policy_version == "risk-v3"
    assert service.activation_seen.account_fingerprint == FINGERPRINT
    assert len(service.reconcile_calls) == 1
    assert service.reconcile_calls[0].startswith("mootrade-")
    events = ledger.list_events()
    assert any(item["event_type"] == "AUTO_PAPER_DECISION" for item in events)
    assert any(item["event_type"] == "AUTO_PAPER_EXECUTION_RUN" for item in events)


def test_holding_the_target_records_hold_without_submission(tmp_path):
    exit_code, report, ledger, service = _harness(
        tmp_path,
        account=_account(
            positions=(Position(symbol="SPY", quantity=388, market_value=Decimal("40000")),)
        ),
    )
    assert exit_code == 0
    assert report["outcome"] == "HOLD"
    assert report["submission_performed"] is False
    assert service.execute_calls == []
    assert any(
        item["event_type"] == "AUTO_PAPER_DECISION" and item["payload_redacted_json"]["action"] == "HOLD"
        for item in ledger.list_events()
    )


def test_above_cap_holding_is_trimmed_to_the_competition_cap(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path,
        account=_account(
            positions=(Position(symbol="SPY", quantity=574, market_value=Decimal("60000")),)
        ),
    )
    assert exit_code == 0
    assert report["submission_performed"] is True
    assert report["symbol"] == "SPY"
    assert report["requested_quantity"] == 186  # 574 held − 388 tier target
    proposal, _quote = service.execute_calls[0]
    assert proposal.action.value == "SELL"
    assert proposal.requested_quantity == 186


def test_opposite_holding_sells_first(tmp_path):
    exit_code, report, ledger, service = _harness(
        tmp_path,
        service=FakeService(
            RiskDecision(
                proposal_id="spy-directional-risk-v3-2026-11-17-SH-SELL",
                policy_version="risk-v3",
                decision=PolicyDecision.APPROVE,
                reasons=(),
                approved_quantity=100,
                account_snapshot_id="test-snapshot",
                expires_at_utc=NOW + timedelta(seconds=30),
            ),
            OrderRecord(
                client_order_key=CLIENT_KEY,
                proposal_id="spy-directional-risk-v3-2026-11-17-SH-SELL",
                paper_account_fingerprint=FINGERPRINT,
                broker_order_id="broker-456",
                status=OrderStatus.ACKNOWLEDGED,
                request=OrderRequest(
                    client_order_key=CLIENT_KEY,
                    proposal_id="spy-directional-risk-v3-2026-11-17-SH-SELL",
                    account_snapshot_id="test-snapshot",
                    symbol="SH",
                    side=OrderSide.SELL,
                    quantity=100,
                    reference_price=Decimal("104.5"),
                ),
                submitted_at_utc=NOW,
            ),
        ),
        account=_account(
            positions=(Position(symbol="SH", quantity=100, market_value=Decimal("2100")),)
        ),
        quote=_quote("SH"),
    )
    assert exit_code == 0
    assert report["symbol"] == "SH"
    assert report["submission_performed"] is True
    proposal, quote = service.execute_calls[0]
    assert proposal.action.value == "SELL"
    assert proposal.requested_quantity == 100
    assert quote.symbol == "SH"
    events = ledger.list_events()
    assert any(
        item["event_type"] == "AUTO_PAPER_DECISION"
        and item["payload_redacted_json"]["action"] == "SELL"
        for item in events
    )


def test_risk_gate_rejection_abstains(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path, service=FakeService(_decision(PolicyDecision.REJECT), None)
    )
    assert exit_code == 1
    assert report["status"] == "ABSTAINED"
    assert report["outcome"] == "POLICY_REJECTED"
    assert report["submission_performed"] is False
    assert report["policy_rules"][0]["rule_id"] == "R002"
    assert len(service.execute_calls) == 1


def test_duplicate_proposal_abstains(tmp_path):
    exit_code, _report, ledger, _service = _harness(tmp_path)
    assert exit_code == 0
    ledger.reserve_submission(_request(388))
    bars = tmp_path / "daily-bars.json"
    artifact_dir = tmp_path / "artifacts"
    service2 = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(ledger, service2, FakeQuotes(_quote()), _account())
    exit_code, report = run_execution(
        now=NOW,
        environ=_environ(),
        bars_path=bars,
        artifact_dir=artifact_dir,
        output_dir=tmp_path / "reports",
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert "already submitted" in report["reason"]
    assert service2.execute_calls == []


def test_unknown_outcome_exits_three_and_never_retries(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path, service=FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.UNKNOWN))
    )
    assert exit_code == 3
    assert report["status"] == "UNKNOWN"
    assert report["outcome"] == "ORDER_UNKNOWN"
    assert report["submission_performed"] is True
    assert len(service.execute_calls) == 1
    assert len(service.reconcile_calls) == 1


def test_abstains_when_quote_is_unavailable(tmp_path):
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    _write_artifact(artifact_dir / "qoder-test-run.json")
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    ledger.record_trading_activation(
        build_auto_paper_activation(FINGERPRINT, NOW - timedelta(days=1))
    )
    service = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(
        ledger,
        service,
        FakeQuotes(error=RuntimeError("market closed")),
        _account(),
    )
    exit_code, report = run_execution(
        now=NOW,
        environ=_environ(),
        bars_path=bars,
        artifact_dir=artifact_dir,
        output_dir=tmp_path / "reports",
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert "no fresh regular-session quote" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_account_is_stale(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path, account=_account(now=NOW - timedelta(seconds=120))
    )
    assert exit_code == 1
    assert "not fresh" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_account_is_unreconciled(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path, account=_account(reconciled=False)
    )
    assert exit_code == 1
    assert "not reconciled" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_account_fingerprint_mismatches(tmp_path):
    exit_code, report, _ledger, service = _harness(
        tmp_path, account=_account(fingerprint="b" * 64)
    )
    assert exit_code == 1
    assert "fingerprint" in report["reason"]
    assert service.execute_calls == []


def test_abstains_when_bars_do_not_end_at_prior_session(tmp_path):
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars, last_session=date(2026, 11, 16))
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    _write_artifact(artifact_dir / "qoder-test-run.json")
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    ledger.record_trading_activation(
        build_auto_paper_activation(FINGERPRINT, NOW - timedelta(days=1))
    )
    service = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(ledger, service, FakeQuotes(_quote()), _account())
    exit_code, report = run_execution(
        now=NOW,
        environ=_environ(),
        bars_path=bars,
        artifact_dir=artifact_dir,
        output_dir=tmp_path / "reports",
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert "bar validation failed" in report["reason"]
    assert service.execute_calls == []


# --- Supervised decision phase (Mode A) ---


def _supervised_environ(**overrides: str) -> dict[str, str]:
    env = {
        "TRADING_MODE": "SUPERVISED_PAPER",
        "ORDER_WRITES_ENABLED": "false",
        "COMPETITION_ACCOUNT_FINGERPRINT": FINGERPRINT,
    }
    env.update(overrides)
    return env


def _supervised_harness(
    tmp_path: Path,
    *,
    service: FakeService | None = None,
    account: AccountSnapshot | None = None,
    writes: bool = False,
    bullish: bool = True,
    artifact_overrides: dict[str, object] | None = None,
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, dict[str, object], SQLiteLedger, FakeService]:
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars, bullish=bullish)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    _write_artifact(artifact_dir / "qoder-test-run.json", **(artifact_overrides or {}))
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    service = service or FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(
        ledger,
        service,
        FakeQuotes(_quote()),
        account or _account(),
        writes=writes,
    )
    exit_code, report = auto_paper_run.run_supervised_decision(
        now=NOW,
        environ=_supervised_environ(**(env_overrides or {})),
        bars_path=bars,
        artifact_dir=artifact_dir,
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    return exit_code, report, ledger, service


def test_supervised_decision_records_buy_proposal_without_submission(tmp_path):
    exit_code, report, ledger, service = _supervised_harness(tmp_path)

    assert exit_code == 0
    assert report["mode"] == "SUPERVISED_DECISION"
    assert report["status"] == "COMPLETED"
    assert report["submission_performed"] is False
    assert report["order_writes_enabled"] is False
    assert report["approval_required"] is True
    assert report["outcome"] == "BUY"
    proposal = report["proposal"]
    assert proposal["symbol"] == "SPY"
    assert proposal["requested_quantity"] > 0
    assert proposal["client_order_key"] == build_client_order_key(
        STRATEGY_VERSION, PROPOSAL_ID
    )
    assert "approval" in proposal["approval_note"]
    assert service.execute_calls == []
    events = ledger.list_events()
    decision_events = [
        item for item in events if item["event_type"] == "AUTO_PAPER_DECISION"
    ]
    assert len(decision_events) == 1
    assert decision_events[0]["source"] == "supervised_scheduler"


def test_supervised_decision_records_cash_without_approval(tmp_path):
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars, bullish=False)
    history, _validation = auto_paper_run._load_bars(bars, NOW, "session")
    snapshot = auto_paper_run.screen(
        history,
        NOW,
        STRATEGY_VERSION,
        exposure_policy=auto_paper_run.exposure_policy_for_activation(None),
    )
    artifact_snapshot = {
        "strategy_version": STRATEGY_VERSION,
        "spy_session_date": SESSION.isoformat(),
        "market_state": snapshot.market_state,
        "direction": snapshot.direction,
        "target_symbol": snapshot.target_symbol,
        "target_exposure_fraction": str(snapshot.target_exposure_fraction),
        "exposure_tier": snapshot.exposure_tier,
        "action": snapshot.action,
    }
    exit_code, report, ledger, service = _supervised_harness(
        tmp_path, bullish=False, artifact_overrides={"snapshot": artifact_snapshot}
    )

    assert exit_code == 0
    assert report["outcome"] == "CASH"
    assert report["approval_required"] is False
    assert "proposal" not in report
    assert service.execute_calls == []
    events = ledger.list_events()
    decision_events = [
        item for item in events if item["event_type"] == "AUTO_PAPER_DECISION"
    ]
    assert len(decision_events) == 1
    assert decision_events[0]["payload_redacted_json"]["action"] == "CASH"


def test_supervised_decision_abstains_on_unknown_submission(tmp_path):
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    ledger.reserve_submission(_request(1))
    ledger.record_order(_order(OrderStatus.UNKNOWN))
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars)
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    _write_artifact(artifact_dir / "qoder-test-run.json")
    service = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(ledger, service, FakeQuotes(_quote()), _account(), writes=False)
    exit_code, report = auto_paper_run.run_supervised_decision(
        now=NOW,
        environ=_supervised_environ(),
        bars_path=bars,
        artifact_dir=artifact_dir,
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert "UNKNOWN submission" in report["reason"]
    assert report["submission_performed"] is False
    assert service.execute_calls == []


def test_supervised_decision_abstains_on_stale_account(tmp_path):
    stale = _account(now=NOW - timedelta(minutes=5))
    exit_code, report, _ledger, service = _supervised_harness(tmp_path, account=stale)

    assert exit_code == 1
    assert "not fresh" in report["reason"]
    assert service.execute_calls == []


def test_supervised_decision_abstains_on_unreconciled_account(tmp_path):
    unreconciled = _account(reconciled=False)
    exit_code, report, _ledger, service = _supervised_harness(
        tmp_path, account=unreconciled
    )

    assert exit_code == 1
    assert "not reconciled" in report["reason"]
    assert service.execute_calls == []


def test_supervised_decision_abstains_when_artifact_missing(tmp_path):
    bars = tmp_path / "daily-bars.json"
    _write_bars(bars)
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    service = FakeService(_decision(PolicyDecision.APPROVE), _order(OrderStatus.ACKNOWLEDGED))
    stack = _stack(ledger, service, FakeQuotes(_quote()), _account(), writes=False)
    empty_artifacts = tmp_path / "empty-artifacts"
    empty_artifacts.mkdir()
    exit_code, report = auto_paper_run.run_supervised_decision(
        now=NOW,
        environ=_supervised_environ(),
        bars_path=bars,
        artifact_dir=empty_artifacts,
        ledger=ledger,
        stack=stack,
        fingerprint=FINGERPRINT,
    )
    assert exit_code == 1
    assert "no COMPLETED" in report["reason"]
    assert service.execute_calls == []


def test_supervised_decision_abstains_when_stack_has_writes(tmp_path):
    exit_code, report, _ledger, service = _supervised_harness(tmp_path, writes=True)

    assert exit_code == 1
    assert "without order writes" in report["reason"]
    assert service.execute_calls == []


def test_supervised_decision_refuses_non_supervised_modes(tmp_path):
    exit_code, report, _ledger, service = _supervised_harness(
        tmp_path, env_overrides={"TRADING_MODE": "READ_ONLY"}
    )

    assert exit_code == 1
    assert "requires SUPERVISED_PAPER" in report["reason"]
    assert service.execute_calls == []
