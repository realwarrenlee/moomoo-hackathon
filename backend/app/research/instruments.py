"""Verified metadata for the four-symbol SPY directional universe."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Instrument:
    symbol: str
    direction: int
    leverage: Decimal
    avg_dollar_volume_20: Decimal
    note: str

    @property
    def effective_exposure(self) -> Decimal:
        return Decimal(self.direction) * self.leverage

    @property
    def leveraged(self) -> bool:
        return self.leverage > 1

    @property
    def economic_direction(self) -> str:
        return "BULLISH" if self.direction > 0 else "BEARISH"


# Average 20-session dollar volume from the read-only Moomoo history probe on
# 2026-11-18. All four products had 370 completed daily bars through 2026-11-17.
INSTRUMENTS: dict[str, Instrument] = {
    "SPY": Instrument(
        "SPY", 1, Decimal("1"), Decimal("37821652435.82"),
        "Unleveraged long S&P 500 exposure.",
    ),
    "UPRO": Instrument(
        "UPRO", 1, Decimal("3"), Decimal("393169316.77"),
        "Daily 3x long S&P 500 exposure; selectable when the risk-v2 target exceeds 100%.",
    ),
    "SH": Instrument(
        "SH", -1, Decimal("1"), Decimal("369048377.47"),
        "Unleveraged inverse S&P 500 exposure; bought with a BUY order.",
    ),
    "SPXU": Instrument(
        "SPXU", -1, Decimal("3"), Decimal("414841698.59"),
        "Daily 3x inverse S&P 500 exposure; bought with a BUY order and selectable when the risk-v2 target is below -100%.",
    ),
}

CANDIDATE_SYMBOLS: tuple[str, ...] = ("SPY", "UPRO", "SH", "SPXU")
LONG_SYMBOLS: tuple[str, ...] = ("SPY", "UPRO")
INVERSE_SYMBOLS: tuple[str, ...] = ("SH", "SPXU")


def select_instrument(direction: int, strong: bool, allow_leveraged: bool) -> str | None:
    """Return the target ETF; leverage requires both a strong signal and approval."""
    if direction > 0:
        return "UPRO" if strong and allow_leveraged else "SPY"
    if direction < 0:
        return "SPXU" if strong and allow_leveraged else "SH"
    return None


def select_instrument_for_exposure(direction: int, target_fraction: Decimal) -> str | None:
    """Choose the ETF that expresses a signed exposure fraction.

    |target| <= 100% uses the 1x product; larger targets use the 3x product so
    the cash outlay stays at |target| / leverage of equity.
    """
    if direction == 0 or target_fraction == 0:
        return None
    if abs(target_fraction) <= Decimal("1"):
        return "SPY" if direction > 0 else "SH"
    return "UPRO" if direction > 0 else "SPXU"
