from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.broker.account_lock import AccountLock
from app.broker.moomoo_orders import build_correlation_tag
from app.broker.moomoo_quotes import QuoteFeedError
from app.broker.moomoo_rest import MoomooRestError, RestOrder
from app.cli import main
from app.ledger.store import SQLiteLedger
from app.models.contracts import (
    AccountSnapshot,
    ControlState,
    Fill,
    OpenOrder,
    OrderRecord,
    OrderRequest,
    OrderSide,
    OrderStatus,
    PolicyDecision,
    Position,
    ProposalAction,
    Quote,
    TradeProposal,
)
from app.research.instruments import INSTRUMENTS
from app.risk.policy import RiskGate
from app.service import TradingService, build_client_order_key
from app.supervised import build_supervised_execution
from app.trading_mode import AUTO_PAPER_SYMBOLS, build_auto_paper_activation

STRATEGY = "spy-directional"
PROPOSAL_ID = "spy-directional-risk-v3-2026-11-20-SPY-BUY"
SYMBOL = "SPY"


@dataclass(frozen=True)
class FakeRecord:
    scope: str = "quote:read trade:read trade:write"


class FakeQuoteFeed:
    def __init__(self, quote: Quote | None = None, error: Exception | None = None):
        self.quote = quote
        self.error = error

    def get_quote(self, symbol: str, now: datetime) -> Quote:
        if self.error is not None:
            raise self.error
        assert self.quote is not None
        assert symbol == self.quote.symbol
        return self.quote


class FakeReads:
    def __init__(self, market_id: int = 100):
        self.market_id = market_id
        self.snapshot: AccountSnapshot | None = None
        self.today_orders: tuple[RestOrder, ...] = ()
        self.history_orders: tuple[RestOrder, ...] = ()
        self.read_error: Exception | None = None

    def account_identity(self):
        return SimpleNamespace(
            masked_id="****0101",
            market_id=self.market_id,
            account_type=2,
            title="Moomoo x Qoder Competition",
        )

    def get_today_orders(self) -> tuple[RestOrder, ...]:
        if self.read_error is not None:
            raise self.read_error
        return self.today_orders

    def get_order_history(self) -> tuple[RestOrder, ...]:
        if self.read_error is not None:
            raise self.read_error
        return self.history_orders

    def get_account_snapshot(self) -> AccountSnapshot:
        if self.read_error is not None:
            raise self.read_error
        assert self.snapshot is not None
        return self.snapshot


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
            allowed_symbols=frozenset({"SPY", "SH"}),
            leverage_by_symbol={
                symbol: item.leverage for symbol, item in INSTRUMENTS.items()
            },
            enforce_min_exposure=False,
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
    monkeypatch.setattr("app.cli.load_local_env", lambda path: None)
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


def test_execute_accepts_a_valid_autonomous_activation_without_approval(
    tmp_path, account_fingerprint
):
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
    quote = Quote(
        symbol=SYMBOL, price=Decimal("100"), as_of_utc=now, regular_session_open=True
    )
    ledger = SQLiteLedger(tmp_path / "audit.db")
    broker = FakePaperBroker(account)
    activation = build_auto_paper_activation(
        account_fingerprint, now - timedelta(days=1)
    )
    service = TradingService(
        broker=broker,
        risk_gate=RiskGate.from_activation(activation),
        ledger=ledger,
        order_writes_enabled=True,
    )
    proposal = TradeProposal(
        proposal_id="autonomous-spy-buy",
        run_id="run-1",
        strategy_version=STRATEGY,
        decision_time_utc=now,
        data_as_of_utc=now,
        symbol=SYMBOL,
        action=ProposalAction.BUY,
        requested_quantity=100,
        thesis="autonomous policy entry",
        invalidation="regime filter fails",
        target_exposure_fraction=Decimal("0.10"),
    )

    result = service.execute(proposal, quote, now, autonomous_activation=activation)

    assert result.decision.decision is PolicyDecision.APPROVE
    assert "R014" not in {reason.rule_id for reason in result.decision.reasons}
    assert result.order is not None
    assert result.order.status is OrderStatus.ACKNOWLEDGED
    assert len(broker.submissions) == 1
    assert ledger.order_for_proposal(proposal.proposal_id) is not None
    assert any(
        event["event_type"] == "RECONCILIATION_OK" for event in ledger.list_events()
    )

    # The same service without the autonomous activation still requires R014.
    result = service.execute(
        proposal.model_copy(update={"proposal_id": "autonomous-spy-buy-2"}),
        quote,
        now,
    )
    assert result.decision.decision is PolicyDecision.REJECT
    assert "R014" in {reason.rule_id for reason in result.decision.reasons}
    assert len(broker.submissions) == 1


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
    unknown_event = next(
        event
        for event in harness.ledger.list_events()
        if event["event_type"] == "ORDER_UNKNOWN"
    )
    assert unknown_event["payload_redacted_json"]["reason"] == (
        "OrderTransportError: order submission outcome is ambiguous (ReadTimeout)"
    )


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


