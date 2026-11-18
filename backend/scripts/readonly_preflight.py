"""Record a sanitized read-only preflight artifact.

The artifact is evidence for the dashboard. It evaluates real broker reads with
the deterministic RiskGate and never contacts an order endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.broker.account_lock import AccountLock
from app.broker.moomoo_auth import FileTokenStore, MoomooOAuth, default_token_path
from app.broker.moomoo_quotes import CLOCK_SKEW_TOLERANCE_SECONDS, MoomooQuoteFeed
from app.broker.moomoo_rest import MoomooRestBroker, MoomooRestClient
from app.cli import load_local_env
from app.ledger.store import SQLiteLedger
from app.models.contracts import ControlState, ProposalAction, Quote, TradeProposal
from app.risk.policy import RiskGate

ROOT = Path(__file__).resolve().parents[2]
SYMBOLS = ("SPY", "QQQ", "IWM")


class PreflightError(RuntimeError):
    pass


def _require_read_only(record) -> None:
    if record is None:
        raise PreflightError("Moomoo read authorization is required")
    if record.has_trade_write():
        raise PreflightError("stored authorization contains trade:write; refusing")
    if not record.has_required_scopes():
        raise PreflightError("stored authorization lacks required read scopes")


def collect(output_dir: Path) -> Path:
    load_local_env(ROOT / ".env")
    if os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower() not in {"false", "0", "no", ""}:
        raise PreflightError("ORDER_WRITES_ENABLED must remain false")

    store = FileTokenStore(default_token_path())
    record = store.load()
    _require_read_only(record)

    lock = AccountLock.from_env(os.environ)
    ledger = SQLiteLedger(ROOT / "data" / "mootrade.db")
    client = MoomooRestClient(MoomooOAuth(store, open_browser=None))
    broker = MoomooRestBroker(client, lock, ledger)
    feed = MoomooQuoteFeed(client)

    now = datetime.now(UTC)
    identity = broker.account_identity()
    account = broker.get_account_snapshot()
    if account.environment != "paper":
        raise PreflightError("account snapshot is not a paper account")
    if account.account_fingerprint != lock.expected_fingerprint:
        raise PreflightError("account snapshot does not match the configured competition fingerprint")
    account_age = (now - account.as_of_utc).total_seconds()
    if account_age < -CLOCK_SKEW_TOLERANCE_SECONDS:
        raise PreflightError("account snapshot is timestamped in the future")
    account_age = max(0.0, account_age)

    observations = {symbol: feed.observe_quote(symbol, now) for symbol in SYMBOLS}
    now = max(
        now,
        account.as_of_utc,
        *(observation.as_of_utc for observation in observations.values()),
    )
    account_age = max(0.0, (now - account.as_of_utc).total_seconds())
    risk_symbol = "QQQ"
    observation = observations[risk_symbol]
    quote = Quote(
        symbol=risk_symbol,
        price=observation.price,
        as_of_utc=observation.as_of_utc,
        regular_session_open=observation.regular_session_open,
    )
    proposal = TradeProposal(
        proposal_id=f"diagnostic-preflight-{now:%Y%m%dT%H%M%SZ}",
        run_id="readonly-preflight",
        strategy_version="operator-preview",
        decision_time_utc=now,
        data_as_of_utc=observation.as_of_utc,
        symbol=risk_symbol,
        action=ProposalAction.BUY,
        requested_quantity=1,
        thesis="Diagnostic read-only risk evaluation; no order will be submitted.",
        invalidation="Evidence capture only.",
    )
    control = ControlState(
        order_writes_enabled=False,
        kill_switch_engaged=ledger.kill_switch_engaged(),
        first_order_approved=ledger.order_approval_count() > 0,
    )
    decision = RiskGate(expected_account_fingerprint=lock.expected_fingerprint).evaluate(
        proposal=proposal,
        account=account,
        quote=quote,
        control=control,
        now=now,
        duplicate=ledger.submission_for_proposal(proposal.proposal_id) is not None,
        unknown_submission=ledger.has_unknown_submissions(),
    )

    payload = {
        "schema_version": "1",
        "kind": "REAL_READ_ONLY_PREFLIGHT",
        "mode": "PAPER",
        "checked_at_utc": now.isoformat(),
        "account": {
            "masked_id": identity.masked_id,
            "market_id": identity.market_id,
            "account_type": identity.account_type,
            "title": identity.title,
            "fingerprint_matches": True,
            "equity_usd": str(account.equity),
            "cash_usd": str(account.cash),
            "buying_power_usd": str(account.buying_power),
            "positions": len(account.positions),
            "open_orders": len(account.open_orders),
            "reconciled": account.reconciled,
            "unknown_orders": account.unknown_orders,
            "snapshot_as_of_utc": account.as_of_utc.isoformat(),
            "age_seconds": account_age,
        },
        "quotes": {
            symbol: {
                "last_price": float(item.price),
                "data_time_utc": item.as_of_utc.isoformat(),
                "age_seconds": round(item.age_seconds, 1),
                "sec_status": item.sec_status,
                "suspension": item.suspended,
                "market_state": item.market_state,
            }
            for symbol, item in observations.items()
        },
        "diagnostic_preview": {
            "submission_performed": False,
            "order_transport_available": False,
            "note": "No order endpoint is implemented or contacted by this collector.",
        },
        "diagnostic_risk_evaluation": {
            "note": (
                "RiskGate evaluated a real diagnostic proposal to record deterministic "
                "rejection reasons. This is not an executable approval."
            ),
            "decision": decision.decision.value,
            "approved_quantity": decision.approved_quantity,
            "rejection_rule_ids": [reason.rule_id for reason in decision.reasons],
            "reasons": [
                f"{reason.rule_id} {reason.message}" for reason in decision.reasons
            ],
            "quote_fresh": max(0.0, (now - quote.as_of_utc).total_seconds()) <= 300,
            "regular_session_open": quote.regular_session_open,
            "trading_status_normal": all(
                item.sec_status == "NORMAL" and not item.suspended
                for item in observations.values()
            ),
            "suspended": any(item.suspended for item in observations.values()),
            "account_fresh": 0 <= account_age <= 60,
        },
        "safety": {
            "order_writes_enabled": False,
            "submissions_in_ledger": ledger.submission_count(),
            "unknown_submissions": ledger.has_unknown_submissions(),
            "order_endpoint_contacted": False,
            "oauth_scope_trade_write": record.has_trade_write(),
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"preflight-{now:%Y-%m-%dT%H%M%SZ}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record a read-only preflight artifact")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "evidence" / "preflight"
    )
    args = parser.parse_args(argv)
    try:
        path = collect(args.output_dir)
    except Exception as exc:
        print(f"Read-only preflight failed closed: {str(exc) or exc.__class__.__name__}")
        return 1
    print(f"Recorded read-only preflight evidence: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
