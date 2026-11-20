"""Operator-only commands.

Only ``moomoo-supervised-execute`` can submit, and only when its write flag and
exact client-order-key confirmation are both supplied after durable approval.
All other commands are read-only or dry-run.
"""

import argparse
import getpass
import json
import os
import webbrowser
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.broker.account_lock import AccountLock, AccountLockError, fingerprint_account_id
from app.broker.moomoo_auth import (
    FileTokenStore,
    MoomooAuthError,
    MoomooExecutionOAuth,
    MoomooOAuth,
    OAuthScopeError,
    default_execution_token_path,
    default_token_path,
    scope_summary,
)
from app.broker.moomoo_orders import (
    MoomooSimulatedOrderAdapter,
    OrderAdapterError,
    reconcile_unknown_order,
)
from app.broker.moomoo_quotes import MoomooQuoteFeed
from app.broker.moomoo_rest import (
    MAX_HISTORY_PAGES,
    MoomooRestBroker,
    MoomooRestClient,
    MoomooRestError,
)
from app.ledger.store import SQLiteLedger
from app.models.contracts import (
    AccountSnapshot,
    ControlState,
    OrderRequest,
    OrderSide,
    OrderStatus,
    PolicyDecision,
    ProposalAction,
    Quote,
    RiskDecision,
    TradeProposal,
    TradingActivation,
)
from app.research.instruments import INSTRUMENTS
from app.research.strategy import STRATEGY_VERSION
from app.risk.policy import POLICY_VERSION_V3, RiskGate
from app.service import build_client_order_key
from app.supervised import build_supervised_execution
from app.trading_mode import (
    SUPERVISED_EXECUTION_SYMBOLS,
    TradingModeError,
    build_auto_paper_activation,
    resolve_trading_mode,
)

_LOCAL_ENV_KEYS = {
    "COMPETITION_ACCOUNT_MASKED_ID",
    "COMPETITION_ACCOUNT_FINGERPRINT",
    "COMPETITION_ACCOUNT_MARKET_ID",
    "DATABASE_URL",
    "DASHBOARD_ORIGIN",
    "MOOTRADE_API_HOST",
    "MOOTRADE_API_PORT",
    "MOOTRADE_DASHBOARD_ORIGINS",
    "MOOTRADE_DASHBOARD_TOKEN",
    "MOOTRADE_EVIDENCE_DIR",
    "MOOTRADE_OAUTH_STORE",
    "MOOTRADE_EXECUTION_OAUTH_STORE",
    "MOOTRADE_PROJECT_ROOT",
    "ORDER_WRITES_ENABLED",
    "TRADING_MODE",
}


def ledger_path_from_env(environ: Mapping[str, str]) -> str:
    url = environ.get("DATABASE_URL", "sqlite:///./data/mootrade.db")
    prefix = "sqlite:///"
    if not url.startswith(prefix) or not url[len(prefix) :]:
        raise SystemExit("DATABASE_URL must be a local sqlite:/// path")
    path = Path(url[len(prefix) :])
    if not path.is_absolute():
        # Anchor relative paths at the project root so scheduled tasks, which
        # run with cwd=backend, never create a second ledger there.
        root_raw = environ.get("MOOTRADE_PROJECT_ROOT", "").strip()
        root = Path(root_raw) if root_raw else Path(__file__).resolve().parents[2]
        path = root / path
    return str(path)


