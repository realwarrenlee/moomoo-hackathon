import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.ledger.store import SQLiteLedger
from app.models.contracts import (
    AccountSnapshot,
    OpenOrder,
    OrderRecord,
    OrderRequest,
    OrderSide,
    OrderStatus,
    Position,
    TradingActivation,
)
from app.trading_mode import build_auto_paper_activation
from scripts import risk_monitor
from scripts.schedule_readonly import ScheduleError

NY = ZoneInfo("America/New_York")
FINGERPRINT = "a" * 64
NOW = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
WINDOWS = {
    "reconcile": {"start": "09:45", "end": "10:30"},
    "midday": {"start": "12:00", "end": "13:00"},
    "pre_close": {"start": "15:45", "end": "16:00"},
}


def _account(**overrides) -> AccountSnapshot:
    fields = {
        "snapshot_id": "snapshot-1",
        "account_fingerprint": FINGERPRINT,
        "environment": "paper",
        "equity": Decimal("100000"),
        "day_start_equity": Decimal("100000"),
        "peak_equity": Decimal("100000"),
        "cash": Decimal("100000"),
        "buying_power": Decimal("100000"),
        "positions": (),
        "open_orders": (),
        "as_of_utc": NOW,
        "reconciled": True,
        "unknown_orders": 0,
    }
    fields.update(overrides)
    return AccountSnapshot(**fields)


def _v2_activation(**overrides) -> TradingActivation:
    activation = build_auto_paper_activation(FINGERPRINT, NOW)
    return activation.model_copy(update=overrides)


def _v1_activation() -> TradingActivation:
    return TradingActivation(
        activated_at_utc=NOW,
        activated_by="owner",
        account_fingerprint=FINGERPRINT,
        strategy_version="spy-directional",
        allowed_symbols=("SPY", "SH"),
        risk_policy_version="risk-v1",
        max_single_exposure=Decimal("0.10"),
        max_total_exposure=Decimal("0.30"),
        position_fraction=Decimal("0.05"),
        max_daily_drawdown=Decimal("0.02"),
    )


class FakeFeed:
    def __init__(self, days: tuple[date, ...]) -> None:
        self.days = sorted(set(days))

    def get_trading_days(self, start: date, end: date) -> list[date]:
        return [day for day in self.days if start <= day <= end]


class FakeReads:
    def __init__(self, account: AccountSnapshot) -> None:
        self.account = account

    def get_account_snapshot(self) -> AccountSnapshot:
        return self.account


class FakeReconciler:
    def __init__(self, status: OrderStatus | None, ledger: SQLiteLedger | None = None) -> None:
        self.status = status
        self.ledger = ledger
        self.calls: list[str] = []

    def reconcile(self, client_order_key: str, now: datetime):
        self.calls.append(client_order_key)
        if self.status is None or self.ledger is None:
            return None if self.status is None else SimpleNamespace(status=self.status)
        local = self.ledger.order_for_key(client_order_key)
        if local is None:
            return None
        resolved = local.model_copy(update={"status": self.status})
        self.ledger.record_order(resolved)
        return resolved


def _config(tmp_path, windows=None):
    payload = {"timezone": "America/New_York", "windows": WINDOWS if windows is None else windows}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _events(ledger: SQLiteLedger) -> list[dict]:
    return [event["event_type"] for event in ledger.list_events()]


def _breach_types(ledger: SQLiteLedger) -> list[str]:
    return [
        event["payload_redacted_json"]["type"]
        for event in ledger.list_events()
        if event["event_type"] == "RISK_BREACH"
    ]


