"""Read-only data assembly for the MooTrade dashboard.

Every value is either a real broker read, a recorded real preflight, a local
ledger event, or explicitly labelled historical evidence. There is no order
transport or write path in this module.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from app.broker.account_lock import AccountLock, AccountLockError
from app.broker.moomoo_auth import (
    FileTokenStore,
    MoomooAuthError,
    MoomooOAuth,
    TokenStoreError,
    default_token_path,
)
from app.broker.moomoo_quotes import MoomooQuoteFeed, QuoteFeedError, QuoteObservation
from app.broker.moomoo_rest import (
    MAX_HISTORY_PAGES,
    MoomooResponseError,
    MoomooRestBroker,
    MoomooRestClient,
    MoomooRestError,
    RestOrder,
)
from app.cli import ledger_path_from_env, load_local_env
from app.ledger.store import SQLiteLedger
from app.models.contracts import AccountSnapshot
from app.research.instruments import INSTRUMENTS
from app.trading_mode import (
    SUPERVISED_EXECUTION_SYMBOLS,
    order_writes_enabled,
    resolve_trading_mode,
)

QUOTE_SYMBOLS = ("SPY", "SH")
OPERATIONAL_LIMITS = {
    "max_quote_age_seconds": 300,
    "max_account_age_seconds": 60,
    "buying_power_buffer_usd": 5.0,
}
RISK_V3_LIMITS = {
    "min_effective_exposure_pct": 10.0,
    "max_effective_exposure_pct": 40.0,
    "max_leverage": 1.0,
    "max_open_positions": 1,
    "max_daily_drawdown_pct": 2.0,
}
COMPETITION_START = date(2026, 11, 17)
COMPETITION_END = date(2026, 11, 30)
COMPETITION_TRADING_DAYS = [
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


def policy_limits() -> tuple[str, dict[str, float]]:
    """Historical activation pins do not override the current supervised limits."""
    return "risk-v3", {**RISK_V3_LIMITS, **OPERATIONAL_LIMITS}


class DashboardDataError(RuntimeError):
    pass


class DashboardAuthRequired(DashboardDataError):
    pass


class DashboardSource(Protocol):
    @property
    def ledger(self) -> SQLiteLedger: ...

    def broker(self) -> MoomooRestBroker: ...

    def quotes(self) -> MoomooQuoteFeed: ...

    def auth_state(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DashboardPaths:
    project_root: Path
    evidence_dir: Path
    database_path: Path

    @classmethod
    def discover(cls) -> "DashboardPaths":
        package_root = Path(__file__).resolve().parents[2]
        default_root = package_root.parent if (package_root.parent / "backend").is_dir() else package_root
        root = Path(os.environ.get("MOOTRADE_PROJECT_ROOT", "").strip() or default_root)
        load_local_env(root / ".env")
        evidence_raw = os.environ.get("MOOTRADE_EVIDENCE_DIR", "").strip()
        evidence = Path(evidence_raw) if evidence_raw else root / "evidence"
        database = Path(ledger_path_from_env(os.environ))
        if not database.is_absolute():
            database = root / database
        return cls(project_root=root, evidence_dir=evidence, database_path=database)


class LiveDashboardSource:
    """Lazily builds the existing read-only REST adapters."""

    def __init__(self, paths: DashboardPaths) -> None:
        self.paths = paths
        self._ledger = SQLiteLedger(paths.database_path)
        self._lock = threading.Lock()
        self._broker: MoomooRestBroker | None = None
        self._quotes: MoomooQuoteFeed | None = None
        self._auth_reason: str | None = None

    @property
    def ledger(self) -> SQLiteLedger:
        return self._ledger

    def _token_store(self) -> FileTokenStore:
        override = os.environ.get("MOOTRADE_OAUTH_STORE", "").strip()
        return FileTokenStore(Path(override) if override else default_token_path())

    def _build(self) -> None:
        store = self._token_store()
        record = store.load()
        if record is None:
            raise DashboardAuthRequired("Moomoo authorization is required")
        if record.has_trade_write():
            raise DashboardAuthRequired("authorization contains trade:write; refusing")
        if not record.has_required_scopes():
            raise DashboardAuthRequired("authorization lacks required read scopes")
        account_lock = AccountLock.from_env(os.environ)
        oauth = MoomooOAuth(store, open_browser=None)
        client = MoomooRestClient(oauth)
        self._broker = MoomooRestBroker(client, account_lock, self._ledger)
        self._quotes = MoomooQuoteFeed(client)

    def _ensure(self) -> None:
        if self._broker is not None and self._quotes is not None:
            return
        with self._lock:
            if self._broker is not None and self._quotes is not None:
                return
            try:
                self._build()
            except (DashboardAuthRequired, MoomooAuthError, TokenStoreError, AccountLockError) as exc:
                self._auth_reason = _safe_reason(exc)
                raise

    def broker(self) -> MoomooRestBroker:
        self._ensure()
        assert self._broker is not None
        return self._broker

    def quotes(self) -> MoomooQuoteFeed:
        self._ensure()
        assert self._quotes is not None
        return self._quotes

    def auth_state(self) -> dict[str, Any]:
        try:
            store = self._token_store()
            record = store.load()
        except (MoomooAuthError, TokenStoreError) as exc:
            return {
                "authorization": "ERROR",
                "reason": _safe_reason(exc),
                "trade_write_granted": None,
                "account_lock_configured": _account_lock_configured(),
            }
        if record is None:
            return {
                "authorization": "AUTH_REQUIRED",
                "reason": "No local Moomoo authorization.",
                "trade_write_granted": None,
                "account_lock_configured": _account_lock_configured(),
            }
        state = "PRESENT"
        reason = None
        if record.has_trade_write() or not record.has_required_scopes():
            state = "INVALID_SCOPE"
            reason = "Stored authorization is not read-only."
        expiry = record.expires_at.isoformat() if record.expires_at else None
        return {
            "authorization": state,
            "reason": reason,
            "trade_write_granted": record.has_trade_write(),
            "account_lock_configured": _account_lock_configured(),
            "expires_at_utc": expiry,
        }


def _account_lock_configured() -> bool:
    return bool(
        os.environ.get("COMPETITION_ACCOUNT_MASKED_ID", "").strip()
        and os.environ.get("COMPETITION_ACCOUNT_FINGERPRINT", "").strip()
    )


def _safe_reason(exc: Exception) -> str:
    if isinstance(exc, (DashboardAuthRequired, MoomooAuthError, TokenStoreError)):
        return "Moomoo read authorization is unavailable."
    if isinstance(exc, AccountLockError):
        return "Competition account identity check failed."
    if isinstance(exc, QuoteFeedError):
        return "Moomoo quote observation failed."
    if isinstance(exc, (MoomooRestError, MoomooResponseError)):
        return "Moomoo read-only request failed."
    return "Dashboard data source is unavailable."


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _age(now: datetime, value: datetime) -> float:
    return max(0.0, (now - value).total_seconds())


class DashboardService:
    def __init__(
        self,
        source: DashboardSource,
        paths: DashboardPaths,
        *,
        clock: Any | None = None,
    ) -> None:
        self.source = source
        self.paths = paths
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("dashboard clock must be timezone-aware")
        return now

    def _trading_state(self) -> tuple[str, bool]:
        """Report runtime controls; a historical pin is not current write authority."""
        return resolve_trading_mode(os.environ).value, order_writes_enabled(os.environ)

    def _safety(self) -> dict[str, Any]:
        ledger = self.source.ledger
        trading_mode, writes = self._trading_state()
        return {
            "trading_mode": trading_mode,
            "order_writes_enabled": writes,
            "kill_switch_engaged": ledger.kill_switch_engaged(),
            "first_order_approval_count": ledger.order_approval_count(),
            "submission_count": ledger.submission_count(),
            "unknown_submissions": ledger.has_unknown_submissions(),
            "broker_order_endpoint_available": False,
            "provenance": "LOCAL_CONTROLS",
        }

    def _account(self) -> tuple[dict[str, Any] | None, str | None]:
        now = self._now()
        try:
            broker = self.source.broker()
            identity = broker.account_identity()
            snapshot = broker.get_account_snapshot()
        except Exception as exc:
            return None, _safe_reason(exc)
        return _account_view(now, identity, snapshot), None

    def _quote(self, symbol: str, now: datetime) -> dict[str, Any]:
        try:
            observation = self.source.quotes().observe_quote(symbol, now)
        except Exception as exc:
            return {
                "symbol": symbol,
                "state": "UNAVAILABLE",
                "provenance": "LIVE_BROKER_READ",
                "error": _safe_reason(exc),
            }
        return _quote_view(observation)

    def _agent_run(self) -> dict[str, Any] | None:
        path = _latest(self.paths.evidence_dir / "qoder", "qoder-*.json")
        if path is None:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, Mapping):
            return None
        research = payload.get("research")
        snapshot = research.get("snapshot") if isinstance(research, Mapping) else None
        candidates = []
        if isinstance(snapshot, Mapping):
            for candidate in snapshot.get("candidates", []):
                if not isinstance(candidate, Mapping):
                    continue
                candidates.append(
                    {
                        "symbol": candidate.get("symbol"),
                        "direction": candidate.get("direction"),
                        "leverage": candidate.get("leverage"),
                        "effective_exposure": candidate.get("effective_exposure"),
                        "close": candidate.get("close"),
                        "eligible": candidate.get("eligible"),
                        "selected": candidate.get("selected"),
                        "reasons": list(candidate.get("reasons", [])),
                    }
                )
        summaries = payload.get("agent_summaries")
        safe_summaries = []
        if isinstance(summaries, Mapping):
            for role in ("coordinator_ready", "researcher", "auditor", "coordinator_final"):
                text = summaries.get(role)
                if isinstance(text, str):
                    safe_summaries.append({"role": role, "text": text[:2500]})
        sessions = payload.get("session_ids")
        session_count = len(sessions) if isinstance(sessions, Mapping) else 0
        mode = payload.get("mode", "HISTORICAL_DRY_RUN")
        provenance = (
            "CURRENT_MARKET_READ_ONLY"
            if mode == "CURRENT_MARKET_READ_ONLY"
            else "HISTORICAL_QODER_RUN"
        )
        collection = payload.get("data_collection")
        collection_summary = None
        if isinstance(collection, Mapping):
            collection_quotes = collection.get("quotes")
            collection_account = collection.get("account")
            account = collection_account if isinstance(collection_account, Mapping) else {}
            validations = collection.get("validations")
            validation = validations if isinstance(validations, Mapping) else {}
            collection_summary = {
                "collected_at_utc": collection.get("collected_at_utc"),
                "us_eastern_time": collection.get("us_eastern_time"),
                "quotes": [
                    {
                        "symbol": quote.get("symbol"),
                        "data_time_utc": quote.get("data_time_utc"),
                        "age_seconds": quote.get("age_seconds"),
                        "market_state": quote.get("market_state"),
                    }
                    for quote in (collection_quotes if isinstance(collection_quotes, list) else [])
                    if isinstance(quote, Mapping)
                ],
                "account_as_of_utc": account.get("as_of_utc"),
                "account_age_seconds": account.get("age_seconds"),
                "regular_session_required": validation.get("regular_session_required"),
            }
        proposal = None
        raw_proposal = research.get("proposal") if isinstance(research, Mapping) else None
        if isinstance(raw_proposal, Mapping):
            proposal = {
                "proposal_id": raw_proposal.get("proposal_id"),
                "symbol": raw_proposal.get("symbol"),
                "action": raw_proposal.get("action"),
                "requested_quantity": raw_proposal.get("requested_quantity"),
                "thesis": raw_proposal.get("thesis"),
                "invalidation": raw_proposal.get("invalidation"),
            }
        risk_decision = None
        raw_risk = payload.get("risk")
        raw_risk_decision = raw_risk.get("risk_decision") if isinstance(raw_risk, Mapping) else None
        if isinstance(raw_risk_decision, Mapping):
            risk_decision = {
                "policy_version": raw_risk_decision.get("policy_version"),
                "decision": raw_risk_decision.get("decision"),
                "approved_quantity": raw_risk_decision.get("approved_quantity"),
                "reasons": [
                    {
                        "rule_id": reason.get("rule_id"),
                        "message": reason.get("message"),
                    }
                    for reason in raw_risk_decision.get("reasons", [])
                    if isinstance(reason, Mapping)
                ],
            }
        return {
            "run_id": payload.get("run_id"),
            "mode": mode,
            "strategy_version": payload.get("strategy_version"),
            "status": payload.get("status"),
            "outcome": payload.get("outcome"),
            "notice": payload.get("notice"),
            "completed_at_utc": payload.get("completed_at_utc"),
            "session_count": session_count,
            "decision_time_utc": snapshot.get("decision_time_utc") if isinstance(snapshot, Mapping) else None,
            "data_as_of_utc": snapshot.get("data_as_of_utc") if isinstance(snapshot, Mapping) else None,
            "spy_session_date": snapshot.get("spy_session_date") if isinstance(snapshot, Mapping) else None,
            "spy_close": snapshot.get("spy_close") if isinstance(snapshot, Mapping) else None,
            "spy_return_10d": snapshot.get("spy_return_10d") if isinstance(snapshot, Mapping) else None,
            "spy_sma50": snapshot.get("spy_sma50") if isinstance(snapshot, Mapping) else None,
            "spy_trend_pct": snapshot.get("spy_trend_pct") if isinstance(snapshot, Mapping) else None,
            "spy_volatility_20d": snapshot.get("spy_volatility_20d") if isinstance(snapshot, Mapping) else None,
            "market_state": snapshot.get("market_state") if isinstance(snapshot, Mapping) else None,
            "direction": snapshot.get("direction") if isinstance(snapshot, Mapping) else None,
            "target_symbol": snapshot.get("target_symbol") if isinstance(snapshot, Mapping) else None,
            "target_effective_exposure": snapshot.get("target_effective_exposure") if isinstance(snapshot, Mapping) else None,
            "current_symbol": snapshot.get("current_symbol") if isinstance(snapshot, Mapping) else None,
            "current_quantity": snapshot.get("current_quantity") if isinstance(snapshot, Mapping) else None,
            "action": snapshot.get("action") if isinstance(snapshot, Mapping) else None,
            "reentry_symbol": snapshot.get("reentry_symbol") if isinstance(snapshot, Mapping) else None,
            "decision_reason": snapshot.get("decision_reason") if isinstance(snapshot, Mapping) else None,
            "selected_symbol": snapshot.get("target_symbol") if isinstance(snapshot, Mapping) else None,
            "proposal": proposal,
            "risk_decision": risk_decision,
            "no_trade_reason": snapshot.get("no_trade_reason") if isinstance(snapshot, Mapping) else None,
            "candidates": candidates,
            "summaries": safe_summaries,
            "data_collection": collection_summary,
            "provenance": provenance,
        }

    def _preflight(self) -> dict[str, Any] | None:
        path = _latest(self.paths.evidence_dir / "preflight", "preflight-*.json")
        if path is None:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, Mapping):
            return None
        diagnostic = payload.get("diagnostic_risk_evaluation")
        preview = payload.get("diagnostic_preview")
        safety = payload.get("safety")
        quotes = payload.get("quotes")
        quote_rows: list[dict[str, Any]] = []
        if isinstance(quotes, Mapping):
            for symbol, row in quotes.items():
                if isinstance(row, Mapping):
                    quote_rows.append(
                        {
                            "symbol": symbol,
                            "last_price": row.get("last_price"),
                            "data_time_utc": row.get("data_time_utc"),
                            "age_seconds": row.get("age_seconds"),
                            "sec_status": row.get("sec_status"),
                            "suspension": row.get("suspension"),
                            "market_state": row.get("market_state"),
                        }
                    )
        return {
            "kind": payload.get("kind"),
            "mode": payload.get("mode"),
            "checked_at_utc": payload.get("checked_at_utc"),
            "decision": diagnostic.get("decision") if isinstance(diagnostic, Mapping) else None,
            "rejection_rule_ids": list(diagnostic.get("rejection_rule_ids", []))
            if isinstance(diagnostic, Mapping)
            else [],
            "reasons": list(diagnostic.get("reasons", [])) if isinstance(diagnostic, Mapping) else [],
            "submission_performed": preview.get("submission_performed")
            if isinstance(preview, Mapping)
            else False,
            "order_endpoint_contacted": safety.get("order_endpoint_contacted")
            if isinstance(safety, Mapping)
            else None,
            "scope_trade_write": safety.get("oauth_scope_trade_write")
            if isinstance(safety, Mapping)
            else None,
            "quotes": quote_rows,
            "provenance": "RECORDED_REAL_PREFLIGHT",
        }

    def overview(self) -> dict[str, Any]:
        now = self._now()
        account, account_error = self._account()
        quotes = [self._quote(symbol, now) for symbol in QUOTE_SYMBOLS]
        warnings: list[str] = []
        if account_error:
            warnings.append(account_error)
        quote_errors = [q["symbol"] for q in quotes if q["state"] == "UNAVAILABLE"]
        if quote_errors:
            warnings.append(f"Quote data unavailable for {', '.join(quote_errors)}.")
        stale = [q["symbol"] for q in quotes if q.get("stale") is True]
        if stale:
            warnings.append(
                f"{', '.join(stale)} quote is outside the 300-second execution window."
            )
        if account is not None and not any(q.get("regular_session_open") for q in quotes):
            warnings.append("US regular market session is not open.")
        if account is None:
            state = "UNAVAILABLE"
        elif quote_errors:
            state = "PARTIAL"
        elif stale:
            state = "STALE"
        else:
            state = "LIVE"
        return {
            "state": state,
            "generated_at_utc": _iso(now),
            "mode": "PAPER",
            "read_only": True,
            "account": account,
            "quotes": quotes,
            "safety": self._safety(),
            "latest_agent_run": self._agent_run(),
            "warnings": warnings,
        }

    def portfolio(self) -> dict[str, Any]:
        now = self._now()
        warnings: list[str] = []
        try:
            broker = self.source.broker()
            identity = broker.account_identity()
            snapshot = broker.get_account_snapshot()
        except Exception as exc:
            return {
                "state": "UNAVAILABLE",
                "generated_at_utc": _iso(now),
                "mode": "PAPER",
                "read_only": True,
                "reason": _safe_reason(exc),
                "account": None,
                "positions": [],
                "open_orders": [],
                "today_orders": [],
                "history_orders": [],
                "warnings": [],
            }
        account = {
            "masked_id": identity.masked_id,
            "equity": str(snapshot.equity),
            "cash": str(snapshot.cash),
            "buying_power": str(snapshot.buying_power),
            "positions_count": len(snapshot.positions),
            "open_orders_count": len(snapshot.open_orders),
            "reconciled": snapshot.reconciled,
            "unknown_orders": snapshot.unknown_orders,
            "as_of_utc": _iso(snapshot.as_of_utc),
            "age_seconds": _age(now, snapshot.as_of_utc),
            "provenance": "LIVE_BROKER_READ",
        }
        today: tuple[RestOrder, ...] = ()
        history: tuple[RestOrder, ...] = ()
        try:
            today = broker.get_today_orders()
        except Exception as exc:
            warnings.append(f"Today's orders unavailable: {_safe_reason(exc)}")
        try:
            history = broker.get_order_history(max_pages=MAX_HISTORY_PAGES)
        except Exception as exc:
            warnings.append(f"Order history unavailable: {_safe_reason(exc)}")
        state = "LIVE" if not warnings else "PARTIAL"
        return {
            "state": state,
            "generated_at_utc": _iso(now),
            "mode": "PAPER",
            "read_only": True,
            "account": account,
            "positions": [
                {
                    "symbol": item.symbol,
                    "quantity": item.quantity,
                    "market_value": str(item.market_value),
                    "provenance": "LIVE_BROKER_READ",
                }
                for item in snapshot.positions
            ],
            "open_orders": [
                {
                    "symbol": item.symbol,
                    "side": item.side.value,
                    "remaining_quantity": item.remaining_quantity,
                    "reference_price": str(item.reference_price),
                    "provenance": "LIVE_BROKER_READ",
                }
                for item in snapshot.open_orders
            ],
            "today_orders": [_order_view(order) for order in today],
            "history_orders": [_order_view(order) for order in history],
            "warnings": warnings,
        }

    def risk(self) -> dict[str, Any]:
        now = self._now()
        account, account_error = self._account()
        quotes = [self._quote(symbol, now) for symbol in QUOTE_SYMBOLS]
        safety = self._safety()
        lock_reasons = []
        if not safety["order_writes_enabled"]:
            lock_reasons.append("ORDER_WRITES_ENABLED=false")
        if safety["kill_switch_engaged"]:
            lock_reasons.append("Kill switch is engaged.")
        lock_reasons.append(
            "EVERY supervised BUY and SELL requires owner approval for the exact proposal and client order key; "
            "only the scheduled autonomous executor may submit without per-order approval, and only under a valid, unexpired risk-v3 activation pin."
        )
        execution_quotes = [q for q in quotes if q["symbol"] in SUPERVISED_EXECUTION_SYMBOLS]
        if not any(q.get("fresh") for q in execution_quotes):
            lock_reasons.append("No fresh quote is available for execution.")
        if not any(q.get("regular_session_open") for q in execution_quotes):
            lock_reasons.append("US regular market session is not open.")
        lock_reasons.append("The read-only REST adapter has no order endpoint.")
        warnings = [account_error] if account_error else []
        state = "UNAVAILABLE" if account is None else "LOCKED"
        activation = self.source.ledger.latest_trading_activation()
        activation_view: dict[str, object] | None = None
        if activation is not None:
            expiry = activation.expires_at_utc
            status = "EXPIRED" if expiry is not None and now >= expiry else "ACTIVE"
            activation_view = {
                "policy_version": activation.risk_policy_version,
                "allowed_symbols": list(activation.allowed_symbols),
                "activated_at_utc": _iso(activation.activated_at_utc),
                "expires_at_utc": expiry.isoformat() if expiry else None,
                "status": status,
            }
            if status == "ACTIVE":
                until = f" until {expiry.isoformat()}" if expiry else ""
                warnings.append(
                    f"{activation.risk_policy_version} AUTO_PAPER pin "
                    f"({', '.join(activation.allowed_symbols)}) authorises the scheduled "
                    f"autonomous executor{until}; this dashboard is read-only and never submits."
                )
            else:
                warnings.append(
                    f"HISTORICAL {activation.risk_policy_version} AUTO_PAPER pin "
                    f"({', '.join(activation.allowed_symbols)}) expired {expiry.isoformat()}; "
                    f"it grants no execution authority."
                )
        policy_version, limits = policy_limits()
        return {
            "state": state,
            "generated_at_utc": _iso(now),
            "mode": "PAPER",
            "read_only": True,
            "policy_version": policy_version,
            "limits": limits,
            "allowed_symbols": list(SUPERVISED_EXECUTION_SYMBOLS),
            "controls": safety,
            "execution_locked": True,
            "lock_reasons": lock_reasons,
            "account": account,
            "quotes": quotes,
            "last_real_preflight": self._preflight(),
            "warnings": warnings,
            "activation": activation_view,
        }

    def agents(self) -> dict[str, Any]:
        now = self._now()
        run = self._agent_run()
        current = bool(run and run.get("provenance") == "CURRENT_MARKET_READ_ONLY")
        return {
            "state": "LIVE" if current else ("HISTORICAL" if run else "EMPTY"),
            "generated_at_utc": _iso(now),
            "mode": "PAPER",
            "read_only": True,
            "notice": (
                "Current read-only Moomoo evidence from the competition paper account, "
                "current quote snapshots and completed daily bars. No order was submitted or approved."
                if current
                else "Historical Qoder dry-run evidence only. Not current market data, "
                "owner approval or an order."
            ),
            "runs": [run] if run else [],
        }

    def analytics(self) -> dict[str, Any]:
        now = self._now()
        dataset, paper_days = self._competition_analytics()
        available = paper_days > 0
        return {
            "state": (
                "LIVE"
                if available
                else ("EMPTY" if dataset is not None else "UNAVAILABLE")
            ),
            "generated_at_utc": _iso(now),
            "mode": "PAPER",
            "read_only": True,
            "notice": (
                "Competition-period evidence only (17 Nov to 30 Nov 2026): "
                "broker-observed day-start equity and completed Moomoo daily bars. "
                "No backtest data is shown."
            ),
            "paper_account_performance": {
                "available": available,
                "reason": (
                    "Broker-observed day-start equity exists within the competition period."
                    if available
                    else "No broker-observed day-start equity within the competition period yet."
                ),
                "provenance": "LIVE_BROKER_READ",
            },
            "datasets": [dataset] if dataset is not None else [],
        }

    def _competition_analytics(self) -> tuple[dict[str, Any] | None, int]:
        paper = self._paper_equity_series()
        spy = self._spy_benchmark_series()
        if not paper and not spy:
            return None, 0
        curves: list[dict[str, Any]] = []
        metrics: list[dict[str, Any]] = []
        if paper:
            curves.append(
                {"key": "paper_account", "label": "Paper account", "points": _normalized(paper)}
            )
            metrics.append(
                _series_metric_row("paper_account", "Paper account", paper, "LIVE_BROKER_READ")
            )
        if spy:
            curves.append({"key": "spy", "label": "SPY", "points": _normalized(spy)})
            metrics.append(
                _series_metric_row("spy", "SPY", spy, "CURRENT_MARKET_READ_ONLY")
            )
        cash_dates = paper or spy
        curves.append(
            {
                "key": "cash",
                "label": "Cash",
                "points": [{"date": day, "value": 100.0} for day, _ in cash_dates],
            }
        )
        metrics.append(_cash_metric_row())
        return {
            "id": "competition-period",
            "label": "Competition period",
            "period": {
                "start": COMPETITION_START.isoformat(),
                "end": COMPETITION_END.isoformat(),
            },
            "generated_at_utc": None,
            "curves": curves,
            "metrics": metrics,
            "axis_dates": list(COMPETITION_TRADING_DAYS),
            "limitations": [
                "Paper-account equity is broker-observed day-start equity, not intraday mark-to-market or fill-derived P&L.",
                "SPY is normalised to its first competition close from completed Moomoo daily bars.",
                "Cash is a flat 100 baseline for comparison, not an account balance.",
                "A few sessions make Sharpe and volatility descriptive only, not statistically meaningful.",
            ],
            "provenance": "LIVE_BROKER_READ" if paper else "CURRENT_MARKET_READ_ONLY",
        }, len(paper)

    def _paper_equity_series(self) -> list[tuple[str, float]]:
        rows = self.source.ledger.equity_days()
        groups: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            groups.setdefault(row["account_fingerprint"], []).append(row)
        if not groups:
            return []
        best = max(groups.values(), key=lambda items: (len(items), items[-1]["trading_day"]))
        series = []
        for row in best:
            day = row["trading_day"]
            if COMPETITION_START.isoformat() <= day <= COMPETITION_END.isoformat():
                series.append((day, float(Decimal(row["day_start_equity"]))))
        return series

    def _spy_benchmark_series(self) -> list[tuple[str, float]]:
        market = self.paths.evidence_dir / "current-market"
        if not market.is_dir():
            return []
        for folder in sorted((p for p in market.iterdir() if p.is_dir()), reverse=True):
            bars_path = folder / "daily-bars.json"
            if not bars_path.is_file():
                continue
            try:
                payload = json.loads(bars_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, Mapping):
                continue
            symbols = payload.get("symbols")
            if not isinstance(symbols, Mapping):
                continue
            spy = symbols.get("SPY")
            if not isinstance(spy, list):
                continue
            closes: list[tuple[str, float]] = []
            for bar in spy:
                if not isinstance(bar, Mapping):
                    continue
                raw_day = bar.get("date")
                close = bar.get("close")
                if not isinstance(raw_day, str) or len(raw_day) != 8:
                    continue
                if isinstance(close, bool):
                    continue
                try:
                    day = date(int(raw_day[:4]), int(raw_day[4:6]), int(raw_day[6:8]))
                    close_number = float(close)
                except (TypeError, ValueError):
                    continue
                if COMPETITION_START <= day <= COMPETITION_END and close_number > 0:
                    closes.append((day.isoformat(), close_number))
            if closes:
                closes.sort()
                return closes
        return []

    def audit(self) -> dict[str, Any]:
        now = self._now()
        events = self.source.ledger.list_events()
        return {
            "state": "LIVE" if events else "EMPTY",
            "generated_at_utc": _iso(now),
            "mode": "PAPER",
            "read_only": True,
            "counts": {
                "events": len(events),
                "submissions": self.source.ledger.submission_count(),
                "unknown_submissions": self.source.ledger.has_unknown_submissions(),
            },
            "events": [_audit_event(event) for event in reversed(events)],
            "notice": "Append-only local ledger summaries. Raw payloads are not exposed.",
        }

    def health(self) -> dict[str, Any]:
        now = self._now()
        auth = self.source.auth_state()
        trading_mode, writes = self._trading_state()
        return {
            "state": "OK",
            "generated_at_utc": _iso(now),
            "mode": "PAPER",
            "read_only": True,
            "trading_mode": trading_mode,
            "order_writes_enabled": writes,
            "auth": auth,
            "database": {"available": True, "provenance": "LOCAL_LEDGER"},
        }


def _account_view(now: datetime, identity: Any, snapshot: AccountSnapshot) -> dict[str, Any]:
    gross = sum(
        (item.market_value for item in snapshot.positions), Decimal("0")
    )
    effective = sum(
        (
            item.market_value * INSTRUMENTS[item.symbol].effective_exposure
            for item in snapshot.positions
            if item.symbol in INSTRUMENTS
        ),
        Decimal("0"),
    )
    return {
        "masked_id": identity.masked_id,
        "title": identity.title,
        "market_id": identity.market_id,
        "account_type": identity.account_type,
        "verified": True,
        "equity": str(snapshot.equity),
        "cash": str(snapshot.cash),
        "buying_power": str(snapshot.buying_power),
        "day_start_equity": str(snapshot.day_start_equity),
        "peak_equity": str(snapshot.peak_equity),
        "positions_count": len(snapshot.positions),
        "open_orders_count": len(snapshot.open_orders),
        "reconciled": snapshot.reconciled,
        "unknown_orders": snapshot.unknown_orders,
        "gross_exposure_pct": float(gross / snapshot.equity * 100),
        "effective_exposure_pct": float(effective / snapshot.equity * 100),
        "as_of_utc": _iso(snapshot.as_of_utc),
        "age_seconds": _age(now, snapshot.as_of_utc),
        "provenance": "LIVE_BROKER_READ",
    }


def _quote_view(observation: QuoteObservation) -> dict[str, Any]:
    stale = observation.age_seconds > OPERATIONAL_LIMITS["max_quote_age_seconds"]
    abnormal = observation.sec_status != "NORMAL" or observation.suspended
    return {
        "symbol": observation.symbol,
        "state": "STALE" if stale else ("ABNORMAL" if abnormal else "LIVE"),
        "price": str(observation.price),
        "as_of_utc": _iso(observation.as_of_utc),
        "age_seconds": round(observation.age_seconds, 1),
        "fresh": not stale and not abnormal,
        "stale": stale,
        "sec_status": observation.sec_status,
        "suspended": observation.suspended,
        "market_state": observation.market_state,
        "regular_session_open": observation.regular_session_open,
        "error": None,
        "provenance": "LIVE_BROKER_READ",
    }


def _order_view(order: RestOrder) -> dict[str, Any]:
    return {
        "broker_order_id": order.broker_order_id,
        "symbol": order.symbol,
        "side": order.side.value,
        "status": order.status_label,
        "quantity": order.quantity,
        "filled_quantity": order.filled_quantity,
        "price": str(order.price),
        "average_fill_price": str(order.average_fill_price),
        "created_at_utc": _iso(order.created_at_utc),
        "updated_at_utc": _iso(order.updated_at_utc),
        "remark": order.remark,
        "provenance": "LIVE_BROKER_READ",
    }


def _normalized(series: list[tuple[str, float]]) -> list[dict[str, Any]]:
    base = series[0][1]
    return [{"date": day, "value": round(value / base * 100.0, 4)} for day, value in series]


def _series_metrics(values: list[float]) -> dict[str, Any]:
    total_return_pct = (values[-1] / values[0] - 1.0) * 100.0
    peak = values[0]
    max_drawdown_pct = 0.0
    for value in values:
        peak = max(peak, value)
        max_drawdown_pct = max(max_drawdown_pct, (peak - value) / peak * 100.0)
    returns = [b / a - 1.0 for a, b in zip(values, values[1:])]
    volatility = None
    sharpe = None
    if len(returns) >= 2:
        spread = statistics.stdev(returns)
        volatility = spread * math.sqrt(252) * 100.0
        if spread > 0:
            sharpe = statistics.mean(returns) / spread * math.sqrt(252)
    return {
        "total_return_pct": round(total_return_pct, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "annualized_volatility_pct": round(volatility, 4) if volatility is not None else None,
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
    }


def _series_metric_row(
    strategy: str, label: str, series: list[tuple[str, float]], provenance: str
) -> dict[str, Any]:
    metrics = _series_metrics([value for _, value in series])
    return {
        "strategy": strategy,
        "label": label,
        "period": f"{COMPETITION_START.isoformat()} to {COMPETITION_END.isoformat()}",
        "trades": None,
        "exposure_pct": None,
        "provenance": provenance,
        **metrics,
    }


def _cash_metric_row() -> dict[str, Any]:
    return {
        "strategy": "cash",
        "label": "Cash",
        "period": f"{COMPETITION_START.isoformat()} to {COMPETITION_END.isoformat()}",
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "annualized_volatility_pct": 0.0,
        "sharpe": None,
        "trades": None,
        "exposure_pct": None,
        "provenance": "LOCAL_LEDGER",
    }


def _audit_event(event: Mapping[str, Any]) -> dict[str, Any]:
    payload = event.get("payload_redacted_json")
    return {
        "event_id": event.get("event_id"),
        "occurred_at_utc": event.get("occurred_at_utc"),
        "event_type": event.get("event_type"),
        "source": event.get("source"),
        "run_id": event.get("run_id"),
        "correlation_id": event.get("correlation_id"),
        "summary": _event_summary(event.get("event_type"), payload),
        "provenance": "LOCAL_LEDGER",
    }


def _event_summary(event_type: Any, payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return "Recorded event."
    if event_type == "QODER_RUN_STARTED":
        return f"Strategy {payload.get('strategy_version', 'unknown')} started."
    if event_type == "QODER_TOOL_RESULT":
        result = payload.get("result")
        if isinstance(result, Mapping):
            return (
                f"{result.get('mode', 'QODER')} tool result; "
                f"proposal={'present' if result.get('proposal') else 'none'}."
            )
        return "QODER tool result recorded."
    if event_type == "QODER_RUN_COMPLETED":
        sessions = payload.get("session_ids")
        count = len(sessions) if isinstance(sessions, Mapping) else 0
        return f"Outcome {payload.get('outcome', 'UNKNOWN')}; {count} agent sessions."
    if event_type in {"POLICY_APPROVED", "POLICY_REJECTED"}:
        reasons = payload.get("reasons")
        rule_ids = [
            item.get("rule_id")
            for item in reasons
            if isinstance(item, Mapping) and item.get("rule_id")
        ] if isinstance(reasons, list) else []
        suffix = f"; rules {', '.join(rule_ids)}" if rule_ids else ""
        return f"Risk decision {payload.get('decision', 'UNKNOWN')}{suffix}."
    if event_type and event_type.startswith("ORDER_"):
        return f"{event_type.replace('_', ' ').title()} ledger event."
    if event_type and event_type.startswith("FILL_"):
        return f"Fill recorded: {payload.get('quantity', '?')} at {payload.get('price', '?')}."
    if event_type and event_type.startswith("RECONCILIATION_"):
        return f"{event_type.replace('_', ' ').title()}."
    return "Recorded append-only ledger event."


def _latest(folder: Path, pattern: str) -> Path | None:
    if not folder.exists():
        return None
    candidates = sorted(folder.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None