@pytest.mark.parametrize("trading_mode", ["SUPERVISED_PAPER", "AUTO_PAPER"])
@pytest.mark.parametrize("command", [
    "moomoo-supervised-preview", "moomoo-supervised-execute", "moomoo-preview-order"
])
def test_cli_requires_approval_for_every_distinct_proposal(
    tmp_path, monkeypatch, capsys, account_fingerprint, command, trading_mode
):
    harness = make_harness(
        tmp_path, monkeypatch, account_fingerprint=account_fingerprint,
        order_writes_enabled=True, trading_mode=trading_mode,
    )
    harness.approve()
    assert main(base_args("moomoo-supervised-execute") + [
        "--enable-order-writes", "--confirm-client-order-key", harness.key
    ]) == 0
    capsys.readouterr()
    assert harness.ledger.submission_count() == 1
    harness.stack.order_writes_enabled = False
    harness.stack.service.order_writes_enabled = False

    if command == "moomoo-preview-order":
        monkeypatch.setattr("app.cli.AccountLock.from_env", lambda env: AccountLock("****0101", account_fingerprint, 100))
        monkeypatch.setattr("app.cli._oauth", lambda *args, **kwargs: None)
        monkeypatch.setattr("app.cli.MoomooRestClient", lambda *args, **kwargs: None)
        monkeypatch.setattr("app.cli.MoomooRestBroker", lambda *args, **kwargs: SimpleNamespace(
            account_identity=harness.reads.account_identity,
            get_account_snapshot=harness.broker.get_account_snapshot,
        ))
        monkeypatch.setattr("app.cli.MoomooQuoteFeed", lambda *args: harness.quote_feed)

    args = base_args(command)
    args[args.index("--proposal-id") + 1] = "spy-directional-risk-v3-2026-11-20-SPY-BUY-2"
    args += ["--ledger", str(tmp_path / "audit.db")]
    if command == "moomoo-supervised-execute":
        args += ["--enable-order-writes", "--confirm-client-order-key", build_client_order_key(STRATEGY, "spy-directional-risk-v3-2026-11-20-SPY-BUY-2")]
    reads_before = harness.broker.snapshot_reads
    result = main(args)
    output = capsys.readouterr().out

    if command == "moomoo-supervised-execute":
        assert result == 2
        assert "no durable approval" in output
        assert harness.broker.snapshot_reads == reads_before
    else:
        assert result == (0 if command == "moomoo-preview-order" else 2)
        report = json.loads(output)
        assert report["approval"]["required"] is True
        assert report["approval"]["found"] is False
        assert report["rule_statuses"]["R014"]["status"] == "FAIL"
        assert report["rule_statuses"]["R010"]["actual_order_writes_enabled"] is False
        assert report["rule_statuses"]["R010"]["status"] == (
            "FAIL" if command == "moomoo-preview-order" else "PASS"
        )
        assert report["submission_performed"] is False
    assert len(harness.broker.submissions) == 1
    assert harness.ledger.submission_count() == 1


