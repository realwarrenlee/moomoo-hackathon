"""Evaluate the frozen volume-confirmed relative-strength protocol on 2016-2024.

Research-only. This script never loads a bar on or after 2025-01-01, never
imports a broker/order path, and never changes production research state.

It uses Vibe-Trading's real GlobalEquityEngine in-process because the full
runner requires fastmcp and an external benchmark module that imports
yfinance. The only substitution is that benchmark resolver, which is stubbed
to return None; all reported benchmarks are separate deterministic runs over
the same Moomoo bars.
"""

from __future__ import annotations

import json
import math
import os
import sys
import types
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
OUT = Path(__file__).resolve().parent
DATA_FILE = OUT / "protocol-data" / "daily-bars-2015-2024.json"
PROTOCOL_FILE = (
    ROOT
    / "evidence"
    / "research"
    / "stock-selection-prereg-2026-11-18"
    / "protocol.json"
)
VIBE_AGENT = ROOT / "Vibe-Trading" / "agent"
VIBE_DEPS = os.environ.get("VIBE_TRADING_DEPS")
NY = ZoneInfo("America/New_York")
INITIAL_CASH = 100_000.0
COST_RATE = 0.0002
EVAL_START = date(2016, 1, 4)
EVAL_END = date(2024, 12, 31)
WARMUP = 200
PER_NAME = 0.10
MAX_NAMES = 3
MAX_GROSS = 0.30


@dataclass(frozen=True)
class Week:
    signal_date: date
    execution_date: date


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _et(day: str | date) -> pd.Timestamp:
    if isinstance(day, str):
        return pd.Timestamp(day, tz=NY)
    return pd.Timestamp(day.isoformat(), tz=NY)


def load_payload() -> dict:
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1":
        raise ValueError("unsupported data schema")
    if payload["period"]["end"] != "2024-12-31":
        raise ValueError("data file does not end at the frozen evaluation boundary")
    if payload["period"]["untouched_after"] != "2025-01-01":
        raise ValueError("unexpected untouched boundary")
    arguments = payload.get("source", {}).get("arguments", {})
    if arguments.get("autype") != 1 or arguments.get("ktype") != 2:
        raise ValueError("data was not fetched with daily forward-adjusted settings")
    return payload


def build_frames(payload: dict) -> tuple[dict[str, pd.DataFrame], list[date]]:
    symbols = payload["symbols"]
    if not isinstance(symbols, dict) or "SPY" not in symbols:
        raise ValueError("missing symbol data")
    frames: dict[str, pd.DataFrame] = {}
    for symbol, rows in symbols.items():
        if not rows:
            raise ValueError(f"{symbol} has no rows")
        index = pd.DatetimeIndex(
            [_et(row["date"]) for row in rows], name="trade_date"
        )
        frame = pd.DataFrame(
            [
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]),
                }
                for row in rows
            ],
            index=index,
        )
        frames[symbol] = frame
    calendar = [date.fromisoformat(day) for day in payload["calendar"]]
    return frames, calendar


def validate_data(
    payload: dict, frames: dict[str, pd.DataFrame], calendar: list[date]
) -> dict:
    from backtest.loaders.base import validate_ohlc

    symbols = list(frames)
    expected = set(calendar)
    errors: list[str] = []
    checks: dict[str, object] = {
        "symbols": symbols,
        "symbol_count": len(symbols),
        "calendar_sessions": len(calendar),
        "calendar_first": calendar[0].isoformat(),
        "calendar_last": calendar[-1].isoformat(),
        "data_first": min(day for f in frames.values() for day in f.index.date).isoformat(),
        "data_last": max(day for f in frames.values() for day in f.index.date).isoformat(),
        "no_bar_on_or_after_2025": all(
            day < date(2025, 1, 1) for f in frames.values() for day in f.index.date
        ),
    }
    for symbol, frame in frames.items():
        observed = [day for day in frame.index.date]
        if len(observed) != len(set(observed)):
            errors.append(f"{symbol}: duplicate sessions")
        if any(observed[i] >= observed[i + 1] for i in range(len(observed) - 1)):
            errors.append(f"{symbol}: sessions not strictly increasing")
        if set(observed) != expected:
            errors.append(
                f"{symbol}: {len(expected - set(observed))} missing, "
                f"{len(set(observed) - expected)} extra sessions"
            )
        if any(day.weekday() >= 5 for day in observed):
            errors.append(f"{symbol}: weekend session")
        for field in ("open", "high", "low", "close"):
            if (frame[field] <= 0).any():
                errors.append(f"{symbol}: non-positive {field}")
        if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
            errors.append(f"{symbol}: high below another price")
        if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
            errors.append(f"{symbol}: low above another price")
        if (frame["volume"] < 0).any():
            errors.append(f"{symbol}: negative volume")
        try:
            validated = validate_ohlc(frame, strategy="raise")
            if len(validated) != len(frame):
                errors.append(f"{symbol}: Vibe validate_ohlc dropped bars")
        except Exception as exc:
            errors.append(f"{symbol}: Vibe validate_ohlc failed: {exc}")

    shared = {tuple(f.index.date) for f in frames.values()}
    checks["all_symbols_share_calendar"] = len(shared) == 1
    checks["no_duplicate_sessions"] = all(f.index.is_unique for f in frames.values())
    checks["strictly_increasing_sessions"] = all(
        f.index.is_monotonic_increasing for f in frames.values()
    )
    checks["no_weekend_bars"] = not any("weekend" in e for e in errors)
    checks["ohlc_valid"] = not any(
        ("high below" in e or "low above" in e or "non-positive" in e or "Vibe" in e)
        for e in errors
    )
    checks["missing_or_extra_sessions"] = not any("missing" in e or "extra" in e for e in errors)
    checks["calendar_no_bar_on_or_after_2025"] = calendar[-1] < date(2025, 1, 1)
    checks["errors"] = errors
    checks["sessions_per_symbol"] = {s: len(f) for s, f in frames.items()}
    checks["max_abs_daily_move"] = {
        symbol: float(frame["close"].pct_change().abs().max())
        for symbol, frame in frames.items()
    }
    checks["extreme_moves_over_50pct"] = {
        symbol: move
        for symbol, move in checks["max_abs_daily_move"].items()
        if move > 0.50
    }
    checks["first_last_close"] = {
        symbol: {
            "first_date": frame.index[0].date().isoformat(),
            "first_close": float(frame["close"].iloc[0]),
            "last_date": frame.index[-1].date().isoformat(),
            "last_close": float(frame["close"].iloc[-1]),
        }
        for symbol, frame in frames.items()
    }
    checks["source"] = payload.get("source")
    checks["research_only"] = payload.get("research_only")
    checks["order_writes_enabled"] = payload.get("order_writes_enabled")
    return checks


