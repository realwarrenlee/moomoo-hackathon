"""Verified metadata for the two-symbol SPY directional universe.

risk-v3 trades SPY (bullish) and SH (bearish) only. UPRO/SPXU metadata is
removed: leveraged instruments are outside the policy, and any proposal that
references them is rejected by the default-deny symbol validation.
"""

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
# 2026-11-18. Both products had 370 completed daily bars through 2026-11-17.
# UPRO/SPXU were part of risk-v2 (HISTORICAL); risk-v3 removed them.
INSTRUMENTS: dict[str, Instrument] = {
    "SPY": Instrument(
        "SPY", 1, Decimal("1"), Decimal("37821652435.82"),
        "Unleveraged long S&P 500 exposure.",
    ),
    "SH": Instrument(
        "SH", -1, Decimal("1"), Decimal("369048377.47"),
        "Unleveraged inverse S&P 500 exposure; bought with a BUY order.",
    ),
}

CANDIDATE_SYMBOLS: tuple[str, ...] = ("SPY", "SH")
LONG_SYMBOLS: tuple[str, ...] = ("SPY",)
INVERSE_SYMBOLS: tuple[str, ...] = ("SH",)


def select_instrument_for_exposure(direction: int, target_fraction: Decimal) -> str | None:
    """Choose the ETF that expresses a signed exposure fraction.

    risk-v3 targets stay within |40%| of equity, so the 1x product always
    expresses the target directly.
    """
    if direction == 0 or target_fraction == 0:
        return None
    return "SPY" if direction > 0 else "SH"