@pytest.mark.parametrize("symbol,direction", [("SPY", 1), ("SH", -1)])
@pytest.mark.parametrize("action", ["BUY", "SELL"])
def test_preview_reports_all_v2_rules_and_conservative_signed_exposure(
    tmp_path, monkeypatch, capsys, account_fingerprint, symbol, direction, action
):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)
    harness.approve()
    harness.quote_feed.quote = harness.quote.model_copy(update={"symbol": symbol})
    harness.broker.account = harness.account.model_copy(update={
        "positions": (Position(symbol=symbol, quantity=10, market_value=Decimal("1000")),),
        "open_orders": (
            OpenOrder(symbol=symbol, side="BUY", remaining_quantity=5, reference_price=Decimal("100")),
            OpenOrder(symbol=symbol, side="SELL", remaining_quantity=7, reference_price=Decimal("100")),
        ),
    })
    args = base_args("moomoo-supervised-preview")
    args[args.index("--symbol") + 1] = symbol
    args[args.index("--action") + 1] = action

    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)

    statuses = report["rule_statuses"]
    assert set(statuses) == {f"R{number:03d}" for number in [1, 2, 3, *range(6, 20)]}
    not_applicable = {"R016", "R018"} if action == "BUY" else {"R006", "R008", "R013", "R016", "R017", "R018", "R019"}
    for rule_id, check in statuses.items():
        assert check["status"] == ("N/A" if rule_id in not_applicable else "PASS")
    assert statuses["R010"]["evaluated_order_writes_enabled"] is True
    assert statuses["R010"]["actual_order_writes_enabled"] is False
    exposure = report["exposure"]
    assert Decimal(exposure["current"]["notional"]) == 1500
    assert Decimal(exposure["current"]["signed_effective_notional"]) == direction * 1500
    assert Decimal(exposure["current"]["signed_effective_equity_fraction"]) == direction * Decimal("0.015")
    post_notional = Decimal("1700" if action == "BUY" else "1300")
    assert Decimal(exposure["post_order"]["notional"]) == post_notional
    assert Decimal(exposure["post_order"]["equity_fraction"]) == post_notional / 100000
    assert Decimal(exposure["post_order"]["signed_effective_notional"]) == direction * post_notional
    assert Decimal(exposure["post_order"]["signed_effective_equity_fraction"]) == direction * post_notional / 100000
    assert report["approval"]["required"] is True
    assert harness.broker.submissions == []
    assert harness.ledger.submission_count() == 0
    assert account_fingerprint not in json.dumps(report)


@pytest.mark.parametrize("target,expected_code", [("0.002", 0), ("0.20", 2)])
def test_proposal_file_is_preserved_through_preview_and_execution(
    tmp_path, monkeypatch, capsys, account_fingerprint, target, expected_code
):
    harness = make_harness(
        tmp_path, monkeypatch, account_fingerprint=account_fingerprint, order_writes_enabled=True
    )
    harness.approve()
    proposal = TradeProposal(
        proposal_id=PROPOSAL_ID, run_id="deterministic-run", strategy_version=STRATEGY,
        decision_time_utc=harness.now - timedelta(minutes=1),
        data_as_of_utc=harness.now - timedelta(days=1),
        symbol=SYMBOL, action="BUY", requested_quantity=2,
        thesis="Test proposal", invalidation="Test invalidation",
        evidence_ids=("daily-signal", "risk-evidence"), target_exposure_fraction=Decimal(target),
    )
    path = tmp_path / "proposal.json"
    path.write_text(proposal.model_dump_json(), encoding="utf-8")
    assert main(base_args("moomoo-supervised-preview") + ["--proposal-file", str(path)]) == expected_code
    preview = json.loads(capsys.readouterr().out)
    assert preview["proposal"] == proposal.model_dump(mode="json")
    assert preview["client_order_key"] == harness.key
    assert preview["rule_statuses"]["R018"]["status"] == ("PASS" if expected_code == 0 else "FAIL")
    assert harness.broker.submissions == []

    assert main(base_args("moomoo-supervised-execute") + [
        "--proposal-file", str(path), "--enable-order-writes", "--confirm-client-order-key", harness.key
    ]) == expected_code
    capsys.readouterr()
    event = next(item for item in harness.ledger.list_events() if item["event_type"] == "PROPOSAL_CREATED")
    assert event["payload_redacted_json"] == proposal.model_dump(mode="json")
    assert len(harness.broker.submissions) == (1 if expected_code == 0 else 0)


