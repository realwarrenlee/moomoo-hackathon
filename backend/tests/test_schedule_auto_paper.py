import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from scripts import schedule_auto_paper
from scripts.schedule_readonly import ScheduleError

NY = ZoneInfo("America/New_York")


class FakeFeed:
    def __init__(self, days: tuple[date, ...]) -> None:
        self.days = set(days)

    def get_trading_days(self, start: date, end: date) -> list[date]:
        return sorted(day for day in self.days if start <= day <= end)


def _config(tmp_path, **overrides):
    payload = {"timezone": "America/New_York", "execution_time": "09:35", "window_end": "10:30"}
    payload.update(overrides)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_window_open_uses_new_york_wall_clock_and_dst_offsets():
    start, end = (9, 35), (10, 30)
    assert schedule_auto_paper._window_open(datetime(2026, 11, 18, 9, 35, tzinfo=NY), start, end)
    assert schedule_auto_paper._window_open(datetime(2026, 11, 18, 10, 29, tzinfo=NY), start, end)
    assert not schedule_auto_paper._window_open(datetime(2026, 11, 18, 9, 34, tzinfo=NY), start, end)
    assert not schedule_auto_paper._window_open(datetime(2026, 11, 18, 10, 30, tzinfo=NY), start, end)
    # 13:35Z is 09:35 ET during EDT and 08:35 ET during EST.
    edt = datetime(2026, 8, 5, 13, 35, tzinfo=ZoneInfo("UTC")).astimezone(NY)
    est = datetime(2026, 1, 7, 13, 35, tzinfo=ZoneInfo("UTC")).astimezone(NY)
    assert schedule_auto_paper._window_open(edt, start, end)
    assert not schedule_auto_paper._window_open(est, start, end)


def test_run_once_skips_outside_the_execution_window(tmp_path, monkeypatch):
    calls = []

    def fake_execute(session, output_dir):
        calls.append(session)
        return {"exit_code": 0}

    monkeypatch.setattr(schedule_auto_paper, "_execute_phase", fake_execute)
    event = schedule_auto_paper.run_once(
        datetime(2026, 11, 18, 8, 35, tzinfo=NY),
        config_path=_config(tmp_path),
        state_path=tmp_path / "state.json",
        output_dir=tmp_path,
    )
    assert event["status"] == "SKIPPED_NOT_IN_WINDOW"
    assert event["order_writes_enabled"] is False
    assert calls == []
    assert not (tmp_path / "state.json").exists()


def test_run_once_skips_when_today_is_not_a_trading_day(tmp_path, monkeypatch):
    monkeypatch.setattr(
        schedule_auto_paper,
        "_history_feed",
        lambda: FakeFeed((date(2026, 11, 13), date(2026, 11, 16))),
    )
    calls = []
    monkeypatch.setattr(
        schedule_auto_paper,
        "_execute_phase",
        lambda session, output_dir: calls.append(session) or {"exit_code": 0},
    )
    saturday = datetime(2026, 11, 14, 9, 40, tzinfo=NY)
    event = schedule_auto_paper.run_once(
        saturday,
        config_path=_config(tmp_path),
        state_path=tmp_path / "state.json",
        output_dir=tmp_path,
    )
    assert event["status"] == "SKIPPED_NOT_TRADING_DAY"
    assert calls == []
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["history"][-1]["status"] == "SKIPPED_NOT_TRADING_DAY"


def test_run_once_resolves_prior_trading_session_across_a_weekend(tmp_path, monkeypatch):
    monkeypatch.setattr(
        schedule_auto_paper,
        "_history_feed",
        lambda: FakeFeed(
            (date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16), date(2026, 11, 17))
        ),
    )
    calls = []
    monkeypatch.setattr(
        schedule_auto_paper,
        "_execute_phase",
        lambda session, output_dir: calls.append(session) or {"exit_code": 0},
    )
    monday = datetime(2026, 11, 16, 9, 40, tzinfo=NY)
    event = schedule_auto_paper.run_once(
        monday,
        config_path=_config(tmp_path),
        state_path=tmp_path / "state.json",
        output_dir=tmp_path,
    )
    assert event["status"] == "COMPLETED"
    assert calls == [date(2026, 11, 13)]


def test_run_once_records_completed_execution_and_skips_repeat(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        schedule_auto_paper,
        "_execute_phase",
        lambda session, output_dir: calls.append(session) or {"exit_code": 0},
    )
    now = datetime(2026, 11, 18, 9, 40, tzinfo=NY)
    state_path = tmp_path / "state.json"
    first = schedule_auto_paper.run_once(
        now,
        config_path=_config(tmp_path),
        state_path=state_path,
        output_dir=tmp_path,
        execution_session=date(2026, 11, 17),
    )
    assert first["status"] == "COMPLETED"
    assert calls == [date(2026, 11, 17)]
    second = schedule_auto_paper.run_once(
        now,
        config_path=_config(tmp_path),
        state_path=state_path,
        output_dir=tmp_path,
        execution_session=date(2026, 11, 17),
    )
    assert second["status"] == "SKIPPED_ALREADY_RUN"
    assert calls == [date(2026, 11, 17)]


