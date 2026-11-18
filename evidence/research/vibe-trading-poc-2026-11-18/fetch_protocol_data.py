"""Fetch only the frozen protocol's 2015-2024 development data.

Read-only Moomoo quote endpoints. Never requests a date on or after
2025-01-01. No account, order, RiskGate or trading state is touched.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.broker.moomoo_auth import FileTokenStore, MoomooOAuth, default_token_path
from app.broker.moomoo_history import HISTORY_KLINES_PATH
from app.broker.moomoo_rest import (
    MoomooRestClient,
    MoomooRestError,
    MoomooRestRateLimitError,
)
from app.cli import load_local_env

OUT = Path(__file__).resolve().parent
PROTOCOL = ROOT / "evidence" / "research" / "stock-selection-prereg-2026-11-18" / "protocol.json"
DATA_DIR = OUT / "protocol-data"
CACHE_DIR = DATA_DIR / "raw"
CALENDAR_START = date(2015, 1, 1)
CALENDAR_END = date(2024, 12, 31)
MIN_REQUEST_INTERVAL = 2.6
_LAST_REQUEST = [0.0]


def _parse_rows(rows: list[object], start: date, end: date) -> list[dict[str, object]]:
    bars = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("history row is not an object")
        raw_date = row.get("date")
        if not isinstance(raw_date, int):
            raise ValueError("history row date is not an integer")
        text = str(raw_date)
        day = date(int(text[:4]), int(text[4:6]), int(text[6:]))
        if not start <= day <= end:
            raise ValueError(f"row {day} outside {start}..{end}")
        prices = {}
        for field in ("open", "high", "low", "close"):
            value = row.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{day} {field} is not numeric")
            if float(value) <= 0:
                raise ValueError(f"{day} {field} is not positive")
            prices[field] = float(value)
        if prices["high"] < max(prices["open"], prices["close"], prices["low"]):
            raise ValueError(f"{day} high does not bracket prices")
        if prices["low"] > min(prices["open"], prices["close"], prices["high"]):
            raise ValueError(f"{day} low does not bracket prices")
        volume = row.get("volume")
        if not isinstance(volume, int) or isinstance(volume, bool) or volume < 0:
            raise ValueError(f"{day} volume is invalid")
        bars.append(
            {
                "date": day.isoformat(),
                "open": prices["open"],
                "high": prices["high"],
                "low": prices["low"],
                "close": prices["close"],
                "volume": volume,
            }
        )
    if any(bars[i]["date"] >= bars[i + 1]["date"] for i in range(len(bars) - 1)):
        raise ValueError("bars are not strictly chronological")
    return bars


def _get_with_retry(client, path: str, params: dict[str, object], attempts: int = 6):
    delay = 2.0
    for attempt in range(attempts):
        try:
            return client.get(path, params)
        except MoomooRestRateLimitError:
            if attempt == attempts - 1:
                raise
            print(f"  rate limited; retrying in {delay:.0f}s")
            time.sleep(delay)
            delay *= 1.5
        except MoomooRestError as exc:
            # The quote endpoint returns ret_code=-11 after ~30 calls/minute.
            # Back off a full minute rather than treating it as a data failure.
            if "-11" not in str(exc) or attempt == attempts - 1:
                raise
            print("  quote quota (ret_code=-11); pausing 65s")
            time.sleep(65.0)
    raise RuntimeError("unreachable")


def _throttled_get(client, path: str, params: dict[str, object]):
    wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _LAST_REQUEST[0])
    if wait > 0:
        time.sleep(wait)
    try:
        return _get_with_retry(client, path, params)
    finally:
        _LAST_REQUEST[0] = time.monotonic()


def main() -> int:
    load_local_env(ROOT / ".env")
    if os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower() not in {
        "false",
        "0",
        "no",
        "",
    }:
        raise SystemExit("ORDER_WRITES_ENABLED must remain false")
    store = FileTokenStore(default_token_path())
    record = store.load()
    if record is None:
        raise SystemExit("Moomoo read authorization is required")
    if record.has_trade_write():
        raise SystemExit("stored authorization contains trade:write; refusing")
    if not record.has_required_scopes():
        raise SystemExit("stored authorization lacks required read scopes")

    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    universe = list(protocol["universe"]) + ["SPY"]
    client = MoomooRestClient(MoomooOAuth(store, open_browser=None))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    calendar_cache = DATA_DIR / "trading-days-US-2015-2024.json"
    if calendar_cache.exists():
        calendar_payload = json.loads(calendar_cache.read_text(encoding="utf-8"))
    else:
        calendar_payload = _throttled_get(
            client,
            "/api/v1.0/quote/trading-days",
            {
                "market": "US",
                "start": CALENDAR_START.isoformat(),
                "end": CALENDAR_END.isoformat(),
            },
        )
        calendar_cache.write_text(json.dumps(calendar_payload, indent=2), encoding="utf-8")
    calendar_rows = calendar_payload.get("data", {}).get("trading_days")
    if not isinstance(calendar_rows, list):
        raise SystemExit("trading-days response has no list")
    calendar = [date.fromisoformat(row["time"]) for row in calendar_rows]
    if any(day.year >= 2025 for day in calendar):
        raise SystemExit("calendar request crossed into the untouched period")
    calendar_set = set(calendar)
    print(f"calendar: {len(calendar)} sessions {calendar[0]}..{calendar[-1]}")

    symbols: dict[str, list[dict[str, object]]] = {}
    requests = []
    for symbol in universe:
        bars: list[dict[str, object]] = []
        for year in range(2015, 2025):
            start = date(year, 1, 1)
            end = date(year, 12, 31)
            cache_file = CACHE_DIR / f"{symbol}-{year}.json"
            if cache_file.exists():
                parsed = json.loads(cache_file.read_text(encoding="utf-8"))
                cached = True
            else:
                payload = _throttled_get(
                    client,
                    HISTORY_KLINES_PATH.format(code=f"US.{symbol}"),
                    {
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "ktype": 2,
                        "autype": 1,
                        "num": 370,
                        "extended_time": 0,
                    },
                )
                rows = payload.get("data", {}).get("kline_list")
                if not isinstance(rows, list) or not rows:
                    raise SystemExit(f"no rows for {symbol} {year}")
                parsed = _parse_rows(rows, start, end)
                cache_file.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
                cached = False
            if not parsed:
                raise SystemExit(f"cached rows for {symbol} {year} are empty")
            if parsed and parsed[-1]["date"] >= "2025-01-01":
                raise SystemExit(f"{symbol} {year} crossed into the untouched period")
            bars.extend(parsed)
            requests.append(
                {
                    "symbol": symbol,
                    "year": year,
                    "rows": len(parsed),
                    "first": parsed[0]["date"],
                    "last": parsed[-1]["date"],
                    "cached": cached,
                }
            )
            print(
                f"{symbol} {year}: {len(parsed)} rows {parsed[0]['date']}..{parsed[-1]['date']}"
                f"{' (cached)' if cached else ''}"
            )
        if any(bars[i]["date"] >= bars[i + 1]["date"] for i in range(len(bars) - 1)):
            raise SystemExit(f"{symbol} duplicated or unordered bars across years")
        observed = [date.fromisoformat(row["date"]) for row in bars]
        if observed != [day for day in calendar if observed[0] <= day <= observed[-1]]:
            missing = sorted(
                calendar_set
                - set(observed)
                - {
                    day
                    for day in calendar
                    if not (observed[0] <= day <= observed[-1])
                }
            )
            raise SystemExit(f"{symbol} is missing {len(missing)} sessions: {missing[:10]}")
        symbols[symbol] = bars

    output = {
        "schema_version": "1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "order_writes_enabled": False,
        "period": {
            "start": CALENDAR_START.isoformat(),
            "end": CALENDAR_END.isoformat(),
            "untouched_after": "2025-01-01",
            "note": "2015 is loaded only as 200-session warmup for the 2016-2024 evaluation.",
        },
        "source": {
            "provider": "Moomoo REST history-kline",
            "endpoint": HISTORY_KLINES_PATH,
            "arguments": {
                "ktype": 2,
                "autype": 1,
                "extended_time": 0,
                "num": 370,
                "chunking": "one calendar year per request",
            },
            "calendar_endpoint": "/api/v1.0/quote/trading-days",
            "calendar_sessions": len(calendar),
            "requests": len(requests),
        },
        "calendar": [day.isoformat() for day in calendar],
        "symbols": symbols,
        "request_log": requests,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "daily-bars-2015-2024.json"
    out.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1_000_000:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