def test_due_window_uses_new_york_wall_clock():
    windows = risk_monitor._parse_windows({"timezone": "America/New_York", "windows": WINDOWS})
    assert risk_monitor._due_window(datetime(2026, 11, 18, 9, 45, tzinfo=NY), windows) == "reconcile"
    assert risk_monitor._due_window(datetime(2026, 11, 18, 10, 29, tzinfo=NY), windows) == "reconcile"
    assert risk_monitor._due_window(datetime(2026, 11, 18, 12, 0, tzinfo=NY), windows) == "midday"
    assert risk_monitor._due_window(datetime(2026, 11, 18, 15, 45, tzinfo=NY), windows) == "pre_close"
    assert risk_monitor._due_window(datetime(2026, 11, 18, 15, 59, tzinfo=NY), windows) == "pre_close"
    assert risk_monitor._due_window(datetime(2026, 11, 18, 10, 30, tzinfo=NY), windows) is None
    assert risk_monitor._due_window(datetime(2026, 11, 18, 13, 0, tzinfo=NY), windows) is None
    assert risk_monitor._due_window(datetime(2026, 11, 18, 16, 0, tzinfo=NY), windows) is None
    assert risk_monitor._due_window(datetime(2026, 11, 18, 8, 0, tzinfo=NY), windows) is None


def test_config_rejects_missing_windows_and_bad_times(tmp_path):
    with pytest.raises(ScheduleError):
        risk_monitor._parse_windows(json.loads(_config(tmp_path, windows={}).read_text()))
    missing = _config(tmp_path, windows={"reconcile": {"start": "09:45", "end": "10:30"}})
    with pytest.raises(ScheduleError):
        risk_monitor._parse_windows(json.loads(missing.read_text()))
    inverted = _config(
        tmp_path,
        windows={"reconcile": {"start": "10:30", "end": "09:45"}},
    )
    with pytest.raises(ScheduleError):
        risk_monitor._parse_windows(json.loads(inverted.read_text()))
    with pytest.raises(ScheduleError):
        risk_monitor._parse_window_time("9am", "midday.start")
    bad_tz = tmp_path / "tz.json"
    bad_tz.write_text(json.dumps({"timezone": "Asia/Singapore", "windows": WINDOWS}), encoding="utf-8")
    with pytest.raises(ScheduleError):
        risk_monitor._config(bad_tz)


def test_drawdown_breach_threshold():
    breached = _account(equity=Decimal("97999"), day_start_equity=Decimal("100000"))
    assert risk_monitor._drawdown_breach(breached, Decimal("0.02")) is not None
    safe = _account(equity=Decimal("98001"), day_start_equity=Decimal("100000"))
    assert risk_monitor._drawdown_breach(safe, Decimal("0.02")) is None


def test_v2_exposure_breach_is_signed_and_effective():
    spxu = _account(
        positions=(Position(symbol="SPXU", quantity=1000, market_value=Decimal("60000")),)
    )
    breaches = risk_monitor._exposure_breaches(spxu, _v2_activation())
    assert [item["type"] for item in breaches] == ["EFFECTIVE_EXPOSURE"]
    spy = _account(
        positions=(Position(symbol="SPY", quantity=100, market_value=Decimal("100000")),)
    )
    assert risk_monitor._exposure_breaches(spy, _v2_activation()) == []


def test_v1_exposure_breaches_use_unsigned_limits():
    activation = _v1_activation()
    single = _account(
        positions=(Position(symbol="SPY", quantity=100, market_value=Decimal("11000")),)
    )
    assert [item["type"] for item in risk_monitor._exposure_breaches(single, activation)] == [
        "SINGLE_EXPOSURE"
    ]
    gross = _account(
        positions=(
            Position(symbol="SPY", quantity=100, market_value=Decimal("15000")),
            Position(symbol="SH", quantity=100, market_value=Decimal("15500")),
        )
    )
    types = [item["type"] for item in risk_monitor._exposure_breaches(gross, activation)]
    assert types == ["SINGLE_EXPOSURE", "SINGLE_EXPOSURE", "GROSS_EXPOSURE"]


