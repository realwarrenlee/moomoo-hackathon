from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.cli import main
from app.ledger.store import SQLiteLedger
from app.models.contracts import TradingActivation, TradingMode
from app.research.strategy import EXPOSURE_POLICY_V3
from app.trading_mode import (
    AUTO_PAPER_SYMBOLS,
    TradingModeError,
    auto_paper_active,
    build_auto_paper_activation,
    exposure_policy_for_activation,
    resolve_trading_mode,
)

FINGERPRINT = "a" * 64
NOW = datetime(2026, 11, 18, 21, 0, tzinfo=UTC)


def test_resolve_trading_mode_defaults_to_read_only():
    assert resolve_trading_mode({}) is TradingMode.READ_ONLY
    assert resolve_trading_mode({"TRADING_MODE": ""}) is TradingMode.READ_ONLY
    assert (
        resolve_trading_mode({"TRADING_MODE": "supervised_paper"})
        is TradingMode.SUPERVISED_PAPER
    )
    assert (
        resolve_trading_mode({"TRADING_MODE": "AUTO_PAPER"})
        is TradingMode.AUTO_PAPER
    )


def test_resolve_trading_mode_rejects_unknown_values():
    with pytest.raises(TradingModeError, match="TRADING_MODE must be one of"):
        resolve_trading_mode({"TRADING_MODE": "LIVE"})


def test_activation_pins_the_exact_strategy_and_limits():
    activation = build_auto_paper_activation(FINGERPRINT, NOW)
    assert activation.activated_at_utc == NOW
    assert activation.activated_by == "owner"
    assert activation.account_fingerprint == FINGERPRINT
    assert activation.strategy_version == "spy-directional"
    assert activation.allowed_symbols == AUTO_PAPER_SYMBOLS
    assert activation.risk_policy_version == "risk-v3"
    assert activation.min_effective_exposure_fraction == Decimal("0.10")
    assert activation.max_effective_exposure_fraction == Decimal("0.40")
    assert not {"max_single_exposure", "max_total_exposure", "position_fraction"} & activation.model_dump().keys()
    assert activation.paper_only is True
    assert activation.order_writes_enabled is True


@pytest.mark.parametrize("version", ["risk-v1", "risk-v2", ""])
def test_activation_contract_rejects_non_v3_versions(version):
    payload = build_auto_paper_activation(FINGERPRINT, NOW).model_dump()
    payload["risk_policy_version"] = version
    with pytest.raises(ValidationError):
        TradingActivation.model_validate(payload)


@pytest.mark.parametrize("field", ["max_single_exposure", "max_total_exposure", "position_fraction"])
def test_activation_contract_has_no_legacy_runtime_fields(field):
    payload = build_auto_paper_activation(FINGERPRINT, NOW).model_dump()
    payload[field] = None
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TradingActivation.model_validate(payload)


@pytest.mark.parametrize("field", ["min_effective_exposure_fraction", "max_effective_exposure_fraction"])
@pytest.mark.parametrize("value", [None, Decimal("0"), Decimal("-0.1"), Decimal("NaN"), Decimal("Infinity")])
def test_activation_requires_positive_finite_effective_limits(field, value):
    payload = build_auto_paper_activation(FINGERPRINT, NOW).model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        TradingActivation.model_validate(payload)


@pytest.mark.parametrize("field", ["min_effective_exposure_fraction", "max_effective_exposure_fraction"])
def test_activation_effective_limits_are_required(field):
    payload = build_auto_paper_activation(FINGERPRINT, NOW).model_dump()
    del payload[field]
    with pytest.raises(ValidationError):
        TradingActivation.model_validate(payload)


@pytest.mark.parametrize("minimum,maximum", [("1.1", "1.5"), ("0.2", "0.2"), ("0.5", "0.2")])
def test_activation_rejects_invalid_effective_range(minimum, maximum):
    payload = build_auto_paper_activation(FINGERPRINT, NOW).model_dump()
    payload.update(min_effective_exposure_fraction=minimum, max_effective_exposure_fraction=maximum)
    with pytest.raises(ValidationError):
        TradingActivation.model_validate(payload)


@pytest.mark.parametrize("version", ["risk-v1", "risk-v2"])
def test_non_v3_pin_is_not_executable_even_if_validation_was_bypassed(version):
    activation = build_auto_paper_activation(FINGERPRINT, NOW).model_copy(
        update={"risk_policy_version": version}
    )
    env = {"TRADING_MODE": "AUTO_PAPER", "ORDER_WRITES_ENABLED": "true"}
    assert not auto_paper_active(env, activation, account_fingerprint=FINGERPRINT)
    with pytest.raises(TradingModeError, match="unsupported risk policy"):
        exposure_policy_for_activation(activation)


