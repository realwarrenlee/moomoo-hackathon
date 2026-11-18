from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.research.data import MarketHistory, NewsArchive
from app.research.dryrun import DryRunDecision
from app.research.evaluate import BacktestResult


@dataclass(frozen=True)
class ReportBundle:
    history: MarketHistory
    news: NewsArchive
    latest: dict[str, DryRunDecision]
    accepted: dict[str, DryRunDecision | None]
    stale: dict[str, DryRunDecision | None]
    oversized: dict[str, DryRunDecision | None]
    control_rejections: tuple[DryRunDecision, ...]
    evaluations: tuple[BacktestResult, ...]
    generated_at_utc: datetime
    fingerprint_note: str


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _pct(value: Decimal | float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:+.{digits}f}%"


def _plain_pct(value: Decimal | float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.{digits}f}%"


def _ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _candidate_table(decision: DryRunDecision) -> str:
    lines = [
        "| Symbol | Close | 20-session SMA | 5-session return | Regime | News (72h) | News score | Outcome | Reasons |",
        "|---|---:|---:|---:|---|---:|---:|---|---|",
    ]
    for candidate in decision.snapshot.candidates:
        outcome = "SELECTED" if candidate.selected else "SKIP"
        reasons = "; ".join(candidate.reasons) or "eligible"
        lines.append(
            f"| {candidate.symbol} | {_money(candidate.close)} | {_money(candidate.sma20)} | "
            f"{_pct(candidate.return_5d)} | {'positive' if candidate.regime_ok else 'negative'} | "
            f"{candidate.news_count} | {candidate.news_score:.3f} | {outcome} | {reasons} |"
        )
    return "\n".join(lines)


def _risk_row(decision: DryRunDecision) -> str:
    rules = ", ".join(rule.rule_id for rule in decision.risk_decision.reasons) if decision.risk_decision else "n/a"
    outcome = decision.risk_decision.decision.value if decision.risk_decision else "NO_PROPOSAL"
    quantity = decision.proposal.requested_quantity if decision.proposal else 0
    symbol = decision.proposal.symbol if decision.proposal else "-"
    return f"| {decision.scenario} | {symbol} | {quantity} | {outcome} | {rules or 'none'} |"


def _evaluation_table(results: tuple[BacktestResult, ...]) -> str:
    lines = [
        "| Strategy / baseline | Period | Signals | Closed trades | Total return | CAGR | Ann. vol | Sharpe | Max drawdown | Exposure | Win rate | Avg trade |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result.name} | {result.start_date} to {result.end_date} | {result.signals} | "
            f"{sum(1 for trade in result.trades if trade.exit_date is not None)} | "
            f"{_pct(result.total_return)} | {_pct(result.cagr)} | {_plain_pct(result.annualized_volatility)} | "
            f"{_ratio(result.sharpe)} | {_plain_pct(result.max_drawdown)} | {_plain_pct(result.exposure_pct)} | "
            f"{_plain_pct(result.win_rate)} | {_pct(result.average_trade_return)} |"
        )
    return "\n".join(lines)