def test_duration_breach_counts_trading_sessions_after_entry(tmp_path):
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    now = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
    ledger.append_event(
        "AUTO_PAPER_ENTRY",
        now,
        None,
        "auto_paper_executor",
        {"symbol": "UPRO", "session": "2026-11-10"},
    )
    sessions = (date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18))
    feed = FakeFeed(sessions)
    account = _account(positions=(Position(symbol="UPRO", quantity=100, market_value=Decimal("10000")),))
    breach = risk_monitor._duration_breach(account, ledger, feed, date(2026, 11, 18))
    assert breach is not None and breach["type"] == "LEVERAGED_HOLDING_DURATION"
    assert breach["sessions_held"] == 6
    short = risk_monitor._duration_breach(account, ledger, feed, date(2026, 11, 13))
    assert short is None
    one_x = _account(positions=(Position(symbol="SPY", quantity=100, market_value=Decimal("10000")),))
    assert risk_monitor._duration_breach(one_x, ledger, feed, date(2026, 11, 18)) is None


def test_leftover_open_orders_reported(tmp_path):
    account = _account(
        open_orders=(
            OpenOrder(symbol="SPY", side=OrderSide.BUY, remaining_quantity=10, reference_price=Decimal("500")),
        )
    )
    breaches = risk_monitor._leftover_open_orders(account)
    assert breaches[0]["type"] == "OPEN_ORDER_AT_PRE_CLOSE"


def _run(tmp_path, window, *, account=None, reconciler=None, activation=None, feed=None):
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    report = risk_monitor.run_checks(
        now=NOW,
        ledger=ledger,
        reads=FakeReads(account or _account()),
        reconciler=reconciler or FakeReconciler(None),
        feed=feed or FakeFeed((date(2026, 11, 18),)),
        fingerprint=FINGERPRINT,
        activation=activation,
        window=window,
        session_iso="2026-11-18",
    )
    return ledger, report


def test_midday_drawdown_breach_engages_kill_switch_once(tmp_path):
    account = _account(equity=Decimal("97999"), day_start_equity=Decimal("100000"))
    ledger, report = _run(tmp_path, "midday", account=account, activation=_v2_activation())
    assert report["status"] == "COMPLETED"
    assert [item["type"] for item in report["breaches"]] == ["DAILY_DRAWDOWN"]
    assert ledger.kill_switch_engaged()
    assert "KILL_SWITCH_ENGAGED" in _events(ledger)
    first_count = _events(ledger).count("KILL_SWITCH_ENGAGED")
    ledger2, report2 = _run(tmp_path, "midday", account=account, activation=_v2_activation())
    assert report2["kill_switch"] == {"engaged": False, "reason": "daily drawdown threshold reached"}
    assert _events(ledger2).count("KILL_SWITCH_ENGAGED") == first_count


def test_exposure_breach_reports_without_kill_switch(tmp_path):
    account = _account(
        positions=(Position(symbol="SPXU", quantity=1000, market_value=Decimal("60000")),)
    )
    ledger, report = _run(tmp_path, "midday", account=account, activation=_v2_activation())
    assert report["status"] == "COMPLETED"
    assert _breach_types(ledger) == ["EFFECTIVE_EXPOSURE"]
    assert not ledger.kill_switch_engaged()


def test_pre_close_open_order_and_duration_breaches_do_not_engage(tmp_path):
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    now = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)
    ledger.append_event(
        "AUTO_PAPER_ENTRY", now, None, "auto_paper_executor",
        {"symbol": "UPRO", "session": "2026-11-10"},
    )
    account = _account(
        positions=(Position(symbol="UPRO", quantity=100, market_value=Decimal("10000")),),
        open_orders=(
            OpenOrder(symbol="SPY", side=OrderSide.BUY, remaining_quantity=10, reference_price=Decimal("500")),
        ),
    )
    sessions = (date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18))
    report = risk_monitor.run_checks(
        now=NOW,
        ledger=ledger,
        reads=FakeReads(account),
        reconciler=FakeReconciler(None),
        feed=FakeFeed(sessions),
        fingerprint=FINGERPRINT,
        activation=_v2_activation(),
        window="pre_close",
        session_iso="2026-11-18",
    )
    types = [item["type"] for item in report["breaches"]]
    assert set(types) == {"LEVERAGED_HOLDING_DURATION", "OPEN_ORDER_AT_PRE_CLOSE"}
    assert not ledger.kill_switch_engaged()


