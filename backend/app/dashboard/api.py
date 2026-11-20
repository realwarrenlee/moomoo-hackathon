"""Typed, read-only FastAPI surface for the MooTrade dashboard."""

from __future__ import annotations

import hmac
import os
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.dashboard.data import (
    DashboardPaths,
    DashboardService,
    LiveDashboardSource,
)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountView(ApiModel):
    masked_id: str
    title: str | None = None
    market_id: int | None = None
    account_type: int | None = None
    verified: bool | None = None
    equity: str | None = None
    cash: str | None = None
    buying_power: str | None = None
    day_start_equity: str | None = None
    peak_equity: str | None = None
    positions_count: int | None = None
    open_orders_count: int | None = None
    reconciled: bool | None = None
    unknown_orders: int | None = None
    gross_exposure_pct: float | None = None
    effective_exposure_pct: float | None = None
    as_of_utc: str | None = None
    age_seconds: float | None = None
    provenance: str = "LIVE_BROKER_READ"


class QuoteView(ApiModel):
    symbol: str
    state: str
    price: str | None = None
    as_of_utc: str | None = None
    age_seconds: float | None = None
    fresh: bool | None = None
    stale: bool | None = None
    sec_status: str | None = None
    suspended: bool | None = None
    market_state: str | None = None
    regular_session_open: bool | None = None
    error: str | None = None
    provenance: str = "LIVE_BROKER_READ"


class SafetyView(ApiModel):
    trading_mode: str
    order_writes_enabled: bool
    kill_switch_engaged: bool
    first_order_approval_count: int
    submission_count: int
    unknown_submissions: bool
    broker_order_endpoint_available: bool
    provenance: str


class AgentSummary(ApiModel):
    role: str
    text: str


class AgentCandidate(ApiModel):
    symbol: str | None = None
    direction: int | None = None
    leverage: str | None = None
    effective_exposure: str | None = None
    close: str | None = None
    eligible: bool | None = None
    selected: bool | None = None
    reasons: list[str] = Field(default_factory=list)


class AgentProposal(ApiModel):
    proposal_id: str | None = None
    symbol: str | None = None
    action: str | None = None
    requested_quantity: int | None = None
    thesis: str | None = None
    invalidation: str | None = None


class AgentRiskReason(ApiModel):
    rule_id: str | None = None
    message: str | None = None


class AgentRiskDecision(ApiModel):
    policy_version: str | None = None
    decision: str | None = None
    approved_quantity: int | None = None
    reasons: list[AgentRiskReason] = Field(default_factory=list)


class AgentDataCollectionQuote(ApiModel):
    symbol: str | None = None
    data_time_utc: str | None = None
    age_seconds: float | None = None
    market_state: str | None = None


class AgentDataCollection(ApiModel):
    collected_at_utc: str | None = None
    us_eastern_time: str | None = None
    quotes: list[AgentDataCollectionQuote] = Field(default_factory=list)
    account_as_of_utc: str | None = None
    account_age_seconds: float | None = None
    regular_session_required: bool | None = None


class AgentRun(ApiModel):
    run_id: str | None = None
    mode: str
    strategy_version: str | None = None
    status: str | None = None
    outcome: str | None = None
    notice: str | None = None
    completed_at_utc: str | None = None
    session_count: int
    decision_time_utc: str | None = None
    data_as_of_utc: str | None = None
    spy_session_date: str | None = None
    spy_close: str | None = None
    spy_return_10d: str | None = None
    spy_sma50: str | None = None
    spy_trend_pct: str | None = None
    spy_volatility_20d: str | None = None
    market_state: str | None = None
    direction: str | None = None
    target_symbol: str | None = None
    target_effective_exposure: str | None = None
    current_symbol: str | None = None
    current_quantity: int | None = None
    action: str | None = None
    reentry_symbol: str | None = None
    decision_reason: str | None = None
    selected_symbol: str | None = None
    proposal: AgentProposal | None = None
    risk_decision: AgentRiskDecision | None = None
    no_trade_reason: str | None = None
    candidates: list[AgentCandidate] = Field(default_factory=list)
    summaries: list[AgentSummary] = Field(default_factory=list)
    data_collection: AgentDataCollection | None = None
    provenance: str


