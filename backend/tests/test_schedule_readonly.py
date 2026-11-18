import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from scripts import schedule_readonly

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def test_next_fire_uses_new_york_time_and_skips_weekends(tmp_path):
    friday_after = datetime(2026, 11, 13, 16, 30, tzinfo=NY)
    due = schedule_readonly.next_fire(friday_after, 16, 20)
    assert due == datetime(2026, 11, 16, 16, 20, tzinfo=NY)

    friday_before = datetime(2026, 11, 13, 9, 0, tzinfo=NY)
    assert schedule_readonly.next_fire(friday_before, 16, 20) == datetime(
        2026, 11, 13, 16, 20, tzinfo=NY
    )


def test_calendar_due_catches_up_late_and_before_time():
    late = datetime(2026, 11, 17, 20, 5, tzinfo=NY)
    assert schedule_readonly._calendar_due(late, 16, 20) == date(2026, 11, 17)

    before = datetime(2026, 11, 18, 9, 0, tzinfo=NY)
    assert schedule_readonly._calendar_due(before, 16, 20) == date(2026, 11, 17)

    weekend = datetime(2026, 11, 21, 16, 30, tzinfo=NY)
    assert schedule_readonly._calendar_due(weekend, 16, 20) == date(2026, 11, 20)


def test_run_once_is_idempotent_and_persists_no_order_authority(tmp_path, monkeypatch):
    calls = []

    def fake_execute(window, output_dir, session_date):
        calls.append((window, session_date))
        return {
            "exit_code": 0,
            "window": window,
            "session_date": session_date.isoformat(),
            "run_id": "qoder-test",
            "status": "COMPLETED",
            "outcome": "NO_TRADE",
            "order_writes_enabled": False,
        }

    monkeypatch.setattr(schedule_readonly, "_execute", fake_execute)
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"timezone": "America/New_York", "run_time": "16:20", "window": "post-close"}),
        encoding="utf-8",
    )
    state = tmp_path / "state.json"
    now = datetime(2026, 11, 17, 16, 25, tzinfo=NY)
    first = schedule_readonly.run_once(
        now, config_path=config, state_path=state, output_dir=tmp_path, trading_day=True
    )
    second = schedule_readonly.run_once(
        now, config_path=config, state_path=state, output_dir=tmp_path, trading_day=True
    )
    assert first["status"] == "COMPLETED"
    assert first["run_key"] == "2026-11-17"
    assert second["status"] == "SKIPPED_ALREADY_RUN"
    assert calls == [("post-close", date(2026, 11, 17))]
    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["history"][0]["order_writes_enabled"] is False
    assert payload["history"][0]["run_id"] == "qoder-test"


def test_late_trigger_records_catch_up_and_does_not_repeat(tmp_path, monkeypatch):
    calls = []

    def fake_execute(window, output_dir, session_date):
        calls.append(session_date)
        return {
            "exit_code": 0,
            "window": window,
            "session_date": session_date.isoformat(),
            "run_id": "qoder-catch-up",
            "status": "COMPLETED",
            "outcome": "NO_TRADE",
            "order_writes_enabled": False,
        }

    monkeypatch.setattr(schedule_readonly, "_execute", fake_execute)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"run_time": "16:20", "window": "post-close"}), encoding="utf-8")
    state = tmp_path / "state.json"
    first = schedule_readonly.run_once(
        datetime(2026, 11, 17, 20, 5, tzinfo=NY),
        config_path=config,
        state_path=state,
        output_dir=tmp_path,
        trading_day=True,
    )
    second = schedule_readonly.run_once(
        datetime(2026, 11, 17, 21, 20, tzinfo=NY),
        config_path=config,
        state_path=state,
        output_dir=tmp_path,
        trading_day=True,
    )
    assert first["status"] == "COMPLETED"
    assert first["run_key"] == "2026-11-17"
    assert first["catch_up"] is True
    assert first["minutes_late"] > 200
    assert second["status"] == "SKIPPED_ALREADY_RUN"
    assert calls == [date(2026, 11, 17)]


def test_run_once_skips_non_trading_days_without_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(
        schedule_readonly,
        "_execute",
        lambda *args: (_ for _ in ()).throw(AssertionError("must not execute")),
    )
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"run_time": "16:20", "window": "post-close"}), encoding="utf-8")
    state = tmp_path / "state.json"
    event = schedule_readonly.run_once(
        datetime(2026, 11, 26, 16, 25, tzinfo=NY),
        config_path=config,
        state_path=state,
        output_dir=tmp_path,
        trading_day=False,
    )
    assert event["status"] == "SKIPPED_NOT_TRADING_DAY"
    assert event["order_writes_enabled"] is False


def test_failed_run_can_retry_and_abandoned_running_record_is_recovered(tmp_path, monkeypatch):
    calls = []

    def fake_execute(window, output_dir, session_date):
        calls.append(session_date)
        return {
            "exit_code": 1,
            "window": window,
            "session_date": session_date.isoformat(),
            "status": "FAILED",
            "order_writes_enabled": False,
        }

    monkeypatch.setattr(schedule_readonly, "_execute", fake_execute)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"run_time": "16:20", "window": "post-close"}), encoding="utf-8")
    state = tmp_path / "state.json"
    now = datetime(2026, 11, 17, 16, 25, tzinfo=NY)
    first = schedule_readonly.run_once(
        now, config_path=config, state_path=state, output_dir=tmp_path, trading_day=True
    )
    assert first["status"] == "FAILED"
    second = schedule_readonly.run_once(
        now, config_path=config, state_path=state, output_dir=tmp_path, trading_day=True
    )
    assert second["status"] == "FAILED"

    payload = json.loads(state.read_text(encoding="utf-8"))
    payload["history"][-1]["status"] = "RUNNING"
    state.write_text(json.dumps(payload), encoding="utf-8")
    third = schedule_readonly.run_once(
        now, config_path=config, state_path=state, output_dir=tmp_path, trading_day=True
    )
    assert third["status"] == "FAILED"
    assert third["attempt"] == 3
    assert len(calls) == 3


def test_interrupted_run_is_persisted_before_the_process_exits(tmp_path, monkeypatch):
    def interrupt(window, output_dir, session_date):
        raise KeyboardInterrupt

    monkeypatch.setattr(schedule_readonly, "_execute", interrupt)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"run_time": "16:20", "window": "post-close"}), encoding="utf-8")
    state = tmp_path / "state.json"
    with pytest.raises(KeyboardInterrupt):
        schedule_readonly.run_once(
            datetime(2026, 11, 17, 16, 25, tzinfo=NY),
            config_path=config,
            state_path=state,
            output_dir=tmp_path,
            trading_day=True,
        )
    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["history"][-1]["status"] == "INTERRUPTED"
    assert payload["history"][-1]["finished_at_utc"] is not None
    assert payload["history"][-1]["order_writes_enabled"] is False


def test_scheduler_lock_rejects_a_second_holder(tmp_path):
    lock = tmp_path / "scheduler.lock"
    with schedule_readonly._exclusive_lock(lock) as first:
        assert first is True
        with schedule_readonly._exclusive_lock(lock) as second:
            assert second is False
    with schedule_readonly._exclusive_lock(lock) as third:
        assert third is True
