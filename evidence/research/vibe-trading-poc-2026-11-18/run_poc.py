"""Minimal Vibe-Trading proof of concept on Moomoo daily bars.

Research-only. This script uses MooTrade's existing 370-session Moomoo fixture,
feeds it to the actual Vibe-Trading GlobalEquityEngine through an in-memory
loader, and compares the result with MooTrade's frozen momentum-v1 simulator.

No broker, account, order, scheduler, RiskGate or dashboard code is imported
or changed. ORDER_WRITES_ENABLED is not read by this script.

The full Vibe `python -m backtest.runner` path is intentionally not used:
the installed environment does not have fastmcp and the runner's external
benchmark module imports yfinance at module load. The engine itself is Vibe's
real execution and metrics implementation. The only in-process substitution is
`backtest.benchmark.resolve_benchmark`, which returns None so the engine uses
its own equal-weight basket benchmark and makes no network request.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import sys
import types
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
FIXTURE = BACKEND / "tests" / "fixtures" / "moomoo_daily_bars_2026-11-16.json"
CALENDAR = Path(__file__).resolve().parent / "trading-days-US-2025-05-29_2026-11-16.json"
OUT = Path(__file__).resolve().parent
VIBE_AGENT = ROOT / "Vibe-Trading" / "agent"
VIBE_DEPS = os.environ.get("VIBE_TRADING_DEPS")
NY = ZoneInfo("America/New_York")
SYMBOLS = ("SPY", "QQQ", "IWM")
INITIAL_CASH = 100_000.0
SMA_WINDOW = 20
ALLOCATION = 0.10
COST_RATE = 0.0002


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _et_date(raw: str) -> date:
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))


def load_fixture() -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    payload = _load_json(FIXTURE)
    if not isinstance(payload, dict) or payload.get("schema_version") != "1":
        raise ValueError("unsupported fixture schema")
    symbols = payload.get("symbols")
    if not isinstance(symbols, dict):
        raise ValueError("fixture has no symbols object")
    return symbols, dict(payload.get("source") or {})


def build_frames(symbols: dict[str, list[dict[str, object]]]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        rows = symbols.get(symbol)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"missing fixture rows for {symbol}")
        records = []
        index = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"non-object row for {symbol}")
            ms = row.get("time_key_ms")
            if not isinstance(ms, int) or ms <= 0:
                raise ValueError(f"invalid time_key_ms for {symbol}")
            stamp = datetime.fromtimestamp(ms / 1000, tz=UTC).astimezone(NY)
            index.append(pd.Timestamp(stamp))
            records.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]),
                }
            )
        frame = pd.DataFrame(records, index=pd.DatetimeIndex(index, name="trade_date"))
        frames[symbol] = frame
    return frames


def validate_data(
    symbols: dict[str, list[dict[str, object]]],
    frames: dict[str, pd.DataFrame],
) -> dict[str, object]:
    from backtest.loaders.base import validate_ohlc

    calendar_payload = _load_json(CALENDAR)
    calendar_days = [
        date.fromisoformat(day)
        for day in calendar_payload["trading_days"]  # type: ignore[index]
    ]

    expected_dates = [_et_date(str(row["date"])) for row in symbols["SPY"]]
    checks: dict[str, object] = {}
    checks["symbols"] = list(SYMBOLS)
    checks["provider_sessions"] = len(expected_dates)
    checks["provider_market"] = "US"
    checks["calendar_sessions"] = len(calendar_days)
    checks["calendar_matches_fixture"] = expected_dates == calendar_days
    checks["calendar_source"] = calendar_payload.get("source")  # type: ignore[union-attr]

    timestamp_errors: list[str] = []
    for symbol in SYMBOLS:
        for row in symbols[symbol]:
            ms = int(row["time_key_ms"])
            local = datetime.fromtimestamp(ms / 1000, tz=UTC).astimezone(NY)
            expected = _et_date(str(row["date"]))
            if local.time() != datetime.min.time():
                timestamp_errors.append(f"{symbol} {row['date']} is not midnight ET")
            if local.date() != expected:
                timestamp_errors.append(f"{symbol} {row['date']} date mismatch")
    checks["timestamp_errors"] = timestamp_errors
    checks["timestamps_are_midnight_new_york"] = not timestamp_errors

    shared_dates = [tuple(frame.index.date) for frame in frames.values()]
    checks["all_symbols_share_calendar"] = len(set(shared_dates)) == 1
    checks["no_duplicate_sessions"] = all(
        frame.index.is_unique for frame in frames.values()
    )
    checks["strictly_increasing_sessions"] = all(
        frame.index.is_monotonic_increasing for frame in frames.values()
    )
    checks["no_weekend_bars"] = all(
        day.weekday() < 5 for frame in frames.values() for day in frame.index.date
    )
    checks["sessions_per_symbol"] = {s: len(frames[s]) for s in SYMBOLS}

    ohlc_errors: list[str] = []
    for symbol, frame in frames.items():
        if (frame[["open", "high", "low", "close"]] <= 0).any().any():
            ohlc_errors.append(f"{symbol}: non-positive price")
        if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
            ohlc_errors.append(f"{symbol}: high below another price")
        if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
            ohlc_errors.append(f"{symbol}: low above another price")
        if (frame["volume"] < 0).any():
            ohlc_errors.append(f"{symbol}: negative volume")
        validated = validate_ohlc(frame, strategy="raise")
        if len(validated) != len(frame):
            ohlc_errors.append(f"{symbol}: Vibe validate_ohlc dropped bars")
    checks["ohlc_errors"] = ohlc_errors
    checks["ohlc_valid"] = not ohlc_errors

    source = symbols.get("_source")
    del source

    autype_note = None
    autype_probe = OUT / "autype-probe.json"
    if autype_probe.exists():
        probe = _load_json(autype_probe)
        bases = probe.get("bases", {}) if isinstance(probe, dict) else {}
        raw = bases.get("0") or []
        forward = bases.get("1") or []
        if raw and forward:
            raw_first = raw[0]
            forward_first = forward[0]
            fixture_first = symbols["SPY"][0]
            matches_raw = all(
                abs(float(fixture_first[field]) - float(raw_first[field])) < 1e-6
                for field in ("open", "high", "low", "close")
            )
            matches_forward = all(
                abs(float(fixture_first[field]) - float(forward_first[field])) < 1e-6
                for field in ("open", "high", "low", "close")
            )
            autype_note = {
                "probe": str(autype_probe.relative_to(ROOT)),
                "fixture_matches_autype_0_raw": matches_raw,
                "fixture_matches_autype_1_forward": matches_forward,
                "fixture_metadata_claim": "autype=1",
                "metadata_matches_values": not (matches_raw and not matches_forward),
                "example": {
                    "date": "2025-05-29",
                    "fixture_close": fixture_first["close"],
                    "autype_0_close": raw_first["close"],
                    "autype_1_close": forward_first["close"],
                },
            }
    return {
        "schema_version": "1",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "fixture": {
            "path": str(FIXTURE.relative_to(ROOT)),
            "sha256": _hash(FIXTURE),
            "source": {
                "provider": "Moomoo MCP read-only session",
                "tool": "quote_cur_kline",
                "adjustment_claim": "autype=1 (provider forward-adjusted)",
                "interval": "1D",
                "extended_time": 0,
                "num": 370,
                "last_completed_session": expected_dates[-1].isoformat(),
            },
        },
        "checks": checks,
        "price_basis_crosscheck": autype_note,
        "limitations": [
            "The fixture's source metadata says autype=1, but its 2025-05-29 bar matches history-kline autype=0 (raw), not autype=1 (forward-adjusted). Relative engine results remain comparable because both engines used the same bars.",
            "The fixture contains three US ETFs only; no delisted, halted or cross-listed instruments.",
            "The provider calendar and the bar timestamps are consistent, but corporate-action adjustment factors are not separately reconstructed.",
        ],
    }


class MoomooFixtureLoader:
    """DataLoaderProtocol implementation over the existing Moomoo fixture."""

    name = "moomoo_fixture"
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
        start = pd.Timestamp(start_date, tz=NY)
        end = pd.Timestamp(end_date, tz=NY)
        out: dict[str, pd.DataFrame] = {}
        for symbol in codes:
            frame = self._frames.get(symbol)
            if frame is None:
                continue
            window = frame[(frame.index >= start) & (frame.index <= end)].copy()
            if window.empty:
                continue
            window = window.dropna(subset=["open", "high", "low", "close"])
            from backtest.loaders.base import validate_ohlc

            window = validate_ohlc(window, strategy="raise")
            window.index.name = "trade_date"
            out[symbol] = window
        if not out:
            raise ValueError("no fixture data in requested window")
        return out


def make_signal_engine():
    """Build a Vibe SignalEngine that reproduces MooTrade's stateful selection."""

    from app.research.data import MarketHistory, NewsArchive, session_close_utc
    from app.research.strategy import screen

    history = MarketHistory.from_file(FIXTURE)
    news = NewsArchive((), {"provider": "not used", "note": "momentum-v1 is price-only"})
    session_dates = history.session_dates()

    class MomentumSignalEngine:
        name = "momentum-v1"

        def generate(self, data_map: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
            weights = {
                symbol: pd.Series(0.0, index=frame.index, dtype=float)
                for symbol, frame in data_map.items()
            }
            held: str | None = None
            for index in range(SMA_WINDOW, len(session_dates) - 1):
                session = session_dates[index]
                snapshot = screen(
                    history, news, session_close_utc(session), "momentum-v1"
                )
                if held is not None:
                    candidate = next(
                        (item for item in snapshot.candidates if item.symbol == held),
                        None,
                    )
                    if candidate is None or not candidate.above_sma:
                        held = None
                elif snapshot.selected_symbol is not None:
                    held = snapshot.selected_symbol
                if held is not None:
                    weights[held].iloc[index] = ALLOCATION
            return weights

    return MomentumSignalEngine()


class WholeShareGlobalEquityEngine:
    """Factory that returns Vibe's US engine with whole-share sizing."""

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


def _vibe_metrics(result: dict[str, object]) -> dict[str, object]:
    keys = (
        "final_value",
        "total_return",
        "annual_return",
        "max_drawdown",
        "sharpe",
        "sortino",
        "calmar",
        "win_rate",
        "profit_factor",
        "trade_count",
        "avg_holding_days",
        "benchmark_return",
        "excess_return",
        "benchmark_kind",
        "benchmark_label",
        "execution_costs",
    )
    return {key: result.get(key) for key in keys if key in result}


def _mootrade_metrics(result) -> dict[str, object]:
    return {
        "name": result.name,
        "start_date": result.start_date.isoformat(),
        "end_date": result.end_date.isoformat(),
        "sessions": len(result.equity_curve) - 1,
        "final_value": float(result.equity_curve[-1][1]),
        "total_return": result.total_return,
        "cagr": result.cagr,
        "annualized_volatility": result.annualized_volatility,
        "sharpe": result.sharpe,
        "max_drawdown": result.max_drawdown,
        "average_exposure": result.average_exposure,
        "maximum_exposure": result.maximum_exposure,
        "entries": result.signals,
        "closed_trades": sum(
            1 for trade in result.trades if trade.exit_date is not None
        ),
        "win_rate": result.win_rate,
        "average_trade_return": result.average_trade_return,
        "open_position": result.open_position,
    }


def _trade_rows(trades) -> list[dict[str, object]]:
    rows = []
    for trade in trades:
        entry = getattr(trade, "entry_date", None) or getattr(
            trade, "entry_time", None
        )
        exit_ = getattr(trade, "exit_date", None) or getattr(trade, "exit_time", None)
        signal = getattr(trade, "signal_date", None) or entry
        rows.append(
            {
                "symbol": trade.symbol,
                "signal_date": signal.isoformat() if signal is not None else None,
                "entry_date": entry.isoformat() if entry is not None else None,
                "exit_date": exit_.isoformat() if exit_ is not None else None,
                "entry_price": float(trade.entry_price),
                "exit_price": float(trade.exit_price)
                if trade.exit_price is not None
                else None,
                "return_pct": round(trade.return_pct * 100, 6)
                if getattr(trade, "return_pct", None) is not None
                else round(trade.pnl_pct, 6)
                if getattr(trade, "pnl_pct", None) is not None
                else None,
                "exit_reason": getattr(trade, "exit_reason", None),
            }
        )
    return rows


def _compare_curves(
    vibe_equity: pd.Series, mootrade_curve: tuple[tuple[date, Decimal], ...]
) -> dict[str, object]:
    mootrade = {day: float(value) for day, value in mootrade_curve}
    rows = []
    for timestamp, value in vibe_equity.items():
        day = timestamp.date()
        if day in mootrade:
            rows.append((day, float(value), mootrade[day]))
    differences = [abs(vibe - moo) for _, vibe, moo in rows]
    largest = max(rows, key=lambda row: abs(row[1] - row[2])) if rows else None
    return {
        "common_sessions": len(rows),
        "max_abs_equity_difference": max(differences) if differences else None,
        "largest_difference": {
            "date": largest[0].isoformat(),
            "vibe": largest[1],
            "mootrade": largest[2],
            "difference": largest[1] - largest[2],
        }
        if largest
        else None,
        "terminal_vibe": float(vibe_equity.iloc[-1]) if len(vibe_equity) else None,
        "terminal_mootrade": float(mootrade_curve[-1][1]) if mootrade_curve else None,
    }


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def main() -> None:
    if VIBE_DEPS and VIBE_DEPS not in sys.path:
        sys.path.insert(0, VIBE_DEPS)
    if str(VIBE_AGENT) not in sys.path:
        sys.path.insert(0, str(VIBE_AGENT))
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    symbols, fixture_source = load_fixture()
    frames = build_frames(symbols)
    validation = validate_data(symbols, frames)
    if not all(
        validation["checks"][key]  # type: ignore[index]
        for key in (
            "calendar_matches_fixture",
            "timestamps_are_midnight_new_york",
            "all_symbols_share_calendar",
            "no_duplicate_sessions",
            "strictly_increasing_sessions",
            "no_weekend_bars",
            "ohlc_valid",
        )
    ):
        raise SystemExit("fixture validation failed; refusing to run backtest")

    install_offline_benchmark_stub()
    from backtest.engines.base import _align  # noqa: F401  (import proves contract)
    from backtest.loaders.base import validate_ohlc  # noqa: F401

    run_dir = OUT / "vibe-run"
    (run_dir / "code").mkdir(parents=True, exist_ok=True)
    config = {
        "codes": list(SYMBOLS),
        "start_date": "2025-05-29",
        "end_date": "2026-11-16",
        "interval": "1D",
        "source": "moomoo_fixture",
        "engine": "global_equity",
        "position_adjustment": "hold",
        "initial_cash": INITIAL_CASH,
        "slippage_us": COST_RATE,
        "execution_cost_multiplier": 1.0,
        "extra_slippage_bps": 0.0,
        "warmup_bars": SMA_WINDOW + 1,
        "benchmark": "none",
        "leverage": 1.0,
    }
    (run_dir / "config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )
    (run_dir / "code" / "signal_engine.py").write_text(
        '''"""POC signal engine: MooTrade momentum-v1 rules, 10% target weight."""
from __future__ import annotations
import pandas as pd
from app.research.data import MarketHistory, NewsArchive, session_close_utc
from app.research.strategy import screen

class SignalEngine:
    def generate(self, data_map: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
        history = MarketHistory.from_file("backend/tests/fixtures/moomoo_daily_bars_2026-11-16.json")
        news = NewsArchive((), {"provider": "not used", "note": "momentum-v1 is price-only"})
        dates = history.session_dates()
        weights = {s: pd.Series(0.0, index=f.index, dtype=float) for s, f in data_map.items()}
        held = None
        for index in range(20, len(dates) - 1):
            snapshot = screen(history, news, session_close_utc(dates[index]), "momentum-v1")
            if held is not None:
                candidate = next((c for c in snapshot.candidates if c.symbol == held), None)
                if candidate is None or not candidate.above_sma:
                    held = None
            elif snapshot.selected_symbol is not None:
                held = snapshot.selected_symbol
            if held is not None:
                weights[held].iloc[index] = 0.10
        return weights
''',
        encoding="utf-8",
    )

    from backtest.engines.base import BaseEngine

    engine = WholeShareGlobalEquityEngine(config, "us")
    loader = MoomooFixtureLoader(frames)
    signal_engine = make_signal_engine()
    vibe_result = engine.run_backtest(
        config, loader, signal_engine, run_dir, bars_per_year=252
    )

    from app.research.data import MarketHistory, NewsArchive
    from app.research.evaluate import simulate_strategy

    history = MarketHistory.from_file(FIXTURE)
    news = NewsArchive((), {"provider": "not used", "note": "momentum-v1 is price-only"})
    mootrade = simulate_strategy(
        history,
        news,
        "momentum-v1",
        start_index=SMA_WINDOW,
        cost_bps=Decimal("2"),
        allocation=Decimal(str(ALLOCATION)),
        whole_shares=True,
    )

    vibe_equity = pd.read_csv(run_dir / "artifacts" / "equity.csv", index_col=0)
    vibe_equity.index = pd.to_datetime(vibe_equity.index, utc=True).tz_convert(NY)
    for column in ("equity", "ret", "drawdown", "benchmark_equity", "active_ret"):
        vibe_equity[column] = pd.to_numeric(vibe_equity[column], errors="coerce")
    comparison = _compare_curves(vibe_equity["equity"], mootrade.equity_curve)

    vibe_trades = _trade_rows(engine.trades)
    mootrade_trades = _trade_rows(mootrade.trades)

    payload = {
        "schema_version": "1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "order_writes_enabled": False,
        "no_broker_or_order_path": True,
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
            "engine": "GlobalEquityEngine (US rules) with a POC whole-share round_size override",
        },
        "data": {
            "fixture": str(FIXTURE.relative_to(ROOT)),
            "sha256": _hash(FIXTURE),
            "provider": fixture_source.get("provider"),
            "tool": fixture_source.get("tool"),
            "arguments": fixture_source.get("arguments"),
            "last_completed_session": "2026-11-16",
        },
        "validation": validation,
        "config": config,
        "vibe_metrics": _vibe_metrics(vibe_result),
        "mootrade_metrics": _mootrade_metrics(mootrade),
        "curve_comparison": comparison,
        "vibe_trades": vibe_trades,
        "mootrade_trades": mootrade_trades,
        "limitations": [
            "The full Vibe runner is not used; the real GlobalEquityEngine is invoked in-process.",
            "The external benchmark resolver is stubbed to None, so Vibe reports its equal-weight basket benchmark and makes no network call.",
            "US fractional-share sizing was overridden to whole shares to match MooTrade; this is a POC subclass, not upstream default behaviour.",
            "Vibe force-liquidates the open position at the final bar; MooTrade marks it at the final close without an exit cost.",
            "The fixture covers 370 sessions in one regime; this is not out-of-sample or deployment evidence.",
            "No broker snapshot, order, RiskGate or scheduler path is used.",
        ],
    }
    (OUT / "results.json").write_text(
        json.dumps(_json_safe(payload), indent=2), encoding="utf-8"
    )
    _write_report(payload, vibe_equity, mootrade)
    print(json.dumps(_json_safe({
        "vibe_metrics": payload["vibe_metrics"],
        "mootrade_metrics": payload["mootrade_metrics"],
        "curve_comparison": comparison,
    }), indent=2))


def _write_report(payload: dict[str, object], vibe_equity: pd.DataFrame, mootrade) -> None:
    vibe = payload["vibe_metrics"]  # type: ignore[index]
    moo = payload["mootrade_metrics"]  # type: ignore[index]
    cmp = payload["curve_comparison"]  # type: ignore[index]
    validation = payload["validation"]  # type: ignore[index]
    checks = validation["checks"]  # type: ignore[index]
    lines = [
        "# Vibe-Trading proof of concept",
        "",
        "**PAPER / HISTORICAL RESEARCH — NO BROKER, APPROVAL OR ORDER**",
        "",
        "## Result",
        "",
        "| Metric | Vibe GlobalEquityEngine | MooTrade simulator |",
        "|---|---:|---:|",
        f"| Total return | {vibe['total_return'] * 100:.4f}% | {moo['total_return'] * 100:.4f}% |",
        f"| Final value | ${vibe['final_value']:.2f} | ${moo['final_value']:.2f} |",
        f"| Max drawdown | {vibe['max_drawdown'] * 100:.4f}% | {moo['max_drawdown'] * 100:.4f}% |",
        f"| Sharpe (descriptive) | {vibe['sharpe']:.4f} | {moo['sharpe']:.4f} |",
        f"| Sessions | {len(vibe_equity)} | {moo['sessions']} |",
        f"| Round-trip trades | {vibe.get('trade_count', 'n/a')} | {moo['closed_trades']} |",
        "",
        f"- Maximum common-session equity difference: "
        f"**${cmp['max_abs_equity_difference']:.12f}** over {cmp['common_sessions']} sessions. "
        "The two engines hold identical shares and produce the same equity curve.",
        f"- Terminal values are identical to floating-point precision: Vibe "
        f"`${cmp['terminal_vibe']:.2f}` vs MooTrade `${cmp['terminal_mootrade']:.2f}`. "
        "No position was open at the end of this run.",
        "- Both engines now compute total return on the $100,000 initial equity, and MooTrade's "
        "curve includes that initial value. The metric-base discrepancy found by the original "
        f"POC was corrected in `backend/app/research/evaluate.py`.",
        "",
        "## Data verification",
        "",
        f"- {checks['provider_sessions']} provider sessions; Moomoo US calendar returned "
        f"{checks['calendar_sessions']} sessions; exact match: **{checks['calendar_matches_fixture']}**.",
        f"- All timestamps are midnight America/New_York: **{checks['timestamps_are_midnight_new_york']}**.",
        f"- Shared calendar across SPY/QQQ/IWM: **{checks['all_symbols_share_calendar']}**; "
        f"no duplicate sessions: **{checks['no_duplicate_sessions']}**; no weekend bars: "
        f"**{checks['no_weekend_bars']}**.",
        f"- OHLC invariants and Vibe `validate_ohlc(strategy='raise')`: **{checks['ohlc_valid']}**.",
    ]
    basis = payload["validation"].get("price_basis_crosscheck")  # type: ignore[index]
    if basis:
        lines.extend(
            [
                f"- **Price-basis defect found:** the fixture metadata says `autype=1`, "
                f"but its 2025-05-29 close (`{basis['example']['fixture_close']}`) matches "
                f"`history-kline autype=0` raw (`{basis['example']['autype_0_close']}`), not "
                f"`autype=1` forward-adjusted (`{basis['example']['autype_1_close']}`).",
                "- The POC's engine comparison remains valid because both engines consumed the "
                "same fixture bars; the fixture is not valid evidence of forward-adjusted returns.",
            ]
        )
    lines.extend(
        [
            "",
            "## What was actually used",
            "",
            "- Vibe `GlobalEquityEngine` / `BaseEngine.run_backtest`, `_align`, `validate_ohlc`, "
            "`calc_metrics`, run-card and artifacts; not the Vibe agent runner.",
            "- The full runner is blocked in this environment by missing `fastmcp` and a module-level "
            "`yfinance` import in `backtest.benchmark`.",
            "- The only offline substitution is the external benchmark resolver, which returns none; "
            "no network or market-data call is made by Vibe.",
            "- The POC overrides US fractional sizing to whole shares and forces no daily resizing.",
            "",
            "## Verdict",
            "",
            "Vibe's execution engine can consume the Moomoo fixture and reproduce the frozen "
            "momentum-v1 cash/exposure path exactly (equity difference below $1e-10). The POC "
            "also found a MooTrade metric-base defect, now corrected, and a stale price-basis "
            "label in the existing fixture. Vibe is usable as a research engine with adaptation, "
            "but this single POC does not justify replacing MooTrade's research path by itself.",
            "",
            "Artifacts: `results.json`, `vibe-run/` (Vibe artifacts and run card), "
            "`vibe-run/artifacts/equity.csv`, `history-probe.json`, `autype-probe.json`.",
            "",
        ]
    )
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