def build_schedule(dates: pd.DatetimeIndex) -> list[Week]:
    by_week: dict[tuple[int, int], list[int]] = {}
    for i, ts in enumerate(dates):
        key = ts.date().isocalendar()[:2]
        by_week.setdefault((key[0], key[1]), []).append(i)
    weeks: list[Week] = []
    for _, indexes in sorted(by_week.items()):
        last = max(indexes)
        if last + 1 >= len(dates):
            continue
        signal_day = dates[last].date()
        execution_day = dates[last + 1].date()
        if execution_day < EVAL_START or execution_day > EVAL_END:
            continue
        weeks.append(Week(signal_day, execution_day))
    signal_days = [w.signal_date for w in weeks]
    execution_days = [w.execution_date for w in weeks]
    if len(signal_days) != len(set(signal_days)):
        raise ValueError("duplicate signal dates")
    if len(execution_days) != len(set(execution_days)):
        raise ValueError("duplicate execution dates")
    if any(w.signal_date >= w.execution_date for w in weeks):
        raise ValueError("signal date is not before execution date")
    if weeks[0].execution_date != EVAL_START:
        raise ValueError("first execution date is not the evaluation start")
    return weeks


def _candidate_rows(
    frames: dict[str, pd.DataFrame],
    universe: list[str],
    i: int,
) -> tuple[bool, float, float, list[tuple[float, str]]]:
    spy = frames["SPY"]["close"].to_numpy()
    spy_sma = float(spy[i - WARMUP + 1 : i + 1].mean())
    regime = bool(spy[i] > spy_sma)
    if not regime:
        return False, float(spy[i]), spy_sma, []
    eligible: list[tuple[float, str]] = []
    for symbol in universe:
        close = frames[symbol]["close"].to_numpy()
        volume = frames[symbol]["volume"].to_numpy()
        sma50 = float(close[i - 49 : i + 1].mean())
        if not close[i] > sma50:
            continue
        r20 = float(close[i] / close[i - 20] - 1.0)
        if not r20 > 0.0:
            continue
        recent = float(volume[i - 4 : i + 1].mean())
        base = float(volume[i - 24 : i - 4].mean())
        if base <= 0.0 or recent < 1.2 * base:
            continue
        eligible.append((r20, symbol))
    eligible.sort(key=lambda item: (-item[0], item[1]))
    return True, float(spy[i]), spy_sma, eligible


def compute_selections(
    frames: dict[str, pd.DataFrame],
    universe: list[str],
    weeks: list[Week],
) -> tuple[dict[date, list[str]], list[dict]]:
    dates = list(frames["SPY"].index.date)
    position = {day: i for i, day in enumerate(dates)}
    selections: dict[date, list[str]] = {}
    details: list[dict] = []
    for week in weeks:
        i = position[week.signal_date]
        if i < WARMUP:
            raise ValueError(f"{week.signal_date} has insufficient warmup")
        regime, spy_close, spy_sma, eligible = _candidate_rows(frames, universe, i)
        selected = [symbol for _, symbol in eligible[:MAX_NAMES]]
        selections[week.signal_date] = selected
        details.append(
            {
                "signal_date": week.signal_date.isoformat(),
                "execution_date": week.execution_date.isoformat(),
                "regime": regime,
                "spy_close": round(spy_close, 6),
                "spy_sma200": round(spy_sma, 6),
                "eligible_count": len(eligible),
                "selected": selected,
                "eligible": [
                    {"symbol": symbol, "return_20": round(r20, 8)}
                    for r20, symbol in eligible
                ],
            }
        )
    return selections, details


def validate_targets(
    frames: dict[str, pd.DataFrame],
    weeks: list[Week],
    selections: dict[date, list[str]],
) -> dict:
    issues: list[str] = []
    for week in weeks:
        selected = selections[week.signal_date]
        if len(selected) > MAX_NAMES:
            issues.append(f"{week.signal_date}: more than {MAX_NAMES} names")
        if len(selected) != len(set(selected)):
            issues.append(f"{week.signal_date}: duplicate names")
        if any(symbol not in frames for symbol in selected):
            issues.append(f"{week.signal_date}: unknown symbol")
        gross = PER_NAME * len(selected)
        if gross > MAX_GROSS + 1e-12:
            issues.append(f"{week.signal_date}: gross {gross} exceeds {MAX_GROSS}")
    return {
        "weeks": len(weeks),
        "max_names_observed": max((len(v) for v in selections.values()), default=0),
        "max_gross_observed": max(
            (PER_NAME * len(v) for v in selections.values()), default=0.0
        ),
        "all_selected_symbols_known": all(
            symbol in frames for selected in selections.values() for symbol in selected
        ),
        "issues": issues,
    }


def reference_selection(
    frames: dict[str, pd.DataFrame], universe: list[str], signal_day: date
) -> list[str]:
    spy = frames["SPY"]
    i = list(spy.index.date).index(signal_day)
    spy_close = spy["close"].iloc[i]
    spy_sma = spy["close"].iloc[i - 199 : i + 1].mean()
    if not spy_close > spy_sma:
        return []
    rows = []
    for symbol in universe:
        frame = frames[symbol]
        close = frame["close"]
        volume = frame["volume"]
        if not close.iloc[i] > close.iloc[i - 49 : i + 1].mean():
            continue
        r20 = close.iloc[i] / close.iloc[i - 20] - 1.0
        if not r20 > 0.0:
            continue
        recent = volume.iloc[i - 4 : i + 1].mean()
        base = volume.iloc[i - 24 : i - 4].mean()
        if base <= 0.0 or recent < 1.2 * base:
            continue
        rows.append((float(r20), symbol))
    rows.sort(key=lambda item: (-item[0], item[1]))
    return [symbol for _, symbol in rows[:MAX_NAMES]]