def _record_unknown(ledger: SQLiteLedger) -> OrderRequest:
    request = OrderRequest(
        client_order_key="mootrade-" + "0" * 64,
        proposal_id="proposal-1",
        account_snapshot_id="snapshot-1",
        symbol="SPY",
        side=OrderSide.BUY,
        quantity=10,
        reference_price=Decimal("500"),
    )
    ledger.reserve_submission(request)
    ledger.record_order(
        OrderRecord(
            client_order_key=request.client_order_key,
            proposal_id=request.proposal_id,
            paper_account_fingerprint=FINGERPRINT,
            broker_order_id="broker-1",
            status=OrderStatus.UNKNOWN,
            request=request,
            submitted_at_utc=NOW,
            last_broker_sync_utc=NOW,
        )
    )
    return request


def test_reconcile_window_reports_unresolved_without_kill_switch(tmp_path):
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    _record_unknown(ledger)
    reconciler = FakeReconciler(OrderStatus.UNKNOWN)
    report = risk_monitor.run_checks(
        now=NOW,
        ledger=ledger,
        reads=FakeReads(_account()),
        reconciler=reconciler,
        feed=FakeFeed((date(2026, 11, 18),)),
        fingerprint=FINGERPRINT,
        activation=_v2_activation(),
        window="reconcile",
        session_iso="2026-11-18",
    )
    assert report["reconciliation"]["attempted"] == 1
    assert [item["type"] for item in report["breaches"]] == ["AMBIGUOUS_SUBMISSION"]
    assert not ledger.kill_switch_engaged()


def test_pre_close_unresolved_ambiguous_submission_engages_kill_switch(tmp_path):
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    _record_unknown(ledger)
    report = risk_monitor.run_checks(
        now=NOW,
        ledger=ledger,
        reads=FakeReads(_account()),
        reconciler=FakeReconciler(None),
        feed=FakeFeed((date(2026, 11, 18),)),
        fingerprint=FINGERPRINT,
        activation=_v2_activation(),
        window="pre_close",
        session_iso="2026-11-18",
    )
    assert ledger.kill_switch_engaged()
    assert report["kill_switch"]["engaged"] is True


def test_stuck_submitting_record_is_ambiguous(tmp_path):
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    request = OrderRequest(
        client_order_key="mootrade-" + "0" * 64,
        proposal_id="proposal-1",
        account_snapshot_id="snapshot-1",
        symbol="SPY",
        side=OrderSide.BUY,
        quantity=10,
        reference_price=Decimal("500"),
    )
    ledger.reserve_submission(request)
    breach = risk_monitor._ambiguous_submission_breach(ledger)
    assert breach is not None and breach["type"] == "AMBIGUOUS_SUBMISSION"


def test_stale_account_fails_the_check_without_kill_switch(tmp_path):
    stale = _account(as_of_utc=NOW.replace(minute=50))
    ledger, report = _run(tmp_path, "midday", account=stale, activation=_v2_activation())
    assert report["status"] == "CHECK_FAILED"
    assert not ledger.kill_switch_engaged()


def test_reconcile_window_resolves_unknown_without_breach(tmp_path):
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    _record_unknown(ledger)
    reconciler = FakeReconciler(OrderStatus.FILLED, ledger)
    report = risk_monitor.run_checks(
        now=NOW,
        ledger=ledger,
        reads=FakeReads(_account()),
        reconciler=reconciler,
        feed=FakeFeed((date(2026, 11, 18),)),
        fingerprint=FINGERPRINT,
        activation=_v2_activation(),
        window="reconcile",
        session_iso="2026-11-18",
    )
    assert report["reconciliation"] == {"attempted": 1, "resolved": 1}
    assert report["breaches"] == []
    assert not ledger.kill_switch_engaged()


