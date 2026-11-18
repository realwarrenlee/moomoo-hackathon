"""Append a point-in-time snapshot of the Moomoo oversold-reversal candidate.

Read-only: the observer never imports an order adapter and refuses to run when
order writes or trade:write authorization are present. It records provider
timestamps so later evaluation cannot mistake a snapshot for a backtest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.broker.moomoo_auth import FileTokenStore, MoomooOAuth, default_token_path
from app.broker.moomoo_rest import MoomooRestClient
from app.cli import load_local_env

ROOT = Path(__file__).resolve().parents[2]
NY = ZoneInfo("America/New_York")
PROTOCOL = "moomoo-oversold-reversal-v1"
STOCKS = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "XOM")
BENCHMARKS = ("SPY", "QQQ")
DEFAULT_OUTPUT = ROOT / "evidence" / "research" / "moomoo-signal-observation" / "observations.jsonl"
PROTOCOL_PATH = ROOT / "evidence" / "research" / "moomoo-tech-audit-2026-11-18" / "protocol.json"


class ObservationError(RuntimeError):
    pass


def _client() -> MoomooRestClient:
    load_local_env(ROOT / ".env")
    if os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower() not in {"false", "0", "no", ""}:
        raise ObservationError("ORDER_WRITES_ENABLED must remain false")
    store = FileTokenStore(default_token_path())
    record = store.load()
    if record is None:
        raise ObservationError("Moomoo read authorization is required")
    if record.has_trade_write():
        raise ObservationError("stored authorization contains trade:write; refusing")
    return MoomooRestClient(MoomooOAuth(store, open_browser=None))


def _session_end(now: datetime) -> str:
    local = now.astimezone(NY)
    day = local.date()
    if local.time() < time(16, 20):
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def _protocol_hash() -> str:
    if not PROTOCOL_PATH.exists():
        raise ObservationError("frozen protocol file is missing")
    return hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest()


def _bars(client: MoomooRestClient, symbol: str, end: str) -> list[dict[str, object]]:
    payload = client.get(
        f"/api/v1.0/quote/US.{symbol}/history-kline",
        {"end": end, "ktype": 2, "autype": 1, "num": 80, "extended_time": 0},
    )
    rows = (payload.get("data") or {}).get("kline_list")
    if not isinstance(rows, list) or len(rows) < 51:
        raise ObservationError(f"{symbol} has insufficient daily bars")
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            raise ObservationError(f"{symbol} daily bar is not an object")
        clean.append(row)
    clean.sort(key=lambda item: int(item["date"]))
    return clean


def _snapshot(client: MoomooRestClient, symbol: str) -> dict[str, object]:
    shape = client.get(f"/api/v1.0/quote/US.{symbol}/kline-shape", {"ktype": 2})
    polarity = client.get(
        f"/api/v1.0/quote/US.{symbol}/indicator-polarity", {"period": "DAY_1"}
    )
    shape_data = shape.get("data")
    polarity_data = polarity.get("data")
    if not isinstance(shape_data, dict) or not isinstance(polarity_data, dict):
        raise ObservationError(f"{symbol} provider response has no data object")
    items = polarity_data.get("items")
    if not isinstance(items, list):
        raise ObservationError(f"{symbol} polarity response has no items")
    compact = []
    rsi6 = None
    for item in items:
        if not isinstance(item, dict):
            continue
        values = item.get("values")
        last = values[-1] if isinstance(values, list) and values else None
        row = {
            "indicator_id": item.get("indicator_id"),
            "name": item.get("indicator_name"),
            "polarity": item.get("polarity"),
            "last_value": last,
        }
        compact.append(row)
        if item.get("indicator_name") == "RSI_6":
            rsi6 = item.get("polarity")
    return {
        "shape": {
            "name": shape_data.get("shape_name"),
            "direction": shape_data.get("direction"),
            "code": shape_data.get("kline_shape"),
        },
        "polarity": {
            "overall_score": polarity_data.get("overall_score"),
            "update_time_ms": polarity_data.get("update_time"),
            "items": compact,
        },
        "rsi6": rsi6,
    }


def _require_completed_session(rows: list[dict[str, object]], symbol: str, end: str) -> None:
    raw = str(rows[-1].get("date"))
    completed = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    if completed != end:
        raise ObservationError(
            f"{symbol} latest completed bar is {completed}, requested session is {end}"
        )


def _require_provider_session(provider: dict[str, object], symbol: str, end: str) -> None:
    raw = provider["polarity"]["update_time_ms"]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ObservationError(f"{symbol} polarity response has no update timestamp")
    observed = datetime.fromtimestamp(raw / 1000, UTC).astimezone(NY).date().isoformat()
    if observed != end:
        raise ObservationError(
            f"{symbol} polarity update is {observed}, requested session is {end}"
        )


def observe(client: MoomooRestClient, now: datetime, run_mode: str) -> dict[str, object]:
    end = _session_end(now)
    bars = {symbol: _bars(client, symbol, end) for symbol in STOCKS + BENCHMARKS}
    for symbol, rows in bars.items():
        _require_completed_session(rows, symbol, end)
    spy_closes = [float(bar["close"]) for bar in bars["SPY"]]
    if len(spy_closes) < 21:
        raise ObservationError("SPY has insufficient bars for the regime filter")
    spy_sma20 = sum(spy_closes[-20:]) / 20
    regime_ok = spy_closes[-1] > spy_sma20
    symbols: dict[str, object] = {}
    qualified: list[str] = []
    for symbol in STOCKS:
        rows = bars[symbol]
        closes = [float(bar["close"]) for bar in rows]
        volumes = [float(bar["volume"]) for bar in rows]
        sma50 = sum(closes[-50:]) / 50
        prior_volumes = volumes[-21:-1]
        volume_ratio = volumes[-1] / (sum(prior_volumes) / len(prior_volumes))
        dollar_volume = sum(
            closes[index] * volumes[index] for index in range(len(rows) - 21, len(rows) - 1)
        ) / 20
        provider = _snapshot(client, symbol)
        _require_provider_session(provider, symbol, end)
        conditions = {
            "regime": regime_ok,
            "trend": closes[-1] > sma50,
            "rsi6_oversold": provider["rsi6"] in {"OVER_SOLD", "SEVERELY_OVER_SOLD"},
            "bullish_pattern": provider["shape"]["direction"] == "BULLISH"
            and provider["shape"]["code"] not in {None, 0},
            "volume": volume_ratio >= 1.2,
            "liquidity": dollar_volume >= 100_000_000,
        }
        passed = all(conditions.values())
        if passed:
            qualified.append(symbol)
        symbols[symbol] = {
            "session_date": str(rows[-1]["date"]),
            "close": closes[-1],
            "sma50": round(sma50, 4),
            "volume_ratio_20": round(volume_ratio, 3),
            "dollar_volume_20": round(dollar_volume, 0),
            "provider": provider,
            "conditions": conditions,
            "qualified": passed,
        }
    ranked = sorted(
        qualified, key=lambda symbol: (-symbols[symbol]["dollar_volume_20"], symbol)
    )
    return {
        "schema_version": 2,
        "protocol": PROTOCOL,
        "protocol_sha256": _protocol_hash(),
        "run_mode": run_mode,
        "recorded_at_utc": now.astimezone(UTC).isoformat(),
        "market_time_et": now.astimezone(NY).isoformat(),
        "session_date": end,
        "regime": {"spy_close": spy_closes[-1], "spy_sma20": round(spy_sma20, 4), "ok": regime_ok},
        "symbols": symbols,
        "qualified": ranked,
        "selected": ranked[:3],
        "order_writes_enabled": False,
    }


def append(output: Path, record: dict[str, object]) -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            if json.loads(line).get("session_date") == record["session_date"]:
                return False
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record Moomoo signal observations")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mode", choices=["manual", "scheduled"], default="manual")
    args = parser.parse_args(argv)
    client = _client()
    record = observe(client, datetime.now(UTC), args.mode)
    written = append(args.output, record)
    state = "recorded" if written else "already recorded"
    print(
        f"{state}: {record['session_date']} regime={record['regime']['ok']} "
        f"qualified={record['qualified'] or 'none'} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
