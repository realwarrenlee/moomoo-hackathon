from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.cli import main
from app.ledger.store import SQLiteLedger
from app.models.contracts import TradingMode
from app.trading_mode import (
    AUTO_PAPER_SYMBOLS,
    TradingModeError,
    auto_paper_active,
    build_auto_paper_activation,
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
    assert activation.risk_policy_version == "risk-v2"
    assert activation.min_effective_exposure_fraction == Decimal("0.20")
    assert activation.max_effective_exposure_fraction == Decimal("1.50")
    assert activation.max_single_exposure is None
    assert activation.max_total_exposure is None
    assert activation.position_fraction is None
    assert activation.paper_only is True
    assert activation.order_writes_enabled is True


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

    import sqlite3

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        with reopened._connect() as connection:
            connection.execute(
                "UPDATE trading_activations SET activated_by = 'mallory'"
            )


def test_pre_risk_v2_database_is_migrated_to_nullable_v1_limits(tmp_path):
    path = tmp_path / "audit.db"
    import sqlite3

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

    ledger = SQLiteLedger(path)
    legacy = ledger.latest_trading_activation()
    assert legacy is not None
    assert legacy.risk_policy_version == "risk-v1"
    assert legacy.max_single_exposure == Decimal("0.10")
    assert legacy.allowed_symbols == ("SPY", "SH")

    ledger.record_trading_activation(build_auto_paper_activation(FINGERPRINT, NOW))

    latest = SQLiteLedger(path).latest_trading_activation()
    assert latest is not None
    assert latest.risk_policy_version == "risk-v2"
    assert latest.max_single_exposure is None
    assert latest.position_fraction is None
    assert latest.min_effective_exposure_fraction == Decimal("0.20")
    assert latest.allowed_symbols == AUTO_PAPER_SYMBOLS

    with sqlite3.connect(path) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM trading_activations").fetchone()
        assert rows[0] == 2
        columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(trading_activations)"
            )
        }
        assert "min_effective_exposure_fraction" in columns


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
    assert output["allowed_symbols"] == ["SPY", "UPRO", "SH", "SPXU"]
    assert output["risk_policy_version"] == "risk-v2"
    assert output["min_effective_exposure_fraction"] == "0.20"
    assert output["max_effective_exposure_fraction"] == "1.50"
    assert output["account_fingerprint"] == FINGERPRINT
    ledger = SQLiteLedger(ledger_path)
    activation = ledger.latest_trading_activation()
    assert activation is not None
    assert activation.allowed_symbols == ("SPY", "UPRO", "SH", "SPXU")
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
    assert status["activation"]["allowed_symbols"] == ["SPY", "UPRO", "SH", "SPXU"]
    assert status["activation"]["risk_policy_version"] == "risk-v2"
    assert status["activation"]["min_effective_exposure_fraction"] == "0.20"
    assert status["activation"]["max_effective_exposure_fraction"] == "1.50"
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
