from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.contracts import ProposalAction, TradeProposal
from app.research.data import UNIVERSE, MarketHistory, NewsArchive, NewsItem

REGIME_SYMBOL = "SPY"
SMA_WINDOW = 20
MOMENTUM_WINDOW = 5
NEWS_LOOKBACK = timedelta(hours=72)

_POSITIVE = re.compile(
    r"\b(?:rally|rallies|surge|surges|gain|gains|rise|rises|climb|climbs|record high|"
    r"inflow|inflows|upgrade|upgrades|beat|beats|strong|strength|growth|optimism|"
    r"rebound|rebounds|bullish|buy|outperform|outperforms|higher)\b|"
    r"上涨|大涨|攀升|走高|反弹|新高|创纪录|流入|看涨|买入|上调|强劲|增长|超预期|乐观|利好",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"\b(?:fall|falls|drop|drops|decline|declines|plunge|plunges|selloff|sell-off|"
    r"crisis|concern|concerns|risk|risks|downgrade|downgrades|miss|misses|weak|"
    r"weakness|outflow|outflows|pressure|bearish|sell|underperform|lower|correction)\b|"
    r"下跌|大跌|回落|走低|重挫|暴跌|新低|流出|看跌|卖出|下调|疲弱|下降|不及预期|悲观|利空|危机|风险",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    symbol: str
    close: Decimal
    sma20: Decimal
    return_5d: Decimal
    regime_ok: bool
    above_sma: bool
    news_count: int
    positive_news_count: int
    news_score: Decimal
    news_ids: tuple[str, ...]
    eligible: bool
    selected: bool
    reasons: tuple[str, ...]

    @property
    def signal_strength(self) -> Decimal:
        return self.return_5d


@dataclass(frozen=True)
class ResearchSnapshot:
    strategy_version: str
    decision_time_utc: datetime
    data_as_of_utc: datetime
    regime_ok: bool
    regime_reason: str
    candidates: tuple[Candidate, ...]
    selected_symbol: str | None
    no_trade_reason: str | None


def _sma(values: tuple[Decimal, ...], window: int) -> Decimal:
    return sum(values[-window:], Decimal("0")) / Decimal(window)


def _news_polarity(item: NewsItem) -> int:
    text = f"{item.title} {item.abstract}"
    positive = len(_POSITIVE.findall(text))
    negative = len(_NEGATIVE.findall(text))
    return (positive > negative) - (negative > positive)


def _news_score(items: tuple[NewsItem, ...], decision_time_utc: datetime) -> tuple[int, int, Decimal]:
    score = Decimal("0")
    positive = 0
    for item in items:
        polarity = _news_polarity(item)
        if polarity > 0:
            positive += 1
        age_hours = (decision_time_utc - item.published_at_utc).total_seconds() / 3600
        recency = Decimal(str(0.5 ** (age_hours / 24)))
        score += Decimal(polarity) * recency
    return len(items), positive, score


def _candidate_reasons(
    close: Decimal,
    sma20: Decimal,
    return_5d: Decimal,
    regime_ok: bool,
    news_count: int,
    news_score: Decimal,
    strategy_version: str,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not regime_ok:
        reasons.append("Broad-market regime negative (SPY below its 20-session SMA)")
    if close <= sma20:
        reasons.append(f"Close {close} is not above its 20-session SMA {sma20:.4f}")
    if return_5d <= 0:
        reasons.append(f"5-session return {return_5d:.4%} is not positive")
    if strategy_version == "news-catalyst-v1":
        if news_count == 0:
            reasons.append("No relevant news in the prior 72 hours")
        elif news_score <= 0:
            reasons.append(f"News catalyst is not positive (score {news_score:.4f})")
    return tuple(reasons)


def _assess_symbol(
    history: MarketHistory,
    news: NewsArchive,
    symbol: str,
    decision_time_utc: datetime,
    strategy_version: str,
    regime_ok: bool,
) -> Candidate | None:
    bars = history.bars_as_of(symbol, decision_time_utc)
    if len(bars) < SMA_WINDOW + 1:
        return None
    closes = tuple(bar.close for bar in bars)
    close = closes[-1]
    sma20 = _sma(closes, SMA_WINDOW)
    return_5d = closes[-1] / closes[-1 - MOMENTUM_WINDOW] - 1
    above_sma = close > sma20
    news_items = news.items_for(symbol, decision_time_utc, NEWS_LOOKBACK)
    news_count, positive_news_count, news_score = _news_score(news_items, decision_time_utc)
    reasons = _candidate_reasons(
        close,
        sma20,
        return_5d,
        regime_ok,
        news_count,
        news_score,
        strategy_version,
    )
    eligible = regime_ok and above_sma and return_5d > 0 and not reasons
    return Candidate(
        symbol=symbol,
        close=close,
        sma20=sma20,
        return_5d=return_5d,
        regime_ok=regime_ok,
        above_sma=above_sma,
        news_count=news_count,
        positive_news_count=positive_news_count,
        news_score=news_score,
        news_ids=tuple(item.evidence_id for item in news_items),
        eligible=eligible,
        selected=False,
        reasons=reasons,
    )


def screen(
    history: MarketHistory,
    news: NewsArchive,
    decision_time_utc: datetime,
    strategy_version: str = "momentum-v1",
) -> ResearchSnapshot:
    if strategy_version not in {"momentum-v1", "news-catalyst-v1"}:
        raise ValueError(f"unknown strategy {strategy_version!r}")
    regime_bars = history.bars_as_of(REGIME_SYMBOL, decision_time_utc)
    if len(regime_bars) < SMA_WINDOW + 1:
        return ResearchSnapshot(
            strategy_version=strategy_version,
            decision_time_utc=decision_time_utc,
            data_as_of_utc=decision_time_utc,
            regime_ok=False,
            regime_reason="insufficient SPY history for the 20-session regime filter",
            candidates=(),
            selected_symbol=None,
            no_trade_reason="Insufficient history; abstain",
        )
    spy_closes = tuple(bar.close for bar in regime_bars)
    spy_sma = _sma(spy_closes, SMA_WINDOW)
    regime_ok = spy_closes[-1] > spy_sma
    regime_reason = (
        f"SPY close {spy_closes[-1]} {'above' if regime_ok else 'below'} "
        f"20-session SMA {spy_sma:.4f}"
    )
    assessed = [
        candidate
        for candidate in (
            _assess_symbol(history, news, symbol, decision_time_utc, strategy_version, regime_ok)
            for symbol in UNIVERSE
        )
        if candidate is not None
    ]
    eligible = sorted(
        (candidate for candidate in assessed if candidate.eligible),
        key=lambda candidate: (-candidate.return_5d, candidate.symbol),
    )
    selected_symbol = eligible[0].symbol if eligible else None
    annotated = tuple(
        Candidate(
            symbol=candidate.symbol,
            close=candidate.close,
            sma20=candidate.sma20,
            return_5d=candidate.return_5d,
            regime_ok=candidate.regime_ok,
            above_sma=candidate.above_sma,
            news_count=candidate.news_count,
            positive_news_count=candidate.positive_news_count,
            news_score=candidate.news_score,
            news_ids=candidate.news_ids,
            eligible=candidate.eligible,
            selected=candidate.symbol == selected_symbol,
            reasons=(
                candidate.reasons
                + (
                    ("Selected: highest 5-session return among eligible candidates",)
                    if candidate.symbol == selected_symbol
                    else ("Eligible but ranked below the selected candidate",)
                    if candidate.eligible
                    else ()
                )
            ),
        )
        for candidate in assessed
    )
    if not regime_ok:
        no_trade_reason = "Broad-market regime filter is negative; abstain from new entries"
    elif selected_symbol is None:
        no_trade_reason = (
            "No candidate has a positive 5-session return above its 20-session SMA"
            if strategy_version == "momentum-v1"
            else "No price-momentum candidate has a positive news catalyst in the prior 72 hours"
        )
    else:
        no_trade_reason = None
    data_as_of = max(
        (bar.available_at_utc for symbol in UNIVERSE for bar in history.bars_as_of(symbol, decision_time_utc)),
        default=decision_time_utc,
    )
    return ResearchSnapshot(
        strategy_version=strategy_version,
        decision_time_utc=decision_time_utc,
        data_as_of_utc=data_as_of,
        regime_ok=regime_ok,
        regime_reason=regime_reason,
        candidates=annotated,
        selected_symbol=selected_symbol,
        no_trade_reason=no_trade_reason,
    )


def build_proposal(
    snapshot: ResearchSnapshot,
    history: MarketHistory,
    equity: Decimal,
    position_fraction: Decimal = Decimal("0.05"),
) -> TradeProposal | None:
    if snapshot.selected_symbol is None:
        return None
    candidate = next(item for item in snapshot.candidates if item.selected)
    quantity = int(equity * position_fraction / candidate.close)
    if quantity < 1:
        return None
    evidence = [f"bar:{candidate.symbol}:{bar.session_date:%Y%m%d}" for bar in history.bars_as_of(
        candidate.symbol, snapshot.decision_time_utc
    )[-SMA_WINDOW:]]
    regime_bar = history.bars_as_of(REGIME_SYMBOL, snapshot.decision_time_utc)[-1]
    evidence.append(regime_bar.evidence_id)
    evidence.extend(candidate.news_ids)
    news_text = (
        f" {candidate.positive_news_count} positive of {candidate.news_count} relevant headlines"
        f" (sentiment score {candidate.news_score:.4f})."
        if snapshot.strategy_version == "news-catalyst-v1"
        else ""
    )
    return TradeProposal(
        proposal_id=f"{snapshot.strategy_version}-{snapshot.decision_time_utc:%Y%m%d}-{candidate.symbol}",
        run_id=f"dryrun-{snapshot.decision_time_utc:%Y%m%dT%H%M%SZ}-{snapshot.strategy_version}",
        strategy_version=snapshot.strategy_version,
        decision_time_utc=snapshot.decision_time_utc,
        data_as_of_utc=snapshot.data_as_of_utc,
        symbol=candidate.symbol,
        action=ProposalAction.BUY,
        requested_quantity=quantity,
        thesis=(
            f"{candidate.symbol} closed at {candidate.close}, above its 20-session SMA "
            f"{candidate.sma20:.4f}, with a {candidate.return_5d:.4%} 5-session return. "
            f"{snapshot.regime_reason}.{news_text}"
        ),
        invalidation="Close below the 20-session SMA or a daily drawdown limit breach.",
        evidence_ids=tuple(evidence),
    )