def test_run_once_skips_outside_all_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(risk_monitor, "_execute", lambda *a, **k: {"exit_code": 0})
    event = risk_monitor.run_once(
        datetime(2026, 11, 18, 8, 0, tzinfo=NY),
        config_path=_config(tmp_path),
        state_path=tmp_path / "state.json",
    )
    assert event["status"] == "SKIPPED_NOT_IN_WINDOW"
    assert not (tmp_path / "state.json").exists()


def test_run_once_skips_non_trading_days(tmp_path, monkeypatch):
    monkeypatch.setattr(
        risk_monitor,
        "_history_feed",
        lambda: FakeFeed((date(2026, 11, 13), date(2026, 11, 16))),
    )
    monkeypatch.setattr(risk_monitor, "_execute", lambda *a, **k: {"exit_code": 0})
    saturday = datetime(2026, 11, 14, 12, 0, tzinfo=NY)
    event = risk_monitor.run_once(
        saturday,
        config_path=_config(tmp_path),
        state_path=tmp_path / "state.json",
    )
    assert event["status"] == "SKIPPED_NOT_TRADING_DAY"


def test_run_once_records_completed_window_and_skips_repeat(tmp_path, monkeypatch):
    calls = []

    def fake_execute(window, session, output_dir):
        calls.append((window, session))
        return {"exit_code": 0, "window": window, "session_date": session.isoformat(), "status": "COMPLETED", "breaches": [], "kill_switch_engaged": False, "report_path": "x.json", "order_writes_enabled": False}

    monkeypatch.setattr(risk_monitor, "_history_feed", lambda: FakeFeed((date(2026, 11, 18),)))
    monkeypatch.setattr(risk_monitor, "_execute", fake_execute)
    now = datetime(2026, 11, 18, 12, 0, tzinfo=NY)
    state_path = tmp_path / "state.json"
    first = risk_monitor.run_once(now, config_path=_config(tmp_path), state_path=state_path)
    assert first["status"] == "COMPLETED"
    assert calls == [("midday", date(2026, 11, 18))]
    second = risk_monitor.run_once(now, config_path=_config(tmp_path), state_path=state_path)
    assert second["status"] == "SKIPPED_ALREADY_RUN"
    assert calls == [("midday", date(2026, 11, 18))]


def test_run_once_abandons_stale_running_record_then_executes(tmp_path, monkeypatch):
    monkeypatch.setattr(risk_monitor, "_history_feed", lambda: FakeFeed((date(2026, 11, 18),)))
    monkeypatch.setattr(
        risk_monitor,
        "_execute",
        lambda window, session, output_dir: {
            "exit_code": 0, "window": window, "session_date": session.isoformat(),
            "status": "COMPLETED", "breaches": [], "kill_switch_engaged": False,
            "report_path": "x.json", "order_writes_enabled": False,
        },
    )
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "history": [
                    {
                        "run_key": "midday-2026-11-18",
                        "status": "RUNNING",
                        "attempt": 1,
                        "started_at_utc": "2026-11-18T16:00:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    event = risk_monitor.run_once(
        datetime(2026, 11, 18, 12, 0, tzinfo=NY),
        config_path=_config(tmp_path),
        state_path=state_path,
    )
    assert event["status"] == "COMPLETED"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert [item["status"] for item in state["history"]] == ["ABANDONED", "COMPLETED"]


def test_monitor_stack_refuses_when_writes_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "true")
    ledger = SQLiteLedger(tmp_path / "ledger.db")
    with pytest.raises(ScheduleError, match="ORDER_WRITES_ENABLED"):
        risk_monitor._monitor_stack(ledger, None)