def test_exposure_policy_is_v3_with_or_without_an_activation():
    assert exposure_policy_for_activation(None) is EXPOSURE_POLICY_V3
    assert exposure_policy_for_activation(build_auto_paper_activation(FINGERPRINT, NOW)) is EXPOSURE_POLICY_V3


def test_activation_rejects_a_malformed_fingerprint():
    with pytest.raises(TradingModeError, match="64 characters"):
        build_auto_paper_activation("short", NOW)
    with pytest.raises(TradingModeError, match="SHA-256 hex"):
        build_auto_paper_activation("z" * 64, NOW)


def test_auto_paper_active_requires_env_and_pin_agreement():
    activation = build_auto_paper_activation(FINGERPRINT, NOW)
    env = {"TRADING_MODE": "AUTO_PAPER", "ORDER_WRITES_ENABLED": "true"}
    assert auto_paper_active(env, activation, account_fingerprint=FINGERPRINT) is True

    assert (
        auto_paper_active({"ORDER_WRITES_ENABLED": "true"}, activation, account_fingerprint=FINGERPRINT)
        is False
    )
    assert (
        auto_paper_active({"TRADING_MODE": "AUTO_PAPER"}, activation, account_fingerprint=FINGERPRINT)
        is False
    )
    assert (
        auto_paper_active(env, None, account_fingerprint=FINGERPRINT) is False
    )
    assert (
        auto_paper_active(env, activation, account_fingerprint="b" * 64) is False
    )


@pytest.mark.parametrize("changes", [
    {"allowed_symbols": ("SPY", "SH", "UPRO")},
    {"strategy_version": "other-strategy"},
    {"min_effective_exposure_fraction": Decimal("0.20")},
    {"max_effective_exposure_fraction": Decimal("2.00")},
    {"max_daily_drawdown": Decimal("0.03")},
])
def test_auto_paper_rejects_v3_pins_with_unapproved_limits(changes):
    activation = build_auto_paper_activation(FINGERPRINT, NOW).model_copy(update=changes)
    assert not auto_paper_active(
        {"TRADING_MODE": "AUTO_PAPER", "ORDER_WRITES_ENABLED": "true"},
        activation, account_fingerprint=FINGERPRINT,
    )


def test_auto_paper_active_honours_the_pin_expiry():
    activation = build_auto_paper_activation(
        FINGERPRINT, NOW, expires_at_utc=datetime.now(UTC) + timedelta(hours=1)
    )
    env = {"TRADING_MODE": "AUTO_PAPER", "ORDER_WRITES_ENABLED": "true"}
    assert auto_paper_active(env, activation, account_fingerprint=FINGERPRINT) is True
    expired = activation.model_copy(
        update={"expires_at_utc": datetime.now(UTC) - timedelta(seconds=1)}
    )
    assert not auto_paper_active(env, expired, account_fingerprint=FINGERPRINT)


def test_activation_rejects_expiry_at_or_before_activation_time():
    with pytest.raises(ValidationError):
        build_auto_paper_activation(FINGERPRINT, NOW, expires_at_utc=NOW)


def test_activation_expiry_round_trips_through_the_ledger(tmp_path):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    expiry = NOW + timedelta(days=2)
    ledger.record_trading_activation(
        build_auto_paper_activation(FINGERPRINT, NOW, expires_at_utc=expiry)
    )
    activation = ledger.latest_trading_activation()
    assert activation is not None
    assert activation.expires_at_utc == expiry


