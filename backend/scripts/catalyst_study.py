from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.research.data import DailyBar, MarketHistory, NewsArchive, SESSION_CLOSE_UTC
from app.research.evaluate import COST_BPS, INITIAL_EQUITY
from app.research.strategy import screen

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence" / "research" / "catalyst-momentum-2026-11-17"
SEC_DIR = Path(r"C:\Users\Warren\.qoder\tmp\C--Users-Warren-Downloads-qoder-trading-challenge\tool-outputs\session-d3d06659-71c5-456b-b940-a1b196ff627d")
MOOMOO_DIR = Path(r"C:\Users\Warren\AppData\Local\Temp\qoder-mcp-outputs")
UNIVERSE = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "JPM", "XOM", "LLY", "COST")
CIKS = {
    "AAPL": "0000320193", "MSFT": "0000789019", "NVDA": "0001045810",
    "AMZN": "0001018724", "GOOGL": "0001652044", "META": "0001326801",
    "AVGO": "0001730168", "TSLA": "0001318605", "JPM": "0000019617",
    "XOM": "0000034088", "LLY": "0000059478", "COST": "0000909832",
}
SEC_FILES = {
    "AAPL": ["webfetch-56a09b29-a2b5-49b8-92ae-f4540a12786c.md"],
    "MSFT": ["webfetch-f9ee4644-fa72-4ef1-a833-c9014ced2f32.md"],
    "NVDA": ["webfetch-a5ae6e32-15de-4874-bf58-4caa02fce5f7.md"],
    "AMZN": ["webfetch-70374b43-f492-4cd2-a77e-18f842598820.md"],
    "GOOGL": ["webfetch-285489ec-9e06-49ff-a7c6-9b68fd3ce629.md"],
    "META": ["webfetch-740e685a-a6b5-44b3-8e28-fc4191f1af66.md"],
    "AVGO": ["webfetch-a19b800f-66ef-429b-b826-7c4633aab8b5.md"],
    "TSLA": ["webfetch-752b592b-2f36-49f3-844f-bcb061434bf9.md"],
    "JPM": [
        "webfetch-310af6fe-f06d-4c8e-b125-818fc5a64197.md",
        "webfetch-1aec301f-44a5-4c6c-8aeb-c8065c87f7fe.md",
        "webfetch-570f69a8-f9c5-489b-907f-a600f6ddc50d.md",
        "webfetch-6bb38ff4-bd84-48cd-8451-338ca869181e.md",
        "webfetch-4085fed0-6b0c-406f-aae4-ffae73692fb6.md",
        "webfetch-caab13ac-19d7-4f5c-9c67-23d1c80d1483.md",
        "webfetch-593dfbf7-dea3-4088-8a63-4970533def84.md",
    ],
    "XOM": ["webfetch-cdb69bf4-04f9-472b-ac2a-655ba2026214.md"],
    "LLY": ["webfetch-bc383db9-9d43-4ee5-8aed-b5fc17746593.md"],
    "COST": ["webfetch-ac5707a2-c455-4730-b4ba-168ab9686a8c.md"],
}
MOOMOO_FILES = {
    "AAPL": "moomoo_quote_cur_kline_4900cfeb2529.txt",
    "MSFT": "moomoo_quote_cur_kline_89e9fb72007c.txt",
    "NVDA": "moomoo_quote_cur_kline_d56beebbd098.txt",
    "AMZN": "moomoo_quote_cur_kline_154b0184a3fe.txt",
    "GOOGL": "moomoo_quote_cur_kline_43a80a397d60.txt",
    "META": "moomoo_quote_cur_kline_feebd3acfc22.txt",
    "AVGO": "moomoo_quote_cur_kline_669c715f30e3.txt",
    "TSLA": "moomoo_quote_cur_kline_9786a98b08f2.txt",
    "JPM": "moomoo_quote_cur_kline_e42348094220.txt",
    "XOM": "moomoo_quote_cur_kline_d3b9f9c2621f.txt",
    "LLY": "moomoo_quote_cur_kline_5695c177838c.txt",
    "COST": "moomoo_quote_cur_kline_fed4e80291de.txt",
}
D = Decimal
ONE = D("1")
ZERO = D("0")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_accepted(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("acceptance timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def close_time(session_date: date) -> datetime:
    return datetime.combine(session_date, SESSION_CLOSE_UTC, tzinfo=timezone.utc)


def normalize_sec_events() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {}
    excluded: list[dict[str, str]] = []
    lower = datetime(2025, 5, 20, tzinfo=timezone.utc)
    upper = close_time(date(2026, 11, 16))
    for symbol in UNIVERSE:
        filing_dates: list[str] = []
        source_records: list[dict[str, str]] = []
        original_count = 0
        amendment_count = 0
        seen: set[str] = set()
        for filename in SEC_FILES[symbol]:
            path = SEC_DIR / filename
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "cik" in payload and payload["cik"] != CIKS[symbol]:
                raise ValueError(f"CIK mismatch for {symbol}")
            table = payload["filings"]["recent"] if "filings" in payload else payload
            digest = sha256(path)
            source_records.append({"file": filename, "sha256": digest, "rows": len(table["form"])})
            for index, form in enumerate(table["form"]):
                filing_dates.append(table["filingDate"][index])
                items = [item.strip() for item in table["items"][index].split(",") if item.strip()]
                if form not in {"8-K", "8-K/A"} or "2.02" not in items:
                    continue
                accession = table["accessionNumber"][index]
                accepted_raw = table["acceptanceDateTime"][index]
                if not accepted_raw:
                    excluded.append({"symbol": symbol, "accession": accession, "reason": "missing acceptanceDateTime"})
                    continue
                try:
                    accepted = parse_accepted(accepted_raw)
                except ValueError:
                    excluded.append({"symbol": symbol, "accession": accession, "reason": "ambiguous acceptanceDateTime"})
                    continue
                if not lower <= accepted <= upper or accession in seen:
                    continue
                seen.add(accession)
                event = {
                    "symbol": symbol,
                    "cik": CIKS[symbol],
                    "accession": accession,
                    "form": form,
                    "items": items,
                    "accepted_at_utc": accepted.isoformat().replace("+00:00", "Z"),
                    "filing_date": table["filingDate"][index],
                    "report_date": table["reportDate"][index],
                    "primary_document": table["primaryDocument"][index],
                    "source_file": filename,
                    "source_sha256": digest,
                }
                events.append(event)
                if form == "8-K":
                    original_count += 1
                else:
                    amendment_count += 1
        coverage[symbol] = {
            "cik": CIKS[symbol],
            "earliest_filing_date_observed": min(filing_dates),
            "latest_filing_date_observed": max(filing_dates),
            "original_item_2_02_events": original_count,
            "item_2_02_amendments": amendment_count,
            "sources": source_records,
        }
        if min(filing_dates) > "2025-05-20":
            raise ValueError(f"SEC coverage gap for {symbol}: starts {min(filing_dates)}")
    events.sort(key=lambda event: (event["accepted_at_utc"], event["symbol"], event["accession"]))
    return events, {"coverage": coverage, "excluded_events": excluded}


def validate_bar(bar: DailyBar) -> None:
    values = (bar.open, bar.high, bar.low, bar.close)
    if any(value <= 0 for value in values) or bar.volume < 0:
        raise ValueError(f"invalid OHLCV for {bar.symbol} {bar.session_date}")
    if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close, bar.high):
        raise ValueError(f"inconsistent OHLC for {bar.symbol} {bar.session_date}")


def normalize_prices() -> tuple[MarketHistory, dict[str, Any]]:
    bars_by_symbol: dict[str, tuple[DailyBar, ...]] = {}
    sources: dict[str, Any] = {}
    for symbol, filename in MOOMOO_FILES.items():
        path = MOOMOO_DIR / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        bars: list[DailyBar] = []
        seen: set[date] = set()
        for row in payload["data"]["kline_list"]:
            session_date = datetime.strptime(str(row["date"]), "%Y%m%d").date()
            if session_date in seen:
                raise ValueError(f"duplicate {symbol} {session_date}")
            seen.add(session_date)
            bar = DailyBar(
                symbol=symbol,
                session_date=session_date,
                open=D(str(row["open_price"])),
                high=D(str(row["high_price"])),
                low=D(str(row["low_price"])),
                close=D(str(row["close_price"])),
                volume=D(str(row["volume"])),
                available_at_utc=close_time(session_date),
            )
            validate_bar(bar)
            bars.append(bar)
        bars.sort(key=lambda bar: bar.session_date)
        bars_by_symbol[symbol] = tuple(bars)
        sources[symbol] = {
            "provider": "Moomoo MCP quote_cur_kline",
            "parameters": {"num": 370, "ktype": 2, "autype": 1},
            "file": filename,
            "sha256": sha256(path),
            "rows": len(bars),
            "first_session": bars[0].session_date.isoformat(),
            "last_session": bars[-1].session_date.isoformat(),
        }
    etf_path = ROOT / "backend" / "tests" / "fixtures" / "moomoo_daily_bars_2026-11-16.json"
    etf_history = MarketHistory.from_file(etf_path)
    for symbol in ("SPY", "QQQ", "IWM"):
        bars_by_symbol[symbol] = etf_history.bars(symbol)
        for bar in bars_by_symbol[symbol]:
            validate_bar(bar)
        sources[symbol] = {
            "provider": "Moomoo MCP quote_cur_kline",
            "parameters": {"num": 370, "ktype": 2, "autype": 1, "extended_time": 0},
            "file": etf_path.name,
            "sha256": sha256(etf_path),
            "rows": len(bars_by_symbol[symbol]),
            "first_session": bars_by_symbol[symbol][0].session_date.isoformat(),
            "last_session": bars_by_symbol[symbol][-1].session_date.isoformat(),
        }
    common = set(bars_by_symbol["SPY"][index].session_date for index in range(len(bars_by_symbol["SPY"])))
    for symbol, bars in bars_by_symbol.items():
        common.intersection_update(bar.session_date for bar in bars)
    expected = {bar.session_date for bar in bars_by_symbol["SPY"]}
    missing = {symbol: sorted(expected - {bar.session_date for bar in bars}) for symbol, bars in bars_by_symbol.items()}
    missing = {symbol: [day.isoformat() for day in days] for symbol, days in missing.items() if days}
    if missing or len(common) != 370:
        raise ValueError(f"common-session validation failed: {missing}, common={len(common)}")
    payload = {
        "schema_version": "1",
        "source": {"study": "sec-earnings-relative-momentum-v1", "sources": sources, "common_sessions": len(common)},
        "symbols": {
            symbol: [
                {
                    "date": bar.session_date.strftime("%Y%m%d"),
                    "open": str(bar.open), "high": str(bar.high),
                    "low": str(bar.low), "close": str(bar.close),
                    "volume": str(bar.volume),
                }
                for bar in bars
            ]
            for symbol, bars in bars_by_symbol.items()
        },
    }
    path = OUT / "normalized-prices.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return MarketHistory.from_file(path), {"sources": sources, "common_sessions": len(common), "missing_sessions": missing}


@dataclass
class Position:
    symbol: str
    accession: str
    shares: Decimal
    entry_date: date
    entry_decision_utc: datetime
    entry_debit: Decimal
    sessions_held: int
    trade_index: int


@dataclass
class WindowResult:
    metrics: dict[str, Any]
    equity: list[tuple[date, Decimal]]
    trades: list[dict[str, Any]]


def sma(closes: list[Decimal], index: int, window: int = 20) -> Decimal:
    if index + 1 < window:
        raise ValueError("insufficient SMA warmup")
    return sum(closes[index - window + 1:index + 1], ZERO) / D(window)


def make_metrics(
    equity: list[tuple[date, Decimal]],
    exposures: list[Decimal],
    trades: list[dict[str, Any]],
    gross_notional: Decimal,
    costs: Decimal,
) -> dict[str, Any]:
    values = [value for _, value in equity]
    daily_values = values[1:]
    returns = [float(values[index] / values[index - 1] - ONE) for index in range(1, len(values))]
    peak = values[0]
    max_drawdown = ZERO
    for value in values:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, ONE - value / peak)
    closed = [trade for trade in trades if trade["exit_date"] is not None]
    average_equity = sum(daily_values, ZERO) / D(len(daily_values))
    nonzero_volatility = len(returns) >= 60 and statistics.pstdev(returns) > 0
    sharpe = None
    if nonzero_volatility:
        sharpe = statistics.mean(returns) / statistics.pstdev(returns) * math.sqrt(252)
    return {
        "start_session": equity[1][0].isoformat(),
        "end_session": equity[-1][0].isoformat(),
        "sessions": len(daily_values),
        "initial_equity": float(values[0]),
        "final_equity": float(values[-1]),
        "total_return_pct": float((values[-1] / values[0] - ONE) * 100),
        "average_exposure_pct": float(sum(exposures, ZERO) / D(len(exposures)) * 100),
        "maximum_exposure_pct": float(max(exposures) * 100),
        "turnover_gross_notional_over_average_equity": float(gross_notional / average_equity),
        "modelled_costs_usd": float(costs),
        "max_drawdown_pct": float(max_drawdown * 100),
        "trade_count": len(trades),
        "closed_trade_count": len(closed),
        "open_trade_count": len(trades) - len(closed),
        "win_rate_pct": float(D(sum(1 for trade in closed if trade["net_pnl"] > 0)) / D(len(closed)) * 100) if closed else None,
        "average_closed_trade_pnl_usd": float(sum((trade["net_pnl"] for trade in closed), ZERO) / D(len(closed))) if closed else None,
        "sharpe_descriptive": sharpe,
        "sharpe_statistically_meaningful": len(closed) >= 30 and sharpe is not None,
    }


