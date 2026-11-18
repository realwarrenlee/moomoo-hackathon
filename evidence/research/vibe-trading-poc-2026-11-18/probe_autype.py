"""Compare Moomoo autype price bases over a short read-only window."""

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
    if record is None or record.has_trade_write() or not record.has_required_scopes():
        raise SystemExit("Moomoo read-only token is unavailable or over-scoped")
    client = MoomooRestClient(MoomooOAuth(store, open_browser=None))

    start, end = date(2025, 5, 29), date(2025, 7, 15)
    output = {
        "schema_version": "1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "order_writes_enabled": False,
        "symbol": "SPY",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "bases": {},
    }
    for autype in (0, 1, 2):
        payload = client.get(
            HISTORY_KLINES_PATH.format(code="US.SPY"),
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "ktype": 2,
                "autype": autype,
                "num": 370,
                "extended_time": 0,
            },
        )
        rows = payload.get("data", {}).get("kline_list")
        if not isinstance(rows, list) or not rows:
            raise SystemExit(f"no rows for autype={autype}")
        output["bases"][str(autype)] = [
            {
                "date": row["date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for row in rows
        ]
        print(f"autype={autype}: {len(rows)} rows")
    (OUT / "autype-probe.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
