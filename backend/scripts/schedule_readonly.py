"""Local read-only Qoder schedule with durable task-run records.

Windows Task Scheduler invokes this module. The schedule has no order
authority: it refreshes read-only bars, runs the deterministic current-market
collection and the three-agent Qoder workflow, and never imports or invokes an
order adapter.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager, redirect_stdout
from datetime import UTC, date, datetime, time as wall_time, timedelta
from io import StringIO
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from app.broker.moomoo_auth import FileTokenStore, MoomooOAuth, default_token_path
from app.broker.moomoo_history import MoomooHistoryFeed
from app.broker.moomoo_rest import MoomooRestClient
from app.cli import load_local_env
from scripts import current_market_run, refresh_daily_bars

ROOT = Path(__file__).resolve().parents[2]
NY = ZoneInfo("America/New_York")
DEFAULT_CONFIG = ROOT / "backend" / "config" / "readonly_schedule.json"
DEFAULT_STATE = ROOT / "data" / "readonly_schedule.json"
DEFAULT_LOG = ROOT / "data" / "scheduler-events.jsonl"
DEFAULT_LOCK = ROOT / "data" / "readonly_schedule.lock"


class ScheduleError(RuntimeError):
    pass


def _config(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScheduleError("schedule config must be a JSON object")
    if payload.get("timezone") not in {None, "America/New_York"}:
        raise ScheduleError("schedule timezone must be America/New_York")
    return payload


def _parse_run_time(value: object) -> tuple[int, int]:
    if not isinstance(value, str):
        raise ScheduleError("schedule run_time must be HH:MM")
    try:
        hour, minute = (int(part) for part in value.split(":"))
    except (TypeError, ValueError):
        raise ScheduleError("schedule run_time must be HH:MM") from None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ScheduleError("schedule run_time is out of range")
    return hour, minute


def _load_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"history": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScheduleError("schedule state is not an object")
    if not isinstance(payload.get("history"), list):
        raise ScheduleError("schedule state history is not a list")
    return payload


def _write_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(path)


def _append_log(path: Path, event: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"logged_at_utc": datetime.now(UTC).isoformat(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                yield False
                return
            locked = True
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                yield False
                return
            locked = True
        yield True
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def next_fire(now: datetime, hour: int, minute: int) -> datetime:
    if now.tzinfo is None:
        raise ValueError("schedule clock must be timezone-aware")
    local = now.astimezone(NY)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _calendar_due(now_et: datetime, hour: int, minute: int) -> date:
    candidate = now_et.date()
    if now_et.time() < wall_time(hour, minute):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _history_feed() -> MoomooHistoryFeed:
    load_local_env(ROOT / ".env")
    store = FileTokenStore(default_token_path())
    record = store.load()
    if record is None:
        raise ScheduleError("Moomoo read authorization is required")
    if record.has_trade_write():
        raise ScheduleError("stored authorization contains trade:write; refusing")
    if not record.has_required_scopes():
        raise ScheduleError("stored authorization lacks required read scopes")
    return MoomooHistoryFeed(MoomooRestClient(MoomooOAuth(store, open_browser=None)))


def _latest_trading_session(candidate: date, feed: MoomooHistoryFeed) -> date:
    days = feed.get_trading_days(candidate - timedelta(days=14), candidate)
    eligible = [day for day in days if day <= candidate]
    if not eligible:
        raise ScheduleError("no US trading day is available in the lookback window")
    return eligible[-1]


def _is_trading_session(day: date, feed: MoomooHistoryFeed) -> bool:
    return day in feed.get_trading_days(day, day)


def _latest_artifact(output_dir: Path, started_at: float) -> dict[str, object] | None:
    candidates = [
        path
        for path in output_dir.glob("qoder-*.json")
        if path.stat().st_mtime >= started_at
    ]
    if not candidates:
        return None
    path = max(candidates, key=lambda item: item.stat().st_mtime)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _execute(window: str, output_dir: Path, session_date: date) -> dict[str, object]:
    load_local_env(ROOT / ".env")
    if os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower() not in {"false", "0", "no", ""}:
        raise ScheduleError("ORDER_WRITES_ENABLED must remain false")
    started_at = time.time()
    if window == "post-close":
        bars_path, _ = refresh_daily_bars.refresh(session_date)
    else:
        bars_path = current_market_run._latest_bars_file()
    buffer = StringIO()
    with redirect_stdout(buffer):
        code = current_market_run.main(
            ["--window", window, "--bars", str(bars_path), "--output-dir", str(output_dir)]
        )
    artifact = _latest_artifact(output_dir, started_at)
    return {
        "exit_code": code,
        "window": window,
        "session_date": session_date.isoformat(),
        "bars_path": str(bars_path.relative_to(ROOT)),
        "stdout": buffer.getvalue()[-4000:],
        "run_id": artifact.get("run_id") if artifact else None,
        "status": artifact.get("status") if artifact else "NO_ARTIFACT",
        "outcome": artifact.get("outcome") if artifact else None,
        "report_path": (
            str(output_dir / f"{artifact['run_id']}.md") if artifact and artifact.get("run_id") else None
        ),
        "order_writes_enabled": False,
    }


def run_once(
    now: datetime,
    *,
    config_path: Path = DEFAULT_CONFIG,
    state_path: Path = DEFAULT_STATE,
    output_dir: Path | None = None,
    window: str | None = None,
    trading_day: bool | None = None,
    due_session: date | None = None,
    trigger: str = "manual",
    log_path: Path | None = None,
    lock_path: Path | None = None,
) -> dict[str, object]:
    if now.tzinfo is None:
        raise ValueError("schedule clock must be timezone-aware")
    if trigger not in {"manual", "task_scheduler"}:
        raise ValueError("schedule trigger must be manual or task_scheduler")
    config = _config(config_path)
    hour, minute = _parse_run_time(config.get("run_time", "16:20"))
    schedule_window = window or str(config.get("window", "post-close"))
    if schedule_window not in {"post-close", "session"}:
        raise ScheduleError("schedule window must be post-close or session")
    now_et = now.astimezone(NY)
    candidate = due_session or _calendar_due(now_et, hour, minute)
    if candidate > now_et.date():
        raise ScheduleError("schedule session is in the future")
    run_started_at = datetime.now(UTC)
    log = log_path or (
        DEFAULT_LOG if state_path == DEFAULT_STATE else state_path.with_suffix(".events.jsonl")
    )
    lock = lock_path or state_path.with_suffix(".lock")

    with _exclusive_lock(lock) as acquired:
        if not acquired:
            event = {
                "run_key": candidate.isoformat(),
                "status": "SKIPPED_ALREADY_RUNNING",
                "trigger": trigger,
                "checked_at_utc": run_started_at.isoformat(),
                "order_writes_enabled": False,
            }
            _append_log(log, event)
            return event

        if due_session is None and trading_day is None:
            feed = _history_feed()
            due_session = _latest_trading_session(candidate, feed)
            is_trading_day = True
        elif due_session is None:
            due_session = candidate
            is_trading_day = trading_day
        elif trading_day is None:
            is_trading_day = _is_trading_session(due_session, _history_feed())
        else:
            is_trading_day = trading_day

        run_key = due_session.isoformat()
        scheduled_for = datetime.combine(due_session, wall_time(hour, minute), NY)
        minutes_late = max(0.0, (now_et - scheduled_for).total_seconds() / 60)
        catch_up = due_session < now_et.date() or minutes_late > 15
        state = _load_state(state_path)
        history = state["history"]
        previous = next(
            (item for item in reversed(history) if item.get("run_key") == run_key),
            None,
        )
        if previous and previous.get("status") == "RUNNING":
            previous["status"] = "ABANDONED"
            previous["abandoned_at_utc"] = run_started_at.isoformat()
            previous["abandon_reason"] = (
                "scheduler lock acquired after a prior RUNNING record; the prior process no longer holds the lock"
            )
            _write_state(state_path, state)
            _append_log(log, {**previous, "trigger": trigger})
        if previous and previous.get("status") == "COMPLETED":
            event = {
                "run_key": run_key,
                "status": "SKIPPED_ALREADY_RUN",
                "trigger": trigger,
                "checked_at_utc": run_started_at.isoformat(),
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
                "checked_at_utc": run_started_at.isoformat(),
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
            "started_at_utc": run_started_at.isoformat(),
            "scheduled_for_et": scheduled_for.isoformat(),
            "minutes_late": round(minutes_late, 3),
            "catch_up": catch_up,
            "window": schedule_window,
            "order_writes_enabled": False,
        }
        history.append(event)
        _write_state(state_path, state)
        _append_log(log, event)
        try:
            result = _execute(schedule_window, output_dir or ROOT / "evidence" / "qoder", due_session)
            event.update(result)
            event["status"] = "COMPLETED" if result["exit_code"] == 0 else "FAILED"
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
    parser = argparse.ArgumentParser(description="Run one read-only Qoder schedule check")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence" / "qoder")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--lock", type=Path, default=None)
    parser.add_argument("--once", action="store_true", help="manual one-shot check")
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="invoked by Windows Task Scheduler",
    )
    parser.add_argument("--window", choices=["session", "post-close"], default=None)
    args = parser.parse_args(argv)
    trigger = "task_scheduler" if args.scheduled else "manual"
    try:
        event = run_once(
            datetime.now(NY),
            config_path=args.config,
            state_path=args.state,
            output_dir=args.output_dir,
            window=args.window,
            trigger=trigger,
            log_path=args.log,
            lock_path=args.lock,
        )
        print(json.dumps(event, indent=2))
        return 0 if event["status"] in {
            "COMPLETED",
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
    raise SystemExit(main(sys.argv[1:]))
