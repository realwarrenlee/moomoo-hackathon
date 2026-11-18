from datetime import UTC, date, datetime

import httpx
import pytest

from app.broker.moomoo_history import HistoryFeedError, MoomooHistoryFeed
from app.broker.moomoo_rest import MoomooRestClient, MoomooRestReadOnlyError


class FakeHistoryClient:
    def __init__(self, rows=None, days=None):
        self.rows = rows if rows is not None else []
        self.days = days if days is not None else []
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path.endswith("/history-kline"):
            return {"data": {"kline_list": self.rows}}
        rows = [
            item
            for item in self.days
            if params["start"] <= item["time"] <= params["end"]
        ]
        return {"data": {"trading_days": rows}}


def row(day=20261116, close=600.0, **overrides):
    payload = {
        "date": day,
        "open": 590.0,
        "high": 605.0,
        "low": 585.0,
        "close": close,
        "volume": 1000,
        "time_key": 1794862800000,
    }
    payload.update(overrides)
    return payload


def test_daily_bars_are_parsed_and_end_date_is_enforced():
    client = FakeHistoryClient(rows=[row(20261113, 590.0), row(20261116, 600.0)])
    feed = MoomooHistoryFeed(client)
    bars = feed.get_daily_bars("SPY", date(2026, 11, 16))
    assert [bar["date"] for bar in bars] == ["20261113", "20261116"]
    assert bars[-1]["close"] == "600.0"
    assert client.calls[0][0] == "/api/v1.0/quote/US.SPY/history-kline"
    assert client.calls[0][1]["end"] == "2026-11-16"
    assert client.calls[0][1]["ktype"] == 2


@pytest.mark.parametrize(
    "bad",
    [
        row(close=700.0),
        row(volume=-1),
        row(time_key=0),
        row(date=20261340),
    ],
)
def test_malformed_daily_bars_fail_closed(bad):
    with pytest.raises(HistoryFeedError):
        MoomooHistoryFeed(FakeHistoryClient(rows=[bad])).get_daily_bars("SPY", date(2026, 11, 16))


def test_duplicate_or_descending_days_fail_closed():
    with pytest.raises(HistoryFeedError, match="strictly chronological"):
        MoomooHistoryFeed(
            FakeHistoryClient(rows=[row(20261116), row(20261116)])
        ).get_daily_bars("SPY", date(2026, 11, 16))


def test_snapshot_requires_the_end_session_and_has_no_account_data():
    feed = MoomooHistoryFeed(FakeHistoryClient(rows=[row(20261116)]))
    payload = feed.snapshot(
        ["SPY"], date(2026, 11, 16), now=datetime(2026, 11, 17, 0, 0, tzinfo=UTC)
    )
    assert payload["source"]["provider"] == "Moomoo REST history-kline"
    assert payload["source"]["last_completed_session"] == "20261116"
    assert "account_fingerprint" not in str(payload)

    stale = MoomooHistoryFeed(FakeHistoryClient(rows=[row(20261113)]))
    with pytest.raises(HistoryFeedError, match="no completed daily bar"):
        stale.snapshot(["SPY"], date(2026, 11, 16), now=datetime.now(UTC))


def test_trading_days_are_parsed_and_scoped():
    feed = MoomooHistoryFeed(
        FakeHistoryClient(
            days=[
                {"time": "2026-11-16", "trade_date_type": "WHOLE"},
                {"time": "2026-11-17", "trade_date_type": "WHOLE"},
            ]
        )
    )
    assert feed.get_trading_days(date(2026, 11, 16), date(2026, 11, 17)) == (
        date(2026, 11, 16),
        date(2026, 11, 17),
    )
    assert feed.is_trading_day(date(2026, 11, 16)) is True
    assert feed.is_trading_day(date(2026, 11, 15)) is False


def test_rest_allowlist_permits_documented_quote_history_reads():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path in {
            "/api/v1.0/quote/US.SPY/history-kline",
            "/api/v1.0/quote/trading-days",
        }
        return httpx.Response(200, json={"ret_code": 0, "data": {}})

    client = MoomooRestClient(
        type("Auth", (), {"access_token": lambda self: "test-token"})(),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.get("/api/v1.0/quote/US.SPY/history-kline", {"end": "2026-11-16"})
    client.get("/api/v1.0/quote/trading-days", {"market": "US"})
    with pytest.raises(MoomooRestReadOnlyError):
        client.get("/api/v1.0/quote/US.SPY/quote")
