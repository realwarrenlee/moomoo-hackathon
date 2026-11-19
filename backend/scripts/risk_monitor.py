"""Daily risk monitor: 09:45 reconcile, 12:00 midday, 15:45 pre-close ET.

Windows Task Scheduler invokes this module. The monitor is strictly read-only
against the broker: it never submits, cancels or liquidates. Every breach
appends a ``RISK_BREACH`` audit event. The daily-drawdown threshold and
ambiguous submissions that remain unresolved by the pre-close check engage the
persistent kill switch, which blocks new orders without liquidating holdings.
Exposure and holding-duration breaches are reported only: the deterministic
reduction rules at the next execution window handle them, and engaging the
kill switch would block those exits.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime, time as wall_time
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Protocol
from zoneinfo import ZoneInfo

from app.broker.account_lock import AccountLock
from app.broker.moomoo_auth import FileTokenStore, MoomooOAuth, default_token_path
from app.broker.moomoo_rest import MoomooRestBroker
from app.cli import ledger_path_from_env, load_local_env
from app.ledger.store import SQLiteLedger
from app.models.contracts import AccountSnapshot, OrderStatus, TradingActivation
from app.research.instruments import INSTRUMENTS
from app.research.strategy import DEFAULT_MAX_LEVERAGED_HOLDING_SESSIONS
from app.risk.policy import (
    DEFAULT_MAX_DAILY_DRAWDOWN,
    EXPOSURE_CONSISTENCY_TOLERANCE,
    POLICY_VERSION_V1,
)
from app.supervised import SupervisedExecution, build_supervised_execution
from scripts.schedule_readonly import (
    ScheduleError,
    _append_log,
    _exclusive_lock,
    _history_feed,
    _is_trading_session,
    _load_state,
    _write_state,
)

ROOT = Path(__file__).resolve().parents[2]
NY = ZoneInfo("America/New_York")
DEFAULT_CONFIG = ROOT / "backend" / "config" / "risk_monitor_schedule.json"
DEFAULT_STATE = ROOT / "data" / "risk_monitor_schedule.json"
DEFAULT_LOG = ROOT / "data" / "risk-monitor-events.jsonl"
DEFAULT_LOCK = ROOT / "data" / "risk_monitor_schedule.lock"
MAX_ACCOUNT_AGE_SECONDS = 60
CLOCK_SKEW_TOLERANCE_SECONDS = 5

WINDOWS = ("reconcile", "midday", "pre_close")
RECONCILABLE_STATUSES = {
    OrderStatus.SUBMITTING.value,
    OrderStatus.ACKNOWLEDGED.value,
    OrderStatus.PARTIALLY_FILLED.value,
    OrderStatus.UNKNOWN.value,
}


class RiskMonitorError(RuntimeError):
    pass


class TradingDaysFeed(Protocol):
    def get_trading_days(self, start: date, end: date) -> list[date]: ...


def _config(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScheduleError("risk monitor config must be a JSON object")
    if payload.get("timezone") not in {None, "America/New_York"}:
        raise ScheduleError("risk monitor timezone must be America/New_York")
    return payload


def _parse_window_time(value: object, field: str) -> tuple[int, int]:
    if not isinstance(value, str):
        raise ScheduleError(f"risk monitor {field} must be HH:MM")
    try:
        hour, minute = (int(part) for part in value.split(":"))
    except (TypeError, ValueError):
        raise ScheduleError(f"risk monitor {field} must be HH:MM") from None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ScheduleError(f"risk monitor {field} is out of range")
    return hour, minute


def _parse_windows(config: Mapping[str, object]) -> dict[str, tuple[tuple[int, int], tuple[int, int]]]:
    windows = config.get("windows")
    if not isinstance(windows, dict) or not windows:
        raise ScheduleError("risk monitor config needs windows")
    parsed: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {}
    for name in WINDOWS:
        window = windows.get(name)
        if not isinstance(window, dict):
            raise ScheduleError(f"risk monitor window {name} is missing")
        start = _parse_window_time(window.get("start"), f"{name}.start")
        end = _parse_window_time(window.get("end"), f"{name}.end")
        if wall_time(*start) >= wall_time(*end):
            raise ScheduleError(f"risk monitor window {name} start is not before end")
        parsed[name] = (start, end)
    return parsed


def _due_window(
    now_et: datetime, windows: Mapping[str, tuple[tuple[int, int], tuple[int, int]]]
) -> str | None:
    current = now_et.time()
    for name in WINDOWS:
        start, end = windows[name]
        if wall_time(*start) <= current < wall_time(*end):
            return name
    return None


def _account_is_fresh(
    account: AccountSnapshot, fingerprint: str, now: datetime
) -> str | None:
    age = (now - account.as_of_utc).total_seconds()
    if age < -CLOCK_SKEW_TOLERANCE_SECONDS or age > MAX_ACCOUNT_AGE_SECONDS:
        return f"account snapshot is not fresh (age {age:.0f}s)"
    if account.account_fingerprint != fingerprint:
        return "account snapshot does not match the configured competition fingerprint"
    if not account.reconciled or account.unknown_orders:
        return "account state is not reconciled"
    return None


def _drawdown(account: AccountSnapshot) -> Decimal:
    return (account.day_start_equity - account.equity) / account.day_start_equity


def _drawdown_breach(account: AccountSnapshot, max_daily_drawdown: Decimal) -> dict[str, object] | None:
    drawdown = _drawdown(account)
    if drawdown >= max_daily_drawdown:
        return {
            "type": "DAILY_DRAWDOWN",
            "drawdown": str(drawdown),
            "limit": str(max_daily_drawdown),
            "day_start_equity": str(account.day_start_equity),
            "equity": str(account.equity),
        }
    return None


def _exposure_breaches(account: AccountSnapshot, activation: TradingActivation | None) -> list[dict[str, object]]:
    if activation is None:
        return []
    breaches: list[dict[str, object]] = []
    if activation.risk_policy_version == POLICY_VERSION_V1:
        assert activation.max_single_exposure is not None
        assert activation.max_total_exposure is not None
        gross = Decimal("0")
        for item in account.positions:
            effective = item.market_value * INSTRUMENTS[item.symbol].leverage
            if effective > account.equity * activation.max_single_exposure:
                breaches.append(
                    {
                        "type": "SINGLE_EXPOSURE",
                        "symbol": item.symbol,
                        "effective": str(effective),
                        "limit": str(account.equity * activation.max_single_exposure),
                    }
                )
            gross += effective
        if gross > account.equity * activation.max_total_exposure:
            breaches.append(
                {
                    "type": "GROSS_EXPOSURE",
                    "effective": str(gross),
                    "limit": str(account.equity * activation.max_total_exposure),
                }
            )
        return breaches
    assert activation.max_effective_exposure_fraction is not None
    signed = sum(
        (
            item.market_value
            * INSTRUMENTS[item.symbol].leverage
            * INSTRUMENTS[item.symbol].direction
            for item in account.positions
        ),
        Decimal("0"),
    )
    ceiling = account.equity * (
        activation.max_effective_exposure_fraction + EXPOSURE_CONSISTENCY_TOLERANCE
    )
    if abs(signed) > ceiling:
        breaches.append(
            {
                "type": "EFFECTIVE_EXPOSURE",
                "signed_effective": str(signed),
                "fraction": str(signed / account.equity),
                "limit": str(ceiling),
            }
        )
    return breaches


def _duration_breach(
    account: AccountSnapshot,
    ledger: SQLiteLedger,
    feed: TradingDaysFeed,
    today: date,
) -> dict[str, object] | None:
    for item in account.positions:
        if item.quantity <= 0 or not INSTRUMENTS[item.symbol].leveraged:
            continue
        entry = ledger.latest_event_payload("AUTO_PAPER_ENTRY", item.symbol)
        exit_event = ledger.latest_event_payload("AUTO_PAPER_EXIT", item.symbol)
        if entry is None or (exit_event is not None and exit_event[1] > entry[1]):
            continue
        entry_session = str(entry[0].get("session") or "")
        try:
            entry_date = date.fromisoformat(entry_session)
        except ValueError:
            continue
        elapsed = sum(
            1 for day in feed.get_trading_days(entry_date, today) if day > entry_date
        )
        if elapsed >= DEFAULT_MAX_LEVERAGED_HOLDING_SESSIONS:
            return {
                "type": "LEVERAGED_HOLDING_DURATION",
                "symbol": item.symbol,
                "sessions_held": elapsed,
                "limit": DEFAULT_MAX_LEVERAGED_HOLDING_SESSIONS,
            }
    return None


def _leftover_open_orders(account: AccountSnapshot) -> list[dict[str, object]]:
    return [
        {
            "type": "OPEN_ORDER_AT_PRE_CLOSE",
            "symbol": order.symbol,
            "side": order.side.value,
            "remaining_quantity": order.remaining_quantity,
        }
        for order in account.open_orders
    ]


def _reconcile_submissions(
    reconciler: Any, ledger: SQLiteLedger, now: datetime
) -> dict[str, object]:
    attempted = 0
    resolved = 0
    for row in ledger.list_submissions():
        if row["status"] not in RECONCILABLE_STATUSES:
            continue
        attempted += 1
        result = reconciler.reconcile(row["client_order_key"], now)
        if result is not None and result.status.value not in {
            OrderStatus.SUBMITTING.value,
            OrderStatus.UNKNOWN.value,
        }:
            resolved += 1
    return {"attempted": attempted, "resolved": resolved}


def _ambiguous_submission_breach(ledger: SQLiteLedger) -> dict[str, object] | None:
    unresolved: list[str] = []
    for row in ledger.list_submissions():
        if row["status"] in {OrderStatus.SUBMITTING.value, OrderStatus.UNKNOWN.value}:
            unresolved.append(str(row["client_order_key"]))
    if unresolved:
        return {
            "type": "AMBIGUOUS_SUBMISSION",
            "client_order_keys": unresolved,
        }
    return None


def _engage_kill_switch(ledger: SQLiteLedger, now: datetime, reason: str) -> bool:
    if ledger.kill_switch_engaged():
        return False
    ledger.set_kill_switch(True)
    ledger.append_event(
        "KILL_SWITCH_ENGAGED",
        now,
        None,
        "risk_monitor",
        {"reason": reason},
    )
    return True


def run_checks(
    *,
    now: datetime,
    ledger: SQLiteLedger,
    reads: MoomooRestBroker,
    reconciler: Any,
    feed: TradingDaysFeed,
    fingerprint: str,
    activation: TradingActivation | None,
    window: str,
    session_iso: str,
) -> dict[str, object]:
    """Run the checks for one monitor window and return the report.

    Appends ``RISK_BREACH`` and ``KILL_SWITCH_ENGAGED`` audit events; the kill
    switch engages on the daily-drawdown threshold and on ambiguous
    submissions still unresolved at the pre-close check.
    """
    if now.tzinfo is None:
        raise ValueError("monitor clock must be timezone-aware")
    if window not in WINDOWS:
        raise ValueError(f"unsupported monitor window {window!r}")
    base: dict[str, object] = {
        "schema_version": "1",
        "mode": "RISK_MONITOR",
        "window": window,
        "checked_at_utc": now.isoformat(),
        "session": session_iso,
        "order_writes_enabled": False,
        "policy_version": activation.risk_policy_version if activation else None,
    }
    try:
        account = reads.get_account_snapshot()
    except Exception as exc:
        base.update({"status": "CHECK_FAILED", "error": f"account read failed ({type(exc).__name__})"})
        ledger.append_event(
            "RISK_MONITOR_RESULT",
            now,
            None,
            "risk_monitor",
            {"window": window, "session": session_iso, "status": "CHECK_FAILED", "error": str(exc)},
        )
        return base
    if stale := _account_is_fresh(account, fingerprint, now):
        base.update({"status": "CHECK_FAILED", "error": stale})
        ledger.append_event(
            "RISK_MONITOR_RESULT",
            now,
            None,
            "risk_monitor",
            {"window": window, "session": session_iso, "status": "CHECK_FAILED", "error": stale},
        )
        return base

    breaches: list[dict[str, object]] = []
    reconciliation: dict[str, object] | None = None
    kill_reason: str | None = None

    if window == "reconcile":
        reconciliation = _reconcile_submissions(reconciler, ledger, now)
        if ambiguous := _ambiguous_submission_breach(ledger):
            breaches.append(ambiguous)

    if window in {"midday", "pre_close"}:
        max_daily_drawdown = (
            activation.max_daily_drawdown if activation is not None else DEFAULT_MAX_DAILY_DRAWDOWN
        )
        if drawdown := _drawdown_breach(account, max_daily_drawdown):
            breaches.append(drawdown)
            kill_reason = "daily drawdown threshold reached"
        breaches.extend(_exposure_breaches(account, activation))
        if duration := _duration_breach(account, ledger, feed, date.fromisoformat(session_iso)):
            breaches.append(duration)

    if window == "pre_close":
        breaches.extend(_leftover_open_orders(account))
        if ambiguous := _ambiguous_submission_breach(ledger):
            breaches.append(ambiguous)
            kill_reason = "ambiguous submission unresolved at the pre-close check"

    engaged = False
    if kill_reason is not None:
        engaged = _engage_kill_switch(ledger, now, kill_reason)

    for breach in breaches:
        ledger.append_event(
            "RISK_BREACH",
            now,
            None,
            "risk_monitor",
            {"window": window, "session": session_iso, **breach},
        )

    base.update(
        {
            "status": "COMPLETED",
            "account": {
                "equity": str(account.equity),
                "day_start_equity": str(account.day_start_equity),
                "cash": str(account.cash),
                "drawdown": str(_drawdown(account)),
                "positions": [
                    {"symbol": item.symbol, "quantity": item.quantity, "market_value": str(item.market_value)}
                    for item in account.positions
                ],
                "open_orders": len(account.open_orders),
            },
            "breaches": breaches,
            "kill_switch": {"engaged": engaged, "reason": kill_reason},
            "reconciliation": reconciliation,
        }
    )
    ledger.append_event(
        "RISK_MONITOR_RESULT",
        now,
        None,
        "risk_monitor",
        {
            "window": window,
            "session": session_iso,
            "status": "COMPLETED",
            "breach_count": len(breaches),
            "kill_switch_engaged": engaged,
        },
    )
    return base


def _monitor_stack(ledger: SQLiteLedger, lock: AccountLock) -> SupervisedExecution:
    load_local_env(ROOT / ".env")
    if os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower() not in {"false", "0", "no", ""}:
        raise ScheduleError("ORDER_WRITES_ENABLED must remain false for the risk monitor")
    store = FileTokenStore(default_token_path())
    record = store.load()
    if record is None:
        raise ScheduleError("Moomoo read authorization is required")
    if record.has_trade_write():
        raise ScheduleError("stored authorization contains trade:write; refusing")
    if not record.has_required_scopes():
        raise ScheduleError("stored authorization lacks required read scopes")
    return build_supervised_execution(
        MoomooOAuth(store, open_browser=None),
        lock,
        ledger,
        order_writes_enabled=False,
    )


def _execute(window: str, session: date, output_dir: Path) -> dict[str, object]:
    load_local_env(ROOT / ".env")
    now = datetime.now(UTC)
    lock = AccountLock.from_env(os.environ)
    ledger = SQLiteLedger(ledger_path_from_env(os.environ))
    stack = _monitor_stack(ledger, lock)
    feed = _history_feed()
    report = run_checks(
        now=now,
        ledger=ledger,
        reads=stack.reads,
        reconciler=stack.service,
        feed=feed,
        fingerprint=lock.expected_fingerprint,
        activation=ledger.latest_trading_activation(),
        window=window,
        session_iso=session.isoformat(),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{window}-{now:%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {
        "exit_code": 0 if report.get("status") == "COMPLETED" else 1,
        "window": window,
        "session_date": session.isoformat(),
        "status": str(report.get("status")),
        "breaches": [item.get("type") for item in report.get("breaches", [])],
        "kill_switch_engaged": bool(report.get("kill_switch", {}).get("engaged")),
        "report_path": str(path.relative_to(ROOT)),
        "order_writes_enabled": False,
    }


def run_once(
    now: datetime,
    *,
    config_path: Path = DEFAULT_CONFIG,
    state_path: Path = DEFAULT_STATE,
    output_dir: Path | None = None,
    due_session: date | None = None,
    trading_day: bool | None = None,
    trigger: str = "manual",
    log_path: Path | None = None,
    lock_path: Path | None = None,
) -> dict[str, object]:
    if now.tzinfo is None:
        raise ValueError("risk monitor clock must be timezone-aware")
    if trigger not in {"manual", "task_scheduler"}:
        raise ValueError("risk monitor trigger must be manual or task_scheduler")
    config = _config(config_path)
    windows = _parse_windows(config)
    now_et = now.astimezone(NY)
    checked_at_utc = datetime.now(UTC).isoformat()
    log = log_path or (
        DEFAULT_LOG if state_path == DEFAULT_STATE else state_path.with_suffix(".events.jsonl")
    )
    window = _due_window(now_et, windows)
    if window is None:
        event = {
            "status": "SKIPPED_NOT_IN_WINDOW",
            "trigger": trigger,
            "checked_at_utc": checked_at_utc,
            "order_writes_enabled": False,
        }
        _append_log(log, event)
        return event

    if due_session is None:
        feed = _history_feed()
        is_trading_day = _is_trading_session(now_et.date(), feed)
        due_session = now_et.date()
    else:
        is_trading_day = True if trading_day is None else trading_day
    run_key = f"{window}-{due_session.isoformat()}"
    lock = lock_path or state_path.with_suffix(".lock")

    with _exclusive_lock(lock) as acquired:
        if not acquired:
            event = {
                "run_key": run_key,
                "status": "SKIPPED_ALREADY_RUNNING",
                "trigger": trigger,
                "checked_at_utc": checked_at_utc,
                "order_writes_enabled": False,
            }
            _append_log(log, event)
            return event

        state = _load_state(state_path)
        history = state["history"]
        previous = next(
            (item for item in reversed(history) if item.get("run_key") == run_key),
            None,
        )
        if previous and previous.get("status") == "RUNNING":
            previous["status"] = "ABANDONED"
            previous["abandoned_at_utc"] = checked_at_utc
            previous["abandon_reason"] = (
                "monitor lock acquired after a prior RUNNING record; the prior process no longer holds the lock"
            )
            _write_state(state_path, state)
            _append_log(log, {**previous, "trigger": trigger})
        if previous and previous.get("status") in {"COMPLETED", "CHECK_FAILED", "ABSTAINED"}:
            event = {
                "run_key": run_key,
                "status": "SKIPPED_ALREADY_RUN",
                "trigger": trigger,
                "checked_at_utc": checked_at_utc,
                "previous": previous,
                "order_writes_enabled": False,
            }
            _append_log(log, event)
            return event
        if not is_trading_day:
            event = {
                "run_key": run_key,
                "status": "SKIPPED_NOT_TRADING_DAY",
                "trigger": trigger,
                "checked_at_utc": checked_at_utc,
                "window": window,
                "session": due_session.isoformat(),
                "order_writes_enabled": False,
            }
            history.append(event)
            _write_state(state_path, state)
            _append_log(log, event)
            return event

        attempt = 1 + sum(1 for item in history if item.get("run_key") == run_key)
        event: dict[str, object] = {
            "run_key": run_key,
            "status": "RUNNING",
            "attempt": attempt,
            "trigger": trigger,
            "started_at_utc": checked_at_utc,
            "window": window,
            "session": due_session.isoformat(),
            "order_writes_enabled": False,
        }
        history.append(event)
        _write_state(state_path, state)
        _append_log(log, event)
        try:
            result = _execute(
                window,
                due_session,
                output_dir or ROOT / "evidence" / "risk-monitor" / due_session.isoformat(),
            )
            event.update(result)
            event["status"] = result["status"]
        except KeyboardInterrupt:
            event["status"] = "INTERRUPTED"
            event["error"] = "process interrupted while the risk monitor was running"
            raise
        except Exception as exc:
            event["status"] = "FAILED"
            event["error"] = str(exc) or exc.__class__.__name__
        finally:
            event["finished_at_utc"] = datetime.now(UTC).isoformat()
            _write_state(state_path, state)
            _append_log(log, event)
        return event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one daily risk-monitor check")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--lock", type=Path, default=None)
    parser.add_argument("--once", action="store_true", help="manual one-shot check")
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="invoked by Windows Task Scheduler",
    )
    args = parser.parse_args(argv)
    trigger = "task_scheduler" if args.scheduled else "manual"
    try:
        event = run_once(
            datetime.now(NY),
            config_path=args.config,
            state_path=args.state,
            output_dir=args.output_dir,
            trigger=trigger,
            log_path=args.log,
            lock_path=args.lock,
        )
        print(json.dumps(event, indent=2))
        return 0 if event["status"] in {
            "COMPLETED",
            "CHECK_FAILED",
            "SKIPPED_NOT_IN_WINDOW",
            "SKIPPED_NOT_TRADING_DAY",
            "SKIPPED_ALREADY_RUN",
            "SKIPPED_ALREADY_RUNNING",
        } else 1
    except KeyboardInterrupt:
        return 1
    except Exception as exc:
        event = {
            "status": "FAILED",
            "trigger": trigger,
            "error": str(exc) or exc.__class__.__name__,
            "order_writes_enabled": False,
        }
        _append_log(args.log, event)
        print(json.dumps(event, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
