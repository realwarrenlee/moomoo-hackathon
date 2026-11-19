from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.broker.account_lock import AccountLock
from app.broker.moomoo_quotes import QuoteFeedError
from app.cli import main
from app.ledger.store import SQLiteLedger
from app.models.contracts import (
    AccountSnapshot,
    ControlState,
    Fill,
    OrderRecord,
    OrderStatus,
    PolicyDecision,
    ProposalAction,
    Quote,
    TradeProposal,
)
from app.research.data import UNIVERSE
from app.research.instruments import INSTRUMENTS
from app.risk.policy import RiskGate
from app.service import TradingService, build_client_order_key
from app.supervised import build_supervised_execution

STRATEGY = "spy-directional"
PROPOSAL_ID = "proposal-1"
SYMBOL = "SPY"


@dataclass(frozen=True)
class FakeRecord:
    scope: str = "quote:read trade:read trade:write"


class FakeQuoteFeed:
    def __init__(self, quote: Quote | None = None, error: Exception | None = None):
        self.quote = quote
        self.error = error

    def get_quote(self, symbol: str, now: datetime) -> Quote:
        assert symbol == SYMBOL
        if self.error is not None:
            raise self.error
        assert self.quote is not None
        return self.quote


class FakeReads:
    def __init__(self, market_id: int = 100):
        self.market_id = market_id

    def account_identity(self):
        return SimpleNamespace(
            masked_id="****0101",
            market_id=self.market_id,
            account_type=2,
            title="Moomoo x Qoder Competition",
        )


class FakePaperBroker:
    source_name = "fake_paper"

    def __init__(self, account: AccountSnapshot):
        self.account = account
        self.submissions = []
        self.order: OrderRecord | None = None
        self.reconcile_record: OrderRecord | None = None
        self.snapshot_reads = 0

    def get_account_snapshot(self) -> AccountSnapshot:
        self.snapshot_reads += 1
        return self.account

    def submit_order(self, request, now: datetime) -> OrderRecord:
        self.submissions.append(request)
        self.order = OrderRecord(
            client_order_key=request.client_order_key,
            proposal_id=request.proposal_id,
            paper_account_fingerprint=self.account.account_fingerprint,
            broker_order_id="broker-1",
            status=OrderStatus.ACKNOWLEDGED,
            request=request,
            submitted_at_utc=now,
        )
        return self.order

    def get_order(self, client_order_key: str) -> OrderRecord | None:
        if self.reconcile_record is not None:
            return self.reconcile_record
        if self.order is None:
            return None
        return self.order.model_copy(
            update={
                "status": OrderStatus.FILLED,
                "fills": (
                    Fill(
                        broker_fill_id="fill-1",
                        quantity=self.order.request.quantity,
                        price=Decimal("100"),
                        filled_at_utc=datetime.now(UTC),
                    ),
                ),
            }
        )


class FakeStack:
    def __init__(
        self,
        *,
        ledger: SQLiteLedger,
        account: AccountSnapshot,
        quote: Quote,
        reads: FakeReads,
        quote_feed: FakeQuoteFeed,
        broker: FakePaperBroker,
        order_writes_enabled: bool,
    ) -> None:
        self.ledger = ledger
        self.reads = reads
        self.quote_feed = quote_feed
        self.broker = broker
        self.order_writes_enabled = order_writes_enabled
        self.risk_gate = RiskGate(
            expected_account_fingerprint=account.account_fingerprint,
            allowed_symbols=frozenset(UNIVERSE),
            leverage_by_symbol={
                symbol: item.leverage for symbol, item in INSTRUMENTS.items()
            },
            allow_leveraged=False,
        )
        self.service = TradingService(
            broker=broker,
            risk_gate=self.risk_gate,
            ledger=ledger,
            order_writes_enabled=order_writes_enabled,
        )


@dataclass
class Harness:
    now: datetime
    ledger: SQLiteLedger
    account: AccountSnapshot
    quote: Quote
    reads: FakeReads
    quote_feed: FakeQuoteFeed
    broker: FakePaperBroker
    stack: FakeStack
    key: str

    def approve(self) -> None:
        self.ledger.approve_first_order(self.key, PROPOSAL_ID, self.now, "owner")