def test_run_once_records_abstained_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(
        schedule_auto_paper,
        "_execute_phase",
        lambda session, output_dir: {"exit_code": 1},
    )
    event = schedule_auto_paper.run_once(
        datetime(2026, 11, 18, 9, 40, tzinfo=NY),
        config_path=_config(tmp_path),
        state_path=tmp_path / "state.json",
        output_dir=tmp_path,
        execution_session=date(2026, 11, 17),
    )
    assert event["status"] == "ABSTAINED"
    assert event["order_writes_enabled_scoped"] is True


def test_run_once_records_unknown_outcome(tmp_path, monkeypatch):
    monkeypatch.setattr(
        schedule_auto_paper,
        "_execute_phase",
        lambda session, output_dir: {"exit_code": 3},
    )
    event = schedule_auto_paper.run_once(
        datetime(2026, 11, 18, 9, 40, tzinfo=NY),
        config_path=_config(tmp_path),
        state_path=tmp_path / "state.json",
        output_dir=tmp_path,
        execution_session=date(2026, 11, 17),
    )
    assert event["status"] == "UNKNOWN_OUTCOME"


def test_run_once_records_failed_phase(tmp_path, monkeypatch):
    def broken(session, output_dir):
        raise RuntimeError("boom")

    monkeypatch.setattr(schedule_auto_paper, "_execute_phase", broken)
    event = schedule_auto_paper.run_once(
        datetime(2026, 11, 18, 9, 40, tzinfo=NY),
        config_path=_config(tmp_path),
        state_path=tmp_path / "state.json",
        output_dir=tmp_path,
        execution_session=date(2026, 11, 17),
    )
    assert event["status"] == "FAILED"
    assert event["error"] == "boom"


def test_run_once_abandons_stale_running_record_then_executes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        schedule_auto_paper,
        "_execute_phase",
        lambda session, output_dir: {"exit_code": 0},
    )
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "history": [
                    {
                        "run_key": "execution-2026-11-17",
                        "status": "RUNNING",
                        "attempt": 1,
                        "started_at_utc": "2026-11-18T13:40:00+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    event = schedule_auto_paper.run_once(
        datetime(2026, 11, 18, 9, 45, tzinfo=NY),
        config_path=_config(tmp_path),
        state_path=state_path,
        output_dir=tmp_path,
        execution_session=date(2026, 11, 17),
    )
    assert event["status"] == "COMPLETED"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    statuses = [item["status"] for item in state["history"]]
    assert statuses == ["ABANDONED", "COMPLETED"]
    abandoned = state["history"][0]
    assert "abandon_reason" in abandoned


def test_execute_phase_scopes_writes_and_restores_env(monkeypatch, tmp_path):
    calls = []

    def fake_main(argv):
        calls.append((argv, os.environ.get("ORDER_WRITES_ENABLED")))
        return 0

    monkeypatch.setattr(schedule_auto_paper.auto_paper_run, "main", fake_main)
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "false")
    result = schedule_auto_paper._execute_phase(date(2026, 11, 17), tmp_path)
    assert calls[0][1] == "true"
    assert os.environ["ORDER_WRITES_ENABLED"] == "false"
    assert result["exit_code"] == 0
    args = calls[0][0]
    assert args.count("--bars") == 1
    assert args.count("--artifact-dir") == 1
    assert args.count("--output-dir") == 1


def test_execute_phase_removes_writes_flag_when_absent_before(monkeypatch, tmp_path):
    monkeypatch.delenv("ORDER_WRITES_ENABLED", raising=False)

    def fake_main(argv):
        return 1

    monkeypatch.setattr(schedule_auto_paper.auto_paper_run, "main", fake_main)
    schedule_auto_paper._execute_phase(date(2026, 11, 17), tmp_path)
    assert "ORDER_WRITES_ENABLED" not in os.environ


def test_config_rejects_other_timezones(tmp_path):
    with pytest.raises(ScheduleError):
        schedule_auto_paper._config(_config(tmp_path, timezone="Asia/Singapore"))


def test_config_rejects_bad_times(tmp_path):
    with pytest.raises(ScheduleError):
        schedule_auto_paper._parse_time("25:00", "execution_time")
    with pytest.raises(ScheduleError):
        schedule_auto_paper._parse_time("9am", "window_end")
