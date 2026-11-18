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
