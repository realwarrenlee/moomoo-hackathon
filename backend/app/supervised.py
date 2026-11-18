"""Composition boundary for one operator-supervised paper order.

This module only assembles existing components. It does not enable writes on its
own: callers must explicitly request an enabled transport and are responsible
for the durable approval and exact-key confirmation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.broker.account_lock import AccountLock
from app.broker.moomoo_orders import MoomooOrderTransport, MoomooPaperBroker
from app.broker.moomoo_quotes import MoomooQuoteFeed
from app.broker.moomoo_rest import MoomooRestBroker, MoomooRestClient
from app.ledger.store import SQLiteLedger
from app.research.data import UNIVERSE
from app.research.instruments import INSTRUMENTS
from app.risk.policy import RiskGate
from app.service import TradingService


@dataclass(frozen=True)
class SupervisedExecution:
    service: TradingService
    quote_feed: MoomooQuoteFeed
    broker: MoomooPaperBroker
    reads: MoomooRestBroker
    ledger: SQLiteLedger
    risk_gate: RiskGate
    order_writes_enabled: bool


def build_supervised_execution(
    oauth: Any,
    account_lock: AccountLock,
    ledger: SQLiteLedger,
    *,
    order_writes_enabled: bool = False,
    http: httpx.Client | None = None,
    clock: Callable[[], datetime] | None = None,
) -> SupervisedExecution:
    if not isinstance(order_writes_enabled, bool):
        raise ValueError("order write state must be explicit")
    client = MoomooRestClient(oauth, http=http)
    reads = MoomooRestBroker(client, account_lock, ledger, clock=clock)
    quote_feed = MoomooQuoteFeed(client)
    transport = MoomooOrderTransport(
        oauth,
        http=http,
        order_writes_enabled=order_writes_enabled,
    )
    broker = MoomooPaperBroker(
        reads,
        ledger,
        transport,
        expected_account_fingerprint=account_lock.expected_fingerprint,
        account_market_id=account_lock.expected_market_id,
        clock=clock,
    )
    risk_gate = RiskGate(
        expected_account_fingerprint=account_lock.expected_fingerprint,
        allowed_symbols=frozenset(UNIVERSE),
        leverage_by_symbol={
            symbol: instrument.leverage for symbol, instrument in INSTRUMENTS.items()
        },
        allow_leveraged=False,
    )
    service = TradingService(
        broker=broker,
        risk_gate=risk_gate,
        ledger=ledger,
        order_writes_enabled=order_writes_enabled,
    )
    return SupervisedExecution(
        service=service,
        quote_feed=quote_feed,
        broker=broker,
        reads=reads,
        ledger=ledger,
        risk_gate=risk_gate,
        order_writes_enabled=order_writes_enabled,
    )