def simulate_catalyst(history: MarketHistory, events: list[dict[str, Any]], start: date, end: date) -> WindowResult:
    dates = [bar.session_date for bar in history.bars("SPY")]
    start_index = dates.index(start)
    end_index = dates.index(end)
    bars = {symbol: {bar.session_date: bar for bar in history.bars(symbol)} for symbol in history.symbols}
    closes = {symbol: [bars[symbol][day].close for day in dates] for symbol in bars}
    originals = [event for event in events if event["form"] == "8-K" and event["symbol"] in UNIVERSE]
    amendments = [event for event in events if event["form"] == "8-K/A" and event["symbol"] in UNIVERSE]
    cash = INITIAL_EQUITY
    positions: dict[str, Position] = {}
    used_accessions: set[str] = set()
    trades: list[dict[str, Any]] = []
    equity: list[tuple[date, Decimal]] = [(dates[start_index - 1], INITIAL_EQUITY)]
    exposures: list[Decimal] = []
    gross_notional = ZERO
    costs = ZERO

    def orders_at(index: int, current_positions: dict[str, Position]) -> tuple[dict[str, str], list[dict[str, Any]]]:
        decision = close_time(dates[index])
        exits: dict[str, str] = {}
        for symbol, position in current_positions.items():
            known_amendment = any(
                event["symbol"] == symbol
                and position.entry_decision_utc < parse_accepted(event["accepted_at_utc"]) <= decision
                for event in amendments
            )
            if known_amendment:
                exits[symbol] = "amendment"
            elif position.sessions_held >= 10:
                exits[symbol] = "maximum_hold"
            elif closes[symbol][index] <= sma(closes[symbol], index) or closes["SPY"][index] <= sma(closes["SPY"], index):
                exits[symbol] = "trend_failure"
        spy_return = closes["SPY"][index] / closes["SPY"][index - 5] - ONE
        candidates: list[dict[str, Any]] = []
        if closes["SPY"][index] > sma(closes["SPY"], index):
            for event in originals:
                symbol = event["symbol"]
                accepted = parse_accepted(event["accepted_at_utc"])
                if event["accession"] in used_accessions or symbol in current_positions:
                    continue
                if not close_time(dates[index - 5]) < accepted <= decision:
                    continue
                if any(
                    amendment["symbol"] == symbol
                    and accepted < parse_accepted(amendment["accepted_at_utc"]) <= decision
                    for amendment in amendments
                ):
                    continue
                stock_return = closes[symbol][index] / closes[symbol][index - 5] - ONE
                if stock_return <= 0 or stock_return <= spy_return or closes[symbol][index] <= sma(closes[symbol], index):
                    continue
                candidates.append({"event": event, "excess_return": stock_return - spy_return, "decision_equity": equity[-1][1]})
        candidates.sort(key=lambda candidate: (-candidate["excess_return"], candidate["event"]["symbol"], candidate["event"]["accession"]))
        return exits, candidates

    pending_exits, pending_entries = orders_at(start_index - 1, positions)
    for index in range(start_index, end_index + 1):
        day = dates[index]
        exited_today: set[str] = set()
        for symbol, reason in sorted(pending_exits.items()):
            position = positions.pop(symbol)
            raw_open = bars[symbol][day].open
            raw_notional = position.shares * raw_open
            exit_cost = raw_notional * COST_BPS / D("10000")
            proceeds = raw_notional - exit_cost
            cash += proceeds
            gross_notional += raw_notional
            costs += exit_cost
            trade = trades[position.trade_index]
            trade.update({
                "exit_date": day.isoformat(), "exit_reason": reason,
                "exit_raw_open": float(raw_open), "exit_cost": float(exit_cost),
                "net_pnl": proceeds - position.entry_debit,
            })
            exited_today.add(symbol)
        for candidate in pending_entries:
            event = candidate["event"]
            symbol = event["symbol"]
            if len(positions) >= 3 or symbol in positions or symbol in exited_today or event["accession"] in used_accessions:
                continue
            target = candidate["decision_equity"] * D("0.10")
            raw_open = bars[symbol][day].open
            execution_price = raw_open * (ONE + COST_BPS / D("10000"))
            shares = target / raw_open
            debit = shares * execution_price
            if debit > cash:
                continue
            entry_cost = target * COST_BPS / D("10000")
            cash -= debit
            gross_notional += target
            costs += entry_cost
            trade_index = len(trades)
            trades.append({
                "symbol": symbol, "accession": event["accession"],
                "signal_date": dates[index - 1].isoformat(), "entry_date": day.isoformat(),
                "entry_raw_open": float(raw_open), "shares": float(shares),
                "entry_raw_notional": float(target), "entry_cost": float(entry_cost),
                "exit_date": None, "exit_reason": None, "exit_raw_open": None,
                "exit_cost": None, "net_pnl": None,
            })
            positions[symbol] = Position(symbol, event["accession"], shares, day, close_time(dates[index - 1]), debit, 0, trade_index)
            used_accessions.add(event["accession"])
        market_value = ZERO
        for position in positions.values():
            position.sessions_held += 1
            market_value += position.shares * closes[position.symbol][index]
        current_equity = cash + market_value
        equity.append((day, current_equity))
        exposures.append(market_value / current_equity if current_equity else ZERO)
        if index < end_index:
            pending_exits, pending_entries = orders_at(index, positions)
    for position in positions.values():
        trade = trades[position.trade_index]
        trade["net_pnl"] = position.shares * closes[position.symbol][end_index] - position.entry_debit
    return WindowResult(make_metrics(equity, exposures, trades, gross_notional, costs), equity, trades)