def make_harness(
    tmp_path,
    monkeypatch,
    *,
    account_fingerprint: str,
    quote: Quote | None = None,
    quote_error: Exception | None = None,
    order_writes_enabled: bool = False,
    trading_mode: str | None = "SUPERVISED_PAPER",
) -> Harness:
    now = datetime.now(UTC)
    monkeypatch.delenv("TRADING_MODE", raising=False)
    if trading_mode is not None:
        monkeypatch.setenv("TRADING_MODE", trading_mode)
    if quote is None:
        quote = Quote(
            symbol=SYMBOL,
            price=Decimal("100"),
            as_of_utc=now,
            regular_session_open=True,
        )
    account = AccountSnapshot(
        snapshot_id="snapshot-1",
        account_fingerprint=account_fingerprint,
        environment="paper",
        equity=Decimal("100000"),
        day_start_equity=Decimal("100000"),
        peak_equity=Decimal("100000"),
        cash=Decimal("100000"),
        buying_power=Decimal("100000"),
        as_of_utc=now,
        reconciled=True,
    )
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker = FakePaperBroker(account)
    stack = FakeStack(
        ledger=ledger,
        account=account,
        quote=quote,
        reads=FakeReads(),
        quote_feed=FakeQuoteFeed(quote, quote_error),
        broker=broker,
        order_writes_enabled=order_writes_enabled,
    )
    lock = AccountLock("****0101", account_fingerprint, 100)
    key = build_client_order_key(STRATEGY, PROPOSAL_ID)
    monkeypatch.setattr(
        "app.cli._supervised_stack",
        lambda args, *, order_writes_enabled, require_write: (
            stack,
            lock,
            ledger,
            FakeRecord(),
        ),
    )
    return Harness(
        now=now,
        ledger=ledger,
        account=account,
        quote=quote,
        reads=stack.reads,
        quote_feed=stack.quote_feed,
        broker=broker,
        stack=stack,
        key=key,
    )


def base_args(command: str) -> list[str]:
    return [
        command,
        "--symbol",
        SYMBOL,
        "--action",
        "BUY",
        "--quantity",
        "2",
        "--proposal-id",
        PROPOSAL_ID,
        "--strategy-version",
        STRATEGY,
        "--thesis",
        "Test proposal",
        "--invalidation",
        "Test invalidation",
    ]


def test_execute_refuses_without_the_write_flag(tmp_path, monkeypatch, capsys, account_fingerprint):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)
    harness.approve()

    result = main(base_args("moomoo-supervised-execute") + ["--confirm-client-order-key", harness.key])

    assert result == 2
    assert harness.broker.submissions == []
    assert "--enable-order-writes is required" in capsys.readouterr().out


def test_execute_refuses_in_read_only_mode(tmp_path, monkeypatch, capsys, account_fingerprint):
    harness = make_harness(
        tmp_path,
        monkeypatch,
        account_fingerprint=account_fingerprint,
        order_writes_enabled=True,
        trading_mode=None,
    )
    harness.approve()

    result = main(
        base_args("moomoo-supervised-execute")
        + [
            "--enable-order-writes",
            "--confirm-client-order-key",
            harness.key,
            "--env-file",
            str(tmp_path / "missing.env"),
        ]
    )

    assert result == 2
    assert harness.broker.submissions == []
    assert "TRADING_MODE=READ_ONLY" in capsys.readouterr().out


def test_execute_refuses_a_mismatched_confirmation_key(tmp_path, monkeypatch, capsys, account_fingerprint):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)
    harness.approve()

    result = main(
        base_args("moomoo-supervised-execute")
        + ["--enable-order-writes", "--confirm-client-order-key", "mootrade-wrong"]
    )

    assert result == 2
    assert harness.broker.submissions == []
    assert "does not match" in capsys.readouterr().out


def test_execute_requires_exact_durable_first_order_approval(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)

    result = main(
        base_args("moomoo-supervised-execute")
        + ["--enable-order-writes", "--confirm-client-order-key", harness.key]
    )

    assert result == 2
    assert harness.broker.submissions == []
    assert "no durable approval" in capsys.readouterr().out


