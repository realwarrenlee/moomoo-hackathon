from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.broker.moomoo_auth import (
    FileTokenStore,
    MoomooAuthError,
    MoomooExecutionOAuth,
    MoomooOAuth,
    OAuthRecord,
    OAuthScopeError,
    TokenStoreError,
    default_execution_token_path,
    default_token_path,
    scope_summary,
)

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)
SCOPE = "quote:read trade:read accid:123456"


def make_record(**overrides) -> OAuthRecord:
    values = {
        "client_id": "client-1",
        "access_token": "secret-access",
        "refresh_token": "secret-refresh",
        "expires_at": NOW + timedelta(hours=2),
        "scope": SCOPE,
    }
    values.update(overrides)
    return OAuthRecord(**values)


def test_oauth_record_repr_hides_tokens_and_account_scope():
    text = repr(make_record())

    assert "secret-access" not in text
    assert "secret-refresh" not in text
    assert "123456" not in text


def test_scope_summary_hides_account_identifier():
    summary = scope_summary(SCOPE)

    assert summary == {
        "quote:read": True,
        "trade:read": True,
        "trade:write": False,
        "account_scope": True,
    }
    assert "123456" not in str(summary)
    assert scope_summary("quote:read") == {
        "quote:read": True,
        "trade:read": False,
        "trade:write": False,
        "account_scope": False,
    }


def test_token_store_roundtrip_is_encrypted_on_windows(tmp_path):
    store = FileTokenStore(tmp_path / "oauth.bin")
    record = make_record()

    store.save(record)
    loaded = store.load()

    assert loaded == record
    raw = (tmp_path / "oauth.bin").read_bytes()
    if sys.platform == "win32":
        assert b"secret-access" not in raw
        assert b"secret-refresh" not in raw
        assert b"123456" not in raw
    else:
        assert (tmp_path / "oauth.bin").stat().st_mode & 0o777 == 0o600


def test_token_store_rejects_unknown_or_corrupt_data(tmp_path):
    path = tmp_path / "oauth.bin"
    path.write_bytes(b"not-a-token-store")
    with pytest.raises(TokenStoreError, match="unknown format"):
        FileTokenStore(path).load()


def test_default_token_path_honours_explicit_override(tmp_path):
    path = default_token_path({"MOOTRADE_OAUTH_STORE": str(tmp_path / "oauth.bin")})

    assert path == tmp_path / "oauth.bin"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows local app data path")
def test_default_token_path_uses_local_app_data_on_windows():
    path = default_token_path({"LOCALAPPDATA": r"C:\Users\test\AppData\Local"})

    assert path == Path(r"C:\Users\test\AppData\Local") / "MooTrade" / "moomoo-oauth.bin"


def test_execution_token_path_is_separate_and_overridable(tmp_path):
    assert default_execution_token_path(
        {"MOOTRADE_EXECUTION_OAUTH_STORE": str(tmp_path / "execution.bin")}
    ) == tmp_path / "execution.bin"
    assert default_token_path({}).name == "moomoo-oauth.bin"
    assert default_execution_token_path({}).name == "moomoo-execution-oauth.bin"


def test_registration_accepts_201_and_requests_read_only_scopes(tmp_path):
    store = FileTokenStore(tmp_path / "oauth.bin")
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read())
        return httpx.Response(201, json={"client_id": "client-9"})

    oauth = MoomooOAuth(
        store,
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        clock=lambda: NOW,
    )

    record = oauth.register()

    assert record.client_id == "client-9"
    assert store.load().client_id == "client-9"
    body = json.loads(bodies[0])
    assert body["scope"] == "quote:read trade:read"
    assert "trade:write" not in body["scope"]


def test_execution_registration_requests_write_scope(tmp_path):
    store = FileTokenStore(tmp_path / "execution.bin")
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read())
        return httpx.Response(201, json={"client_id": "execution-client"})

    oauth = MoomooExecutionOAuth(
        store,
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        clock=lambda: NOW,
    )

    record = oauth.register()

    assert record.client_id == "execution-client"
    body = json.loads(bodies[0])
    assert body["client_name"] == "MooTrade Paper Execution"
    assert body["scope"] == "quote:read trade:read trade:write"


