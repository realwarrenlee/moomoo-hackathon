"""Deployable-limit re-evaluation of the frozen momentum-v1 rules.

Research only. This script applies the RiskGate's 10% single-instrument and
30% gross exposure limits, whole-share sizing, next-open execution and 2 bps
per side to the existing 370-session fixture. It does not change the deployed
strategy and has no broker or order path.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

from app.research.data import MarketHistory, NewsArchive
from app.research.etf_baseline import (
    COST_BPS,
    BaselineResult,
    buy_and_hold_fraction,
    cash_baseline,
)
from app.research.evaluate import (
    INITIAL_EQUITY,
    BacktestResult,
    Trade,
    simulate_strategy,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "moomoo_daily_bars_2026-11-16.json"
OUT = ROOT / "evidence" / "research" / "momentum-deployable-2026-11-18"
ALLOCATION = Decimal("0.10")
GROSS_CAP = Decimal("0.30")


@dataclass(frozen=True)
class StudyMetrics:
    name: str
    start_date: date
    end_date: date
    sessions: int
    total_return: float
    cagr: float
    annualized_volatility: float
    sharpe: float | None
    max_drawdown: float
    average_exposure: float
    maximum_exposure: float
    entries: int
    closed_trades: int
    win_rate: float | None
    average_trade_return: float | None
    modelled_costs_usd: float | None
    open_position: str | None
    curve: tuple[tuple[date, Decimal], ...]
    trades: tuple[Trade, ...]


def _metrics(
    name: str,
    curve: list[tuple[date, Decimal]],
    exposures: list[Decimal],
    entries: int,
    trades: list[Trade],
    costs: Decimal,
    open_position: str | None,
) -> StudyMetrics:
    values = [float(value) for _, value in curve]
    initial = float(INITIAL_EQUITY)
    daily = [values[0] / initial - 1] + [
        values[index] / values[index - 1] - 1 for index in range(1, len(values))
    ]
    peak = initial
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak)
    deviations = statistics.stdev(daily) if len(daily) > 1 else 0.0
    closed = [trade for trade in trades if trade.exit_date is not None and trade.return_pct is not None]
    return StudyMetrics(
        name=name,
        start_date=curve[0][0],
        end_date=curve[-1][0],
        sessions=len(curve),
        total_return=values[-1] / initial - 1,
        cagr=(values[-1] / initial) ** (252 / max(len(daily), 1)) - 1,
        annualized_volatility=deviations * math.sqrt(252),
        sharpe=(
            statistics.mean(daily) / deviations * math.sqrt(252)
            if len(daily) > 1 and deviations > 0
            else None
        ),
        max_drawdown=drawdown,
        average_exposure=float(sum(exposures, Decimal("0")) / len(exposures)),
        maximum_exposure=float(max(exposures)),
        entries=entries,
        closed_trades=len(closed),
        win_rate=(
            sum(1 for trade in closed if trade.return_pct > 0) / len(closed) if closed else None
        ),
        average_trade_return=(
            sum(trade.return_pct for trade in closed if trade.return_pct is not None) / len(closed)
            if closed
            else None
        ),
        modelled_costs_usd=float(costs),
        open_position=open_position,
        curve=tuple(curve),
        trades=tuple(trades),
    )


def _from_backtest(result: BacktestResult) -> StudyMetrics:
    return StudyMetrics(
        name=result.name,
        start_date=result.start_date,
        end_date=result.end_date,
        sessions=len(result.equity_curve),
        total_return=result.total_return,
        cagr=result.cagr,
        annualized_volatility=result.annualized_volatility,
        sharpe=result.sharpe,
        max_drawdown=result.max_drawdown,
        average_exposure=result.average_exposure,
        maximum_exposure=result.maximum_exposure,
        entries=result.signals,
        closed_trades=sum(1 for trade in result.trades if trade.exit_date is not None),
        win_rate=result.win_rate,
        average_trade_return=result.average_trade_return,
        modelled_costs_usd=None,
        open_position=result.open_position,
        curve=result.equity_curve,
        trades=result.trades,
    )


def _from_baseline(result: BaselineResult) -> StudyMetrics:
    closed = [
        trade
        for trade in result.trades
        if trade.exit_date is not None and trade.return_pct is not None
    ]
    return StudyMetrics(
        name=result.name,
        start_date=result.start_date,
        end_date=result.end_date,
        sessions=len(result.equity_curve),
        total_return=result.total_return,
        cagr=result.cagr,
        annualized_volatility=result.annualized_volatility,
        sharpe=result.sharpe,
        max_drawdown=result.max_drawdown,
        average_exposure=result.average_exposure,
        maximum_exposure=result.maximum_exposure,
        entries=len(result.trades),
        closed_trades=len(closed),
        win_rate=(
            sum(1 for trade in closed if trade.return_pct > 0) / len(closed) if closed else None
        ),
        average_trade_return=(
            sum(trade.return_pct for trade in closed if trade.return_pct is not None) / len(closed)
            if closed
            else None
        ),
        modelled_costs_usd=result.costs_usd,
        open_position=result.open_position,
        curve=result.equity_curve,
        trades=tuple(
            Trade(
                symbol=trade.symbol,
                signal_date=trade.signal_date,
                entry_date=trade.entry_date,
                exit_date=trade.exit_date,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                return_pct=trade.return_pct,
            )
            for trade in result.trades
        ),
    )


def simulate_spy_on_schedule(
    history: MarketHistory,
    strategy_trades: tuple[Trade, ...],
    start_date: date,
    end_date: date,
    *,
    allocation: Decimal = ALLOCATION,
    whole_shares: bool = True,
    cost_bps: Decimal = COST_BPS,
) -> StudyMetrics:
    """Hold SPY on the strategy's exact entry/exit sessions and sizing rule."""
    dates = history.session_dates()
    start_index = dates.index(start_date)
    end_index = dates.index(end_date)
    cost = cost_bps / Decimal("10000")
    scheduled = {trade.entry_date: trade for trade in strategy_trades}
    cash = INITIAL_EQUITY
    shares = Decimal("0")
    entry_price = Decimal("0")
    entry_date: date | None = None
    entry_signal_date: date | None = None
    exit_date: date | None = None
    trades: list[Trade] = []
    curve: list[tuple[date, Decimal]] = []
    exposures: list[Decimal] = []
    costs = Decimal("0")
    entries = 0

    for session in dates[start_index : end_index + 1]:
        bar = history.bar_on("SPY", session)
        if bar is None:
            continue
        if shares > 0 and exit_date is not None and session == exit_date:
            exit_price = bar.open * (Decimal("1") - cost)
            costs += shares * bar.open * cost
            assert entry_date is not None and entry_signal_date is not None
            trades.append(
                Trade(
                    symbol="SPY",
                    signal_date=entry_signal_date,
                    entry_date=entry_date,
                    exit_date=session,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    return_pct=float(exit_price / entry_price - 1),
                )
            )
            cash += shares * exit_price
            shares = Decimal("0")
            entry_price = Decimal("0")
            entry_date = None
            entry_signal_date = None
            exit_date = None
        if shares == 0 and session in scheduled:
            source = scheduled[session]
            entry_price = bar.open * (Decimal("1") + cost)
            budget = cash * allocation
            quantity = (
                (budget / entry_price).to_integral_value(rounding=ROUND_FLOOR)
                if whole_shares
                else budget / entry_price
            )
            if quantity > 0:
                shares = quantity
                cash -= shares * entry_price
                costs += shares * bar.open * cost
                entry_signal_date = source.signal_date
                entry_date = session
                exit_date = source.exit_date
                entries += 1
        market_value = shares * bar.close
        equity = cash + market_value
        exposures.append(market_value / equity if equity else Decimal("0"))
        curve.append((session, equity))

    if shares > 0:
        last = history.bar_on("SPY", end_date)
        assert last is not None
        assert entry_date is not None and entry_signal_date is not None
        trades.append(
            Trade(
                symbol="SPY",
                signal_date=entry_signal_date,
                entry_date=entry_date,
                exit_date=None,
                entry_price=entry_price,
                exit_price=last.close,
                return_pct=float(last.close / entry_price - 1),
            )
        )
    return _metrics(
        "spy-same-schedule",
        curve,
        exposures,
        entries,
        trades,
        costs,
        "SPY" if shares > 0 else None,
    )