def render_report(bundle: ReportBundle) -> str:
    history = bundle.history
    news = bundle.news
    last_session = history.last_completed_session()
    news_coverage = ", ".join(
        f"{symbol} {coverage[0].date()} to {coverage[1].date()}"
        for symbol in history.symbols
        if (coverage := news.coverage(symbol)) is not None
    )
    sections: list[str] = [
        "# MooTrade decision report — PAPER / DRY RUN",
        "",
        "> **No order was submitted. Order writes remain disabled.** This report is a deterministic "
        "research and risk-policy demonstration, not broker execution evidence and not a claim of "
        "actual investment returns.",
        "",
        f"Generated: `{bundle.generated_at_utc.isoformat().replace('+00:00', 'Z')}`  ",
        f"Decision input: last fully completed session `{last_session}` at the conservative "
        "`21:00 UTC` close timestamp.  ",
        f"Account identity: {bundle.fingerprint_note}",
        "",
        "## 1. Data provenance and safety state",
        "",
        f"- **Market bars:** `{history.source.get('provider', 'unknown')}` via "
        f"`{history.source.get('tool', 'unknown')}`, {len(history.bars('SPY'))} daily bars per symbol, "
        f"{history.bars('SPY')[0].session_date} to {last_session}, forward-adjusted (`autype=1`). "
        f"Source fetch: `{history.source.get('fetched_at_utc', 'unknown')}`.",
        f"- **News metadata:** `{news.source.get('provider', 'unknown')}` via "
        f"`{news.source.get('tool', 'unknown')}`; {len(news.items)} relevant headlines with provider "
        f"publish timestamps. Coverage: {news_coverage}.",
        "- **Account values used for dry-run:** `$100,000` cash/equity and zero positions/orders, "
        "consistent with the read-only Moomoo session verified on 17 November 2026. The dry-run "
        "`AccountSnapshot` is a flat hypothetical snapshot timestamped at the decision time; it is "
        "not a broker snapshot at that historical timestamp.",
        "- **Actual execution controls:** `ORDER_WRITES_ENABLED=false`; no kill switch or circuit "
        "breaker was changed; no first-order approval was consumed. The approval examples use an "
        "ephemeral dry-run `ControlState` only so the deterministic gate can be exercised.",
        "- **No broker call:** the research path calls `RiskGate.evaluate` directly. It does not call "
        "`TradingService.execute`, the mock broker or any Moomoo order tool.",
        "",
        "## 2. Strategy rules evaluated",
        "",
        "### `momentum-v1` (frozen from `docs/strategy-and-risk.md`)",
        "",
        "- Broad-market regime: `SPY` completed close above its trailing 20-session SMA.",
        "- Candidate: close above its own 20-session SMA and 5-session return positive.",
        "- Selection: highest 5-session return; ticker alphabetical tie-break.",
        "- Exit assumption for the research simulation: completed close below the held ETF's 20-session SMA.",
        "- Warmup: 21 completed sessions; otherwise abstain.",
        "",
        "### `news-catalyst-v1`",
        "",
        "- Same regime, price-trend and selection rules as `momentum-v1`.",
        "- Additional entry filter: at least one relevant headline published in the prior 72 hours and a "
        "positive recency-weighted headline sentiment score. The score is a transparent keyword "
        "lexicon over title and abstract, not an LLM judgement.",
        "- Headlines are used only when `publish_time <= decision_time`.",
        "",
        "## 3. Latest completed-session decision",
        "",
    ]
    for strategy_version, decision in bundle.latest.items():
        sections.extend(
            [
                f"### `{strategy_version}` — "
                f"{'NO TRADE' if decision.proposal is None else 'HYPOTHETICAL BUY'}",
                "",
                f"Regime: {decision.snapshot.regime_reason}.  ",
                f"Outcome reason: {decision.snapshot.no_trade_reason or 'selected candidate generated a proposal.'}",
                "",
                _candidate_table(decision),
                "",
            ]
        )
        if decision.proposal is not None and decision.risk_decision is not None:
            sections.extend(
                [
                    f"Proposal: `{decision.proposal.symbol}` x {decision.proposal.requested_quantity}, "
                    f"risk decision `{decision.risk_decision.decision.value}`, "
                    f"approved quantity `{decision.risk_decision.approved_quantity}`.",
                    "",
                ]
            )
    sections.extend(
        [
            "The latest session is a deliberate **abstention** for both strategies: the broad-market "
            "regime filter is negative, so no eligible candidate exists. The gate is not asked to "
            "approve a no-trade proposal; the absence of a proposal is recorded as a no-trade decision.",
            "",
            "## 4. Accepted hypothetical proposals",
            "",
            "These examples use a historical decision time and the same frozen rules. They show that a "
            "signal can pass the existing deterministic gate. **No order was placed.**",
            "",
            "| Strategy | Decision time | Symbol | Qty | Quote | Notional | Risk | Approved qty | Rules |",
            "|---|---|---|---:|---:|---:|---|---:|---|",
        ]
    )
    for strategy_version, decision in bundle.accepted.items():
        if decision is None or decision.proposal is None or decision.quote is None or decision.risk_decision is None:
            sections.append(f"| {strategy_version} | no accepted example | - | - | - | - | - | - | - |")
            continue
        notional = decision.quote.price * decision.proposal.requested_quantity
        rules = ", ".join(rule.rule_id for rule in decision.risk_decision.reasons) or "none"
        sections.append(
            f"| {strategy_version} | {decision.snapshot.decision_time_utc.isoformat()} | "
            f"{decision.proposal.symbol} | {decision.proposal.requested_quantity} | "
            f"{_money(decision.quote.price)} | {_money(notional)} | "
            f"{decision.risk_decision.decision.value} | {decision.risk_decision.approved_quantity} | {rules} |"
        )
    sections.extend(["", "**Thesis and invalidation for the accepted examples**", ""])
    for strategy_version, decision in bundle.accepted.items():
        if decision is None or decision.proposal is None:
            continue
        sections.extend(
            [
                f"- `{strategy_version}`: {decision.proposal.thesis}",
                f"  Invalidation: {decision.proposal.invalidation}",
            ]
        )
    sections.extend(
        [
            "",
            "## 5. Rejected or blocked proposals",
            "",
            "| Scenario | Symbol | Qty | Risk | Rules |",
            "|---|---|---:|---|---|",
        ]
    )
    for decision in bundle.stale.values():
        if decision is not None:
            sections.append(_risk_row(decision))
    for decision in bundle.oversized.values():
        if decision is not None:
            sections.append(_risk_row(decision))
    for decision in bundle.control_rejections:
        sections.append(_risk_row(decision))
    sections.extend(
        [
            "",
            "The stale-quote case fails `R007`; the 20%-of-equity case fails `R004`; disabled writes fail "
            "`R010`; a missing first-order approval fails `R014`. No rejection reaches a broker method.",
            "",
            "## 6. Historical strategy evaluation",
            "",
            "Research simulation only: 100% long/cash, fractional shares, 2 bps cost per side, no "
            "leverage or shorting, and no application of the 10%/30% live exposure caps. This is a "
            "signal-quality study, not the return of the risk-gated paper account.",
            "",
            _evaluation_table(bundle.evaluations),
            "",
            "**No-look-ahead convention:** a signal is computed only from bars whose conservative "
            "21:00 UTC availability timestamp is at or before the decision time. Orders are assumed "
            "to execute at the next session's open; exits also occur at the next open after a close "
            "below the 20-session SMA. News is filtered by provider `publish_time <= decision_time`. "
            "Future bars are never used to construct a signal.",
            "",
            "## 7. Limitations",
            "",
            "- The sample is about 17 months of daily bars for three ETFs and one market regime. It "
            "cannot establish durable alpha or statistical significance.",
            "- The news archive is sparse and asymmetric: QQQ headlines begin only on 2026-10-06, while "
            "SPY and IWM have earlier coverage. Headlines are not a complete news feed, and the keyword "
            "sentiment score is a crude proxy.",
            "- The simulation ignores dividends, taxes, borrow, corporate actions beyond the provider's "
            "forward adjustment, market impact, queue position, partial fills and any Moomoo-specific "
            "execution constraints.",
            "- The backtest enters at the next open but the live system would require a fresh quote and "
            "account snapshot; the gate's 300-second quote and 60-second account freshness rules still "
            "apply.",
            "- `news-catalyst-v1` was defined before this evaluation, but it is a first draft. No "
            "parameter search or retrofitting was performed.",
            "",
            "## 8. Reproduce",
            "",
            "From the repository root, with the local fingerprint supplied through the environment "
            "(never printed):",
            "",
            "```bash",
            ".venv/Scripts/python -m app.research.demo \\",
            "  --bars backend/tests/fixtures/moomoo_daily_bars_2026-11-16.json \\",
            "  --news backend/tests/fixtures/moomoo_news_2026-11-17.json \\",
            "  --out evidence/sample-reports/decision-report-2026-11-17.md",
            "```",
            "",
            "If `COMPETITION_ACCOUNT_FINGERPRINT` is not set, the demo uses a clearly labelled local "
            "dry-run fingerprint; the account-lock rule is then a fixture check, not broker evidence.",
            "",
        ]
    )
    return "\n".join(sections)
