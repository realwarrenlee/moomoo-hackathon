"""Trading-mode resolution and the durable AUTO_PAPER activation pin.

READ_ONLY (the default) and SUPERVISED_PAPER are environment-driven.
AUTO_PAPER additionally requires a persisted ``TradingActivation`` whose
pinned account fingerprint, strategy, symbol allowlist, risk-policy version
and exposure limits must match at every run. Only ``risk-v3`` is executable:
its two-symbol (SPY/SH) tier-based model requires a 10% floor and 40% ceiling.
Retired-policy activation rows remain immutable but cannot authorise trading.

The activation table is append-only in the ledger; deactivation is env-driven
(TRADING_MODE change or the persistent kill switch), never a silent record
rewrite.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from app.models.contracts import TradingActivation, TradingMode
from app.research.strategy import (
    EXPOSURE_POLICY_V3,
    ExposurePolicy,
    STRATEGY_VERSION,
)
from app.risk.policy import (
    DEFAULT_MAX_DAILY_DRAWDOWN,
    DEFAULT_MAX_EFFECTIVE_EXPOSURE_FRACTION,
    DEFAULT_MIN_EFFECTIVE_EXPOSURE_FRACTION,
    POLICY_VERSION_V3,
)

AUTO_PAPER_SYMBOLS: tuple[str, ...] = ("SPY", "SH")

# risk-v3 supervised execution authority: SPY/SH only, no leveraged funds.
# UPRO/SPXU were removed from the universe entirely by risk-v3.
SUPERVISED_EXECUTION_SYMBOLS: tuple[str, ...] = ("SPY", "SH")

_TRUE_VALUES = {"true", "1", "yes"}


class TradingModeError(RuntimeError):
    pass


def resolve_trading_mode(environ: Mapping[str, str]) -> TradingMode:
    raw = environ.get("TRADING_MODE", "").strip().upper()
    if not raw:
        return TradingMode.READ_ONLY
    try:
        return TradingMode(raw)
    except ValueError:
        raise TradingModeError(
            "TRADING_MODE must be one of READ_ONLY, SUPERVISED_PAPER, AUTO_PAPER; "
            f"got {raw!r}"
        ) from None


def order_writes_enabled(environ: Mapping[str, str]) -> bool:
    return environ.get("ORDER_WRITES_ENABLED", "false").strip().lower() in _TRUE_VALUES


def build_auto_paper_activation(
    account_fingerprint: str,
    activated_at_utc: datetime,
    activated_by: str = "owner",
    expires_at_utc: datetime | None = None,
) -> TradingActivation:
    """Pin AUTO_PAPER to the risk-v3 tier-based exposure policy."""
    if len(account_fingerprint) != 64:
        raise TradingModeError(
            "competition account fingerprint must be exactly 64 characters"
        )
    try:
        int(account_fingerprint, 16)
    except ValueError:
        raise TradingModeError(
            "competition account fingerprint is not a SHA-256 hex digest"
        ) from None
    if activated_at_utc.tzinfo is None:
        raise TradingModeError("activation timestamp must include a timezone")
    if expires_at_utc is not None and expires_at_utc.tzinfo is None:
        raise TradingModeError("activation expiry must include a timezone")
    return TradingActivation(
        activated_at_utc=activated_at_utc,
        activated_by=activated_by,
        account_fingerprint=account_fingerprint,
        strategy_version=STRATEGY_VERSION,
        allowed_symbols=AUTO_PAPER_SYMBOLS,
        risk_policy_version=POLICY_VERSION_V3,
        min_effective_exposure_fraction=DEFAULT_MIN_EFFECTIVE_EXPOSURE_FRACTION,
        max_effective_exposure_fraction=DEFAULT_MAX_EFFECTIVE_EXPOSURE_FRACTION,
        max_daily_drawdown=DEFAULT_MAX_DAILY_DRAWDOWN,
        expires_at_utc=expires_at_utc,
    )


def auto_paper_active(
    environ: Mapping[str, str],
    activation: TradingActivation | None,
    *,
    account_fingerprint: str,
) -> bool:
    """True only when env mode, write flag and the durable pin all agree."""
    if resolve_trading_mode(environ) is not TradingMode.AUTO_PAPER:
        return False
    if not order_writes_enabled(environ):
        return False
    if activation is None:
        return False
    if (
        activation.expires_at_utc is not None
        and datetime.now(UTC) >= activation.expires_at_utc
    ):
        return False
    if activation.account_fingerprint != account_fingerprint:
        return False
    if activation.strategy_version != STRATEGY_VERSION:
        return False
    if activation.max_daily_drawdown != DEFAULT_MAX_DAILY_DRAWDOWN:
        return False
    return (
        activation.risk_policy_version == POLICY_VERSION_V3
        and tuple(activation.allowed_symbols) == AUTO_PAPER_SYMBOLS
        and activation.min_effective_exposure_fraction
        == DEFAULT_MIN_EFFECTIVE_EXPOSURE_FRACTION
        and activation.max_effective_exposure_fraction
        == DEFAULT_MAX_EFFECTIVE_EXPOSURE_FRACTION
    )


def exposure_policy_for_activation(
    activation: TradingActivation | None,
) -> ExposurePolicy:
    """Use v2 for research; reject any supplied non-v2 activation pin."""
    if activation is not None and activation.risk_policy_version != POLICY_VERSION_V3:
        raise TradingModeError(
            f"activation pin binds unsupported risk policy {activation.risk_policy_version}"
        )
    return EXPOSURE_POLICY_V3
