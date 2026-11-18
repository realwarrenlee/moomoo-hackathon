"""Trading-mode resolution and the durable AUTO_PAPER activation pin.

READ_ONLY (the default) and SUPERVISED_PAPER are environment-driven.
AUTO_PAPER additionally requires a persisted ``TradingActivation`` whose
pinned account fingerprint, strategy, symbol allowlist, risk-policy version
and exposure limits must match at every run. The activation record is
append-only in the ledger; deactivation is env-driven (TRADING_MODE change or
the persistent kill switch), never a silent record rewrite.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from app.models.contracts import TradingActivation, TradingMode
from app.research.strategy import POSITION_FRACTION, STRATEGY_VERSION
from app.risk.policy import (
    DEFAULT_MAX_DAILY_DRAWDOWN,
    DEFAULT_MAX_SINGLE_EXPOSURE,
    DEFAULT_MAX_TOTAL_EXPOSURE,
    POLICY_VERSION,
)

AUTO_PAPER_SYMBOLS: tuple[str, ...] = ("SPY", "SH")

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
) -> TradingActivation:
    """Pin AUTO_PAPER to the live competition-account, strategy and risk constants."""
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
    return TradingActivation(
        activated_at_utc=activated_at_utc,
        activated_by=activated_by,
        account_fingerprint=account_fingerprint,
        strategy_version=STRATEGY_VERSION,
        allowed_symbols=AUTO_PAPER_SYMBOLS,
        risk_policy_version=POLICY_VERSION,
        max_single_exposure=DEFAULT_MAX_SINGLE_EXPOSURE,
        max_total_exposure=DEFAULT_MAX_TOTAL_EXPOSURE,
        max_daily_drawdown=DEFAULT_MAX_DAILY_DRAWDOWN,
        position_fraction=POSITION_FRACTION,
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
    if activation.account_fingerprint != account_fingerprint:
        return False
    if activation.strategy_version != STRATEGY_VERSION:
        return False
    if activation.risk_policy_version != POLICY_VERSION:
        return False
    return True
