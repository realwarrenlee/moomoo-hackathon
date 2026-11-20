from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

from app.models.contracts import Quote

UNIVERSE: tuple[str, ...] = ("SPY", "SH")
SESSION_CLOSE_UTC = time(21, 0)


def session_close_utc(session_date: date) -> datetime:
    # 21:00 UTC is conservative: it is after the close in both US summer and winter time.
    return datetime.combine(session_date, SESSION_CLOSE_UTC, tzinfo=UTC)


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    available_at_utc: datetime

    @property
    def evidence_id(self) -> str:
        return f"bar:{self.symbol}:{self.session_date:%Y%m%d}"


class MarketHistory:
    def __init__(self, bars_by_symbol: dict[str, tuple[DailyBar, ...]], source: dict[str, object]) -> None:
        if not bars_by_symbol:
            raise ValueError("market history is empty")
        self._bars = bars_by_symbol
        self.source = source

    @classmethod
    def from_file(cls, path: str | Path) -> MarketHistory:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema_version") != "1":
            raise ValueError("unsupported market-history schema")
        bars_by_symbol: dict[str, tuple[DailyBar, ...]] = {}
        for symbol, rows in payload["symbols"].items():
            bars = tuple(
                DailyBar(
                    symbol=symbol,
                    session_date=datetime.strptime(row["date"], "%Y%m%d").date(),
                    open=Decimal(row["open"]),
                    high=Decimal(row["high"]),
                    low=Decimal(row["low"]),
                    close=Decimal(row["close"]),
                    volume=int(row["volume"]),
                    available_at_utc=session_close_utc(
                        datetime.strptime(row["date"], "%Y%m%d").date()
                    ),
                )
                for row in rows
            )
            if not bars:
                raise ValueError(f"no bars for {symbol}")
            if any(left.session_date >= right.session_date for left, right in zip(bars, bars[1:])):
                raise ValueError(f"bars for {symbol} are not strictly chronological")
            bars_by_symbol[symbol] = bars
        return cls(bars_by_symbol, dict(payload.get("source", {})))

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(self._bars)

    def bars(self, symbol: str) -> tuple[DailyBar, ...]:
        return self._bars[symbol]

    def bars_as_of(self, symbol: str, decision_time_utc: datetime) -> tuple[DailyBar, ...]:
        return tuple(bar for bar in self._bars[symbol] if bar.available_at_utc <= decision_time_utc)

    def session_dates(self) -> tuple[date, ...]:
        return tuple(bar.session_date for bar in self._bars["SPY"])

    def bar_on(self, symbol: str, session_date: date) -> DailyBar | None:
        bars = self._bars.get(symbol)
        if bars is None:
            return None
        return next((bar for bar in bars if bar.session_date == session_date), None)

    def next_bar(self, symbol: str, session_date: date) -> DailyBar | None:
        for bar in self._bars[symbol]:
            if bar.session_date > session_date:
                return bar
        return None

    def quote(self, symbol: str, decision_time_utc: datetime) -> Quote | None:
        available = self.bars_as_of(symbol, decision_time_utc)
        if not available:
            return None
        bar = available[-1]
        return Quote(
            symbol=symbol,
            price=bar.close,
            as_of_utc=bar.available_at_utc,
            regular_session_open=True,
        )

    def last_completed_session(self) -> date:
        return self._bars["SPY"][-1].session_date
