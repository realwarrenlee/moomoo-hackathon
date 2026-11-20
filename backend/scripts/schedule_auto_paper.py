"""AUTO_PAPER execution-phase scheduler.

Windows Task Scheduler invokes this module at 13:35Z and 14:35Z (09:35 ET in
either US DST offset). The execution phase runs only inside the documented
09:35-10:30 ET window, against the read-only scheduler's evening decision
artifacts and daily bars.

- ``TRADING_MODE=SUPERVISED_PAPER``: the supervised decision phase runs with
  writes disabled, records the deterministic decision and awaits exact-order
  owner approval. No submission path exists in this mode.
- ``TRADING_MODE=AUTO_PAPER``: ``ORDER_WRITES_ENABLED=true`` is scoped to the
  executor subprocess only, and every submission still requires the durable
  activation pin and all per-run checks.

Every miss fails closed: outside the window, no prior-session decision
artifact, no AUTO_PAPER activation pin, an engaged kill switch or a
market-closed quote all produce an abstention and no submission.
"""

from __future__ import annotations

import argparse
import json
import os
from contextlib import redirect_stdout
from datetime import UTC, date, datetime, time as wall_time, timedelta
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import auto_paper_run
from scripts.schedule_readonly import (
    ScheduleError,
    _append_log,
    _exclusive_lock,
    _history_feed,
    _is_trading_session,
    _latest_trading_session,
    _load_state,
    _write_state,
)

ROOT = Path(__file__).resolve().parents[2]
NY = ZoneInfo("America/New_York")
DEFAULT_CONFIG = ROOT / "backend" / "config" / "auto_paper_schedule.json"
DEFAULT_STATE = ROOT / "data" / "auto_paper_schedule.json"
DEFAULT_LOG = ROOT / "data" / "auto-scheduler-events.jsonl"
DEFAULT_LOCK = ROOT / "data" / "auto_paper_schedule.lock"
DECISION_ARTIFACTS = ROOT / "evidence" / "qoder"


def _config(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScheduleError("schedule config must be a JSON object")
    if payload.get("timezone") not in {None, "America/New_York"}:
        raise ScheduleError("schedule timezone must be America/New_York")
    return payload


def _parse_time(value: object, field: str) -> tuple[int, int]:
    if not isinstance(value, str):
        raise ScheduleError(f"schedule {field} must be HH:MM")
    try:
        hour, minute = (int(part) for part in value.split(":"))
    except (TypeError, ValueError):
        raise ScheduleError(f"schedule {field} must be HH:MM") from None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ScheduleError(f"schedule {field} is out of range")
    return hour, minute


def _window_open(now_et: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    current = now_et.time()
    return wall_time(*start) <= current < wall_time(*end)


def _execute_phase(session: date, output_dir: Path) -> dict[str, object]:
    bars_path = ROOT / "evidence" / "current-market" / session.isoformat() / "daily-bars.json"
    previous = os.environ.get("ORDER_WRITES_ENABLED")
    # Writes are scoped to the executor subprocess only in autonomous mode;
    # the supervised decision phase runs with the runtime's disabled writes.
    enable_writes = os.environ.get("TRADING_MODE", "").strip().upper() == "AUTO_PAPER"
    if enable_writes:
        os.environ["ORDER_WRITES_ENABLED"] = "true"
    try:
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = auto_paper_run.main(
                [
                    "--bars",
                    str(bars_path),
                    "--artifact-dir",
                    str(DECISION_ARTIFACTS),
                    "--output-dir",
                    str(output_dir),
                    "--expected-session",
                    session.isoformat(),
                ]
            )
    finally:
        if previous is None:
            os.environ.pop("ORDER_WRITES_ENABLED", None)
        else:
            os.environ["ORDER_WRITES_ENABLED"] = previous
    return {
        "exit_code": code,
        "session_date": session.isoformat(),
        "bars_path": str(bars_path.relative_to(ROOT)) if bars_path.exists() else None,
        "stdout": buffer.getvalue()[-4000:],
        "order_writes_enabled_scoped": enable_writes,
        "trading_mode": os.environ.get("TRADING_MODE", "").strip().upper(),
    }


def run_once(
    now: datetime,
    *,
    config_path: Path = DEFAULT_CONFIG,
    state_path: Path = DEFAULT_STATE,
    output_dir: Path | None = None,
    execution_session: date | None = None,
    trading_day: bool | None = None,
    trigger: str = "manual",
    log_path: Path | None = None,
    lock_path: Path | None = None,
) -> dict[str, object]:
    if now.tzinfo is None:
        raise ValueError("schedule clock must be timezone-aware")
    if trigger not in {"manual", "task_scheduler"}:
        raise ValueError("schedule trigger must be manual or task_scheduler")
    config = _config(config_path)
    start = _parse_time(config.get("execution_time", "09:35"), "execution_time")
    end = _parse_time(config.get("window_end", "10:30"), "window_end")
    now_et = now.astimezone(NY)
    checked_at_utc = datetime.now(UTC).isoformat()
    log = log_path or (
        DEFAULT_LOG if state_path == DEFAULT_STATE else state_path.with_suffix(".events.jsonl")
    )
    if not _window_open(now_et, start, end):
        event = {
            "status": "SKIPPED_NOT_IN_WINDOW",
            "trigger": trigger,
            "checked_at_utc": checked_at_utc,
            "window_start_et": f"{start[0]:02d}:{start[1]:02d}",
            "window_end_et": f"{end[0]:02d}:{end[1]:02d}",
            "order_writes_enabled": False,
        }
        _append_log(log, event)
        return event

    if execution_session is None:
        feed = _history_feed()
        is_trading_day = _is_trading_session(now_et.date(), feed)
        execution_session = (
            _latest_trading_session(now_et.date() - timedelta(days=1), feed)
            if is_trading_day
            else now_et.date()
        )
    else:
        is_trading_day = True if trading_day is None else trading_day
    run_key = f"execution-{execution_session.isoformat()}"
    scheduled_for = datetime.combine(execution_session + timedelta(days=1), wall_time(*start), NY)
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
                "scheduler lock acquired after a prior RUNNING record; the prior process no longer holds the lock"
            )
            _write_state(state_path, state)
            _append_log(log, {**previous, "trigger": trigger})
        if previous and previous.get("status") in {"COMPLETED", "ABSTAINED", "UNKNOWN_OUTCOME"}:
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
                "scheduled_for_et": scheduled_for.isoformat(),
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
            "scheduled_for_et": scheduled_for.isoformat(),
            "order_writes_enabled_scoped": (
                os.environ.get("TRADING_MODE", "").strip().upper() == "AUTO_PAPER"
            ),
        }
        history.append(event)
        _write_state(state_path, state)
        _append_log(log, event)
        try:
            result = _execute_phase(
                execution_session,
                output_dir or ROOT / "evidence" / "auto" / execution_session.isoformat(),
            )
            event.update(result)
            if result["exit_code"] == 0:
                event["status"] = "COMPLETED"
            elif result["exit_code"] == 3:
                event["status"] = "UNKNOWN_OUTCOME"
            else:
                event["status"] = "ABSTAINED"
        except KeyboardInterrupt:
            event["status"] = "INTERRUPTED"
            event["error"] = "process interrupted while the schedule was running"
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
    parser = argparse.ArgumentParser(description="Run one AUTO_PAPER execution-schedule check")
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