@pytest.mark.parametrize("command", ["moomoo-supervised-preview", "moomoo-supervised-execute"])
@pytest.mark.parametrize("field,value", [
    ("symbol", "SH"), ("action", "SELL"), ("requested_quantity", 3),
    ("proposal_id", "different-proposal"), ("strategy_version", "different-strategy"),
    ("thesis", "different thesis"), ("invalidation", "different invalidation"),
])
def test_proposal_file_mismatch_rejected_before_ledger_or_broker_access(
    tmp_path, monkeypatch, capsys, proposal, command, field, value
):
    proposal = TradeProposal.model_validate({
        **proposal.model_dump(), "thesis": "Test proposal", "invalidation": "Test invalidation", field: value,
    })
    path = tmp_path / "proposal.json"
    path.write_text(proposal.model_dump_json(), encoding="utf-8")

    def unexpected(*args, **kwargs):
        raise AssertionError("No environment, ledger or broker access expected")

    monkeypatch.setattr("app.cli._supervised_stack", unexpected)
    monkeypatch.setattr("app.cli.load_local_env", unexpected)
    args = base_args(command) + ["--proposal-file", str(path)]
    if command == "moomoo-supervised-execute":
        args += ["--enable-order-writes", "--confirm-client-order-key", build_client_order_key(STRATEGY, PROPOSAL_ID)]

    assert main(args) == 1
    output = capsys.readouterr().out
    assert "Proposal file does not match flags" in output
    assert field in output


@pytest.mark.parametrize("contents", [None, "not-json", '{"unknown": "field"}'])
def test_invalid_proposal_file_fails_closed_without_access(
    tmp_path, monkeypatch, capsys, contents
):
    path = tmp_path / "proposal.json"
    if contents is not None:
        path.write_text(contents, encoding="utf-8")

    def unexpected(*args, **kwargs):
        raise AssertionError("No ledger or broker access expected")

    monkeypatch.setattr("app.cli._supervised_stack", unexpected)
    assert main(base_args("moomoo-supervised-preview") + ["--proposal-file", str(path)]) == 1
    assert "not a valid TradeProposal" in capsys.readouterr().out


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
                update={"symbol": "SH"}
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


def record_local_order(harness: Harness, status: OrderStatus) -> OrderRecord:
    request = OrderRequest(
        client_order_key=harness.key,
        proposal_id=PROPOSAL_ID,
        account_snapshot_id=harness.account.snapshot_id,
        symbol=SYMBOL,
        side=OrderSide.BUY,
        quantity=2,
        reference_price=Decimal("100"),
    )
    assert harness.ledger.reserve_submission(request)
    order = OrderRecord(
        client_order_key=harness.key,
        proposal_id=PROPOSAL_ID,
        paper_account_fingerprint=harness.account.account_fingerprint,
        status=status,
        request=request,
        submitted_at_utc=harness.now,
    )
    harness.ledger.record_order(order)
    return order


def matching_broker_order(harness: Harness) -> RestOrder:
    return RestOrder(
        broker_order_id="broker-found",
        symbol=SYMBOL,
        side=OrderSide.BUY,
        status_code=1,
        status_label="SUBMITTED",
        quantity=2,
        filled_quantity=0,
        price=Decimal("100"),
        average_fill_price=Decimal("0"),
        created_at_utc=harness.now,
        updated_at_utc=harness.now,
        order_type=3,
        time_in_force=1,
        trading_session=1,
        remark=build_correlation_tag(harness.key),
    )


def resolve_args(harness: Harness, confirm: bool = True) -> list[str]:
    args = ["moomoo-supervised-resolve-unknown", "--client-order-key", harness.key]
    if confirm:
        args.append("--confirm-resolve")
    return args


def test_resolve_unknown_records_rejected_after_broker_no_match(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)
    harness.reads.snapshot = harness.account
    record_local_order(harness, OrderStatus.UNKNOWN)

    result = main(resolve_args(harness))
    report = json.loads(capsys.readouterr().out)

    assert result == 0
    assert report["read_only_resolution"] is True
    assert report["order_writes_enabled"] is False
    assert report["resolved_status"] == "REJECTED"
    assert report["broker_evidence"]["detail"] == "no broker order carries the correlation tag"
    assert harness.ledger.has_unknown_submissions() is False
    local = harness.ledger.order_for_key(harness.key)
    assert local.status is OrderStatus.REJECTED
    events = harness.ledger.list_events()
    assert [event for event in events if event["event_type"] == "UNKNOWN_RESOLVED"]
    assert len(harness.broker.submissions) == 0


def test_resolve_unknown_refuses_without_confirmation(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)
    harness.reads.snapshot = harness.account
    record_local_order(harness, OrderStatus.UNKNOWN)

    result = main(resolve_args(harness, confirm=False))
    out = capsys.readouterr().out

    assert result == 2
    assert "--confirm-resolve is required" in out
    assert harness.ledger.has_unknown_submissions() is True
    assert harness.ledger.order_for_key(harness.key).status is OrderStatus.UNKNOWN