class OverviewResponse(ApiModel):
    state: str
    generated_at_utc: str
    mode: str
    read_only: bool
    account: AccountView | None
    quotes: list[QuoteView]
    safety: SafetyView
    latest_agent_run: AgentRun | None
    warnings: list[str]


class PortfolioAccount(ApiModel):
    masked_id: str
    equity: str
    cash: str
    buying_power: str
    positions_count: int
    open_orders_count: int
    reconciled: bool
    unknown_orders: int
    as_of_utc: str | None
    age_seconds: float | None = None
    provenance: str


class PositionView(ApiModel):
    symbol: str
    quantity: int
    market_value: str
    provenance: str


class OpenOrderView(ApiModel):
    symbol: str
    side: str
    remaining_quantity: int
    reference_price: str
    provenance: str


class OrderView(ApiModel):
    broker_order_id: str
    symbol: str
    side: str
    status: str
    quantity: int
    filled_quantity: int
    price: str
    average_fill_price: str
    created_at_utc: str | None
    updated_at_utc: str | None
    remark: str
    provenance: str


class PortfolioResponse(ApiModel):
    state: str
    generated_at_utc: str
    mode: str
    read_only: bool
    reason: str | None = None
    account: PortfolioAccount | None
    positions: list[PositionView]
    open_orders: list[OpenOrderView]
    today_orders: list[OrderView]
    history_orders: list[OrderView]
    warnings: list[str]


class PreflightQuote(ApiModel):
    symbol: str
    last_price: float | None = None
    data_time_utc: str | None = None
    age_seconds: float | None = None
    sec_status: str | None = None
    suspension: bool | None = None
    market_state: str | None = None


class PreflightView(ApiModel):
    kind: str | None = None
    mode: str | None = None
    checked_at_utc: str | None = None
    decision: str | None = None
    rejection_rule_ids: list[str]
    reasons: list[str]
    submission_performed: bool | None = None
    order_endpoint_contacted: bool | None = None
    scope_trade_write: bool | None = None
    quotes: list[PreflightQuote]
    provenance: str


class RiskLimits(ApiModel):
    min_effective_exposure_pct: float
    max_effective_exposure_pct: float
    max_leverage: float
    max_open_positions: int
    max_daily_drawdown_pct: float
    max_quote_age_seconds: int
    max_account_age_seconds: int
    buying_power_buffer_usd: float


class ActivationView(ApiModel):
    policy_version: str
    allowed_symbols: list[str]
    activated_at_utc: str
    expires_at_utc: str | None = None
    status: Literal["ACTIVE", "EXPIRED"]


class RiskResponse(ApiModel):
    state: str
    generated_at_utc: str
    mode: str
    read_only: bool
    policy_version: Literal["risk-v3"]
    limits: RiskLimits
    allowed_symbols: list[str] | None = None
    controls: SafetyView
    execution_locked: bool
    lock_reasons: list[str]
    account: AccountView | None
    quotes: list[QuoteView]
    last_real_preflight: PreflightView | None
    activation: ActivationView | None = None
    warnings: list[str]


class AgentsResponse(ApiModel):
    state: str
    generated_at_utc: str
    mode: str
    read_only: bool
    notice: str
    runs: list[AgentRun]


class CurvePoint(ApiModel):
    date: str
    value: float


class Curve(ApiModel):
    key: str
    label: str
    points: list[CurvePoint]


class MetricRow(ApiModel):
    strategy: str
    label: str
    period: str
    total_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    annualized_volatility_pct: float | None = None
    sharpe: float | None = None
    trades: int | None = None
    exposure_pct: float | None = None
    provenance: str


class AnalyticsDataset(ApiModel):
    id: str
    label: str
    version: str | None = None
    period: dict[str, Any]
    generated_at_utc: str | None = None
    curves: list[Curve]
    metrics: list[MetricRow]
    limitations: list[str]
    axis_dates: list[str] | None = None
    provenance: str