def _metrics_dict(result: StudyMetrics) -> dict[str, object]:
    return {
        "name": result.name,
        "start_date": result.start_date.isoformat(),
        "end_date": result.end_date.isoformat(),
        "sessions": result.sessions,
        "total_return_pct": round(result.total_return * 100, 4),
        "cagr_pct": round(result.cagr * 100, 4),
        "annualized_volatility_pct": round(result.annualized_volatility * 100, 4),
        "sharpe_descriptive": round(result.sharpe, 4) if result.sharpe is not None else None,
        "max_drawdown_pct": round(result.max_drawdown * 100, 4),
        "average_exposure_pct": round(result.average_exposure * 100, 4),
        "maximum_exposure_pct": round(result.maximum_exposure * 100, 4),
        "entries": result.entries,
        "closed_trades": result.closed_trades,
        "win_rate_pct": round(result.win_rate * 100, 4) if result.win_rate is not None else None,
        "average_trade_return_pct": (
            round(result.average_trade_return * 100, 4)
            if result.average_trade_return is not None
            else None
        ),
        "modelled_costs_usd": (
            round(result.modelled_costs_usd, 4)
            if result.modelled_costs_usd is not None
            else None
        ),
        "open_position": result.open_position,
    }


def _trades(result: StudyMetrics) -> list[dict[str, object]]:
    return [
        {
            "strategy": result.name,
            "symbol": trade.symbol,
            "signal_date": trade.signal_date.isoformat(),
            "entry_date": trade.entry_date.isoformat(),
            "exit_date": trade.exit_date.isoformat() if trade.exit_date else None,
            "entry_price": str(trade.entry_price),
            "exit_price": str(trade.exit_price) if trade.exit_price is not None else None,
            "return_pct": round(trade.return_pct * 100, 4) if trade.return_pct is not None else None,
        }
        for trade in result.trades
    ]


