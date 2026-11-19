"""Read-only data assembly for the MooTrade dashboard.

Every value is either a real broker read, a recorded real preflight, a local
ledger event, or explicitly labelled historical evidence. There is no order
transport or write path in this module.
"""

from __future__ import annotations

import csv
import json
import math
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
from app.models.contracts import AccountSnapshot, TradingActivation, TradingMode
from app.research.instruments import INSTRUMENTS
from app.trading_mode import order_writes_enabled, resolve_trading_mode

QUOTE_SYMBOLS = ("SPY", "UPRO", "SH", "SPXU")
OPERATIONAL_LIMITS = {
    "max_quote_age_seconds": 300,
    "max_account_age_seconds": 60,
    "buying_power_buffer_usd": 5.0,
}
RISK_V1_LIMITS = {
    "max_single_exposure_pct": 10.0,
    "max_total_exposure_pct": 30.0,
    "max_open_positions": 3,
    "max_daily_drawdown_pct": 2.0,
}
RISK_V2_LIMITS = {
    "min_effective_exposure_pct": 20.0,
    "max_effective_exposure_pct": 150.0,
    "max_leverage": 3.0,
    "max_open_positions": 1,
    "max_daily_drawdown_pct": 2.0,
}


def policy_limits_for(
    activation: TradingActivation | None,
) -> tuple[str, dict[str, float]]:
    if activation is not None and activation.risk_policy_version == "risk-v2":
        limits = dict(RISK_V2_LIMITS)
        limits["min_effective_exposure_pct"] = float(
            activation.min_effective_exposure_fraction * 100
        )
        limits["max_effective_exposure_pct"] = float(
            activation.max_effective_exposure_fraction * 100
        )
        limits["max_daily_drawdown_pct"] = float(activation.max_daily_drawdown * 100)
        return "risk-v2", {**limits, **OPERATIONAL_LIMITS}
    limits = dict(RISK_V1_LIMITS)
    if activation is not None:
        if activation.max_single_exposure is not None:
            limits["max_single_exposure_pct"] = float(
                activation.max_single_exposure * 100
            )
        if activation.max_total_exposure is not None:
            limits["max_total_exposure_pct"] = float(
                activation.max_total_exposure * 100
            )
        limits["max_daily_drawdown_pct"] = float(activation.max_daily_drawdown * 100)
    return "risk-v1", {**limits, **OPERATIONAL_LIMITS}


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
        """Report the recorded trading mode and effective order-write capability.

        Writes are effective when the environment flag is set or when the
        ledger holds an AUTO_PAPER activation pin that authorises writes
        (the autonomous scheduler scopes the flag in-process only).
        """
        mode = resolve_trading_mode(os.environ)
        writes = order_writes_enabled(os.environ)
        if mode is TradingMode.AUTO_PAPER:
            activation = self.source.ledger.latest_trading_activation()
            if activation is not None and activation.order_writes_enabled:
                writes = True
        return mode.value, writes

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
        if safety["first_order_approval_count"] == 0:
            lock_reasons.append("No first-order owner approval is recorded.")
        if not any(q.get("fresh") for q in quotes):
            lock_reasons.append("No fresh quote is available for execution.")
        if not any(q.get("regular_session_open") for q in quotes):
            lock_reasons.append("US regular market session is not open.")
        lock_reasons.append("The read-only REST adapter has no order endpoint.")
        warnings = [account_error] if account_error else []
        state = "UNAVAILABLE" if account is None else "LOCKED"
        activation = self.source.ledger.latest_trading_activation()
        policy_version, limits = policy_limits_for(activation)
        return {
            "state": state,
            "generated_at_utc": _iso(now),
            "mode": "PAPER",
            "read_only": True,
            "policy_version": policy_version,
            "limits": limits,
            "allowed_symbols": (
                list(activation.allowed_symbols) if activation is not None else None
            ),
            "controls": safety,
            "execution_locked": True,
            "lock_reasons": lock_reasons,
            "account": account,
            "quotes": quotes,
            "last_real_preflight": self._preflight(),
            "warnings": warnings,
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
        datasets = []
        baseline = self._baseline_analytics()
        if baseline is not None:
            datasets.append(baseline)
        catalyst = self._catalyst_analytics()
        if catalyst is not None:
            datasets.append(catalyst)
        return {
            "state": "HISTORICAL" if datasets else "UNAVAILABLE",
            "generated_at_utc": _iso(now),
            "mode": "PAPER",
            "read_only": True,
            "notice": (
                "Historical signal-quality research. These are not paper-account "
                "returns, broker fills or executable strategy results."
            ),
            "paper_account_performance": {
                "available": False,
                "reason": "No filled paper trades or broker-backed equity history.",
                "provenance": "LIVE_BROKER_READ",
            },
            "datasets": datasets,
        }

    def _baseline_analytics(self) -> dict[str, Any] | None:
        folder = self.paths.evidence_dir / "research" / "etf-trend-baseline-2026-11-17"
        result_path = folder / "results.json"
        curve_path = folder / "equity-curves.csv"
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(result, Mapping):
            return None
        curves = []
        mapping = {
            "trend_baseline": "Trend baseline",
            "spy_hold_10pct": "SPY 10%",
            "spy_hold_100pct": "SPY 100%",
            "cash": "Cash",
        }
        for key, label in mapping.items():
            points = _normalized_curve(curve_path, key)
            if points:
                curves.append({"key": key, "label": label, "points": points})
        metrics = []
        results = result.get("results")
        if isinstance(results, Mapping):
            for key, label in mapping.items():
                item = results.get(key)
                if isinstance(item, Mapping) and isinstance(item.get("metrics"), Mapping):
                    metrics.append(_metric_row(label, "2026-04-01 to 2026-11-16", item["metrics"]))
        period = result.get("period")
        return {
            "id": "etf-trend-baseline",
            "label": "ETF trend baseline",
            "version": result.get("baseline_version"),
            "period": period if isinstance(period, Mapping) else {},
            "generated_at_utc": result.get("generated_at_utc"),
            "curves": curves,
            "metrics": metrics,
            "limitations": list(result.get("limitations", [])),
            "provenance": "HISTORICAL_BACKTEST",
        }

    def _catalyst_analytics(self) -> dict[str, Any] | None:
        folder = self.paths.evidence_dir / "research" / "catalyst-momentum-2026-11-17"
        result_path = folder / "results.json"
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(result, Mapping):
            return None
        results = result.get("results")
        holdout = results.get("holdout") if isinstance(results, Mapping) else None
        development = results.get("development") if isinstance(results, Mapping) else None
        curves = []
        labels = {
            "momentum-v1": "Momentum v1 (retired)",
            "SPY": "SPY",
            "QQQ": "QQQ",
            "cash": "Cash",
        }
        for key, label in labels.items():
            points = _normalized_catalyst_curve(folder / f"holdout-{key}-equity.csv")
            if points:
                curves.append({"key": key, "label": label, "points": points})
        metrics = []
        for period_name, block in (("Development", development), ("Holdout", holdout)):
            if not isinstance(block, Mapping):
                continue
            for key, label in labels.items():
                item = block.get(key)
                if isinstance(item, Mapping):
                    metrics.append(
                        _catalyst_metric_row(period_name, label, item)
                    )
        return {
            "id": "catalyst-momentum",
            "label": "SEC catalyst study",
            "version": result.get("strategy_version"),
            "period": {
                "development": "2025-06-30 to 2026-03-31",
                "holdout": "2026-04-01 to 2026-11-16",
            },
            "generated_at_utc": None,
            "curves": curves,
            "metrics": metrics,
            "limitations": [
                "Historical signal study, not a broker or paper-account result.",
                "Short samples; descriptive Sharpe is not statistically meaningful.",
                "SEC filing coverage and adjusted-price fixtures constrain the sample.",
                "Momentum v1 is retired from the active product; its results are retained as historical evidence.",
                "Not registered as an executable strategy or linked to RiskGate order flow.",
            ],
            "provenance": "HISTORICAL_BACKTEST",
        }

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


def _metric_row(label: str, period: str, metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy": str(metrics.get("name") or label),
        "label": label,
        "period": period,
        "total_return_pct": _float(metrics.get("total_return_pct")),
        "max_drawdown_pct": _float(metrics.get("max_drawdown_pct")),
        "annualized_volatility_pct": _float(metrics.get("annualized_volatility_pct")),
        "sharpe": _float(metrics.get("sharpe_descriptive")),
        "trades": _int(metrics.get("entries")),
        "exposure_pct": _float(metrics.get("average_exposure_pct")),
        "provenance": "HISTORICAL_BACKTEST",
    }


def _catalyst_metric_row(period: str, label: str, metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy": label,
        "label": label,
        "period": period,
        "total_return_pct": _float(metrics.get("total_return_pct")),
        "max_drawdown_pct": _float(metrics.get("max_drawdown_pct")),
        "annualized_volatility_pct": None,
        "sharpe": _float(metrics.get("sharpe_descriptive")),
        "trades": _int(metrics.get("trade_count")),
        "exposure_pct": _float(metrics.get("average_exposure_pct")),
        "provenance": "HISTORICAL_BACKTEST",
    }


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return round(float(value), 4)


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _normalized_curve(path: Path, column: str) -> list[dict[str, Any]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return []
    raw: list[tuple[str, float]] = []
    for row in rows:
        date = row.get("session_date")
        value = row.get(column)
        if not date or value is None:
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        if math.isfinite(number) and number > 0:
            raw.append((date, number))
    return _normalize_points(raw)


def _normalized_catalyst_curve(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return []
    raw: list[tuple[str, float]] = []
    for row in rows:
        date = row.get("session_date")
        value = row.get("equity_usd")
        if not date or value is None:
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        if math.isfinite(number) and number > 0:
            raw.append((date, number))
    return _normalize_points(raw)


def _normalize_points(raw: list[tuple[str, float]]) -> list[dict[str, Any]]:
    if not raw:
        return []
    base = raw[0][1]
    normalized = [(date, value / base * 100.0) for date, value in raw]
    step = max(1, math.ceil(len(normalized) / 160))
    sampled = normalized[::step]
    if sampled[-1][0] != normalized[-1][0]:
        sampled.append(normalized[-1])
    return [{"date": date, "value": round(value, 4)} for date, value in sampled]


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