def test_activate_cli_accepts_expires_at_and_rejects_past_expiry(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "AUTO_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "true")
    monkeypatch.setenv("COMPETITION_ACCOUNT_FINGERPRINT", FINGERPRINT)
    ledger_path = tmp_path / "audit.db"
    expiry = datetime.now(UTC) + timedelta(days=1)

    result = main(
        [
            "moomoo-activate-auto-paper",
            "--confirm-auto-paper",
            "--expires-at",
            expiry.isoformat(),
            "--ledger",
            str(ledger_path),
        ]
    )
    assert result == 0
    activation = SQLiteLedger(ledger_path).latest_trading_activation()
    assert activation is not None
    assert activation.expires_at_utc == expiry

    result = main(
        [
            "moomoo-activate-auto-paper",
            "--confirm-auto-paper",
            "--expires-at",
            (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "--ledger",
            str(ledger_path),
        ]
    )
    assert result == 2
    assert "--expires-at must be in the future" in capsys.readouterr().out


def test_activation_round_trips_through_the_ledger_and_is_append_only(tmp_path):
    ledger = SQLiteLedger(tmp_path / "audit.db")
    assert ledger.latest_trading_activation() is None
    activation = build_auto_paper_activation(FINGERPRINT, NOW)
    ledger.record_trading_activation(activation)

    reopened = SQLiteLedger(tmp_path / "audit.db")
    loaded = reopened.latest_trading_activation()
    assert loaded is not None
    assert loaded == activation
    assert loaded.paper_only is True
    assert loaded.order_writes_enabled is True

    with reopened._connect() as connection:
        row = connection.execute("SELECT * FROM trading_activations").fetchone()
        assert all(row[field] is None for field in ("max_single_exposure", "max_total_exposure", "position_fraction"))
    for statement in (
        "UPDATE trading_activations SET activated_by = 'mallory'",
        "DELETE FROM trading_activations",
    ):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            with reopened._connect() as connection:
                connection.execute(statement)


def test_pre_risk_v2_migration_preserves_non_executable_history(tmp_path):
    path = tmp_path / "audit.db"

    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE trading_activations (
                activation_id TEXT PRIMARY KEY,
                activated_at_utc TEXT NOT NULL,
                activated_by TEXT NOT NULL,
                account_fingerprint TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                allowed_symbols_json TEXT NOT NULL,
                risk_policy_version TEXT NOT NULL,
                max_single_exposure TEXT NOT NULL,
                max_total_exposure TEXT NOT NULL,
                position_fraction TEXT NOT NULL,
                max_daily_drawdown TEXT NOT NULL,
                paper_only INTEGER NOT NULL,
                order_writes_enabled INTEGER NOT NULL,
                schema_version TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO trading_activations (
                activation_id, activated_at_utc, activated_by,
                account_fingerprint, strategy_version, allowed_symbols_json,
                risk_policy_version, max_single_exposure, max_total_exposure,
                position_fraction, max_daily_drawdown, paper_only,
                order_writes_enabled, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-v1-pin",
                "2026-11-18T16:03:10+00:00",
                "owner",
                FINGERPRINT,
                "spy-directional",
                '["SPY", "SH"]',
                "risk-v1",
                "0.10",
                "0.30",
                "0.05",
                "0.02",
                1,
                1,
                "1",
            ),
        )

        connection.row_factory = sqlite3.Row
        historical = dict(connection.execute("SELECT * FROM trading_activations").fetchone())

    ledger = SQLiteLedger(path)
    assert ledger.latest_trading_activation() is None
    assert not auto_paper_active(
        {"TRADING_MODE": "AUTO_PAPER", "ORDER_WRITES_ENABLED": "true"},
        ledger.latest_trading_activation(), account_fingerprint=FINGERPRINT,
    )

    activation = build_auto_paper_activation(FINGERPRINT, NOW)
    ledger.record_trading_activation(activation)
    assert SQLiteLedger(path).latest_trading_activation() == activation

    with ledger._connect() as connection:
        rows = connection.execute("SELECT * FROM trading_activations ORDER BY activated_at_utc").fetchall()
        assert len(rows) == 2
        assert {key: rows[0][key] for key in historical} == historical
        assert rows[0]["min_effective_exposure_fraction"] is None
        assert rows[0]["max_effective_exposure_fraction"] is None
        assert all(rows[1][field] is None for field in ("max_single_exposure", "max_total_exposure", "position_fraction"))
    for statement in (
        "UPDATE trading_activations SET activated_by = 'mallory'",
        "DELETE FROM trading_activations",
    ):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            with ledger._connect() as connection:
                connection.execute(statement)


@pytest.mark.parametrize("version", ["risk-v1", "risk-v2"])
def test_latest_non_v3_row_blocks_older_v3_pin_without_deleting_history(tmp_path, version):
    path = tmp_path / "audit.db"
    ledger = SQLiteLedger(path)
    ledger.record_trading_activation(build_auto_paper_activation(FINGERPRINT, NOW))
    with ledger._connect() as connection:
        # Historical fixtures bypass the runtime contract, never reactivate v1.
        connection.execute(
            """
            INSERT INTO trading_activations (
                activation_id, activated_at_utc, activated_by, account_fingerprint,
                strategy_version, allowed_symbols_json, risk_policy_version,
                max_single_exposure, max_total_exposure, position_fraction,
                max_daily_drawdown, paper_only, order_writes_enabled, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("historical-pin", NOW.isoformat(), "owner", FINGERPRINT,
             "spy-directional", '["SPY", "SH"]', version, "0.10", "0.30", "0.05",
             "0.02", 1, 1, "1"),
        )
        before = [dict(row) for row in connection.execute("SELECT * FROM trading_activations ORDER BY rowid")]
    reopened = SQLiteLedger(path)
    assert reopened.latest_trading_activation() is None
    with reopened._connect() as connection:
        assert [dict(row) for row in connection.execute("SELECT * FROM trading_activations ORDER BY rowid")] == before


def test_activate_cli_refuses_without_the_confirmation_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "AUTO_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "true")
    monkeypatch.setenv("COMPETITION_ACCOUNT_FINGERPRINT", FINGERPRINT)
    ledger = tmp_path / "audit.db"

    result = main(["moomoo-activate-auto-paper", "--ledger", str(ledger)])

    assert result == 2
    assert "--confirm-auto-paper is required" in capsys.readouterr().out
    assert SQLiteLedger(ledger).latest_trading_activation() is None


def test_activate_cli_refuses_when_the_mode_is_not_auto_paper(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("TRADING_MODE", "SUPERVISED_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "true")
    monkeypatch.setenv("COMPETITION_ACCOUNT_FINGERPRINT", FINGERPRINT)
    ledger = tmp_path / "audit.db"

    result = main(
        [
            "moomoo-activate-auto-paper",
            "--confirm-auto-paper",
            "--ledger",
            str(ledger),
        ]
    )

    assert result == 2
    assert "TRADING_MODE must be AUTO_PAPER" in capsys.readouterr().out
    assert SQLiteLedger(ledger).latest_trading_activation() is None


def test_activate_cli_refuses_without_writes_enabled(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "AUTO_PAPER")
    monkeypatch.delenv("ORDER_WRITES_ENABLED", raising=False)
    monkeypatch.setenv("COMPETITION_ACCOUNT_FINGERPRINT", FINGERPRINT)
    ledger = tmp_path / "audit.db"

    result = main(
        [
            "moomoo-activate-auto-paper",
            "--confirm-auto-paper",
            "--ledger",
            str(ledger),
        ]
    )

    assert result == 2
    assert "ORDER_WRITES_ENABLED must be true" in capsys.readouterr().out
    assert SQLiteLedger(ledger).latest_trading_activation() is None


def test_activate_cli_records_the_pin_and_status_shows_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "AUTO_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "true")
    monkeypatch.setenv("COMPETITION_ACCOUNT_FINGERPRINT", FINGERPRINT)
    ledger_path = tmp_path / "audit.db"

    result = main(
        [
            "moomoo-activate-auto-paper",
            "--confirm-auto-paper",
            "--ledger",
            str(ledger_path),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert result == 0
    assert output["activation_recorded"] is True
    assert output["order_submitted"] is False
    assert output["allowed_symbols"] == ["SPY", "SH"]
    assert output["risk_policy_version"] == "risk-v3"
    assert output["min_effective_exposure_fraction"] == "0.10"
    assert output["max_effective_exposure_fraction"] == "0.40"
    assert output["account_fingerprint"] == FINGERPRINT
    ledger = SQLiteLedger(ledger_path)
    activation = ledger.latest_trading_activation()
    assert activation is not None
    assert activation.allowed_symbols == ("SPY", "SH")
    assert {
        event["event_type"] for event in ledger.list_events()
    } == {"AUTO_PAPER_ACTIVATED"}

    result = main(
        ["moomoo-auto-paper-status", "--ledger", str(ledger_path)]
    )
    status = json.loads(capsys.readouterr().out)
    assert result == 0
    assert status["trading_mode"] == "AUTO_PAPER"
    assert status["order_writes_enabled_env"] is True
    assert status["kill_switch_engaged"] is False
    assert status["activation"]["allowed_symbols"] == ["SPY", "SH"]
    assert status["activation"]["risk_policy_version"] == "risk-v3"
    assert status["activation"]["min_effective_exposure_fraction"] == "0.10"
    assert status["activation"]["max_effective_exposure_fraction"] == "0.40"
    assert status["activation"]["paper_only"] is True


def test_activate_cli_rejects_a_missing_fingerprint(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "AUTO_PAPER")
    monkeypatch.setenv("ORDER_WRITES_ENABLED", "true")
    monkeypatch.delenv("COMPETITION_ACCOUNT_FINGERPRINT", raising=False)
    ledger = tmp_path / "audit.db"

    result = main(
        [
            "moomoo-activate-auto-paper",
            "--confirm-auto-paper",
            "--env-file",
            str(tmp_path / "missing.env"),
            "--ledger",
            str(ledger),
        ]
    )

    assert result == 2
    assert "fingerprint must be exactly 64 characters" in capsys.readouterr().out
    assert SQLiteLedger(ledger).latest_trading_activation() is None
