"""Refresh completed daily bars from the documented Moomoo read-only REST endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.broker.moomoo_auth import FileTokenStore, MoomooOAuth, default_token_path
from app.broker.moomoo_history import MoomooHistoryFeed
from app.broker.moomoo_rest import MoomooRestClient
from app.cli import load_local_env
from app.research.data import UNIVERSE

ROOT = Path(__file__).resolve().parents[2]
NY = ZoneInfo("America/New_York")
MARKET_CLOSE_ET = time(16, 0)


class RefreshError(RuntimeError):
    pass


def _previous_trading_day(feed: MoomooHistoryFeed, today: date) -> date:
    days = feed.get_trading_days(today - timedelta(days=14), today)
    candidates = [day for day in days if day < today]
    if not candidates:
        raise RefreshError("no prior US trading day is available from the provider calendar")
    return candidates[-1]


def refresh(as_of: date | None, *, now: datetime | None = None) -> tuple[Path, dict[str, object]]:
    load_local_env(ROOT / ".env")
    if os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower() not in {"false", "0", "no", ""}:
        raise RefreshError("ORDER_WRITES_ENABLED must remain false")
    store = FileTokenStore(default_token_path())
    record = store.load()
    if record is None:
        raise RefreshError("Moomoo read authorization is required")
    if record.has_trade_write():
        raise RefreshError("stored authorization contains trade:write; refusing")
    if not record.has_required_scopes():
        raise RefreshError("stored authorization lacks required read scopes")

    oauth = MoomooOAuth(store, open_browser=None)
    feed = MoomooHistoryFeed(MoomooRestClient(oauth))
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        raise RefreshError("refresh clock must be timezone-aware")
    now_et = clock.astimezone(NY)
    if as_of is None:
        if now_et.time() >= MARKET_CLOSE_ET and feed.is_trading_day(now_et.date()):
            as_of = now_et.date()
        else:
            as_of = _previous_trading_day(feed, now_et.date())
    elif as_of > now_et.date():
        raise RefreshError("bar refresh date is in the future")
    elif as_of == now_et.date() and now_et.time() < MARKET_CLOSE_ET:
        raise RefreshError("the current US session has not closed")

    payload = feed.snapshot(UNIVERSE, as_of, now=clock, require_end_session=True)
    out_dir = ROOT / "evidence" / "current-market" / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "daily-bars.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path, payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh completed Moomoo daily bars (read-only)")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)
    try:
        path, payload = refresh(args.as_of)
    except Exception as exc:
        print(f"ABSTAINED: {str(exc) or exc.__class__.__name__}")
        return 1
    source = payload["source"]
    print(f"Bars refreshed: {path}")
    print(f"Last completed session: {source['last_completed_session']}")
    print(f"Fetched at: {source['fetched_at_utc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