def test_execution_token_requires_read_and_write_scopes(tmp_path):
    oauth = MoomooExecutionOAuth(FileTokenStore(tmp_path / "execution.bin"), clock=lambda: NOW)
    valid = {
        "access_token": "execution-access",
        "refresh_token": "execution-refresh",
        "token_type": "Bearer",
        "expires_in": 7200,
        "scope": "quote:read trade:read accid:123456 trade:write",
    }

    record = oauth._record_from_token(valid, "execution-client", None)

    assert record.has_trade_write() is True
    assert record.has_required_scopes() is True

    missing_write = {**valid, "scope": "quote:read trade:read accid:123456"}
    with pytest.raises(OAuthScopeError, match="trade:write"):
        oauth._record_from_token(missing_write, "execution-client", None)

    missing_read = {**valid, "scope": "trade:write"}
    with pytest.raises(OAuthScopeError, match="quote:read plus account or trade read"):
        oauth._record_from_token(missing_read, "execution-client", None)


def test_access_token_requires_login(tmp_path):
    oauth = MoomooOAuth(FileTokenStore(tmp_path / "oauth.bin"))

    with pytest.raises(MoomooAuthError, match="login is required"):
        oauth.access_token()


def test_refresh_updates_tokens_without_rotating_the_refresh_token(tmp_path):
    store = FileTokenStore(tmp_path / "oauth.bin")
    store.save(replace(make_record(), access_token="expired"))
    form_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        form_calls.append(parse_qs(request.content.decode("ascii")))
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "token_type": "Bearer",
                "expires_in": 7200,
                "scope": SCOPE,
            },
        )

    oauth = MoomooOAuth(
        store,
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        clock=lambda: NOW,
    )

    updated = oauth.refresh()

    assert updated.access_token == "new-access"
    assert updated.refresh_token == "secret-refresh"
    assert updated.scope == SCOPE
    assert store.load().access_token == "new-access"
    assert form_calls == [
        {
            "grant_type": ["refresh_token"],
            "refresh_token": ["secret-refresh"],
            "client_id": ["client-1"],
        }
    ]


def test_refresh_rejects_missing_required_scope(tmp_path):
    store = FileTokenStore(tmp_path / "oauth.bin")
    store.save(make_record())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "token_type": "Bearer",
                "expires_in": 7200,
                "scope": "quote:read",
            },
        )

    oauth = MoomooOAuth(
        store,
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        clock=lambda: NOW,
    )

    with pytest.raises(OAuthScopeError, match="quote:read plus account or trade read"):
        oauth.refresh()
    assert store.load().access_token == "secret-access"


def test_account_scoped_sim_trade_read_token_is_accepted():
    record = make_record(scope="quote:read accid:123456")

    assert record.has_required_scopes() is True
    assert record.has_trade_write() is False


def test_refresh_rejects_trade_write_scope(tmp_path):
    store = FileTokenStore(tmp_path / "oauth.bin")
    store.save(make_record())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "token_type": "Bearer",
                "expires_in": 7200,
                "scope": "quote:read trade:read accid:123456 trade:write",
            },
        )

    oauth = MoomooOAuth(
        store,
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        clock=lambda: NOW,
    )

    with pytest.raises(OAuthScopeError, match="trade:write"):
        oauth.refresh()
    assert store.load().access_token == "secret-access"


def test_access_token_refreshes_before_the_expiry_margin(tmp_path):
    store = FileTokenStore(tmp_path / "oauth.bin")
    store.save(make_record(expires_at=NOW + timedelta(seconds=30)))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "token_type": "Bearer",
                "expires_in": 7200,
                "scope": SCOPE,
            },
        )

    oauth = MoomooOAuth(
        store,
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        clock=lambda: NOW,
    )

    assert oauth.access_token() == "new-access"
    assert calls == 1


def test_valid_access_token_is_reused(tmp_path):
    store = FileTokenStore(tmp_path / "oauth.bin")
    store.save(make_record())

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("valid token must not refresh")

    oauth = MoomooOAuth(
        store,
        http=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        clock=lambda: NOW,
    )

    assert oauth.access_token() == "secret-access"


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"access_token": "a", "expires_in": 100, "scope": SCOPE}, "Bearer"),
        (
            {
                "access_token": "a",
                "token_type": "Bearer",
                "expires_in": True,
                "scope": SCOPE,
            },
            "lifetime",
        ),
        (
            {
                "access_token": "a",
                "token_type": "Bearer",
                "expires_in": 100,
                "scope": "",
            },
            "quote:read plus account or trade read",
        ),
    ],
)
def test_token_payload_validation(tmp_path, payload, match):
    oauth = MoomooOAuth(FileTokenStore(tmp_path / "oauth.bin"), clock=lambda: NOW)

    with pytest.raises(MoomooAuthError, match=match):
        oauth._record_from_token(payload, "client-1", "refresh-1", "")

    assert not (tmp_path / "oauth.bin").exists()


def test_status_returns_the_stored_record(tmp_path):
    store = FileTokenStore(tmp_path / "oauth.bin")
    store.save(make_record())

    assert MoomooOAuth(store).status() == make_record()