def test_execute_submits_once_and_reconciles_a_fill(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(
        tmp_path,
        monkeypatch,
        account_fingerprint=account_fingerprint,
        order_writes_enabled=True,
    )
    harness.approve()

    result = main(
        base_args("moomoo-supervised-execute")
        + ["--enable-order-writes", "--confirm-client-order-key", harness.key]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == 0
    assert len(harness.broker.submissions) == 1
    assert report["submission_attempted"] is True
    assert report["order"]["status"] == "ACKNOWLEDGED"
    assert report["reconciliation"]["outcome"] == "RECONCILIATION_OK"
    assert report["reconciliation"]["status"] == "FILLED"
    assert report["reconciliation"]["fills"][0]["quantity"] == 2
    assert report["account_exclusive_write_scope_verified"] is False
    assert "token" not in json.dumps(report).lower()
    assert "0000000000000101" not in json.dumps(report)


def test_execute_marks_an_ambiguous_submission_unknown_without_retry(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    from app.broker.moomoo_orders import OrderTransportError

    harness = make_harness(
        tmp_path,
        monkeypatch,
        account_fingerprint=account_fingerprint,
        order_writes_enabled=True,
    )
    harness.approve()
    attempts = []

    def ambiguous(request, now):
        attempts.append(request)
        raise OrderTransportError("order submission outcome is ambiguous (ReadTimeout)")

    harness.broker.submit_order = ambiguous

    result = main(
        base_args("moomoo-supervised-execute")
        + ["--enable-order-writes", "--confirm-client-order-key", harness.key]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == 3
    assert len(attempts) == 1
    assert report["order"]["status"] == "UNKNOWN"
    assert harness.ledger.has_unknown_submissions() is True
    assert "ORDER_UNKNOWN" in {event["event_type"] for event in harness.ledger.list_events()}


def test_execute_never_submits_for_a_nonmatching_account(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(
        tmp_path,
        monkeypatch,
        account_fingerprint=account_fingerprint,
        order_writes_enabled=True,
    )
    harness.approve()
    harness.stack.account = harness.account.model_copy(
        update={"account_fingerprint": "b" * 64}
    )
    harness.broker.account = harness.stack.account

    result = main(
        base_args("moomoo-supervised-execute")
        + ["--enable-order-writes", "--confirm-client-order-key", harness.key]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == 2
    assert harness.broker.submissions == []
    assert report["submission_attempted"] is False
    assert report["risk_decision"]["decision"] == "REJECT"
    assert "R001" in {reason["rule_id"] for reason in report["risk_decision"]["reasons"]}


def test_execute_never_submits_with_the_kill_switch_engaged(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(
        tmp_path,
        monkeypatch,
        account_fingerprint=account_fingerprint,
        order_writes_enabled=True,
    )
    harness.approve()
    harness.ledger.set_kill_switch(True)

    result = main(
        base_args("moomoo-supervised-execute")
        + ["--enable-order-writes", "--confirm-client-order-key", harness.key]
    )

    assert result == 2
    assert harness.broker.submissions == []
    assert "kill switch" in capsys.readouterr().out


def test_preview_reports_approval_and_never_submits(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)
    harness.approve()

    result = main(base_args("moomoo-supervised-preview"))
    report = json.loads(capsys.readouterr().out)

    assert result == 0
    assert harness.broker.submissions == []
    assert report["submission_performed"] is False
    assert report["order_writes_enabled"] is False
    assert report["risk_approved"] is True
    assert report["approval"]["found"] is True
    assert report["documented_order_payload_preview"]["symbol"] == f"US.{SYMBOL}"


def test_preview_reports_missing_approval_without_submitting(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)

    result = main(base_args("moomoo-supervised-preview"))
    report = json.loads(capsys.readouterr().out)

    assert result == 2
    assert harness.broker.submissions == []
    assert report["approval"]["found"] is False
    assert "R014" in {reason["rule_id"] for reason in report["risk_decision"]["reasons"]}


def test_preview_fails_closed_on_a_stale_quote(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(
        tmp_path,
        monkeypatch,
        account_fingerprint=account_fingerprint,
        quote_error=QuoteFeedError("quote is stale (older than 300s)"),
    )
    harness.approve()

    result = main(base_args("moomoo-supervised-preview"))

    assert result == 1
    assert harness.broker.submissions == []
    assert "stale" in capsys.readouterr().out


def test_preview_reports_a_closed_regular_session(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    quote = Quote(
        symbol=SYMBOL,
        price=Decimal("100"),
        as_of_utc=datetime.now(UTC),
        regular_session_open=False,
    )
    harness = make_harness(
        tmp_path,
        monkeypatch,
        account_fingerprint=account_fingerprint,
        quote=quote,
    )
    harness.approve()

    result = main(base_args("moomoo-supervised-preview"))
    report = json.loads(capsys.readouterr().out)

    assert result == 2
    assert harness.broker.submissions == []
    assert "R012" in {reason["rule_id"] for reason in report["risk_decision"]["reasons"]}


def test_reconcile_is_read_only_and_reports_a_broker_mismatch(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(
        tmp_path,
        monkeypatch,
        account_fingerprint=account_fingerprint,
        order_writes_enabled=True,
    )
    harness.approve()
    main(
        base_args("moomoo-supervised-execute")
        + ["--enable-order-writes", "--confirm-client-order-key", harness.key]
    )
    capsys.readouterr()
    harness.broker.reconcile_record = harness.broker.order.model_copy(
        update={
            "request": harness.broker.order.request.model_copy(
                update={"symbol": "SPY"}
            )
        }
    )

    result = main(
        ["moomoo-supervised-reconcile", "--client-order-key", harness.key]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == 0
    assert len(harness.broker.submissions) == 1
    assert report["read_only_reconciliation"] is True
    assert report["reconciliation_outcome"] == "RECONCILIATION_MISMATCH"
    assert report["order"]["status"] == "FILLED"


def test_execute_without_execution_authorization_fails_before_any_broker_call(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    for key in [
        "COMPETITION_ACCOUNT_MASKED_ID",
        "COMPETITION_ACCOUNT_FINGERPRINT",
        "COMPETITION_ACCOUNT_MARKET_ID",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("COMPETITION_ACCOUNT_MASKED_ID", "****0101")
    monkeypatch.setenv("COMPETITION_ACCOUNT_FINGERPRINT", account_fingerprint)
    monkeypatch.setenv("COMPETITION_ACCOUNT_MARKET_ID", "100")
    monkeypatch.setenv("TRADING_MODE", "SUPERVISED_PAPER")
    key = build_client_order_key(STRATEGY, PROPOSAL_ID)

    result = main(
        base_args("moomoo-supervised-execute")
        + [
            "--enable-order-writes",
            "--confirm-client-order-key",
            key,
            "--store",
            str(tmp_path / "missing-oauth.bin"),
            "--env-file",
            str(tmp_path / "missing.env"),
            "--ledger",
            str(tmp_path / "audit.db"),
        ]
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "execution authorization is required" in output
    assert "Bearer" not in output


def test_supervised_builder_defaults_to_disabled_writes(tmp_path, account_fingerprint):
    import httpx

    class FakeAuth:
        def access_token(self) -> str:
            return "token-1"

        def refresh(self) -> None:
            raise AssertionError("no HTTP call is expected")

    lock = AccountLock("****0101", account_fingerprint, 100)
    stack = build_supervised_execution(
        FakeAuth(),
        lock,
        SQLiteLedger(tmp_path / "audit.db"),
        http=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    AssertionError("no HTTP call is expected")
                )
            ),
            trust_env=False,
        ),
    )

    assert stack.order_writes_enabled is False
    assert stack.service.order_writes_enabled is False
    assert stack.broker._transport.order_writes_enabled is False


def test_supervised_gate_covers_the_universe_for_acceptance_tests(
    tmp_path, account_fingerprint
):
    import httpx

    class FakeAuth:
        def access_token(self) -> str:
            return "token-1"

        def refresh(self) -> None:
            raise AssertionError("no HTTP call is expected")

    lock = AccountLock("****0101", account_fingerprint, 100)
    stack = build_supervised_execution(
        FakeAuth(),
        lock,
        SQLiteLedger(tmp_path / "audit.db"),
        http=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (_ for _ in ()).throw(
                    AssertionError("no HTTP call is expected")
                )
            ),
            trust_env=False,
        ),
    )
    gate = stack.risk_gate
    assert gate.allowed_symbols == frozenset({"SPY", "UPRO", "SH", "SPXU"})
    assert gate.policy_version == "risk-v2"
    assert gate.allow_leveraged is True
    assert gate.enforce_min_exposure is False
    assert gate.leverage_by_symbol["SPY"] == Decimal("1")
    assert gate.leverage_by_symbol["SH"] == Decimal("1")
    assert gate.leverage_by_symbol["UPRO"] == Decimal("3")
    assert gate.leverage_by_symbol["SPXU"] == Decimal("3")

    now = datetime.now(UTC)
    account = AccountSnapshot(
        snapshot_id="snapshot-1",
        account_fingerprint=account_fingerprint,
        environment="paper",
        equity=Decimal("100000"),
        day_start_equity=Decimal("100000"),
        peak_equity=Decimal("100000"),
        cash=Decimal("100000"),
        buying_power=Decimal("100000"),
        as_of_utc=now,
        reconciled=True,
    )
    control = ControlState(
        order_writes_enabled=True,
        kill_switch_engaged=False,
        circuit_breaker_open=False,
        first_order_approved=True,
    )

    def proposal_for(symbol: str) -> TradeProposal:
        return TradeProposal(
            proposal_id=f"test-{symbol}",
            run_id="test-run",
            strategy_version=STRATEGY,
            decision_time_utc=now,
            data_as_of_utc=now,
            symbol=symbol,
            action=ProposalAction.BUY,
            requested_quantity=10,
            thesis="t",
            invalidation="i",
        )

    def quote_for(symbol: str) -> Quote:
        return Quote(
            symbol=symbol,
            price=Decimal("100"),
            as_of_utc=now,
            regular_session_open=True,
        )

    for symbol in ("SPY", "SH", "UPRO", "SPXU"):
        decision = gate.evaluate(
            proposal_for(symbol), account, quote_for(symbol), control, now
        )
        assert decision.decision is PolicyDecision.APPROVE
        assert decision.reasons == ()