def test_resolve_unknown_refuses_when_broker_has_a_matching_order(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)
    harness.reads.snapshot = harness.account
    record_local_order(harness, OrderStatus.UNKNOWN)
    harness.reads.today_orders = (matching_broker_order(harness),)

    result = main(resolve_args(harness))
    out = capsys.readouterr().out

    assert result == 2
    assert "MATCHED" in out
    assert harness.ledger.has_unknown_submissions() is True
    assert harness.ledger.order_for_key(harness.key).status is OrderStatus.UNKNOWN


def test_resolve_unknown_refuses_when_local_order_is_not_unknown(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)
    harness.reads.snapshot = harness.account
    record_local_order(harness, OrderStatus.ACKNOWLEDGED)

    result = main(resolve_args(harness))
    out = capsys.readouterr().out

    assert result == 2
    assert "not UNKNOWN" in out
    assert harness.ledger.order_for_key(harness.key).status is OrderStatus.ACKNOWLEDGED


def test_resolve_unknown_fails_closed_when_broker_read_fails(
    tmp_path, monkeypatch, capsys, account_fingerprint
):
    harness = make_harness(tmp_path, monkeypatch, account_fingerprint=account_fingerprint)
    harness.reads.snapshot = harness.account
    harness.reads.read_error = MoomooRestError("broker unavailable")
    record_local_order(harness, OrderStatus.UNKNOWN)

    result = main(resolve_args(harness))
    out = capsys.readouterr().out

    assert result == 1
    assert "failed closed" in out
    assert harness.ledger.has_unknown_submissions() is True
    assert harness.ledger.order_for_key(harness.key).status is OrderStatus.UNKNOWN


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


def test_supervised_builder_defaults_to_disabled_writes(
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

    assert stack.order_writes_enabled is False
    assert stack.service.order_writes_enabled is False
    assert stack.broker._transport.order_writes_enabled is False


def test_supervised_gate_allows_spy_sh_and_rejects_upro_spxu(
    tmp_path, account_fingerprint
):
    """risk-v3: SPY/SH pass the supervised gate; UPRO/SPXU are outside the
    universe and any new proposal for them is rejected (R002)."""
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
    assert gate.allowed_symbols == frozenset({"SPY", "SH"})
    assert gate.policy_version == "risk-v3"
    assert gate.enforce_min_exposure is False
    assert gate.leverage_by_symbol["SPY"] == Decimal("1")
    assert gate.leverage_by_symbol["SH"] == Decimal("1")
    assert "UPRO" not in gate.leverage_by_symbol
    assert "SPXU" not in gate.leverage_by_symbol

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

    for symbol in ("SPY", "SH"):
        decision = gate.evaluate(
            proposal_for(symbol), account, quote_for(symbol), control, now
        )
        assert decision.decision is PolicyDecision.APPROVE
        assert decision.reasons == ()
    for symbol in ("UPRO", "SPXU"):
        decision = gate.evaluate(
            proposal_for(symbol), account, quote_for(symbol), control, now
        )
        assert decision.decision is PolicyDecision.REJECT
        assert {reason.rule_id for reason in decision.reasons} == {"R002"}


def test_leverage_permission_cannot_restore_upro_spxu_eligibility(
    tmp_path, account_fingerprint
):
    """risk-v3 has no leveraged path: even a hand-built gate with the
    AUTO_PAPER symbol set cannot make UPRO/SPXU eligible, because their
    metadata was removed from the universe and 1x is the hard leverage cap.
    """
    gate = RiskGate(
        expected_account_fingerprint=account_fingerprint,
        allowed_symbols=frozenset(AUTO_PAPER_SYMBOLS),
        leverage_by_symbol={
            symbol: instrument.leverage for symbol, instrument in INSTRUMENTS.items()
        },
        enforce_min_exposure=False,
    )
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

    for symbol in AUTO_PAPER_SYMBOLS:
        decision = gate.evaluate(
            proposal_for(symbol), account, quote_for(symbol), control, now
        )
        assert decision.decision is PolicyDecision.APPROVE, (
            symbol,
            [reason.rule_id for reason in decision.reasons],
        )
    for symbol in ("UPRO", "SPXU"):
        decision = gate.evaluate(
            proposal_for(symbol), account, quote_for(symbol), control, now
        )
        assert decision.decision is PolicyDecision.REJECT
        assert "R002" in {reason.rule_id for reason in decision.reasons}