def simulate_buy_and_hold(history: MarketHistory, symbol: str, start: date, end: date) -> WindowResult:
    dates = [bar.session_date for bar in history.bars("SPY")]
    start_index, end_index = dates.index(start), dates.index(end)
    bars = {bar.session_date: bar for bar in history.bars(symbol)}
    raw_open = bars[start].open
    execution_price = raw_open * (ONE + COST_BPS / D("10000"))
    shares = INITIAL_EQUITY / execution_price
    cash = INITIAL_EQUITY - shares * execution_price
    cost = shares * raw_open * COST_BPS / D("10000")
    equity = [(dates[start_index - 1], INITIAL_EQUITY)]
    exposures: list[Decimal] = []
    for index in range(start_index, end_index + 1):
        day = dates[index]
        value = cash + shares * bars[day].close
        equity.append((day, value))
        exposures.append(shares * bars[day].close / value)
    trades = [{
        "symbol": symbol, "accession": None, "signal_date": dates[start_index - 1].isoformat(),
        "entry_date": start.isoformat(), "entry_raw_open": float(raw_open), "shares": float(shares),
        "entry_raw_notional": float(shares * raw_open), "entry_cost": float(cost),
        "exit_date": None, "exit_reason": None, "exit_raw_open": None, "exit_cost": None,
        "net_pnl": shares * bars[end].close - INITIAL_EQUITY,
    }]
    return WindowResult(make_metrics(equity, exposures, trades, shares * raw_open, cost), equity, trades)


