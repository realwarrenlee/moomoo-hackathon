"""Read-only Moomoo history probe for the Vibe-Trading POC.

This script only calls the documented quote/trading-days and quote/history-kline
GET endpoints. It does not import or contact any order, account or trade path.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.broker.moomoo_auth import FileTokenStore, MoomooOAuth, default_token_path
from app.broker.moomoo_history import HISTORY_KLINES_PATH
from app.broker.moomoo_rest import MoomooRestClient
from app.cli import load_local_env

OUT = Path(__file__).resolve().parent


def _records(rows: list[object], start: date, end: date) -> list[dict[str, object]]:
    records = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("history row is not an object")
        raw = row.get("date")
        if not isinstance(raw, int):
            raise ValueError("history row date is not an integer")
        text = str(raw)
        day = date(int(text[:4]), int(text[4:6]), int(text[6:]))
        if not start <= day <= end:
            raise ValueError(f"history row {day} outside {start}..{end}")
        records.append(
            {
                "date": day.isoformat(),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "time_key_ms": row["time_key"],
            }
        )
    if any(
        records[index]["date"] >= records[index + 1]["date"]
        for index in range(len(records) - 1)
    ):
        raise ValueError("history rows are not strictly chronological")
    return records


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

    client = MoomooRestClient(MoomooOAuth(store, open_browser=None))
    requests = [
        ("SPY", date(2016, 1, 4), date(2016, 12, 31)),
        ("SPY", date(2020, 1, 2), date(2020, 12, 31)),
        ("SPY", date(2024, 1, 2), date(2024, 12, 31)),
        ("AAPL", date(2016, 1, 4), date(2016, 12, 31)),
        ("AAPL", date(2024, 1, 2), date(2024, 12, 31)),
        ("SPY", date(2025, 5, 29), date(2026, 11, 16)),
    ]
    output = {
        "schema_version": "1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "order_writes_enabled": False,
        "endpoint": HISTORY_KLINES_PATH,
        "requests": [],
    }
    for symbol, start, end in requests:
        payload = client.get(
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
        data = payload.get("data")
        rows = data.get("kline_list") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise SystemExit(f"no history rows for {symbol} {start}..{end}")
        records = _records(rows, start, end)
        output["requests"].append(
            {
                "symbol": symbol,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "ret_code": payload.get("ret_code"),
                "rows": len(records),
                "first": records[0],
                "last": records[-1],
                "bars": records,
            }
        )
        print(
            f"{symbol} {start}..{end}: {len(records)} rows, "
            f"{records[0]['date']} to {records[-1]['date']}"
        )

    current = next(
        item
        for item in output["requests"]
        if item["symbol"] == "SPY" and item["start"] == "2025-05-29"
    )
    fixture = json.loads(
        (ROOT / "backend" / "tests" / "fixtures" / "moomoo_daily_bars_2026-11-16.json")
        .read_text(encoding="utf-8")
    )["symbols"]["SPY"]
    fresh = {
        row["date"]: row
        for row in current["bars"]
    }
    mismatches = []
    for row in fixture:
        day = f"{row['date'][:4]}-{row['date'][4:6]}-{row['date'][6:]}"
        other = fresh.get(day)
        if other is None:
            mismatches.append({"date": day, "issue": "missing from fresh response"})
            continue
        for field in ("open", "high", "low", "close"):
            if abs(float(row[field]) - float(other[field])) > 1e-6:
                mismatches.append(
                    {
                        "date": day,
                        "field": field,
                        "fixture": row[field],
                        "fresh": other[field],
                    }
                )
        if int(row["volume"]) != int(other["volume"]):
            mismatches.append(
                {
                    "date": day,
                    "field": "volume",
                    "fixture": row["volume"],
                    "fresh": other["volume"],
                }
            )
    output["fixture_crosscheck"] = {
        "same_range_as_fixture": len(fresh) == len(fixture),
        "fresh_rows": len(fresh),
        "fixture_rows": len(fixture),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
    }
    print("fixture crosscheck:", output["fixture_crosscheck"]["mismatch_count"], "mismatches")
    (OUT / "history-probe.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
