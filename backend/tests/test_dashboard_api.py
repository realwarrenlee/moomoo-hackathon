import json
import shutil
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from app.broker.moomoo_quotes import QuoteFeedError, QuoteObservation
from app.broker.moomoo_rest import RestAccountIdentity, RestOrder
from app.dashboard.api import create_app
from app.dashboard.data import DashboardAuthRequired, DashboardPaths, DashboardService
from app.ledger.store import SQLiteLedger
from app.models.contracts import AccountSnapshot, OrderSide, Position, TradingActivation
from app.trading_mode import build_auto_paper_activation

NOW = datetime(2026, 11, 17, 15, 0, tzinfo=UTC)
TOKEN = "test-dashboard-token"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeIdentity:
    masked_id = "****0101"
    market_id = 100
    account_type = 2
    title = "Moomoo x Qoder AI Paper Trading Agent Challenge"


class FakeBroker:
    def __init__(self) -> None:
        self.fail = False

    def account_identity(self) -> RestAccountIdentity:
        if self.fail:
            raise DashboardAuthRequired("no auth")
        return RestAccountIdentity(
            masked_id="****0101",
            market_id=100,
            account_type=2,
            title="Moomoo x Qoder AI Paper Trading Agent Challenge",
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        if self.fail:
            raise DashboardAuthRequired("no auth")
        return AccountSnapshot(
            snapshot_id="snap-1",
            account_fingerprint="f" * 64,
            environment="paper",
            equity=Decimal("100000"),
            day_start_equity=Decimal("100000"),
            peak_equity=Decimal("100000"),
            cash=Decimal("100000"),
            buying_power=Decimal("100000"),
            positions=(Position(symbol="SPY", quantity=2, market_value=Decimal("1479.90")),),
            as_of_utc=NOW,
            reconciled=True,
        )

    def get_today_orders(self) -> tuple[RestOrder, ...]:
        if self.fail:
            raise DashboardAuthRequired("no auth")
        return (
            RestOrder(
                broker_order_id="ord-1",
                symbol="SPY",
                side=OrderSide.BUY,
                status_code=4,
                status_label="FILLED",
                quantity=2,
                filled_quantity=2,
                price=Decimal("739.95"),
                average_fill_price=Decimal("739.95"),
                created_at_utc=NOW - timedelta(minutes=10),
                updated_at_utc=NOW - timedelta(minutes=9),
                order_type=3,
                time_in_force=1,
                trading_session=1,
                remark="MTP1-" + "a" * 64,
            ),
        )

    def get_order_history(self, *, max_pages: int = 10) -> tuple[RestOrder, ...]:
        if self.fail:
            raise DashboardAuthRequired("no auth")
        return self.get_today_orders()


class FakeQuotes:
    def __init__(self, *, stale: bool = False, fail_symbol: str | None = None) -> None:
        self.stale = stale
        self.fail_symbol = fail_symbol

    def observe_quote(self, symbol: str, now: datetime) -> QuoteObservation:
        if symbol == self.fail_symbol:
            raise QuoteFeedError("unavailable")
        age = 5000 if self.stale else 40
        return QuoteObservation(
            symbol=symbol,
            price=Decimal("739.95"),
            as_of_utc=now - timedelta(seconds=age),
            age_seconds=age,
            sec_status="NORMAL",
            suspended=False,
            market_state="PRE_MARKET_BEGIN",
            regular_session_open=False,
        )


class FakeSource:
    def __init__(self, ledger: SQLiteLedger, *, stale: bool = False) -> None:
        self._ledger = ledger
        self.broker_obj = FakeBroker()
        self.quote_obj = FakeQuotes(stale=stale)

    @property
    def ledger(self) -> SQLiteLedger:
        return self._ledger

    def broker(self) -> FakeBroker:
        return self.broker_obj

    def quotes(self) -> FakeQuotes:
        return self.quote_obj

    def auth_state(self) -> dict:
        return {
            "authorization": "PRESENT",
            "reason": None,
            "trade_write_granted": False,
            "account_lock_configured": True,
            "expires_at_utc": NOW.isoformat(),
        }


def build_client(
    tmp_path: Path, *, stale: bool = False, evidence_dir: Path | None = None
) -> tuple[TestClient, SQLiteLedger]:
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    ledger.append_event("QODER_RUN_STARTED", NOW, "run-1", "qoder_readonly_runner", {"strategy_version": "spy-directional"})
    paths = DashboardPaths(
        project_root=PROJECT_ROOT,
        evidence_dir=evidence_dir or PROJECT_ROOT / "evidence",
        database_path=tmp_path / "ledger.db",
    )
    service = DashboardService(FakeSource(ledger, stale=stale), paths, clock=lambda: NOW)
    app = create_app(service, dashboard_token=TOKEN, token_required=True)
    return TestClient(app), ledger


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


def test_dashboard_routes_are_get_only(tmp_path: Path) -> None:
    client, _ = build_client(tmp_path)
    app = client.app
    paths = {route.path for route in app.routes if route.path.startswith("/api/v1/")}
    assert paths == {
        "/api/v1/health",
        "/api/v1/overview",
        "/api/v1/portfolio",
        "/api/v1/risk",
        "/api/v1/agents",
        "/api/v1/analytics",
        "/api/v1/audit",
    }
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if methods:
            assert methods <= {"GET", "HEAD", "OPTIONS"}
    assert client.post("/api/v1/overview", headers=headers()).status_code == 405
    assert client.delete("/api/v1/audit", headers=headers()).status_code == 405


def test_dashboard_requires_token(tmp_path: Path) -> None:
    client, _ = build_client(tmp_path)
    response = client.get("/api/v1/health")
    assert response.status_code == 401
    assert response.json() == {"detail": "Dashboard authentication failed"}


def test_overview_exposes_real_data_without_identity_secrets(tmp_path: Path) -> None:
    client, _ = build_client(tmp_path)
    response = client.get("/api/v1/overview", headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "PAPER"
    assert body["read_only"] is True
    assert body["account"]["masked_id"] == "****0101"
    assert body["account"]["equity"] == "100000"
    assert body["safety"]["order_writes_enabled"] is False
    assert body["safety"]["broker_order_endpoint_available"] is False
    serialized = response.text
    assert "f" * 64 not in serialized
    assert "acc" + "ess_token" not in serialized
    assert "trade:write" not in serialized


def test_trading_mode_is_reported_from_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "SUPERVISED_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "false")
    client, _ = build_client(tmp_path)
    health = client.get("/api/v1/health", headers=headers()).json()
    assert health["trading_mode"] == "SUPERVISED_PAPER"
    assert health["order_writes_enabled"] is False
    overview = client.get("/api/v1/overview", headers=headers()).json()
    assert overview["safety"]["trading_mode"] == "SUPERVISED_PAPER"
    assert overview["safety"]["order_writes_enabled"] is False


def test_historical_auto_pin_does_not_enable_reported_order_writes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "AUTO_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "false")
    client, ledger = build_client(tmp_path)
    ledger.record_trading_activation(build_auto_paper_activation("f" * 64, NOW))
    overview = client.get("/api/v1/overview", headers=headers()).json()
    assert overview["safety"]["trading_mode"] == "AUTO_PAPER"
    assert overview["safety"]["order_writes_enabled"] is False
    health = client.get("/api/v1/health", headers=headers()).json()
    assert health["trading_mode"] == "AUTO_PAPER"
    assert health["order_writes_enabled"] is False


def test_stale_quotes_are_labelled_and_risk_is_locked(tmp_path: Path) -> None:
    client, _ = build_client(tmp_path, stale=True)
    overview = client.get("/api/v1/overview", headers=headers()).json()
    assert overview["state"] == "STALE"
    assert any("300-second" in warning for warning in overview["warnings"])
    assert all(quote["stale"] for quote in overview["quotes"])
    assert all(quote["fresh"] is False for quote in overview["quotes"])

    risk = client.get("/api/v1/risk", headers=headers()).json()
    assert risk["state"] == "LOCKED"
    assert risk["execution_locked"] is True
    assert "ORDER_WRITES_ENABLED=false" in risk["lock_reasons"]
    assert risk["last_real_preflight"]["submission_performed"] is False
    assert risk["last_real_preflight"]["scope_trade_write"] is False


def _activation(**overrides):
    fields = dict(
        activated_at_utc=NOW,
        activated_by="owner",
        account_fingerprint="f" * 64,
        strategy_version="spy-directional",
        allowed_symbols=("SPY", "SH"),
        risk_policy_version="risk-v3",
        min_effective_exposure_fraction=Decimal("0.10"),
        max_effective_exposure_fraction=Decimal("0.40"),
        max_daily_drawdown=Decimal("0.02"),
    )
    fields.update(overrides)
    return TradingActivation(**fields)


def test_risk_limits_default_to_v3_without_implying_activation(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("TRADING_MODE", "SUPERVISED_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "false")
    client, ledger = build_client(tmp_path)
    response = client.get("/api/v1/risk", headers=headers())
    assert response.status_code == 200
    risk = response.json()
    assert risk["policy_version"] == "risk-v3"
    assert risk["limits"] == {
        "min_effective_exposure_pct": 10.0,  # Strategy floor; supervised path skips R016.
        "max_effective_exposure_pct": 40.0,
        "max_leverage": 1.0,  # Policy ceiling, not current leverage permission.
        "max_open_positions": 1,
        "max_daily_drawdown_pct": 2.0,
        "max_quote_age_seconds": 300,
        "max_account_age_seconds": 60,
        "buying_power_buffer_usd": 5.0,
    }
    assert risk["allowed_symbols"] == ["SPY", "SH"]
    assert risk["execution_locked"] is True
    assert risk["controls"]["trading_mode"] == "SUPERVISED_PAPER"
    assert risk["controls"]["order_writes_enabled"] is False
    assert "No risk-v3 activation is pinned." not in risk["lock_reasons"]
    assert any("EVERY supervised BUY and SELL" in reason for reason in risk["lock_reasons"])
    assert risk["activation"] is None
    assert ledger.latest_trading_activation() is None


def test_historical_pin_cannot_expand_supervised_execution_scope(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "SUPERVISED_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "false")
    client, ledger = build_client(tmp_path)
    activation = _activation()
    ledger.record_trading_activation(activation)
    risk = client.get("/api/v1/risk", headers=headers()).json()
    assert risk["policy_version"] == "risk-v3"
    limits = risk["limits"]
    assert limits["min_effective_exposure_pct"] == 10.0
    assert limits["max_effective_exposure_pct"] == 40.0
    assert limits["max_leverage"] == 1.0
    assert limits["max_open_positions"] == 1
    assert limits["max_daily_drawdown_pct"] == 2.0
    assert "max_single_exposure_pct" not in limits
    assert "max_total_exposure_pct" not in limits
    assert risk["allowed_symbols"] == ["SPY", "SH"]
    assert risk["execution_locked"] is True
    assert risk["controls"]["order_writes_enabled"] is False
    assert risk["controls"]["broker_order_endpoint_available"] is False
    assert risk["activation"]["status"] == "ACTIVE"
    assert risk["activation"]["policy_version"] == "risk-v3"
    assert risk["activation"]["allowed_symbols"] == ["SPY", "SH"]
    assert any(
        "authorises the scheduled autonomous executor" in warning
        and "read-only and never submits" in warning
        for warning in risk["warnings"]
    )
    assert ledger.latest_trading_activation() == activation
    assert ledger.submission_count() == 0


def test_expired_activation_pin_grants_no_execution_authority(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "SUPERVISED_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "false")
    client, ledger = build_client(tmp_path)
    ledger.record_trading_activation(
        _activation(
            activated_at_utc=NOW - timedelta(hours=2),
            expires_at_utc=NOW - timedelta(hours=1),
        )
    )
    risk = client.get("/api/v1/risk", headers=headers()).json()
    assert risk["activation"]["status"] == "EXPIRED"
    assert risk["execution_locked"] is True
    assert any(
        "expired" in warning and "grants no execution authority" in warning
        for warning in risk["warnings"]
    )


def test_historical_pin_cannot_override_current_policy_limits(tmp_path: Path) -> None:
    client, ledger = build_client(tmp_path)
    ledger.record_trading_activation(
        _activation(
            allowed_symbols=("SPY", "SH"),
            min_effective_exposure_fraction=Decimal("0.25"),
            max_effective_exposure_fraction=Decimal("1.20"),
            max_daily_drawdown=Decimal("0.015"),
        )
    )
    risk = client.get("/api/v1/risk", headers=headers()).json()
    assert risk["policy_version"] == "risk-v3"
    assert risk["limits"]["min_effective_exposure_pct"] == 10.0
    assert risk["limits"]["max_effective_exposure_pct"] == 40.0
    assert risk["limits"]["max_daily_drawdown_pct"] == 2.0
    assert risk["allowed_symbols"] == ["SPY", "SH"]
    assert {quote["symbol"] for quote in risk["quotes"]} == {"SPY", "SH"}


def test_prior_approval_does_not_remove_every_order_approval_requirement(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "SUPERVISED_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "false")
    client, ledger = build_client(tmp_path)
    ledger.approve_first_order("prior-key", "prior-proposal", NOW, "owner")
    risk = client.get("/api/v1/risk", headers=headers()).json()
    assert risk["controls"]["first_order_approval_count"] == 1
    assert risk["execution_locked"] is True
    assert any(
        "EVERY supervised BUY and SELL" in reason and "exact proposal and client order key" in reason
        for reason in risk["lock_reasons"]
    )
    assert not any("first-order" in reason for reason in risk["lock_reasons"])
    assert ledger.order_approval_count() == 1
    assert ledger.submission_count() == 0


def test_risk_api_schema_exposes_only_v3_limits(tmp_path: Path) -> None:
    client, _ = build_client(tmp_path)
    schemas = client.get("/api/openapi.json", headers=headers()).json()["components"]["schemas"]
    properties = schemas["RiskLimits"]["properties"]
    assert "max_single_exposure_pct" not in properties
    assert "max_total_exposure_pct" not in properties
    assert {"min_effective_exposure_pct", "max_effective_exposure_pct", "max_leverage"} <= set(
        schemas["RiskLimits"]["required"]
    )
    assert schemas["RiskResponse"]["properties"]["policy_version"]["const"] == "risk-v3"


def test_historical_v1_audit_rules_remain_readable(tmp_path: Path) -> None:
    client, ledger = build_client(tmp_path)
    ledger.append_event(
        "POLICY_REJECTED", NOW, "historical-run", "risk_gate",
        {
            "policy_version": "risk-v1",
            "decision": "REJECT",
            "reasons": [{"rule_id": "R004"}, {"rule_id": "R005"}],
        },
    )
    before = ledger.list_events()
    audit = client.get("/api/v1/audit", headers=headers()).json()
    event = next(event for event in audit["events"] if event["run_id"] == "historical-run")
    assert event["summary"] == "Risk decision REJECT; rules R004, R005."
    assert event["provenance"] == "LOCAL_LEDGER"
    assert ledger.list_events() == before
    assert ledger.latest_trading_activation() is None


def test_portfolio_and_audit_return_broker_and_ledger_data(tmp_path: Path) -> None:
    client, ledger = build_client(tmp_path)
    portfolio = client.get("/api/v1/portfolio", headers=headers()).json()
    assert portfolio["state"] == "LIVE"
    assert portfolio["account"]["masked_id"] == "****0101"
    assert portfolio["positions"][0]["symbol"] == "SPY"
    assert portfolio["today_orders"][0]["status"] == "FILLED"
    assert portfolio["history_orders"][0]["remark"].startswith("MTP1-")

    audit = client.get("/api/v1/audit", headers=headers()).json()
    assert audit["state"] == "LIVE"
    assert audit["counts"]["submissions"] == 0
    assert audit["events"][0]["event_type"] == "QODER_RUN_STARTED"
    assert "payload" not in audit["events"][0]
    assert ledger.submission_count() == 0


def test_agents_are_labelled_historical(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    (evidence / "qoder").mkdir(parents=True)
    historical = [
        path
        for path in (PROJECT_ROOT / "evidence" / "qoder").glob("qoder-*.json")
        if json.loads(path.read_text(encoding="utf-8")).get("mode") == "HISTORICAL_DRY_RUN"
    ]
    assert historical, "historical Qoder artifact fixture missing"
    shutil.copy(historical[0], evidence / "qoder" / historical[0].name)
    client, _ = build_client(tmp_path, evidence_dir=evidence)
    agents = client.get("/api/v1/agents", headers=headers()).json()
    assert agents["state"] == "HISTORICAL"
    assert agents["runs"][0]["mode"] == "HISTORICAL_DRY_RUN"
    assert agents["runs"][0]["provenance"] == "HISTORICAL_QODER_RUN"
    assert "Not current market data" in agents["notice"]


def _write_daily_bars(evidence: Path) -> None:
    folder = evidence / "current-market" / "2026-11-19"
    folder.mkdir(parents=True)
    bars = {
        "schema_version": "1",
        "source": {"provider": "fixture", "last_completed_session": "20261119"},
        "symbols": {
            "SPY": [
                {"date": "20261117", "close": 600.0},
                {"date": "20261118", "close": 606.0},
                {"date": "20261119", "close": 603.0},
            ]
        },
    }
    (folder / "daily-bars.json").write_text(json.dumps(bars), encoding="utf-8")


def test_analytics_shows_competition_period_without_paper_equity(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    _write_daily_bars(evidence)
    client, _ = build_client(tmp_path, evidence_dir=evidence)
    analytics = client.get("/api/v1/analytics", headers=headers()).json()
    assert analytics["state"] == "EMPTY"
    assert analytics["paper_account_performance"]["available"] is False
    assert len(analytics["datasets"]) == 1
    dataset = analytics["datasets"][0]
    assert dataset["id"] == "competition-period"
    assert dataset["label"] == "Competition period"
    assert dataset["period"] == {"start": "2026-11-17", "end": "2026-11-30"}
    assert dataset["axis_dates"] == [
        "2026-11-17",
        "2026-11-18",
        "2026-11-19",
        "2026-11-20",
        "2026-11-23",
        "2026-11-24",
        "2026-11-25",
        "2026-11-27",
        "2026-11-30",
    ]
    assert dataset["provenance"] == "CURRENT_MARKET_READ_ONLY"
    labels = {curve["label"] for curve in dataset["curves"]}
    assert labels == {"SPY", "Cash"}
    spy = next(curve for curve in dataset["curves"] if curve["key"] == "spy")
    assert [point["date"] for point in spy["points"]] == [
        "2026-11-17",
        "2026-11-18",
        "2026-11-19",
    ]
    assert spy["points"][0]["value"] == 100.0
    assert spy["points"][-1]["value"] == 100.5
    cash = next(curve for curve in dataset["curves"] if curve["key"] == "cash")
    assert all(point["value"] == 100.0 for point in cash["points"])
    spy_metric = next(metric for metric in dataset["metrics"] if metric["strategy"] == "spy")
    assert spy_metric["provenance"] == "CURRENT_MARKET_READ_ONLY"
    assert spy_metric["period"] == "2026-11-17 to 2026-11-30"
    assert spy_metric["total_return_pct"] == 0.5
    cash_metric = next(metric for metric in dataset["metrics"] if metric["strategy"] == "cash")
    assert cash_metric["total_return_pct"] == 0.0
    assert cash_metric["max_drawdown_pct"] == 0.0


def test_analytics_reports_ledger_equity_within_competition_period(tmp_path: Path) -> None:
    client, ledger = build_client(tmp_path)
    ledger.observe_equity("f" * 64, Decimal("100000"), NOW)
    ledger.observe_equity("f" * 64, Decimal("99991.02"), NOW + timedelta(days=1))
    analytics = client.get("/api/v1/analytics", headers=headers()).json()
    assert analytics["state"] == "LIVE"
    assert analytics["paper_account_performance"]["available"] is True
    dataset = analytics["datasets"][0]
    assert dataset["provenance"] == "LIVE_BROKER_READ"
    labels = {curve["label"] for curve in dataset["curves"]}
    assert labels == {"Paper account", "SPY", "Cash"}
    paper = next(curve for curve in dataset["curves"] if curve["key"] == "paper_account")
    assert [point["date"] for point in paper["points"]] == ["2026-11-17", "2026-11-18"]
    assert paper["points"][0]["value"] == 100.0
    assert abs(paper["points"][1]["value"] - 99.991) < 0.001
    paper_metric = next(
        metric for metric in dataset["metrics"] if metric["strategy"] == "paper_account"
    )
    assert paper_metric["provenance"] == "LIVE_BROKER_READ"
    assert paper_metric["total_return_pct"] == round((99991.02 / 100000 - 1) * 100, 4)
    assert paper_metric["annualized_volatility_pct"] is None


def _write_current_agent_artifact(tmp_path: Path, *, account: object) -> None:
    folder = tmp_path / "evidence" / "qoder"
    folder.mkdir(parents=True)
    payload = {
        "run_id": "current-run-1",
        "mode": "CURRENT_MARKET_READ_ONLY",
        "strategy_version": "spy-directional",
        "status": "COMPLETED",
        "outcome": "REJECT",
        "completed_at_utc": NOW.isoformat(),
        "session_ids": {"coordinator_ready": "s1", "researcher": "s2", "auditor": "s3", "coordinator_final": "s4"},
        "agent_summaries": {"researcher": "Proposal recorded.", "auditor": "Deterministic gate rejects."},
        "research": {
            "snapshot": {
                "decision_time_utc": NOW.isoformat(),
                "data_as_of_utc": NOW.isoformat(),
                "spy_session_date": "2026-11-17",
                "spy_close": "732.44",
                "spy_return_10d": "-0.0290",
                "spy_sma50": "762.89",
                "spy_trend_pct": "-0.0399",
                "spy_volatility_20d": "0.2306",
                "market_state": "BEARISH",
                "direction": "BEARISH",
                "target_symbol": "SH",
                "target_effective_exposure": "-1",
                "current_symbol": None,
                "current_quantity": 0,
                "action": "BUY",
                "reentry_symbol": None,
                "decision_reason": "SPY 10-session return and trend are bearish; target inverse exposure.",
                "selected_symbol": "SH",
                "no_trade_reason": None,
                "candidates": [
                    {
                        "symbol": "SH",
                        "direction": -1,
                        "leverage": "1",
                        "effective_exposure": "-1",
                        "close": "18.42",
                        "eligible": True,
                        "selected": True,
                        "reasons": [],
                    }
                ],
            },
            "proposal": {
                "proposal_id": "spy-directional-2026-11-17-SH-BUY",
                "symbol": "SH",
                "action": "BUY",
                "requested_quantity": 6,
                "thesis": "Bearish SPY signal targets inverse exposure.",
                "invalidation": "Exit after a neutral or bullish signal.",
            },
        },
        "risk": {
            "risk_decision": {
                "policy_version": "risk-v1",
                "decision": "REJECT",
                "approved_quantity": 0,
                "reasons": [
                    {"rule_id": "R010", "message": "Order writes are disabled by control state"},
                    {"rule_id": "R014", "message": "First paper order requires explicit owner approval"},
                ],
            }
        },
        "data_collection": {
            "collected_at_utc": NOW.isoformat(),
            "us_eastern_time": "2026-11-17T10:00:00-05:00",
            "quotes": [
                {
                    "symbol": "SPY",
                    "price": "739.95",
                    "data_time_utc": NOW.isoformat(),
                    "age_seconds": 12.5,
                    "market_state": "AFTERNOON",
                }
            ],
            "account": account,
            "account_fingerprint": "f" * 64,
            "validations": {"regular_session_required": True},
        },
    }
    (folder / "qoder-current-run-1.json").write_text(json.dumps(payload), encoding="utf-8")


def _current_agents_client(tmp_path: Path) -> TestClient:
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    paths = DashboardPaths(
        project_root=PROJECT_ROOT,
        evidence_dir=tmp_path / "evidence",
        database_path=tmp_path / "ledger.db",
    )
    service = DashboardService(FakeSource(ledger), paths, clock=lambda: NOW)
    return TestClient(create_app(service, dashboard_token=TOKEN, token_required=True))


def test_current_agent_run_is_labelled_and_sanitized(tmp_path: Path) -> None:
    _write_current_agent_artifact(
        tmp_path,
        account={
            "masked_id": "****0101",
            "as_of_utc": NOW.isoformat(),
            "age_seconds": 8.0,
            "account_fingerprint": "f" * 64,
        },
    )
    client = _current_agents_client(tmp_path)
    response = client.get("/api/v1/agents", headers=headers())
    assert response.status_code == 200
    agents = response.json()
    run = agents["runs"][0]
    assert agents["state"] == "LIVE"
    assert run["provenance"] == "CURRENT_MARKET_READ_ONLY"
    assert run["strategy_version"] == "spy-directional"
    assert run["spy_session_date"] == "2026-11-17"
    assert run["market_state"] == "BEARISH"
    assert run["direction"] == "BEARISH"
    assert run["target_symbol"] == "SH"
    assert run["selected_symbol"] == "SH"
    assert run["action"] == "BUY"
    assert run["proposal"]["symbol"] == "SH"
    assert run["proposal"]["action"] == "BUY"
    assert run["risk_decision"]["decision"] == "REJECT"
    assert run["risk_decision"]["policy_version"] == "risk-v1"  # Recorded evidence, not current policy.
    assert {reason["rule_id"] for reason in run["risk_decision"]["reasons"]} == {"R010", "R014"}
    assert run["candidates"][0]["symbol"] == "SH"
    assert run["candidates"][0]["direction"] == -1
    assert run["candidates"][0]["leverage"] == "1"
    assert run["candidates"][0]["effective_exposure"] == "-1"
    assert run["data_collection"]["collected_at_utc"] == NOW.isoformat()
    assert run["data_collection"]["account_as_of_utc"] == NOW.isoformat()
    assert run["data_collection"]["account_age_seconds"] == 8.0
    assert run["data_collection"]["regular_session_required"] is True
    assert run["data_collection"]["quotes"][0]["market_state"] == "AFTERNOON"
    assert "No order was submitted" in agents["notice"]
    serialized = response.text
    assert "f" * 64 not in serialized
    assert "****0101" not in serialized
    assert "account_fingerprint" not in serialized


def test_current_agent_run_tolerates_missing_account_snapshot(tmp_path: Path) -> None:
    _write_current_agent_artifact(tmp_path, account=None)
    client = _current_agents_client(tmp_path)
    response = client.get("/api/v1/agents", headers=headers())
    assert response.status_code == 200
    run = response.json()["runs"][0]
    assert run["data_collection"]["account_as_of_utc"] is None
    assert run["data_collection"]["account_age_seconds"] is None
    assert run["provenance"] == "CURRENT_MARKET_READ_ONLY"


def test_unavailable_broker_returns_explicit_state(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    source = FakeSource(ledger)
    source.broker_obj.fail = True
    source.quote_obj.fail_symbol = "SPY"
    paths = DashboardPaths(
        project_root=PROJECT_ROOT,
        evidence_dir=PROJECT_ROOT / "evidence",
        database_path=tmp_path / "ledger.db",
    )
    service = DashboardService(source, paths, clock=lambda: NOW)
    client = TestClient(create_app(service, dashboard_token=TOKEN, token_required=True))
    overview = client.get("/api/v1/overview", headers=headers()).json()
    assert overview["state"] == "UNAVAILABLE"
    assert overview["account"] is None
    assert "Moomoo read authorization is unavailable." in overview["warnings"]
    assert overview["quotes"][0]["state"] == "UNAVAILABLE"
    assert "no auth" not in str(overview)

    portfolio = client.get("/api/v1/portfolio", headers=headers()).json()
    assert portfolio["state"] == "UNAVAILABLE"
    assert portfolio["account"] is None
    assert portfolio["reason"] == "Moomoo read authorization is unavailable."