def simulate_cash(history: MarketHistory, start: date, end: date) -> WindowResult:
    dates = [bar.session_date for bar in history.bars("SPY")]
    selected = dates[dates.index(start):dates.index(end) + 1]
    equity = [(dates[dates.index(start) - 1], INITIAL_EQUITY)] + [(day, INITIAL_EQUITY) for day in selected]
    return WindowResult(make_metrics(equity, [ZERO] * len(selected), [], ZERO, ZERO), equity, [])


def simulate_legacy(history: MarketHistory, news: NewsArchive, version: str, start: date, end: date) -> WindowResult:
    dates = [bar.session_date for bar in history.bars("SPY")]
    start_index, end_index = dates.index(start), dates.index(end)
    bars = {symbol: {bar.session_date: bar for bar in history.bars(symbol)} for symbol in ("SPY", "QQQ", "IWM")}
    cash = INITIAL_EQUITY
    position: Position | None = None
    trades: list[dict[str, Any]] = []
    equity: list[tuple[date, Decimal]] = [(dates[start_index - 1], INITIAL_EQUITY)]
    exposures: list[Decimal] = []
    gross_notional = ZERO
    costs = ZERO
    candidate = screen(history, news, close_time(dates[start_index - 1]), version)
    pending_symbol = candidate.selected_symbol
    pending_exit = False
    for index in range(start_index, end_index + 1):
        day = dates[index]
        if pending_exit and position is not None:
            raw_open = bars[position.symbol][day].open
            raw_notional = position.shares * raw_open
            exit_cost = raw_notional * COST_BPS / D("10000")
            proceeds = raw_notional - exit_cost
            cash += proceeds
            gross_notional += raw_notional
            costs += exit_cost
            trades[position.trade_index].update({
                "exit_date": day.isoformat(), "exit_reason": "trend_failure",
                "exit_raw_open": float(raw_open), "exit_cost": float(exit_cost),
                "net_pnl": proceeds - position.entry_debit,
            })
            position = None
            pending_exit = False
        if pending_symbol is not None and position is None:
            raw_open = bars[pending_symbol][day].open
            execution_price = raw_open * (ONE + COST_BPS / D("10000"))
            shares = cash / execution_price
            raw_notional = shares * raw_open
            entry_cost = raw_notional * COST_BPS / D("10000")
            debit = shares * execution_price
            trade_index = len(trades)
            trades.append({
                "symbol": pending_symbol, "accession": None, "signal_date": dates[index - 1].isoformat(),
                "entry_date": day.isoformat(), "entry_raw_open": float(raw_open), "shares": float(shares),
                "entry_raw_notional": float(raw_notional), "entry_cost": float(entry_cost),
                "exit_date": None, "exit_reason": None, "exit_raw_open": None, "exit_cost": None, "net_pnl": None,
            })
            position = Position(pending_symbol, "", shares, day, close_time(dates[index - 1]), debit, 0, trade_index)
            cash -= debit
            gross_notional += raw_notional
            costs += entry_cost
            pending_symbol = None
        if position is None:
            market_value = ZERO
        else:
            position.sessions_held += 1
            market_value = position.shares * bars[position.symbol][day].close
        current_equity = cash + market_value
        equity.append((day, current_equity))
        exposures.append(market_value / current_equity)
        if index < end_index:
            if position is not None:
                recent = history.bars_as_of(position.symbol, close_time(day))
                pending_exit = recent[-1].close <= sum((bar.close for bar in recent[-20:]), ZERO) / D("20")
            else:
                candidate = screen(history, news, close_time(day), version)
                pending_symbol = candidate.selected_symbol
    if position is not None:
        trades[position.trade_index]["net_pnl"] = position.shares * bars[position.symbol][end].close - position.entry_debit
    return WindowResult(make_metrics(equity, exposures, trades, gross_notional, costs), equity, trades)