def validate_reference(
    frames: dict[str, pd.DataFrame],
    universe: list[str],
    weeks: list[Week],
    selections: dict[date, list[str]],
) -> dict:
    checks = []
    for index in (0, len(weeks) // 2, len(weeks) - 1):
        week = weeks[index]
        expected = reference_selection(frames, universe, week.signal_date)
        observed = selections[week.signal_date]
        checks.append(
            {
                "signal_date": week.signal_date.isoformat(),
                "observed": observed,
                "reference": expected,
                "match": observed == expected,
            }
        )
    return {
        "checks": checks,
        "all_match": all(item["match"] for item in checks),
    }


def validate_no_lookahead(
    frames: dict[str, pd.DataFrame],
    universe: list[str],
    weeks: list[Week],
    selections: dict[date, list[str]],
) -> dict:
    cutoff = date(2020, 6, 30)
    subset = [week for week in weeks if week.signal_date <= cutoff]
    truncated = {
        symbol: frame[frame.index.date <= cutoff].copy()
        for symbol, frame in frames.items()
    }
    truncated_selections, _ = compute_selections(truncated, universe, subset)
    perturbed = {symbol: frame.copy() for symbol, frame in frames.items()}
    for symbol, frame in perturbed.items():
        future = frame.index.date > cutoff
        for field in ("open", "high", "low", "close"):
            frame.loc[future, field] = frame.loc[future, field] * 10.0
        frame.loc[future, "volume"] = frame.loc[future, "volume"] * 100
    perturbed_selections, _ = compute_selections(perturbed, universe, subset)
    base = {week.signal_date: selections[week.signal_date] for week in subset}
    truncated_mismatches = [
        week.signal_date.isoformat()
        for week in subset
        if truncated_selections[week.signal_date] != base[week.signal_date]
    ]
    perturbed_mismatches = [
        week.signal_date.isoformat()
        for week in subset
        if perturbed_selections[week.signal_date] != base[week.signal_date]
    ]
    return {
        "cutoff": cutoff.isoformat(),
        "weeks_checked": len(subset),
        "truncated_future_mismatches": truncated_mismatches,
        "perturbed_future_mismatches": perturbed_mismatches,
        "passes": not truncated_mismatches and not perturbed_mismatches,
    }


def build_targets(
    frames: dict[str, pd.DataFrame],
    weeks: list[Week],
    selections: dict[date, list[str]],
) -> dict[str, pd.Series]:
    index = frames["SPY"].index
    targets = {
        symbol: pd.Series(0.0, index=index, dtype=float) for symbol in frames
    }
    for week in weeks:
        ts = _et(week.signal_date)
        for symbol in selections[week.signal_date]:
            targets[symbol].loc[ts] = PER_NAME
    return targets


class PrecomputedSignalEngine:
    def __init__(self, name: str, targets: dict[str, pd.Series]) -> None:
        self.name = name
        self._targets = targets

    def generate(self, data_map: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        return {
            symbol: self._targets[symbol].reindex(frame.index).fillna(0.0)
            for symbol, frame in data_map.items()
        }


def benchmark_targets(
    frames: dict[str, pd.DataFrame],
    weeks: list[Week],
    selections: dict[date, list[str]],
    universe: list[str],
    kind: str,
) -> dict[str, pd.Series]:
    index = frames["SPY"].index
    targets = {
        symbol: pd.Series(0.0, index=index, dtype=float) for symbol in frames
    }
    for week in weeks:
        ts = _et(week.signal_date)
        if kind == "exposure_matched_spy":
            targets["SPY"].loc[ts] = PER_NAME * len(selections[week.signal_date])
        elif kind == "constant_spy":
            targets["SPY"].loc[ts] = MAX_GROSS
        elif kind == "equal_weight":
            weight = MAX_GROSS / len(universe)
            for symbol in universe:
                targets[symbol].loc[ts] = weight
        else:
            raise ValueError(f"unknown benchmark kind {kind!r}")
    return targets


class ProtocolLoader:
    name = "moomoo_protocol_2015_2024"
    markets = {"us_equity"}
    requires_auth = False

    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self._frames = frames

    def is_available(self) -> bool:
        return True

    def fetch(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: list[str] | None = None,
    ) -> dict[str, pd.DataFrame]:
        del fields
        if interval not in {"1D", "1d"}:
            raise ValueError(f"unsupported interval {interval!r}")
        start = _et(start_date)
        end = _et(end_date)
        out: dict[str, pd.DataFrame] = {}
        for symbol in codes:
            frame = self._frames.get(symbol)
            if frame is None:
                continue
            window = frame[(frame.index >= start) & (frame.index <= end)].copy()
            if window.empty:
                continue
            from backtest.loaders.base import validate_ohlc

            window = validate_ohlc(window, strategy="raise")
            window.index.name = "trade_date"
            out[symbol] = window
        if not out:
            raise ValueError("no data in requested window")
        return out


class WholeShareGlobalEquityEngine:
    def __new__(cls, config: dict, market: str = "us"):
        from backtest.engines.global_equity import GlobalEquityEngine

        class _Engine(GlobalEquityEngine):
            def round_size(self, raw_size: float, price: float) -> float:
                if self.market == "us":
                    return float(math.floor(max(raw_size, 0.0)))
                return super().round_size(raw_size, price)

        return _Engine(config, market)


def install_offline_benchmark_stub() -> None:
    module = types.ModuleType("backtest.benchmark")

    def resolve_benchmark(**kwargs):
        del kwargs
        return None

    def default_benchmark(*args, **kwargs):
        del args, kwargs
        return None

    module.resolve_benchmark = resolve_benchmark  # type: ignore[attr-defined]
    module.default_benchmark = default_benchmark  # type: ignore[attr-defined]
    sys.modules["backtest.benchmark"] = module


def config_for(
    universe: list[str], execution_days: list[date], name: str
) -> dict:
    return {
        "codes": list(universe) + ["SPY"],
        "start_date": "2015-01-02",
        "end_date": "2024-12-31",
        "evaluation_start_date": EVAL_START.isoformat(),
        "interval": "1D",
        "source": "moomoo_protocol_2015_2024",
        "engine": "global_equity",
        "position_adjustment": "rebalance",
        "rebalance_mask": [day.isoformat() for day in execution_days],
        "initial_cash": INITIAL_CASH,
        "slippage_us": COST_RATE,
        "execution_cost_multiplier": 1.0,
        "extra_slippage_bps": 0.0,
        "rebalance_tolerance": 0.0,
        "benchmark": "none",
        "leverage": 1.0,
        "run_name": name,
    }


def _read_frame(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    frame = pd.read_csv(path, index_col=0)
    if frame.empty:
        return frame
    frame.index = pd.to_datetime(frame.index, utc=True).tz_convert(NY)
    for column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def read_artifacts(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict]]:
    artifacts = run_dir / "artifacts"
    equity = _read_frame(artifacts / "equity.csv")
    positions = _read_frame(artifacts / "positions.csv")
    targets = _read_frame(artifacts / "target_positions.csv")
    fills = []
    with (artifacts / "fills.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                fills.append(json.loads(line))
    return equity, positions, targets, fills


def episodes_from_fills(fills: list[dict]) -> dict:
    states: dict[str, dict] = {}
    episodes: list[dict] = []
    partial_reductions = 0
    reasons: dict[str, int] = {}
    for fill in fills:
        symbol = str(fill["symbol"])
        action = str(fill["action"])
        quantity = abs(float(fill["signed_quantity"]))
        notional = abs(float(fill["notional"]))
        fee = float(fill.get("fee") or 0.0)
        timestamp = pd.Timestamp(fill["timestamp"])
        bar_idx = int(fill["bar_idx"])
        state = states.setdefault(
            symbol,
            {
                "size": 0.0,
                "bought": 0.0,
                "sold": 0.0,
                "fees": 0.0,
                "entry_bar": None,
                "entry_time": None,
            },
        )
        if action in {"open", "increase"}:
            if state["size"] == 0.0:
                state["entry_bar"] = bar_idx
                state["entry_time"] = timestamp
                state["bought"] = 0.0
                state["sold"] = 0.0
                state["fees"] = 0.0
            state["size"] += quantity
            state["bought"] += notional
            state["fees"] += fee
        elif action in {"reduce", "close"}:
            state["sold"] += notional
            state["fees"] += fee
            state["size"] = max(0.0, state["size"] - quantity)
            reason = str(fill.get("reason") or action)
            reasons[reason] = reasons.get(reason, 0) + 1
            if state["size"] > 1e-9:
                partial_reductions += 1
            else:
                bought = state["bought"]
                pnl = state["sold"] - bought - state["fees"]
                episodes.append(
                    {
                        "symbol": symbol,
                        "entry_time": state["entry_time"].isoformat(),
                        "exit_time": timestamp.isoformat(),
                        "entry_bar": state["entry_bar"],
                        "exit_bar": bar_idx,
                        "holding_bars": bar_idx - int(state["entry_bar"]),
                        "holding_days": (timestamp - state["entry_time"]).days,
                        "bought": bought,
                        "sold": state["sold"],
                        "fees": state["fees"],
                        "pnl": pnl,
                        "return_pct": pnl / bought * 100.0 if bought > 0 else None,
                        "exit_reason": reason,
                    }
                )
                states[symbol] = {
                    "size": 0.0,
                    "bought": 0.0,
                    "sold": 0.0,
                    "fees": 0.0,
                    "entry_bar": None,
                    "entry_time": None,
                }
        else:
            raise ValueError(f"unknown fill action {action!r}")
    open_episodes = [
        {
            "symbol": symbol,
            "size": state["size"],
            "bought": state["bought"],
            "entry_time": state["entry_time"].isoformat()
            if state["entry_time"] is not None
            else None,
        }
        for symbol, state in states.items()
        if state["size"] > 1e-9
    ]
    pnls = [episode["pnl"] for episode in episodes]
    positive = [pnl for pnl in pnls if pnl > 0]
    top_three = sorted(pnls, reverse=True)[:3]
    total_pnl = sum(pnls)
    return {
        "completed_episodes": len(episodes),
        "hit_rate": (sum(1 for pnl in pnls if pnl > 0) / len(pnls))
        if pnls
        else None,
        "average_return_pct": float(np.mean([e["return_pct"] for e in episodes]))
        if episodes
        else None,
        "median_return_pct": float(np.median([e["return_pct"] for e in episodes]))
        if episodes
        else None,
        "average_holding_bars": float(np.mean([e["holding_bars"] for e in episodes]))
        if episodes
        else None,
        "average_holding_days": float(np.mean([e["holding_days"] for e in episodes]))
        if episodes
        else None,
        "net_pnl": total_pnl,
        "gross_positive_pnl": sum(positive),
        "top_three_pnl": top_three,
        "top_three_share_of_net": (sum(top_three) / total_pnl)
        if total_pnl > 0
        else None,
        "top_three_share_of_positive": (sum(top_three) / sum(positive))
        if positive
        else None,
        "best_episode": max(episodes, key=lambda e: e["pnl"]) if episodes else None,
        "worst_episode": min(episodes, key=lambda e: e["pnl"]) if episodes else None,
        "partial_reductions": partial_reductions,
        "exit_reasons": reasons,
        "open_episodes": open_episodes,
        "episodes": episodes,
    }


def compute_metrics(
    name: str,
    run_dir: Path | None,
    execution_days: list[date],
    weeks: int,
    selections: dict[date, list[str]] | None = None,
    cash_index: pd.DatetimeIndex | None = None,
) -> dict:
    if run_dir is None:
        index = cash_index if cash_index is not None else pd.DatetimeIndex([_et(EVAL_END)])
        equity = pd.Series(INITIAL_CASH, index=index)
        positions = pd.DataFrame()
        targets = pd.DataFrame()
        fills = []
    else:
        equity_frame, positions, targets, fills = read_artifacts(run_dir)
        equity = equity_frame["equity"]
        del equity_frame
    equity = equity.sort_index()
    ret = equity.pct_change().fillna(equity.iloc[0] / INITIAL_CASH - 1.0)
    peak = equity.cummax().clip(lower=INITIAL_CASH)
    drawdown = equity / peak - 1.0
    total_return = float(equity.iloc[-1] / INITIAL_CASH - 1.0)
    sessions = len(equity)
    cagr = (
        (equity.iloc[-1] / INITIAL_CASH) ** (252.0 / sessions) - 1.0
        if sessions > 0 and equity.iloc[-1] > 0
        else None
    )
    volatility = float(ret.std(ddof=1) * math.sqrt(252)) if sessions > 1 else None
    if not positions.empty:
        gross = positions.abs().sum(axis=1).reindex(equity.index).fillna(0.0)
        names = (positions.abs() > 1e-9).sum(axis=1).reindex(equity.index).fillna(0)
    else:
        gross = pd.Series(0.0, index=equity.index)
        names = pd.Series(0, index=equity.index)
    execution_targets = []
    turnover_total = 0.0
    previous = None
    if not targets.empty:
        for day in execution_days:
            ts = _et(day)
            if ts not in targets.index:
                continue
            row = targets.loc[ts].fillna(0.0)
            execution_targets.append(row)
            if previous is None:
                previous = pd.Series(0.0, index=row.index)
            turnover_total += 0.5 * float((row - previous).abs().sum())
            previous = row
    target_gross = [float(row.abs().sum()) for row in execution_targets]
    target_names = [int((row.abs() > 1e-9).sum()) for row in execution_targets]
    episodes = episodes_from_fills(fills)
    equity_pnl = float(equity.iloc[-1]) - INITIAL_CASH
    episode_pnl = float(episodes["net_pnl"])
    traded_notional = sum(abs(float(fill["notional"])) for fill in fills)
    fees = sum(float(fill.get("fee") or 0.0) for fill in fills)
    yearly = {}
    for year in range(EVAL_START.year, EVAL_END.year + 1):
        end = equity[equity.index.year == year]
        if end.empty:
            continue
        prior = equity[equity.index.year < year]
        start_value = float(prior.iloc[-1]) if len(prior) else INITIAL_CASH
        yearly[str(year)] = {
            "start": start_value,
            "end": float(end.iloc[-1]),
            "return_pct": (float(end.iloc[-1]) / start_value - 1.0) * 100.0,
        }
    return {
        "name": name,
        "sessions": sessions,
        "weeks": weeks,
        "final_value": float(equity.iloc[-1]),
        "total_return_pct": total_return * 100.0,
        "cagr_pct": cagr * 100.0 if cagr is not None else None,
        "annualized_volatility_pct": volatility * 100.0 if volatility is not None else None,
        "max_drawdown_pct": float(drawdown.min()) * 100.0,
        "average_gross_exposure_pct": float(gross.mean()) * 100.0,
        "maximum_gross_exposure_pct": float(gross.max()) * 100.0,
        "gross_cap_breach_days": int((gross > MAX_GROSS + 1e-9).sum()),
        "average_names": float(names.mean()),
        "weeks_invested": sum(1 for value in target_gross if value > 1e-9),
        "weeks_cash": sum(1 for value in target_gross if value <= 1e-9),
        "average_target_gross_pct": float(np.mean(target_gross)) * 100.0
        if target_gross
        else 0.0,
        "average_target_names": float(np.mean(target_names))
        if target_names
        else 0.0,
        "average_weekly_one_way_turnover_pct": (turnover_total / len(execution_targets) * 100.0)
        if execution_targets
        else 0.0,
        "annualized_one_way_turnover_pct": (turnover_total / len(execution_targets) * 52.0 * 100.0)
        if execution_targets
        else 0.0,
        "total_target_one_way_turnover_pct": turnover_total * 100.0,
        "fills": len(fills),
        "traded_notional": traded_notional,
        "fees": fees,
        "estimated_slippage": traded_notional * COST_RATE,
        "traded_notional_pct_of_average_equity": (
            traded_notional / float(equity.mean()) * 100.0 if len(equity) else None
        ),
        "yearly": yearly,
        "episodes": episodes,
        "episode_pnl_sum": episode_pnl,
        "equity_pnl": equity_pnl,
        "pnl_reconciliation_difference": episode_pnl - equity_pnl,
        "equity": equity,
        "positions": positions,
        "targets": targets,
    }


def selection_stats(weeks: list[Week], selections: dict[date, list[str]], details: list[dict]) -> dict:
    counts = {0: 0, 1: 0, 2: 0, 3: 0}
    per_symbol: dict[str, int] = {}
    per_year: dict[str, dict] = {}
    for week in weeks:
        selected = selections[week.signal_date]
        counts[len(selected)] = counts.get(len(selected), 0) + 1
        for symbol in selected:
            per_symbol[symbol] = per_symbol.get(symbol, 0) + 1
        year = str(week.execution_date.year)
        entry = per_year.setdefault(year, {"weeks": 0, "zero_names": 0, "selected": 0})
        entry["weeks"] += 1
        entry["zero_names"] += int(len(selected) == 0)
        entry["selected"] += len(selected)
    regime_false = sum(1 for item in details if not item["regime"])
    return {
        "weeks": len(weeks),
        "first_execution": weeks[0].execution_date.isoformat() if weeks else None,
        "last_execution": weeks[-1].execution_date.isoformat() if weeks else None,
        "first_signal": weeks[0].signal_date.isoformat() if weeks else None,
        "last_signal": weeks[-1].signal_date.isoformat() if weeks else None,
        "selection_count_histogram": {str(k): v for k, v in counts.items()},
        "regime_false_weeks": regime_false,
        "weeks_with_zero_names": counts.get(0, 0),
        "per_symbol_counts": dict(sorted(per_symbol.items(), key=lambda item: (-item[1], item[0]))),
        "per_year": per_year,
        "average_eligible_count": float(np.mean([item["eligible_count"] for item in details]))
        if details
        else 0.0,
        "max_eligible_count": max((item["eligible_count"] for item in details), default=0),
        "last_week": details[-1] if details else None,
    }


def run_one(
    name: str,
    frames: dict[str, pd.DataFrame],
    universe: list[str],
    weeks: list[Week],
    targets: dict[str, pd.Series],
) -> tuple[dict, Path]:
    run_dir = OUT / "protocol-runs" / name
    run_dir.mkdir(parents=True, exist_ok=True)
    config = config_for(universe, [week.execution_date for week in weeks], name)
    (run_dir / "config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )
    signal_engine = PrecomputedSignalEngine(name, targets)
    loader = ProtocolLoader(frames)
    engine = WholeShareGlobalEquityEngine(config, "us")
    result = engine.run_backtest(
        config, loader, signal_engine, run_dir, bars_per_year=252
    )
    (run_dir / "engine_metrics.json").write_text(
        json.dumps(_json_safe(result), indent=2), encoding="utf-8"
    )
    return result, run_dir


def _write_report(payload: dict) -> None:
    strategy = payload["strategy"]
    benchmarks = payload["benchmarks"]
    validation = payload["validation"]
    selections = payload["selections"]
    checks = validation["data_checks"]
    target_checks = validation["target_checks"]
    reference = validation["reference"]
    lookahead = validation["lookahead"]
    strategy_metrics = strategy["metrics"]
    episodes = strategy_metrics["episodes"]
    cmp = payload["comparison"]
    lines = [
        "# Frozen protocol evaluation — volume-confirmed relative strength",
        "",
        "**PAPER / HISTORICAL RESEARCH — NO BROKER, APPROVAL OR ORDER**",
        "",
        "Protocol: `volume-confirmed-relative-strength-v1`, frozen at "
        "`evidence/research/stock-selection-prereg-2026-11-18/protocol.json`. "
        "Window: 2016-01-04 to 2024-12-31. No 2025-2026 bar was loaded.",
        "",
        "## Verdict",
        "",
        f"- Strategy total return: **{strategy_metrics['total_return_pct']:.2f}%**; "
        f"CAGR **{strategy_metrics['cagr_pct']:.2f}%**; max drawdown "
        f"**{strategy_metrics['max_drawdown_pct']:.2f}%**.",
        f"- Same-schedule exposure-matched SPY: "
        f"**{benchmarks['exposure_matched_spy']['metrics']['total_return_pct']:.2f}%**; "
        f"equal-weight fixed universe at 30% gross: "
        f"**{benchmarks['equal_weight']['metrics']['total_return_pct']:.2f}%**; "
        f"constant 30% SPY: **{benchmarks['constant_spy']['metrics']['total_return_pct']:.2f}%**; "
        "cash: **0.00%**.",
        f"- Beat exposure-matched SPY: **{cmp['beats_exposure_matched']}**; "
        f"beat equal-weight universe: **{cmp['beats_equal_weight']}**.",
        f"- Pre-registered rejection rule triggered: **{cmp['rejection_rule_triggered']}** "
        f"(top-three episode concentration: **{cmp['depends_on_handful']}**; "
        f"fewer than 30 completed episodes: **{cmp['fewer_than_30_episodes']}**).",
        "",
        "This is one pre-registered run, not a parameter search. It is historical "
        "development evidence only; it is not deployment approval and does not "
        "authorise any allowlist, RiskGate or order change.",
        "",
        "## Data verification",
        "",
        f"- {checks['symbol_count']} symbols; {checks['calendar_sessions']} US sessions "
        f"({checks['calendar_first']} to {checks['calendar_last']}).",
        f"- No bar on or after 2025-01-01: **{checks['no_bar_on_or_after_2025']}**.",
        f"- All symbols share the provider calendar: **{checks['all_symbols_share_calendar']}**; "
        f"no duplicates: **{checks['no_duplicate_sessions']}**; no weekends: "
        f"**{checks['no_weekend_bars']}**; OHLC valid: **{checks['ohlc_valid']}**.",
        f"- Price basis: Moomoo `history-kline` `autype=1` forward-adjusted OHLC; "
        "volume is the provider daily volume. No adjustment factor is reconstructed "
        "independently.",
        f"- Largest absolute one-session close move across all symbols: "
        f"**{max(checks['max_abs_daily_move'].values()) * 100:.1f}%**; symbols above 50%: "
        f"**{len(checks['extreme_moves_over_50pct'])}**. No unadjusted split-scale break "
        "is visible, which is consistent with `autype=1` but is not independent proof.",
        f"- Data errors: **{len(checks['errors'])}**.",
        "",
        "## Protocol implementation checks",
        "",
        f"- Weekly schedule: **{selections['weeks']}** decision weeks, first execution "
        f"{selections['first_execution']}, last execution {selections['last_execution']}.",
        f"- Target constraints: max names **{target_checks['max_names_observed']}**, "
        f"max gross **{target_checks['max_gross_observed']:.2f}**, "
        f"issues **{len(target_checks['issues'])}**.",
        f"- Independent reference selection on first/middle/last weeks: "
        f"**{reference['all_match']}**.",
        f"- Look-ahead test (truncate and multiply all post-{lookahead['cutoff']} bars): "
        f"**{lookahead['passes']}** across {lookahead['weeks_checked']} weeks.",
        "",
        "## Strategy result",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Final value | ${strategy_metrics['final_value']:.2f} |",
        f"| Total return | {strategy_metrics['total_return_pct']:.2f}% |",
        f"| CAGR | {strategy_metrics['cagr_pct']:.2f}% |",
        f"| Annualized volatility | {strategy_metrics['annualized_volatility_pct']:.2f}% |",
        f"| Maximum drawdown | {strategy_metrics['max_drawdown_pct']:.2f}% |",
        f"| Average gross exposure | {strategy_metrics['average_gross_exposure_pct']:.2f}% |",
        f"| Maximum gross exposure | {strategy_metrics['maximum_gross_exposure_pct']:.2f}% |",
        f"| Days above 30% gross (intraweek drift) | {strategy_metrics['gross_cap_breach_days']} |",
        f"| Average names held | {strategy_metrics['average_names']:.2f} |",
        f"| Weeks invested / cash | {strategy_metrics['weeks_invested']} / {strategy_metrics['weeks_cash']} |",
        f"| Average weekly one-way turnover | {strategy_metrics['average_weekly_one_way_turnover_pct']:.2f}% |",
        f"| Completed holding episodes | {episodes['completed_episodes']} |",
        f"| Fill-episode P&L vs equity P&L | ${strategy_metrics['pnl_reconciliation_difference']:.6f} difference |",
        f"| Hit rate | {episodes['hit_rate'] * 100.0:.1f}% |" if episodes['hit_rate'] is not None else "| Hit rate | n/a |",
        (
            f"| Average holding period | {episodes['average_holding_bars']:.1f} sessions |"
            if episodes['average_holding_bars'] is not None
            else "| Average holding period | n/a |"
        ),
        (
            f"| Top three episodes' share of net P&L | "
            f"{episodes['top_three_share_of_net'] * 100.0:.1f}% |"
            if episodes['top_three_share_of_net'] is not None
            else "| Top three episodes' share of net P&L | n/a |"
        ),
        "",
        "## Benchmark comparison",
        "",
        "| Run | Total return | CAGR | Volatility | Max drawdown | Average gross |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key in ("strategy", "exposure_matched_spy", "constant_spy", "equal_weight", "cash"):
        if key == "strategy":
            item = strategy_metrics
            label = "Strategy"
        else:
            item = benchmarks[key]["metrics"]
            label = {
                "exposure_matched_spy": "SPY at strategy weekly gross",
                "constant_spy": "SPY constant 30%",
                "equal_weight": "Equal-weight 20 stocks, 30% gross",
                "cash": "Cash",
            }[key]
        lines.append(
            f"| {label} | {item['total_return_pct']:.2f}% | "
            f"{item['cagr_pct']:.2f}% | {item['annualized_volatility_pct']:.2f}% | "
            f"{item['max_drawdown_pct']:.2f}% | {item['average_gross_exposure_pct']:.2f}% |"
        )
    lines.extend(
        [
            "",
            f"- Excess vs same-schedule exposure-matched SPY: "
            f"**{cmp['excess_vs_exposure_matched_pct']:.2f}%**.",
            f"- Excess vs equal-weight fixed universe: "
            f"**{cmp['excess_vs_equal_weight_pct']:.2f}%**.",
            "",
            "## Year-by-year returns",
            "",
            "| Year | Strategy | Exposure-matched SPY | Constant 30% SPY | Equal-weight 30% |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for year in sorted(strategy_metrics["yearly"]):
        row = [f"| {year} | {strategy_metrics['yearly'][year]['return_pct']:.2f}%"]
        for key in ("exposure_matched_spy", "constant_spy", "equal_weight"):
            item = benchmarks[key]["metrics"]["yearly"].get(year)
            row.append(f"{item['return_pct']:.2f}%" if item else "n/a")
        lines.append(" | ".join(row) + " |")
    lines.extend(
        [
            "",
            "### Selection by year",
            "",
            "| Year | Weeks | Zero-name weeks | Selected-name slots |",
            "|---|---:|---:|---:|",
        ]
    )
    for year in sorted(selections["per_year"]):
        item = selections["per_year"][year]
        lines.append(
            f"| {year} | {item['weeks']} | {item['zero_names']} | {item['selected']} |"
        )
    lines.extend(
        [
            "",
            "## Selection activity",
            "",
            f"- Weeks with 0 / 1 / 2 / 3 names: "
            f"{selections['selection_count_histogram'].get('0', 0)} / "
            f"{selections['selection_count_histogram'].get('1', 0)} / "
            f"{selections['selection_count_histogram'].get('2', 0)} / "
            f"{selections['selection_count_histogram'].get('3', 0)}.",
            f"- SPY regime false in **{selections['regime_false_weeks']}** weeks; "
            f"zero-name weeks **{selections['weeks_with_zero_names']}**.",
            f"- Average eligible names per week: "
            f"{selections['average_eligible_count']:.1f}; maximum "
            f"{selections['max_eligible_count']}.",
            f"- Most selected symbols: "
            + ", ".join(
                f"{symbol} ({count})"
                for symbol, count in list(selections["per_symbol_counts"].items())[:8]
            )
            + ".",
            "",
            "## Interpretation assumptions",
            "",
            "- 10% per name is 10% of current portfolio equity; the weekly rebalance "
            "resets selected names to 10% and sells names no longer selected. This is "
            "the target-rebalance reading of the frozen protocol.",
            "- Initial capital is $100,000, whole shares, cash only, no leverage, no shorting.",
            "- The 30% gross limit is a weekly rebalance target, not an intraweek stop; "
            "price drift can leave close-of-day gross slightly above 30%, and those days "
            "are counted in the result.",
            "- Costs are 2 bps per side via Vibe's US slippage setting; US commission is zero.",
            "- The 2015-12-31 weekly signal is used for the first 2016-01-04 execution. "
            "2015 is warmup only.",
            "- 2024-12-31 is the last bar. Vibe force-closes any open position at that bar's "
            "close with slippage (`end_of_backtest`); the protocol has no intraweek stop.",
            "- The final week's signal (2024-12-31) has no execution inside the window and "
            "is not used.",
            "- The frozen rule's \"depends on a handful of trades\" is operationalised as: "
            "the top three completed holding episodes account for at least 100% of positive "
            "net P&L, or fewer than 30 completed episodes exist. Both diagnostics are "
            "reported; this is an evaluator check, not a tuned parameter.",
            "",
            "## Limitations",
            "",
            "- Fixed 20-stock universe declared before evaluation: survivorship and "
            "selection bias; it is not point-in-time index membership.",
            "- Forward-adjusted OHLC uses adjustment factors known only after the fact; "
            "relative returns and SMAs are largely invariant to multiplicative adjustment, "
            "but this is not a fully point-in-time corporate-action reconstruction.",
            "- Volume is raw provider volume. A stock split inside the 25-session volume "
            "window can create a false volume expansion (AAPL, NVDA, TSLA, AMZN, GOOGL and "
            "AVGO all split in this period). No split-adjusted volume was fabricated.",
            "- No delisted or halted names are present; large-cap coverage was complete.",
            "- Only one run was made; no parameter grid, threshold search or holdout reuse.",
            "- Vibe's terminal liquidation may differ from a mark-to-market ending and is "
            "applied to every run.",
            "- The full Vibe runner is not used: fastmcp is missing and `backtest.benchmark` "
            "imports yfinance. The real engine is invoked in-process with only the external "
            "benchmark resolver stubbed.",
            "",
            "## Evidence",
            "",
            "- `protocol-data/daily-bars-2015-2024.json` — 21-symbol OHLCV, provider metadata, "
            "calendar and request log.",
            "- `protocol-runs/strategy/artifacts/` and `protocol-runs/*/artifacts/` — Vibe "
            "equity, fills, trades, positions, targets and run cards for every run.",
            "- `results.json` — metrics, selections, validation and comparison.",
            "",
        ]
    )
    (OUT / "protocol-report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if VIBE_DEPS and VIBE_DEPS not in sys.path:
        sys.path.insert(0, VIBE_DEPS)
    if str(VIBE_AGENT) not in sys.path:
        sys.path.insert(0, str(VIBE_AGENT))
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    protocol = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    universe = list(protocol["universe"])
    payload = load_payload()
    frames, calendar = build_frames(payload)
    if set(frames) != set(universe) | {"SPY"}:
        raise SystemExit("data symbols do not match the frozen universe plus SPY")
    validation = {
        "data_checks": validate_data(payload, frames, calendar),
    }
    if validation["data_checks"]["errors"]:
        raise SystemExit(
            "data validation failed; refusing to evaluate: "
            + "; ".join(validation["data_checks"]["errors"][:5])
        )
    dates = frames["SPY"].index
    weeks = build_schedule(dates)
    selections, details = compute_selections(frames, universe, weeks)
    target_checks = validate_targets(frames, weeks, selections)
    if target_checks["issues"]:
        raise SystemExit("target validation failed: " + "; ".join(target_checks["issues"]))
    reference = validate_reference(frames, universe, weeks, selections)
    if not reference["all_match"]:
        raise SystemExit("independent reference selection mismatch")
    lookahead = validate_no_lookahead(frames, universe, weeks, selections)
    if not lookahead["passes"]:
        raise SystemExit("look-ahead check failed")
    validation["target_checks"] = target_checks
    validation["reference"] = reference
    validation["lookahead"] = lookahead

    install_offline_benchmark_stub()
    from backtest.engines.base import BaseEngine  # noqa: F401

    targets = build_targets(frames, weeks, selections)
    runs = {
        "strategy": targets,
        "exposure_matched_spy": benchmark_targets(
            frames, weeks, selections, universe, "exposure_matched_spy"
        ),
        "constant_spy": benchmark_targets(
            frames, weeks, selections, universe, "constant_spy"
        ),
        "equal_weight": benchmark_targets(
            frames, weeks, selections, universe, "equal_weight"
        ),
    }
    engine_results = {}
    run_dirs = {}
    for name, run_targets in runs.items():
        print(f"running {name}...")
        result, run_dir = run_one(name, frames, universe, weeks, run_targets)
        engine_results[name] = result
        run_dirs[name] = run_dir
    execution_days = [week.execution_date for week in weeks]
    metrics = {
        name: compute_metrics(
            name,
            run_dirs[name],
            execution_days,
            len(weeks),
            selections if name == "strategy" else None,
        )
        for name in runs
    }
    metrics["cash"] = compute_metrics(
        "cash",
        None,
        execution_days,
        len(weeks),
        cash_index=dates[dates.date >= EVAL_START],
    )
    reconciliation = metrics["strategy"]["pnl_reconciliation_difference"]
    if abs(reconciliation) > 1e-4:
        raise SystemExit(
            f"fill-episode P&L does not reconcile to equity: {reconciliation:.6f}"
        )
    for item in metrics.values():
        item.pop("equity", None)
        item.pop("positions", None)
        item.pop("targets", None)
    sel_stats = selection_stats(weeks, selections, details)
    benchmark_payload = {
        "exposure_matched_spy": {
            "metrics": metrics["exposure_matched_spy"],
            "engine_metrics": _json_safe(engine_results["exposure_matched_spy"]),
        },
        "constant_spy": {
            "metrics": metrics["constant_spy"],
            "engine_metrics": _json_safe(engine_results["constant_spy"]),
        },
        "equal_weight": {
            "metrics": metrics["equal_weight"],
            "engine_metrics": _json_safe(engine_results["equal_weight"]),
        },
        "cash": {"metrics": metrics["cash"]},
    }
    cmp = {
        "excess_vs_exposure_matched_pct": metrics["strategy"]["total_return_pct"]
        - metrics["exposure_matched_spy"]["total_return_pct"],
        "excess_vs_equal_weight_pct": metrics["strategy"]["total_return_pct"]
        - metrics["equal_weight"]["total_return_pct"],
        "beats_exposure_matched": metrics["strategy"]["total_return_pct"]
        > metrics["exposure_matched_spy"]["total_return_pct"],
        "beats_equal_weight": metrics["strategy"]["total_return_pct"]
        > metrics["equal_weight"]["total_return_pct"],
    }
    cmp["rejection_rule_triggered"] = not (
        cmp["beats_exposure_matched"] and cmp["beats_equal_weight"]
    )
    episodes = metrics["strategy"]["episodes"]
    top_three_share = episodes["top_three_share_of_net"]
    cmp["top_three_share_of_net"] = top_three_share
    cmp["depends_on_handful"] = bool(
        episodes["net_pnl"] > 0
        and top_three_share is not None
        and top_three_share >= 1.0
    )
    cmp["fewer_than_30_episodes"] = episodes["completed_episodes"] < 30
    cmp["rejection_rule_triggered"] = bool(
        cmp["rejection_rule_triggered"]
        or cmp["depends_on_handful"]
        or cmp["fewer_than_30_episodes"]
    )
    output = {
        "schema_version": "1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "order_writes_enabled": False,
        "no_broker_or_order_path": True,
        "protocol": {
            "id": protocol["protocol_id"],
            "status": protocol["status"],
            "window": {"start": EVAL_START.isoformat(), "end": EVAL_END.isoformat()},
            "untouched_after": protocol["data"]["evaluation_window"]["untouched_after"],
            "universe": universe,
            "no_parameter_search": protocol["evaluation_plan"]["no_parameter_search"],
        },
        "vibe_trading": {
            "version": "0.1.19",
            "commit": "a8d815d17ec054a34dbdfc7ce8d1d9972566b709",
            "license": "MIT",
            "modules_used": [
                "backtest.engines.global_equity.GlobalEquityEngine",
                "backtest.engines.base.BaseEngine.run_backtest",
                "backtest.engines.base._align",
                "backtest.loaders.base.validate_ohlc",
                "backtest.metrics.calc_metrics",
                "backtest.run_card.write_run_card",
                "backtest.rebalance_notes",
                "backtest.risk_xray",
            ],
            "runner_used": False,
            "runner_blocker": "fastmcp missing via safe_run_dir; yfinance imported by backtest.benchmark",
            "offline_substitution": "sys.modules['backtest.benchmark'].resolve_benchmark returns None",
            "engine": "GlobalEquityEngine (US) with a whole-share round_size override",
            "position_adjustment": "rebalance",
            "rebalance_mask": "explicit next-session execution dates",
        },
        "data": {
            "path": str(DATA_FILE.relative_to(ROOT)),
            "source": payload["source"],
            "calendar": str((OUT / "protocol-data" / "trading-days-US-2015-2024.json").relative_to(ROOT))
            if (OUT / "protocol-data" / "trading-days-US-2015-2024.json").exists()
            else None,
            "symbol_count": len(frames),
            "sessions": len(calendar),
        },
        "config": config_for(universe, execution_days, "strategy"),
        "validation": validation,
        "selections": sel_stats,
        "selection_details": details,
        "strategy": {
            "metrics": metrics["strategy"],
            "engine_metrics": _json_safe(engine_results["strategy"]),
        },
        "benchmarks": benchmark_payload,
        "comparison": cmp,
        "limitations": [
            "Fixed 20-stock universe: survivorship and selection bias.",
            "Forward-adjusted OHLC uses post-hoc adjustment factors; volume is raw and split-unadjusted.",
            "No delisted names; large-cap coverage was complete on the provider calendar.",
            "Vibe force-liquidates open positions at the final bar close.",
            "Full Vibe runner not used; external benchmark resolver is stubbed to None.",
            "One pre-registered run only; not out-of-sample alpha and not deployment approval.",
        ],
    }
    output = _json_safe(output)
    (OUT / "protocol-results.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    _write_report(output)
    print(
        json.dumps(
            {
                "strategy": {
                    "total_return_pct": metrics["strategy"]["total_return_pct"],
                    "cagr_pct": metrics["strategy"]["cagr_pct"],
                    "max_drawdown_pct": metrics["strategy"]["max_drawdown_pct"],
                    "average_gross_exposure_pct": metrics["strategy"][
                        "average_gross_exposure_pct"
                    ],
                    "episodes": metrics["strategy"]["episodes"]["completed_episodes"],
                },
                "benchmarks": {
                    key: value["metrics"]["total_return_pct"]
                    for key, value in benchmark_payload.items()
                },
                "comparison": cmp,
                "validation": {
                    "data_errors": len(validation["data_checks"]["errors"]),
                    "reference": reference["all_match"],
                    "lookahead": lookahead["passes"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
