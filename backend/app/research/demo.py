from __future__ import annotations

import argparse
import os
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from app.research.data import MarketHistory, NewsArchive
from app.research.dryrun import (
    STRATEGIES,
    control_rejection_example,
    find_accepted_example,
    latest_decision,
    oversized_example,
    stale_quote_example,
)
from app.research.evaluate import buy_and_hold, cash_baseline, simulate_strategy
from app.research.report import ReportBundle, render_report

DEFAULT_BARS = "backend/tests/fixtures/moomoo_daily_bars_2026-11-16.json"
DEFAULT_NEWS = "backend/tests/fixtures/moomoo_news_2026-11-17.json"
DEFAULT_OUT = "evidence/sample-reports/decision-report-2026-11-17.md"
DRY_RUN_FINGERPRINT = "dryrun-competition-paper-fingerprint"


def _start_index(dates: tuple[date, ...], start: date) -> int:
    return next(index for index, session in enumerate(dates) if session >= start)


def build_bundle(bars_path: str, news_path: str, fingerprint: str) -> ReportBundle:
    history = MarketHistory.from_file(bars_path)
    news = NewsArchive.from_file(news_path)
    latest = {
        strategy: latest_decision(history, news, strategy, fingerprint)
        for strategy in STRATEGIES
    }
    accepted = {
        strategy: find_accepted_example(history, news, strategy, fingerprint)
        for strategy in STRATEGIES
    }
    stale = {
        strategy: stale_quote_example(decision, fingerprint) if decision is not None else None
        for strategy, decision in accepted.items()
    }
    oversized = {
        strategy: oversized_example(decision, fingerprint) if decision is not None else None
        for strategy, decision in accepted.items()
    }
    control_rejections = []
    reference = accepted.get("momentum-v1") or next((item for item in accepted.values() if item), None)
    if reference is not None:
        writes_disabled = control_rejection_example(
            reference,
            fingerprint,
            "production control: order writes disabled",
            order_writes_enabled=False,
            first_order_approved=True,
        )
        approval_missing = control_rejection_example(
            reference,
            fingerprint,
            "first paper order without owner approval",
            order_writes_enabled=True,
            first_order_approved=False,
        )
        control_rejections.extend(item for item in (writes_disabled, approval_missing) if item is not None)

    dates = history.session_dates()
    full_start = 20
    news_coverage = [coverage for symbol in history.symbols if (coverage := news.coverage(symbol)) is not None]
    news_start_date = min(coverage[0].date() for coverage in news_coverage)
    news_start = _start_index(dates, news_start_date)

    evaluations = [
        replace(simulate_strategy(history, news, "momentum-v1", start_index=full_start), name="momentum-v1 (full fixture)"),
        replace(simulate_strategy(history, news, "momentum-v1", start_index=news_start), name="momentum-v1 (news window)"),
        replace(simulate_strategy(history, news, "news-catalyst-v1", start_index=news_start), name="news-catalyst-v1 (news window)"),
        replace(buy_and_hold(history, "SPY", start_index=full_start), name="SPY buy-and-hold (full fixture)"),
        replace(buy_and_hold(history, "SPY", start_index=news_start), name="SPY buy-and-hold (news window)"),
        replace(buy_and_hold(history, "QQQ", start_index=news_start), name="QQQ buy-and-hold (news window)"),
        replace(buy_and_hold(history, "IWM", start_index=news_start), name="IWM buy-and-hold (news window)"),
        replace(cash_baseline(history, start_index=news_start), name="cash (news window)"),
    ]

    if "COMPETITION_ACCOUNT_FINGERPRINT" in os.environ:
        fingerprint_note = (
            "locally configured competition fingerprint supplied through the environment "
            "(redacted); this is a dry-run identity check, not a broker snapshot."
        )
    else:
        fingerprint_note = (
            "synthetic local dry-run fingerprint; the account-lock rule is a fixture check, "
            "not broker evidence."
        )
    return ReportBundle(
        history=history,
        news=news,
        latest=latest,
        accepted=accepted,
        stale=stale,
        oversized=oversized,
        control_rejections=tuple(control_rejections),
        evaluations=tuple(evaluations),
        generated_at_utc=datetime.now(UTC),
        fingerprint_note=fingerprint_note,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.research.demo",
        description="Run the read-only research pipeline and deterministic dry-run risk gate.",
    )
    parser.add_argument("--bars", default=DEFAULT_BARS)
    parser.add_argument("--news", default=DEFAULT_NEWS)
    parser.add_argument(
        "--fingerprint",
        default=os.environ.get("COMPETITION_ACCOUNT_FINGERPRINT", DRY_RUN_FINGERPRINT),
    )
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    bundle = build_bundle(args.bars, args.news, args.fingerprint)
    report = render_report(bundle)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    print("PAPER / DRY RUN — no order was submitted")
    for strategy_version, decision in bundle.latest.items():
        outcome = "NO_TRADE" if decision.proposal is None else "HYPOTHETICAL_BUY"
        print(f"latest {strategy_version}: {outcome} — {decision.snapshot.regime_reason}")
        if decision.snapshot.no_trade_reason:
            print(f"  reason: {decision.snapshot.no_trade_reason}")
    for strategy_version, decision in bundle.accepted.items():
        if decision is None or decision.proposal is None or decision.risk_decision is None:
            print(f"accepted example {strategy_version}: none")
            continue
        print(
            f"accepted example {strategy_version}: {decision.snapshot.decision_time_utc.date()} "
            f"{decision.proposal.symbol} x {decision.proposal.requested_quantity} "
            f"→ {decision.risk_decision.decision.value}"
        )
    print("evaluation:")
    for result in bundle.evaluations:
        print(
            f"  {result.name}: total {result.total_return * 100:+.2f}% | "
            f"max drawdown {result.max_drawdown * 100:.2f}% | signals {result.signals}"
        )
    print(f"report written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
