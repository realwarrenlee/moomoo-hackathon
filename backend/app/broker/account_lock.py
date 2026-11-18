"""Exact competition-account identity lock.

Live MCP adapters must map ``sim_trade_account_list`` rows into ``BrokerAccount``
and must never log or persist ``account_id``. The lock requires both the masked
identifier and a SHA-256 fingerprint, so a market ID alone can never select an
account.
"""

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Literal

AccountSource = Literal["simulated", "live"]


class AccountLockError(RuntimeError):
    pass


def fingerprint_account_id(account_id: str) -> str:
    normalized = account_id.strip()
    if not normalized:
        raise ValueError("account id is required")
    return sha256(f"mootrade:account:{normalized}".encode("utf-8")).hexdigest()


def mask_account_id(account_id: str) -> str:
    normalized = account_id.strip()
    if len(normalized) < 4:
        return "****"
    return f"****{normalized[-4:]}"


@dataclass(frozen=True)
class BrokerAccount:
    account_id: str = field(repr=False)
    masked_id: str
    fingerprint: str
    market_id: int
    source: AccountSource
    account_type: str

    @classmethod
    def from_provider(
        cls,
        *,
        account_id: str,
        market_id: int,
        source: AccountSource,
        account_type: str,
    ) -> "BrokerAccount":
        normalized = account_id.strip()
        if not normalized:
            raise ValueError("provider returned an empty account id")
        if source not in ("simulated", "live"):
            raise ValueError("unsupported account source")
        return cls(
            account_id=normalized,
            masked_id=mask_account_id(normalized),
            fingerprint=fingerprint_account_id(normalized),
            market_id=market_id,
            source=source,
            account_type=account_type,
        )


@dataclass(frozen=True)
class AccountLock:
    expected_masked_id: str
    expected_fingerprint: str
    expected_market_id: int = 100

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\*{4}\d{4}", self.expected_masked_id):
            raise AccountLockError("expected masked id must look like ****0000")
        if not re.fullmatch(r"[0-9a-f]{64}", self.expected_fingerprint):
            raise AccountLockError("expected fingerprint must be a lowercase SHA-256 hex digest")
        if self.expected_market_id <= 0:
            raise AccountLockError("expected market id must be positive")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AccountLock":
        env = os.environ if environ is None else environ
        masked_id = env.get("COMPETITION_ACCOUNT_MASKED_ID", "").strip()
        fingerprint = env.get("COMPETITION_ACCOUNT_FINGERPRINT", "").strip()
        market_raw = env.get("COMPETITION_ACCOUNT_MARKET_ID", "100").strip() or "100"
        if not masked_id or not fingerprint:
            raise AccountLockError(
                "COMPETITION_ACCOUNT_MASKED_ID and COMPETITION_ACCOUNT_FINGERPRINT are required"
            )
        try:
            market_id = int(market_raw)
        except ValueError as exc:
            raise AccountLockError("COMPETITION_ACCOUNT_MARKET_ID must be an integer") from exc
        return cls(
            expected_masked_id=masked_id,
            expected_fingerprint=fingerprint,
            expected_market_id=market_id,
        )

    def resolve(self, accounts: Iterable[BrokerAccount]) -> BrokerAccount:
        available = list(accounts)
        candidates = [
            account
            for account in available
            if account.source == "simulated"
            and account.masked_id == self.expected_masked_id
            and account.fingerprint == self.expected_fingerprint
        ]
        if not candidates:
            live_match = any(
                account.source == "live"
                and account.masked_id == self.expected_masked_id
                and account.fingerprint == self.expected_fingerprint
                for account in available
            )
            if live_match:
                raise AccountLockError("competition identity resolves to a live account; refusing")
            raise AccountLockError("verified competition simulated account not found")
        if len(candidates) != 1:
            raise AccountLockError("multiple simulated accounts match the competition identity")
        account = candidates[0]
        if account.market_id != self.expected_market_id:
            raise AccountLockError("competition account market does not match the expected market")
        return account
