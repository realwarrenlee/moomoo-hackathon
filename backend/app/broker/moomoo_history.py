"""Read-only Moomoo daily-bar and trading-calendar retrieval."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.broker.moomoo_rest import MoomooRestError

HISTORY_KLINES_PATH = "/api/v1.0/quote/{code}/history-kline"
TRADING_DAYS_PATH = "/api/v1.0/quote/trading-days"
MAX_DAILY_BARS = 370


class HistoryFeedError(MoomooRestError):
    pass


class MoomooHistoryFeed:
    def __init__(self, client: Any, *, max_bars: int = MAX_DAILY_BARS) -> None:
        if not 21 <= max_bars <= MAX_DAILY_BARS:
            raise ValueError("max_bars must be between 21 and 370")
        self._client = client
        self._max_bars = max_bars

    def get_trading_days(self, start: date, end: date) -> tuple[date, ...]:
        if start > end:
            raise ValueError("trading-day start must not be after end")
        payload = self._client.get(
            TRADING_DAYS_PATH,
            {"market": "US", "start": start.isoformat(), "end": end.isoformat()},
        )
        data = _data(payload)
        rows = data.get("trading_days")
        if not isinstance(rows, list):
            raise HistoryFeedError("Moomoo trading-days response has no trading_days list")
        days: list[date] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise HistoryFeedError("Moomoo trading-day row is not an object")
            raw = row.get("time")
            if not isinstance(raw, str):
                raise HistoryFeedError("Moomoo trading-day value is missing")
            try:
                parsed = date.fromisoformat(raw)
            except ValueError:
                raise HistoryFeedError("Moomoo trading-day value is invalid") from None
            if not start <= parsed <= end:
                raise HistoryFeedError("Moomoo trading day is outside the requested range")
            if days and parsed <= days[-1]:
                raise HistoryFeedError("Moomoo trading days are not strictly chronological")
            days.append(parsed)
        return tuple(days)

    def is_trading_day(self, day: date) -> bool:
        return day in self.get_trading_days(day, day)

    def get_daily_bars(self, symbol: str, end: date) -> list[dict[str, object]]:
        if not symbol.isalpha() or not symbol.isupper() or len(symbol) > 10:
            raise ValueError("history symbol is not an approved US ticker")
        payload = self._client.get(
            HISTORY_KLINES_PATH.format(code=f"US.{symbol}"),
            {
                "end": end.isoformat(),
                "ktype": 2,
                "autype": 1,
                "num": self._max_bars,
                "extended_time": 0,
            },
        )
        data = _data(payload)
        rows = data.get("kline_list")
        if not isinstance(rows, list) or not rows:
            raise HistoryFeedError("Moomoo history-kline response has no daily bars")
        if len(rows) > self._max_bars:
            raise HistoryFeedError("Moomoo history-kline response exceeds the requested bar count")
        bars: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise HistoryFeedError("Moomoo history-kline row is not an object")
            bar = _parse_daily_bar(symbol, row, end)
            if bars and bar["date"] <= bars[-1]["date"]:
                raise HistoryFeedError("Moomoo daily bars are not strictly chronological")
            bars.append(bar)
        return bars

    def snapshot(
        self,
        symbols: Iterable[str],
        end: date,
        *,
        now: datetime,
        require_end_session: bool = True,
    ) -> dict[str, object]:
        if now.tzinfo is None:
            raise ValueError("history clock must be timezone-aware")
        symbol_rows: dict[str, list[dict[str, object]]] = {}
        for symbol in symbols:
            bars = self.get_daily_bars(symbol, end)
            if require_end_session and bars[-1]["date"] != end.strftime("%Y%m%d"):
                raise HistoryFeedError(
                    f"{symbol} has no completed daily bar for {end.isoformat()}"
                )
            if any(str(bar["date"]) > end.strftime("%Y%m%d") for bar in bars):
                raise HistoryFeedError(f"{symbol} contains a bar after the requested end date")
            symbol_rows[symbol] = bars
        return {
            "schema_version": "1",
            "source": {
                "provider": "Moomoo REST history-kline",
                "endpoint": HISTORY_KLINES_PATH,
                "arguments": {
                    "ktype": 2,
                    "autype": 1,
                    "extended_time": 0,
                    "num": self._max_bars,
                },
                "fetched_at_utc": now.astimezone(UTC).isoformat(),
                "last_completed_session": end.strftime("%Y%m%d"),
                "note": (
                    "Read-only completed daily bars fetched from the documented Moomoo REST "
                    "history-kline endpoint. No account identifiers or credentials are included."
                ),
            },
            "symbols": symbol_rows,
        }


def _data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise HistoryFeedError("Moomoo history response has no data object")
    return data


def _parse_daily_bar(
    symbol: str, row: Mapping[str, Any], end: date
) -> dict[str, object]:
    raw_date = row.get("date")
    if isinstance(raw_date, bool) or not isinstance(raw_date, int):
        raise HistoryFeedError("Moomoo daily bar date is not an integer")
    raw_text = str(raw_date)
    if len(raw_text) != 8:
        raise HistoryFeedError("Moomoo daily bar date is not YYYYMMDD")
    try:
        session_date = date(int(raw_text[:4]), int(raw_text[4:6]), int(raw_text[6:]))
    except ValueError:
        raise HistoryFeedError("Moomoo daily bar date is invalid") from None
    if session_date > end:
        raise HistoryFeedError("Moomoo daily bar is after the requested end date")

    prices = {}
    for field in ("open", "high", "low", "close"):
        raw = row.get(field)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise HistoryFeedError(f"Moomoo daily bar {field} is not numeric")
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            raise HistoryFeedError(f"Moomoo daily bar {field} is not numeric") from None
        if not value.is_finite() or value <= 0:
            raise HistoryFeedError(f"Moomoo daily bar {field} is not positive")
        prices[field] = value
    if prices["high"] < max(prices["open"], prices["close"]) or prices["low"] > min(
        prices["open"], prices["close"]
    ):
        raise HistoryFeedError("Moomoo daily bar OHLC values are inconsistent")

    volume = row.get("volume")
    if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
        raise HistoryFeedError("Moomoo daily bar volume is not a non-negative integer")
    time_key = row.get("time_key")
    if isinstance(time_key, bool) or not isinstance(time_key, int) or time_key <= 0:
        raise HistoryFeedError("Moomoo daily bar time_key is not a positive millisecond value")
    return {
        "date": raw_text,
        "open": str(prices["open"]),
        "high": str(prices["high"]),
        "low": str(prices["low"]),
        "close": str(prices["close"]),
        "volume": volume,
        "time_key_ms": time_key,
    }