def load_local_env(path: Path) -> None:
    """Load only competition/ledger keys; never load Qoder or broker credentials."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in _LOCAL_ENV_KEYS:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _token_store(path: str | None) -> FileTokenStore:
    return FileTokenStore(Path(path) if path else default_token_path())


def _oauth(path: str | None, *, open_browser: bool = True) -> MoomooOAuth:
    return MoomooOAuth(
        _token_store(path),
        open_browser=webbrowser.open if open_browser else None,
    )


def _execution_token_store(path: str | None) -> FileTokenStore:
    return FileTokenStore(Path(path) if path else default_execution_token_path())


def _execution_oauth(path: str | None, *, open_browser: bool = True) -> MoomooExecutionOAuth:
    return MoomooExecutionOAuth(
        _execution_token_store(path),
        open_browser=webbrowser.open if open_browser else None,
    )


def _execution_authorization(path: str | None, *, require_write: bool):
    record = _execution_token_store(path).load()
    if record is None:
        raise MoomooAuthError("execution authorization is required")
    if not record.access_token:
        raise MoomooAuthError(
            "execution client registration exists but no authorization token is present; "
            "complete `moomoo-execution-login`"
        )
    if not record.has_required_scopes():
        raise OAuthScopeError("execution token lacks quote/account read access")
    if require_write and not record.has_trade_write():
        raise OAuthScopeError("execution authorization did not grant trade:write")
    return record


def _supervised_stack(
    args,
    *,
    order_writes_enabled: bool,
    require_write: bool,
):
    load_local_env(Path(args.env_file))
    lock = AccountLock.from_env(os.environ)
    ledger = SQLiteLedger(args.ledger or ledger_path_from_env(os.environ))
    record = _execution_authorization(args.store, require_write=require_write)
    stack = build_supervised_execution(
        _execution_oauth(args.store, open_browser=False),
        lock,
        ledger,
        order_writes_enabled=order_writes_enabled,
    )
    return stack, lock, ledger, record


def _supervised_proposal(args, quote, now: datetime | None = None) -> TradeProposal:
    if args.proposal_file:
        try:
            proposal = TradeProposal.model_validate_json(
                Path(args.proposal_file).read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ValueError("Proposal file could not be read or is not a valid TradeProposal") from exc
        expected = {
            "symbol": args.symbol,
            "action": ProposalAction(args.action),
            "requested_quantity": args.quantity,
            "proposal_id": args.proposal_id,
            "strategy_version": args.strategy_version,
            "thesis": args.thesis,
            "invalidation": args.invalidation,
        }
        mismatches = [name for name, value in expected.items() if getattr(proposal, name) != value]
        if mismatches:
            raise ValueError("Proposal file does not match flags: " + ", ".join(mismatches))
        return proposal
    decision_time = now or max(datetime.now(UTC), quote.as_of_utc)
    return TradeProposal(
        proposal_id=args.proposal_id,
        run_id="supervised-paper-order",
        strategy_version=args.strategy_version,
        decision_time_utc=decision_time,
        data_as_of_utc=quote.as_of_utc,
        symbol=args.symbol,
        action=ProposalAction(args.action),
        requested_quantity=args.quantity,
        thesis=args.thesis,
        invalidation=args.invalidation,
    )


def _require_current_policy_proposal(proposal: TradeProposal) -> None:
    """Refuse research proposals whose ID predates risk-v3.

    risk-v3 embeds the policy version in spy-directional proposal IDs, so a
    proposal without it (e.g. the superseded 576-SH BUY) can never be
    submitted under the new tiers, even with a fresh approval attempt.
    """
    if (
        proposal.strategy_version == STRATEGY_VERSION
        and POLICY_VERSION_V3 not in proposal.proposal_id
    ):
        raise ValueError(
            f"Proposal {proposal.proposal_id!r} predates {POLICY_VERSION_V3}; "
            "generate a fresh proposal under the current policy."
        )


def _reconciliation_outcome(ledger: SQLiteLedger, proposal_id: str) -> str:
    events = [
        event
        for event in ledger.list_events()
        if event["correlation_id"] == proposal_id
        and event["event_type"]
        in {"RECONCILIATION_OK", "RECONCILIATION_MISMATCH"}
    ]
    return events[-1]["event_type"] if events else "NOT_ATTEMPTED"


def _preview_rule_statuses(
    proposal: TradeProposal,
    decision: RiskDecision,
    gate: RiskGate,
    *,
    hypothetical_writes_enabled: bool,
) -> dict[str, object]:
    checks = {
        "R001": "Exact competition paper account",
        "R002": "Approved instrument allowlist",
        "R003": "Long-only order quantity",
        "R006": "Daily drawdown",
        "R007": "Fresh, valid account and quote data",
        "R008": "Unlevered buying power after buffer",
        "R009": "Clean reconciliation and no unknown submissions",
        "R010": "Write controls, kill switch and circuit breaker",
        "R011": "No duplicate submission",
        "R012": "Regular exchange session",
        "R013": "Post-order position count",
        "R014": "Exact durable owner approval for this order",
        "R015": "Separate leverage approval and maximum leverage",
        "R016": "Minimum effective exposure floor",
        "R017": "Maximum post-order signed effective exposure",
        "R018": "Declared target exposure consistency",
        "R019": "Competition single-security 40% concentration cap",
    }
    statuses = {}
    for rule_id, label in checks.items():
        failures = [reason.message for reason in decision.reasons if reason.rule_id == rule_id]
        not_applicable = None
        if proposal.action is ProposalAction.SELL and rule_id in {"R006", "R008", "R013", "R016", "R017", "R018", "R019"}:
            not_applicable = "BUY-only check; not applied to SELL"
        elif rule_id == "R016" and not gate.enforce_min_exposure:
            not_applicable = "Exposure floor disabled for supervised orders"
        elif rule_id == "R018" and proposal.target_exposure_fraction is None:
            not_applicable = "No declared target exposure"
        statuses[rule_id] = {
            "status": "FAIL" if failures else "N/A" if not_applicable else "PASS",
            "check": label,
            "note": "; ".join(failures) if failures else not_applicable,
        }
    statuses["R010"].update({
        "evaluated_order_writes_enabled": hypothetical_writes_enabled,
        "actual_order_writes_enabled": False,
        "scope": (
            "Hypothetical writes enabled for risk evaluation; actual transport writes disabled"
            if hypothetical_writes_enabled else "Actual writes disabled; no hypothetical override"
        ),
    })
    return statuses


def _preview_exposure(
    proposal: TradeProposal, snapshot: AccountSnapshot, quote: Quote, gate: RiskGate
) -> dict[str, object]:
    def multiplier(symbol: str) -> Decimal:
        direction = INSTRUMENTS[symbol].direction if symbol in INSTRUMENTS else Decimal("1")
        return gate.leverage_by_symbol.get(symbol, Decimal("1")) * direction

    def amounts(notional: Decimal, effective: Decimal) -> dict[str, object]:
        return {
            "notional": str(notional),
            "equity_fraction": str(notional / snapshot.equity) if snapshot.equity > 0 else None,
            "signed_effective_notional": str(effective),
            "signed_effective_equity_fraction": (
                str(effective / snapshot.equity) if snapshot.equity > 0 else None
            ),
        }

    held_notional = sum((item.market_value for item in snapshot.positions), Decimal("0"))
    held_effective = sum(
        (item.market_value * multiplier(item.symbol) for item in snapshot.positions), Decimal("0")
    )
    pending_buys = [item for item in snapshot.open_orders if item.side is OrderSide.BUY]
    pending_notional = sum(
        (item.reference_price * item.remaining_quantity for item in pending_buys), Decimal("0")
    )
    pending_effective = sum(
        (item.reference_price * item.remaining_quantity * multiplier(item.symbol) for item in pending_buys),
        Decimal("0"),
    )
    current_notional = held_notional + pending_notional
    current_effective = held_effective + pending_effective
    delta = quote.price * proposal.requested_quantity * (1 if proposal.action is ProposalAction.BUY else -1)
    effective_delta = delta * multiplier(proposal.symbol)
    return {
        "currency": "USD",
        "equity": str(snapshot.equity),
        "basis": (
            "Positions plus pending BUY orders; pending SELL orders are not credited. "
            "Post-order estimate assumes only the proposed order fills at the quote price, not a confirmed fill."
        ),
        "positions": amounts(held_notional, held_effective),
        "pending_buys": amounts(pending_notional, pending_effective),
        "current": amounts(current_notional, current_effective),
        "proposed_delta": amounts(delta, effective_delta),
        "post_order": amounts(current_notional + delta, current_effective + effective_delta),
    }


def _activation_policy_fields(activation: TradingActivation) -> dict[str, object]:
    return {
        "min_effective_exposure_fraction": (
            str(activation.min_effective_exposure_fraction)
            if activation.min_effective_exposure_fraction is not None
            else None
        ),
        "max_effective_exposure_fraction": (
            str(activation.max_effective_exposure_fraction)
            if activation.max_effective_exposure_fraction is not None
            else None
        ),
        "max_daily_drawdown": str(activation.max_daily_drawdown),
        "expires_at_utc": (
            activation.expires_at_utc.isoformat()
            if activation.expires_at_utc is not None
            else None
        ),
    }


def _add_supervised_order_arguments(parser) -> None:
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--action", choices=["BUY", "SELL"], required=True)
    parser.add_argument("--quantity", type=int, required=True)
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--proposal-file", help="Exact TradeProposal JSON; order flags must match")
    parser.add_argument("--strategy-version", default="operator-supervised")
    parser.add_argument("--thesis", required=True)
    parser.add_argument("--invalidation", required=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mootrade")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "fingerprint-account",
        help="Print a SHA-256 fingerprint of a Moomoo acc_id without echoing the id",
    )

    approve = commands.add_parser(
        "approve-first-order",
        help="Record explicit owner approval for one paper order; never submits an order",
    )
    approve.add_argument("--proposal-id", required=True)
    approve.add_argument("--strategy-version", required=True)
    approve.add_argument("--ledger")
    approve.add_argument("--approved-by", default="owner")

    supersede_approval = commands.add_parser(
        "moomoo-supersede-approval",
        help="Mark one durable order approval superseded; never submits an order",
    )
    supersede_approval.add_argument("--proposal-id", required=True)
    supersede_approval.add_argument("--strategy-version", required=True)
    supersede_approval.add_argument("--confirm-supersede", action="store_true")
    supersede_approval.add_argument("--superseded-by", default="owner")
    supersede_approval.add_argument("--reason", required=True)
    supersede_approval.add_argument("--env-file", default=".env")
    supersede_approval.add_argument("--ledger")

    login = commands.add_parser(
        "moomoo-login",
        help="Authorize a local read-only Moomoo REST token through OAuth 2.1 + PKCE",
    )
    login.add_argument("--store")
    login.add_argument("--timeout", type=int, default=300)
    login.add_argument("--no-browser", action="store_true")

    status = commands.add_parser(
        "moomoo-auth-status",
        help="Show whether a local Moomoo OAuth token exists without printing it",
    )
    status.add_argument("--store")

    execution_login = commands.add_parser(
        "moomoo-execution-login",
        help="Authorize the separate simulated-order client through OAuth 2.1 + PKCE",
    )
    execution_login.add_argument("--store")
    execution_login.add_argument("--timeout", type=int, default=300)
    execution_login.add_argument("--no-browser", action="store_true")

    execution_status = commands.add_parser(
        "moomoo-execution-status",
        help="Show the separate execution token's scopes without printing it",
    )
    execution_status.add_argument("--store")

    execution_check = commands.add_parser(
        "moomoo-execution-check",
        help="Read-only account check with the execution token; never submits",
    )
    execution_check.add_argument("--store")
    execution_check.add_argument("--env-file", default=".env")
    execution_check.add_argument("--ledger")
    execution_check.add_argument("--max-pages", type=int, default=MAX_HISTORY_PAGES)

    read = commands.add_parser(
        "moomoo-read",
        help="Read the exact competition paper account through the read-only REST adapter",
    )
    read.add_argument("--store")
    read.add_argument("--env-file", default=".env")
    read.add_argument("--ledger")
    read.add_argument("--max-pages", type=int, default=MAX_HISTORY_PAGES)

    preview = commands.add_parser(
        "moomoo-preview-order",
        help="Preview a possible first paper order; never submits or enables writes",
    )
    preview.add_argument("--symbol", required=True)
    preview.add_argument("--action", choices=["BUY", "SELL"], required=True)
    preview.add_argument("--quantity", type=int, required=True)
    preview.add_argument("--proposal-id", required=True)
    preview.add_argument("--strategy-version", default="operator-preview")
    preview.add_argument("--thesis", default="Operator-requested preview; no strategy signal")
    preview.add_argument("--invalidation", default="Preview only; no order will be submitted")
    preview.add_argument("--store")
    preview.add_argument("--env-file", default=".env")
    preview.add_argument("--ledger")

    supervised_preview = commands.add_parser(
        "moomoo-supervised-preview",
        help="Evaluate one exact paper order with the execution client; never submits",
    )
    _add_supervised_order_arguments(supervised_preview)
    supervised_preview.add_argument("--store")
    supervised_preview.add_argument("--env-file", default=".env")
    supervised_preview.add_argument("--ledger")

    supervised_execute = commands.add_parser(
        "moomoo-supervised-execute",
        help="Submit one pre-approved paper order after exact-key confirmation",
    )
    _add_supervised_order_arguments(supervised_execute)
    supervised_execute.add_argument("--confirm-client-order-key", required=True)
    supervised_execute.add_argument("--enable-order-writes", action="store_true")
    supervised_execute.add_argument("--store")
    supervised_execute.add_argument("--env-file", default=".env")
    supervised_execute.add_argument("--ledger")

    supervised_reconcile = commands.add_parser(
        "moomoo-supervised-reconcile",
        help="Read-only broker reconciliation for one supervised client order key",
    )
    supervised_reconcile.add_argument("--client-order-key", required=True)
    supervised_reconcile.add_argument("--store")
    supervised_reconcile.add_argument("--env-file", default=".env")
    supervised_reconcile.add_argument("--ledger")

    resolve_unknown = commands.add_parser(
        "moomoo-supervised-resolve-unknown",
        help=(
            "Resolve one UNKNOWN submission to REJECTED after re-verifying the broker "
            "has no matching order. Requires explicit confirmation; never submits."
        ),
    )
    resolve_unknown.add_argument("--client-order-key", required=True)
    resolve_unknown.add_argument("--confirm-resolve", action="store_true")
    resolve_unknown.add_argument("--store")
    resolve_unknown.add_argument("--env-file", default=".env")
    resolve_unknown.add_argument("--ledger")

    auto_paper_status = commands.add_parser(
        "moomoo-auto-paper-status",
        help="Show the trading mode, write flag and durable AUTO_PAPER activation state",
    )
    auto_paper_status.add_argument("--env-file", default=".env")
    auto_paper_status.add_argument("--ledger")

    auto_paper_activate = commands.add_parser(
        "moomoo-activate-auto-paper",
        help=(
            "Record the explicit, durable AUTO_PAPER activation pin for the exact "
            "competition paper account, strategy, symbols, policy version and limits. "
            "Requires TRADING_MODE=AUTO_PAPER and ORDER_WRITES_ENABLED=true in the environment. "
            "Never submits an order."
        ),
    )
    auto_paper_activate.add_argument("--confirm-auto-paper", action="store_true")
    auto_paper_activate.add_argument("--authorized-by", default="owner")
    auto_paper_activate.add_argument(
        "--expires-at",
        help="Optional ISO 8601 UTC deadline after which the pin stops authorising execution",
    )
    auto_paper_activate.add_argument("--env-file", default=".env")
    auto_paper_activate.add_argument("--ledger")

    kill_switch = commands.add_parser(
        "moomoo-kill-switch",
        help=(
            "Show, engage or release the persistent kill switch. Engaging blocks "
            "new paper orders; it never liquidates holdings. Every state change "
            "is an explicit, logged audit event and requires a confirmation flag."
        ),
    )
    kill_switch.add_argument("--engage", action="store_true")
    kill_switch.add_argument("--confirm-engage", action="store_true")
    kill_switch.add_argument("--release", action="store_true")
    kill_switch.add_argument("--confirm-release", action="store_true")
    kill_switch.add_argument("--env-file", default=".env")
    kill_switch.add_argument("--ledger")

    args = parser.parse_args(argv)
    file_proposal = None
    if args.command in {"moomoo-supervised-preview", "moomoo-supervised-execute"} and args.proposal_file:
        try:
            # Validate once before any ledger or broker access; preserve the
            # exact file proposal through the later fresh-quote risk check.
            file_proposal = _supervised_proposal(args, None)
        except ValueError as exc:
            print(f"Supervised proposal failed closed: {exc}")
            return 1

    if args.command == "fingerprint-account":
        account_id = getpass.getpass("Moomoo acc_id (hidden): ").strip()
        if not account_id:
            raise SystemExit("no account id provided")
        print(fingerprint_account_id(account_id))
        return 0

    if args.command == "moomoo-login":
        try:
            oauth = _oauth(args.store, open_browser=not args.no_browser)
            record = oauth.login(
                timeout_seconds=args.timeout,
                on_url=lambda url: print(
                    "Open this URL and authorize Moomoo read-only access:\n"
                    f"{url}\n"
                    "Select every read-only permission, including quote and "
                    "account/positions/orders read. Do not grant trade:write.\n"
                    "Waiting for the local callback...",
                    flush=True,
                ),
            )
        except (MoomooAuthError, OSError) as exc:
            print(f"Moomoo authorization failed: {exc}")
            return 1
        print("Moomoo read-only authorization stored outside the repository.")
        print(f"Access token expires at {record.expires_at.isoformat()}.")
        print(f"Granted scopes: {json.dumps(scope_summary(record.scope))}")
        return 0

    if args.command == "moomoo-auth-status":
        try:
            store = _token_store(args.store)
            record = store.load()
        except MoomooAuthError as exc:
            print(f"Moomoo authorization status unavailable: {exc}")
            return 1
        if record is None:
            print("No local Moomoo OAuth authorization. Run `moomoo-login` first.")
            return 1
        expiry = record.expires_at.isoformat() if record.expires_at else "unknown"
        print("Moomoo OAuth authorization present.")
        print(f"Access token present: {bool(record.access_token)} (expires {expiry})")
        print(f"Refresh token present: {bool(record.refresh_token)}")
        print(f"Granted scopes: {json.dumps(scope_summary(record.scope))}")
        return 0

    if args.command == "moomoo-execution-login":
        try:
            oauth = _execution_oauth(args.store, open_browser=not args.no_browser)
            record = oauth.login(
                timeout_seconds=args.timeout,
                on_url=lambda url: print(
                    "Open this URL to authorize the separate MooTrade paper-execution client:\n"
                    f"{url}\n"
                    "This client requests quote/account read plus trade:write for simulated "
                    "order placement. The provider has not proven that trade:write is limited "
                    "to the competition paper account. Authorize only if you accept that scope. "
                    "Order writes remain disabled after consent.\n"
                    "Waiting for the local callback...",
                    flush=True,
                ),
            )
        except (MoomooAuthError, OSError) as exc:
            print(f"Moomoo execution authorization failed: {exc}")
            return 1
        print("Moomoo execution authorization stored separately, outside the repository.")
        print(f"Access token expires at {record.expires_at.isoformat()}.")
        print(f"Granted scopes: {json.dumps(scope_summary(record.scope))}")
        print("Account-exclusive write scope: UNVERIFIED by the provider.")
        return 0

    if args.command == "moomoo-execution-status":
        try:
            record = _execution_token_store(args.store).load()
        except MoomooAuthError as exc:
            print(f"Moomoo execution authorization status unavailable: {exc}")
            return 1
        if record is None:
            print("No separate execution authorization. Run `moomoo-execution-login` first.")
            return 1
        if not record.access_token:
            print(
                "Execution client registration exists, but no authorization token is present."
            )
            print("Complete `moomoo-execution-login` in the browser.")
            print(f"Granted scopes: {json.dumps(scope_summary(record.scope))}")
            return 1
        expiry = record.expires_at.isoformat() if record.expires_at else "unknown"
        print("Moomoo execution authorization present.")
        print(f"Access token present: {bool(record.access_token)} (expires {expiry})")
        print(f"Refresh token present: {bool(record.refresh_token)}")
        print(f"Granted scopes: {json.dumps(scope_summary(record.scope))}")
        print(f"trade:write granted: {record.has_trade_write()}")
        print("Account-exclusive write scope: UNVERIFIED by the provider.")
        return 0

    if args.command == "moomoo-execution-check":
        load_local_env(Path(args.env_file))
        try:
            record = _execution_token_store(args.store).load()
            if record is None:
                raise MoomooAuthError("execution authorization is required")
            if not record.has_required_scopes() or not record.has_trade_write():
                raise MoomooAuthError("execution token lacks the required scopes")
            lock = AccountLock.from_env(os.environ)
            ledger = SQLiteLedger(args.ledger or ledger_path_from_env(os.environ))
            broker = MoomooRestBroker(
                MoomooRestClient(_execution_oauth(args.store, open_browser=False)),
                lock,
                ledger,
            )
            identity = broker.account_identity()
            snapshot = broker.get_account_snapshot()
            history = broker.get_order_history(max_pages=args.max_pages)
        except (MoomooAuthError, MoomooRestError, AccountLockError, ValueError) as exc:
            print(f"Moomoo execution account check failed: {exc}")
            return 1
        report = {
            "mode": "PAPER",
            "execution_authorization": True,
            "read_only_check": True,
            "order_endpoint_contacted": False,
            "order_writes": "disabled",
            "granted_scopes": scope_summary(record.scope),
            "account_exclusive_write_scope_verified": False,
            "account": {
                "masked_id": identity.masked_id,
                "market_id": identity.market_id,
                "account_type": identity.account_type,
                "account_title": identity.title,
                "fingerprint_matches": snapshot.account_fingerprint
                == lock.expected_fingerprint,
            },
            "cash": {
                "equity": str(snapshot.equity),
                "cash": str(snapshot.cash),
                "buying_power": str(snapshot.buying_power),
            },
            "positions": len(snapshot.positions),
            "open_orders": len(snapshot.open_orders),
            "order_history_count": len(history),
            "as_of_utc": snapshot.as_of_utc.isoformat(),
            "reconciled": snapshot.reconciled,
            "unknown_orders": snapshot.unknown_orders,
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0

    if args.command == "moomoo-read":
        load_local_env(Path(args.env_file))
        try:
            lock = AccountLock.from_env(os.environ)
            ledger = SQLiteLedger(args.ledger or ledger_path_from_env(os.environ))
            broker = MoomooRestBroker(
                MoomooRestClient(_oauth(args.store, open_browser=False)),
                lock,
                ledger,
            )
            identity = broker.account_identity()
            snapshot = broker.get_account_snapshot()
            history = broker.get_order_history(max_pages=args.max_pages)
        except (MoomooAuthError, MoomooRestError, AccountLockError, ValueError) as exc:
            print(f"Moomoo read-only verification failed: {exc}")
            return 1
        report = {
            "mode": "PAPER",
            "rest_read_only": True,
            "order_writes": "disabled",
            "account": {
                "masked_id": identity.masked_id,
                "market_id": identity.market_id,
                "account_type": identity.account_type,
                "account_title": identity.title,
                "fingerprint_matches": True,
            },
            "cash": {
                "equity": str(snapshot.equity),
                "cash": str(snapshot.cash),
                "buying_power": str(snapshot.buying_power),
            },
            "positions": [
                {
                    "symbol": item.symbol,
                    "quantity": item.quantity,
                    "market_value": str(item.market_value),
                }
                for item in snapshot.positions
            ],
            "open_orders": [
                {
                    "symbol": item.symbol,
                    "side": item.side.value,
                    "remaining_quantity": item.remaining_quantity,
                    "reference_price": str(item.reference_price),
                }
                for item in snapshot.open_orders
            ],
            "order_history": [item.to_dict() for item in history],
            "order_history_count": len(history),
            "as_of_utc": snapshot.as_of_utc.isoformat(),
            "reconciled": snapshot.reconciled,
            "unknown_orders": snapshot.unknown_orders,
            "read_at_utc": datetime.now(UTC).isoformat(),
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0

    if args.command == "moomoo-preview-order":
        if args.quantity < 1:
            print("Preview quantity must be positive.")
            return 2
        load_local_env(Path(args.env_file))
        try:
            lock = AccountLock.from_env(os.environ)
            ledger = SQLiteLedger(args.ledger or ledger_path_from_env(os.environ))
            client = MoomooRestClient(_oauth(args.store, open_browser=False))
            broker = MoomooRestBroker(client, lock, ledger)
            identity = broker.account_identity()
            snapshot = broker.get_account_snapshot()
            decision_now = datetime.now(UTC)
            quote = MoomooQuoteFeed(client).get_quote(args.symbol, decision_now)
            proposal = TradeProposal(
                proposal_id=args.proposal_id,
                run_id="operator-preview",
                strategy_version=args.strategy_version,
                decision_time_utc=decision_now,
                data_as_of_utc=quote.as_of_utc,
                symbol=args.symbol,
                action=args.action,
                requested_quantity=args.quantity,
                thesis=args.thesis,
                invalidation=args.invalidation,
            )
            client_order_key = build_client_order_key(
                proposal.strategy_version, proposal.proposal_id
            )
            request = OrderRequest(
                client_order_key=client_order_key,
                proposal_id=proposal.proposal_id,
                account_snapshot_id=snapshot.snapshot_id,
                symbol=proposal.symbol,
                side=OrderSide(proposal.action.value),
                quantity=proposal.requested_quantity,
                reference_price=quote.price,
            )
            adapter = MoomooSimulatedOrderAdapter(
                lock.expected_fingerprint, identity.market_id
            )
            prepared = adapter.prepare(request, snapshot)
            approval_ok = ledger.is_first_order_approved(
                client_order_key, proposal.proposal_id
            )
            control = ControlState(
                order_writes_enabled=False,
                kill_switch_engaged=ledger.kill_switch_engaged(),
                first_order_approved=approval_ok,
            )
            risk_gate = RiskGate(
                expected_account_fingerprint=lock.expected_fingerprint,
                policy_version=POLICY_VERSION_V3,
                allowed_symbols=frozenset(SUPERVISED_EXECUTION_SYMBOLS),
                enforce_min_exposure=False,
            )
            decision = risk_gate.evaluate(
                proposal=proposal,
                account=snapshot,
                quote=quote,
                control=control,
                now=decision_now,
                duplicate=ledger.submission_for_proposal(proposal.proposal_id) is not None,
                unknown_submission=ledger.has_unknown_submissions(),
            )
        except (
            MoomooAuthError,
            MoomooRestError,
            AccountLockError,
            OrderAdapterError,
            ValueError,
        ) as exc:
            print(f"Order preview failed closed: {exc}")
            return 1

        risk_approved = decision.decision is PolicyDecision.APPROVE
        preview_report = {
            "mode": "PAPER",
            "preview_only": True,
            "order_writes": "disabled",
            "submission_performed": False,
            "account": {
                "masked_id": identity.masked_id,
                "market_id": identity.market_id,
                "account_type": identity.account_type,
                "account_title": identity.title,
                "fingerprint_matches": snapshot.account_fingerprint
                == lock.expected_fingerprint,
            },
            "instrument": {
                "symbol": proposal.symbol,
                "action": proposal.action.value,
                "quantity": proposal.requested_quantity,
                "estimated_cost": str(quote.price * proposal.requested_quantity),
            },
            "quote": {
                "price": str(quote.price),
                "as_of_utc": quote.as_of_utc.isoformat(),
                "age_seconds": (decision_now - quote.as_of_utc).total_seconds(),
                "regular_session_open": quote.regular_session_open,
            },
            "account_snapshot": {
                "as_of_utc": snapshot.as_of_utc.isoformat(),
                "age_seconds": (decision_now - snapshot.as_of_utc).total_seconds(),
                "equity": str(snapshot.equity),
                "cash": str(snapshot.cash),
                "buying_power": str(snapshot.buying_power),
                "positions": len(snapshot.positions),
                "open_orders": len(snapshot.open_orders),
                "reconciled": snapshot.reconciled,
            },
            "proposal": proposal.model_dump(mode="json"),
            "risk_decision": decision.model_dump(mode="json"),
            "risk_approved": risk_approved,
            "rule_statuses": _preview_rule_statuses(
                proposal, decision, risk_gate, hypothetical_writes_enabled=False
            ),
            "exposure": _preview_exposure(proposal, snapshot, quote, risk_gate),
            "approval": {"required": True, "found": approval_ok, "durable": True},
            "all_safety_checks_pass": risk_approved,
            "safety_checks": {
                "order_writes_enabled": False,
                "exact_account_fingerprint": snapshot.account_fingerprint
                == lock.expected_fingerprint,
                "account_snapshot_fresh": 0
                <= (decision_now - snapshot.as_of_utc).total_seconds()
                <= 60,
                "quote_fresh": 0
                <= (decision_now - quote.as_of_utc).total_seconds()
                <= 300,
                "regular_session_open": quote.regular_session_open,
                "risk_gate_approved": risk_approved,
                "first_order_approved": approval_ok,
            },
            "client_order_key": client_order_key,
            "correlation_tag": prepared.correlation_tag,
            "correlation_note": (
                "Remarks are not an idempotency key. An ambiguous match must remain UNKNOWN."
            ),
            "documented_order_payload_preview": dict(prepared.payload),
            "order_transport_available": False,
        }
        print(json.dumps(preview_report, indent=2, ensure_ascii=True))
        return 0

    if args.command == "moomoo-supervised-preview":
        if args.quantity < 1:
            print("Preview quantity must be positive.")
            return 2
        try:
            stack, lock, ledger, record = _supervised_stack(
                args, order_writes_enabled=False, require_write=True
            )
            identity = stack.reads.account_identity()
            snapshot = stack.broker.get_account_snapshot()
            now = datetime.now(UTC)
            quote = stack.quote_feed.get_quote(args.symbol, now)
            decision_time = max(datetime.now(UTC), quote.as_of_utc)
            proposal = file_proposal or _supervised_proposal(args, quote, decision_time)
            _require_current_policy_proposal(proposal)
            client_order_key = build_client_order_key(
                proposal.strategy_version, proposal.proposal_id
            )
            request = OrderRequest(
                client_order_key=client_order_key,
                proposal_id=proposal.proposal_id,
                account_snapshot_id=snapshot.snapshot_id,
                symbol=proposal.symbol,
                side=OrderSide(proposal.action.value),
                quantity=proposal.requested_quantity,
                reference_price=quote.price,
            )
            prepared = MoomooSimulatedOrderAdapter(
                lock.expected_fingerprint, identity.market_id
            ).prepare(request, snapshot)
            approval_ok = ledger.is_first_order_approved(
                client_order_key, proposal.proposal_id
            )
            decision = stack.risk_gate.evaluate(
                proposal=proposal,
                account=snapshot,
                quote=quote,
                control=ControlState(
                    order_writes_enabled=True,
                    kill_switch_engaged=ledger.kill_switch_engaged(),
                    first_order_approved=approval_ok,
                ),
                now=decision_time,
                duplicate=ledger.submission_for_proposal(proposal.proposal_id)
                is not None,
                unknown_submission=ledger.has_unknown_submissions(),
            )
        except (
            MoomooAuthError,
            MoomooRestError,
            AccountLockError,
            OrderAdapterError,
            ValueError,
        ) as exc:
            print(f"Supervised preview failed closed: {exc}")
            return 1

        risk_approved = decision.decision is PolicyDecision.APPROVE
        report = {
            "mode": "PAPER",
            "supervised_preview": True,
            "submission_performed": False,
            "order_writes_enabled": False,
            "order_transport_installed": True,
            "risk_decision_scope": (
                "evaluated with writes hypothetically enabled and the current durable approval; "
                "no transport submission occurred"
            ),
            "granted_scopes": scope_summary(record.scope),
            "account_exclusive_write_scope_verified": False,
            "account": {
                "masked_id": identity.masked_id,
                "market_id": identity.market_id,
                "account_type": identity.account_type,
                "account_title": identity.title,
                "fingerprint_matches": snapshot.account_fingerprint
                == lock.expected_fingerprint,
                "equity": str(snapshot.equity),
                "cash": str(snapshot.cash),
                "buying_power": str(snapshot.buying_power),
                "positions": [
                    {
                        "symbol": item.symbol,
                        "quantity": item.quantity,
                        "market_value": str(item.market_value),
                    }
                    for item in snapshot.positions
                ],
                "open_orders": len(snapshot.open_orders),
                "as_of_utc": snapshot.as_of_utc.isoformat(),
                "age_seconds": (decision_time - snapshot.as_of_utc).total_seconds(),
                "reconciled": snapshot.reconciled,
                "unknown_orders": snapshot.unknown_orders,
            },
            "instrument": {
                "symbol": proposal.symbol,
                "action": proposal.action.value,
                "quantity": proposal.requested_quantity,
                "estimated_notional": str(quote.price * proposal.requested_quantity),
            },
            "quote": {
                "price": str(quote.price),
                "as_of_utc": quote.as_of_utc.isoformat(),
                "age_seconds": (decision_time - quote.as_of_utc).total_seconds(),
                "regular_session_open": quote.regular_session_open,
            },
            "proposal": proposal.model_dump(mode="json"),
            "client_order_key": client_order_key,
            "approval": {
                "required": True,
                "found": approval_ok,
                "identifier": client_order_key if approval_ok else None,
                "durable": True,
                "expires_at_utc": None,
                "note": (
                    "Approval is durable and exact-proposal bound; the risk "
                    "decision is recomputed at submission."
                ),
            },
            "risk_decision": decision.model_dump(mode="json"),
            "risk_approved": risk_approved,
            "rule_statuses": _preview_rule_statuses(
                proposal, decision, stack.risk_gate, hypothetical_writes_enabled=True
            ),
            "exposure": _preview_exposure(proposal, snapshot, quote, stack.risk_gate),
            "all_safety_checks_pass": (
                risk_approved
                and approval_ok
                and snapshot.reconciled
                and quote.regular_session_open
            ),
            "documented_order_payload_preview": dict(prepared.payload),
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0 if risk_approved else 2

    if args.command == "moomoo-supervised-execute":
        if args.quantity < 1:
            print("Execution quantity must be positive.")
            return 2
        load_local_env(Path(args.env_file))
        try:
            mode = resolve_trading_mode(os.environ)
        except TradingModeError as exc:
            print(f"Refusing: {exc}")
            return 2
        if mode.value == "READ_ONLY":
            print(
                "Refusing: TRADING_MODE=READ_ONLY. Supervised execution requires "
                "SUPERVISED_PAPER or AUTO_PAPER mode."
            )
            return 2
        client_order_key = build_client_order_key(
            args.strategy_version, args.proposal_id
        )
        if args.confirm_client_order_key != client_order_key:
            print("Refusing: --confirm-client-order-key does not match this proposal.")
            return 2
        if not args.enable_order_writes:
            print(
                "Refusing: --enable-order-writes is required for the one supervised "
                "submission. No order was sent."
            )
            return 2
        try:
            stack, lock, ledger, record = _supervised_stack(
                args, order_writes_enabled=True, require_write=True
            )
            if not ledger.is_first_order_approved(
                client_order_key, args.proposal_id
            ):
                print(
                    "Refusing: this paper order has no durable approval for "
                    "this exact proposal."
                )
                return 2
            if ledger.kill_switch_engaged():
                print("Refusing: the persistent kill switch is engaged.")
                return 2
            identity = stack.reads.account_identity()
            now = datetime.now(UTC)
            quote = stack.quote_feed.get_quote(args.symbol, now)
            decision_time = max(datetime.now(UTC), quote.as_of_utc)
            proposal = file_proposal or _supervised_proposal(args, quote, decision_time)
            _require_current_policy_proposal(proposal)
            submissions_before = ledger.submission_count()
            result = stack.service.execute(proposal, quote, decision_time)
            submission_attempted = ledger.submission_count() > submissions_before
            reconciled = None
            if result.order is not None:
                reconciled = stack.service.reconcile(
                    client_order_key, datetime.now(UTC)
                )
        except (
            MoomooAuthError,
            MoomooRestError,
            AccountLockError,
            OrderAdapterError,
            ValueError,
        ) as exc:
            print(f"Supervised execution failed closed: {exc}")
            return 1

        order = result.order or reconciled
        report = {
            "mode": "PAPER",
            "supervised_execution": True,
            "submission_attempted": submission_attempted,
            "order_writes_restored_disabled": True,
            "granted_scopes": scope_summary(record.scope),
            "account_exclusive_write_scope_verified": False,
            "account": {
                "masked_id": identity.masked_id,
                "market_id": identity.market_id,
                "account_type": identity.account_type,
                "fingerprint_matches": True,
            },
            "client_order_key": client_order_key,
            "proposal_id": proposal.proposal_id,
            "risk_decision": result.decision.model_dump(mode="json"),
            "order": (
                {
                    "broker_order_id": order.broker_order_id,
                    "status": order.status.value,
                    "fills": [
                        fill.model_dump(mode="json") for fill in order.fills
                    ],
                    "submitted_at_utc": (
                        order.submitted_at_utc.isoformat()
                        if order.submitted_at_utc
                        else None
                    ),
                }
                if order is not None
                else None
            ),
            "reconciliation": (
                {
                    "outcome": _reconciliation_outcome(
                        ledger, proposal.proposal_id
                    ),
                    "status": reconciled.status.value,
                    "broker_order_id": reconciled.broker_order_id,
                    "fills": [
                        fill.model_dump(mode="json") for fill in reconciled.fills
                    ],
                }
                if reconciled is not None
                else None
            ),
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
        if result.decision.decision is not PolicyDecision.APPROVE:
            return 2
        if result.order is None:
            return 2
        if result.order.status.value == "UNKNOWN":
            return 3
        return 0

    if args.command == "moomoo-supervised-reconcile":
        try:
            stack, lock, ledger, record = _supervised_stack(
                args, order_writes_enabled=False, require_write=False
            )
            local = ledger.order_for_key(args.client_order_key)
            if local is None:
                print("No local supervised order matches that client order key.")
                return 1
            reconciled = stack.service.reconcile(
                args.client_order_key, datetime.now(UTC)
            )
        except (
            MoomooAuthError,
            MoomooRestError,
            AccountLockError,
            OrderAdapterError,
            ValueError,
        ) as exc:
            print(f"Supervised reconciliation failed closed: {exc}")
            return 1
        order = reconciled or local
        report = {
            "mode": "PAPER",
            "read_only_reconciliation": True,
            "order_writes_enabled": False,
            "granted_scopes": scope_summary(record.scope),
            "account_exclusive_write_scope_verified": False,
            "client_order_key": args.client_order_key,
            "order": {
                "broker_order_id": order.broker_order_id,
                "status": order.status.value,
                "fills": [fill.model_dump(mode="json") for fill in order.fills],
                "last_broker_sync_utc": (
                    order.last_broker_sync_utc.isoformat()
                    if order.last_broker_sync_utc
                    else None
                ),
            },
            "reconciliation_outcome": _reconciliation_outcome(
                ledger, order.proposal_id
            ),
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0 if reconciled is not None else 1

    if args.command == "moomoo-supervised-resolve-unknown":
        try:
            stack, lock, ledger, record = _supervised_stack(
                args, order_writes_enabled=False, require_write=False
            )
            local = ledger.order_for_key(args.client_order_key)
            if local is None:
                print("No local supervised order matches that client order key.")
                return 1
            if local.status is not OrderStatus.UNKNOWN:
                print(
                    f"Refusing to resolve: local order status is "
                    f"{local.status.value}, not UNKNOWN. Nothing was written."
                )
                return 2
            now = datetime.now(UTC)
            verdict = reconcile_unknown_order(local, stack.reads, now)
            if verdict.outcome != "NO_MATCH":
                print(
                    f"Refusing to resolve ({verdict.outcome}): {verdict.detail}. "
                    "Run `moomoo-supervised-reconcile` instead if a broker order "
                    "now exists. Nothing was written."
                )
                return 2
            if not args.confirm_resolve:
                print(
                    "Broker re-verification passed (no matching order), but "
                    "--confirm-resolve is required. Nothing was written."
                )
                return 2
            resolved = local.model_copy(
                update={
                    "status": OrderStatus.REJECTED,
                    "last_broker_sync_utc": now,
                }
            )
            ledger.record_order(resolved)
            ledger.append_event(
                "UNKNOWN_RESOLVED",
                now,
                local.proposal_id,
                "resolve_unknown_cli",
                {
                    "client_order_key": args.client_order_key,
                    "reason": (
                        "broker has no matching order; transport failure before "
                        "acknowledgement"
                    ),
                    "today_orders": verdict.today_orders,
                    "history_orders": verdict.history_orders,
                },
                local.proposal_id,
            )
        except (
            MoomooAuthError,
            MoomooRestError,
            AccountLockError,
            OrderAdapterError,
            ValueError,
        ) as exc:
            print(f"Unknown-order resolution failed closed: {exc}")
            return 1
        report = {
            "mode": "PAPER",
            "read_only_resolution": True,
            "order_writes_enabled": False,
            "granted_scopes": scope_summary(record.scope),
            "client_order_key": args.client_order_key,
            "previous_status": "UNKNOWN",
            "resolved_status": "REJECTED",
            "broker_evidence": {
                "today_orders": verdict.today_orders,
                "history_orders": verdict.history_orders,
                "detail": verdict.detail,
            },
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0

    if args.command == "moomoo-auto-paper-status":
        load_local_env(Path(args.env_file))
        ledger = SQLiteLedger(args.ledger or ledger_path_from_env(os.environ))
        try:
            mode = resolve_trading_mode(os.environ)
        except TradingModeError as exc:
            print(f"Auto-paper status unavailable: {exc}")
            return 2
        activation = ledger.latest_trading_activation()
        report = {
            "mode": "PAPER",
            "trading_mode": mode.value,
            "order_writes_enabled_env": (
                os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower()
                in {"true", "1", "yes"}
            ),
            "kill_switch_engaged": ledger.kill_switch_engaged(),
            "activation": (
                {
                    "activated_at_utc": activation.activated_at_utc.isoformat(),
                    "activated_by": activation.activated_by,
                    "account_fingerprint": activation.account_fingerprint,
                    "strategy_version": activation.strategy_version,
                    "allowed_symbols": list(activation.allowed_symbols),
                    "risk_policy_version": activation.risk_policy_version,
                    **_activation_policy_fields(activation),
                    "paper_only": True,
                    "order_writes_enabled": True,
                }
                if activation is not None
                else None
            ),
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0

    if args.command == "moomoo-activate-auto-paper":
        load_local_env(Path(args.env_file))
        if not args.confirm_auto_paper:
            print(
                "Refusing: --confirm-auto-paper is required to record the durable "
                "AUTO_PAPER activation pin. Nothing was written."
            )
            return 2
        try:
            mode = resolve_trading_mode(os.environ)
        except TradingModeError as exc:
            print(f"Refusing: {exc}")
            return 2
        if mode.value != "AUTO_PAPER":
            print(
                "Refusing: TRADING_MODE must be AUTO_PAPER before recording the "
                f"activation pin (current: {mode.value})."
            )
            return 2
        writes_flag = os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower()
        if writes_flag not in {"true", "1", "yes"}:
            print(
                "Refusing: ORDER_WRITES_ENABLED must be true before recording the "
                "activation pin. Nothing was written."
            )
            return 2
        fingerprint = os.environ.get("COMPETITION_ACCOUNT_FINGERPRINT", "").strip()
        if args.expires_at is not None:
            try:
                expires_at = datetime.fromisoformat(
                    args.expires_at.replace("Z", "+00:00")
                )
            except ValueError:
                print("Refusing: --expires-at must be an ISO 8601 UTC timestamp")
                return 2
            if expires_at.tzinfo is None:
                print("Refusing: --expires-at must include a UTC offset")
                return 2
            if expires_at <= datetime.now(UTC):
                print("Refusing: --expires-at must be in the future")
                return 2
        else:
            expires_at = None
        ledger = SQLiteLedger(args.ledger or ledger_path_from_env(os.environ))
        try:
            activation = build_auto_paper_activation(
                fingerprint,
                datetime.now(UTC),
                activated_by=args.authorized_by,
                expires_at_utc=expires_at,
            )
        except TradingModeError as exc:
            print(f"Refusing: {exc}")
            return 2
        ledger.record_trading_activation(activation)
        ledger.append_event(
            "AUTO_PAPER_ACTIVATED",
            activation.activated_at_utc,
            None,
            "operator-cli",
            {
                "strategy_version": activation.strategy_version,
                "allowed_symbols": list(activation.allowed_symbols),
                "risk_policy_version": activation.risk_policy_version,
                **_activation_policy_fields(activation),
                "paper_only": True,
                "order_writes_enabled": True,
            },
        )
        print(json.dumps({
            "mode": "PAPER",
            "activation_recorded": True,
            "order_submitted": False,
            "trading_mode": mode.value,
            "strategy_version": activation.strategy_version,
            "allowed_symbols": list(activation.allowed_symbols),
            "risk_policy_version": activation.risk_policy_version,
            **_activation_policy_fields(activation),
            "account_fingerprint": activation.account_fingerprint,
            "paper_only": True,
            "note": (
                "Autonomous submissions still require the per-run pipeline checks, "
                "a fresh RiskGate decision and an unengaged kill switch."
            ),
        }, indent=2, ensure_ascii=True))
        return 0

    if args.command == "moomoo-kill-switch":
        load_local_env(Path(args.env_file))
        ledger = SQLiteLedger(args.ledger or ledger_path_from_env(os.environ))
        engaged = ledger.kill_switch_engaged()
        now = datetime.now(UTC)
        changed = False
        if args.engage and args.release:
            print("Refusing: --engage and --release are mutually exclusive.")
            return 2
        if args.engage:
            if not args.confirm_engage:
                print(
                    "Refusing: --confirm-engage is required to engage the kill "
                    "switch. Nothing was written."
                )
                return 2
            if engaged:
                print("The persistent kill switch is already engaged.")
            else:
                ledger.set_kill_switch(True)
                ledger.append_event(
                    "KILL_SWITCH_ENGAGED", now, None, "operator-cli", {"reason": "manual owner action"}
                )
                engaged = True
                changed = True
        if args.release:
            if not args.confirm_release:
                print(
                    "Refusing: --confirm-release is required to release the kill "
                    "switch. Nothing was written."
                )
                return 2
            if not engaged:
                print("The persistent kill switch is not engaged.")
            else:
                ledger.set_kill_switch(False)
                ledger.append_event(
                    "KILL_SWITCH_RELEASED", now, None, "operator-cli", {"reason": "manual owner action"}
                )
                engaged = False
                changed = True
        print(json.dumps({
            "mode": "PAPER",
            "kill_switch_engaged": engaged,
            "state_changed": changed,
            "action": (
                "engaged" if changed and engaged else
                "released" if changed else
                "reported"
            ),
            "note": (
                "The kill switch blocks new paper orders and never liquidates "
                "holdings. Release it only after the triggering condition is resolved."
            ),
        }, indent=2, ensure_ascii=True))
        return 0

    if args.command == "moomoo-supersede-approval":
        load_local_env(Path(args.env_file))
        ledger = SQLiteLedger(args.ledger or ledger_path_from_env(os.environ))
        client_order_key = build_client_order_key(args.strategy_version, args.proposal_id)
        if not args.confirm_supersede:
            print("Refusing: --confirm-supersede is required. Nothing was written.")
            return 2
        now = datetime.now(UTC)
        superseded = ledger.supersede_order_approval(
            client_order_key, now, args.superseded_by, args.reason
        )
        if superseded:
            ledger.append_event(
                "APPROVAL_SUPERSEDED",
                now,
                None,
                "operator-cli",
                {
                    "client_order_key": client_order_key,
                    "proposal_id": args.proposal_id,
                    "superseded_by": args.superseded_by,
                    "reason": args.reason,
                },
            )
        print(json.dumps({
            "mode": "PAPER",
            "superseded": superseded,
            "client_order_key": client_order_key,
            "proposal_id": args.proposal_id,
            "note": (
                "The approval row remains in the ledger as historical evidence "
                "but can no longer authorise an order under any policy."
            ),
        }, indent=2, ensure_ascii=True))
        return 0

    ledger_path = args.ledger or ledger_path_from_env(os.environ)
    client_order_key = build_client_order_key(args.strategy_version, args.proposal_id)
    ledger = SQLiteLedger(ledger_path)
    ledger.approve_first_order(
        client_order_key,
        args.proposal_id,
        datetime.now(UTC),
        args.approved_by,
    )
    print(f"Recorded approval for client_order_key={client_order_key}")
    print(f"Policy version: {POLICY_VERSION_V3}")
    print("No order was submitted. Order writes remain disabled unless separately enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
