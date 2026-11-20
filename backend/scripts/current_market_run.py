from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.broker.account_lock import AccountLock
from app.broker.moomoo_auth import FileTokenStore, MoomooOAuth, default_token_path
from app.broker.moomoo_quotes import (
    CLOCK_SKEW_TOLERANCE_SECONDS,
    MoomooQuoteFeed,
    QuoteObservation,
)
from app.broker.moomoo_rest import MoomooRestBroker, MoomooRestClient
from app.cli import load_local_env
from app.ledger.store import SQLiteLedger
from app.models.contracts import AccountSnapshot, ControlState, Quote
from app.qoder_tools import CurrentMarketContext, QoderToolService
from app.research.data import MarketHistory
from app.research.instruments import CANDIDATE_SYMBOLS
from app.research.strategy import STRATEGY_VERSION, MIN_COMPLETED_SESSIONS
from app.trading_mode import exposure_policy_for_activation
from scripts.qoder_readonly_run import (
    QoderReadonlyRunner,
    QoderRunError,
    _load_local_qoder_credentials,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "backend" / "config" / "current_market.json"
NY = ZoneInfo("America/New_York")


class CollectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Collection:
    mode: str
    collected_at_utc: datetime
    quotes: tuple[QuoteObservation, ...]
    quote_map: dict[str, Quote]
    account: AccountSnapshot
    masked_id: str
    today_orders: tuple[object, ...]
    history_orders: tuple[object, ...]
    bars_path: Path
    history: MarketHistory
    payload: dict[str, object]


def _previous_weekday(value: date) -> date:
    candidate = value - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _observation_quote(observation: QuoteObservation) -> Quote:
    return Quote(
        symbol=observation.symbol,
        price=observation.price,
        as_of_utc=observation.as_of_utc,
        regular_session_open=observation.regular_session_open,
    )


def _load_bars(
    path: Path,
    now: datetime,
    window: str = "session",
    expected_session: date | None = None,
) -> tuple[MarketHistory, dict[str, object]]:
    if window not in {"session", "post-close"}:
        raise CollectionError("bar validation window is not supported")
    history = MarketHistory.from_file(path)
    missing = sorted(set(CANDIDATE_SYMBOLS) - set(history.symbols))
    if missing:
        raise CollectionError(f"bar file is missing symbols: {', '.join(missing)}")
    last_dates = {symbol: history.bars(symbol)[-1].session_date for symbol in CANDIDATE_SYMBOLS}
    if len(set(last_dates.values())) != 1:
        raise CollectionError("bar file symbols do not share the same last session")
    last_session = next(iter(last_dates.values()))
    now_et = now.astimezone(NY)
    today_et = now_et.date()
    # The scheduler resolves the prior completed session against the provider
    # trading calendar (holidays included); the weekday fallback only applies
    # when no calendar-aware session is supplied.
    expected = (
        expected_session if expected_session is not None else _previous_weekday(today_et)
    )
    if window == "session":
        if last_session >= today_et:
            raise CollectionError("bar file contains an incomplete current-session bar")
        if last_session != expected:
            raise CollectionError(
                f"bar history ends {last_session}; expected the prior completed session {expected}"
            )
    else:
        if last_session > today_et:
            raise CollectionError("bar history contains a future session")
        if last_session == today_et and now_et.time() < time(16, 0):
            raise CollectionError("the current US session has not closed")
        if (today_et - last_session).days > 5:
            raise CollectionError(
                f"bar history ends {last_session}; no recent completed session is available"
            )
    for symbol in CANDIDATE_SYMBOLS:
        bars = history.bars(symbol)
        if len(bars) < MIN_COMPLETED_SESSIONS:
            raise CollectionError(
                f"bar history for {symbol} has fewer than {MIN_COMPLETED_SESSIONS} sessions"
            )
        if window == "session" and any(bar.session_date >= today_et for bar in bars):
            raise CollectionError(f"bar history for {symbol} contains a current-session bar")
        if any(bar.session_date > today_et for bar in bars):
            raise CollectionError(f"bar history for {symbol} contains a future-session bar")
    fetched_at = _parse_utc(history.source.get("fetched_at_utc"))
    if fetched_at is None:
        raise CollectionError("bar source has no timezone-aware fetch timestamp")
    if fetched_at > now + timedelta(minutes=5):
        raise CollectionError("bar source fetch timestamp is in the future")
    fetch_age_hours = (now - fetched_at).total_seconds() / 3600
    if fetch_age_hours > 96:
        raise CollectionError("bar source fetch is more than 96 hours old")
    validation = {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "source": history.source,
        "window": window,
        "today_session_et": today_et.isoformat(),
        "last_completed_session": last_session.isoformat(),
        "today_bar_available": last_session == today_et,
        "expected_previous_session": expected.isoformat(),
        "bars_per_symbol": {symbol: len(history.bars(symbol)) for symbol in CANDIDATE_SYMBOLS},
        "fetch_age_hours": round(fetch_age_hours, 2),
        "complete": True,
    }
    return history, validation


def collect(mode: str, bars_path: Path) -> Collection:
    load_local_env(ROOT / ".env")
    if os.environ.get("ORDER_WRITES_ENABLED", "false").strip().lower() not in {"false", "0", "no", ""}:
        raise CollectionError("ORDER_WRITES_ENABLED must remain false")
    fingerprint = os.environ.get("COMPETITION_ACCOUNT_FINGERPRINT", "").strip()
    if not fingerprint:
        raise CollectionError("competition account fingerprint is not configured")
    store = FileTokenStore(default_token_path())
    record = store.load()
    if record is None:
        raise CollectionError("Moomoo read authorization is required")
    if record.has_trade_write():
        raise CollectionError("stored authorization contains trade:write; refusing")
    if not record.has_required_scopes():
        raise CollectionError("stored authorization lacks required read scopes")

    ledger = SQLiteLedger(ROOT / "data" / "mootrade.db")
    account_lock = AccountLock.from_env(os.environ)
    oauth = MoomooOAuth(store, open_browser=None)
    client = MoomooRestClient(oauth)
    broker = MoomooRestBroker(client, account_lock, ledger)
    feed = MoomooQuoteFeed(client)

    now = datetime.now(UTC)
    observations: list[QuoteObservation] = []
    quote_map: dict[str, Quote] = {}
    for symbol in CANDIDATE_SYMBOLS:
        if mode == "session":
            quote = feed.get_quote(symbol, now)
            if not quote.regular_session_open:
                raise CollectionError(f"{symbol} is not in the regular US session")
            # get_quote already validated NORMAL, unsuspended, and the AFTERNOON state.
            observation = QuoteObservation(
                symbol=symbol,
                price=quote.price,
                as_of_utc=quote.as_of_utc,
                age_seconds=max(0.0, (now - quote.as_of_utc).total_seconds()),
                sec_status="NORMAL",
                suspended=False,
                market_state="AFTERNOON",
                regular_session_open=True,
            )
        else:
            observation = feed.observe_quote(symbol, now)
            quote = _observation_quote(observation)
        observations.append(observation)
        quote_map[symbol] = quote

    identity = broker.account_identity()
    account = broker.get_account_snapshot()
    account_age = (datetime.now(UTC) - account.as_of_utc).total_seconds()
    if account.environment != "paper":
        raise CollectionError("account snapshot is not a paper account")
    if account.account_fingerprint != fingerprint:
        raise CollectionError("account snapshot does not match the configured competition fingerprint")
    if account_age < -CLOCK_SKEW_TOLERANCE_SECONDS or account_age > 60:
        raise CollectionError("account snapshot is stale or future-dated at collection time")
    account_age = max(0.0, account_age)
    if not account.reconciled or account.unknown_orders:
        raise CollectionError("account state is not reconciled")

    today_orders = broker.get_today_orders()
    history_orders = broker.get_order_history()
    history, bar_validation = _load_bars(bars_path, now, mode)

    payload: dict[str, object] = {
        "mode": mode,
        "provenance": "CURRENT_MARKET_READ_ONLY",
        "collected_at_utc": now.isoformat(),
        "us_eastern_time": now.astimezone(NY).isoformat(),
        "quotes": [
            {
                "symbol": item.symbol,
                "price": str(item.price),
                "data_time_utc": item.as_of_utc.isoformat(),
                "age_seconds": round(item.age_seconds, 1),
                "sec_status": item.sec_status,
                "suspended": item.suspended,
                "market_state": item.market_state,
                "regular_session_open": item.regular_session_open,
                "provenance": "LIVE_BROKER_READ",
            }
            for item in observations
        ],
        "account": {
            "masked_id": identity.masked_id,
            "equity": str(account.equity),
            "cash": str(account.cash),
            "buying_power": str(account.buying_power),
            "day_start_equity": str(account.day_start_equity),
            "positions_count": len(account.positions),
            "open_orders_count": len(account.open_orders),
            "reconciled": account.reconciled,
            "unknown_orders": account.unknown_orders,
            "as_of_utc": account.as_of_utc.isoformat(),
            "age_seconds": round(account_age, 1),
            "provenance": "LIVE_BROKER_READ",
        },
        "positions": [
            {"symbol": item.symbol, "quantity": item.quantity, "market_value": str(item.market_value)}
            for item in account.positions
        ],
        "orders": {
            "today_count": len(today_orders),
            "history_count": len(history_orders),
            "open_count": len(account.open_orders),
        },
        "history": bar_validation,
        "validations": {
            "account_verified_paper": True,
            "account_reconciled": True,
            "account_age_seconds": round(account_age, 1),
            "regular_session_required": mode == "session",
            "quotes_collected": len(observations),
            "history_complete": True,
            "order_writes_enabled": False,
        },
    }
    return Collection(
        mode=mode,
        collected_at_utc=now,
        quotes=tuple(observations),
        quote_map=quote_map,
        account=account,
        masked_id=identity.masked_id,
        today_orders=today_orders,
        history_orders=history_orders,
        bars_path=bars_path,
        history=history,
        payload=payload,
    )


def _control_state(ledger: SQLiteLedger) -> ControlState:
    return ControlState(
        order_writes_enabled=False,
        kill_switch_engaged=ledger.kill_switch_engaged(),
        circuit_breaker_open=False,
        first_order_approved=False,
    )


def _latest_bars_file() -> Path:
    candidates = sorted(
        (ROOT / "evidence" / "current-market").glob("*/daily-bars.json"),
        key=lambda item: item.parent.name,
        reverse=True,
    )
    if not candidates:
        raise CollectionError("no current-market daily-bar snapshot was found")
    return candidates[0]


def _write_collection(collection: Collection, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"collection-{collection.collected_at_utc:%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(collection.payload, indent=2), encoding="utf-8")
    return path


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CollectionError("current-market config must be a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the current-market read-only three-agent workflow")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--bars", type=Path)
    parser.add_argument("--window", choices=["session", "post-close"], default="session")
    parser.add_argument("--strategy", choices=[STRATEGY_VERSION], default=None)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evidence" / "qoder")
    parser.add_argument("--collection-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    config = _load_config(args.config)
    bars_path = args.bars or _latest_bars_file()
    collection_dir = args.collection_dir or (ROOT / "evidence" / "current-market" / datetime.now(NY).date().isoformat())
    try:
        collection = collect(args.window, bars_path)
        collection_path = _write_collection(collection, collection_dir)
        print(f"Collected: {collection_path}")
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        collection_dir.mkdir(parents=True, exist_ok=True)
        failure = collection_dir / f"collection-failed-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
        failure.write_text(
            json.dumps(
                {
                    "mode": args.window,
                    "provenance": "CURRENT_MARKET_READ_ONLY",
                    "status": "ABSTAINED",
                    "reason": message,
                    "recorded_at_utc": datetime.now(UTC).isoformat(),
                    "order_writes_enabled": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"ABSTAINED: {message}")
        print(f"Failure evidence: {failure}")
        return 1

    strategy = args.strategy or str(config.get("strategy", STRATEGY_VERSION))
    agent_ids = {
        "coordinator": str(config["coordinator_agent_id"]),
        "researcher": str(config["researcher_agent_id"]),
        "auditor": str(config["auditor_agent_id"]),
    }
    load_local_env(ROOT / ".env")
    _load_local_qoder_credentials()
    import httpx
    from qca import Managed

    store = FileTokenStore(default_token_path())
    ledger = SQLiteLedger(ROOT / "data" / "mootrade.db")
    fingerprint = os.environ["COMPETITION_ACCOUNT_FINGERPRINT"].strip()
    oauth = MoomooOAuth(store, open_browser=None)
    client = MoomooRestClient(oauth)
    broker = MoomooRestBroker(client, AccountLock.from_env(os.environ), ledger)
    feed = MoomooQuoteFeed(client)
    control = _control_state(ledger)

    def account_provider() -> AccountSnapshot:
        return broker.get_account_snapshot()

    if args.window == "session":
        def quote_provider(symbol: str) -> Quote:
            return feed.get_quote(symbol, datetime.now(UTC))
    else:
        def quote_provider(symbol: str) -> Quote:
            return _observation_quote(feed.observe_quote(symbol, datetime.now(UTC)))

    tools = QoderToolService(
        collection.history,
        fingerprint,
        current=CurrentMarketContext(
            decision_time_utc=collection.collected_at_utc,
            fingerprint=fingerprint,
            account_provider=account_provider,
            quote_provider=quote_provider,
            control=control,
        ),
        clock=lambda: datetime.now(UTC),
        exposure_policy=exposure_policy_for_activation(ledger.latest_trading_activation()),
    )
    runner = QoderReadonlyRunner(
        client=Managed(
            http_client=httpx.Client(follow_redirects=False, trust_env=False),
            max_retries=0,
        ),
        tools=tools,
        workspace_id=str(config["workspace_id"]),
        environment_id=str(config["environment_id"]),
        agent_ids=agent_ids,
        output_dir=args.output_dir,
        ledger=ledger,
        mode="CURRENT_MARKET_READ_ONLY",
        notice=(
            "Current read-only Moomoo evidence captured during/after the regular session. "
            "No order was submitted, approved or filled."
        ),
        data_collection=collection.payload,
    )
    try:
        result = runner.run(strategy)  # type: ignore[arg-type]
    except QoderRunError as exc:
        print(f"Qoder run failed closed: {exc}")
        return 1
    print(f"Run ID: {result.run_id}")
    print(f"Status: {result.status}; outcome: {result.outcome}")
    print(f"Report: {result.report_path}")
    return 0 if result.status == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
