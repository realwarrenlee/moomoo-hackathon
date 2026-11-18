from __future__ import annotations

import os

from app.broker.moomoo_auth import FileTokenStore, OAuthRecord
from app.cli import load_local_env, main


def test_local_env_loader_ignores_provider_credentials(tmp_path, monkeypatch):
    for key in [
        "QODER_ACCESS_TOKEN",
        "MOOMOO_MCP_URL",
        "COMPETITION_ACCOUNT_MASKED_ID",
        "COMPETITION_ACCOUNT_FINGERPRINT",
        "COMPETITION_ACCOUNT_MARKET_ID",
        "DATABASE_URL",
        "MOOTRADE_OAUTH_STORE",
    ]:
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "QODER_ACCESS_TOKEN=must-not-load",
                "MOOMOO_MCP_URL=https://example.invalid",
                "COMPETITION_ACCOUNT_MASKED_ID=****0101",
                "COMPETITION_ACCOUNT_FINGERPRINT=" + "a" * 64,
                "COMPETITION_ACCOUNT_MARKET_ID=100",
                "DATABASE_URL=sqlite:///./data/test.db",
                "MOOTRADE_OAUTH_STORE=" + str(tmp_path / "oauth.bin"),
            ]
        ),
        encoding="utf-8",
    )

    load_local_env(env_file)

    assert os.environ["COMPETITION_ACCOUNT_MASKED_ID"] == "****0101"
    assert os.environ["COMPETITION_ACCOUNT_MARKET_ID"] == "100"
    assert os.environ["DATABASE_URL"] == "sqlite:///./data/test.db"
    assert "QODER_ACCESS_TOKEN" not in os.environ
    assert "MOOMOO_MCP_URL" not in os.environ


def test_auth_status_reports_no_token_without_printing_one(tmp_path, capsys):
    result = main(["moomoo-auth-status", "--store", str(tmp_path / "oauth.bin")])

    output = capsys.readouterr().out
    assert result == 1
    assert "No local Moomoo OAuth authorization" in output
    assert "token-1" not in output


def test_execution_status_rejects_registration_only(tmp_path, capsys):
    store = FileTokenStore(tmp_path / "execution.bin")
    store.save(OAuthRecord(client_id="execution-client"))

    result = main(["moomoo-execution-status", "--store", str(store.path)])

    output = capsys.readouterr().out
    assert result == 1
    assert "no authorization token" in output
    assert "execution-client" not in output


def test_read_without_login_fails_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COMPETITION_ACCOUNT_MASKED_ID", "****0101")
    monkeypatch.setenv("COMPETITION_ACCOUNT_FINGERPRINT", "a" * 64)
    monkeypatch.setenv("COMPETITION_ACCOUNT_MARKET_ID", "100")

    result = main(
        [
            "moomoo-read",
            "--store",
            str(tmp_path / "oauth.bin"),
            "--env-file",
            str(tmp_path / "missing.env"),
            "--ledger",
            str(tmp_path / "ledger.db"),
        ]
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "login is required" in output
    assert "Bearer" not in output
