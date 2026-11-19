from app.cli import main
from app.ledger.store import SQLiteLedger
from app.service import build_client_order_key


def test_approve_first_order_cli_records_durable_approval(tmp_path, proposal, capsys):
    path = tmp_path / "audit.db"

    exit_code = main(
        [
            "approve-first-order",
            "--proposal-id",
            proposal.proposal_id,
            "--strategy-version",
            proposal.strategy_version,
            "--ledger",
            str(path),
            "--approved-by",
            "owner",
        ]
    )

    assert exit_code == 0
    key = build_client_order_key(proposal.strategy_version, proposal.proposal_id)
    assert SQLiteLedger(path).is_first_order_approved(key, proposal.proposal_id) is True
    assert "No order was submitted" in capsys.readouterr().out


def _kill_switch_args(path, *extra):
    return ["moomoo-kill-switch", "--ledger", str(path), "--env-file", str(path.parent / ".env"), *extra]


def test_kill_switch_cli_reports_state_without_change(tmp_path, capsys):
    path = tmp_path / "audit.db"
    assert main(_kill_switch_args(path)) == 0
    out = capsys.readouterr().out
    assert '"kill_switch_engaged": false' in out
    assert '"state_changed": false' in out
    assert not SQLiteLedger(path).kill_switch_engaged()


def test_kill_switch_cli_requires_confirmation_for_engage(tmp_path, capsys):
    path = tmp_path / "audit.db"
    assert main(_kill_switch_args(path, "--engage")) == 2
    assert "Refusing" in capsys.readouterr().out
    assert not SQLiteLedger(path).kill_switch_engaged()


def test_kill_switch_cli_engages_and_releases_with_audit_events(tmp_path, capsys):
    path = tmp_path / "audit.db"
    assert main(_kill_switch_args(path, "--engage", "--confirm-engage")) == 0
    ledger = SQLiteLedger(path)
    assert ledger.kill_switch_engaged()
    types = [event["event_type"] for event in ledger.list_events()]
    assert types == ["KILL_SWITCH_ENGAGED"]

    assert main(_kill_switch_args(path, "--release")) == 2
    assert ledger.kill_switch_engaged()

    assert main(_kill_switch_args(path, "--release", "--confirm-release")) == 0
    assert not ledger.kill_switch_engaged()
    types = [event["event_type"] for event in ledger.list_events()]
    assert types == ["KILL_SWITCH_ENGAGED", "KILL_SWITCH_RELEASED"]


def test_kill_switch_cli_rejects_contradictory_flags(tmp_path, capsys):
    path = tmp_path / "audit.db"
    assert main(_kill_switch_args(path, "--engage", "--release", "--confirm-engage", "--confirm-release")) == 2
    assert "Refusing" in capsys.readouterr().out
