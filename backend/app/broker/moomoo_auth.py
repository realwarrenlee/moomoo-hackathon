"""Moomoo OAuth 2.1 + PKCE for the local read-only REST client.

The token file lives outside the repository and is DPAPI-protected on Windows.
No token value is logged, printed, or returned in an exception message.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import secrets
import sys
import time
import webbrowser
from collections.abc import Callable, Mapping
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

OAUTH_BASE_URL = "https://webapi.moomoo.com"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:60355/callback"
ACCOUNT_SCOPE_PREFIX = "accid:"
_REFRESH_MARGIN = timedelta(seconds=60)
_DPAPI_MAGIC = b"MOOTRADE-OAUTH-DPAPI-1\n"
_PLAIN_MAGIC = b"MOOTRADE-OAUTH-PLAIN-1\n"


class MoomooAuthError(RuntimeError):
    pass


class OAuthScopeError(MoomooAuthError):
    pass


class TokenStoreError(MoomooAuthError):
    pass


@dataclass(frozen=True)
class OAuthRecord:
    client_id: str
    access_token: str | None = field(default=None, repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    expires_at: datetime | None = None
    scope: str = field(default="", repr=False)

    def has_required_scopes(self) -> bool:
        granted = set(self.scope.split())
        if "quote:read" not in granted:
            return False
        # Simulated-account consent can return an account binding instead of trade:read
        # even though the sim-trade read endpoints are authorized for that account.
        return "trade:read" in granted or any(
            item.startswith(ACCOUNT_SCOPE_PREFIX) for item in granted
        )

    def has_trade_write(self) -> bool:
        return "trade:write" in set(self.scope.split())

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OAuthRecord":
        client_id = value.get("client_id")
        if not isinstance(client_id, str) or not client_id:
            raise TokenStoreError("OAuth token store has no client id")
        access_token = value.get("access_token")
        refresh_token = value.get("refresh_token")
        scope = value.get("scope", "")
        if access_token is not None and not isinstance(access_token, str):
            raise TokenStoreError("OAuth token store has an invalid access token")
        if refresh_token is not None and not isinstance(refresh_token, str):
            raise TokenStoreError("OAuth token store has an invalid refresh token")
        if not isinstance(scope, str):
            raise TokenStoreError("OAuth token store has an invalid scope")
        expires_at = None
        raw_expiry = value.get("expires_at")
        if raw_expiry is not None:
            if not isinstance(raw_expiry, str):
                raise TokenStoreError("OAuth token store has an invalid expiry")
            try:
                expires_at = datetime.fromisoformat(raw_expiry)
            except ValueError:
                raise TokenStoreError("OAuth token store has an invalid expiry") from None
            if expires_at.tzinfo is None:
                raise TokenStoreError("OAuth token store expiry must be timezone-aware")
        return cls(
            client_id=client_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=scope,
        )


def scope_summary(scope: str) -> dict[str, bool]:
    granted = set(scope.split())
    return {
        "quote:read": "quote:read" in granted,
        "trade:read": "trade:read" in granted,
        "trade:write": "trade:write" in granted,
        "account_scope": any(item.startswith(ACCOUNT_SCOPE_PREFIX) for item in granted),
    }


def _default_store_path(
    env: Mapping[str, str], override_key: str, filename: str
) -> Path:
    override = env.get(override_key, "").strip()
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = env.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "MooTrade" / filename


def default_token_path(environ: Mapping[str, str] | None = None) -> Path:
    return _default_store_path(
        os.environ if environ is None else environ,
        "MOOTRADE_OAUTH_STORE",
        "moomoo-oauth.bin",
    )


def default_execution_token_path(environ: Mapping[str, str] | None = None) -> Path:
    return _default_store_path(
        os.environ if environ is None else environ,
        "MOOTRADE_EXECUTION_OAUTH_STORE",
        "moomoo-execution-oauth.bin",
    )


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    buffer = ctypes.create_string_buffer(data, len(data))
    input_blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    output_blob = _DataBlob()
    if protect:
        function = crypt32.CryptProtectData
        function.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
    else:
        function = crypt32.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
    function.restype = wintypes.BOOL
    ok = function(
        ctypes.byref(input_blob),
        "MooTrade OAuth" if protect else None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    if not ok:
        raise TokenStoreError("Windows DPAPI operation failed")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, wintypes.HLOCAL))


class FileTokenStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> OAuthRecord | None:
        if not self.path.exists():
            return None
        try:
            raw = self.path.read_bytes()
        except OSError:
            raise TokenStoreError("OAuth token store is unreadable") from None
        if raw.startswith(_DPAPI_MAGIC):
            if sys.platform != "win32":
                raise TokenStoreError("OAuth token store was written by Windows DPAPI")
            payload = _dpapi(raw[len(_DPAPI_MAGIC) :], protect=False)
        elif raw.startswith(_PLAIN_MAGIC):
            if sys.platform == "win32":
                raise TokenStoreError("plaintext OAuth token store is not allowed on Windows")
            payload = raw[len(_PLAIN_MAGIC) :]
        else:
            raise TokenStoreError("OAuth token store has an unknown format")
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TokenStoreError("OAuth token store is corrupt") from None
        if not isinstance(value, Mapping):
            raise TokenStoreError("OAuth token store is corrupt")
        return OAuthRecord.from_dict(value)

    def save(self, record: OAuthRecord) -> None:
        payload = json.dumps(record.to_dict(), sort_keys=True).encode("utf-8")
        if sys.platform == "win32":
            blob = _DPAPI_MAGIC + _dpapi(payload, protect=True)
        else:
            blob = _PLAIN_MAGIC + payload
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
            with temporary.open("wb") as handle:
                handle.write(blob)
                handle.flush()
                os.fsync(handle.fileno())
            if sys.platform != "win32":
                os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        except OSError:
            raise TokenStoreError("OAuth token store could not be written") from None


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _pkce() -> tuple[str, str]:
    verifier = _base64url(secrets.token_bytes(64))
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        query = parse_qs(parsed.query)
        type(self).result = {key: values[0] for key, values in query.items() if values}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body>MooTrade authorization received. You may close this tab.</body></html>"
        )

    def log_message(self, format: str, *args: Any) -> None:
        return


class MoomooOAuth:
    registration_scope = "quote:read trade:read"
    client_name = "MooTrade Read-Only"

    def __init__(
        self,
        store: FileTokenStore,
        *,
        http: httpx.Client | None = None,
        clock: Callable[[], datetime] | None = None,
        redirect_uri: str = DEFAULT_REDIRECT_URI,
        open_browser: Callable[[str], Any] | None = webbrowser.open,
    ) -> None:
        self._store = store
        self._http = http or httpx.Client(timeout=20, trust_env=False)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._redirect_uri = redirect_uri
        self._open_browser = open_browser
        parsed = urlparse(redirect_uri)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("redirect URI must be a local HTTP callback")

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None:
            raise MoomooAuthError("clock must return a timezone-aware datetime")
        return current

    def _json(
        self,
        response: httpx.Response,
        operation: str,
        *,
        statuses: frozenset[int] = frozenset({200}),
    ) -> Mapping[str, Any]:
        if response.status_code not in statuses:
            raise MoomooAuthError(f"{operation} failed (HTTP {response.status_code})")
        try:
            payload = response.json()
        except ValueError:
            raise MoomooAuthError(f"{operation} returned invalid JSON") from None
        if not isinstance(payload, Mapping):
            raise MoomooAuthError(f"{operation} returned a non-object response")
        return payload

    def register(self) -> OAuthRecord:
        response = self._http.post(
            f"{OAUTH_BASE_URL}/oauth2/register",
            json={
                "redirect_uris": [self._redirect_uri],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "client_name": self.client_name,
                "scope": self.registration_scope,
            },
        )
        payload = self._json(
            response, "OAuth client registration", statuses=frozenset({200, 201})
        )
        client_id = payload.get("client_id")
        if not isinstance(client_id, str) or not client_id:
            raise MoomooAuthError("OAuth client registration returned no client id")
        record = OAuthRecord(client_id=client_id)
        self._store.save(record)
        return record

    def _record_or_register(self) -> OAuthRecord:
        record = self._store.load()
        if record is not None and record.client_id:
            return record
        return self.register()

    def _authorization_url(self, client_id: str, challenge: str, state: str) -> str:
        query = urlencode(
            {
                "client_id": client_id,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "state": state,
            }
        )
        return f"{OAUTH_BASE_URL}/oauth2/authorize/confirm?{query}"

    def _authorization_code(
        self, client_id: str, challenge: str, state: str, timeout_seconds: int, on_url
    ) -> str:
        parsed = urlparse(self._redirect_uri)
        port = parsed.port or 80
        _CallbackHandler.result = None
        try:
            server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
        except OSError:
            raise MoomooAuthError("local OAuth callback port is unavailable") from None
        url = self._authorization_url(client_id, challenge, state)
        try:
            if on_url is not None:
                on_url(url)
            if self._open_browser is not None:
                try:
                    self._open_browser(url)
                except Exception:
                    pass
            deadline = time.monotonic() + timeout_seconds
            while _CallbackHandler.result is None and time.monotonic() < deadline:
                server.timeout = min(1.0, max(0.0, deadline - time.monotonic()))
                server.handle_request()
        finally:
            server.server_close()
        result = _CallbackHandler.result
        if result is None:
            raise MoomooAuthError("authorization callback timed out")
        if result.get("state") != state:
            raise MoomooAuthError("authorization callback state did not match")
        if result.get("error"):
            raise MoomooAuthError(f"authorization failed ({result['error']})")
        code = result.get("code")
        if not isinstance(code, str) or not code:
            raise MoomooAuthError("authorization callback contained no code")
        return code

    def login(
        self,
        *,
        timeout_seconds: int = 300,
        on_url: Callable[[str], None] | None = None,
    ) -> OAuthRecord:
        if timeout_seconds <= 0:
            raise ValueError("authorization timeout must be positive")
        record = self._record_or_register()
        verifier, challenge = _pkce()
        state = _base64url(secrets.token_bytes(32))
        code = self._authorization_code(
            record.client_id, challenge, state, timeout_seconds, on_url
        )
        response = self._http.post(
            f"{OAUTH_BASE_URL}/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": record.client_id,
                "redirect_uri": self._redirect_uri,
                "code_verifier": verifier,
            },
        )
        payload = self._json(response, "OAuth token exchange")
        new_record = self._record_from_token(payload, record.client_id, None)
        self._store.save(new_record)
        return new_record

    def _record_from_token(
        self,
        payload: Mapping[str, Any],
        client_id: str,
        previous_refresh_token: str | None,
        previous_scope: str = "",
    ) -> OAuthRecord:
        token_type = payload.get("token_type")
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise MoomooAuthError("OAuth token response is not a Bearer token")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise MoomooAuthError("OAuth token response has no access token")
        refresh_token = payload.get("refresh_token", previous_refresh_token)
        if not isinstance(refresh_token, str) or not refresh_token:
            raise MoomooAuthError("OAuth token response has no refresh token")
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in <= 0:
            raise MoomooAuthError("OAuth token response has an invalid lifetime")
        scope = payload.get("scope", previous_scope)
        if not isinstance(scope, str):
            raise MoomooAuthError("OAuth token response has an invalid scope")
        record = OAuthRecord(
            client_id=client_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=self._now() + timedelta(seconds=expires_in),
            scope=scope,
        )
        self._validate_scope(record)
        return record

    def _validate_scope(self, record: OAuthRecord) -> None:
        if record.has_trade_write():
            raise OAuthScopeError(
                "authorization granted trade:write; reauthorize with read-only permissions"
            )
        if not record.has_required_scopes():
            raise OAuthScopeError(
                "authorization did not grant quote:read plus account or trade read access "
                f"(granted flags: {json.dumps(scope_summary(record.scope))})"
            )

    def refresh(self) -> OAuthRecord:
        record = self._store.load()
        if record is None or not record.refresh_token:
            raise MoomooAuthError("Moomoo OAuth login is required")
        response = self._http.post(
            f"{OAUTH_BASE_URL}/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": record.refresh_token,
                "client_id": record.client_id,
            },
        )
        if response.status_code != 200:
            raise MoomooAuthError(
                f"Moomoo authorization refresh failed (HTTP {response.status_code}); log in again"
            )
        payload = self._json(response, "OAuth token refresh")
        updated = self._record_from_token(
            payload, record.client_id, record.refresh_token, record.scope
        )
        self._store.save(updated)
        return updated

    def access_token(self) -> str:
        record = self._store.load()
        if record is None or not record.access_token:
            raise MoomooAuthError("Moomoo OAuth login is required")
        if record.expires_at is None or record.expires_at <= self._now() + _REFRESH_MARGIN:
            record = self.refresh()
        if not record.access_token:
            raise MoomooAuthError("Moomoo OAuth login is required")
        return record.access_token

    def status(self) -> OAuthRecord | None:
        return self._store.load()


class MoomooExecutionOAuth(MoomooOAuth):
    """Separate OAuth client for the guarded simulated-order transport."""

    registration_scope = "quote:read trade:read trade:write"
    client_name = "MooTrade Paper Execution"

    def _validate_scope(self, record: OAuthRecord) -> None:
        if not record.has_required_scopes():
            raise OAuthScopeError(
                "execution authorization did not grant quote:read plus account or trade read "
                f"access (granted flags: {json.dumps(scope_summary(record.scope))})"
            )
        if not record.has_trade_write():
            raise OAuthScopeError(
                "execution authorization did not grant trade:write"
            )
