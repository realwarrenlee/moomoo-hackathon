from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.research.data import MarketHistory
from app.research.etf_baseline import (
    BASELINE_VERSION,
    COST_BPS,
    INITIAL_EQUITY,
    POLICY_MAX_SINGLE_EXPOSURE,
    SMA_WINDOW,
    BaselineResult,
    buy_and_hold_fraction,
    cash_baseline,
    default_period,
    simulate_monthly_trend,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "moomoo_daily_bars_2026-11-16.json"
OUT = ROOT / "evidence" / "research" / "etf-trend-baseline-2026-11-17"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(result: BaselineResult) -> dict[str, object]:
    return {
        "name": result.name,
        "start_date": result.start_date.isoformat(),
        "end_date": result.end_date.isoformat(),
        "sessions": len(result.equity_curve),
        "initial_equity_usd": str(result.initial_equity.quantize(Decimal("0.01"))),
        "final_equity_usd": str(result.final_equity.quantize(Decimal("0.01"))),
        "total_return_pct": round(result.total_return * 100, 4),
        "cagr_pct": round(result.cagr * 100, 4),
        "annualized_volatility_pct": round(result.annualized_volatility * 100, 4),
        "sharpe_descriptive": round(result.sharpe, 4) if result.sharpe is not None else None,
        "max_drawdown_pct": round(result.max_drawdown * 100, 4),
        "average_exposure_pct": round(result.average_exposure * 100, 4),
        "maximum_exposure_pct": round(result.maximum_exposure * 100, 4),
        "monthly_checks": result.monthly_checks,
        "turnover_gross_notional_over_average_equity": round(result.turnover, 6),
        "modelled_costs_usd": round(result.costs_usd, 4),
        "entries": len(result.trades),
        "open_position": result.open_position,
    }


def trades(result: BaselineResult) -> list[dict[str, object]]:
    return [
        {
            "strategy": result.name,
            "symbol": trade.symbol,
            "signal_date": trade.signal_date.isoformat(),
            "entry_date": trade.entry_date.isoformat(),
            "exit_date": trade.exit_date.isoformat() if trade.exit_date else None,
            "entry_price": str(trade.entry_price),
            "exit_price": str(trade.exit_price),
            "entry_notional_usd": str(trade.entry_notional.quantize(Decimal("0.01"))),
            "exit_notional_usd": str(trade.exit_notional.quantize(Decimal("0.01"))),
            "return_pct": round(trade.return_pct * 100, 4),
        }
        for trade in result.trades
    ]


def write_csvs(results: dict[str, BaselineResult]) -> None:
    dates = [day for day, _ in results["trend_baseline"].equity_curve]
    with (OUT / "equity-curves.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["session_date", *results])
        for index, day in enumerate(dates):
            writer.writerow(
                [day.isoformat(), *(str(results[name].equity_curve[index][1]) for name in results)]
            )
    with (OUT / "trades.csv").open("w", newline="", encoding="utf-8") as handle:
        rows = [row for result in results.values() for row in trades(result)]
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def markdown(
    results: dict[str, BaselineResult],
    output: dict[str, object],
) -> str:
    labels = {
        "trend_baseline": "ETF trend baseline (10% max)",
        "spy_hold_10pct": "SPY hold (10%)",
        "spy_hold_100pct": "SPY hold (100%, reference)",
        "cash": "Cash",
    }
    lines = [
        "# ETF trend baseline study",
        "",
        "**PAPER / HISTORICAL RESEARCH — NO BROKER SNAPSHOT, APPROVAL OR ORDER**",
        "",
        f"- Baseline: `{BASELINE_VERSION}`",
        f"- Data: committed Moomoo daily bars, `{output['data']['first_session']}` to "
        f"`{output['data']['last_session']}`",
        f"- Evaluation: `{output['period']['start']}` to `{output['period']['end']}`",
        "- Rules: at each completed month-end, hold SPY only if its close exceeds its "
        f"{SMA_WINDOW}-session SMA; execute at the next session open; maximum 10% of equity "
        "at entry; 2 bps per side; fractional shares.",
        "",
        "## Results",
        "",
        "| Series | Total return | CAGR | Ann. vol | Sharpe | Max drawdown | Avg exposure | Turnover | Cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in results.items():
        row = metrics(result)
        lines.append(
            f"| {labels[name]} | {row['total_return_pct']:.2f}% | {row['cagr_pct']:.2f}% | "
            f"{row['annualized_volatility_pct']:.2f}% | "
            f"{row['sharpe_descriptive'] if row['sharpe_descriptive'] is not None else 'n/a'} | "
            f"{row['max_drawdown_pct']:.2f}% | {row['average_exposure_pct']:.2f}% | "
            f"{row['turnover_gross_notional_over_average_equity']:.4f} | "
            f"${row['modelled_costs_usd']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Trades",
            "",
            "| Entry signal | Entry | Exit | Symbol | Entry notional | Return |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for trade in trades(results["trend_baseline"]):
        lines.append(
            f"| {trade['signal_date']} | {trade['entry_date']} | "
            f"{trade['exit_date'] or 'open at end'} | {trade['symbol']} | "
            f"${trade['entry_notional_usd']} | {trade['return_pct']:.2f}% |"
        )
    comparison = output["comparison"]
    lines.extend(
        [
            "",
            f"The baseline returned **{comparison['trend_total_return_pct']:.2f}%**, versus "
            f"**{comparison['spy_10pct_total_return_pct']:.2f}%** for a matched 10% SPY holding "
            f"and **{comparison['spy_full_total_return_pct']:.2f}%** for a fully invested SPY "
            "reference. It made one entry and did not exit before the data ended. The trend "
            "filter avoided most of April's decline but entered on 1 May after the recovery "
            "had begun, illustrating monthly timing lag.",
            "",
            "## Limitations",
            "",
            "- This is a signal-quality study with fractional shares, not a competition paper-account "
            "return. It does not prove execution, fills, buying power or account identity.",
            "- The fixture contains 370 sessions; the 200-session warmup leaves only about eight "
            "months and seven monthly decisions. One entry cannot establish durable alpha.",
            "- The 10% cap is enforced at entry. Mark-to-market drift can exceed it between "
            f"monthly reviews (observed maximum {metrics(results['trend_baseline'])['maximum_exposure_pct']:.2f}%).",
            "- Monthly decisions can miss fast reversals and produce a large gap between the "
            "signal close and the next-open fill.",
            "- Corporate-action and distribution treatment depends on the pinned Moomoo adjusted "
            "bars; cash dividends and taxes are not separately modelled.",
            "- The strategy is not registered in the order pipeline, has no proposal builder, and "
            "cannot submit orders. Any promotion requires a new reviewed version, the deterministic "
            "RiskGate, reconciliation and explicit first-order approval.",
            "- Descriptive Sharpe is not statistically meaningful for this short sample.",
            "",
            "Artifacts: `results.json`, `equity-curves.csv`, `trades.csv`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    history = MarketHistory.from_file(FIXTURE)
    start, end = default_period(history)
    results = {
        "trend_baseline": simulate_monthly_trend(history, start, end),
        "spy_hold_10pct": buy_and_hold_fraction(
            history, start, end, allocation=POLICY_MAX_SINGLE_EXPOSURE
        ),
        "spy_hold_100pct": buy_and_hold_fraction(history, start, end),
        "cash": cash_baseline(start, end, history),
    }
    baseline_metrics = metrics(results["trend_baseline"])
    ten_metrics = metrics(results["spy_hold_10pct"])
    full_metrics = metrics(results["spy_hold_100pct"])
    first_session = history.bars("SPY")[0].session_date.isoformat()
    last_session = history.bars("SPY")[-1].session_date.isoformat()
    output: dict[str, object] = {
        "schema_version": "1",
        "baseline_version": BASELINE_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "data": {
            "provider": history.source.get("provider"),
            "tool": history.source.get("tool"),
            "arguments": history.source.get("arguments"),
            "fetched_at_utc": history.source.get("fetched_at_utc"),
            "file": FIXTURE.name,
            "sha256": sha256(FIXTURE),
            "first_session": first_session,
            "last_session": last_session,
        },
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "parameters": {
            "symbol": "SPY",
            "sma_window_sessions": SMA_WINDOW,
            "decision_cadence": "completed month-end close",
            "execution": "next session open",
            "allocation_pct_of_equity": float(POLICY_MAX_SINGLE_EXPOSURE * 100),
            "policy_single_instrument_cap": True,
            "cost_bps_per_side": float(COST_BPS),
            "initial_equity_usd": str(INITIAL_EQUITY),
            "fractional_shares": True,
        },
        "results": {
            name: {"metrics": metrics(result), "trades": trades(result)}
            for name, result in results.items()
        },
        "comparison": {
            "trend_total_return_pct": baseline_metrics["total_return_pct"],
            "spy_10pct_total_return_pct": ten_metrics["total_return_pct"],
            "spy_full_total_return_pct": full_metrics["total_return_pct"],
            "excess_return_vs_spy_10pct_pct": round(
                baseline_metrics["total_return_pct"] - ten_metrics["total_return_pct"], 4
            ),
            "drawdown_difference_vs_spy_10pct_pct": round(
                ten_metrics["max_drawdown_pct"] - baseline_metrics["max_drawdown_pct"], 4
            ),
        },
        "limitations": [
            "Historical signal study, not a broker or paper-account result.",
            "Short post-warmup sample with one entry.",
            "Policy cap applied at entry; mark-to-market exposure can drift.",
            "Monthly timing lag between signal close and next-open execution.",
            "Dividend, tax and corporate-action modelling depends on adjusted fixture bars.",
            "Not registered as an executable strategy or linked to RiskGate order flow.",
        ],
    }
    write_csvs(results)
    (OUT / "results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    (OUT / "report.md").write_text(markdown(results, output), encoding="utf-8")
    print(json.dumps({"period": output["period"], "comparison": output["comparison"]}, indent=2))


if __name__ == "__main__":
    main()