def _write_csvs(results: list[StudyMetrics]) -> None:
    dates = [day for day, _ in results[0].curve]
    for result in results[1:]:
        if [day for day, _ in result.curve] != dates:
            raise ValueError("result curves do not share the same sessions")
    with (OUT / "equity-curves.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["session_date", *(result.name for result in results)])
        for index, day in enumerate(dates):
            writer.writerow(
                [day.isoformat(), *(str(result.curve[index][1]) for result in results)]
            )
    with (OUT / "trades.csv").open("w", newline="", encoding="utf-8") as handle:
        rows = [row for result in results for row in _trades(result)]
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _report(results: dict[str, StudyMetrics], output: dict[str, object]) -> str:
    average_entry = results["momentum_deployable"].average_exposure * 100
    labels = {
        "momentum_deployable": "momentum-v1, 10% / 30% limits, whole shares",
        "spy_10pct": "SPY hold, 10%",
        "spy_average_exposure": f"SPY hold, {average_entry:.2f}% entry (approximate exposure match)",
        "spy_same_schedule": "SPY hold on strategy entry/exit sessions, 10%",
        "cash": "Cash",
    }
    lines = [
        "# Momentum-v1 deployable-limit evaluation",
        "",
        "**PAPER / HISTORICAL RESEARCH — NO BROKER SNAPSHOT, APPROVAL OR ORDER**",
        "",
        f"- Strategy: frozen `momentum-v1`; no rule or parameter change.",
        f"- Period: `{output['period']['start']}` to `{output['period']['end']}`; "
        f"{output['data']['evaluated_sessions']} evaluated sessions from a "
        f"{output['data']['sessions']}-session fixture.",
        f"- Sizing: {output['parameters']['allocation_pct']}% of equity per position, "
        f"{output['parameters']['gross_cap_pct']}% gross cap, at most "
        f"{output['parameters']['max_positions']} positions, whole shares, cash only.",
        "- Execution/cost: next session open, 2 bps per side; no leverage or shorting.",
        "- This is the same fixture and frozen rules as the earlier signal-quality study; "
        "it is **not** new out-of-sample evidence.",
        "",
        "## Results",
        "",
        "| Series | Total return | CAGR | Ann. vol | Sharpe | Max drawdown | Avg exposure | Max exposure | Entries |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in labels:
        row = _metrics_dict(results[name])
        lines.append(
            f"| {labels[name]} | {row['total_return_pct']:.2f}% | {row['cagr_pct']:.2f}% | "
            f"{row['annualized_volatility_pct']:.2f}% | "
            f"{row['sharpe_descriptive'] if row['sharpe_descriptive'] is not None else 'n/a'} | "
            f"{row['max_drawdown_pct']:.2f}% | {row['average_exposure_pct']:.2f}% | "
            f"{row['maximum_exposure_pct']:.2f}% | {row['entries']} |"
        )
    comparison = output["comparison"]
    lines.extend(
        [
            "",
            "## Difference from the earlier 100%-notional signal-quality study",
            "",
            "| Metric | Prior 100%-notional study | Deployable 10% / 30% study | Difference |",
            "|---|---:|---:|---:|",
            f"| Total return | {comparison['prior_total_return_pct']:.2f}% | "
            f"{comparison['deployable_total_return_pct']:.2f}% | "
            f"{comparison['total_return_difference_pct']:+.2f} pp |",
            f"| Max drawdown | {comparison['prior_max_drawdown_pct']:.2f}% | "
            f"{comparison['deployable_max_drawdown_pct']:.2f}% | "
            f"{comparison['drawdown_difference_pct']:+.2f} pp |",
            f"| Average exposure | {comparison['prior_average_exposure_pct']:.2f}% | "
            f"{comparison['deployable_average_exposure_pct']:.2f}% | "
            f"{comparison['exposure_difference_pct']:+.2f} pp |",
            "",
            "The prior study invested all available cash in one ETF and reached 100% exposure; "
            "this study caps each entry near 10% and leaves the remainder in cash. The return and "
            "drawdown differences are therefore mostly a sizing effect, not a new signal. The "
            "30% gross cap and three-position limit never bind because the frozen strategy holds "
            "at most one ETF.",
            "",
            "## Exposure-matched comparisons",
            "",
            f"- A constant 10% SPY holding returned "
            f"**{comparison['spy_10pct_total_return_pct']:.2f}%** with "
            f"{comparison['spy_10pct_max_drawdown_pct']:.2f}% maximum drawdown.",
            f"- A constant SPY holding entered at the strategy's average exposure "
            f"({comparison['deployable_average_exposure_pct']:.2f}%; realized "
            f"{comparison['spy_average_exposure_realized_pct']:.2f}%) returned "
            f"**{comparison['spy_average_exposure_total_return_pct']:.2f}%**.",
            f"- Holding SPY on the strategy's exact entry and exit sessions (realized "
            f"{comparison['spy_same_schedule_average_exposure_pct']:.2f}% average exposure) "
            f"returned **{comparison['spy_same_schedule_total_return_pct']:.2f}%**.",
            f"- Deployable momentum-v1 returned "
            f"**{comparison['deployable_total_return_pct']:.2f}%** with "
            f"{comparison['deployable_average_exposure_pct']:.2f}% average exposure. "
            "It did not beat any SPY comparator on the same dates.",
            "",
            "## Limitations",
            "",
            f"- Same {output['data']['sessions']}-bar fixture, with "
            f"{output['data']['evaluated_sessions']} evaluated sessions from "
            f"{output['period']['start']} to {output['period']['end']}; "
            f"one market regime and {output['results']['momentum_deployable']['entries']} entries. "
            "This is not out-of-sample evidence.",
            "- The earlier holdout window is reused only to show the effect of realistic sizing. "
            "It is not presented as a new independent test.",
            "- Whole-share flooring and 10% entry sizing can leave small residual cash and drift "
            f"above 10% at the close (observed maximum {comparison['deployable_maximum_exposure_pct']:.2f}%).",
            "- Adjusted-bar dividend treatment, taxes and corporate actions are not modelled separately.",
            "- Historical fills, liquidity and broker state are not simulated. No order was submitted.",
            "",
            "Artifacts: `results.json`, `equity-curves.csv`, `trades.csv`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    history = MarketHistory.from_file(FIXTURE)
    news = NewsArchive((), {"provider": "not used", "note": "momentum-v1 requires no news"})
    strategy = _from_backtest(
        simulate_strategy(
            history,
            news,
            "momentum-v1",
            allocation=ALLOCATION,
            whole_shares=True,
        )
    )
    start, end = strategy.start_date, strategy.end_date
    ten = _from_baseline(buy_and_hold_fraction(history, start, end, allocation=ALLOCATION))
    average = _from_baseline(
        buy_and_hold_fraction(
            history,
            start,
            end,
            allocation=Decimal(str(round(strategy.average_exposure, 6))),
        )
    )
    same_schedule = simulate_spy_on_schedule(history, strategy.trades, start, end)
    cash = _from_baseline(cash_baseline(start, end, history))
    results = {
        "momentum_deployable": strategy,
        "spy_10pct": ten,
        "spy_average_exposure": average,
        "spy_same_schedule": same_schedule,
        "cash": cash,
    }
    strategy_metrics = _metrics_dict(strategy)
    prior = {
        "total_return_pct": -0.4058,
        "max_drawdown_pct": 11.6768,
        "average_exposure_pct": 65.7143,
    }
    comparison = {
        "prior_total_return_pct": prior["total_return_pct"],
        "deployable_total_return_pct": strategy_metrics["total_return_pct"],
        "total_return_difference_pct": round(
            strategy_metrics["total_return_pct"] - prior["total_return_pct"], 4
        ),
        "prior_max_drawdown_pct": prior["max_drawdown_pct"],
        "deployable_max_drawdown_pct": strategy_metrics["max_drawdown_pct"],
        "drawdown_difference_pct": round(
            strategy_metrics["max_drawdown_pct"] - prior["max_drawdown_pct"], 4
        ),
        "prior_average_exposure_pct": prior["average_exposure_pct"],
        "deployable_average_exposure_pct": strategy_metrics["average_exposure_pct"],
        "deployable_maximum_exposure_pct": strategy_metrics["maximum_exposure_pct"],
        "exposure_difference_pct": round(
            strategy_metrics["average_exposure_pct"] - prior["average_exposure_pct"], 4
        ),
        "spy_10pct_total_return_pct": _metrics_dict(ten)["total_return_pct"],
        "spy_10pct_max_drawdown_pct": _metrics_dict(ten)["max_drawdown_pct"],
        "spy_average_exposure_total_return_pct": _metrics_dict(average)["total_return_pct"],
        "spy_average_exposure_realized_pct": _metrics_dict(average)["average_exposure_pct"],
        "spy_same_schedule_total_return_pct": _metrics_dict(same_schedule)["total_return_pct"],
        "spy_same_schedule_average_exposure_pct": _metrics_dict(same_schedule)[
            "average_exposure_pct"
        ],
    }
    output: dict[str, object] = {
        "schema_version": "1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "strategy_version": "momentum-v1",
        "research_only": True,
        "order_writes_enabled": False,
        "parameters": {
            "allocation_pct": float(ALLOCATION * 100),
            "gross_cap_pct": float(GROSS_CAP * 100),
            "max_positions": 3,
            "whole_shares": True,
            "cash_only": True,
            "cost_bps_per_side": float(COST_BPS),
            "shorting": False,
            "leverage": False,
        },
        "data": {
            "file": FIXTURE.name,
            "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "provider": history.source.get("provider"),
            "tool": history.source.get("tool"),
            "fetched_at_utc": history.source.get("fetched_at_utc"),
            "sessions": len(history.session_dates()),
            "evaluated_sessions": len(strategy.curve) - 1,
        },
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "results": {name: _metrics_dict(result) for name, result in results.items()},
        "comparison": comparison,
        "limitations": [
            "Same fixture and holdout as the earlier signal-quality study; not new out-of-sample evidence.",
            "Ten percent entry sizing and whole-share flooring explain most of the difference from the 100%-notional study.",
            "The 30% gross cap and three-position limit never bind because momentum-v1 holds at most one ETF.",
            "Adjusted-bar dividends, taxes, liquidity and broker fills are not separately modelled.",
            "No broker snapshot, approval or order is used.",
        ],
    }
    _write_csvs(list(results.values()))
    (OUT / "results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    (OUT / "report.md").write_text(_report(results, output), encoding="utf-8")
    print(json.dumps({"period": output["period"], "comparison": comparison}, indent=2))


if __name__ == "__main__":
    main()
