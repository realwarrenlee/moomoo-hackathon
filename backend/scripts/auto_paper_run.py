"""AUTO_PAPER execution phase for the deterministic spy-directional strategy.

This is the only unattended path that can submit a paper order. It runs at the
start of the next US regular session after the read-only decision phase and
fails closed on every ambiguity: no AUTO_PAPER activation pin, an engaged kill
switch, an UNKNOWN submission, a missing decision artifact, a stale account, a
closed market, a RiskGate rejection or a duplicate proposal all abort without
submission. Each proposal is submitted at most once, and an ambiguous broker
outcome is recorded and never retried.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from app.broker.account_lock import AccountLock
from app.broker.moomoo_auth import (
    FileTokenStore,
    MoomooExecutionOAuth,
    default_execution_token_path,
)
from app.cli import ledger_path_from_env, load_local_env
from app.ledger.store import SQLiteLedger
from app.models.contracts import AccountSnapshot, OrderStatus, PolicyDecision
from app.research.data import MarketHistory
from app.research.instruments import CANDIDATE_SYMBOLS
from app.research.strategy import (
    STRATEGY_VERSION,
    ExposurePolicy,
    ResearchSnapshot,
    decide,
    screen,
)
from app.risk.policy import POLICY_VERSION_V1, POLICY_VERSION_V2, RiskGate
from app.service import build_client_order_key
from app.supervised import SupervisedExecution, build_supervised_execution
from app.trading_mode import (
    AUTO_PAPER_SYMBOLS,
    LEGACY_AUTO_PAPER_SYMBOLS,
    TradingMode,
    TradingModeError,
    auto_paper_active,
    exposure_policy_for_activation,
    order_writes_enabled,
    resolve_trading_mode,
)
from scripts.current_market_run import CollectionError, _load_bars

ROOT = Path(__file__).resolve().parents[2]
DECISION_ARTIFACT_MODES = frozenset({"CURRENT_MARKET_READ_ONLY"})
MAX_ACCOUNT_AGE_SECONDS = 60
CLOCK_SKEW_TOLERANCE_SECONDS = 5

PAPER_BANNER = (
    "PAPER TRADING ONLY. This autonomous executor submits orders exclusively to "
    "the competition paper account bound by the AUTO_PAPER activation pin."
)


class AutoPaperError(RuntimeError):
    pass


def _abstain(reason: str, now: datetime) -> dict[str, object]:
    return {
        "schema_version": "1",
        "mode": "AUTO_PAPER_EXECUTION",
        "status": "ABSTAINED",
        "reason": reason,
        "executed_at_utc": now.isoformat(),
        "submission_performed": False,
    }


def _auto_paper_block(
    environ: Mapping[str, str],
    activation: object,
    fingerprint: str,
) -> str | None:
    try:
        mode = resolve_trading_mode(environ)
    except TradingModeError as exc:
        return str(exc)
    if mode is not TradingMode.AUTO_PAPER:
        return f"TRADING_MODE={mode.value}; autonomous execution requires AUTO_PAPER"
    if not order_writes_enabled(environ):
        return "ORDER_WRITES_ENABLED is not true"
    if activation is None:
        return "no AUTO_PAPER activation pin compatible with the current policy is recorded in the ledger"
    if activation.account_fingerprint != fingerprint:
        return "activation pin does not match the configured competition-account fingerprint"
    if activation.strategy_version != STRATEGY_VERSION:
        return f"activation pin binds strategy {activation.strategy_version}, not {STRATEGY_VERSION}"
    if activation.risk_policy_version == POLICY_VERSION_V1:
        expected_symbols = LEGACY_AUTO_PAPER_SYMBOLS
    elif activation.risk_policy_version == POLICY_VERSION_V2:
        expected_symbols = AUTO_PAPER_SYMBOLS
    else:
        return (
            f"activation pin binds unsupported risk policy "
            f"{activation.risk_policy_version}"
        )
    if tuple(activation.allowed_symbols) != expected_symbols:
        return (
            f"activation pin allowlist is {tuple(activation.allowed_symbols)}, "
            f"expected {expected_symbols}"
        )
    if activation.paper_only is not True:
        return "activation pin is not paper-only"
    if not auto_paper_active(environ, activation, account_fingerprint=fingerprint):
        return "AUTO_PAPER activation checks failed"
    return None


def _artifact_snapshot(artifact: Mapping[str, Any]) -> dict[str, Any] | None:
    research = artifact.get("research")
    if not isinstance(research, dict):
        return None
    snapshot = research.get("snapshot")
    return snapshot if isinstance(snapshot, dict) else None


def _pinned_artifact(artifact_dir: Path, session_iso: str) -> dict[str, Any]:
    if not artifact_dir.is_dir():
        raise AutoPaperError(f"decision artifact directory {artifact_dir} does not exist")
    for path in sorted(artifact_dir.glob("*.json"), reverse=True):
        if path.name.startswith(("collection-", "collection-failed-", "auto-paper-")):
            continue
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        snapshot = _artifact_snapshot(artifact)
        if snapshot is None or artifact.get("status") != "COMPLETED":
            continue
        if str(artifact.get("mode")) not in DECISION_ARTIFACT_MODES:
            continue
        if str(artifact.get("strategy_version")) != STRATEGY_VERSION:
            continue
        if str(snapshot.get("spy_session_date")) != session_iso:
            continue
        return artifact
    raise AutoPaperError(
        f"no COMPLETED {STRATEGY_VERSION} decision artifact in {artifact_dir} "
        f"covers session {session_iso}"
    )


def _verify_signal(
    artifact: Mapping[str, Any], snapshot: ResearchSnapshot, policy: ExposurePolicy
) -> None:
    pinned = _artifact_snapshot(artifact)
    if pinned is None:
        raise AutoPaperError("decision artifact carries no research snapshot")
    keys = ["market_state", "direction", "target_symbol"]
    if policy.version != POLICY_VERSION_V1:
        keys += ["target_exposure_fraction", "exposure_tier"]
    for key in keys:
        pinned_value = pinned.get(key)
        actual = getattr(snapshot, key)
        if str(pinned_value) != str(actual):
            raise AutoPaperError(
                f"decision artifact {key}={pinned_value!r} does not match the "
                f"recomputed {actual!r}"
            )


def _held_strategy_symbol(account: AccountSnapshot) -> str | None:
    for position in account.positions:
        if position.quantity > 0 and position.symbol in CANDIDATE_SYMBOLS:
            return position.symbol
    return None


def _holding_entry_session(
    ledger: SQLiteLedger, account: AccountSnapshot, session_iso: str, now: datetime
) -> str | None:
    """Track 3x entry sessions through append-only AUTO_PAPER_ENTRY/EXIT events.

    The entry clock starts at the executor's first observation of a strategy
    position (autonomous or supervised) and ends when the position disappears.
    """
    symbol = _held_strategy_symbol(account)
    if symbol is None:
        return None
    entry = ledger.latest_event_payload("AUTO_PAPER_ENTRY", symbol)
    exit_event = ledger.latest_event_payload("AUTO_PAPER_EXIT", symbol)
    if entry is None or (exit_event is not None and exit_event[1] > entry[1]):
        ledger.append_event(
            "AUTO_PAPER_ENTRY",
            now,
            None,
            "auto_paper_executor",
            {"symbol": symbol, "session": session_iso},
        )
        return session_iso
    return str(entry[0].get("session") or session_iso)


def _record_exit_if_position_gone(
    ledger: SQLiteLedger, account: AccountSnapshot, session_iso: str, now: datetime
) -> None:
    if _held_strategy_symbol(account) is not None:
        return
    entry = ledger.latest_event_payload("AUTO_PAPER_ENTRY")
    if entry is None:
        return
    exit_event = ledger.latest_event_payload("AUTO_PAPER_EXIT")
    if exit_event is not None and exit_event[1] > entry[1]:
        return
    ledger.append_event(
        "AUTO_PAPER_EXIT",
        now,
        None,
        "auto_paper_executor",
        {"symbol": str(entry[0].get("symbol")), "session": session_iso},
    )


def _leveraged_reentry_blocked_through(
    ledger: SQLiteLedger, history: MarketHistory, session_iso: str
) -> str | None:
    """Block 3x re-entry for the session after a holding-duration exit."""
    exit_event = ledger.latest_event_payload("LEVERAGED_DURATION_EXIT")
    if exit_event is None:
        return None
    exit_session = str(exit_event[0].get("session") or "")
    sessions = history.session_dates()
    for index, session in enumerate(sessions):
        if session == exit_session and index + 1 < len(sessions):
            return sessions[index + 1]
    return None


def _account_is_fresh(account: AccountSnapshot, fingerprint: str, now: datetime) -> str | None:
    age = (now - account.as_of_utc).total_seconds()
    if age < -CLOCK_SKEW_TOLERANCE_SECONDS or age > MAX_ACCOUNT_AGE_SECONDS:
        return f"account snapshot is not fresh (age {age:.0f}s)"
    if account.account_fingerprint != fingerprint:
        return "account snapshot does not match the configured competition fingerprint"
    if not account.reconciled or account.unknown_orders:
        return "account state is not reconciled"
    return None


def _order_summary(order: object) -> dict[str, object]:
    return {
        "client_order_key": order.client_order_key,
        "broker_order_id": order.broker_order_id,
        "status": order.status.value,
        "fills": [fill.model_dump(mode="json") for fill in order.fills],
    }


def run_execution(
    *,
    now: datetime,
    environ: Mapping[str, str],
    bars_path: Path,
    artifact_dir: Path,
    output_dir: Path,
    ledger: SQLiteLedger,
    stack: SupervisedExecution,
    fingerprint: str,
) -> tuple[int, dict[str, object]]:
    """Run one AUTO_PAPER execution window. Returns (exit_code, report)."""
    if not stack.order_writes_enabled:
        return 1, _abstain("execution stack was built without order writes", now)
    if not fingerprint:
        return 1, _abstain("competition account fingerprint is not configured", now)
    activation = ledger.latest_trading_activation()
    if block := _auto_paper_block(environ, activation, fingerprint):
        return 1, _abstain(block, now)
    if ledger.kill_switch_engaged():
        return 1, _abstain("kill switch is engaged", now)
    if ledger.has_unknown_submissions():
        return 1, _abstain(
            "an UNKNOWN submission exists; reconcile it before autonomous trading", now
        )
    try:
        history, _validation = _load_bars(bars_path, now, "session")
    except (CollectionError, OSError, ValueError) as exc:
        return 1, _abstain(f"bar validation failed: {exc}", now)
    session_iso = history.last_completed_session().isoformat()
    try:
        artifact = _pinned_artifact(artifact_dir, session_iso)
        policy = exposure_policy_for_activation(activation)
        snapshot = screen(history, now, STRATEGY_VERSION, exposure_policy=policy)
        _verify_signal(artifact, snapshot, policy)
    except AutoPaperError as exc:
        return 1, _abstain(str(exc), now)
    try:
        account = stack.reads.get_account_snapshot()
    except Exception as exc:
        return 1, _abstain(f"account read failed ({type(exc).__name__})", now)
    if stale := _account_is_fresh(account, fingerprint, now):
        return 1, _abstain(stale, now)

    holding_entry_session = _holding_entry_session(ledger, account, session_iso, now)
    _record_exit_if_position_gone(ledger, account, session_iso, now)
    blocked_through = _leveraged_reentry_blocked_through(ledger, history, session_iso)
    decision_snapshot, proposal = decide(
        snapshot,
        history,
        account,
        exposure_policy=policy,
        holding_entry_session=holding_entry_session,
        leveraged_reentry_blocked_through=blocked_through,
    )
    ledger.append_event(
        "AUTO_PAPER_DECISION",
        now,
        getattr(proposal, "run_id", None),
        "auto_paper_executor",
        {
            "session": session_iso,
            "policy_version": policy.version,
            "exposure_tier": decision_snapshot.exposure_tier,
            "target_exposure_fraction": (
                str(decision_snapshot.target_exposure_fraction)
                if decision_snapshot.target_exposure_fraction is not None
                else None
            ),
            "action": decision_snapshot.action,
            "symbol": getattr(proposal, "symbol", None),
            "requested_quantity": getattr(proposal, "requested_quantity", 0),
            "reason": decision_snapshot.decision_reason,
        },
        getattr(proposal, "proposal_id", None),
    )
    if decision_snapshot.duration_exit and decision_snapshot.current_symbol:
        ledger.append_event(
            "LEVERAGED_DURATION_EXIT",
            now,
            getattr(proposal, "run_id", None),
            "auto_paper_executor",
            {"symbol": decision_snapshot.current_symbol, "session": session_iso},
            getattr(proposal, "proposal_id", None),
        )
    base_report = {
        "schema_version": "1",
        "mode": "AUTO_PAPER_EXECUTION",
        "status": "COMPLETED",
        "executed_at_utc": now.isoformat(),
        "session": session_iso,
        "policy_version": policy.version,
        "exposure_tier": decision_snapshot.exposure_tier,
        "target_exposure_fraction": (
            str(decision_snapshot.target_exposure_fraction)
            if decision_snapshot.target_exposure_fraction is not None
            else None
        ),
        "market_state": decision_snapshot.market_state,
        "target_symbol": decision_snapshot.target_symbol,
        "action": decision_snapshot.action,
        "decision_reason": decision_snapshot.decision_reason,
        "submission_performed": False,
    }
    if proposal is None:
        base_report["outcome"] = decision_snapshot.action
        return 0, base_report

    if ledger.submission_for_proposal(proposal.proposal_id) is not None:
        return 1, _abstain(f"proposal {proposal.proposal_id} was already submitted", now)
    try:
        quote = stack.quote_feed.get_quote(proposal.symbol, now)
    except Exception as exc:
        return 1, _abstain(
            f"no fresh regular-session quote for {proposal.symbol} ({type(exc).__name__})",
            now,
        )
    if not quote.regular_session_open:
        return 1, _abstain(f"{proposal.symbol} is not in the regular US session", now)

    result = stack.service.execute(proposal, quote, now)
    base_report.update(
        {
            "symbol": proposal.symbol,
            "requested_quantity": proposal.requested_quantity,
            "proposal_id": proposal.proposal_id,
            "policy_decision": result.decision.decision.value,
            "policy_rules": [
                {"rule_id": item.rule_id, "message": item.message}
                for item in result.decision.reasons
            ],
        }
    )
    if result.decision.decision is PolicyDecision.REJECT:
        reject = {
            **base_report,
            **_abstain(
                "RiskGate rejected the proposal: "
                + "; ".join(item.message for item in result.decision.reasons)
                or "no reason recorded",
                now,
            ),
            "outcome": "POLICY_REJECTED",
        }
        return 1, reject
    order = result.order
    if order is None:
        return 1, _abstain("execution produced no order record", now)
    base_report["submission_performed"] = True

    client_order_key = build_client_order_key(
        proposal.strategy_version, proposal.proposal_id
    )
    reconciled = None
    try:
        reconciled = stack.service.reconcile(client_order_key, now)
    except Exception:
        reconciled = None
    final_order = reconciled or order
    base_report["outcome"] = final_order.status.value
    base_report["order"] = _order_summary(final_order)
    if reconciled is not None:
        base_report["reconciled"] = True
    ledger.append_event(
        "AUTO_PAPER_EXECUTION_RUN",
        now,
        proposal.run_id,
        "auto_paper_executor",
        {
            "session": session_iso,
            "symbol": proposal.symbol,
            "action": proposal.action.value,
            "requested_quantity": proposal.requested_quantity,
            "order_status": final_order.status.value,
            "broker_order_id": final_order.broker_order_id,
            "reconciled": reconciled is not None,
        },
        proposal.proposal_id,
    )
    if final_order.status is OrderStatus.UNKNOWN:
        base_report["status"] = "UNKNOWN"
        base_report["outcome"] = "ORDER_UNKNOWN"
        return 3, base_report
    return 0, base_report


def _execution_stack(
    args: argparse.Namespace, ledger: SQLiteLedger, lock: AccountLock
) -> SupervisedExecution:
    store_path = Path(args.store) if args.store else default_execution_token_path()
    store = FileTokenStore(store_path)
    record = store.load()
    if record is None:
        raise AutoPaperError("execution authorization is required")
    if not record.access_token:
        raise AutoPaperError(
            "execution client has no authorization token; complete moomoo-execution-login"
        )
    if not record.has_required_scopes():
        raise AutoPaperError("execution token lacks quote/account read access")
    if not record.has_trade_write():
        raise AutoPaperError("execution authorization did not grant trade:write")
    activation = ledger.latest_trading_activation()
    risk_gate = RiskGate.from_activation(activation) if activation is not None else None
    return build_supervised_execution(
        MoomooExecutionOAuth(store, open_browser=None),
        lock,
        ledger,
        order_writes_enabled=True,
        risk_gate=risk_gate,
    )


def _emit(
    output_dir: Path, exit_code: int, report: dict[str, object], now: datetime
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"auto-paper-{now:%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(PAPER_BANNER)
    print(f"Report: {path}")
    print(f"Status: {report['status']}; outcome: {report.get('outcome', 'ABSTAINED')}")
    print(f"Submission performed: {report.get('submission_performed', False)}")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AUTO_PAPER execution phase for the spy-directional strategy"
    )
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args(argv)

    load_local_env(Path(args.env_file))
    now = datetime.now(UTC)
    output_dir = args.output_dir or args.artifact_dir
    try:
        lock = AccountLock.from_env(os.environ)
    except Exception as exc:
        return _emit(
            output_dir,
            1,
            _abstain(f"account lock is not configured ({type(exc).__name__})", now),
            now,
        )
    ledger = SQLiteLedger(args.ledger or ledger_path_from_env(os.environ))
    try:
        stack = _execution_stack(args, ledger, lock)
    except AutoPaperError as exc:
        return _emit(output_dir, 1, _abstain(str(exc), now), now)
    exit_code, report = run_execution(
        now=now,
        environ=os.environ,
        bars_path=args.bars,
        artifact_dir=args.artifact_dir,
        output_dir=output_dir,
        ledger=ledger,
        stack=stack,
        fingerprint=lock.expected_fingerprint,
    )
    return _emit(output_dir, exit_code, report, now)


if __name__ == "__main__":
    raise SystemExit(main())
