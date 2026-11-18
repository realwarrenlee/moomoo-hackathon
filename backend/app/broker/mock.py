from datetime import datetime
from decimal import Decimal

from app.models.contracts import (
    AccountSnapshot,
    Fill,
    OpenOrder,
    OrderRecord,
    OrderRequest,
    OrderSide,
    OrderStatus,
    Position,
)


class BrokerTimeoutError(Exception):
    pass


class MockPaperBroker:
    def __init__(
        self,
        account: AccountSnapshot,
        auto_fill: bool = True,
        fill_quantity: int | None = None,
        accept_then_timeout: bool = False,
    ) -> None:
        if account.environment != "paper":
            raise ValueError("MockPaperBroker accepts paper accounts only")
        self._account = account
        self._auto_fill = auto_fill
        self._fill_quantity = fill_quantity
        self._accept_then_timeout = accept_then_timeout
        self._orders: dict[str, OrderRecord] = {}
        self._snapshot_sequence = 0
        self.submission_calls = 0
        self.fail_next_submission = False

    def get_account_snapshot(self) -> AccountSnapshot:
        return self._account

    def get_order(self, client_order_key: str) -> OrderRecord | None:
        return self._orders.get(client_order_key)

    def submit_order(self, request: OrderRequest, now: datetime) -> OrderRecord:
        existing = self._orders.get(request.client_order_key)
        if existing is not None:
            return existing
        self.submission_calls += 1
        if self.fail_next_submission:
            self.fail_next_submission = False
            raise BrokerTimeoutError("simulated ambiguous broker timeout")
        if request.account_snapshot_id != self._account.snapshot_id:
            raise ValueError("order approval is bound to a stale account snapshot")

        broker_order_id = f"mock-order-{len(self._orders) + 1}"
        fill_quantity = 0
        if self._auto_fill:
            fill_quantity = request.quantity if self._fill_quantity is None else min(
                request.quantity, self._fill_quantity
            )
        fills = ()
        if fill_quantity:
            fills = (
                Fill(
                    broker_fill_id=f"{broker_order_id}-fill-1",
                    quantity=fill_quantity,
                    price=request.reference_price,
                    filled_at_utc=now,
                ),
            )

        remaining = request.quantity - fill_quantity
        if remaining == 0:
            status = OrderStatus.FILLED
        elif fill_quantity:
            status = OrderStatus.PARTIALLY_FILLED
        else:
            status = OrderStatus.ACKNOWLEDGED

        order = OrderRecord(
            client_order_key=request.client_order_key,
            proposal_id=request.proposal_id,
            paper_account_fingerprint=self._account.account_fingerprint,
            broker_order_id=broker_order_id,
            status=status,
            request=request,
            submitted_at_utc=now,
            last_broker_sync_utc=now,
            fills=fills,
        )
        self._orders[request.client_order_key] = order
        self._apply_order(request, fill_quantity, remaining, now)
        if self._accept_then_timeout:
            # Simulate the broker accepting the order while the client loses the response.
            self._accept_then_timeout = False
            raise BrokerTimeoutError("simulated timeout after broker acceptance")
        return order

    def _apply_order(self, request: OrderRequest, filled: int, remaining: int, now: datetime) -> None:
        positions = [item for item in self._account.positions if item.symbol != request.symbol]
        current = next(
            (item for item in self._account.positions if item.symbol == request.symbol),
            Position(symbol=request.symbol, quantity=0, market_value=Decimal("0")),
        )
        signed_fill = filled if request.side is OrderSide.BUY else -filled
        new_quantity = current.quantity + signed_fill
        if new_quantity < 0:
            raise ValueError("mock broker cannot create a short position")
        if new_quantity:
            positions.append(
                Position(
                    symbol=request.symbol,
                    quantity=new_quantity,
                    market_value=request.reference_price * new_quantity,
                )
            )

        notional = request.reference_price * filled
        cash_delta = -notional if request.side is OrderSide.BUY else notional
        cash = self._account.cash + cash_delta
        buying_power = self._account.buying_power + cash_delta
        open_orders = list(self._account.open_orders)
        if remaining:
            open_orders.append(
                OpenOrder(
                    symbol=request.symbol,
                    side=request.side,
                    remaining_quantity=remaining,
                    reference_price=request.reference_price,
                )
            )
        equity = cash + sum((item.market_value for item in positions), Decimal("0"))
        self._snapshot_sequence += 1
        self._account = self._account.model_copy(
            update={
                "snapshot_id": f"mock-snapshot-{self._snapshot_sequence}",
                "cash": cash,
                "buying_power": buying_power,
                "equity": equity,
                "positions": tuple(positions),
                "open_orders": tuple(open_orders),
                "as_of_utc": now,
                "reconciled": True,
            }
        )