def write_window(name: str, results: dict[str, WindowResult]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for label, result in results.items():
        metrics[label] = result.metrics
        stem = f"{name}-{label}"
        with (OUT / f"{stem}-equity.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["session_date", "equity_usd"])
            writer.writerows((day.isoformat(), str(value)) for day, value in result.equity)
        with (OUT / f"{stem}-trades.csv").open("w", newline="", encoding="utf-8") as handle:
            fields = ["symbol", "accession", "signal_date", "entry_date", "entry_raw_open", "shares", "entry_raw_notional", "entry_cost", "exit_date", "exit_reason", "exit_raw_open", "exit_cost", "net_pnl"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(result.trades)
    return metrics


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    events, sec_quality = normalize_sec_events()
    (OUT / "sec-events.json").write_text(json.dumps({"schema_version": "1", "events": events, "quality": sec_quality}, indent=2), encoding="utf-8")
    history, price_quality = normalize_prices()
    news = NewsArchive.from_file(ROOT / "backend" / "tests" / "fixtures" / "moomoo_news_2026-11-17.json")
    windows = {"development": (date(2025, 6, 30), date(2026, 3, 31)), "holdout": (date(2026, 4, 1), date(2026, 11, 16))}
    results: dict[str, Any] = {}
    for name, (start, end) in windows.items():
        window_results = {
            "catalyst": simulate_catalyst(history, events, start, end),
            "SPY": simulate_buy_and_hold(history, "SPY", start, end),
            "QQQ": simulate_buy_and_hold(history, "QQQ", start, end),
            "cash": simulate_cash(history, start, end),
            "momentum-v1": simulate_legacy(history, news, "momentum-v1", start, end),
            "news-catalyst-v1": simulate_legacy(history, news, "news-catalyst-v1", start, end),
        }
        results[name] = write_window(name, window_results)
    output = {
        "schema_version": "1",
        "strategy_version": "sec-earnings-relative-momentum-v1",
        "protocol_sha256": sha256(OUT / "protocol.json"),
        "price_data_sha256": sha256(OUT / "normalized-prices.json"),
        "event_data_sha256": sha256(OUT / "sec-events.json"),
        "data_quality": {"sec": sec_quality, "prices": price_quality},
        "results": results,
    }
    (OUT / "results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({
        "original_events": sum(item["original_item_2_02_events"] for item in sec_quality["coverage"].values()),
        "amendments": sum(item["item_2_02_amendments"] for item in sec_quality["coverage"].values()),
        "excluded_events": len(sec_quality["excluded_events"]),
        "common_sessions": price_quality["common_sessions"],
        "results": results,
    }, indent=2))


if __name__ == "__main__":
    main()