class PaperPerformance(ApiModel):
    available: bool
    reason: str
    provenance: str


class AnalyticsResponse(ApiModel):
    state: str
    generated_at_utc: str
    mode: str
    read_only: bool
    notice: str
    paper_account_performance: PaperPerformance
    datasets: list[AnalyticsDataset]


class AuditCounts(ApiModel):
    events: int
    submissions: int
    unknown_submissions: bool


class AuditEvent(ApiModel):
    event_id: str | None
    occurred_at_utc: str | None
    event_type: str | None
    source: str | None
    run_id: str | None
    correlation_id: str | None
    summary: str
    provenance: str


class AuditResponse(ApiModel):
    state: str
    generated_at_utc: str
    mode: str
    read_only: bool
    counts: AuditCounts
    events: list[AuditEvent]
    notice: str


class AuthState(ApiModel):
    authorization: str
    reason: str | None = None
    trade_write_granted: bool | None = None
    account_lock_configured: bool
    expires_at_utc: str | None = None


class DatabaseState(ApiModel):
    available: bool
    provenance: str


class HealthResponse(ApiModel):
    state: str
    generated_at_utc: str
    mode: str
    read_only: bool
    trading_mode: str
    order_writes_enabled: bool
    auth: AuthState
    database: DatabaseState


class ErrorResponse(ApiModel):
    detail: str


def create_app(
    service: DashboardService | None = None,
    *,
    dashboard_token: str | None = None,
    token_required: bool | None = None,
) -> FastAPI:
    writes = os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower()
    if writes == "true":
        raise RuntimeError("Dashboard API refuses ORDER_WRITES_ENABLED=true")

    if service is None:
        paths = DashboardPaths.discover()
        service = DashboardService(LiveDashboardSource(paths), paths)
    token = (
        dashboard_token
        if dashboard_token is not None
        else os.environ.get("MOOTRADE_DASHBOARD_TOKEN", "").strip()
    )
    require_token = bool(token) if token_required is None else token_required

    app = FastAPI(
        title="MooTrade Dashboard API",
        version="1.0.0",
        description="Read-only dashboard data. No order, approval or control endpoints.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.service = service
    app.state.dashboard_token = token

    origins = _origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def read_only_guard(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                return JSONResponse(
                    status_code=405,
                    content={"detail": "MooTrade dashboard API is read-only"},
                )
            if require_token:
                header = request.headers.get("authorization", "")
                prefix = "Bearer "
                supplied = header[len(prefix) :] if header.startswith(prefix) else ""
                if not token or not hmac.compare_digest(supplied, token):
                    return JSONResponse(
                        status_code=401, content={"detail": "Dashboard authentication failed"}
                    )
            else:
                host = request.client.host if request.client else ""
                if host not in LOOPBACK_HOSTS:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Dashboard API is loopback-only"},
                    )
        return await call_next(request)

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> dict[str, Any]:
        return service.health()

    @app.get("/api/v1/overview", response_model=OverviewResponse)
    def overview() -> dict[str, Any]:
        return service.overview()

    @app.get("/api/v1/portfolio", response_model=PortfolioResponse)
    def portfolio() -> dict[str, Any]:
        return service.portfolio()

    @app.get("/api/v1/risk", response_model=RiskResponse)
    def risk() -> dict[str, Any]:
        return service.risk()

    @app.get("/api/v1/agents", response_model=AgentsResponse)
    def agents() -> dict[str, Any]:
        return service.agents()

    @app.get("/api/v1/analytics", response_model=AnalyticsResponse)
    def analytics() -> dict[str, Any]:
        return service.analytics()

    @app.get("/api/v1/audit", response_model=AuditResponse)
    def audit() -> dict[str, Any]:
        return service.audit()

    return app


def _origins() -> list[str]:
    raw = (
        os.environ.get("MOOTRADE_DASHBOARD_ORIGINS", "").strip()
        or os.environ.get("DASHBOARD_ORIGIN", "").strip()
        or "http://localhost:3000,http://127.0.0.1:3000"
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


app = create_app()
