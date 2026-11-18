"""Execution-time quote and market-session reads from documented Moomoo endpoints."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.broker.moomoo_rest import MoomooRestError
from app.models.contracts import Quote

STOCK_QUOTE_PATH = "/api/v1.0/quote/stock-quote"
MARKET_STATE_PATH = "/api/v1.0/quote/market-state"
US_REGULAR_SESSION_STATE = "AFTERNOON"
# Provider timestamps can lead the local clock by fractions of a second.
CLOCK_SKEW_TOLERANCE_SECONDS = 5

_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


class QuoteFeedError(MoomooRestError):
    pass


@dataclass(frozen=True)
class QuoteObservation:
    """Read-only market display data; never an executable Quote."""

    symbol: str
    price: Decimal
    as_of_utc: datetime
    age_seconds: float
    sec_status: str
    suspended: bool
    market_state: str
    regular_session_open: bool


class MoomooQuoteFeed:
    def __init__(
        self,
        client: Any,
        *,
        max_quote_age_seconds: int = 300,
    ) -> None:
        if max_quote_age_seconds <= 0:
            raise ValueError("max quote age must be positive")
        self._client = client
        self._max_quote_age = max_quote_age_seconds

    def get_quote(self, symbol: str, now: datetime) -> Quote:
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("quote symbol is not an approved US ticker")
        if now.tzinfo is None:
            raise ValueError("quote clock must be timezone-aware")
        code = f"US.{symbol}"
        quote_payload = self._client.post_read(
            STOCK_QUOTE_PATH, {"code_list": [code]}
        )
        quote = _parse_quote(_data(quote_payload), code, now, self._max_quote_age)

        state_payload = self._client.post_read(
            MARKET_STATE_PATH,
            {
                "code_list": [code],
                "is_contain_ba": False,
                "is_contain_overnight": False,
            },
        )
        regular_open = _parse_regular_session(_data(state_payload), code)
        return Quote(
            symbol=symbol,
            price=quote.price,
            as_of_utc=quote.as_of,
            regular_session_open=regular_open,
        )

    def observe_quote(self, symbol: str, now: datetime) -> QuoteObservation:
        """Return display data even when stale; never usable as an execution Quote."""
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("quote symbol is not an approved US ticker")
        if now.tzinfo is None:
            raise ValueError("quote clock must be timezone-aware")
        code = f"US.{symbol}"
        quote_payload = self._client.post_read(
            STOCK_QUOTE_PATH, {"code_list": [code]}
        )
        price, as_of, sec_status, suspended = _parse_quote_observation(
            _data(quote_payload), code, now
        )
        state_payload = self._client.post_read(
            MARKET_STATE_PATH,
            {
                "code_list": [code],
                "is_contain_ba": False,
                "is_contain_overnight": False,
            },
        )
        market_state = _parse_market_state(_data(state_payload), code)
        return QuoteObservation(
            symbol=symbol,
            price=price,
            as_of_utc=as_of,
            age_seconds=max(0.0, (now - as_of).total_seconds()),
            sec_status=sec_status,
            suspended=suspended,
            market_state=market_state,
            regular_session_open=market_state == US_REGULAR_SESSION_STATE,
        )


class _ParsedQuote:
    def __init__(self, price: Decimal, as_of: datetime) -> None:
        self.price = price
        self.as_of = as_of


def _data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise QuoteFeedError("Moomoo quote response has no data object")
    return data


def _parse_quote(
    data: Mapping[str, Any], code: str, now: datetime, max_age_seconds: int
) -> _ParsedQuote:
    rows = data.get("quote_list")
    if not isinstance(rows, list) or len(rows) != 1:
        raise QuoteFeedError("Moomoo quote response must contain exactly one quote")
    row = rows[0]
    if not isinstance(row, Mapping):
        raise QuoteFeedError("Moomoo quote response row is not an object")
    if row.get("code") != code:
        raise QuoteFeedError("Moomoo quote response code does not match the requested symbol")

    data_time = row.get("data_time")
    if isinstance(data_time, bool) or not isinstance(data_time, int) or data_time <= 0:
        raise QuoteFeedError("Moomoo quote data_time is not a positive Unix millisecond value")
    as_of = datetime.fromtimestamp(data_time / 1_000, tz=UTC)
    if (as_of - now).total_seconds() > CLOCK_SKEW_TOLERANCE_SECONDS:
        raise QuoteFeedError("Moomoo quote is timestamped in the future")
    age = (now - as_of).total_seconds()
    if age > max_age_seconds:
        raise QuoteFeedError(
            f"Moomoo quote is stale ({int(age)}s old, limit {max_age_seconds}s)"
        )

    raw_price = row.get("last_price")
    if isinstance(raw_price, bool) or not isinstance(raw_price, (int, float)):
        raise QuoteFeedError("Moomoo quote last_price is not numeric")
    try:
        price = Decimal(str(raw_price))
    except InvalidOperation:
        raise QuoteFeedError("Moomoo quote last_price is not numeric") from None
    if not price.is_finite() or price <= 0:
        raise QuoteFeedError("Moomoo quote last_price is not positive")

    if row.get("sec_status") != "NORMAL":
        raise QuoteFeedError("Moomoo quote security status is not NORMAL")
    if row.get("suspension") is not False:
        raise QuoteFeedError("Moomoo quote security is suspended or has invalid suspension data")
    return _ParsedQuote(price=price, as_of=as_of)


def _parse_quote_observation(
    data: Mapping[str, Any], code: str, now: datetime
) -> tuple[Decimal, datetime, str, bool]:
    rows = data.get("quote_list")
    if not isinstance(rows, list) or len(rows) != 1:
        raise QuoteFeedError("Moomoo quote response must contain exactly one quote")
    row = rows[0]
    if not isinstance(row, Mapping):
        raise QuoteFeedError("Moomoo quote response row is not an object")
    if row.get("code") != code:
        raise QuoteFeedError("Moomoo quote response code does not match the requested symbol")

    data_time = row.get("data_time")
    if isinstance(data_time, bool) or not isinstance(data_time, int) or data_time <= 0:
        raise QuoteFeedError("Moomoo quote data_time is not a positive Unix millisecond value")
    as_of = datetime.fromtimestamp(data_time / 1_000, tz=UTC)
    if (as_of - now).total_seconds() > CLOCK_SKEW_TOLERANCE_SECONDS:
        raise QuoteFeedError("Moomoo quote is timestamped in the future")

    raw_price = row.get("last_price")
    if isinstance(raw_price, bool) or not isinstance(raw_price, (int, float)):
        raise QuoteFeedError("Moomoo quote last_price is not numeric")
    try:
        price = Decimal(str(raw_price))
    except InvalidOperation:
        raise QuoteFeedError("Moomoo quote last_price is not numeric") from None
    if not price.is_finite() or price <= 0:
        raise QuoteFeedError("Moomoo quote last_price is not positive")

    sec_status = row.get("sec_status")
    if not isinstance(sec_status, str) or not sec_status:
        raise QuoteFeedError("Moomoo quote security status is missing")
    suspended = row.get("suspension")
    if not isinstance(suspended, bool):
        raise QuoteFeedError("Moomoo quote suspension flag is invalid")
    return price, as_of, sec_status, suspended


def _parse_market_state(data: Mapping[str, Any], code: str) -> str:
    rows = data.get("market_state_list")
    if not isinstance(rows, list) or len(rows) != 1:
        raise QuoteFeedError("Moomoo market-state response must contain exactly one row")
    row = rows[0]
    if not isinstance(row, Mapping):
        raise QuoteFeedError("Moomoo market-state row is not an object")
    if row.get("code") != code:
        raise QuoteFeedError("Moomoo market-state code does not match the requested symbol")
    state = row.get("market_state")
    if not isinstance(state, str) or not state:
        raise QuoteFeedError("Moomoo market-state value is missing")
    return state


def _parse_regular_session(data: Mapping[str, Any], code: str) -> bool:
    # Only AFTERNOON is documented as regular US trading hours; fail closed otherwise.
    return _parse_market_state(data, code) == US_REGULAR_SESSION_STATE
